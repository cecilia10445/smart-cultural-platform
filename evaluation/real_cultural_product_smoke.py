"""One-case, explicit-opt-in real text smoke for the cultural-product contract."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from backend.domain.cultural_product_brief import validate_cultural_product_request
from backend.prompts.cultural_product_v1 import PROMPT_TEMPLATE_VERSION
from backend.services.aigc_service import AIGCService, AIGCServiceError


def run_smoke(case, service, clock=time.perf_counter):
    brief = validate_cultural_product_request(case["request"])
    started = clock()
    try:
        result, usage = service.generate_cultural_product_text_with_metadata(brief)
    except AIGCServiceError as error:
        return {
            "status": "failed", "stable_error_category": error.code,
            "http_status": error.http_status, "timeout_stage": error.timeout_stage,
            "provider_error_code": error.provider_error_code,
            "response_summary": error.response_summary, "latency_ms": round((clock() - started) * 1000, 3),
        }
    return {
        "status": "passed", "stable_error_category": None, "http_status": 200,
        "timeout_stage": None, "provider_error_code": None,
        "response_summary": getattr(service, "last_response_summary", None), "latency_ms": round((clock() - started) * 1000, 3),
        "schema_valid": all(isinstance(result.get(key), str) and result[key] for key in ("product_name", "design_interpretation", "product_copy")),
        "provider_usage": usage,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--executor", choices=("real",), required=True)
    parser.add_argument("--allow-real-model", action="store_true")
    parser.add_argument("--max-real-cases", type=int)
    args = parser.parse_args()
    if not args.allow_real_model or args.max_real_cases != 1:
        parser.error("real smoke requires --allow-real-model --max-real-cases 1")
    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    case = dataset["cases"][0]
    service = AIGCService()
    result = run_smoke(case, service)
    report = {
        "executor_type": "real", "data_origin": "production_model", "measurement_scope": "real_model_smoke",
        "sample_size": 1, "model_name": service.text_model, "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "case_id": case["case_id"], **result,
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["status"] == "passed" and result.get("schema_valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
