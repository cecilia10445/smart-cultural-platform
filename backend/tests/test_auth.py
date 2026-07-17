import json

from werkzeug.security import check_password_hash

from conftest import login


def test_legacy_login_migrates_password_and_returns_pyjwt_string(app_module, client, tmp_path):
    token = login(client)
    assert isinstance(token, str)
    user = app_module.users_data["users"][0]
    assert "password" not in user
    assert check_password_hash(user["password_hash"], "legacy-password")
    persisted = json.loads((tmp_path / "data" / "test_users.json").read_text(encoding="utf-8"))
    assert "password" not in persisted["users"][0]


def test_registration_hashes_password_and_forces_user_role(app_module, client):
    response = client.post("/api/register", json={"username": "newuser", "password": "secure123", "role": "user"})
    assert response.status_code == 200
    user = next(item for item in app_module.users_data["users"] if item["username"] == "newuser")
    assert user["role"] == "user"
    assert "password" not in user
    assert check_password_hash(user["password_hash"], "secure123")


def test_public_admin_registration_is_forbidden(app_module, client):
    response = client.post("/api/register", json={"username": "badadmin", "password": "secure123", "role": "admin"})
    body = response.get_json()
    assert response.status_code == 403
    assert body["code"] == "ADMIN_REGISTRATION_FORBIDDEN"
    assert not any(item["username"] == "badadmin" for item in app_module.users_data["admins"])


def test_login_does_not_expose_password_or_hash(app_module, client):
    body = client.post("/api/login", json={"username": "admin", "password": "admin-password", "role": "admin"}).get_json()
    assert body["status"] == "success"
    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]
