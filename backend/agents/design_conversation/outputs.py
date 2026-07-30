"""Structured outputs deliberately separate planning from business state changes."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class DirectAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["direct_answer"] = "direct_answer"
    answer: str = Field(min_length=1, max_length=2000)


class AskUser(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["ask_user"] = "ask_user"
    question: str = Field(min_length=1, max_length=1000)
    missing_fields: list[str] = Field(default_factory=list)
    reason_summary: str = Field(min_length=1, max_length=1000)


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
