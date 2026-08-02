"""Explicit opt-in provider construction for agent-runtime only."""
from __future__ import annotations

import httpx
from typing import Any


DEFAULT_DASHSCOPE_OPENAI_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_AGENT_RUNTIME_MODEL = "qwen-plus"


class RuntimeProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


def resolve_runtime_base_url(settings) -> str:
    """Keep the Runtime on the same configured DashScope endpoint as the app.

    Existing deployments may use a workspace-scoped compatible endpoint for
    the established text/image services while the Runtime setting still holds
    the historical public default. Sending one API key to two different
    endpoint families makes connection failures look like generic Runtime
    errors. A deliberate non-default Runtime endpoint remains authoritative.
    """
    runtime_url = getattr(settings, "agent_runtime_base_url", "").strip().rstrip("/")
    shared_url = getattr(settings, "dashscope_openai_base_url", "").strip().rstrip("/")
    if runtime_url == DEFAULT_DASHSCOPE_OPENAI_BASE_URL and shared_url and shared_url != runtime_url:
        return shared_url
    return runtime_url


def resolve_runtime_model_name(settings) -> str:
    """Use the established text model when Runtime still has its old default."""
    runtime_model = getattr(settings, "agent_runtime_model", "").strip()
    shared_model = getattr(settings, "dashscope_text_model", "").strip()
    if runtime_model == DEFAULT_AGENT_RUNTIME_MODEL and shared_model and shared_model != runtime_model:
        return shared_model
    return runtime_model


def build_runtime_model_settings(settings=None) -> dict[str, Any]:
    """Return provider-specific settings required by Runtime tool calling.

    DashScope's thinking mode rejects the forced ``tool_choice`` used by
    Pydantic AI for structured outputs. The Runtime deliberately uses
    structured Conversation Reply output and Function Calling, so an explicit
    ``none`` reasoning setting must translate to DashScope's compatible API
    switch. This affects only the Agent Runtime request; legacy text and image
    clients keep their existing configuration.
    """
    if settings is None:
        from backend.config import load_settings
        settings = load_settings()
    provider = getattr(settings, "agent_runtime_provider", "").strip().lower()
    reasoning_effort = getattr(settings, "dashscope_text_reasoning_effort", "").strip().lower()
    if provider == "dashscope" and reasoning_effort == "none":
        return {"extra_body": {"enable_thinking": False}}
    return {}


def build_runtime_model(settings=None):
    """Return a Pydantic AI model without altering legacy AIGCService clients."""
    if settings is None:
        from backend.config import load_settings
        settings = load_settings()
    if not getattr(settings, "agent_runtime_allow_real_model", False):
        raise RuntimeProviderError("RUNTIME_PROVIDER_UNAVAILABLE", "Assistant runtime is not enabled.")
    provider = getattr(settings, "agent_runtime_provider", "").strip().lower()
    model_name = resolve_runtime_model_name(settings)
    base_url = resolve_runtime_base_url(settings)
    timeout_seconds = getattr(settings, "agent_runtime_timeout_seconds", 0)
    if provider != "dashscope":
        raise RuntimeProviderError("RUNTIME_PROVIDER_INVALID", "Assistant runtime provider is not supported.")
    if not model_name:
        raise RuntimeProviderError("RUNTIME_MODEL_INVALID", "Assistant runtime model is not configured.")
    if not base_url.startswith("https://"):
        raise RuntimeProviderError("RUNTIME_BASE_URL_INVALID", "Assistant runtime endpoint is invalid.")
    if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
        raise RuntimeProviderError("RUNTIME_TIMEOUT_INVALID", "Assistant runtime timeout is invalid.")
    api_key = getattr(settings, "dashscope_api_key", None)
    if not api_key:
        raise RuntimeProviderError("RUNTIME_PROVIDER_UNAVAILABLE", "Assistant runtime credentials are not configured.")
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.alibaba import AlibabaProvider
    timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 10))
    provider_client = AlibabaProvider(api_key=api_key, base_url=base_url, http_client=httpx.AsyncClient(timeout=timeout))
    return OpenAIChatModel(model_name, provider=provider_client)
