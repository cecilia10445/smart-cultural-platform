from pydantic import BaseModel

from backend.agents.runtime import AgentDefinition, RuntimeContext, ToolCall, ToolErrorCode, ToolPolicy, ToolRisk, ToolSpec


class Input(BaseModel):
    value: str


class Output(BaseModel):
    value: str


def handler(_context, value):
    return {"value": value.value}


def make_spec(risk=ToolRisk.READ_ONLY, statuses=frozenset({"draft"})):
    return ToolSpec("test_tool", "policy test", Input, Output, handler, risk, frozenset({"designer"}), statuses, 1, 1)


def definition():
    return AgentDefinition("designer", "Use only declared tools.", frozenset({"test_tool"}), Output)


def context(**changes):
    values = dict(user_id="u-1", session_id="s-1", agent_name="designer", session_status="draft")
    values.update(changes)
    return RuntimeContext(**values)


def call():
    return ToolCall(tool_call_id="call-1", tool_name="test_tool", arguments={"value": "x"})


def test_policy_allows_read_only_and_low_risk():
    policy = ToolPolicy()
    assert policy.authorize(definition(), context(), make_spec(ToolRisk.READ_ONLY), call()).allowed
    assert policy.authorize(definition(), context(), make_spec(ToolRisk.LOW_RISK), call()).allowed


def test_policy_requires_approval_for_high_risk_and_rejects_forbidden():
    policy = ToolPolicy()
    high = policy.authorize(definition(), context(), make_spec(ToolRisk.HIGH_RISK), call())
    assert high.approval_required and high.error_code is ToolErrorCode.TOOL_APPROVAL_REQUIRED
    forbidden = policy.authorize(definition(), context(), make_spec(ToolRisk.FORBIDDEN), call())
    assert not forbidden.allowed and forbidden.error_code is ToolErrorCode.TOOL_FORBIDDEN


def test_policy_rechecks_agent_and_status():
    policy = ToolPolicy()
    decision = policy.authorize(definition(), context(agent_name="other"), make_spec(), call())
    assert decision.error_code is ToolErrorCode.TOOL_POLICY_DENIED
    decision = policy.authorize(definition(), context(session_status="blocked"), make_spec(), call())
    assert decision.error_code is ToolErrorCode.TOOL_POLICY_DENIED
