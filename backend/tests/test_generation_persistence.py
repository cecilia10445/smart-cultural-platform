import logging

import pymysql

from backend.services.mysql_service import MySQLService
from backend.tests.conftest import login


class StubImageResponse:
    status_code = 503


class StubMySQLService:
    def __init__(self, insert_result=41, insert_error=None, available=True):
        self.insert_result = insert_result
        self.insert_error = insert_error
        self.available = available
        self.connect_calls = 0
        self.insert_calls = []

    def connect(self):
        self.connect_calls += 1
        return self.available

    def execute_query(self, query, params=None):
        if query.lstrip().upper().startswith("SELECT"):
            return []
        self.insert_calls.append((query, params))
        if self.insert_error:
            raise self.insert_error
        return self.insert_result

    def execute_insert(self, query, params=None):
        self.insert_calls.append((query, params))
        if self.insert_error:
            raise self.insert_error
        return self.insert_result


def post_generation(app_module, client, monkeypatch, mysql_service, prompt="safe topic"):
    token = login(client)
    monkeypatch.setattr(app_module, "mysql_service", mysql_service)
    monkeypatch.setattr(app_module, "generate_content", lambda *_: ("https://example.invalid/image.png", "title", "content"))
    monkeypatch.setattr(app_module, "log_event", lambda *_: True)
    monkeypatch.setattr("requests.get", lambda *_args, **_kwargs: StubImageResponse())
    return client.post(
        "/api/generate",
        json={"prompt": prompt, "style": "ink"},
        headers={"Authorization": f"Bearer {token}"},
    )


def test_generate_returns_real_insert_id_and_inserts_once(app_module, client, monkeypatch):
    service = StubMySQLService(insert_result=731)

    response = post_generation(app_module, client, monkeypatch, service)

    assert response.status_code == 200
    assert response.get_json()["status"] == "success"
    assert response.get_json()["log_id"] == 731
    assert len(service.insert_calls) == 1


def test_generate_rejects_none_insert_result(app_module, client, monkeypatch):
    response = post_generation(app_module, client, monkeypatch, StubMySQLService(insert_result=None))

    assert response.status_code == 503
    assert response.get_json()["status"] != "success"
    assert response.get_json()["code"] == "GENERATION_PERSIST_FAILED"
    assert "log_id" not in response.get_json()


def test_generate_rejects_insert_exception_without_temporary_log_id(app_module, client, monkeypatch):
    service = StubMySQLService(insert_error=RuntimeError("database rejected insert"))

    response = post_generation(app_module, client, monkeypatch, service)

    assert response.status_code == 503
    assert response.get_json()["code"] == "GENERATION_PERSIST_FAILED"
    assert "log_id" not in response.get_json()


def test_unknown_age_and_gender_are_persisted_as_null(app_module, client, monkeypatch):
    service = StubMySQLService()

    response = post_generation(app_module, client, monkeypatch, service)

    assert response.status_code == 200
    _, params = service.insert_calls[0]
    assert params[12] is None
    assert params[13] is None
    assert params[15] == "production"


def test_generate_checks_mysql_once(app_module, client, monkeypatch):
    service = StubMySQLService()

    response = post_generation(app_module, client, monkeypatch, service)

    assert response.status_code == 200
    assert service.connect_calls == 1


def test_generate_checks_mysql_before_model_call(app_module, client, monkeypatch):
    service = StubMySQLService(available=False)
    model_calls = []
    monkeypatch.setattr(app_module, "mysql_service", service)
    monkeypatch.setattr(app_module, "generate_content", lambda *_: model_calls.append(True))
    token = login(client)

    response = client.post(
        "/api/generate",
        json={"prompt": "topic", "style": "ink"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 503
    assert response.get_json()["code"] == "MYSQL_UNAVAILABLE"
    assert model_calls == []
    assert service.connect_calls == 1


def test_persistence_failure_logs_do_not_expose_sensitive_values(app_module, client, monkeypatch, capsys):
    prompt = "private-prompt-that-must-not-be-logged"
    error = RuntimeError("password=hunter2 token=full-token params=('private-prompt-that-must-not-be-logged',)")

    response = post_generation(app_module, client, monkeypatch, StubMySQLService(insert_error=error), prompt)
    output = capsys.readouterr().out

    assert response.status_code == 503
    assert prompt not in output
    assert "hunter2" not in output
    assert "full-token" not in output
    assert "params=" not in output


class FakeCursor:
    def __init__(self, lastrowid=99, execute_error=None):
        self.lastrowid = lastrowid
        self.execute_error = execute_error

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _query, _params):
        if self.execute_error:
            raise self.execute_error


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


def test_execute_insert_returns_lastrowid_and_closes_connection(monkeypatch):
    connection = FakeConnection(FakeCursor(lastrowid=1234))
    monkeypatch.setattr(pymysql, "connect", lambda **_kwargs: connection)
    service = MySQLService()

    result = service.execute_insert("INSERT INTO generation_logs (user_id) VALUES (%s)", ("U1",))

    assert result == 1234
    assert connection.closed is True


def test_execute_insert_does_not_retry_integrity_errors(monkeypatch, caplog):
    connection = FakeConnection(FakeCursor(execute_error=pymysql.err.IntegrityError(1062, "duplicate")))
    connection_attempts = []
    monkeypatch.setattr(pymysql, "connect", lambda **_kwargs: connection_attempts.append(True) or connection)
    service = MySQLService()

    with caplog.at_level(logging.ERROR):
        result = service.execute_insert("INSERT INTO generation_logs (user_id) VALUES (%s)", ("private-value",))

    assert result is None
    assert len(connection_attempts) == 1
    assert connection.closed is True
    assert "private-value" not in caplog.text


def test_execute_insert_retries_only_transient_connection_errors(monkeypatch):
    connections = [
        FakeConnection(FakeCursor(execute_error=pymysql.err.OperationalError(2013, "connection lost"))),
        FakeConnection(FakeCursor(lastrowid=88)),
    ]
    monkeypatch.setattr(pymysql, "connect", lambda **_kwargs: connections.pop(0))
    monkeypatch.setattr("backend.services.mysql_service.time.sleep", lambda _seconds: None)
    service = MySQLService()

    result = service.execute_insert("INSERT INTO generation_logs (user_id) VALUES (%s)", ("U1",), max_retries=1)

    assert result == 88
    assert connections == []
