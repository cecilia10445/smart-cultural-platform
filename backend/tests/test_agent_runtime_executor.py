import asyncio

from pydantic import BaseModel

from backend.agents.runtime import (
    AgentDefinition, RuntimeContext, RuntimeUsage, ToolCall, ToolCallLedger, ToolErrorCode,
    ToolExecutor, ToolPolicy, ToolRegistry, ToolRisk, ToolSpec,
)
from backend.agents.runtime.trace import TraceRecorder


class NumberInput(BaseModel):
    value: int


class NumberOutput(BaseModel):
    value: int


def agent(**overrides):
    values = dict(name="designer", instructions="test", allowed_tools=frozenset({"add_numbers", "slow_tool", "failing_tool", "invalid_output_tool", "high_risk_tool", "forbidden_tool"}), output_model=NumberOutput, max_total_tool_calls=8, max_calls_per_tool=3)
    values.update(overrides)
    return AgentDefinition(**values)


def context():
    return RuntimeContext("user", "session", "designer", "draft")


def add(_context, value):
    return {"value": value.value + 1}


async def slow(_context, value):
    await asyncio.sleep(0.04)
    return {"value": value.value}


def failing(_context, _value):
    raise RuntimeError("database password must never escape")


def invalid(_context, _value):
    return {"wrong": 1}


def build_registry():
    registry = ToolRegistry()
    for name, handler, risk, timeout in [
        ("add_numbers", add, ToolRisk.READ_ONLY, 1), ("slow_tool", slow, ToolRisk.READ_ONLY, 0.001),
        ("failing_tool", failing, ToolRisk.READ_ONLY, 1), ("invalid_output_tool", invalid, ToolRisk.READ_ONLY, 1),
        ("high_risk_tool", add, ToolRisk.HIGH_RISK, 1), ("forbidden_tool", add, ToolRisk.FORBIDDEN, 1),
    ]:
        registry.register(ToolSpec(name, name, NumberInput, NumberOutput, handler, risk, frozenset({"designer"}), frozenset({"draft"}), timeout, 2))
    return registry


async def execute(call, *, definition=None, ledger=None, usage=None):
    usage = usage or RuntimeUsage()
    recorder = TraceRecorder("run-test")
    outcome = await ToolExecutor(build_registry(), ToolPolicy()).execute(definition or agent(), context(), call, usage, ledger or ToolCallLedger(), recorder)
    return outcome, usage, recorder.records


def test_executor_validates_input_and_unknown_tool_without_leaking_details():
    outcome, usage, _ = asyncio.run(execute(ToolCall(tool_call_id="1", tool_name="add_numbers", arguments={"value": "bad"})))
    assert outcome.result.error.code == ToolErrorCode.TOOL_INPUT_INVALID.value
    assert usage.requested_tool_calls == 1 and usage.executed_tool_calls == 0
    outcome, _, _ = asyncio.run(execute(ToolCall(tool_call_id="2", tool_name="unknown", arguments={})))
    assert outcome.result.error.code == ToolErrorCode.TOOL_NOT_FOUND.value


def test_executor_runs_sync_handler_and_validates_errors():
    outcome, usage, _ = asyncio.run(execute(ToolCall(tool_call_id="1", tool_name="add_numbers", arguments={"value": 2})))
    assert outcome.result.ok and outcome.result.output == {"value": 3} and usage.executed_tool_calls == 1
    for name, code in [("failing_tool", ToolErrorCode.TOOL_EXECUTION_FAILED), ("invalid_output_tool", ToolErrorCode.TOOL_OUTPUT_INVALID), ("slow_tool", ToolErrorCode.TOOL_TIMEOUT)]:
        outcome, _, _ = asyncio.run(execute(ToolCall(tool_call_id=name, tool_name=name, arguments={"value": 1})))
        assert outcome.result.error.code == code.value
        assert "password" not in outcome.result.error.message


def test_high_risk_and_forbidden_never_invoke_handler():
    outcome, usage, _ = asyncio.run(execute(ToolCall(tool_call_id="h", tool_name="high_risk_tool", arguments={"value": 1})))
    assert outcome.pending_approval and outcome.result.error.code == ToolErrorCode.TOOL_APPROVAL_REQUIRED.value
    assert usage.executed_tool_calls == 0
    outcome, usage, _ = asyncio.run(execute(ToolCall(tool_call_id="f", tool_name="forbidden_tool", arguments={"value": 1})))
    assert outcome.result.error.code == ToolErrorCode.TOOL_FORBIDDEN.value and usage.executed_tool_calls == 0


def test_executor_denies_tools_not_granted_to_definition_or_status():
    denied_agent = agent(allowed_tools=frozenset())
    outcome, usage, _ = asyncio.run(execute(ToolCall(tool_call_id="d", tool_name="add_numbers", arguments={"value": 1}), definition=denied_agent))
    assert outcome.result.error.code == ToolErrorCode.TOOL_POLICY_DENIED.value and usage.executed_tool_calls == 0


def test_ledger_replays_identical_calls_and_rejects_conflicts():
    ledger, usage = ToolCallLedger(), RuntimeUsage()
    first, usage, _ = asyncio.run(execute(ToolCall(tool_call_id="same", tool_name="add_numbers", arguments={"value": 2}), ledger=ledger, usage=usage))
    replay, usage, traces = asyncio.run(execute(ToolCall(tool_call_id="same", tool_name="add_numbers", arguments={"value": 2}), ledger=ledger, usage=usage))
    conflict, usage, _ = asyncio.run(execute(ToolCall(tool_call_id="same", tool_name="add_numbers", arguments={"value": 3}), ledger=ledger, usage=usage))
    assert first.result.ok and replay.result.replayed and usage.executed_tool_calls == 1
    assert conflict.result.error.code == ToolErrorCode.TOOL_CALL_ID_CONFLICT.value
    assert traces[-1].event_type == "tool_replayed"


def test_budget_counts_unique_requests_and_spec_execution_limit():
    definition = agent(max_total_tool_calls=1, max_calls_per_tool=1)
    ledger, usage = ToolCallLedger(), RuntimeUsage()
    asyncio.run(execute(ToolCall(tool_call_id="1", tool_name="add_numbers", arguments={"value": 1}), definition=definition, ledger=ledger, usage=usage))
    outcome, usage, _ = asyncio.run(execute(ToolCall(tool_call_id="2", tool_name="failing_tool", arguments={"value": 1}), definition=definition, ledger=ledger, usage=usage))
    assert outcome.result.error.code == ToolErrorCode.TOOL_CALL_LIMIT_EXCEEDED.value
    per_tool = agent(max_total_tool_calls=8, max_calls_per_tool=1)
    ledger, usage = ToolCallLedger(), RuntimeUsage()
    asyncio.run(execute(ToolCall(tool_call_id="first", tool_name="add_numbers", arguments={"value": 1}), definition=per_tool, ledger=ledger, usage=usage))
    outcome, _, _ = asyncio.run(execute(ToolCall(tool_call_id="second", tool_name="add_numbers", arguments={"value": 2}), definition=per_tool, ledger=ledger, usage=usage))
    assert outcome.result.error.code == ToolErrorCode.TOOL_CALL_LIMIT_EXCEEDED.value
