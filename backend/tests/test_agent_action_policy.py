from datetime import datetime

from backend.agents.actions.policy import ActionPolicyInput, available_actions, evaluate_action
from backend.domain.agent_design_domain import (
    ActionType, ArtifactRecord, ArtifactStatus, ArtifactType, ConversationProjection,
    ConversationStatus, DesignTaskOrigin, DesignTaskRecord, DesignTaskStatus,
)
from backend.domain.agent_dialogue import AgentSessionStatus
from backend.services.agent_action_service import AgentActionService


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
    assert all(item["disabled_reason"] == "Create or select a design task before using this action." for item in values)


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
