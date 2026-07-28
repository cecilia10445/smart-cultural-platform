"""Experimental, text-only business entry point for the audited Round 17C Agent.

This is deliberately separate from the existing V2 image workflow. A caller
may persist a completed text result through the existing ``generation_logs``
service before its artifact is sealed; it never calls an image model or
DeepSeek.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from backend.agents.skill_registry import SKILLS
from evaluation.round17c_contract import Round17CContractError, sha256_json
from evaluation.round17c_runner import (
    InstrumentedTransport,
    build_dashscope_client,
    build_model,
    freeze_evidence,
    run_guided_final,
    run_guided_plan,
    sanitized_model_error,
    seal_run,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BUSINESS_ARTIFACT_ROOT = PROJECT_ROOT / "evaluation" / "artifacts" / "round-17c-business"


class BusinessGenerationError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise BusinessGenerationError("ARTIFACT_IMMUTABLE")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _run_id() -> str:
    git_short = "unknown"
    head = PROJECT_ROOT / ".git"
    if head.exists():
        try:
            import subprocess
            git_short = subprocess.check_output(["git", "rev-parse", "--short=7", "HEAD"], cwd=PROJECT_ROOT, text=True).strip()
        except Exception:  # report remains useful even without git metadata
            pass
    return f"round-17c-business-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{git_short}"


def _report_html(report: dict[str, Any]) -> str:
    output = report["output"]
    source_ids = ", ".join(report["source_ids"])
    return """<!doctype html><meta charset=\"utf-8\"><title>Round 17C business generation</title>
<main><h1>Round 17C 实验性业务生成报告</h1>
<p>展示已经完整性校验的真实业务生成轨迹、文化证据与文本 Skill 调用记录。</p>
<dl><dt>Run ID</dt><dd>{run}</dd><dt>RAG</dt><dd>{rag}</dd><dt>Text Skill</dt><dd>{skill}</dd><dt>Qwen 请求</dt><dd>{calls}</dd><dt>业务记录</dt><dd>{record}</dd></dl>
<h2>产品文案</h2><p>{copy}</p><h2>文字版设计说明</h2><p>{spec}</p><h2>来源</h2><p>{sources}</p></main>""".format(
        run=html.escape(report["run_id"]), rag=html.escape(report["rag_status"]),
        skill=html.escape(report["selected_skill_id"]), calls=report["actual_calls"]["qwen"], record=html.escape(str(report.get("business_record_id", "未写入"))),
        copy=html.escape(output["product_copy"]), spec=html.escape(output["image_design_spec"]),
        sources=html.escape(source_ids),
    )


def generate_with_text_skill(
    brief: dict[str, Any], *, api_key: str | None, model_name: str, base_url: str,
    artifact_root: Path = BUSINESS_ARTIFACT_ROOT,
    persist_completed_generation: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Run the proven two-request text-only Agent flow and seal its report."""
    if not api_key:
        raise BusinessGenerationError("TEXT_SKILL_MODEL_UNAVAILABLE")
    run_id, started = _run_id(), _utc_now()
    total_started = time.perf_counter()
    run_dir = artifact_root / run_id
    if run_dir.exists():
        raise BusinessGenerationError("RUN_ID_COLLISION")
    run_dir.mkdir(parents=True)
    wire: dict[str, Any] = {"requests": 0, "attempts": [], "stage": "planner"}
    manifest: dict[str, Any] = {
        "run_id": run_id, "started_at": started, "finished_at": None,
        "technical_status": "failed", "integrity_status": "pending", "failure_stage": None,
        "stable_error": None, "model": {"name": model_name, "base_url": base_url},
        "actual_calls": {"qwen": 0, "deepseek": 0, "image": 0, "database_writes": 0},
        "retries": 0, "experimental": True,
    }
    try:
        _atomic_json(run_dir / "brief.json", brief)
        frozen = freeze_evidence(brief)
        _atomic_json(run_dir / "frozen-evidence.json", frozen)
        if frozen.get("status") != "grounded" or not frozen.get("sources"):
            raise BusinessGenerationError("RAG_EVIDENCE_REQUIRED")
        client = build_dashscope_client(api_key=api_key, base_url=base_url, counter=wire, trust_env=False)
        model = build_model(model_name=model_name, openai_client=client)
        started_planner = time.perf_counter()
        wire["stage"] = "planner"
        deps, receipt, planner_metrics = run_guided_plan(model, brief, frozen)
        planner_metrics["latency_ms"] = round((time.perf_counter() - started_planner) * 1000, 3)
        _atomic_json(run_dir / "planner.json", {
            "receipt": receipt, "selected_skill_id": deps.loaded_skill_id,
            "skill_body_sha256": deps.loaded_skill_sha256, "catalog_sha256": deps.catalog_sha256,
            "tool_trajectory": deps.trajectory, "metrics": planner_metrics,
        })
        wire["stage"] = "final"
        final, final_metrics = run_guided_final(model, brief, frozen, deps)
        if wire["requests"] > 2:
            raise BusinessGenerationError("QWEN_BUDGET_EXCEEDED")
        _atomic_json(run_dir / "qwen-request-events.json", wire["attempts"])
        source_ids = [item["source_id"] for item in frozen["sources"]]
        report = {
            "run_id": run_id, "created_at": started, "status": "completed", "rag_status": frozen["status"],
            "source_ids": source_ids, "selected_skill_id": deps.loaded_skill_id,
            "skill_version": SKILLS[deps.loaded_skill_id].version, "skill_body_sha256": deps.loaded_skill_sha256,
            "tool_trajectory": deps.trajectory, "planner_latency_ms": planner_metrics["latency_ms"],
            "final_latency_ms": final_metrics["latency_ms"], "actual_calls": {"qwen": wire["requests"], "deepseek": 0, "image": 0, "database_writes": 0},
            "model_name": model_name, "output": final.model_dump(),
        }
        _atomic_json(run_dir / "final-output.json", final.model_dump())
        if persist_completed_generation is not None:
            persistence = persist_completed_generation(report)
            if not isinstance(persistence, dict) or not isinstance(persistence.get("log_id"), int):
                raise BusinessGenerationError("GENERATION_PERSIST_FAILED")
            report["business_record_id"] = persistence["log_id"]
            report["database_transaction_status"] = persistence.get("transaction_status", "committed")
            report["actual_calls"]["database_writes"] = persistence.get("database_writes", 0)
        _atomic_json(run_dir / "normalized-report.json", report)
        (run_dir / "report.html").write_text(_report_html(report), encoding="utf-8")
        manifest.update({"finished_at": _utc_now(), "technical_status": "completed", "integrity_status": "verified", "actual_calls": report["actual_calls"], "brief_sha256": sha256_json(brief), "evidence_sha256": sha256_json(frozen)})
        _atomic_json(run_dir / "manifest.json", manifest)
        seal_run(run_dir)
        return {"status": "success", "experimental_text_skill": True, "run_id": run_id, "generation_time": round(time.perf_counter() - total_started, 3), **final.model_dump(), "sources": frozen["sources"], "selected_skill_id": deps.loaded_skill_id, "business_record_id": report.get("business_record_id"), "database_writes": report["actual_calls"]["database_writes"]}
    except Exception as error:
        manifest["finished_at"] = _utc_now()
        manifest["actual_calls"]["qwen"] = wire.get("requests", 0)
        manifest["failure_stage"] = wire.get("stage")
        manifest["stable_error"] = getattr(error, "code", None) or (str(error) if isinstance(error, BusinessGenerationError) else "TEXT_SKILL_GENERATION_FAILED")
        try:
            _atomic_json(run_dir / "qwen-request-events.json", wire.get("attempts", []))
            _atomic_json(run_dir / "model-error.json", sanitized_model_error(error, stage=wire.get("stage", "unknown"), model_name=model_name, request_ordinal=wire.get("requests", 0), request_shape_hash=(wire.get("attempts") or [{}])[-1].get("request_shape_sha256")))
            _atomic_json(run_dir / "manifest.json", manifest)
            seal_run(run_dir)
        except Exception:
            pass
        if isinstance(error, BusinessGenerationError):
            raise
        if isinstance(error, Round17CContractError):
            raise BusinessGenerationError(error.code) from error
        raise BusinessGenerationError("TEXT_SKILL_GENERATION_FAILED") from error
