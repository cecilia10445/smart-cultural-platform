import asyncio

from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from backend.agents.design_conversation import DESIGN_CONVERSATION_DEFINITION, DesignConversationService, build_design_tool_registry
from backend.agents.runtime import (
    AgentRunResult,
    AgentRunStatus,
    RuntimeUsage,
    ToolError,
    ToolExecutor,
)
from backend.agents.runtime.models import TraceRecord
from backend.agents.runtime.adapters import PydanticAIRuntimeEngine


class FakeRag:
    def decide_query(self, query, top_k):
        assert query == "青花瓷"
        assert top_k == 1
        item = type("Result", (), {"source_id": "source-1", "title": "Blue-and-white porcelain", "evidence": {"fact": "Cobalt decoration"}})
        return type("Decision", (), {"status": "matched", "reason": "reliable_match", "results": (item,)})


def state_reader(user_id, session_id):
    assert (user_id, session_id) == ("owner", "session-1")
    return {"status": "created", "text_revision_count": 0, "brief_summary": "No confirmed brief", "unresolved_fields": ["product_type"]}


def test_design_conversation_function_model_reads_each_tool_observation_before_next_step():
    observed = []

    async def model(messages, info):
        returns = [part for message in messages for part in message.parts if isinstance(part, ToolReturnPart)]
        observed.append([part.tool_name for part in returns])
        if not returns:
            return ModelResponse(parts=[ToolCallPart("inspect_design_state", {}, "state")])
        if len(returns) == 1:
            assert returns[0].content["output"]["session_id"] == "session-1"
            return ModelResponse(parts=[ToolCallPart("search_cultural_knowledge", {"query": "青花瓷", "top_k": 1}, "rag")])
        if len(returns) == 2:
            assert returns[1].content["output"]["sources"][0]["source_id"] == "source-1"
            return ModelResponse(parts=[ToolCallPart("load_design_skill", {"skill_id": "heritage-motif-translation"}, "skill")])
        if len(returns) == 3:
            assert returns[2].content["output"]["skill_id"] == "heritage-motif-translation"
            return ModelResponse(parts=[ToolCallPart("validate_design_constraints", {
                "candidate_brief": {}, "evidence_source_ids": ["source-1"], "skill_ids": ["heritage-motif-translation"]
            }, "validate")])
        assert returns[3].content["output"]["requires_user_confirmation"] is True
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "kind": "propose_brief", "payload": {"brief": {}, "summary": "Need details before confirmation.", "assumptions": [],
            "evidence_source_ids": ["source-1"], "used_skill_ids": ["heritage-motif-translation"], "used_memory_ids": []}
        })])

    engine = PydanticAIRuntimeEngine(ToolExecutor(build_design_tool_registry()), FunctionModel(model))
    service = DesignConversationService(engine, state_reader, FakeRag())
    result = asyncio.run(service.run_turn("owner", "session-1", "设计青花瓷文创"))
    assert result.status == "completed"
    assert result.final_output["result"]["kind"] == "propose_brief"
    assert [item.tool_name for item in result.tool_results] == [
        "inspect_design_state", "search_cultural_knowledge", "load_design_skill", "validate_design_constraints",
    ]
    assert observed == [[], ["inspect_design_state"], ["inspect_design_state", "search_cultural_knowledge"],
                        ["inspect_design_state", "search_cultural_knowledge", "load_design_skill"],
                        ["inspect_design_state", "search_cultural_knowledge", "load_design_skill", "validate_design_constraints"]]


def test_design_conversation_returns_valid_ask_user_after_bounded_tool_loop_exhaustion():
    class ExhaustedEngine:
        async def run(self, definition, context, runtime_input):
            return AgentRunResult(
                run_id="run-1",
                status=AgentRunStatus.FAILED,
                error=ToolError(code="MODEL_REQUEST_LIMIT_EXCEEDED", message="budget exceeded"),
                usage=RuntimeUsage(model_requests=7, requested_tool_calls=4),
                traces=[TraceRecord(
                    run_id="run-1", step=1, event_type="budget_exceeded",
                    error_code="TOOL_CALL_LIMIT_EXCEEDED", budget_snapshot={},
                )],
            )

    result = asyncio.run(DesignConversationService(ExhaustedEngine(), state_reader).run_turn(
        "owner", "session-1", "请提出文创 Brief",
    ))

    assert result.status == AgentRunStatus.COMPLETED
    assert result.error is None
    assert result.final_output["result"]["kind"] == "ask_user"
