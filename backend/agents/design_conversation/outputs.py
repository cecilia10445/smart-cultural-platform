"""Structured outputs deliberately separate planning from business state changes."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator
from backend.domain.agent_design_domain import ActionType


class DirectAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["direct_answer"] = "direct_answer"
    answer: str = Field(min_length=1, max_length=2000)
    answer_kind: Literal[
        "general_answer", "cultural_research", "design_explanation",
        "design_comparison", "design_critique",
    ] = "general_answer"
    sections: list["AnswerSection"] = Field(default_factory=list, max_length=6)


class AnswerSection(BaseModel):
    """Short, user-visible structure for analysis without turning it into an artifact."""

    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=1000)


class AskUser(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["ask_user"] = "ask_user"
    question: str = Field(min_length=1, max_length=1000)
    missing_fields: list[str] = Field(default_factory=list)
    reason_summary: str = Field(min_length=1, max_length=1000)
    continuation_actions: list["AskUserContinuationAction"] = Field(default_factory=list)


class AskUserContinuationAction(BaseModel):
    """A user-visible, safe way to continue without unsupported citations."""

    model_config = ConfigDict(extra="forbid")
    id: Literal["continue_creative_only"] = "continue_creative_only"
    label: str = Field(default="继续按纯创意方向设计", min_length=1, max_length=80)


class ProposeBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["propose_brief"] = "propose_brief"
    brief: dict
    summary: str = Field(min_length=1, max_length=2000)
    assumptions: list[str] = Field(default_factory=list)
    evidence_source_ids: list[str] = Field(default_factory=list)
    used_skill_ids: list[str] = Field(default_factory=list)
    used_memory_ids: list[str] = Field(default_factory=list)


class ProposeDesignRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["propose_design_revision"] = "propose_design_revision"
    changes: list[str] = Field(min_length=1)
    summary: str = Field(min_length=1, max_length=2000)
    preserved_constraints: list[str] = Field(default_factory=list)


class RequestBusinessAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["request_business_action"] = "request_business_action"
    action: Literal["confirm_brief", "regenerate_product_text", "confirm_product_text", "confirm_image_generation"]
    reason_summary: str = Field(min_length=1, max_length=1000)


DesignConversationVariant = Annotated[
    Union[DirectAnswer, AskUser, ProposeBrief, ProposeDesignRevision, RequestBusinessAction],
    Field(discriminator="kind"),
]


class DesignConversationOutput(BaseModel):
    """Object-shaped Pydantic AI output containing a discriminated union."""

    model_config = ConfigDict(extra="forbid")
    result: DesignConversationVariant


# The variants above remain the compatibility shape for rows persisted by the
# earlier Runtime rounds. New provider turns use only Conversation Reply V2.
ConversationIntent = Literal[
    "exploration", "clarification", "general_answer", "cultural_research",
    "design_explanation", "design_comparison", "design_critique",
    "brief_proposal", "design_revision", "business_action_request",
]
RagStatus = Literal["matched", "creative_only", "needs_clarification"]


class ConversationSuggestion(BaseModel):
    """A model-authored option that may fill, but never submit, the composer."""

    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=120)
    draft_text: str | None = Field(default=None, max_length=1000)


class ArtifactProposal(BaseModel):
    """An unsaved design attachment, never a business-state transition."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["brief", "design_revision"]
    content: dict[str, Any] = Field(default_factory=dict)
    summary: str = Field(min_length=1, max_length=2000)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    evidence_source_ids: list[str] = Field(default_factory=list, max_length=20)
    used_skill_ids: list[str] = Field(default_factory=list, max_length=20)
    preserved_constraints: list[str] = Field(default_factory=list, max_length=20)
    saved: Literal[False] = False
    valid: Literal[True] = True


class BusinessActionRequest(BaseModel):
    """A request for explicit human confirmation; it does not execute itself."""

    model_config = ConfigDict(extra="forbid")
    # Legacy Runtime values remain readable.  New explicit commands reuse the
    # domain ActionType rather than inventing a second action vocabulary.
    action: ActionType | Literal["confirm_brief", "regenerate_product_text", "confirm_product_text", "confirm_image_generation"]
    reason_summary: str = Field(min_length=1, max_length=1000)


class ConversationReply(BaseModel):
    """The sole primary user-facing result for new assistant turns."""

    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=4000)
    intent: ConversationIntent = "general_answer"
    suggestions: list[ConversationSuggestion] = Field(default_factory=list, max_length=4)
    rag_status: RagStatus | None = None
    artifact_proposal: ArtifactProposal | None = None
    business_action: BusinessActionRequest | None = None
    output_origin: Literal["provider", "provider_repair", "system_fallback", "legacy_projection"] = "provider"

    @model_validator(mode="after")
    def _attachments_match_explicit_intent(self):
        expected_artifact = {"brief_proposal": "brief", "design_revision": "design_revision"}.get(self.intent)
        if expected_artifact is None and self.artifact_proposal is not None:
            raise ValueError("artifact_proposal is only allowed for an artifact intent")
        if expected_artifact is not None:
            if self.artifact_proposal is None:
                raise ValueError("artifact_proposal is required for an artifact intent")
            if self.artifact_proposal.kind != expected_artifact:
                raise ValueError("artifact kind must match intent")
        if (self.intent == "business_action_request") != (self.business_action is not None):
            raise ValueError("business_action must exactly match business_action_request intent")
        if _looks_like_protocol_echo(self.message, self.artifact_proposal):
            raise ValueError("user-visible reply contains internal output-repair protocol text")
        return self


class ProviderBriefPayloadV2(BaseModel):
    """Minimum useful content for an unsaved Brief attachment."""

    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=2, max_length=120)
    product_type: str = Field(min_length=1, max_length=120)
    design_goal: str = Field(min_length=8, max_length=1000)
    concept: str = Field(min_length=16, max_length=2000)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    confirmed_constraints: list[str] = Field(default_factory=list, max_length=20)
    tentative_fields: list[str] = Field(default_factory=list, max_length=20)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=20)


class ProviderDesignRevisionPayloadV2(BaseModel):
    """Minimum useful content for an unsaved design-revision attachment."""

    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=2, max_length=120)
    change_summary: str = Field(min_length=8, max_length=1000)
    changes: list[str] = Field(min_length=1, max_length=20)
    affected_constraints: list[str] = Field(default_factory=list, max_length=20)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=20)


class ProviderBriefArtifactV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_type: Literal["brief"] = "brief"
    summary: str = Field(min_length=8, max_length=2000)
    brief: ProviderBriefPayloadV2
    evidence_source_ids: list[str] = Field(default_factory=list, max_length=20)
    used_skill_ids: list[str] = Field(default_factory=list, max_length=20)
    preserved_constraints: list[str] = Field(default_factory=list, max_length=20)


class ProviderDesignRevisionArtifactV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_type: Literal["design_revision"] = "design_revision"
    summary: str = Field(min_length=8, max_length=2000)
    revision: ProviderDesignRevisionPayloadV2
    evidence_source_ids: list[str] = Field(default_factory=list, max_length=20)
    used_skill_ids: list[str] = Field(default_factory=list, max_length=20)
    preserved_constraints: list[str] = Field(default_factory=list, max_length=20)


ProviderArtifactV2 = Annotated[
    Union[ProviderBriefArtifactV2, ProviderDesignRevisionArtifactV2],
    Field(discriminator="artifact_type"),
]


class ProviderBusinessActionV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: ActionType | Literal["confirm_brief", "regenerate_product_text", "confirm_product_text", "confirm_image_generation"]
    reason_summary: str = Field(min_length=1, max_length=1000)


class ProviderConversationReplyV2(BaseModel):
    """The only provider-facing contract for new Conversation Output V2 turns.

    This model intentionally does not accept historical ``kind``/``payload``
    envelopes. Full intent/attachment and user-visible semantic checks happen
    after adaptation in :class:`ConversationReply` for normal and repair paths.
    """

    model_config = ConfigDict(extra="forbid")
    contract_version: Literal["conversation_reply_v2"] = "conversation_reply_v2"
    message: str = Field(min_length=1, max_length=4000)
    intent: ConversationIntent = "general_answer"
    suggestions: list[ConversationSuggestion] = Field(default_factory=list, max_length=4)
    rag_status: RagStatus | None = None
    artifact: ProviderArtifactV2 | None = None
    business_action: ProviderBusinessActionV2 | None = None


def adapt_provider_reply_v2(value: ProviderConversationReplyV2 | dict[str, Any]) -> dict[str, Any]:
    raw = value.model_dump(mode="json") if isinstance(value, BaseModel) else dict(value)
    artifact = None
    if raw.get("artifact") is not None:
        provider_artifact = dict(raw["artifact"])
        artifact_type = provider_artifact["artifact_type"]
        content = provider_artifact["brief"] if artifact_type == "brief" else provider_artifact["revision"]
        artifact = {
            "kind": artifact_type, "content": content,
            "summary": provider_artifact["summary"],
            "assumptions": content.get("assumptions", []),
            "evidence_source_ids": provider_artifact.get("evidence_source_ids", []),
            "used_skill_ids": provider_artifact.get("used_skill_ids", []),
            "preserved_constraints": provider_artifact.get("preserved_constraints", []),
            "saved": False, "valid": True,
        }
    return {
        "message": raw["message"], "intent": raw["intent"], "suggestions": raw.get("suggestions") or [],
        "rag_status": raw.get("rag_status"), "artifact_proposal": artifact,
        "business_action": raw.get("business_action"), "output_origin": "provider",
    }


def _looks_like_protocol_echo(message: str, artifact: ArtifactProposal | None) -> bool:
    """Block narrow repair-protocol echoes, without treating normal topic text as unsafe.

    The rule requires a protocol marker plus no independent design attachment;
    valid artifact payloads still undergo their own typed validation.
    """
    normalized = " ".join(message.lower().split())
    markers = (
        "previous output was invalid", "corrected json envelope", "corrected compact json envelope",
        "output repair", "return only json", "schema validation", "validation error",
        "kind / payload envelope", "kind/payload envelope",
    )
    if not any(marker in normalized for marker in markers):
        return False
    if artifact is None:
        return True
    # A typed artifact must contain actual design content; protocol-only text in
    # either user-visible surface is never a valid attachment.
    return True
