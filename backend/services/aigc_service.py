"""DashScope adapters with stable application-level error semantics.

The text and image providers use different HTTP contracts.  This module keeps
provider details here so application routes continue to receive validated text
and a temporary image URL only; the URL is persisted locally by image_storage.
"""

from __future__ import annotations

import json

import httpx
import requests
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)

from backend.prompts.cultural_product_v1 import build_text_messages, validate_text_response


ALLOWED_WAN_IMAGE_SIZES = {"1280*1280"}

try:
    from config import load_settings
except ImportError:
    from backend.config import load_settings


class AIGCServiceError(Exception):
    def __init__(self, code, message, retryable=False, timeout_stage=None, http_status=None, provider_error_code=None, response_summary=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.timeout_stage = timeout_stage
        self.http_status = http_status
        self.provider_error_code = provider_error_code
        self.response_summary = response_summary


class AIGCService:
    def __init__(self, settings=None, text_client=None):
        self.settings = settings or load_settings()
        self.api_key = self.settings.dashscope_api_key
        self.text_api_url = f"{self.settings.dashscope_openai_base_url.rstrip('/')}/responses"
        self.image_api_url = f"{self.settings.dashscope_api_base_url.rstrip('/')}/services/aigc/multimodal-generation/generation"
        self.text_model = self.settings.dashscope_text_model
        self.text_reasoning_effort = self.settings.dashscope_text_reasoning_effort
        self.image_model = self.settings.dashscope_image_model
        self.image_size = self.settings.dashscope_image_size
        self.text_client = text_client or self._create_text_client()

    def _create_text_client(self):
        if not self.api_key:
            return None
        timeout = httpx.Timeout(
            connect=self.settings.dashscope_text_connect_timeout_seconds,
            read=self.settings.dashscope_text_read_timeout_seconds,
            write=self.settings.dashscope_text_read_timeout_seconds,
            pool=self.settings.dashscope_text_connect_timeout_seconds,
        )
        return OpenAI(
            api_key=self.api_key,
            base_url=self.settings.dashscope_openai_base_url,
            timeout=timeout,
            max_retries=0,
        )

    def _headers(self):
        if not self.api_key:
            raise AIGCServiceError("MODEL_UNAVAILABLE", "Model service is not configured.")
        return {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}

    def generate_content(self, prompt, style):
        title, content = self.generate_text_content(prompt, style)
        return self.generate_image(prompt, style), title, content

    def generate_text_content(self, prompt, style):
        title, content, _usage = self.generate_text_content_with_metadata(prompt, style)
        return title, content

    def generate_text_content_with_metadata(self, prompt, style):
        messages = [
            {
                "role": "system",
                "content": "Generate a JSON object with title and content. Return only JSON: {\"title\": \"...\", \"content\": \"...\"}.",
            },
            {"role": "user", "content": f"Theme: {prompt}\nStyle: {style}"},
        ]
        raw_content, usage = self._request_text(messages, 300)
        title, content = self.parse_text_content(raw_content)
        return title, content, usage

    def generate_cultural_product_text(self, brief):
        result, _usage = self.generate_cultural_product_text_with_metadata(brief)
        return result

    def generate_cultural_product_text_with_metadata(self, brief):
        """Generate creative fields only; factual background remains server-side."""
        raw_content, usage = self._request_text(build_text_messages(brief), 500)
        try:
            return validate_text_response(raw_content), usage
        except ValueError as exc:
            code = str(exc) if str(exc) in {"MODEL_INVALID_RESPONSE", "MODEL_EMPTY_RESPONSE"} else "MODEL_INVALID_RESPONSE"
            raise AIGCServiceError(code, "Text model returned an invalid cultural-product response.") from exc

    def _request_text(self, messages, max_output_tokens):
        payload = {
            "model": self.text_model,
            "input": [
                {
                    "role": message["role"],
                    "content": [{"type": "input_text", "text": message["content"]}],
                }
                for message in messages
            ],
            "max_output_tokens": max_output_tokens,
            "temperature": 0.4,
            "reasoning": {"effort": self.text_reasoning_effort},
            "stream": False,
        }
        if not self.api_key or self.text_client is None:
            raise AIGCServiceError("MODEL_UNAVAILABLE", "Model service is not configured.")
        try:
            response = self.text_client.responses.create(**payload)
        except Exception as exc:
            raise _map_sdk_error(exc) from exc
        data = _sdk_response_mapping(response)
        summary = summarize_responses_response(data, _sdk_response_headers(response))
        self.last_response_summary = summary
        status = data.get("status")
        if status == "incomplete":
            raise AIGCServiceError(
                "MODEL_RESPONSE_INCOMPLETE",
                "Text model response was incomplete.",
                http_status=_sdk_response_http_status(response),
                provider_error_code=summary.get("error_code"),
                response_summary=summary,
            )
        if status in {"failed", "cancelled"}:
            raise AIGCServiceError(
                "MODEL_INVALID_RESPONSE",
                "Text model did not complete the response.",
                http_status=_sdk_response_http_status(response),
                provider_error_code=summary.get("error_code"),
                response_summary=summary,
            )
        if isinstance(data.get("error"), dict):
            raise AIGCServiceError(
                "MODEL_INVALID_RESPONSE",
                "Text model returned an error response.",
                http_status=_sdk_response_http_status(response),
                provider_error_code=summary.get("error_code"),
                response_summary=summary,
            )
        raw_content = getattr(response, "output_text", None)
        if not isinstance(raw_content, str) or not raw_content.strip():
            raw_content = self._extract_responses_output_text(data)
        if not raw_content:
            output_items = summary["output_items"]
            code = "MODEL_RESPONSE_REASONING_ONLY" if output_items and all(item["type"] == "reasoning" for item in output_items) else "MODEL_EMPTY_RESPONSE"
            raise AIGCServiceError(
                code,
                "Text model returned an empty response.",
                http_status=_sdk_response_http_status(response),
                response_summary=summary,
            )
        return raw_content.strip(), self._safe_usage(data.get("usage"))

    @staticmethod
    def _extract_responses_output_text(data):
        direct_text = data.get("output_text")
        if isinstance(direct_text, str) and direct_text.strip():
            return direct_text.strip()
        output = data.get("output")
        if not isinstance(output, list):
            return None
        parts = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict) or part.get("type") != "output_text":
                    continue
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts) or None

    @staticmethod
    def _safe_usage(value):
        """Pass through actual scalar usage fields only; never estimate usage."""
        if not isinstance(value, dict):
            return None
        usage = {key: value[key] for key in ("input_tokens", "output_tokens", "total_tokens") if isinstance(value.get(key), (int, float))}
        return usage or None

    def parse_text_content(self, content):
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AIGCServiceError("MODEL_INVALID_RESPONSE", "Text model did not return JSON.") from exc
        title = data.get("title") if isinstance(data, dict) else None
        body = data.get("content") if isinstance(data, dict) else None
        if not isinstance(title, str) or not isinstance(body, str):
            raise AIGCServiceError("MODEL_INVALID_RESPONSE", "Text model response has invalid fields.")
        title, body = title.strip(), body.strip()
        if not title or not body:
            raise AIGCServiceError("MODEL_EMPTY_RESPONSE", "Text model response is missing title or content.")
        return title, body

    def generate_image(self, prompt, style):
        # Legacy API remains compatible while using the configured image adapter.
        return self.generate_image_from_prompt(f"{prompt}；画面方向：{style}")

    def generate_image_from_prompt(self, image_prompt):
        if self.image_size not in ALLOWED_WAN_IMAGE_SIZES:
            raise AIGCServiceError("MODEL_INVALID_IMAGE_SIZE", "Image size is not supported by the configured model.")
        payload = {
            "model": self.image_model,
            "input": {
                "messages": [{
                    "role": "user",
                    "content": [{"text": image_prompt}],
                }],
            },
            "parameters": {
                "size": self.image_size,
                "n": 1,
                "watermark": False,
                "prompt_extend": True,
            },
        }
        response = self._post(
            self.image_api_url,
            self._headers(),
            payload,
            (self.settings.dashscope_image_connect_timeout_seconds, self.settings.dashscope_image_read_timeout_seconds),
            "IMAGE",
        )
        data = self._response_json(response, "Image")
        return self._extract_image_url(data)

    @staticmethod
    def _extract_image_url(data):
        output = data.get("output") if isinstance(data, dict) else None
        if not isinstance(output, dict):
            raise AIGCServiceError("MODEL_INVALID_RESPONSE", "Image model returned an invalid response.")
        choices = output.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0] if isinstance(choices[0], dict) else {}
            if first.get("finish_reason") in {"content_filter", "content_filtered"}:
                raise AIGCServiceError("MODEL_CONTENT_FILTERED", "Image request was rejected by content policy.")
            content = first.get("message", {}).get("content", []) if isinstance(first.get("message"), dict) else []
            if isinstance(content, list) and content and isinstance(content[0], dict):
                image_url = content[0].get("image")
                if isinstance(image_url, str) and image_url:
                    return image_url
        code = output.get("code")
        if code in {"DataInspectionFailed", "ContentFiltered"}:
            raise AIGCServiceError("MODEL_CONTENT_FILTERED", "Image request was rejected by content policy.")
        if output.get("task_status") in {"FAILED", "CANCELED"}:
            raise AIGCServiceError("MODEL_REQUEST_FAILED", "Image generation failed.")
        raise AIGCServiceError("MODEL_EMPTY_RESPONSE", "Image model returned no image.")

    @staticmethod
    def _response_json(response, operation):
        try:
            data = response.json()
        except (ValueError, AttributeError) as exc:
            raise AIGCServiceError("MODEL_INVALID_RESPONSE", f"{operation} model returned invalid JSON.") from exc
        if not isinstance(data, dict):
            raise AIGCServiceError("MODEL_INVALID_RESPONSE", f"{operation} model returned invalid JSON.")
        return data

    @staticmethod
    def _post(url, headers, payload, timeout, operation):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except requests.ConnectTimeout as exc:
            raise AIGCServiceError("MODEL_CONNECT_TIMEOUT", f"{operation} model connection timed out.", True, timeout_stage="connect") from exc
        except requests.ReadTimeout as exc:
            raise AIGCServiceError("MODEL_READ_TIMEOUT", f"{operation} model response timed out.", True, timeout_stage="read") from exc
        except requests.Timeout as exc:
            raise AIGCServiceError("MODEL_REQUEST_TIMEOUT", f"{operation} model request timed out.", True) from exc
        except requests.RequestException as exc:
            raise AIGCServiceError("MODEL_REQUEST_FAILED", f"{operation} model request failed.", True) from exc
        provider_error_code = _provider_error_code(response)
        if response.status_code == 401:
            raise AIGCServiceError("MODEL_AUTH_FAILED", f"{operation} model authentication failed.", http_status=401, provider_error_code=provider_error_code)
        if response.status_code == 403:
            raise AIGCServiceError("MODEL_ACCESS_DENIED", f"{operation} model access was denied.", http_status=403, provider_error_code=provider_error_code)
        if response.status_code == 429:
            raise AIGCServiceError("MODEL_RATE_LIMITED", f"{operation} model request was rate limited.", True, http_status=429, provider_error_code=provider_error_code)
        if response.status_code >= 500:
            raise AIGCServiceError("MODEL_UPSTREAM_ERROR", f"{operation} model service failed.", True, http_status=response.status_code, provider_error_code=provider_error_code)
        if response.status_code != 200:
            raise AIGCServiceError("MODEL_REQUEST_FAILED", f"{operation} model request was rejected.", http_status=response.status_code, provider_error_code=provider_error_code)
        return response


def _sdk_response_mapping(response):
    """Read the SDK response only in memory; callers retain a content-free summary."""
    if hasattr(response, "model_dump"):
        data = response.model_dump(mode="json")
    elif isinstance(response, dict):
        data = response
    else:
        data = {
            "status": getattr(response, "status", None),
            "model": getattr(response, "model", None),
            "output": getattr(response, "output", None),
            "usage": getattr(response, "usage", None),
            "error": getattr(response, "error", None),
            "incomplete_details": getattr(response, "incomplete_details", None),
        }
    if not isinstance(data, dict):
        raise AIGCServiceError("MODEL_INVALID_RESPONSE", "Text model returned an invalid response.")
    return data


def _sdk_response_headers(response):
    http_response = getattr(response, "_response", None)
    headers = getattr(http_response, "headers", None)
    return headers if headers is not None else {}


def _sdk_response_http_status(response):
    http_response = getattr(response, "_response", None)
    status = getattr(http_response, "status_code", None)
    return status if isinstance(status, int) else 200


def _sdk_error_code(error):
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        nested = body.get("error")
        if isinstance(nested, dict) and isinstance(nested.get("code"), str):
            return nested["code"]
        if isinstance(body.get("code"), str):
            return body["code"]
    return None


def _map_sdk_error(error):
    """Map OpenAI SDK transport/status errors without retaining provider text."""
    if isinstance(error, APITimeoutError):
        cause = error.__cause__
        if isinstance(cause, httpx.ConnectTimeout):
            return AIGCServiceError("MODEL_CONNECT_TIMEOUT", "TEXT model connection timed out.", True, timeout_stage="connect")
        return AIGCServiceError("MODEL_READ_TIMEOUT", "TEXT model response timed out.", True, timeout_stage="read")
    if isinstance(error, AuthenticationError):
        return AIGCServiceError("MODEL_AUTH_FAILED", "TEXT model authentication failed.", http_status=401, provider_error_code=_sdk_error_code(error))
    if isinstance(error, PermissionDeniedError):
        return AIGCServiceError("MODEL_ACCESS_DENIED", "TEXT model access was denied.", http_status=403, provider_error_code=_sdk_error_code(error))
    if isinstance(error, RateLimitError):
        return AIGCServiceError("MODEL_RATE_LIMITED", "TEXT model request was rate limited.", True, http_status=429, provider_error_code=_sdk_error_code(error))
    if isinstance(error, APIStatusError):
        status = error.status_code
        code = "MODEL_UPSTREAM_ERROR" if status >= 500 else "MODEL_REQUEST_FAILED"
        return AIGCServiceError(code, "TEXT model request was rejected.", status >= 500, http_status=status, provider_error_code=_sdk_error_code(error))
    if isinstance(error, APIConnectionError):
        return AIGCServiceError("MODEL_REQUEST_FAILED", "TEXT model request failed.", True)
    return AIGCServiceError("MODEL_REQUEST_FAILED", "TEXT model request failed.", True)


def _provider_error_code(response):
    """Extract a provider code only; never preserve the provider message/body."""
    try:
        data = response.json()
    except (ValueError, AttributeError):
        return None
    if not isinstance(data, dict):
        return None
    error = data.get("error")
    if isinstance(error, dict) and isinstance(error.get("code"), str):
        return error["code"]
    if isinstance(data.get("code"), str):
        return data["code"]
    return None


def summarize_responses_response(data, headers=None):
    """Return a content-free Responses shape summary for temporary diagnostics."""
    if not isinstance(data, dict):
        return {"top_level_object": False, "top_level_fields": [], "output_items": [], "usage": None, "partial_response_header_present": False}
    output_items = []
    output = data.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            content = content if isinstance(content, list) else []
            content_types = [part.get("type") for part in content if isinstance(part, dict) and isinstance(part.get("type"), str)]
            text_lengths = [len(part["text"]) for part in content if isinstance(part, dict) and isinstance(part.get("text"), str)]
            output_items.append({"type": item.get("type"), "status": item.get("status"), "content_types": content_types, "text_lengths": text_lengths})
    incomplete = data.get("incomplete_details")
    error = data.get("error")
    return {
        "top_level_object": True,
        "top_level_fields": sorted(data.keys()),
        "status": data.get("status"),
        "model": data.get("model"),
        "error_code": error.get("code") if isinstance(error, dict) else None,
        "incomplete_reason": incomplete.get("reason") if isinstance(incomplete, dict) else None,
        "output_items": output_items,
        "usage": AIGCService._safe_usage(data.get("usage")),
        "partial_response_header_present": bool((headers or {}).get("x-dashscope-partialresponse")),
    }


aigc_service = AIGCService()


def generate_content(prompt, style):
    return aigc_service.generate_content(prompt, style)
