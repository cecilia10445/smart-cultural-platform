import asyncio

import httpx
from pydantic import BaseModel
from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from backend.agents.runtime import (
    AgentDefinition, AgentRunStatus, RuntimeContext, RuntimeInput, RuntimeUsage, ToolExecutor, ToolRegistry, ToolRisk, ToolSpec,
)
from backend.agents.runtime.adapters import PydanticAIRuntimeEngine
from backend.agents.runtime.trace import TraceRecorder


class ValueInput(BaseModel):
    value: int


class ValueOutput(BaseModel):
    value: int


class FinalOutput(BaseModel):
    answer: str


def add_one(_context, value):
    return {"value": value.value + 1}


def multiply_two(_context, value):
    return {"value": value.value * 2}


def runtime(model, *, risk=ToolRisk.READ_ONLY):
    registry = ToolRegistry()
    registry.register(ToolSpec("add_one", "Increment one number.", ValueInput, ValueOutput, add_one, risk,
                               frozenset({"test_agent"}), frozenset({"ready"}), 1, 2))
    registry.register(ToolSpec("multiply_two", "Multiply one number by two.", ValueInput, ValueOutput, multiply_two,
                               ToolRisk.READ_ONLY, frozenset({"test_agent"}), frozenset({"ready"}), 1, 2))
    definition = AgentDefinition("test_agent", "Use the available tools before answering.",
                                 frozenset({"add_one", "multiply_two"}), FinalOutput, 5, 4, 2)
    return PydanticAIRuntimeEngine(ToolExecutor(registry), model), definition


def run(engine, definition):
    return asyncio.run(engine.run(definition, RuntimeContext("user", "session", "test_agent", "ready"),
                                  RuntimeInput(text="derive a value", request_id="request")))


def test_function_model_runs_tool_a_then_observation_driven_tool_b_then_final():
    seen = []

    async def model(messages, info):
        returns = [part for message in messages for part in message.parts if isinstance(part, ToolReturnPart)]
        seen.append((len(returns), [tool.name for tool in info.function_tools]))
        if not returns:
            return ModelResponse(parts=[ToolCallPart("add_one", {"value": 2}, "call-a")])
        if len(returns) == 1:
            assert returns[0].tool_call_id == "call-a"
            assert returns[0].content["output"] == {"value": 3}
            return ModelResponse(parts=[ToolCallPart("multiply_two", {"value": returns[0].content["output"]["value"]}, "call-b")])
        assert returns[1].tool_call_id == "call-b"
        assert returns[1].content["output"] == {"value": 6}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"answer": "computed 6"})])

    engine, definition = runtime(FunctionModel(model))
    result = run(engine, definition)
    assert result.status == "completed"
    assert result.final_output == {"answer": "computed 6"}
    assert [item.tool_call_id for item in result.tool_results] == ["call-a", "call-b"]
    assert seen == [(0, ["add_one", "multiply_two"]), (1, ["add_one", "multiply_two"]), (2, ["add_one", "multiply_two"])]


def test_function_model_final_and_high_risk_pause_are_projected_without_internal_messages():
    async def direct(_messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"answer": "direct"})])

    engine, definition = runtime(FunctionModel(direct))
    result = run(engine, definition)
    assert result.status == "completed" and result.final_output == {"answer": "direct"}
    assert all("ModelResponse" not in str(item.model_dump()) for item in result.traces)

    async def high_risk(_messages, _info):
        return ModelResponse(parts=[ToolCallPart("add_one", {"value": 2}, "approval-call")])

    engine, definition = runtime(FunctionModel(high_risk), risk=ToolRisk.HIGH_RISK)
    result = run(engine, definition)
    assert result.status == "pending_approval"
    assert result.pending_approval.tool_call_id == "approval-call"
    assert result.usage.executed_tool_calls == 0


def test_model_transport_failure_is_classified_without_persisting_provider_text():
    error = httpx.ReadTimeout("provider body must not escape", request=httpx.Request("POST", "https://provider.invalid"))
    code = PydanticAIRuntimeEngine._classify_runtime_exception(error)
    summary = PydanticAIRuntimeEngine._safe_runtime_failure_summary(error, code)
    result = PydanticAIRuntimeEngine._failed("run-1", RuntimeUsage(), TraceRecorder("run-1"), [], code, "run_failed")

    assert result.status is AgentRunStatus.FAILED
    assert result.error.code == "RUNTIME_MODEL_TIMEOUT"
    assert result.error.message == "The assistant request timed out."
    assert summary == {
        "phase": "model_run",
        "failure_family": "RUNTIME_MODEL_TIMEOUT",
        "exception_type": "ReadTimeout",
    }
    assert "provider body" not in str({"result": result.model_dump(), "summary": summary})


def test_runtime_failure_codes_distinguish_transport_provider_and_adapter_boundaries():
    assert PydanticAIRuntimeEngine._classify_runtime_exception(httpx.ConnectError("hidden")) == "RUNTIME_PROVIDER_UNAVAILABLE"
    wrapped_timeout = ModelAPIError("qwen-plus", "hidden")
    wrapped_timeout.__cause__ = httpx.ReadTimeout("hidden", request=httpx.Request("POST", "https://provider.invalid"))
    assert PydanticAIRuntimeEngine._classify_runtime_exception(wrapped_timeout) == "RUNTIME_MODEL_TIMEOUT"
    assert PydanticAIRuntimeEngine._classify_runtime_exception(ValueError("hidden")) == "RUNTIME_EXECUTION_FAILED"


def test_repair_prompt_carries_only_the_previous_user_visible_reply():
    prompt = PydanticAIRuntimeEngine._repair_prompt(None, {
        "contract_version": "conversation_reply_v2", "message": "为竹编收纳筐生成三视图试稿。",
        "intent": "business_action_request", "suggestions": [], "rag_status": None,
        "artifact": None, "business_action": "generate_image_from_conversation",
        "provider_raw_response": "must not be included",
    }, ValueError("business_action"))
    assert "为竹编收纳筐生成三视图试稿。" in prompt
    assert "generate_image_from_conversation" in prompt
    assert "must not be included" not in prompt


def test_missing_structured_final_output_uses_one_no_tool_json_text_retry():
    calls = []

    async def model(_messages, info):
        calls.append([tool.name for tool in info.function_tools])
        if info.function_tools:
            # Compatible providers can acknowledge a read-only Function Calling
            # loop yet omit the structured output-tool payload.
            return ModelResponse(parts=[])
        return ModelResponse(parts=[TextPart('{"answer":"recovered"}')])

    engine, definition = runtime(FunctionModel(model))
    result = run(engine, definition)

    assert result.status is AgentRunStatus.COMPLETED
    assert result.final_output == {"answer": "recovered"}
    assert calls[-1] == []
    assert all(call == ["add_one", "multiply_two"] for call in calls[:-1])
    assert any(item.event_type == "output_retry_requested" for item in result.traces)


def test_explicit_image_request_guard_only_requests_a_model_correction():
    assert PydanticAIRuntimeEngine._requires_image_action("请根据刚才讨论直接生成一版三视图效果图")
    assert PydanticAIRuntimeEngine._requires_image_action("请画一版正反面")
    assert not PydanticAIRuntimeEngine._requires_image_action("图片完成后我还想继续讨论材质")
    assert not PydanticAIRuntimeEngine._is_conversation_image_action({
        "intent": "clarification", "business_action": None,
    })
    assert PydanticAIRuntimeEngine._is_conversation_image_action({
        "intent": "business_action_request",
        "business_action": {"action": "generate_image_from_conversation"},
    })
