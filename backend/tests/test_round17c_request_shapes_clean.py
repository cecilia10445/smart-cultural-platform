from __future__ import annotations

import asyncio

import httpx

from evaluation.round17c_request_shapes import request_shapes
from evaluation.round17c_runner import build_dashscope_client, sanitized_model_error


def test_mock_transport_records_the_real_runner_request_factories():
    evidence = request_shapes()
    baseline = evidence["baseline"]
    guided = evidence["guided"]

    assert evidence["transport"] == "httpx.MockTransport"
    assert len(baseline) == 1
    assert baseline[0]["business_tool_names"] == []
    assert baseline[0]["output_tool_names"] == []
    assert baseline[0]["response_format"] == {"type": "json_object"}
    assert baseline[0]["parallel_tool_calls"] in (None, False)
    assert baseline[0]["thinking"] == "disabled"
    assert baseline[0]["reasoning_effort"] == "none"
    assert baseline[0]["enable_thinking"] is None
    assert evidence["baseline_wire"]["requests"] == 1
    assert evidence["baseline_wire"]["attempts"][0]["stage"] == "unknown"
    assert evidence["baseline_wire"]["attempts"][0]["response_format"] == {"type": "json_object"}
    assert guided[0]["parallel_tool_calls"] is False
    assert guided[-1]["parallel_tool_calls"] in (None, False)
    assert all(shape["thinking"] == "disabled" for shape in guided)
    assert all(not shape["contains_visual_skill"] for shape in guided + baseline)
    assert guided[-1]["business_tool_names"] == []
    planner_tools = set(guided[0]["business_tool_names"])
    assert planner_tools == {"load_generation_skill"}
    assert guided[0]["tool_choice"] == "required"
    assert guided[0]["response_format"] is None
    assert all("retrieve_cultural_sources" not in shape["business_tool_names"] for shape in guided)
    assert all(not shape["output_tool_names"] for shape in guided)


def test_wire_attempt_is_recorded_before_connection_failure_without_secret_leakage():
    counter = {"requests": 0, "attempts": [], "stage": "baseline"}

    def unavailable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Authorization: Bearer offline-test-key unavailable", request=request)

    client = build_dashscope_client(
        api_key="offline-test-key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        transport=httpx.MockTransport(unavailable),
        counter=counter,
    )

    async def send() -> None:
        await client.chat.completions.create(model="qwen3.7-plus", messages=[{"role": "user", "content": "offline fixture"}])

    try:
        asyncio.run(send())
    except Exception as error:
        record = sanitized_model_error(error, stage="baseline", model_name="qwen3.7-plus", request_ordinal=counter["requests"], request_shape_hash=counter["attempts"][-1]["request_shape_sha256"])
    else:
        raise AssertionError("MockTransport must fail before a provider response")

    assert counter["requests"] == 1
    assert counter["attempts"][0]["stage"] == "baseline"
    assert record["request_ordinal"] == 1
    assert record["request_shape_sha256"] == counter["attempts"][0]["request_shape_sha256"]
    assert "offline-test-key" not in str(record)
    assert "Bearer" not in str(record)
