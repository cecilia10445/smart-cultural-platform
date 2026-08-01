from types import SimpleNamespace

import pytest

from backend.agents.runtime.providers import RuntimeProviderError, build_runtime_model


def settings(**changes):
    value = dict(agent_runtime_allow_real_model=False, agent_runtime_provider="dashscope",
                 agent_runtime_model="qwen-plus", agent_runtime_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                 agent_runtime_timeout_seconds=30, dashscope_api_key="not-a-real-key")
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
