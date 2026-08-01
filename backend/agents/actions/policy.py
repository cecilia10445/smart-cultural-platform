"""Pure eligibility checks for explicit design commands."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.domain.agent_design_domain import (
    ActionType, ArtifactRecord, ArtifactStatus, ArtifactType, ConversationProjection,
    ConversationStatus, DesignTaskRecord, DesignTaskStatus,
)


@dataclass(frozen=True)
class ActionPolicyInput:
    user_id: str
    conversation: ConversationProjection
    active_task: DesignTaskRecord | None
    artifacts: tuple[ArtifactRecord, ...] = ()
    pending_actions: tuple[Any, ...] = ()
    requested_action_type: ActionType | None = None
    proposal_snapshot: dict[str, Any] | None = None
    source_runtime_run: dict[str, Any] | None = None


@dataclass(frozen=True)
class ActionPolicyDecision:
    allowed: bool
    code: str
    reason: str
    required_confirmation: bool = True
    required_artifact_types: tuple[ArtifactType, ...] = ()
    missing_requirements: tuple[str, ...] = ()
    available_assumptions: tuple[str, ...] = ()


def _deny(code: str, reason: str, *missing: str, required_artifact_types: tuple[ArtifactType, ...] = ()) -> ActionPolicyDecision:
    return ActionPolicyDecision(False, code, reason, required_artifact_types=required_artifact_types, missing_requirements=tuple(missing))


def _proposal_kind(snapshot: dict[str, Any] | None) -> str | None:
    value = (snapshot or {}).get("proposal_kind")
    return value if isinstance(value, str) else None


def _assumptions(snapshot: dict[str, Any] | None) -> tuple[str, ...]:
    values = (snapshot or {}).get("tentative_assumptions") or []
    return tuple(item for item in values if isinstance(item, str))[:20]


def _confirmed(artifacts: tuple[ArtifactRecord, ...], types: tuple[ArtifactType, ...] = ()) -> list[ArtifactRecord]:
    return [item for item in artifacts if item.status == ArtifactStatus.CONFIRMED and (not types or item.artifact_type in types)]


def evaluate_action(input: ActionPolicyInput) -> ActionPolicyDecision:
    action = input.requested_action_type
    if action is None:
        return _deny("ACTION_TYPE_REQUIRED", "Choose a design action first.")
    if input.conversation.conversation_status != ConversationStatus.ACTIVE:
        return _deny("CONVERSATION_ARCHIVED", "Restore this conversation before using design actions.")
    task = input.active_task
    if task is None:
        return _deny("ACTIVE_TASK_REQUIRED", "Create or select a design task before using this action.")
    if task.status == DesignTaskStatus.CLOSED:
        return _deny("TASK_CLOSED", "This design task is closed.")
    snapshot = input.proposal_snapshot or {}
    if action == ActionType.SAVE_BRIEF and _proposal_kind(snapshot) != "brief":
        return _deny("BRIEF_PROPOSAL_REQUIRED", "A valid Brief proposal is required.", "brief_proposal")
    if action == ActionType.SAVE_DESIGN_TEXT and _proposal_kind(snapshot) not in {"product_design_text", "design_text"}:
        return _deny("DESIGN_TEXT_PROPOSAL_REQUIRED", "A valid design-text proposal is required.", "design_text_proposal")
    if action == ActionType.APPLY_REVISION:
        ids = snapshot.get("base_artifact_ids") or []
        if not ids or not any(item.id in ids for item in _confirmed(input.artifacts)):
            return _deny("BASE_ARTIFACT_REQUIRED", "Choose a confirmed artifact to revise.", "confirmed_base_artifact")
    if action == ActionType.BUILD_VISUAL_DIRECTION and not snapshot and not input.artifacts:
        return _deny("DESIGN_CONTEXT_REQUIRED", "A proposal or saved design context is required.", "design_context")
    if action == ActionType.GENERATE_IMAGE_FROM_CONVERSATION:
        required = ("confirmed_constraints", "tentative_assumptions", "source_message_ids", "presentation_mode")
        missing = tuple(name for name in required if not snapshot.get(name))
        if missing:
            return _deny("GENERATION_SNAPSHOT_REQUIRED", "A reviewable image-generation snapshot is required.", *missing)
    if action == ActionType.GENERATE_IMAGE_FROM_ARTIFACT:
        selected = snapshot.get("selected_artifact_ids") or []
        if not selected or not any(item.id in selected for item in _confirmed(input.artifacts)):
            return _deny("CONFIRMED_ARTIFACT_REQUIRED", "Choose a confirmed artifact before generating an image.", "confirmed_artifact", required_artifact_types=(ArtifactType.BRIEF, ArtifactType.PRODUCT_DESIGN_TEXT, ArtifactType.VISUAL_DIRECTION, ArtifactType.IMAGE_PROMPT))
    if action == ActionType.REGENERATE_IMAGE:
        has_image = any(item.artifact_type == ArtifactType.GENERATED_IMAGE for item in input.artifacts)
        if not has_image and not snapshot.get("generation_log_id"):
            return _deny("IMAGE_SOURCE_REQUIRED", "Choose an earlier generated image before regenerating.", "generated_image")
    return ActionPolicyDecision(True, "ACTION_ALLOWED", "This action is ready for your explicit confirmation.", available_assumptions=_assumptions(snapshot))


def available_actions(conversation: ConversationProjection, active_task: DesignTaskRecord | None, artifacts: list[ArtifactRecord], pending_actions: list[Any] | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for action in ActionType:
        decision = evaluate_action(ActionPolicyInput(
            user_id=conversation.user_id, conversation=conversation, active_task=active_task,
            artifacts=tuple(artifacts), pending_actions=tuple(pending_actions or ()), requested_action_type=action,
            proposal_snapshot={},
        ))
        items.append({"action_type": action, "available": decision.allowed, "disabled_reason": None if decision.allowed else decision.reason,
                      "requires_confirmation": decision.required_confirmation, "requirements": list(decision.missing_requirements)})
    return items
