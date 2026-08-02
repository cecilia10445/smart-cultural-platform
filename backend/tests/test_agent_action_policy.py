from datetime import datetime

from backend.agents.actions.policy import ActionPolicyInput, available_actions, evaluate_action
from backend.domain.agent_design_domain import (
    ActionType, ArtifactRecord, ArtifactStatus, ArtifactType, ConversationProjection,
    ConversationStatus, DesignTaskOrigin, DesignTaskRecord, DesignTaskStatus, canonical_json_hash,
)
from backend.domain.agent_dialogue import AgentSessionStatus
from backend.services.agent_action_service import AgentActionService
from backend.agents.design_conversation.outputs import ConversationReply, ProviderConversationReplyV2, adapt_provider_reply_v2


NOW = datetime(2026, 8, 1)


def conversation(status=ConversationStatus.ACTIVE):
    return ConversationProjection(id="s", user_id="u", conversation_status=status, version=1, created_at=NOW, updated_at=NOW,
                                  legacy_session_status=AgentSessionStatus.COMPLETED.value)


def task(status=DesignTaskStatus.EXPLORING):
    return DesignTaskRecord(id="t", user_id="u", session_id="s", title="task", status=status, origin=DesignTaskOrigin.NATIVE,
                            version=1, created_at=NOW, updated_at=NOW)


def artifact(kind=ArtifactType.BRIEF, status=ArtifactStatus.CONFIRMED):
    return ArtifactRecord(id="a", user_id="u", session_id="s", task_id="t", artifact_type=kind, status=status, version_number=1,
                          content_json={"safe": True}, content_hash="0" * 64, origin="native", created_at=NOW)


def decision(action, *, status=ConversationStatus.ACTIVE, task_status=DesignTaskStatus.EXPLORING, snapshot=None, artifacts=()):
    return evaluate_action(ActionPolicyInput(user_id="u", conversation=conversation(status), active_task=task(task_status), artifacts=tuple(artifacts),
                                              requested_action_type=action, proposal_snapshot=snapshot or {}))


def test_legacy_completed_status_does_not_block_native_task_actions():
    assert decision(ActionType.SAVE_BRIEF, snapshot={"proposal_kind": "brief"}).allowed


def test_archived_and_closed_states_block_actions_without_legacy_state():
    assert decision(ActionType.ARCHIVE_TASK, status=ConversationStatus.ARCHIVED).code == "CONVERSATION_ARCHIVED"
    assert decision(ActionType.SAVE_BRIEF, task_status=DesignTaskStatus.CLOSED, snapshot={"proposal_kind": "brief"}).code == "TASK_CLOSED"


def test_action_requirements_are_explicit_and_direct_generation_needs_no_brief():
    direct = decision(ActionType.GENERATE_IMAGE_FROM_CONVERSATION, snapshot={"confirmed_constraints": ["x"], "tentative_assumptions": ["y"], "source_message_ids": ["m"], "presentation_mode": "product"})
    assert direct.allowed
    assert decision(ActionType.GENERATE_IMAGE_FROM_ARTIFACT, snapshot={"selected_artifact_ids": ["a"]}, artifacts=[artifact()]).allowed
    assert decision(ActionType.REGENERATE_IMAGE, snapshot={}).code == "IMAGE_SOURCE_REQUIRED"


def test_available_actions_is_deterministic_and_never_exposes_legacy_enum():
    values = available_actions(conversation(), None, [])
    assert len(values) == len(ActionType)
    by_type = {item["action_type"]: item for item in values}
    assert by_type[ActionType.ARCHIVE_TASK]["disabled_reason"] == "Choose a design task before archiving it."
    assert by_type[ActionType.GENERATE_IMAGE_FROM_CONVERSATION]["disabled_reason"] != "Create or select a design task before using this action."


def test_conversation_scope_can_generate_without_creating_a_task():
    result = evaluate_action(ActionPolicyInput(
        user_id="u", conversation=conversation(), active_task=None, requested_action_type=ActionType.GENERATE_IMAGE_FROM_CONVERSATION,
        proposal_snapshot={"confirmed_constraints": ["竹编收纳篮"], "tentative_assumptions": ["生成试稿"],
                           "source_message_ids": ["m1"], "presentation_mode": "three_view"},
    ))
    assert result.allowed


def test_runtime_action_conversion_requires_typed_provider_business_action_not_keywords():
    service = AgentActionService(None)
    run = {"status": "completed", "final_output_json": {
        "message": "Please save this brief", "intent": "business_action_request", "output_origin": "provider",
        "business_action": {"action": "save_brief", "reason_summary": "Save the reviewed brief."},
    }}
    snapshot = service._runtime_proposal(run, ActionType.SAVE_BRIEF)
    assert snapshot["source_type"] == "runtime_proposal"
    fallback = {**run, "final_output_json": {**run["final_output_json"], "output_origin": "system_fallback"}}
    from backend.domain.agent_design_domain import ActionReferenceConflict
    import pytest
    with pytest.raises(ActionReferenceConflict):
        service._runtime_proposal(fallback, ActionType.SAVE_BRIEF)
    with pytest.raises(ActionReferenceConflict):
        service._runtime_proposal(run, ActionType.SAVE_DESIGN_TEXT)


def test_closed_provider_action_enum_is_adapted_but_unrelated_text_is_not_an_action():
    reply = ProviderConversationReplyV2.model_validate({
        "contract_version": "conversation_reply_v2", "message": "可以生成一版试稿。",
        "business_action": "generate_image_from_conversation",
    })
    value = adapt_provider_reply_v2(reply)
    assert value["intent"] == "business_action_request"
    assert value["business_action"]["action"] == "generate_image_from_conversation"
    assert ConversationReply.model_validate(value).business_action.action is ActionType.GENERATE_IMAGE_FROM_CONVERSATION


def test_conversation_image_snapshot_is_server_frozen_without_a_task():
    class Repository:
        def get_runtime_message_snapshot(self, user_id, session_id, task_id):
            assert (user_id, session_id, task_id) == ("u", "s", None)
            return [{"id": "m1", "role": "user", "content_text": "请生成竹编小篮子的三视图"}]
    service = AgentActionService(Repository())
    run = {"id": "r", "status": "completed", "task_id": None, "final_output_json": {
        "message": "我已整理出一版三视图试稿方向。", "intent": "business_action_request", "output_origin": "provider",
        "business_action": {"action": "generate_image_from_conversation", "reason_summary": "生成一版试稿。"},
    }}
    snapshot = service._runtime_proposal("u", "s", run, ActionType.GENERATE_IMAGE_FROM_CONVERSATION)
    assert snapshot["source_type"] == "conversation_snapshot"
    assert snapshot["source_task_id"] is None
    assert snapshot["source_message_ids"] == ["m1"]
    assert snapshot["presentation_mode"] == "three_view"
    assert snapshot["snapshot_hash"] == canonical_json_hash({key: snapshot.get(key) for key in (
        "source_type", "source_session_id", "source_task_id", "source_runtime_run_id", "source_message_ids",
        "source_artifact_ids", "parent_image_artifact_id", "confirmed_constraints", "tentative_assumptions",
        "positive_prompt", "negative_prompt", "presentation_mode", "provider_options",
    )})
