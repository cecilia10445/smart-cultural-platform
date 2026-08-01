"""Domain contracts for the collaborative cultural-design dialogue MVP.

This module deliberately contains no model/provider integration.  It defines
the controlled state machine and the API projection boundary used by round one.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from enum import Enum
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field


SCHEMA_VERSION = "agent-session-detail-v1"


class AgentSessionStatus(str, Enum):
    CREATED = "created"
    EXTRACTING_BRIEF = "extracting_brief"
    WAITING_BRIEF_CONFIRMATION = "waiting_brief_confirmation"
    GENERATING_PRODUCT_TEXT = "generating_product_text"
    WAITING_TEXT_FEEDBACK = "waiting_text_feedback"
    BUILDING_VISUAL_PROMPT = "building_visual_prompt"
    WAITING_IMAGE_CONFIRMATION = "waiting_image_confirmation"
    GENERATING_IMAGE = "generating_image"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentMessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class AgentStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


ALLOWED_TRANSITIONS: dict[AgentSessionStatus, set[AgentSessionStatus]] = {
    AgentSessionStatus.CREATED: {AgentSessionStatus.EXTRACTING_BRIEF, AgentSessionStatus.FAILED},
    AgentSessionStatus.EXTRACTING_BRIEF: {AgentSessionStatus.WAITING_BRIEF_CONFIRMATION, AgentSessionStatus.FAILED},
    AgentSessionStatus.WAITING_BRIEF_CONFIRMATION: {AgentSessionStatus.EXTRACTING_BRIEF, AgentSessionStatus.GENERATING_PRODUCT_TEXT, AgentSessionStatus.FAILED},
    AgentSessionStatus.GENERATING_PRODUCT_TEXT: {AgentSessionStatus.WAITING_TEXT_FEEDBACK, AgentSessionStatus.FAILED},
    AgentSessionStatus.WAITING_TEXT_FEEDBACK: {AgentSessionStatus.GENERATING_PRODUCT_TEXT, AgentSessionStatus.BUILDING_VISUAL_PROMPT, AgentSessionStatus.FAILED},
    AgentSessionStatus.BUILDING_VISUAL_PROMPT: {AgentSessionStatus.WAITING_IMAGE_CONFIRMATION, AgentSessionStatus.FAILED},
    AgentSessionStatus.WAITING_IMAGE_CONFIRMATION: {AgentSessionStatus.GENERATING_IMAGE, AgentSessionStatus.FAILED},
    AgentSessionStatus.GENERATING_IMAGE: {AgentSessionStatus.COMPLETED, AgentSessionStatus.FAILED},
    AgentSessionStatus.COMPLETED: set(),
    AgentSessionStatus.FAILED: set(),
}


class AgentDialogueError(RuntimeError):
    code = "AGENT_DIALOGUE_ERROR"
    status_code = 500
    retryable = False

    def __init__(self, message: str | None = None):
        self.message = message or self.code
        super().__init__(self.message)


class AgentSessionNotFound(AgentDialogueError):
    code = "AGENT_SESSION_NOT_FOUND"
    status_code = 404
    message = "Agent session was not found."


class AgentSessionStateConflict(AgentDialogueError):
    code = "SESSION_STATE_CONFLICT"
    status_code = 409
    message = "Agent session is not in the expected state."


class AgentSessionVersionConflict(AgentDialogueError):
    code = "SESSION_VERSION_CONFLICT"
    status_code = 409
    message = "Agent session was changed by another request."

class RuntimeTurnIdempotencyConflict(AgentDialogueError):
    code = "RUNTIME_TURN_IDEMPOTENCY_CONFLICT"
    status_code = 409
    message = "Client turn id was reused for another design task."


class AgentInvalidTransition(AgentDialogueError):
    code = "INVALID_SESSION_TRANSITION"
    status_code = 409
    message = "Requested session transition is not allowed."


class AgentDecisionNotSupported(AgentDialogueError):
    code = "AGENT_DECISION_NOT_SUPPORTED"
    status_code = 409
    message = "Agent decisions are not available in this implementation round."


class AgentPersistenceUnavailable(AgentDialogueError):
    code = "AGENT_PERSISTENCE_UNAVAILABLE"
    status_code = 503
    retryable = True
    message = "Agent session data service is temporarily unavailable."


class BriefOutputInvalid(AgentDialogueError):
    code = "BRIEF_OUTPUT_INVALID"
    status_code = 422
    message = "The brief proposal could not be validated."


class AgentModelUnavailable(AgentDialogueError):
    code = "MODEL_UNAVAILABLE"
    status_code = 503
    retryable = True
    message = "Brief generation service is temporarily unavailable."


class AgentModelTimeout(AgentDialogueError):
    code = "MODEL_TIMEOUT"
    status_code = 503
    retryable = True
    message = "Brief generation service did not respond in time."


class ProductTextModelUnavailable(AgentDialogueError):
    code = "PRODUCT_TEXT_MODEL_UNAVAILABLE"
    status_code = 503
    retryable = True
    message = "Product design text service is temporarily unavailable."


class ProductTextModelTimeout(AgentDialogueError):
    code = "PRODUCT_TEXT_MODEL_TIMEOUT"
    status_code = 503
    retryable = True
    message = "Product design text service did not respond in time."


class ProductTextOutputInvalid(AgentDialogueError):
    code = "PRODUCT_TEXT_OUTPUT_INVALID"
    status_code = 422
    message = "The product design text could not be validated."


class AgentImageGenerationFailed(AgentDialogueError):
    code = "AGENT_IMAGE_GENERATION_FAILED"
    status_code = 502
    retryable = True
    message = "The final product image could not be generated."


class AgentImagePersistenceFailed(AgentDialogueError):
    code = "AGENT_IMAGE_PERSISTENCE_FAILED"
    status_code = 503
    retryable = False
    message = "The generated image is awaiting a recoverable persistence step."


class TextRevisionLimitReached(AgentDialogueError):
    code = "TEXT_REVISION_LIMIT_REACHED"
    status_code = 409
    message = "The product design text has reached the four-revision limit."


class CreateAgentSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_request_id: str | None = Field(default=None, min_length=1, max_length=128)


class AppendAgentMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_turn_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=4000)
    expected_status: AgentSessionStatus | None = None
    expected_version: int | None = Field(default=None, ge=1)


class AssistantTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=4000)
    client_turn_id: str = Field(min_length=1, max_length=128)
    task_id: str | None = Field(default=None, min_length=1, max_length=36)


class AgentDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(min_length=1, max_length=128)
    decision: str = Field(min_length=1, max_length=64)
    expected_status: AgentSessionStatus
    expected_version: int | None = Field(default=None, ge=1)


class BriefUnderstanding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cultural_theme: str
    product_type: str
    use_case: str
    style: str
    form_and_material: str
    presentation_mode: str
    design_constraints: list[str] = Field(default_factory=list)


class BriefProposal(BaseModel):
    """Structured, user-visible-safe result of the restricted Brief stage."""

    model_config = ConfigDict(extra="forbid")

    normalized_brief: dict[str, Any]
    understanding: BriefUnderstanding
    assumptions: list[str] = Field(default_factory=list)
    user_facing_summary: str = Field(min_length=1, max_length=2000)


class ProductDesignDraft(BaseModel):
    """Validated internal result for the product-text stage.

    This is deliberately separate from the legacy fast-generation response.
    It only contains user-visible design material and compact evidence metadata.
    """

    model_config = ConfigDict(extra="forbid")

    product_name: str = Field(min_length=1, max_length=2000)
    design_concept: str = Field(min_length=1, max_length=2000)
    cultural_translation: str = Field(min_length=1, max_length=2000)
    structure: str = Field(min_length=1, max_length=2000)
    materials: str = Field(min_length=1, max_length=2000)
    color_plan: str = Field(min_length=1, max_length=1000)
    usage_scene: str = Field(min_length=1, max_length=1000)
    selling_points: list[str] = Field(min_length=1, max_length=5)
    creative_origin: str = Field(min_length=1, max_length=2000)
    factual_background: str = Field(min_length=1, max_length=2000)
    evidence_status: Literal["grounded", "insufficient_evidence", "creative_only"]
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    used_source_ids: list[str] = Field(default_factory=list)
    selected_text_skill: str | None = None
    revision_summary: str | None = Field(default=None, max_length=1000)


class ImagePromptPackage(BaseModel):
    """Validated, internal-only image instruction package for an Agent session."""

    model_config = ConfigDict(extra="forbid")

    positive_prompt: str = Field(min_length=1, max_length=6000)
    negative_prompt: str = Field(min_length=1, max_length=3000)
    required_constraints: list[str] = Field(default_factory=list)
    product_form: str = Field(min_length=1, max_length=2000)
    materials: str = Field(min_length=1, max_length=2000)
    color_plan: str = Field(min_length=1, max_length=1000)
    composition: str = Field(min_length=1, max_length=1000)
    scene: str = Field(min_length=1, max_length=1000)
    avoid: list[str] = Field(default_factory=list)
    presentation_mode: str = Field(min_length=1, max_length=64)
    selected_visual_skill: str | None = None
    evidence_source_ids: list[str] = Field(default_factory=list)
    user_facing_direction: str = Field(min_length=1, max_length=2000)


class AgentMessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    sequence_no: int = Field(ge=1)
    role: AgentMessageRole
    message_type: str
    text: str
    created_at: str
    client_turn_id: str | None = None
    structured_output: dict[str, Any] | None = None


class AgentStepErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str | None = None
    retryable: bool = False
    stage: str | None = None


class AgentStepResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    ordinal: int = Field(ge=1)
    stage: str
    status: str
    summary: str
    tool: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error: AgentStepErrorResponse | None = None


class BriefSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cultural_theme: str | None = None
    product_type: str | None = None
    use_case: str | None = None
    style: str | None = None
    design_constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class ProductDesignResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_name: str | None = None
    design_concept: str | None = None
    cultural_translation: str | None = None
    structure: str | None = None
    materials: str | None = None
    color_plan: str | None = None
    usage_scene: str | None = None
    selling_points: list[str] = Field(default_factory=list)
    creative_origin: str | None = None
    factual_background: str | None = None
    evidence_status: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    used_source_ids: list[str] = Field(default_factory=list)
    selected_text_skill: str | None = None
    revision_summary: str | None = None


class VisualDirectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str | None = None
    selected_visual_skill: str | None = None
    positive_prompt_summary: str | None = None
    negative_constraints: list[str] = Field(default_factory=list)
    presentation_mode: str | None = None
    product_form: str | None = None
    materials: str | None = None
    color_plan: str | None = None
    composition: str | None = None
    scene: str | None = None
    avoid: list[str] = Field(default_factory=list)


class FinalResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generation_log_id: int | None = None
    product_name: str | None = None
    image_url: str | None = None
    generation_time: float | None = None
    evidence_status: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    selected_text_skill: str | None = None
    selected_visual_skill: str | None = None


class AgentErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str | None = None
    retryable: bool = False
    stage: str | None = None


class AgentSessionDetailResponse(BaseModel):
    """Stable, owner-scoped DTO.  Its shape never varies by state."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    session_id: str
    status: AgentSessionStatus
    current_stage: AgentSessionStatus
    revision_count: int = Field(ge=0, le=4)
    generation_log_id: int | None = None
    brief_summary: BriefSummaryResponse | None = None
    product_design: ProductDesignResponse | None = None
    visual_direction: VisualDirectionResponse | None = None
    final_result: FinalResultResponse | None = None
    messages: list[AgentMessageResponse] = Field(default_factory=list)
    steps: list[AgentStepResponse] = Field(default_factory=list)
    error: AgentErrorResponse | None = None
    created_at: str
    updated_at: str


class AgentSessionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["success"] = "success"
    request_id: str
    data: AgentSessionDetailResponse


class AgentSessionListItemResponse(BaseModel):
    """Compact owner-scoped list projection for the text workspace."""
    model_config = ConfigDict(extra="forbid")

    session_id: str
    title: str
    status: AgentSessionStatus
    updated_at: str
    has_pending_action: bool = False


class AgentSessionListEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["success"] = "success"
    request_id: str
    data: list[AgentSessionListItemResponse]


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, (str, bytes)):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _text_list(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _object_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _iso(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value if isinstance(value, str) else ""


def _status(value: Any) -> AgentSessionStatus:
    try:
        return AgentSessionStatus(value)
    except (TypeError, ValueError):
        return AgentSessionStatus.CREATED


def _brief_projection(value: Any) -> BriefSummaryResponse | None:
    raw = _json_object(value)
    if not raw:
        return None
    understanding = _json_object(raw.get("understanding"))
    if understanding:
        raw = {**raw, **understanding, "assumptions": raw.get("assumptions", [])}
    return BriefSummaryResponse(
        cultural_theme=_text(raw.get("cultural_theme") or raw.get("cultural_source")),
        product_type=_text(raw.get("product_type")),
        use_case=_text(raw.get("use_case")),
        style=_text(raw.get("style")),
        design_constraints=_text_list(raw.get("design_constraints")),
        assumptions=_text_list(raw.get("assumptions")),
    )


def project_agent_session_list_item(session_row: Mapping[str, Any]) -> AgentSessionListItemResponse:
    brief = _brief_projection(session_row.get("brief_json"))
    status = _status(session_row.get("status"))
    title = _session_title(_text(session_row.get("first_user_text"))) or (brief.product_type if brief and brief.product_type else None) or "文创设计对话"
    return AgentSessionListItemResponse(
        session_id=str(session_row.get("id", "")), title=title[:80], status=status,
        updated_at=_iso(session_row.get("updated_at")),
        has_pending_action=status in {
            AgentSessionStatus.WAITING_BRIEF_CONFIRMATION,
            AgentSessionStatus.WAITING_TEXT_FEEDBACK,
            AgentSessionStatus.WAITING_IMAGE_CONFIRMATION,
        },
    )


def _session_title(value: str | None) -> str | None:
    if not value:
        return None
    import re
    text = re.sub(r"\s+", " ", value).strip(" ，。；、：:！!？?\n\t")
    if not text:
        return None
    sentence = re.split(r"[。！？!?\n]", text, maxsplit=1)[0].strip()
    # Remove common polite lead-ins so the visible title starts with the idea.
    sentence = re.sub(r"^(我想|请|帮我|想要|设计一款|做一款|帮忙做一款)", "", sentence).strip()
    if len(sentence) > 22:
        sentence = sentence[:21].rstrip(" ，。；、：:") + "…"
    return sentence or "文创设计对话"


def _design_projection(value: Any) -> ProductDesignResponse | None:
    raw = _json_object(value)
    if not raw:
        return None
    return ProductDesignResponse(
        product_name=_text(raw.get("product_name")),
        design_concept=_text(raw.get("design_concept")),
        cultural_translation=_text(raw.get("cultural_translation")),
        structure=_text(raw.get("structure")),
        materials=_text(raw.get("materials")),
        color_plan=_text(raw.get("color_plan")),
        usage_scene=_text(raw.get("usage_scene")),
        selling_points=_text_list(raw.get("selling_points")),
        creative_origin=_text(raw.get("creative_origin")),
        factual_background=_text(raw.get("factual_background")),
        evidence_status=_text(raw.get("evidence_status")),
        evidence=_object_list(raw.get("evidence")),
        used_source_ids=_text_list(raw.get("used_source_ids")),
        selected_text_skill=_text(raw.get("selected_text_skill")),
        revision_summary=_text(raw.get("revision_summary")),
    )


def _visual_projection(value: Any) -> VisualDirectionResponse | None:
    raw = _json_object(value)
    if not raw:
        return None
    return VisualDirectionResponse(
        summary=_text(raw.get("summary")) or _text(raw.get("user_facing_direction")),
        selected_visual_skill=_text(raw.get("selected_visual_skill")),
        positive_prompt_summary=_text(raw.get("positive_prompt_summary")) or _text(raw.get("product_form")),
        negative_constraints=_text_list(raw.get("negative_constraints") or raw.get("required_constraints")),
        presentation_mode=_text(raw.get("presentation_mode")),
        product_form=_text(raw.get("product_form")),
        materials=_text(raw.get("materials")),
        color_plan=_text(raw.get("color_plan")),
        composition=_text(raw.get("composition")),
        scene=_text(raw.get("scene")),
        avoid=_text_list(raw.get("avoid")),
    )


def _error_projection(value: Any, error_code: Any, failure_stage: Any) -> AgentErrorResponse | None:
    raw = _json_object(value)
    code = _text(raw.get("code")) or _text(error_code)
    if not code:
        return None
    return AgentErrorResponse(
        code=code,
        message=_text(raw.get("message")),
        retryable=raw.get("retryable") is True,
        stage=_text(raw.get("stage")) or _text(failure_stage),
    )


def _final_projection(value: Any, generation_log_id: int | None) -> FinalResultResponse | None:
    raw = _json_object(value)
    result = _json_object(raw.get("final_result"))
    if not result and generation_log_id is None:
        return None
    return FinalResultResponse(
        generation_log_id=generation_log_id,
        product_name=_text(result.get("product_name")),
        image_url=_text(result.get("image_url")),
        generation_time=(float(result["generation_time"]) if isinstance(result.get("generation_time"), (int, float)) else None),
        evidence_status=_text(result.get("evidence_status")),
        citations=_object_list(result.get("citations")),
        selected_text_skill=_text(result.get("selected_text_skill")),
        selected_visual_skill=_text(result.get("selected_visual_skill")),
    )


def _runtime_conversation_projection(value: Any) -> dict[str, Any] | None:
    """Project both current natural replies and persisted legacy variants.

    Runtime rows are append-only facts.  This presentation adapter makes older
    ``result.kind`` payloads readable without rewriting them in MySQL.
    """
    raw = _json_object(value)
    if isinstance(raw.get("message"), str) and raw["message"].strip():
        return raw
    result = _json_object(raw.get("result"))
    kind = _text(result.get("kind"))
    if not kind:
        return None
    if kind == "direct_answer":
        return {"message": _text(result.get("answer")) or "设计助手已回复。",
                "intent": _text(result.get("answer_kind")) or "general_answer", "suggestions": [],
                "artifact_proposal": None, "business_action": None, "output_origin": "legacy_projection"}
    if kind == "ask_user":
        actions = _object_list(result.get("continuation_actions"))
        return {"message": _text(result.get("question")) or _text(result.get("reason_summary")) or "请补充后继续。",
                "intent": "clarification",
                "suggestions": [{"label": _text(item.get("label")) or "继续讨论", "draft_text": None} for item in actions],
                "artifact_proposal": None, "business_action": None, "output_origin": "legacy_projection"}
    if kind == "propose_brief":
        return {"message": _text(result.get("summary")) or "我已整理一版初步设计方案。", "intent": "brief_proposal", "suggestions": [],
                "artifact_proposal": {"kind": "brief", "content": _json_object(result.get("brief")),
                                      "summary": _text(result.get("summary")) or "初步设计方案", "assumptions": _text_list(result.get("assumptions")),
                                      "evidence_source_ids": _text_list(result.get("evidence_source_ids")),
                                      "used_skill_ids": _text_list(result.get("used_skill_ids")), "preserved_constraints": [], "saved": False, "valid": True},
                "business_action": None, "output_origin": "legacy_projection"}
    if kind == "propose_design_revision":
        return {"message": _text(result.get("summary")) or "我已整理修订建议。", "intent": "design_revision", "suggestions": [],
                "artifact_proposal": {"kind": "design_revision", "content": {"changes": _text_list(result.get("changes"))},
                                      "summary": _text(result.get("summary")) or "设计修订建议", "assumptions": [],
                                      "evidence_source_ids": [], "used_skill_ids": [],
                                      "preserved_constraints": _text_list(result.get("preserved_constraints")), "saved": False, "valid": True},
                "business_action": None, "output_origin": "legacy_projection"}
    if kind == "request_business_action":
        return {"message": _text(result.get("reason_summary")) or "这项操作需要你的确认。", "intent": "business_action_request", "suggestions": [],
                "artifact_proposal": None,
                "business_action": {"action": _text(result.get("action")), "reason_summary": _text(result.get("reason_summary"))},
                "output_origin": "legacy_projection"}
    return None


def project_agent_session_detail(
    session_row: Mapping[str, Any],
    message_rows: list[Mapping[str, Any]] | None = None,
    step_rows: list[Mapping[str, Any]] | None = None,
) -> AgentSessionDetailResponse:
    """Allow-list database rows into the stable public response model."""
    messages = [
        AgentMessageResponse(
            id=str(row.get("id", "")), sequence_no=max(int(row.get("sequence_no") or 1), 1),
            role=AgentMessageRole(row.get("role") if row.get("role") in {item.value for item in AgentMessageRole} else "system"),
            message_type=_text(row.get("message_type")) or "system", text=_text(row.get("content_text")) or "",
            created_at=_iso(row.get("created_at")),
            client_turn_id=_text(row.get("client_turn_id")),
            structured_output=(_runtime_conversation_projection(_json_object(row.get("content_json")).get("output"))
                               if row.get("message_type") == "runtime_result" else None),
        )
        for row in (message_rows or [])
    ]
    steps: list[AgentStepResponse] = []
    for row in step_rows or []:
        raw_error = _error_projection(row.get("error_json"), row.get("error_code"), row.get("stage"))
        output = _json_object(row.get("output_summary_json"))
        result = _json_object(row.get("tool_result_summary_json"))
        steps.append(AgentStepResponse(
            id=str(row.get("id", "")), ordinal=max(int(row.get("ordinal") or 1), 1),
            stage=_text(row.get("stage")) or "unknown", status=_text(row.get("status")) or "unknown",
            summary=_text(output.get("summary")) or _text(result.get("summary")) or "",
            tool=_text(row.get("tool_name")), started_at=_iso(row.get("started_at")) or None,
            finished_at=_iso(row.get("finished_at")) or None,
            error=raw_error.model_dump() if raw_error is not None else None,
        ))
    generation_log_id = session_row.get("generation_log_id")
    try:
        generation_log_id = int(generation_log_id) if generation_log_id is not None else None
    except (TypeError, ValueError):
        generation_log_id = None
    return AgentSessionDetailResponse(
        session_id=str(session_row.get("id", "")), status=_status(session_row.get("status")),
        current_stage=_status(session_row.get("current_stage")),
        revision_count=min(max(int(session_row.get("text_revision_count") or 0), 0), 4),
        generation_log_id=generation_log_id, brief_summary=_brief_projection(session_row.get("brief_json")),
        product_design=_design_projection(session_row.get("confirmed_text_json")),
        visual_direction=_visual_projection(session_row.get("image_prompt_json")),
        final_result=_final_projection(session_row.get("context_summary_json"), generation_log_id),
        messages=messages, steps=steps,
        error=_error_projection(session_row.get("error_json"), session_row.get("error_code"), session_row.get("failure_stage")),
        created_at=_iso(session_row.get("created_at")), updated_at=_iso(session_row.get("updated_at")),
    )
