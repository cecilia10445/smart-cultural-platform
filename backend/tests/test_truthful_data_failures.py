import pandas as pd

from backend.services.hive_service import HiveService
from backend.tests.conftest import login


class RaisingDataService:
    def __init__(self, message="internal-password=secret-value"):
        self.message = message

    def get_user_profile_dashboard(self, *_args, **_kwargs):
        raise RuntimeError(self.message)

    def get_personalized_recommendations(self, *_args, **_kwargs):
        raise RuntimeError(self.message)


class UnavailableDataService:
    def get_user_profile_dashboard(self, *_args, **_kwargs):
        return None

    def get_personalized_recommendations(self, *_args, **_kwargs):
        return None


def assert_stable_data_unavailable(response):
    body = response.get_json()
    assert response.status_code == 503
    assert body["status"] == "unavailable"
    assert body["code"] == "DATA_UNAVAILABLE"
    assert "data" not in body
    response_text = response.get_data(as_text=True)
    assert "secret-value" not in response_text
    assert "internal-password" not in response_text


def test_user_profile_exception_never_returns_fabricated_data(app_module, client, monkeypatch):
    token = login(client, "admin", "admin-password", "admin")
    monkeypatch.setattr(app_module, "mysql_service", RaisingDataService())
    monkeypatch.setattr(app_module, "hive_service", UnavailableDataService())

    response = client.get(
        "/api/dashboard/user-profile",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert_stable_data_unavailable(response)


def test_recommendation_exception_never_returns_mock_or_details(app_module, client, monkeypatch):
    token = login(client)
    monkeypatch.setattr(app_module, "mysql_service", RaisingDataService())
    monkeypatch.setattr(app_module, "hive_service", RaisingDataService())

    response = client.get(
        "/api/recommendations/personalized",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert_stable_data_unavailable(response)
    response_text = response.get_data(as_text=True)
    assert "style_recommendations" not in response_text
    assert "hot_keywords" not in response_text


def test_hive_history_connection_failure_returns_none_without_mock_claim(monkeypatch, capsys):
    service = HiveService()
    monkeypatch.setattr(service, "connect", lambda: False)

    result = service.get_user_history("U-test")
    output = capsys.readouterr().out

    assert result is None
    assert "模拟" not in output


def test_hive_history_real_empty_result_returns_empty_list(monkeypatch):
    service = HiveService()
    monkeypatch.setattr(service, "connect", lambda: True)
    monkeypatch.setattr(service, "execute_query", lambda _query: pd.DataFrame())

    assert service.get_user_history("U-test") == []


def test_hive_service_has_no_random_history_generator():
    assert not hasattr(HiveService, "get_mock_history")
