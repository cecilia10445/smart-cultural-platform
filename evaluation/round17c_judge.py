"""Deterministic audit processing for Promptfoo's real Judge artifacts.

This module never calls a provider. It validates raw strings written by
Promptfoo and produces explicit inconclusive states rather than defaults.
"""

from __future__ import annotations

import json
from typing import Any

from evaluation.round17c_contract import JudgeIndividualResult, JudgePairwiseResult, Round17CContractError, assess_pairwise_consistency, parse_judge_json


DIMENSIONS = (
    "professional_readability", "product_title_recognition", "brief_fit", "cultural_specificity",
    "design_executability", "factual_fidelity", "delivery_format", "conciseness_non_repetition",
)


def opaque_candidate_mapping() -> dict[str, dict[str, str]]:
    return {
        "ab": {"candidate_0": "baseline", "candidate_1": "skill_guided"},
        "ba": {"candidate_0": "skill_guided", "candidate_1": "baseline"},
    }


def parse_individual(raw: str) -> dict[str, Any]:
    try:
        parsed = parse_judge_json(raw, JudgeIndividualResult)
    except Round17CContractError:
        return {"status": "judge_parse_error", "raw": raw, "score": None}
    if set(parsed.dimensions) != set(DIMENSIONS):
        return {"status": "judge_parse_error", "raw": raw, "score": None}
    score = round(sum(item.score for item in parsed.dimensions.values()) / len(DIMENSIONS), 3)
    return {"status": "success", "raw": raw, "dimensions": parsed.model_dump()["dimensions"], "score": score, "scale": 5, "final_reason": parsed.final_reason}


def parse_pairwise(raw: str) -> dict[str, Any]:
    try:
        parsed = parse_judge_json(raw, JudgePairwiseResult)
    except Round17CContractError:
        return {"status": "judge_parse_error", "raw": raw}
    if parsed.winner_candidate_id not in {"candidate_0", "candidate_1"}:
        return {"status": "judge_inconsistent", "raw": raw}
    if parsed.winner_candidate_id != f"candidate_{parsed.winner_index}":
        return {"status": "judge_inconsistent", "raw": raw}
    reason = parsed.final_reason.lower()
    winner_id = parsed.winner_candidate_id.lower()
    loser_id = f"candidate_{1 - parsed.winner_index}"
    if winner_id not in reason or loser_id in reason:
        return {"status": "judge_inconsistent", "raw": raw}
    return {"status": "success", "raw": raw, **parsed.model_dump()}


def normalize_judge_results(individual_baseline: str, individual_guided: str, ab: str, ba: str) -> dict[str, Any]:
    individual = {"baseline": parse_individual(individual_baseline), "skill_guided": parse_individual(individual_guided)}
    pairwise = {"ab": parse_pairwise(ab), "ba": parse_pairwise(ba)}
    statuses = [result["status"] for result in individual.values()] + [result["status"] for result in pairwise.values()]
    if "judge_inconsistent" in statuses:
        return {"evaluation_validity": "judge_inconsistent", "winner": None, "individual": individual, "pairwise": pairwise, "reason": "judge_inconsistent"}
    if any(status != "success" for status in statuses):
        return {"evaluation_validity": "judge_parse_error", "winner": None, "individual": individual, "pairwise": pairwise, "reason": "judge_parse_error"}
    mapping = opaque_candidate_mapping()
    ab_result = JudgePairwiseResult.model_validate({
        key: pairwise["ab"][key] for key in ("winner_index", "winner_candidate_id", "final_reason")
    })
    ba_result = JudgePairwiseResult.model_validate({
        key: pairwise["ba"][key] for key in ("winner_index", "winner_candidate_id", "final_reason")
    })
    validity, winner = assess_pairwise_consistency(
        ab_result, ba_result, mapping,
    )
    return {"evaluation_validity": validity, "winner": winner, "individual": individual, "pairwise": pairwise, "candidate_mapping": mapping}


def extract_promptfoo_jobs(payload: dict[str, Any]) -> dict[str, str]:
    """Extract exactly four raw target outputs from a Promptfoo result artifact."""
    container = payload.get("results") if isinstance(payload, dict) else None
    rows = container.get("results") if isinstance(container, dict) else None
    if not isinstance(rows, list):
        raise Round17CContractError("PROMPTFOO_ARTIFACT_INVALID")
    values: dict[str, str] = {}
    for row in rows:
        metadata = row.get("metadata") if isinstance(row, dict) else None
        response = row.get("response") if isinstance(row, dict) else None
        job = metadata.get("round17c_judge_job") if isinstance(metadata, dict) else None
        raw = response.get("output") if isinstance(response, dict) else None
        if not isinstance(job, str) or not isinstance(raw, str) or job in values:
            raise Round17CContractError("PROMPTFOO_ARTIFACT_INVALID")
        values[job] = raw
    expected = {"individual-baseline", "individual-guided", "pairwise-ab", "pairwise-ba"}
    if set(values) != expected:
        raise Round17CContractError("PROMPTFOO_JOB_COUNT_INVALID")
    return values
