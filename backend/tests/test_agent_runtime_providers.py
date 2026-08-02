from types import SimpleNamespace

import pytest

from backend.agents.runtime.providers import (
    DEFAULT_DASHSCOPE_OPENAI_BASE_URL,
    RuntimeProviderError,
    build_runtime_model,
    build_runtime_model_settings,
    resolve_runtime_base_url,
    resolve_runtime_model_name,
)


def settings(**changes):
    value = dict(agent_runtime_allow_real_model=False, agent_runtime_provider="dashscope",
                 agent_runtime_model="qwen-plus", agent_runtime_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                 agent_runtime_timeout_seconds=30, dashscope_api_key="not-a-real-key",
                 dashscope_openai_base_url=DEFAULT_DASHSCOPE_OPENAI_BASE_URL, dashscope_text_model="qwen-plus",
                 dashscope_text_reasoning_effort="none")
    value.update(changes)
    return SimpleNamespace(**value)


@pytest.mark.parametrize("changes,code", [
    ({}, "RUNTIME_PROVIDER_UNAVAILABLE"),
    ({"agent_runtime_allow_real_model": True, "dashscope_api_key": None}, "RUNTIME_PROVIDER_UNAVAILABLE"),
    ({"agent_runtime_allow_real_model": True, "agent_runtime_provider": "other"}, "RUNTIME_PROVIDER_INVALID"),
    ({"agent_runtime_allow_real_model": True, "agent_runtime_model": ""}, "RUNTIME_MODEL_INVALID"),
    ({"agent_runtime_allow_real_model": True, "agent_runtime_base_url": "http://localhost"}, "RUNTIME_BASE_URL_INVALID"),
    ({"agent_runtime_allow_real_model": True, "agent_runtime_timeout_seconds": 0}, "RUNTIME_TIMEOUT_INVALID"),
])
def test_provider_factory_rejects_invalid_or_disabled_configuration(changes, code):
    with pytest.raises(RuntimeProviderError) as raised:
        build_runtime_model(settings(**changes))
    assert raised.value.code == code
    assert "not-a-real-key" not in str(raised.value)


def test_runtime_reuses_workspace_compatible_endpoint_when_runtime_keeps_historical_default():
    value = settings(dashscope_openai_base_url="https://workspace.example/compatible-mode/v1")

    assert resolve_runtime_base_url(value) == "https://workspace.example/compatible-mode/v1"


def test_explicit_non_default_runtime_endpoint_remains_authoritative():
    value = settings(agent_runtime_base_url="https://runtime.example/compatible-mode/v1",
                     dashscope_openai_base_url="https://workspace.example/compatible-mode/v1")

    assert resolve_runtime_base_url(value) == "https://runtime.example/compatible-mode/v1"


def test_runtime_reuses_established_text_model_when_runtime_keeps_historical_default():
    assert resolve_runtime_model_name(settings(dashscope_text_model="qwen3.7-plus")) == "qwen3.7-plus"


def test_explicit_non_default_runtime_model_remains_authoritative():
    assert resolve_runtime_model_name(settings(agent_runtime_model="qwen-max", dashscope_text_model="qwen3.7-plus")) == "qwen-max"


def test_dashscope_runtime_disables_thinking_for_structured_tool_output():
    assert build_runtime_model_settings(settings()) == {"extra_body": {"enable_thinking": False}}


def test_runtime_keeps_provider_defaults_when_reasoning_is_explicitly_enabled():
    assert build_runtime_model_settings(settings(dashscope_text_reasoning_effort="high")) == {}
