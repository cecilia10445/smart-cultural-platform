import importlib
import json
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class AvailableMySQLStub:
    """Default unit-test database boundary; individual tests replace as needed."""

    def connect(self):
        return True


@pytest.fixture()
def app_module(monkeypatch, tmp_path):
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret")
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("TEST_USERS_DATA_PATH", str(data_dir / "test_users.json"))
    sys.modules.pop("backend.routes.api", None)
    app = importlib.import_module("backend.routes.api")
    app.backend_dir = str(tmp_path)
    app.users_data = {
        "users": [{"user_id": "U1", "username": "legacy", "password": "legacy-password", "role": "user", "name": "Legacy"}],
        "admins": [{"user_id": "A1", "username": "admin", "password_hash": app.generate_password_hash("admin-password"), "role": "admin", "name": "Admin"}],
    }
    (data_dir / "test_users.json").write_text(json.dumps(app.users_data), encoding="utf-8")
    app.mysql_service = AvailableMySQLStub()
    return app


@pytest.fixture()
def client(app_module):
    application = FastAPI()
    from backend.routes.auth import router as auth_router
    from backend.routes.dashboard import router as dashboard_router
    from backend.routes.generation import router as generation_router
    from backend.routes.health import router as health_router
    from backend.routes.system import router as system_router
    from backend.routes.users import router as users_router
    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(system_router)
    application.include_router(users_router)
    application.include_router(dashboard_router)
    application.include_router(generation_router)
    return TestClient(application)


def login(client, username="legacy", password="legacy-password", role="user"):
    response = client.post("/api/login", json={"username": username, "password": password, "role": role})
    assert response.status_code == 200
    return response.get_json()["token"]
