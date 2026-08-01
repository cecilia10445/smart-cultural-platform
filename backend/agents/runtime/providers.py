"""Explicit opt-in provider construction for agent-runtime only."""
from __future__ import annotations

import httpx


class RuntimeProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


def build_runtime_model(settings=None):
    """Return a Pydantic AI model without altering legacy AIGCService clients."""
    if settings is None:
        from backend.config import load_settings
        settings = load_settings()
    if not getattr(settings, "agent_runtime_allow_real_model", False):
        raise RuntimeProviderError("RUNTIME_PROVIDER_UNAVAILABLE", "Assistant runtime is not enabled.")
    provider = getattr(settings, "agent_runtime_provider", "").strip().lower()
    model_name = getattr(settings, "agent_runtime_model", "").strip()
    base_url = getattr(settings, "agent_runtime_base_url", "").strip()
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
