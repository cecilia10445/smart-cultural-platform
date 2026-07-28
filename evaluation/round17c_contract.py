"""Immutable, text-only contracts for the Round 17C rebuild."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ROUND17C_FINAL_SCHEMA_VERSION = "round17c-final-1.0"
FORBIDDEN_DELIVERY_MARKERS = (
    "标题：", "\"标题\"", "受众与场景：", "卖点：", "事实说明：",
    "来源纹样：", "现代转译：", "```", "|---",
)


class Round17CContractError(ValueError):
    """A stable failure for a controlled offline/real run boundary."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def text_skill_catalog(skills: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"skill_id": skill.skill_id, "kind": skill.kind, "version": skill.version, "description": skill.description}
        for skill in skills.values() if skill.kind == "text"
    ]


def _delivery_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Round17CContractError("OUTPUT_CONTRACT_INVALID")
    value = value.strip()
    if value.startswith(("{", "[")):
        raise Round17CContractError("OUTPUT_CONTRACT_INVALID")
    if any(marker in value for marker in FORBIDDEN_DELIVERY_MARKERS):
        raise Round17CContractError("OUTPUT_CONTRACT_INVALID")
    if re.search(r"\b(?:met|source)-[A-Za-z0-9_-]+\b", value, re.IGNORECASE):
        raise Round17CContractError("OUTPUT_CONTRACT_INVALID")
    return value


class Round17CFinalOutput(BaseModel):
    """The single business-delivery schema shared by baseline and guided arms."""

    model_config = ConfigDict(extra="forbid")

    product_copy: str = Field(min_length=20, max_length=1200)
    image_design_spec: str = Field(min_length=20, max_length=1600)
    used_source_ids: list[str] = Field(min_length=1, max_length=3)

    @field_validator("product_copy", "image_design_spec")
    @classmethod
    def delivery_is_plain_business_text(cls, value: str, info: Any) -> str:
        return _delivery_text(value, info.field_name)

    @field_validator("used_source_ids")
    @classmethod
    def source_ids_are_plain_nonempty(cls, value: list[str]) -> list[str]:
        if not value or any(not isinstance(item, str) or not item.strip() for item in value):
            raise Round17CContractError("OUTPUT_CONTRACT_INVALID")
        return value


class GuidedPlan(BaseModel):
    """Internal planner output; never rendered or sent to the final generator."""

    model_config = ConfigDict(extra="forbid")

    selected_text_skill_id: str = Field(min_length=1)


class JudgeDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: float = Field(ge=1, le=5)
    reason: str = Field(min_length=1, max_length=500)


class JudgeIndividualResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dimensions: dict[str, JudgeDimension]
    final_reason: str = Field(min_length=1, max_length=800)


class JudgePairwiseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    winner_index: int = Field(ge=0, le=1)
    winner_candidate_id: str
    final_reason: str = Field(min_length=1, max_length=800)


TECHNICAL_STATUSES = {"not_run", "blocked", "completed", "failed"}
EVALUATION_VALIDITIES = {
    "not_run", "comparable", "evaluation_inconclusive", "judge_parse_error",
    "judge_inconsistent", "inconclusive_position_bias",
}
INTEGRITY_STATUSES = {"pending", "verified", "failed"}


def validate_final_output(output: Round17CFinalOutput, frozen_evidence: dict[str, Any]) -> Round17CFinalOutput:
    source_ids = {item.get("source_id") for item in frozen_evidence.get("sources", []) if isinstance(item, dict)}
    if frozen_evidence.get("status") == "grounded" and not source_ids:
        raise Round17CContractError("GROUNDED_EVIDENCE_EMPTY")
    if not source_ids or not set(output.used_source_ids).issubset(source_ids):
        raise Round17CContractError("INVALID_CITATIONS")
    return output


def parse_judge_json(raw: str, expected: type[BaseModel]) -> BaseModel:
    try:
        decoded = json.loads(raw)
        return expected.model_validate(decoded)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise Round17CContractError("JUDGE_PARSE_ERROR") from error


def assess_pairwise_consistency(
    ab: JudgePairwiseResult,
    ba: JudgePairwiseResult,
    mapping: dict[str, dict[str, str]],
) -> tuple[str, str | None]:
    """Return validity plus a winner only when both randomized orders agree."""
    ab_winner = mapping["ab"].get(ab.winner_candidate_id)
    ba_winner = mapping["ba"].get(ba.winner_candidate_id)
    if not ab_winner or not ba_winner:
        return "judge_inconsistent", None
    if ab.winner_candidate_id == ba.winner_candidate_id:
        return "inconclusive_position_bias", None
    if ab_winner != ba_winner:
        return "evaluation_inconclusive", None
    return "comparable", ab_winner


@dataclass(frozen=True)
class RunCounters:
    qwen: int = 0
    deepseek: int = 0
    image: int = 0
    database_writes: int = 0
