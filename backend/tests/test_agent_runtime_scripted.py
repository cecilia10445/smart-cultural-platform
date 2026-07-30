import asyncio

from pydantic import BaseModel

from backend.agents.runtime import AgentDefinition, RuntimeContext, RuntimeInput, ToolExecutor, ToolRegistry, ToolRisk, ToolSpec
from backend.agents.runtime.adapters import (
    ScriptedEmptyResponse, ScriptedFinalResponse, ScriptedMultipleToolCallsResponse,
    ScriptedRuntimeEngine, ScriptedToolCallResponse,
)
from backend.agents.runtime.models import ToolCall


class ToolInput(BaseModel):
    text: str


class ToolOutput(BaseModel):
    text: str


class FinalOutput(BaseModel):
    answer: str


def echo(_context, value):
    return {"text": value.text}


def engine(responses, *, max_requests=5, max_tools=4, per_tool=3, risk=ToolRisk.READ_ONLY):
    registry = ToolRegistry()
    registry.register(ToolSpec("echo_tool", "echo", ToolInput, ToolOutput, echo, risk, frozenset({"designer"}), frozenset({"draft"}), 1, per_tool))
    definition = AgentDefinition("designer", "Test scripted loop.", frozenset({"echo_tool"}), FinalOutput, max_requests, max_tools, per_tool)
    return ScriptedRuntimeEngine(ToolExecutor(registry), responses), definition


def run(responses, **kwargs):
    runtime, definition = engine(responses, **kwargs)
    return asyncio.run(runtime.run(definition, RuntimeContext("user", "session", "designer", "draft"), RuntimeInput(text="private input", request_id="req-1")))


def call(call_id="call-1", text="one"):
    return ScriptedToolCallResponse(ToolCall(tool_call_id=call_id, tool_name="echo_tool", arguments={"text": text}))


def test_scripted_runtime_supports_direct_final_and_two_tool_observations_then_final():
    direct = run([ScriptedFinalResponse({"answer": "done"})])
    assert direct.status == "completed" and direct.final_output == {"answer": "done"}
    result = run([call("a", "one"), call("b", "two"), ScriptedFinalResponse({"answer": "done"})])
    assert result.status == "completed" and [item.output for item in result.tool_results] == [{"text": "one"}, {"text": "two"}]
    assert result.usage.model_requests == 3


def test_scripted_runtime_stops_for_approval_and_handles_tool_failures():
    pending = run([call(), ScriptedFinalResponse({"answer": "never"})], risk=ToolRisk.HIGH_RISK)
    assert pending.status == "pending_approval" and pending.pending_approval.tool_name == "echo_tool"
    invalid = run([ScriptedToolCallResponse(ToolCall(tool_call_id="bad", tool_name="echo_tool", arguments={"unknown": 1})), ScriptedFinalResponse({"answer": "recovered"})])
    assert invalid.status == "completed" and invalid.tool_results[0].error.code == "TOOL_INPUT_INVALID"


def test_scripted_runtime_passes_unknown_and_forbidden_observations_without_execution():
    unknown = run([
        ScriptedToolCallResponse(ToolCall(tool_call_id="unknown", tool_name="not_registered", arguments={})),
        ScriptedFinalResponse({"answer": "recovered"}),
    ])
    assert unknown.status == "completed" and unknown.tool_results[0].error.code == "TOOL_NOT_FOUND"
    forbidden = run([call(), ScriptedFinalResponse({"answer": "recovered"})], risk=ToolRisk.FORBIDDEN)
    assert forbidden.status == "completed" and forbidden.tool_results[0].error.code == "TOOL_FORBIDDEN"


def test_scripted_runtime_enforces_model_and_tool_budgets_and_response_shape():
    model_limited = run([call(), ScriptedFinalResponse({"answer": "late"})], max_requests=1)
    assert model_limited.status == "failed" and model_limited.error.code == "MODEL_REQUEST_LIMIT_EXCEEDED"
    tool_limited = run([call("a", "one"), call("b", "two"), ScriptedFinalResponse({"answer": "late"})], max_tools=1)
    assert tool_limited.tool_results[-1].error.code == "TOOL_CALL_LIMIT_EXCEEDED"
    multiple = run([ScriptedMultipleToolCallsResponse((call("a").call, call("b").call))])
    assert multiple.status == "failed" and multiple.error.code == "MULTIPLE_TOOL_CALLS_NOT_ALLOWED" and not multiple.tool_results
    empty = run([ScriptedEmptyResponse()])
    assert empty.status == "failed" and empty.error.code == "EMPTY_MODEL_RESPONSE"
    bad_final = run([ScriptedFinalResponse({"missing": "answer"})])
    assert bad_final.error.code == "FINAL_OUTPUT_INVALID"


def test_trace_is_summary_only_and_never_records_private_payload_or_chain_of_thought():
    secret = "secret-value-and-hidden-reasoning"
    result = run([call("a", secret), ScriptedFinalResponse({"answer": secret})])
    trace_data = [item.model_dump(mode="json") for item in result.traces]
    assert all(secret not in str(item) for item in trace_data)
    assert all("arguments" not in item for item in trace_data)
    assert any(item["event_type"] == "tool_completed" for item in trace_data)
