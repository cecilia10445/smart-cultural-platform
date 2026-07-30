from pydantic import BaseModel
import pytest

from backend.agents.runtime import ToolRegistry, ToolRisk, ToolSpec


class EchoInput(BaseModel):
    text: str


class EchoOutput(BaseModel):
    echoed: str


def handler(_context, value):
    return {"echoed": value.text}


def spec(name="echo_tool", risk=ToolRisk.READ_ONLY, agents=frozenset({"designer"}), statuses=frozenset({"draft"})):
    return ToolSpec(name, "Echo a small test value", EchoInput, EchoOutput, handler, risk, agents, statuses, 1, 2)


def test_registry_is_deterministic_and_rejects_duplicates():
    registry = ToolRegistry()
    registry.register(spec("zeta_tool"))
    registry.register(spec("alpha_tool"))
    assert [item.name for item in registry.list_all()] == ["alpha_tool", "zeta_tool"]
    with pytest.raises(ValueError, match="already registered"):
        registry.register(spec("alpha_tool"))
    assert registry.get("missing") is None
    with pytest.raises(KeyError):
        registry.require("missing")


def test_registry_exports_only_allowed_non_forbidden_openai_schemas():
    registry = ToolRegistry()
    registry.register_many([
        spec("available_tool"), spec("wrong_agent", agents=frozenset({"writer"})),
        spec("wrong_status", statuses=frozenset({"approved"})), spec("forbidden_tool", ToolRisk.FORBIDDEN),
    ])
    exported = registry.export_openai_schema("designer", "draft")
    assert [item["function"]["name"] for item in exported] == ["available_tool"]
    parameters = exported[0]["function"]["parameters"]
    assert parameters["properties"]["text"]["type"] == "string"
    assert "handler" not in str(exported)


def test_tool_spec_validates_models_and_function_call_name():
    with pytest.raises(ValueError):
        spec("not-valid-name")
    with pytest.raises(TypeError):
        ToolSpec("bad_tool", "x", dict, EchoOutput, handler, ToolRisk.READ_ONLY)
