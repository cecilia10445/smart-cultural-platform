from types import SimpleNamespace


class MySQLProbe:
    def __init__(self, available):
        self.available = available
        self.connect_calls = 0

    def connect(self):
        self.connect_calls += 1
        return self.available


class ForbiddenMySQLProbe:
    def connect(self):
        raise AssertionError("liveness must not access MySQL")


class RaisingMySQLProbe:
    def __init__(self):
        self.connect_calls = 0

    def connect(self):
        self.connect_calls += 1
        raise RuntimeError(
            "mysql probe failed password=synthetic-secret connection=private"
        )


def settings_with_model_key(value):
    return SimpleNamespace(dashscope_api_key=value)


def test_live_and_legacy_health_do_not_access_mysql(app_module, client, monkeypatch):
    monkeypatch.setattr(app_module, "mysql_service", ForbiddenMySQLProbe())

    live_response = client.get("/api/health/live")
    legacy_response = client.get("/api/health")

    assert live_response.status_code == 200
    assert live_response.get_json()["status"] == "alive"
    assert legacy_response.status_code == 200
    assert legacy_response.get_json()["status"] == "alive"


def test_ready_when_mysql_and_generation_model_are_available(app_module, client, monkeypatch):
    mysql_probe = MySQLProbe(True)
    monkeypatch.setattr(app_module, "mysql_service", mysql_probe)
    monkeypatch.setattr(app_module, "load_settings", lambda: settings_with_model_key("configured-test-key"))

    response = client.get("/api/health/ready")
    body = response.get_json()

    assert response.status_code == 200
    assert body == {
        "status": "ready",
        "checks": {
            "mysql": "ready",
            "generation_model": "configured",
            "hive": "optional",
        },
    }
    assert mysql_probe.connect_calls == 1
    assert "configured-test-key" not in response.get_data(as_text=True)


def test_ready_reports_mysql_unavailable_without_details(app_module, client, monkeypatch):
    mysql_probe = MySQLProbe(False)
    monkeypatch.setattr(app_module, "mysql_service", mysql_probe)
    monkeypatch.setattr(app_module, "load_settings", lambda: settings_with_model_key("configured-test-key"))

    response = client.get("/api/health/ready")

    assert response.status_code == 503
    assert response.get_json()["status"] == "unavailable"
    assert response.get_json()["checks"]["mysql"] == "unavailable"
    assert response.get_json()["checks"]["generation_model"] == "configured"
    assert "configured-test-key" not in response.get_data(as_text=True)


def test_ready_handles_mysql_probe_exception_without_details(app_module, client, monkeypatch):
    mysql_probe = RaisingMySQLProbe()
    model_key = "configured-synthetic-model-key"
    monkeypatch.setattr(app_module, "mysql_service", mysql_probe)
    monkeypatch.setattr(app_module, "load_settings", lambda: settings_with_model_key(model_key))

    response = client.get("/api/health/ready")
    response_text = response.get_data(as_text=True)

    assert response.status_code == 503
    assert response.get_json() == {
        "status": "unavailable",
        "checks": {
            "mysql": "unavailable",
            "generation_model": "configured",
            "hive": "optional",
        },
    }
    assert mysql_probe.connect_calls == 1
    assert "synthetic-secret" not in response_text
    assert "password=" not in response_text
    assert "connection=private" not in response_text
    assert model_key not in response_text


def test_ready_reports_generation_model_unconfigured(app_module, client, monkeypatch):
    mysql_probe = MySQLProbe(True)
    monkeypatch.setattr(app_module, "mysql_service", mysql_probe)
    monkeypatch.setattr(app_module, "load_settings", lambda: settings_with_model_key(None))

    response = client.get("/api/health/ready")

    assert response.status_code == 503
    assert response.get_json() == {
        "status": "unavailable",
        "checks": {
            "mysql": "ready",
            "generation_model": "unavailable",
            "hive": "optional",
        },
    }
