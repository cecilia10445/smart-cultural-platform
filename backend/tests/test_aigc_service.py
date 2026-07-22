from types import SimpleNamespace

import httpx
import pytest
from openai import APIStatusError, APITimeoutError, RateLimitError

from backend.services.aigc_service import AIGCService, AIGCServiceError, summarize_responses_response
from conftest import login


class FakeResponses:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


class FakeTextClient:
    def __init__(self, response=None, error=None):
        self.responses = FakeResponses(response, error)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.output_text = payload.get("output_text")

    def model_dump(self, mode="json"):
        assert mode == "json"
        return self.payload


def _settings(api_key="unit-test-key"):
    return SimpleNamespace(
        dashscope_api_key=api_key,
        dashscope_openai_base_url="https://text.example/v1",
        dashscope_api_base_url="https://image.example/api/v1",
        dashscope_text_model="qwen3.7-plus",
        dashscope_text_reasoning_effort="none",
        dashscope_image_model="wan2.6-t2i",
        dashscope_image_size="1280*1280",
        dashscope_text_connect_timeout_seconds=5,
        dashscope_text_read_timeout_seconds=120,
        dashscope_image_connect_timeout_seconds=5,
        dashscope_image_read_timeout_seconds=30,
    )


def cultural_response():
    return FakeResponse({
        "status": "completed", "model": "qwen3.7-plus",
        "output": [{"type": "message", "status": "completed", "content": [{
            "type": "output_text", "text": '{"product_name":"青花书签","design_interpretation":"纹样转译","product_copy":"一枚书签"}',
        }]}],
        "usage": {"input_tokens": 12, "output_tokens": 8, "total_tokens": 20},
    })


def brief():
    return {
        "brief_version": "1.0", "product_type": "bookmark",
        "cultural_source": {"source_type": "artifact", "name": "青花折枝纹", "era": None, "creator": None},
        "confirmed_facts": [], "form_and_material": "纸质书签", "use_case": "博物馆商店", "target_audience": None,
        "visual_direction": {"preset_id": "blue-white-pattern", "cultural_context": "青花瓷", "medium": "釉下青花", "palette": "靛青瓷白", "composition": "中心纹样", "additional_requirements": ""},
    }


def test_missing_key_is_explicit_failure():
    with pytest.raises(AIGCServiceError, match="configured") as error:
        AIGCService(_settings(None)).generate_text_content("topic", "style")
    assert error.value.code == "MODEL_UNAVAILABLE"


def test_sdk_text_contract_uses_none_reasoning_and_no_tools():
    client = FakeTextClient(cultural_response())
    result, usage = AIGCService(_settings(), text_client=client).generate_cultural_product_text_with_metadata(brief())
    request = client.responses.calls[0]
    assert result["product_name"] == "青花书签"
    assert usage == {"input_tokens": 12, "output_tokens": 8, "total_tokens": 20}
    assert request["model"] == "qwen3.7-plus"
    assert request["reasoning"] == {"effort": "none"}
    assert request["temperature"] == 0.4 and request["stream"] is False
    assert request["max_output_tokens"] == 500
    assert [item["role"] for item in request["input"]] == ["system", "user"]
    assert "enable_thinking" not in request and "tools" not in request and "tool_choice" not in request


@pytest.mark.parametrize(("payload", "code"), [
    ({"status": "completed", "output": []}, "MODEL_EMPTY_RESPONSE"),
    ({"status": "completed", "output": [{"type": "reasoning", "content": []}]}, "MODEL_RESPONSE_REASONING_ONLY"),
    ({"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}, "output": []}, "MODEL_RESPONSE_INCOMPLETE"),
    ({"status": "failed", "output": []}, "MODEL_INVALID_RESPONSE"),
])
def test_sdk_response_states_are_stable(payload, code):
    with pytest.raises(AIGCServiceError) as error:
        AIGCService(_settings(), text_client=FakeTextClient(FakeResponse(payload))).generate_text_content("青花", "图案")
    assert error.value.code == code
    assert error.value.http_status == 200


def test_sdk_output_text_property_is_preferred():
    response = FakeResponse({"status": "completed", "output_text": '{"title":"标题","content":"正文"}', "output": []})
    assert AIGCService(_settings(), text_client=FakeTextClient(response)).generate_text_content("青花", "图案") == ("标题", "正文")


def test_sdk_error_payload_uses_underlying_http_status_without_content_leak():
    response = FakeResponse({
        "status": "completed",
        "error": {"code": "provider_error", "message": "private model body Authorization: Bearer unit-test-key"},
        "output": [],
        "input": "private prompt",
    })
    response._response = SimpleNamespace(status_code=200, headers={})

    with pytest.raises(AIGCServiceError) as raised:
        AIGCService(_settings(), text_client=FakeTextClient(response)).generate_text_content("青花", "图案")

    error = raised.value
    assert (error.code, error.http_status, error.provider_error_code) == ("MODEL_INVALID_RESPONSE", 200, "provider_error")
    rendered = str(error.response_summary)
    for secret in ("private model body", "private prompt", "unit-test-key", "Authorization"):
        assert secret not in rendered


def test_response_summary_is_content_free():
    summary = summarize_responses_response({
        "status": "incomplete", "model": "qwen3.7-plus", "input": "private prompt",
        "incomplete_details": {"reason": "max_output_tokens"},
        "output": [{"type": "message", "status": "completed", "content": [
            {"type": "reasoning", "text": "private reasoning"}, {"type": "output_text", "text": "private generated content"},
        ]}], "usage": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
        "error": {"code": "provider-code", "message": "Authorization: Bearer unit-test-key"},
    }, {"x-dashscope-partialresponse": "true"})
    rendered = str(summary)
    assert summary["output_items"][0]["content_types"] == ["reasoning", "output_text"]
    assert summary["output_items"][0]["text_lengths"] == [17, 25]
    assert summary["partial_response_header_present"] is True
    for secret in ("private prompt", "private reasoning", "private generated content", "unit-test-key", "Authorization"):
        assert secret not in rendered


def timeout_error(cause):
    error = APITimeoutError(request=httpx.Request("POST", "https://example.invalid/responses"))
    error.__cause__ = cause
    return error


@pytest.mark.parametrize(("error", "code", "stage"), [
    (timeout_error(httpx.ConnectTimeout("connect")), "MODEL_CONNECT_TIMEOUT", "connect"),
    (timeout_error(httpx.ReadTimeout("read")), "MODEL_READ_TIMEOUT", "read"),
    (RateLimitError("limited", response=httpx.Response(429, request=httpx.Request("POST", "https://example.invalid")), body={"code": "Throttling"}), "MODEL_RATE_LIMITED", None),
    (APIStatusError("upstream", response=httpx.Response(503, request=httpx.Request("POST", "https://example.invalid")), body={"code": "InternalError"}), "MODEL_UPSTREAM_ERROR", None),
])
def test_sdk_errors_map_stably_without_retry(error, code, stage):
    client = FakeTextClient(error=error)
    with pytest.raises(AIGCServiceError) as raised:
        AIGCService(_settings(), text_client=client).generate_text_content("青花", "图案")
    assert raised.value.code == code and raised.value.timeout_stage == stage
    assert len(client.responses.calls) == 1


def test_wan_sync_request_uses_official_messages_contract(monkeypatch):
    observed = {}
    response = SimpleNamespace(status_code=200, json=lambda: {"output": {"choices": [{"finish_reason": "stop", "message": {"content": [{"image": "https://image.invalid/generated.png"}]}}]}})
    monkeypatch.setattr("backend.services.aigc_service.requests.post", lambda url, **kwargs: (observed.update({"url": url, **kwargs}) or response))
    assert AIGCService(_settings(), text_client=FakeTextClient()).generate_image_from_prompt("产品摄影") == "https://image.invalid/generated.png"
    assert observed["url"] == "https://image.example/api/v1/services/aigc/multimodal-generation/generation"
    assert observed["json"] == {"model": "wan2.6-t2i", "input": {"messages": [{"role": "user", "content": [{"text": "产品摄影"}]}]}, "parameters": {"size": "1280*1280", "n": 1, "watermark": False, "prompt_extend": True}}


def test_wan_rejects_unknown_size_before_request(monkeypatch):
    settings = _settings(); settings.dashscope_image_size = "1024*1024"
    monkeypatch.setattr("backend.services.aigc_service.requests.post", lambda *args, **kwargs: pytest.fail("request must not be sent"))
    with pytest.raises(AIGCServiceError, match="supported") as error:
        AIGCService(settings, text_client=FakeTextClient()).generate_image_from_prompt("产品摄影")
    assert error.value.code == "MODEL_INVALID_IMAGE_SIZE"


@pytest.mark.parametrize(("http_status", "provider_code", "code", "retryable"), [
    (400, "InvalidParameter", "MODEL_REQUEST_FAILED", False), (401, "InvalidApiKey", "MODEL_AUTH_FAILED", False),
    (403, "AccessDenied", "MODEL_ACCESS_DENIED", False), (429, "Throttling", "MODEL_RATE_LIMITED", True),
    (503, "InternalError", "MODEL_UPSTREAM_ERROR", True),
])
def test_wan_http_failures_are_stable(monkeypatch, http_status, provider_code, code, retryable):
    response = SimpleNamespace(status_code=http_status, json=lambda: {"code": provider_code, "message": "private provider body"})
    monkeypatch.setattr("backend.services.aigc_service.requests.post", lambda *args, **kwargs: response)
    with pytest.raises(AIGCServiceError) as error:
        AIGCService(_settings(), text_client=FakeTextClient()).generate_image_from_prompt("产品摄影")
    assert (error.value.code, error.value.retryable, error.value.http_status, error.value.provider_error_code) == (code, retryable, http_status, provider_code)


def test_generation_api_converts_model_failure_to_502(app_module, client, monkeypatch):
    token = login(client)
    error = AIGCServiceError("MODEL_REQUEST_TIMEOUT", "Text model request timed out.", True)
    monkeypatch.setattr(app_module, "generate_content", lambda *args: (_ for _ in ()).throw(error))
    response = client.post("/api/generate", json={"prompt": "topic", "style": "style"}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 502
    assert response.get_json()["code"] == "MODEL_REQUEST_TIMEOUT"
