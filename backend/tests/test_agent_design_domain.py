from datetime import datetime

import pytest

from backend.domain.agent_design_domain import (
    ActionStatus, ActionType, ArtifactStatus, ArtifactType, ConversationStatus,
    DesignTaskStatus, DesignTaskTransitionConflict, TASK_TRANSITIONS,
    canonical_json_hash, project_legacy_session,
)
from backend.domain.agent_dialogue import AgentSessionStatus


def test_new_domain_enums_are_independent_from_legacy_session_status():
    assert set(ConversationStatus) == {ConversationStatus.ACTIVE, ConversationStatus.ARCHIVED}
    assert AgentSessionStatus.COMPLETED.value not in {item.value for item in ConversationStatus}
    assert set(ArtifactType) == {ArtifactType.BRIEF, ArtifactType.PRODUCT_DESIGN_TEXT, ArtifactType.VISUAL_DIRECTION, ArtifactType.IMAGE_PROMPT, ArtifactType.GENERATED_IMAGE}
    assert set(ArtifactStatus) == {ArtifactStatus.PROPOSED, ArtifactStatus.CONFIRMED, ArtifactStatus.SUPERSEDED}
    assert ActionType.GENERATE_IMAGE_FROM_CONVERSATION.value == "generate_image_from_conversation"
    assert ActionStatus.COMPLETED.value == "completed"


def test_task_transition_contract_has_no_artifact_or_run_statuses():
    assert TASK_TRANSITIONS[DesignTaskStatus.EXPLORING] == {DesignTaskStatus.ACTIVE, DesignTaskStatus.PAUSED, DesignTaskStatus.CLOSED}
    assert DesignTaskStatus.EXPLORING not in TASK_TRANSITIONS[DesignTaskStatus.ACTIVE]
    assert TASK_TRANSITIONS[DesignTaskStatus.CLOSED] == set()
    with pytest.raises(DesignTaskTransitionConflict):
        from backend.domain.agent_design_domain import assert_task_transition
        assert_task_transition(DesignTaskStatus.CLOSED, DesignTaskStatus.ACTIVE)


def test_canonical_hash_is_stable_for_key_order_and_changes_for_content():
    assert canonical_json_hash({"b": 2, "a": 1}) == canonical_json_hash({"a": 1, "b": 2})
    assert canonical_json_hash({"a": 1}) != canonical_json_hash({"a": 2})


def test_legacy_projection_is_stable_read_only_and_does_not_invent_absent_data():
    row = {
        "id": "session-1", "user_id": "U1", "status": "completed",
        "brief_json": {"product_type": "书签"}, "confirmed_text_json": None,
        "image_prompt_json": {"positive_prompt": "safe summary"}, "generation_log_id": 7,
        "created_at": datetime(2026, 8, 1),
    }
    first, second = project_legacy_session(row), project_legacy_session(dict(row))
    assert first == second and first.task.read_only and not first.task.materialized
    assert [item.artifact_type for item in first.artifacts] == [ArtifactType.BRIEF, ArtifactType.IMAGE_PROMPT, ArtifactType.GENERATED_IMAGE]
    assert all(item.read_only and not item.materialized for item in first.artifacts)
    assert first.artifacts[-1].generation_log_id == 7 and first.artifacts[-1].content_json is None
    assert row["status"] == "completed" and row["confirmed_text_json"] is None


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_legacy_projection_keeps_terminal_legacy_sessions_read_only(status):
    projection = project_legacy_session({"id": f"s-{status}", "user_id": "U1", "status": status})
    assert projection.task.status is DesignTaskStatus.CLOSED
