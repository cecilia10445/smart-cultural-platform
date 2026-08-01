"""Read-only domain tools; they are registered through the generic Runtime registry."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.agents.runtime import RuntimeContext, ToolRegistry, ToolRisk, ToolSpec
from backend.agents.skill_registry import SKILLS, SkillAssetError, load_skill
from backend.domain.cultural_product_brief import validate_cultural_product_request

from .definition import ALLOWED_STATUSES


class InspectDesignStateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    include_summaries: bool = True


class InspectDesignStateOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    status: str
    revision_count: int = Field(ge=0)
    brief_summary: str | None = None
    product_design_summary: str | None = None
    visual_direction_summary: str | None = None
    unresolved_fields: list[str] = Field(default_factory=list)


class SearchCulturalKnowledgeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=3, ge=1, le=3)


class KnowledgeSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    title: str
    evidence_summary: str


class SearchCulturalKnowledgeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["matched", "creative_only", "needs_clarification"]
    reason: str
    sources: list[KnowledgeSource] = Field(default_factory=list)


class LoadDesignSkillInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skill_id: str = Field(min_length=1, max_length=100)


class LoadDesignSkillOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skill_id: str
    kind: str
    version: str
    description: str
    instructions: str


class ValidateDesignConstraintsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_brief: dict[str, Any]
    user_constraints: list[str] = Field(default_factory=list)
    evidence_source_ids: list[str] = Field(default_factory=list)
    skill_ids: list[str] = Field(default_factory=list)


class ValidateDesignConstraintsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    requires_user_confirmation: bool = True


def _state_bucket(context: RuntimeContext) -> dict[str, Any]:
    bucket = context.services.get("design_runtime_state")
    if not isinstance(bucket, dict):
        raise RuntimeError("DESIGN_CAPABILITY_UNAVAILABLE")
    return bucket


def inspect_design_state(context: RuntimeContext, value: InspectDesignStateInput) -> InspectDesignStateOutput:
    reader = context.services.get("design_state_reader")
    if not callable(reader):
        raise RuntimeError("DESIGN_CAPABILITY_UNAVAILABLE")
    state = reader(context.user_id, context.session_id)
    if not isinstance(state, dict):
        raise RuntimeError("DESIGN_STATE_INVALID")
    return InspectDesignStateOutput(
        session_id=context.session_id, status=str(state.get("status", context.session_status)),
        revision_count=int(state.get("text_revision_count", state.get("revision_count", 0)) or 0),
        brief_summary=state.get("brief_summary") if value.include_summaries else None,
        product_design_summary=state.get("product_design_summary") if value.include_summaries else None,
        visual_direction_summary=state.get("visual_direction_summary") if value.include_summaries else None,
        unresolved_fields=[str(item) for item in state.get("unresolved_fields", [])][:12],
    )


def search_cultural_knowledge(context: RuntimeContext, value: SearchCulturalKnowledgeInput) -> SearchCulturalKnowledgeOutput:
    rag = context.services.get("cultural_rag")
    if rag is None:
        return SearchCulturalKnowledgeOutput(status="creative_only", reason="knowledge_unavailable", sources=[])
    try:
        decision = rag.decide_query(value.query, value.top_k)
        sources = [KnowledgeSource(source_id=item.source_id, title=item.title,
                                   evidence_summary="; ".join(f"{key}: {val}" for key, val in item.evidence.items())[:600])
                   for item in decision.results]
        _state_bucket(context).setdefault("retrieved_source_ids", set()).update(source.source_id for source in sources)
        if decision.status == "matched":
            return SearchCulturalKnowledgeOutput(status="matched", reason=decision.reason, sources=sources)
        # A low score or competing RAG matches limit evidence; they do not make
        # an otherwise understandable design request ambiguous.
        if _is_genuinely_ambiguous_query(value.query):
            return SearchCulturalKnowledgeOutput(status="needs_clarification", reason="request_ambiguous", sources=[])
        return SearchCulturalKnowledgeOutput(status="creative_only", reason="no_reliable_cultural_match", sources=[])
    except Exception:
        return SearchCulturalKnowledgeOutput(status="creative_only", reason="knowledge_unavailable", sources=[])


def load_design_skill(context: RuntimeContext, value: LoadDesignSkillInput) -> LoadDesignSkillOutput:
    skill = SKILLS.get(value.skill_id)
    if skill is None:
        raise RuntimeError("UNKNOWN_SKILL")
    try:
        instructions = load_skill(value.skill_id)
    except SkillAssetError as error:
        raise RuntimeError("SKILL_UNAVAILABLE") from error
    _state_bucket(context).setdefault("loaded_skill_ids", set()).add(skill.skill_id)
    return LoadDesignSkillOutput(skill_id=skill.skill_id, kind=skill.kind, version=skill.version,
                                 description=skill.description, instructions=instructions)


def validate_design_constraints(context: RuntimeContext, value: ValidateDesignConstraintsInput) -> ValidateDesignConstraintsOutput:
    """Validate a formal artifact candidate, never a normal conversation reply."""
    errors, warnings, missing = [], ["image_generation_requires_human_confirmation"], []
    try:
        normalized = validate_cultural_product_request({"brief_version": "1.0", "brief": value.candidate_brief})
        if normalized.get("presentation_mode") == "single_hero" and any(normalized.get(field) for field in ("back_design_requirements", "side_design_requirements")):
            warnings.append("single_hero_ignores_secondary_view_requirements")
    except Exception:
        errors.append("BRIEF_INVALID")
        for field in ("product_type", "presentation_mode", "cultural_source", "visual_direction"):
            if not value.candidate_brief.get(field):
                missing.append(field)
    bucket = _state_bucket(context)
    known_sources = bucket.get("retrieved_source_ids", set())
    known_skills = bucket.get("loaded_skill_ids", set())
    if not set(value.evidence_source_ids).issubset(known_sources):
        errors.append("UNKNOWN_EVIDENCE_SOURCE")
    if not set(value.skill_ids).issubset(known_skills):
        errors.append("SKILL_NOT_LOADED")
    constraints_text = " ".join(str(item) for item in value.candidate_brief.values())
    if any(item and item not in constraints_text for item in value.user_constraints):
        errors.append("USER_CONSTRAINT_NOT_PRESERVED")
    return ValidateDesignConstraintsOutput(valid=not errors, errors=errors, warnings=warnings,
                                           missing_fields=missing, requires_user_confirmation=True)


def _is_genuinely_ambiguous_query(value: str) -> bool:
    """Only label an input ambiguous when it has no usable subject at all."""
    compact = "".join(value.split()).lower()
    return not compact or compact in {"文化", "文创", "资料", "查资料", "查一下", "帮我查", "这个", "那个", "相关"}


def build_design_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    common = frozenset({"design_conversation"})
    registry.register_many([
        ToolSpec("inspect_design_state", "Read an allow-list projection of the current design session.", InspectDesignStateInput, InspectDesignStateOutput, inspect_design_state, ToolRisk.READ_ONLY, common, ALLOWED_STATUSES, 3, 2),
        ToolSpec("search_cultural_knowledge", "Search the approved cultural knowledge corpus once. matched permits only returned source IDs as cultural evidence. creative_only means no reliable source is available: say so and continue ordinary design as a creative interpretation without citations. needs_clarification is reserved for a genuinely ambiguous request, never a failed search. Do not refine or retry the same query.", SearchCulturalKnowledgeInput, SearchCulturalKnowledgeOutput, search_cultural_knowledge, ToolRisk.READ_ONLY, common, ALLOWED_STATUSES, 5, 2),
        ToolSpec("load_design_skill", "Load one versioned design guidance skill.", LoadDesignSkillInput, LoadDesignSkillOutput, load_design_skill, ToolRisk.READ_ONLY, common, ALLOWED_STATUSES, 3, 2),
        ToolSpec("validate_design_constraints", "Validate a candidate only before requesting a formal business action such as saving or applying an artifact. It is not required for ordinary discussion, research, critique, comparison, or a tentative ProposeBrief. Pass only source IDs returned by search and skill IDs returned by load.", ValidateDesignConstraintsInput, ValidateDesignConstraintsOutput, validate_design_constraints, ToolRisk.READ_ONLY, common, ALLOWED_STATUSES, 3, 1),
    ])
    return registry
