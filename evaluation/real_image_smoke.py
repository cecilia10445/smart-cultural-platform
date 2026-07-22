"""One-image, explicit-opt-in wan2.6-t2i smoke with temporary local storage."""
from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

from backend.services.aigc_service import AIGCService, AIGCServiceError
from backend.services.image_storage import ImagePersistenceError, persist_generated_image

FIXED_TEST_PROMPT = "文创产品设计效果图：青花纹样纸质书签，靛青与瓷白，产品摄影，纯色背景。"


def run_smoke(service, persist=persist_generated_image, clock=time.perf_counter):
    started = clock()
    with tempfile.TemporaryDirectory(prefix="round13a-image-") as temporary_dir:
        try:
            provider_url = service.generate_image_from_prompt(FIXED_TEST_PROMPT)
        except AIGCServiceError as error:
            return {"status": "failed", "stage": "image_generation", "stable_error_category": error.code, "http_status": error.http_status, "provider_error_code": error.provider_error_code, "latency_ms": round((clock() - started) * 1000, 3), "temporary_files_cleaned": True}
        try:
            local_url = persist(provider_url, temporary_dir)
            files = list(Path(temporary_dir).iterdir())
            valid_file = len(files) == 1 and files[0].is_file() and files[0].stat().st_size > 0 and files[0].stat().st_size <= 8 * 1024 * 1024
            return {"status": "passed" if valid_file else "failed", "stage": "image_generation", "stable_error_category": None if valid_file else "IMAGE_PERSIST_FAILED", "http_status": 200, "provider_error_code": None, "image_count": 1 if valid_file else 0, "image_signature_valid": valid_file, "latency_ms": round((clock() - started) * 1000, 3), "temporary_files_cleaned": True}
        except ImagePersistenceError:
            return {"status": "failed", "stage": "image_download", "stable_error_category": "IMAGE_PERSIST_FAILED", "http_status": None, "provider_error_code": None, "latency_ms": round((clock() - started) * 1000, 3), "temporary_files_cleaned": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executor", choices=("real",), required=True)
    parser.add_argument("--allow-real-model", action="store_true")
    parser.add_argument("--max-real-cases", type=int)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    if not args.allow_real_model or args.max_real_cases != 1:
        parser.error("real smoke requires --allow-real-model --max-real-cases 1")
    service = AIGCService()
    report = {"executor_type": "real", "data_origin": "production_model", "measurement_scope": "real_model_smoke", "sample_size": 1, "model_name": service.image_model, "size": service.image_size, **run_smoke(service)}
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
