import asyncio

import pytest
from pydantic import ValidationError
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from backend.agents.design_conversation import DESIGN_CONVERSATION_DEFINITION, DesignConversationService, build_design_tool_registry
from backend.agents.design_conversation.outputs import (
    ConversationReply,
    ProviderConversationReplyV2,
    adapt_provider_reply_v2,
)
from backend.agents.design_conversation.tools import SearchCulturalKnowledgeInput, search_cultural_knowledge
from backend.agents.runtime import AgentRunStatus, RuntimeContext, ToolExecutor
from backend.agents.runtime.adapters import PydanticAIRuntimeEngine


def state_reader(user_id, session_id):
    assert (user_id, session_id) == ("owner", "session-1")
    return {"status": "created", "text_revision_count": 0, "brief_summary": None, "unresolved_fields": []}


def reply(message, intent="general_answer", *, artifact=None, business_action=None, suggestions=None):
    return {
        "contract_version": "conversation_reply_v2", "message": message, "intent": intent,
        "suggestions": suggestions or [], "rag_status": None, "artifact": artifact,
        "business_action": business_action,
    }


def brief_artifact():
    return {
        "artifact_type": "brief", "summary": "现代家居陶杯垫的初步设计 Brief。",
        "brief": {
            "title": "现代景德镇陶杯垫", "product_type": "陶杯垫",
            "design_goal": "为书桌场景提供克制耐用的日常承托。",
            "concept": "以留白和低饱和釉色表达现代转译，避免复刻传统器型。",
            "assumptions": ["默认用于室内书桌"], "confirmed_constraints": [],
            "tentative_fields": ["釉色深浅"], "unresolved_questions": [],
        },
        "evidence_source_ids": [], "used_skill_ids": [], "preserved_constraints": [],
    }


def revision_artifact():
    return {
        "artifact_type": "design_revision", "summary": "将色彩改为低饱和自然色的修订建议。",
        "revision": {
            "title": "自然色修订", "change_summary": "降低颜色对竹编纹理的干扰。",
            "changes": ["改用低饱和自然色"], "affected_constraints": ["现代简约"], "unresolved_questions": [],
        },
        "evidence_source_ids": [], "used_skill_ids": [], "preserved_constraints": ["避免仿古"],
    }


def engine(model):
    return PydanticAIRuntimeEngine(ToolExecutor(build_design_tool_registry()), FunctionModel(model))


def run_model(response, text="测试输入"):
    async def model(_messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, response)])
    return asyncio.run(DesignConversationService(engine(model), state_reader).run_turn(
        "owner", "session-1", text, {"current_user_input": text},
    ))


@pytest.mark.parametrize("intent", ["general_answer", "exploration", "design_critique"])
def test_non_artifact_intents_reject_an_attachment(intent):
    with pytest.raises(ValidationError, match="only allowed for an artifact intent"):
        ConversationReply.model_validate({
            "message": "这是一段自然回复。", "intent": intent,
            "artifact_proposal": {"kind": "brief", "content": brief_artifact()["brief"],
                                  "summary": "独立的设计摘要。", "valid": True},
        })


def test_artifact_and_business_action_have_bidirectional_contracts():
    with pytest.raises(ValidationError, match="artifact_proposal is required"):
        ConversationReply.model_validate({"message": "整理好了。", "intent": "brief_proposal"})
    with pytest.raises(ValidationError, match="artifact kind must match"):
        ConversationReply.model_validate({
            "message": "整理好了。", "intent": "brief_proposal",
            "artifact_proposal": {"kind": "design_revision", "content": revision_artifact()["revision"],
                                  "summary": "独立的修订摘要。", "valid": True},
        })
    with pytest.raises(ValidationError, match="business_action"):
        ConversationReply.model_validate({
            "message": "可以保存。", "intent": "general_answer",
            "business_action": {"action": "confirm_brief", "reason_summary": "会写入正式稿。"},
        })
    with pytest.raises(ValidationError, match="business_action"):
        ConversationReply.model_validate({"message": "请确认。", "intent": "business_action_request"})


def test_v2_provider_rejects_legacy_envelopes_and_invalid_artifacts():
    with pytest.raises(ValidationError):
        ProviderConversationReplyV2.model_validate({"kind": "propose_brief", "payload": {}})
    with pytest.raises(ValidationError):
        ProviderConversationReplyV2.model_validate(reply("这是回复。", "brief_proposal", artifact={
            "artifact_type": "brief", "summary": "有效摘要文本。", "brief": {"kind": "brief", "payload": {}},
        }))
    with pytest.raises(ValidationError):
        ProviderConversationReplyV2.model_validate(reply("这是回复。", "brief_proposal", artifact={
            "artifact_type": "brief", "summary": "有效摘要文本。", "brief": {},
        }))


def test_v2_provider_normalizes_closed_action_payload_envelope():
    provider = ProviderConversationReplyV2.model_validate(reply(
        "我已整理好一版试稿方向，确认后会进入图片生成。", "business_action_request",
        business_action={"action": "generate_image_from_conversation", "payload": {"presentation_mode": "three_view"}},
    ))
    result = ConversationReply.model_validate(adapt_provider_reply_v2(provider))
    assert result.business_action.action.value == "generate_image_from_conversation"
    assert result.business_action.snapshot == {"presentation_mode": "three_view"}
    assert result.business_action.reason_summary


def test_valid_v2_brief_and_revision_pass_full_contract_without_message_copy():
    brief = ProviderConversationReplyV2.model_validate(reply("我整理了一版可继续修改的 Brief。", "brief_proposal", artifact=brief_artifact()))
    result = ConversationReply.model_validate(adapt_provider_reply_v2(brief))
    assert result.artifact_proposal.kind == "brief"
    assert result.artifact_proposal.summary != result.message
    revision = ProviderConversationReplyV2.model_validate(reply("这里是一版修改建议。", "design_revision", artifact=revision_artifact()))
    assert ConversationReply.model_validate(adapt_provider_reply_v2(revision)).artifact_proposal.kind == "design_revision"


def test_exploration_is_message_only_and_never_exposes_formal_validator():
    async def model(_messages, info):
        assert "validate_design_constraints" not in {tool.name for tool in info.function_tools}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, reply(
            "我先按现代景德镇方向给出一版初步构思，材质可以先比较哑光陶和软木两条路线。", "exploration",
        ))])
    result = asyncio.run(DesignConversationService(engine(model), state_reader).run_turn(
        "owner", "session-1", "我还是比较犹豫，因为材质问题，你先出一版我看看", {"current_user_input": "我还是比较犹豫，因为材质问题，你先出一版我看看"},
    ))
    assert result.status == AgentRunStatus.COMPLETED
    assert result.final_output["intent"] == "exploration"
    assert result.final_output["artifact_proposal"] is None


def test_explicit_brief_has_an_unsaved_attachment_without_business_action():
    result = run_model(reply("我已按讨论整理成一版正式 Brief，仍未保存。", "brief_proposal", artifact=brief_artifact()), "整理成正式 Brief，但先不要保存")
    assert result.status == AgentRunStatus.COMPLETED
    assert result.final_output["artifact_proposal"]["valid"] is True
    assert result.final_output["business_action"] is None


def test_unsaved_brief_does_not_expose_formal_validator_despite_the_save_word():
    async def model(_messages, info):
        assert "validate_design_constraints" not in {tool.name for tool in info.function_tools}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, reply(
            "我已整理成一版正式 Brief，仍未保存。", "brief_proposal", artifact=brief_artifact(),
        ))])
    result = asyncio.run(DesignConversationService(engine(model), state_reader).run_turn(
        "owner", "session-1", "整理成正式 Brief，但先不要保存", {"current_user_input": "整理成正式 Brief，但先不要保存"},
    ))
    assert result.status == AgentRunStatus.COMPLETED


def test_critique_and_research_are_natural_message_only_replies():
    for response, text, intent in [
        (reply("这份文字稿的卖点明确，但缺少清洁方式和承重边界。", "design_critique"), "你觉得文字稿有什么问题？", "design_critique"),
        (reply("竹编通常通过经纬交错获得通风和承托结构；未检索到资料时应说明边界。", "cultural_research"), "竹编有哪些结构特点？", "cultural_research"),
    ]:
        result = run_model(response, text)
        assert result.status == AgentRunStatus.COMPLETED
        assert result.final_output["intent"] == intent
        assert result.final_output["artifact_proposal"] is None


def test_one_output_schema_retry_can_finish_after_a_read_only_tool_without_replaying_it():
    calls = []

    async def model(_messages, info):
        calls.append(info)
        if len(calls) == 1:
            return ModelResponse(parts=[ToolCallPart("search_cultural_knowledge", {"query": "竹编收纳篮", "top_k": 1})])
        if len(calls) == 2:
            # Simulate a provider that omits a required V2 field on its first
            # final-result tool call. The Runtime may ask for output repair,
            # but it must not rerun the read-only search.
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"contract_version": "conversation_reply_v2"})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, reply(
            "我会按轻量、通风和可陈列的方向给出一版竹编收纳篮方案。", "exploration",
        ))])

    result = asyncio.run(DesignConversationService(engine(model), state_reader).run_turn(
        "owner", "session-1", "设计一个竹编收纳篮", {"current_user_input": "设计一个竹编收纳篮"},
    ))

    assert result.status == AgentRunStatus.COMPLETED
    assert result.final_output["message"].startswith("我会按轻量")
    assert len(calls) == 3
    assert result.usage.executed_calls_by_tool == {"search_cultural_knowledge": 1}


def test_invalid_final_reply_after_a_successful_read_only_tool_uses_safe_continuation():
    calls = []

    async def model(_messages, info):
        calls.append(info)
        if len(calls) == 1:
            return ModelResponse(parts=[ToolCallPart("search_cultural_knowledge", {"query": "竹编收纳篮", "top_k": 1})])
        if len(calls) == 2:
            # Provider schema accepts this, but the domain adapter correctly
            # rejects an attachment paired with a non-artifact intent.
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, reply(
                "我先给出方向。", "general_answer", artifact=brief_artifact(),
            ))])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, reply(
            "The previous output was invalid. Here is the corrected compact JSON envelope.", "general_answer",
        ))])

    result = asyncio.run(DesignConversationService(engine(model), state_reader).run_turn(
        "owner", "session-1", "设计一个竹编收纳篮", {"current_user_input": "设计一个竹编收纳篮"},
    ))

    assert result.status == AgentRunStatus.COMPLETED
    assert result.final_output["output_origin"] == "system_fallback"
    assert result.final_output["business_action"] is None
    assert result.usage.executed_calls_by_tool == {"search_cultural_knowledge": 1}


def test_one_bounded_repair_can_correct_a_usable_v2_reply_without_exceeding_budget():
    calls = []
    async def model(_messages, info):
        calls.append(info)
        if len(calls) == 1:
            # Structurally V2 but semantically inconsistent, so a one-shot repair is allowed.
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, reply("我先给出材质方向。", "general_answer", artifact=brief_artifact()))])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, reply("我建议先比较哑光陶、软木和竹纤维复合材的触感与耐污性。", "exploration"))])
    result = asyncio.run(DesignConversationService(engine(model), state_reader).run_turn(
        "owner", "session-1", "先出一版材质方向", {"current_user_input": "先出一版材质方向"},
    ))
    assert result.status == AgentRunStatus.COMPLETED
    assert result.final_output["output_origin"] == "provider_repair"
    assert result.final_output["artifact_proposal"] is None
    assert result.usage.model_requests == 2 <= 7


def test_repair_echo_and_legacy_first_output_are_retryable_failures_not_briefs():
    calls = []
    async def echo_model(_messages, info):
        calls.append(info)
        if len(calls) == 1:
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, reply("我先给出材质方向。", "general_answer", artifact=brief_artifact()))])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, reply(
            "The previous output was invalid. Here is the corrected compact JSON envelope.", "general_answer",
        ))])
    echoed = asyncio.run(DesignConversationService(engine(echo_model), state_reader).run_turn(
        "owner", "session-1", "先出一版", {"current_user_input": "先出一版"},
    ))
    assert echoed.status == AgentRunStatus.FAILED
    assert echoed.error.code == "RUNTIME_OUTPUT_REPAIR_INVALID"
    assert echoed.final_output is None
    assert echoed.usage.model_requests <= 7

    async def legacy_model(_messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"kind": "propose_brief", "payload": {}})])
    legacy = asyncio.run(DesignConversationService(engine(legacy_model), state_reader).run_turn(
        "owner", "session-1", "先出一版", {"current_user_input": "先出一版"},
    ))
    assert legacy.status == AgentRunStatus.FAILED
    assert legacy.error.code == "RUNTIME_OUTPUT_REPAIR_INVALID"
    assert legacy.final_output is None


def test_repair_prompt_is_v2_only_and_contains_no_legacy_discriminated_contract():
    prompt = PydanticAIRuntimeEngine._repair_prompt(DESIGN_CONVERSATION_DEFINITION, reply("有效正文"), ValueError("bad"))
    lower = prompt.lower()
    for forbidden in ("propose_brief", "propose_design_revision", "request_business_action", "kind and payload", "compact json envelope"):
        assert forbidden not in lower
    assert "conversation_reply_v2" in lower


def test_creative_only_is_metadata_not_an_artifact_gate():
    class NoMatchRag:
        def decide_query(self, _query, _top_k):
            return type("Decision", (), {"status": "no_match", "reason": "no_match", "results": ()})
    context = RuntimeContext("owner", "session-1", "design_conversation", "created", {
        "cultural_rag": NoMatchRag(), "design_runtime_state": {"retrieved_source_ids": set()},
    })
    assert search_cultural_knowledge(context, SearchCulturalKnowledgeInput(query="竹编收纳筐")).status == "creative_only"
