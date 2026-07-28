"""Network-free Promptfoo target used to prove the four-job Judge contract."""

from __future__ import annotations

import json
from typing import Any

DIMENSIONS = (
    "professional_readability", "product_title_recognition", "brief_fit", "cultural_specificity",
    "design_executability", "factual_fidelity", "delivery_format", "conciseness_non_repetition",
)


def call_api(_prompt: str, options: dict[str, Any], _context: dict[str, Any]) -> dict[str, Any]:
    config = options.get("config", {}) if isinstance(options, dict) else {}
    job = config.get("job")
    if job in {"individual-baseline", "individual-guided"}:
        raw = {"dimensions": {key: {"score": 4, "reason": "offline fixture"} for key in DIMENSIONS}, "final_reason": "offline fixture"}
    elif job == "pairwise-ab":
        raw = {"winner_index": 0, "winner_candidate_id": "candidate_0", "final_reason": "candidate_0 is the selected fixture winner"}
    elif job == "pairwise-ba":
        raw = {"winner_index": 1, "winner_candidate_id": "candidate_1", "final_reason": "candidate_1 is the selected fixture winner"}
    else:
        return {"output": "", "error": "ROUND17C_FAKE_JUDGE_JOB_INVALID", "metadata": {"network": "disabled"}}
    return {"output": json.dumps(raw, ensure_ascii=False), "metadata": {"round17c_judge_job": job, "network": "disabled", "provider_calls": 1}}
