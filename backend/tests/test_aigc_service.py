from types import SimpleNamespace

import pytest
import requests

from backend.services.aigc_service import AIGCService, AIGCServiceError
from conftest import login


def service_without_key():
    return AIGCService(SimpleNamespace(dashscope_api_key=None, dashscope_text_timeout_seconds=1, dashscope_image_timeout_seconds=1, dashscope_poll_timeout_seconds=1))


def service_with_key():
    return AIGCService(SimpleNamespace(dashscope_api_key="unit-test-key", dashscope_text_timeout_seconds=1, dashscope_image_timeout_seconds=1, dashscope_poll_timeout_seconds=1))


def test_missing_key_is_explicit_failure():
    with pytest.raises(AIGCServiceError) as error:
        service_without_key().generate_text_content("topic", "style")
    assert error.value.code == "MODEL_UNAVAILABLE"


def test_text_timeout_is_explicit_failure(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: (_ for _ in ()).throw(requests.Timeout()))
    with pytest.raises(AIGCServiceError) as error:
        service_with_key().generate_text_content("topic", "style")
    assert error.value.code == "MODEL_REQUEST_TIMEOUT"


def test_text_5xx_is_explicit_failure(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: SimpleNamespace(status_code=503))
    with pytest.raises(AIGCServiceError) as error:
        service_with_key().generate_text_content("topic", "style")
    assert error.value.code == "MODEL_UPSTREAM_ERROR"


def test_empty_text_response_is_explicit_failure(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: SimpleNamespace(status_code=200, json=lambda: {"output": {"text": ""}}))
    with pytest.raises(AIGCServiceError) as error:
        service_with_key().generate_text_content("topic", "style")
    assert error.value.code == "MODEL_EMPTY_RESPONSE"


def test_generation_api_converts_model_failure_to_502(app_module, client, monkeypatch):
    token = login(client)
    error = AIGCServiceError("MODEL_REQUEST_TIMEOUT", "Text model request timed out.", True)
    monkeypatch.setattr(app_module, "generate_content", lambda *args: (_ for _ in ()).throw(error))
    response = client.post("/api/generate", json={"prompt": "topic", "style": "style"}, headers={"Authorization": f"Bearer {token}"})
    body = response.get_json()
    assert response.status_code == 502
    assert body["code"] == "MODEL_REQUEST_TIMEOUT"
    assert body["retryable"] is True
