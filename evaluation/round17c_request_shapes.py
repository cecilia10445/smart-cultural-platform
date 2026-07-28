"""MockTransport evidence generated through the clean runner's real factories."""

from __future__ import annotations

import json
from typing import Any

import httpx
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessage, ChatCompletionMessageToolCall
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_message_tool_call import Function
from pydantic_ai import models as pydantic_models

from backend.agents.skill_registry import SKILLS
from evaluation.round17c_contract import text_skill_catalog
from evaluation.round17c_runner import BRIEF_PAYLOAD, build_dashscope_client, build_model, run_baseline, run_guided


def _completion(step: int, *, content: str | None = None, tool_name: str | None = None, arguments: dict[str, Any] | None = None) -> ChatCompletion:
    kwargs: dict[str, Any] = {"role": "assistant"}
    finish = "stop"
    if content is not None:
        kwargs["content"] = content
    if tool_name:
        kwargs["tool_calls"] = [ChatCompletionMessageToolCall(id=f"call-{step}", type="function", function=Function(name=tool_name, arguments=json.dumps(arguments or {}, ensure_ascii=False)))]
        finish = "tool_calls"
    return ChatCompletion(id=f"mock-{step}", choices=[Choice(index=0, finish_reason=finish, message=ChatCompletionMessage(**kwargs))], created=0, model="offline-qwen", object="chat.completion", usage={"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18})


def _shape(request: httpx.Request) -> dict[str, Any]:
    body = json.loads(request.content.decode("utf-8"))
    tools = body.get("tools") or []
    names = [tool.get("function", {}).get("name") for tool in tools]
    messages = body.get("messages") or []
    system = "\n".join(str(message.get("content", "")) for message in messages if message.get("role") == "system")
    return {
        "endpoint": request.url.path,
        "model": body.get("model"),
        "response_format": body.get("response_format"),
        "reasoning_effort": body.get("reasoning_effort"),
        "enable_thinking": body.get("enable_thinking"),
        "tool_choice": body.get("tool_choice"),
        "parallel_tool_calls": body.get("parallel_tool_calls"),
        "thinking": "disabled" if body.get("reasoning_effort") in (None, "none") else "enabled",
        "temperature": body.get("temperature"),
        "max_tokens": body.get("max_tokens") or body.get("max_completion_tokens"),
        "business_tool_names": names,
        "output_tool_names": [name for name in names if name and name.startswith("final_result")],
        "contains_visual_skill": any(skill.skill_id in system for skill in SKILLS.values() if skill.kind == "visual"),
        "system_sha256": __import__("hashlib").sha256(system.encode("utf-8")).hexdigest(),
    }


class _SequenceHandler:
    def __init__(self, responses: list[ChatCompletion]):
        self.responses = responses
        self.requests: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(_shape(request))
        response = self.responses.pop(0)
        return httpx.Response(200, content=json.dumps(response.model_dump()).encode("utf-8"), headers={"content-type": "application/json"})


def request_shapes() -> dict[str, Any]:
    """Exercise baseline and guided through exactly the factories used by a real run."""
    text_skill_id = text_skill_catalog(SKILLS)[0]["skill_id"]
    baseline_handler = _SequenceHandler([_completion(0, content=json.dumps({"product_copy": "清韵折叠阅读灯以竹木与半透明纸质扩散罩营造安静阅读光线，适合书房与旅途。", "image_design_spec": "以展开的折叠阅读灯为主体，突出竹木纹理、纸罩透光和米白墨色的克制留白。", "used_source_ids": ["fixture-source"]}, ensure_ascii=False))])
    guided_handler = _SequenceHandler([
        _completion(0, tool_name="load_generation_skill", arguments={"skill_id": text_skill_id}),
        _completion(1, content=json.dumps({"product_copy": "清韵折叠阅读灯以竹木与半透明纸质扩散罩营造安静阅读光线，适合书房与旅途。", "image_design_spec": "以展开的折叠阅读灯为主体，突出竹木纹理、纸罩透光和米白墨色的克制留白。", "used_source_ids": ["fixture-source"]}, ensure_ascii=False)),
    ])
    original = pydantic_models.ALLOW_MODEL_REQUESTS
    pydantic_models.ALLOW_MODEL_REQUESTS = True
    try:
        evidence = {"query": "fixture", "top_k": 1, "status": "grounded", "reason": "fixture", "sources": [{"source_id": "fixture-source", "title": "Fixture", "evidence": {"period": "Qing"}, "license": "CC0-1.0", "source_url": "https://example.invalid/source"}]}
        baseline_wire = {"requests": 0, "attempts": []}
        baseline_client = build_dashscope_client(api_key="offline-test-key", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", transport=httpx.MockTransport(baseline_handler), counter=baseline_wire)
        guided_client = build_dashscope_client(api_key="offline-test-key", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", transport=httpx.MockTransport(guided_handler))
        run_baseline(build_model(model_name="qwen3.7-plus", openai_client=baseline_client), BRIEF_PAYLOAD["brief"], evidence)
        run_guided(build_model(model_name="qwen3.7-plus", openai_client=guided_client), BRIEF_PAYLOAD["brief"], evidence)
    finally:
        pydantic_models.ALLOW_MODEL_REQUESTS = original
    return {"transport": "httpx.MockTransport", "baseline": baseline_handler.requests, "guided": guided_handler.requests, "baseline_wire": baseline_wire, "catalog": text_skill_catalog(SKILLS), "fixture_selected_text_skill": text_skill_id}
