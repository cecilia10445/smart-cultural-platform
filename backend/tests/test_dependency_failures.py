from conftest import login


class UnavailableService:
    def get_user_history(self, *args, **kwargs):
        return None

    def get_dashboard_stats(self, *args, **kwargs):
        return None

    def get_user_profile_dashboard(self, *args, **kwargs):
        return None

    def get_personalized_recommendations(self, *args, **kwargs):
        return None


def test_history_reports_unavailable_when_all_data_services_fail(app_module, client, monkeypatch):
    token = login(client)
    monkeypatch.setattr(app_module, "mysql_service", UnavailableService())
    monkeypatch.setattr(app_module, "hive_service", UnavailableService())
    response = client.get("/api/user/history", headers={"Authorization": f"Bearer {token}"})
    body = response.get_json()
    assert response.status_code == 503
    assert body["status"] == "unavailable"


def test_dashboard_reports_unavailable_when_all_data_services_fail(app_module, client, monkeypatch):
    token = login(client, "admin", "admin-password", "admin")
    monkeypatch.setattr(app_module, "mysql_service", UnavailableService())
    monkeypatch.setattr(app_module, "hive_service", UnavailableService())
    response = client.get("/api/dashboard/stats", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 503
    assert response.get_json()["status"] == "unavailable"


def test_user_profile_dashboard_does_not_return_fabricated_data(app_module, client, monkeypatch):
    token = login(client, "admin", "admin-password", "admin")
    monkeypatch.setattr(app_module, "mysql_service", UnavailableService())
    monkeypatch.setattr(app_module, "hive_service", UnavailableService())
    response = client.get("/api/dashboard/user-profile", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 503
    assert response.get_json()["status"] == "unavailable"


def test_recommendations_do_not_return_fabricated_data(app_module, client, monkeypatch):
    token = login(client)
    monkeypatch.setattr(app_module, "mysql_service", UnavailableService())
    monkeypatch.setattr(app_module, "hive_service", UnavailableService())
    response = client.get("/api/recommendations/personalized", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 503
    assert response.get_json()["status"] == "unavailable"
