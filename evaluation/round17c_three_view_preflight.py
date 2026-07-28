"""Zero-model preflight for the browser's three-view experimental Brief.

It validates exactly the intercepted browser JSON, freezes local evidence and
opens/rolls back the existing MySQL persistence boundary.  It deliberately
does not construct a Qwen client or call the generation service.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from backend.domain.cultural_product_brief import BriefValidationError, canonical_brief_json, validate_cultural_product_request
from backend.services.mysql_service import MySQLService
from evaluation.round17c_runner import freeze_evidence


def preflight(payload: dict, mysql_service: MySQLService | None = None) -> dict:
    brief = validate_cultural_product_request(payload)
    if brief["presentation_mode"] != "three_view":
        raise ValueError("PREFLIGHT_REQUIRES_THREE_VIEW")
    requirements = [brief[name] for name in ("front_design_requirements", "back_design_requirements", "side_design_requirements")]
    if not all(requirements) or len(set(requirements)) != 3:
        raise ValueError("PREFLIGHT_INVALID_THREE_VIEW_REQUIREMENTS")
    frozen = freeze_evidence(brief)
    if frozen.get("status") != "grounded" or not frozen.get("sources"):
        raise ValueError("PREFLIGHT_RAG_EVIDENCE_REQUIRED")
    storage = (mysql_service or MySQLService()).preflight_text_skill_generation_storage()
    if not storage:
        raise ValueError("PREFLIGHT_DATABASE_UNAVAILABLE")
    canonical = canonical_brief_json(brief).encode("utf-8")
    return {
        "status": "ready", "payload_sha256": hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
        "normalized_brief_sha256": hashlib.sha256(canonical).hexdigest(),
        "rag_status": frozen["status"], "source_ids": [source["source_id"] for source in frozen["sources"]],
        "database": storage, "model_calls": {"qwen": 0, "deepseek": 0, "image": 0},
    }


def main(argv: list[str] | None = None) -> int:
    arguments = argv or sys.argv[1:]
    if len(arguments) != 2:
        print("usage: python -m evaluation.round17c_three_view_preflight PAYLOAD_JSON OUTPUT_JSON", file=sys.stderr)
        return 2
    payload_path, output_path = map(Path, arguments)
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        result = preflight(payload)
    except (OSError, ValueError, BriefValidationError, json.JSONDecodeError) as error:
        print(f"three-view preflight failed: {getattr(error, 'code', type(error).__name__)}", file=sys.stderr)
        return 1
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "rag_status": result["rag_status"], "source_ids": result["source_ids"], "model_calls": result["model_calls"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
