import importlib
import json
import sys

import pytest


@pytest.fixture()
def app_module(monkeypatch, tmp_path):
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret")
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    sys.modules.pop("backend.app", None)
    app = importlib.import_module("backend.app")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    app.backend_dir = str(tmp_path)
    app.users_data = {
        "users": [{"user_id": "U1", "username": "legacy", "password": "legacy-password", "role": "user", "name": "Legacy"}],
        "admins": [{"user_id": "A1", "username": "admin", "password_hash": app.generate_password_hash("admin-password"), "role": "admin", "name": "Admin"}],
    }
    (data_dir / "test_users.json").write_text(json.dumps(app.users_data), encoding="utf-8")
    app.app.config.update(TESTING=True)
    return app


@pytest.fixture()
def client(app_module):
    return app_module.app.test_client()


def login(client, username="legacy", password="legacy-password", role="user"):
    response = client.post("/api/login", json={"username": username, "password": password, "role": role})
    assert response.status_code == 200
    return response.get_json()["token"]
