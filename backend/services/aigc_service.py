import json
import time

import requests

try:
    from config import load_settings
except ImportError:
    from backend.config import load_settings


class AIGCServiceError(Exception):
    def __init__(self, code, message, retryable=False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class AIGCService:
    def __init__(self, settings=None):
        self.settings = settings or load_settings()
        self.api_key = self.settings.dashscope_api_key
        self.text_api_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
        self.image_api_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
        self.task_query_url = "https://dashscope.aliyuncs.com/api/v1/tasks/"

    def _headers(self, asynchronous=False):
        if not self.api_key:
            raise AIGCServiceError("MODEL_UNAVAILABLE", "Model service is not configured.")
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        if asynchronous:
            headers["X-DashScope-Async"] = "enable"
        return headers

    def generate_content(self, prompt, style):
        title, content = self.generate_text_content(prompt, style)
        return self.generate_image(prompt, style), title, content

    def generate_text_content(self, prompt, style):
        payload = {
            "model": "qwen-turbo",
            "input": {"messages": [{"role": "user", "content": self._text_prompt(prompt, style)}]},
            "parameters": {"max_tokens": 300, "temperature": 0.8},
        }
        response = self._post(self.text_api_url, self._headers(), payload, self.settings.dashscope_text_timeout_seconds, "TEXT")
        try:
            raw_content = response.json().get("output", {}).get("text", "").strip()
        except (ValueError, AttributeError) as exc:
            raise AIGCServiceError("MODEL_INVALID_RESPONSE", "Text model returned invalid JSON.") from exc
        if not raw_content:
            raise AIGCServiceError("MODEL_EMPTY_RESPONSE", "Text model returned an empty response.")
        return self.parse_text_content(raw_content)

    def _text_prompt(self, prompt, style):
        return (
            "Generate a JSON object with title and content for the following creative request. "
            f"Theme: {prompt}\nStyle: {style}\n"
            "Return only JSON: {\"title\": \"...\", \"content\": \"...\"}."
        )

    def parse_text_content(self, content):
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AIGCServiceError("MODEL_INVALID_RESPONSE", "Text model did not return JSON.") from exc
        title = str(data.get("title", "")).strip()
        body = str(data.get("content", "")).strip()
        if not title or not body:
            raise AIGCServiceError("MODEL_EMPTY_RESPONSE", "Text model response is missing title or content.")
        return title, body

    def generate_image(self, prompt, style):
        payload = {"model": "wanx-v1", "input": {"prompt": f"{prompt}, {style} style"}, "parameters": {"size": "1024*1024", "n": 1}}
        response = self._post(self.image_api_url, self._headers(True), payload, self.settings.dashscope_image_timeout_seconds, "IMAGE")
        try:
            task_id = response.json().get("output", {}).get("task_id")
        except (ValueError, AttributeError) as exc:
            raise AIGCServiceError("MODEL_INVALID_RESPONSE", "Image model returned invalid JSON.") from exc
        if not task_id:
            raise AIGCServiceError("MODEL_EMPTY_RESPONSE", "Image model did not return a task id.")
        return self.wait_for_image_task(task_id)

    def wait_for_image_task(self, task_id, max_attempts=12, interval=5):
        for _ in range(max_attempts):
            try:
                response = requests.get(f"{self.task_query_url}{task_id}", headers=self._headers(), timeout=self.settings.dashscope_poll_timeout_seconds)
            except requests.Timeout as exc:
                raise AIGCServiceError("MODEL_REQUEST_TIMEOUT", "Image task polling timed out.", True) from exc
            except requests.RequestException as exc:
                raise AIGCServiceError("MODEL_REQUEST_FAILED", "Image task polling failed.", True) from exc
            if response.status_code >= 500:
                raise AIGCServiceError("MODEL_UPSTREAM_ERROR", "Image model service failed.", True)
            if response.status_code != 200:
                raise AIGCServiceError("MODEL_REQUEST_FAILED", "Image task polling was rejected.")
            try:
                output = response.json().get("output", {})
            except (ValueError, AttributeError) as exc:
                raise AIGCServiceError("MODEL_INVALID_RESPONSE", "Image task returned invalid JSON.") from exc
            if output.get("task_status") == "SUCCEEDED":
                results = output.get("results") or []
                image_url = results[0].get("url") if results else None
                if image_url:
                    return image_url
                raise AIGCServiceError("MODEL_EMPTY_RESPONSE", "Image task completed without an image URL.")
            if output.get("task_status") in {"FAILED", "CANCELED"}:
                raise AIGCServiceError("MODEL_REQUEST_FAILED", "Image generation task failed.")
            time.sleep(interval)
        raise AIGCServiceError("MODEL_REQUEST_TIMEOUT", "Image generation task timed out.", True)

    def _post(self, url, headers, payload, timeout, operation):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except requests.Timeout as exc:
            raise AIGCServiceError("MODEL_REQUEST_TIMEOUT", f"{operation} model request timed out.", True) from exc
        except requests.RequestException as exc:
            raise AIGCServiceError("MODEL_REQUEST_FAILED", f"{operation} model request failed.", True) from exc
        if response.status_code >= 500:
            raise AIGCServiceError("MODEL_UPSTREAM_ERROR", f"{operation} model service failed.", True)
        if response.status_code != 200:
            raise AIGCServiceError("MODEL_REQUEST_FAILED", f"{operation} model request was rejected.")
        return response


aigc_service = AIGCService()


def generate_content(prompt, style):
    return aigc_service.generate_content(prompt, style)
