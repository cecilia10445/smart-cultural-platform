from types import SimpleNamespace

import pytest

from evaluation.real_business_v2_smoke import (
    BusinessSmokeConfigurationError,
    REQUIRED_DATABASE,
    run_business_smoke,
    validate_business_smoke_settings,
)


def settings(**overrides):
    values = {
        "run_real_business_smoke": True,
        "mysql_database": REQUIRED_DATABASE,
        "smoke_test_username": "user1",
        "smoke_test_password": "local-only",
        "dashscope_api_key": "configured-for-test",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize("overrides,code", [
    ({"run_real_business_smoke": False}, "RUN_REAL_BUSINESS_SMOKE_REQUIRED"),
    ({"mysql_database": "aigc_platform"}, "SMOKE_DATABASE_NOT_ALLOWED"),
    ({"smoke_test_username": "someone-else"}, "SMOKE_USERNAME_NOT_ALLOWED"),
    ({"smoke_test_password": None}, "SMOKE_PASSWORD_REQUIRED"),
    ({"dashscope_api_key": None}, "DASHSCOPE_API_KEY_REQUIRED"),
])
def test_business_smoke_preflight_rejects_each_missing_gate(overrides, code):
    with pytest.raises(BusinessSmokeConfigurationError, match=code):
        validate_business_smoke_settings(settings(**overrides))


def test_business_smoke_uses_login_and_one_v2_request_without_client_data_origin(app_module, monkeypatch):
    app_module.settings = settings()
    calls = []

    class Response:
        def __init__(self, status_code, body):
            self.status_code, self.body = status_code, body

        def get_json(self, silent=False):
            return self.body

    class Client:
        def post(self, path, json, headers=None):
            calls.append((path, json, headers))
            if path == "/api/login":
                return Response(200, {"token": "test-token"})
            return Response(200, {"status": "success", "log_id": 77, "generation_kind": "cultural_product", "prompt_template_version": "cultural-product-v1"})

    monkeypatch.setattr(app_module.app, "test_client", lambda: Client())
    result = run_business_smoke(app_module)
    assert result["status"] == "passed"
    assert [item[0] for item in calls] == ["/api/login", "/api/v2/cultural-products/generate"]
    assert "data_origin" not in calls[1][1]
