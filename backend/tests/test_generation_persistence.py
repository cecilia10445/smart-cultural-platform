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
    monkeypatch.setattr(app_module, "persist_generated_image", lambda *_args, **_kwargs: "/static/images/test.png")
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
    def __init__(self, lastrowid=99, execute_error=None, rows=None):
        self.lastrowid = lastrowid
        self.execute_error = execute_error
        self.rows = [] if rows is None else rows

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _query, _params=None):
        if self.execute_error:
            raise self.execute_error

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def cursor(self, *args, **kwargs):
        self.cursor_args = args
        self.cursor_kwargs = kwargs
        return self._cursor

    def close(self):
        self.closed = True


def test_execute_insert_returns_lastrowid_and_releases_pooled_connection(monkeypatch):
    connection = FakeConnection(FakeCursor(lastrowid=1234))
    service = MySQLService()
    monkeypatch.setattr(service, "_borrow_connection", lambda: connection)

    result = service.execute_insert("INSERT INTO generation_logs (user_id) VALUES (%s)", ("U1",))

    assert result == 1234
    assert connection.closed is True


def test_execute_insert_does_not_retry_integrity_errors(monkeypatch, caplog):
    connection = FakeConnection(FakeCursor(execute_error=pymysql.err.IntegrityError(1062, "duplicate")))
    connection_attempts = []
    service = MySQLService()
    monkeypatch.setattr(service, "_borrow_connection", lambda: connection_attempts.append(True) or connection)

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
    monkeypatch.setattr("backend.services.mysql_service.time.sleep", lambda _seconds: None)
    service = MySQLService()
    monkeypatch.setattr(service, "_borrow_connection", lambda: connections.pop(0))

    result = service.execute_insert("INSERT INTO generation_logs (user_id) VALUES (%s)", ("U1",), max_retries=1)

    assert result == 88
    assert connections == []


def test_mysql_service_configures_sqlalchemy_connection_pool():
    service = MySQLService()

    assert service.engine is not None
    assert service.engine.pool._pre_ping is True
    assert service.engine.pool.size() == 5

    service.close()


def test_connect_uses_and_releases_a_pooled_connection(monkeypatch):
    connection = FakeConnection(FakeCursor())
    service = MySQLService()
    monkeypatch.setattr(service, "_borrow_connection", lambda: connection)

    assert service.connect() is True
    assert connection.closed is True


def test_execute_query_uses_dict_cursor_and_preserves_dict_rows(monkeypatch):
    expected = [{"log_id": 1, "title": "测试标题"}]
    connection = FakeConnection(FakeCursor(rows=expected))
    service = MySQLService()
    monkeypatch.setattr(service, "_borrow_connection", lambda: connection)

    result = service.execute_query("SELECT id AS log_id, title FROM generation_logs")

    assert result == expected
    assert connection.cursor_args == (pymysql.cursors.DictCursor,)
    assert connection.closed is True
