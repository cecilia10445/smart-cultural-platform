"""Contracts for the additive nonlinear design-domain foundation."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from backend.domain.agent_dialogue import AgentDialogueError


class ConversationStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class DesignTaskStatus(str, Enum):
    EXPLORING = "exploring"
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"


class DesignTaskOrigin(str, Enum):
    NATIVE = "native"
    LEGACY_IMPORT = "legacy_import"


class ArtifactType(str, Enum):
    BRIEF = "brief"
    PRODUCT_DESIGN_TEXT = "product_design_text"
    VISUAL_DIRECTION = "visual_direction"
    IMAGE_PROMPT = "image_prompt"
    GENERATED_IMAGE = "generated_image"


class ArtifactStatus(str, Enum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"


class ArtifactOrigin(str, Enum):
    NATIVE = "native"
    LEGACY_PROJECTION = "legacy_projection"
    LEGACY_IMPORT = "legacy_import"


class ActionType(str, Enum):
    SAVE_BRIEF = "save_brief"
    SAVE_DESIGN_TEXT = "save_design_text"
    APPLY_REVISION = "apply_revision"
    BUILD_VISUAL_DIRECTION = "build_visual_direction"
    GENERATE_IMAGE_FROM_CONVERSATION = "generate_image_from_conversation"
    GENERATE_IMAGE_FROM_ARTIFACT = "generate_image_from_artifact"
    REGENERATE_IMAGE = "regenerate_image"
    ARCHIVE_TASK = "archive_task"


class ActionStatus(str, Enum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY_REQUESTED = "retry_requested"


TASK_TRANSITIONS = {
    DesignTaskStatus.EXPLORING: frozenset({DesignTaskStatus.ACTIVE, DesignTaskStatus.PAUSED, DesignTaskStatus.CLOSED}),
    DesignTaskStatus.ACTIVE: frozenset({DesignTaskStatus.PAUSED, DesignTaskStatus.CLOSED}),
    DesignTaskStatus.PAUSED: frozenset({DesignTaskStatus.EXPLORING, DesignTaskStatus.ACTIVE, DesignTaskStatus.CLOSED}),
    DesignTaskStatus.CLOSED: frozenset(),
}


class AgentDesignDomainError(AgentDialogueError):
    pass


class DesignTaskNotFound(AgentDesignDomainError):
    code = "AGENT_DESIGN_TASK_NOT_FOUND"; status_code = 404; message = "Design task was not found."


class DesignTaskVersionConflict(AgentDesignDomainError):
    code = "DESIGN_TASK_VERSION_CONFLICT"; status_code = 409; message = "Design task was changed by another request."


class DesignTaskScopeConflict(AgentDesignDomainError):
    code = "DESIGN_TASK_SCOPE_CONFLICT"; status_code = 409; message = "Design task does not belong to this conversation."


class DesignTaskTransitionConflict(AgentDesignDomainError):
    code = "INVALID_DESIGN_TASK_TRANSITION"; status_code = 409; message = "Requested design task transition is not allowed."


class ArtifactNotFound(AgentDesignDomainError):
    code = "AGENT_ARTIFACT_NOT_FOUND"; status_code = 404; message = "Design artifact was not found."


class ArtifactVersionConflict(AgentDesignDomainError):
    code = "ARTIFACT_VERSION_CONFLICT"; status_code = 409; message = "Artifact version already exists for this design task."


class ArtifactParentConflict(AgentDesignDomainError):
    code = "ARTIFACT_PARENT_CONFLICT"; status_code = 409; message = "Artifact parent must belong to the same task and type."


class ActionNotFound(AgentDesignDomainError):
    code = "AGENT_ACTION_NOT_FOUND"; status_code = 404; message = "Design action was not found."


class ActionIdempotencyConflict(AgentDesignDomainError):
    code = "ACTION_IDEMPOTENCY_CONFLICT"; status_code = 409; message = "Action idempotency key was reused with a different request."


class ActionReferenceConflict(AgentDesignDomainError):
    code = "ACTION_REFERENCE_CONFLICT"; status_code = 409; message = "Action references do not belong to this design task."


class ActionPolicyDenied(AgentDesignDomainError):
    code = "ACTION_POLICY_DENIED"; status_code = 409; message = "This design action is not currently available."


class ActionStateConflict(AgentDesignDomainError):
    code = "ACTION_STATE_CONFLICT"; status_code = 409; message = "Design action is no longer in the expected state."


class ActionApprovalIdempotencyConflict(AgentDesignDomainError):
    code = "ACTION_APPROVAL_IDEMPOTENCY_CONFLICT"; status_code = 409; message = "Approval idempotency key was reused with different confirmation details."


def assert_task_transition(source: DesignTaskStatus, target: DesignTaskStatus) -> None:
    if target not in TASK_TRANSITIONS[source]:
        raise DesignTaskTransitionConflict()


def canonical_json_hash(value: Mapping[str, Any] | list[Any] | None) -> str:
    raw = json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ConversationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str; user_id: str; conversation_status: ConversationStatus; active_task_id: str | None = None
    archived_at: datetime | None = None; version: int = Field(ge=1); created_at: datetime; updated_at: datetime


class ConversationProjection(ConversationRecord):
    legacy_session_status: str | None = None


class DesignTaskRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str; user_id: str; session_id: str; title: str = Field(min_length=1, max_length=255)
    status: DesignTaskStatus; origin: DesignTaskOrigin; version: int = Field(ge=1)
    client_task_id: str | None = None
    created_at: datetime; updated_at: datetime; paused_at: datetime | None = None; closed_at: datetime | None = None


class ArtifactRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str; user_id: str; session_id: str; task_id: str; artifact_type: ArtifactType; status: ArtifactStatus
    version_number: int = Field(ge=1); parent_artifact_id: str | None = None; source_runtime_run_id: str | None = None
    source_action_id: str | None = None; content_json: dict[str, Any]; content_hash: str = Field(min_length=64, max_length=64)
    generation_log_id: int | None = Field(default=None, ge=1); origin: ArtifactOrigin; created_at: datetime
    confirmed_at: datetime | None = None; superseded_at: datetime | None = None


class ActionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str; user_id: str; session_id: str; task_id: str; action_type: ActionType; status: ActionStatus
    idempotency_key: str = Field(min_length=1, max_length=128); request_hash: str = Field(min_length=64, max_length=64)
    expected_task_version: int | None = Field(default=None, ge=1); source_runtime_run_id: str | None = None
    source_artifact_ids_json: list[str] = Field(default_factory=list); proposal_snapshot_json: dict[str, Any] | None = None
    approval_snapshot_json: dict[str, Any] | None = None; result_json: dict[str, Any] | None = None
    error_code: str | None = None; error_summary: str | None = None; generation_log_id: int | None = Field(default=None, ge=1)
    retry_of_action_id: str | None = None; created_at: datetime; updated_at: datetime; approved_at: datetime | None = None; completed_at: datetime | None = None
    approval_idempotency_key: str | None = None; approval_hash: str | None = None
    rejection_idempotency_key: str | None = None; rejection_hash: str | None = None
    rejected_at: datetime | None = None; rejection_reason: str | None = None


class LegacyTaskProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str; session_id: str; user_id: str; title: str; status: DesignTaskStatus = DesignTaskStatus.CLOSED
    origin: ArtifactOrigin = ArtifactOrigin.LEGACY_PROJECTION; read_only: bool = True; materialized: bool = False


class LegacyArtifactProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str; session_id: str; task_id: str; artifact_type: ArtifactType; status: ArtifactStatus = ArtifactStatus.CONFIRMED
    origin: ArtifactOrigin = ArtifactOrigin.LEGACY_PROJECTION; content_json: dict[str, Any] | None = None
    generation_log_id: int | None = Field(default=None, ge=1); read_only: bool = True; materialized: bool = False


class LegacySessionProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task: LegacyTaskProjection; artifacts: list[LegacyArtifactProjection] = Field(default_factory=list)


class CreateDesignTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=255)
    initial_goal: str | None = Field(default=None, max_length=2000)
    client_task_id: str | None = Field(default=None, min_length=1, max_length=128)
    select: bool = False
    expected_session_version: int | None = Field(default=None, ge=1)


class SelectDesignTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_session_version: int | None = Field(default=None, ge=1)


class CreateActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_type: ActionType
    idempotency_key: str = Field(min_length=1, max_length=128)
    source_runtime_run_id: str = Field(min_length=1, max_length=36)
    source_proposal_digest: str = Field(min_length=64, max_length=64)
    expected_task_version: int | None = Field(default=None, ge=1)


class ApproveActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=128)
    expected_action_status: str = Field(default="requested", max_length=24)
    expected_task_version: int | None = Field(default=None, ge=1)
    approval_snapshot: dict[str, Any] | None = None


class RejectActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=128)
    reason: str | None = Field(default=None, max_length=1000)


def project_legacy_session(session: Mapping[str, Any]) -> LegacySessionProjection:
    session_id, user_id = str(session.get("id") or ""), str(session.get("user_id") or "")
    seed, task_id = f"legacy-session:{session_id}", _synthetic_id(f"legacy-session:{session_id}:task")
    task = LegacyTaskProjection(id=task_id, session_id=session_id, user_id=user_id, title="Legacy design session")
    artifacts = []
    for artifact_type, source in ((ArtifactType.BRIEF, "brief_json"), (ArtifactType.PRODUCT_DESIGN_TEXT, "confirmed_text_json"), (ArtifactType.IMAGE_PROMPT, "image_prompt_json")):
        content = _json_object(session.get(source))
        if content is not None:
            artifacts.append(LegacyArtifactProjection(id=_synthetic_id(f"{seed}:{source}"), session_id=session_id, task_id=task_id, artifact_type=artifact_type, content_json=content))
    log_id = session.get("generation_log_id")
    if isinstance(log_id, int) and log_id > 0:
        artifacts.append(LegacyArtifactProjection(id=_synthetic_id(f"{seed}:generation-log:{log_id}"), session_id=session_id, task_id=task_id, artifact_type=ArtifactType.GENERATED_IMAGE, generation_log_id=log_id))
    return LegacySessionProjection(task=task, artifacts=artifacts)


def _synthetic_id(value: str) -> str:
    return "legacy-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def _json_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict): return value
    if isinstance(value, str):
        try: value = json.loads(value)
        except ValueError: return None
    return value if isinstance(value, dict) else None
