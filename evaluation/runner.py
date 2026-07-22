"""Offline-safe regression executor for AIGCService text generation only."""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


TARGET_TYPE = "aigc_text_generation_component"
MAX_REAL_CASES = 1
REQUIRED_CASE_KEYS = {
    "case_id", "category", "prompt", "style", "expected", "required_fields",
    "contains_keywords", "forbidden_keywords", "assertion_strength", "description",
}


class DatasetValidationError(ValueError):
    """Raised when a versioned evaluation dataset cannot be safely executed."""


@dataclass(frozen=True)
class ExecutorResponse:
    outcome: str
    title: str | None = None
    content: str | None = None
    error_code: str | None = None
    usage: dict[str, int | float] | None = None
    timeout_stage: str | None = None
    http_status: int | None = None


class Executor(Protocol):
    executor_type: str
    model_mode: str
    measurement_scope: str

    def execute(self, case: dict[str, Any]) -> ExecutorResponse:
        """Execute one text-component case without exposing provider internals."""


class StubExecutor:
    """Deterministic test-only executor; it never sends network requests."""

    executor_type = "stub"
    model_mode = "stub"
    measurement_scope = "harness_self_test"

    def execute(self, case: dict[str, Any]) -> ExecutorResponse:
        prompt = case["prompt"]
        if "青花" in prompt:
            return ExecutorResponse("success", "青花瓷书签", "青花纹样与留白构成国潮书签的文化表达。")
        if "丝路" in prompt:
            return ExecutorResponse("success", "丝路茶器", "丝路商旅与敦煌壁画色彩共同塑造茶器故事。")
        if "端午" in prompt or "传统节日" in prompt:
            return ExecutorResponse("success", "传统节日香囊", "传统节日的端午香囊连接祝福、草本香气与手作记忆。")
        if "敦煌" in prompt:
            return ExecutorResponse("success", "敦煌壁画茶器", "敦煌壁画的飞天纹样被转化为现代茶器装饰。")
        return ExecutorResponse("error", error_code="STUB_UNSUPPORTED_CASE")


class RealDashScopeExecutor:
    """Explicit opt-in text provider executor; it never estimates token usage or cost."""

    executor_type = "real"
    model_mode = "real_model"
    measurement_scope = "real_model_smoke"

    def __init__(self) -> None:
        from backend.services.aigc_service import AIGCService, AIGCServiceError
        self._service = AIGCService()
        if not self._service.api_key:
            raise RuntimeError("REAL_MODEL_NOT_CONFIGURED")
        self._provider_error = AIGCServiceError
        self.model_name = self._service.text_model

    def execute(self, case: dict[str, Any]) -> ExecutorResponse:
        try:
            title, content, usage = self._service.generate_text_content_with_metadata(case["prompt"], case["style"])
        except self._provider_error as error:
            return ExecutorResponse(
                "error",
                error_code=error.code,
                timeout_stage=error.timeout_stage,
                http_status=error.http_status,
            )
        return ExecutorResponse("success", title=title, content=content, usage=usage)


def load_dataset(path: str | Path) -> dict[str, Any]:
    try:
        dataset = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DatasetValidationError("DATASET_INVALID") from error
    if not isinstance(dataset, dict) or not isinstance(dataset.get("dataset_version"), str):
        raise DatasetValidationError("DATASET_VERSION_MISSING")
    if dataset.get("target_type") != TARGET_TYPE or dataset.get("data_origin") != "test":
        raise DatasetValidationError("DATASET_TARGET_ORIGIN_INVALID")
    if not isinstance(dataset.get("cases"), list):
        raise DatasetValidationError("DATASET_SCHEMA_INVALID")
    case_ids: set[str] = set()
    for case in dataset["cases"]:
        validate_case(case, case_ids)
    return dataset


def validate_case(case: Any, case_ids: set[str]) -> None:
    if not isinstance(case, dict) or not REQUIRED_CASE_KEYS.issubset(case):
        raise DatasetValidationError("CASE_REQUIRED_FIELDS_MISSING")
    case_id = case["case_id"]
    if not isinstance(case_id, str) or not case_id or case_id in case_ids:
        raise DatasetValidationError("CASE_ID_INVALID_OR_DUPLICATE")
    case_ids.add(case_id)
    for field in ("category", "prompt", "style", "description"):
        if not isinstance(case[field], str) or not case[field]:
            raise DatasetValidationError("CASE_METADATA_INVALID")
    expected = case["expected"]
    if not isinstance(expected, dict) or expected.get("outcome") not in {"success", "error"}:
        raise DatasetValidationError("CASE_EXPECTED_OUTCOME_INVALID")
    if "error_code" in expected and not isinstance(expected["error_code"], str):
        raise DatasetValidationError("CASE_ERROR_CODE_INVALID")
    for field in ("required_fields", "contains_keywords", "forbidden_keywords"):
        values = case[field]
        if not isinstance(values, list) or not all(isinstance(value, str) and value for value in values):
            raise DatasetValidationError("CASE_RULE_INVALID")
    if case["assertion_strength"] not in {"strict", "heuristic"}:
        raise DatasetValidationError("CASE_ASSERTION_STRENGTH_INVALID")


def percentile_nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def _assert_case(case: dict[str, Any], response: ExecutorResponse) -> list[str]:
    expected = case["expected"]
    reasons: list[str] = []
    if response.outcome != expected["outcome"]:
        reasons.append("OUTCOME_MISMATCH")
    if expected.get("error_code") and response.error_code != expected["error_code"]:
        reasons.append("ERROR_CODE_MISMATCH")
    values = {"title": response.title, "content": response.content, "error_code": response.error_code}
    for field in case["required_fields"]:
        if values.get(field) in (None, ""):
            reasons.append(f"MISSING_FIELD:{field}")
    response_text = " ".join(value or "" for value in (response.title, response.content)).lower()
    for keyword in case["contains_keywords"]:
        if keyword.lower() not in response_text:
            reasons.append(f"MISSING_KEYWORD:{keyword}")
    for keyword in case["forbidden_keywords"]:
        if keyword.lower() in response_text:
            reasons.append(f"FORBIDDEN_KEYWORD:{keyword}")
    return reasons


def run_evaluation(dataset: dict[str, Any], executor: Executor, cases: list[dict[str, Any]] | None = None, clock=time.perf_counter) -> dict[str, Any]:
    selected_cases = dataset["cases"] if cases is None else cases
    started_at = datetime.now(timezone.utc).isoformat()
    results: list[dict[str, Any]] = []
    latency_samples_ms: list[float] = []
    for case in selected_cases:
        start = clock()
        try:
            response = executor.execute(case)
            reasons = _assert_case(case, response)
            result = {
                "case_id": case["case_id"], "status": "passed" if not reasons else "failed",
                "outcome": response.outcome, "error_code": response.error_code, "reasons": reasons,
                "provider_usage": response.usage, "timeout_stage": response.timeout_stage,
                "http_status": response.http_status,
            }
        except TimeoutError:
            result = {"case_id": case["case_id"], "status": "error", "outcome": "error", "error_code": "EXECUTOR_TIMEOUT", "reasons": ["EXECUTOR_TIMEOUT"], "provider_usage": None, "timeout_stage": None, "http_status": None}
        except Exception:
            result = {"case_id": case["case_id"], "status": "error", "outcome": "error", "error_code": "EXECUTOR_ERROR", "reasons": ["EXECUTOR_ERROR"], "provider_usage": None, "timeout_stage": None, "http_status": None}
        result["latency_ms"] = round((clock() - start) * 1000, 3)
        latency_samples_ms.append(result["latency_ms"])
        results.append(result)
    counts = {name: sum(item["status"] == name for item in results) for name in ("passed", "failed", "error")}
    selection_rule = "all dataset cases" if cases is None else "first explicit max_real_cases cases"
    return {
        "dataset_version": dataset["dataset_version"],
        "target_type": TARGET_TYPE,
        "data_origin": "production_model" if executor.executor_type == "real" else "test",
        "executor_type": executor.executor_type,
        "model_mode": executor.model_mode,
        "measurement_scope": executor.measurement_scope,
        "model_name": getattr(executor, "model_name", None),
        "prompt_template_version": dataset.get("prompt_template_version"),
        "sample_size": len(selected_cases),
        "scope_description": "Only AIGCService.generate_text_content text generation is covered; this is not /api/generate, image generation, login, or persistence.",
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "dataset_case_count": len(dataset["cases"]),
        "selected_case_count": len(selected_cases),
        "selection_rule": selection_rule,
        **counts,
        "latency": {"unit": "milliseconds", "sample_count": len(latency_samples_ms), "percentile_method": "nearest-rank: ceil(p * n), one-indexed", "p50": percentile_nearest_rank(latency_samples_ms, 0.50), "p95": percentile_nearest_rank(latency_samples_ms, 0.95)},
        "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=Path(__file__).parent / "datasets" / "cultural_generation_v1.json")
    parser.add_argument("--report", required=True)
    parser.add_argument("--executor", choices=("stub", "real"), default="stub")
    parser.add_argument("--allow-real-model", action="store_true")
    parser.add_argument("--max-real-cases", type=int)
    args = parser.parse_args()
    if args.executor == "real" and not args.allow_real_model:
        parser.error("real execution requires --allow-real-model")
    if args.executor == "real" and args.max_real_cases != MAX_REAL_CASES:
        parser.error("real execution requires --max-real-cases 1")
    dataset = load_dataset(args.dataset)
    cases = dataset["cases"][:args.max_real_cases] if args.executor == "real" else None
    executor: Executor = StubExecutor() if args.executor == "stub" else RealDashScopeExecutor()
    report = run_evaluation(dataset, executor, cases=cases)
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["failed"] == report["error"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
