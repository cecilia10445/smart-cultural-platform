import asyncio

from pydantic import BaseModel
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from backend.agents.runtime import (
    AgentDefinition, RuntimeContext, RuntimeInput, ToolExecutor, ToolRegistry, ToolRisk, ToolSpec,
)
from backend.agents.runtime.adapters import PydanticAIRuntimeEngine


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
