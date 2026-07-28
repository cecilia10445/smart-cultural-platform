"""Explicit, authorization-gated Round 17C real-run orchestrator.

Importing this module never constructs a provider. `--real` plus the dedicated
environment authorization flag are both required before any client is made.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from evaluation.round17c_contract import Round17CContractError, canonical_json, sha256_json
from evaluation.round17c_runner import BRIEF_PAYLOAD, ROOT, build_dashscope_client, build_model, create_blocked_run, freeze_evidence, run_baseline, run_guided, seal_run
from evaluation.round17c_orchestrator import execute_round17c


QWEN_BUDGET = {"baseline": 1, "guided_planner": 3, "guided_final": 1, "total": 5}
DEEPSEEK_BUDGET = 4
STAGES = ("authorization", "configuration", "freeze_evidence", "baseline", "guided_planner", "guided_final", "generation_seal", "judge_individual_baseline", "judge_individual_guided", "judge_ab", "judge_ba", "judge_normalization", "report", "evaluation_seal")
GENERATION_INVENTORY = ["manifest.json", "effective-config.json", "brief.json", "frozen-evidence.json", "baseline-result.json", "guided-result.json", "judge-inputs.json", "stage-status.json"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git(args: list[str], default: str = "unknown") -> str:
    try:
        return subprocess.check_output(args, text=True, cwd=Path(__file__).parents[1]).strip()
    except (OSError, subprocess.SubprocessError):
        return default


def _write(path: Path, value: Any) -> None:
    if path.exists():
        raise Round17CContractError("SEALED_RUN_IMMUTABLE")
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def secret_presence(name: str) -> dict[str, bool]:
    return {"present": bool(os.environ.get(name)), "value_recorded": False}


def authorized(real_flag: bool) -> bool:
    return real_flag and os.environ.get("ROUND17C_REAL_RUN_AUTHORIZED") == "1"


def resolve_config() -> dict[str, str]:
    """Resolve only non-secret settings; DeepSeek endpoint has no guessed default."""
    from backend.config import load_settings
    settings = load_settings()
    qwen_model = os.environ.get("ROUND17C_QWEN_MODEL") or settings.dashscope_text_model
    qwen_base_url = os.environ.get("ROUND17C_QWEN_BASE_URL") or settings.dashscope_openai_base_url
    deepseek_model = os.environ.get("ROUND17C_DEEPSEEK_MODEL") or "deepseek-v4-pro"
    deepseek_base_url = os.environ.get("ROUND17C_DEEPSEEK_BASE_URL")
    if not qwen_model or not qwen_base_url:
        raise Round17CContractError("ROUND17C_CONFIGURATION_REQUIRED")
    if not deepseek_base_url:
        raise Round17CContractError("ROUND17C_DEEPSEEK_CONFIGURATION_REQUIRED")
    return {"qwen_model": qwen_model, "qwen_base_url": qwen_base_url, "deepseek_model": deepseek_model, "deepseek_base_url": deepseek_base_url}


def effective_config(run_id: str, *, qwen_model: str, qwen_base_url: str, deepseek_model: str, deepseek_base_url: str) -> dict[str, Any]:
    return {
        "run_id": run_id, "utc": utc_now(), "timezone": "UTC", "git_sha": _git(["git", "rev-parse", "HEAD"]),
        "dirty": bool(_git(["git", "status", "--porcelain"], "")), "dirty_patch_sha256": hashlib.sha256(_git(["git", "diff", "--binary"], "").encode()).hexdigest(),
        "runner_version": "round17c-real-1", "python": sys.version.split()[0], "os": platform.platform(), "architecture": platform.machine(),
        "qwen": {"provider": "dashscope-chat-completions", "model": qwen_model, "base_url": qwen_base_url},
        "deepseek": {"provider": "promptfoo-openai-compatible", "model": deepseek_model, "base_url": deepseek_base_url},
        "generation": {"temperature": 0, "max_tokens": 1800, "reasoning": "none", "response_format": {"type": "json_object"}, "tool_choice": "auto", "parallel_tool_calls": False, "retries": 0},
        "timeouts_seconds": {"connect": 10, "read": 90, "write": 30, "pool": 10}, "budgets": {"qwen": QWEN_BUDGET, "deepseek": DEEPSEEK_BUDGET, "image": 0, "database_writes": 0},
        "secrets": {"DASHSCOPE_API_KEY": secret_presence("DASHSCOPE_API_KEY"), "DEEPSEEK_API_KEY": secret_presence("DEEPSEEK_API_KEY")},
    }


def _stage(stages: dict[str, Any], name: str, fn: Callable[[], Any], calls: dict[str, int]) -> Any:
    before = dict(calls); started = utc_now(); clock = time.perf_counter()
    try:
        value = fn(); status, error = "completed", None
        return value
    except Exception as exc:
        status, error = "failed", getattr(exc, "code", type(exc).__name__)
        raise
    finally:
        stages[name] = {"started_at": started, "finished_at": utc_now(), "status": status, "stable_error": error, "actual_request_delta": {key: calls.get(key, 0) - before.get(key, 0) for key in calls}, "latency_ms": round((time.perf_counter() - clock) * 1000, 3)}


def execute_promptfoo_judges(*, generation: Path, evaluation: Path, deepseek_base_url: str, result_stem: str = "promptfoo", allow_nonzero: bool = False) -> dict[str, Any]:
    """Run exactly the four configured Promptfoo targets against sealed judge inputs.

    The function deliberately owns the subprocess environment so a provider
    cannot inherit ProxyChains or ambient HTTP proxy configuration.
    """
    generation = generation.resolve()
    evaluation = evaluation.resolve()
    config_path = (Path(__file__).parent / "promptfoo" / "round17c-promptfooconfig-real.yaml").resolve()
    entrypoint = (Path(__file__).parents[1] / "evaluation" / "promptfoo" / "node_modules" / "promptfoo" / "dist" / "src" / "entrypoint.js").resolve()
    output = evaluation / f"{result_stem}-cli-results.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    state_dir = evaluation / f".{result_stem}-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    for name in ("LD_PRELOAD", "PROXYCHAINS_CONF_FILE", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "FTP_PROXY", "http_proxy", "https_proxy", "all_proxy", "ftp_proxy"):
        env.pop(name, None)
    env.update({
        "NO_PROXY": "*", "no_proxy": "*", "ROUND17C_JUDGE_INPUTS_PATH": str(generation / "judge-inputs.json"),
        "ROUND17C_DEEPSEEK_BASE_URL": deepseek_base_url, "ROUND17C_DEEPSEEK_TRUST_ENV": "false",
        "ROUND17C_DEEPSEEK_MODEL": os.environ.get("ROUND17C_DEEPSEEK_MODEL", "deepseek-v4-pro"),
        "PROMPTFOO_DISABLE_TELEMETRY": "true", "PROMPTFOO_DISABLE_WAL_MODE": "true",
        "PROMPTFOO_CONFIG_DIR": str(state_dir),
    })
    argv = ["node", str(entrypoint), "eval", "-c", str(config_path), "--no-cache", "--no-share", "--no-progress-bar", "--no-table", "--max-concurrency", "1", "-o", str(output)]
    started = utc_now()
    completed = subprocess.run(argv, cwd=config_path.parent, env=env, capture_output=True, text=True, check=False)
    evaluation.mkdir(parents=True, exist_ok=True)
    (evaluation / f"{result_stem}-stdout.log").write_text(completed.stdout, encoding="utf-8")
    (evaluation / f"{result_stem}-stderr.log").write_text(completed.stderr, encoding="utf-8")
    process = {"argv": argv, "cwd": str(config_path.parent), "started_at": started, "finished_at": utc_now(), "exit_code": completed.returncode, "promptfoo_version": subprocess.check_output(["node", str(entrypoint), "--version"], cwd=config_path.parent, env=env, text=True).strip(), "environment_names": sorted(name for name in env if name in {"DEEPSEEK_API_KEY", "ROUND17C_DEEPSEEK_BASE_URL", "ROUND17C_DEEPSEEK_MODEL", "ROUND17C_DEEPSEEK_TRUST_ENV", "ROUND17C_JUDGE_INPUTS_PATH", "NO_PROXY", "no_proxy"})}
    (evaluation / f"{result_stem}-process.json").write_text(json.dumps(process, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not output.exists():
        raise Round17CContractError("PROMPTFOO_OUTPUT_MISSING")
    payload = json.loads(output.read_text(encoding="utf-8"))
    rows = payload.get("results", {}).get("results", [])
    attempts = [{"job": row.get("metadata", {}).get("round17c_judge_job"), "status": "attempted"} for row in rows if isinstance(row, dict)]
    if completed.returncode and not allow_nonzero:
        raise Round17CContractError("PROMPTFOO_NONZERO_EXIT")
    return {"attempts": attempts, "results": payload, "process": process}


def orchestrate(*, real_flag: bool, root: Path = ROOT, qwen_model: str | None = None, qwen_base_url: str | None = None, deepseek_model: str | None = None, deepseek_base_url: str | None = None) -> Path:
    """Run generation stages; Judge execution is delegated only to Promptfoo in a later stage.

    The callable is intentionally gated before reading configuration or constructing clients.
    """
    if not authorized(real_flag):
        return create_blocked_run(root=root)
    if not os.environ.get("DASHSCOPE_API_KEY") or not os.environ.get("DEEPSEEK_API_KEY"):
        return create_blocked_run(root=root)
    resolved = resolve_config()
    qwen_model = qwen_model or resolved["qwen_model"]; qwen_base_url = qwen_base_url or resolved["qwen_base_url"]
    deepseek_model = deepseek_model or resolved["deepseek_model"]; deepseek_base_url = deepseek_base_url or resolved["deepseek_base_url"]
    run_id = f"round-17c-clean-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{_git(['git','rev-parse','--short','HEAD'])}"
    qwen_wire: dict[str, Any] = {"requests": 0, "attempts": []}
    def qwen_factory():
        return build_model(model_name=qwen_model, openai_client=build_dashscope_client(api_key=os.environ["DASHSCOPE_API_KEY"], base_url=qwen_base_url, counter=qwen_wire))
    def promptfoo_executor(generation: Path, _prompts: dict[str, Any]) -> dict[str, Any]:
        return execute_promptfoo_judges(generation=generation, evaluation=generation.parent / "evaluation", deepseek_base_url=deepseek_base_url)
    return execute_round17c({"run_id": run_id, "qwen": {"model": qwen_model, "base_url": qwen_base_url}, "deepseek": {"model": deepseek_model, "base_url": deepseek_base_url}, "retries": 0}, qwen_factory, promptfoo_executor, root, qwen_wire=qwen_wire)

    # Legacy implementation below is intentionally unreachable.
    run_dir = root / run_id; run_dir.mkdir(parents=True, exist_ok=False)
    calls = {"qwen": 0, "deepseek": 0, "image": 0, "database_writes": 0}; stages: dict[str, Any] = {}
    config = effective_config(run_id, qwen_model=qwen_model, qwen_base_url=qwen_base_url, deepseek_model=deepseek_model, deepseek_base_url=deepseek_base_url)
    _write(run_dir / "effective-config.json", config); _write(run_dir / "brief.json", BRIEF_PAYLOAD)
    manifest = {"run_id": run_id, "started_at": utc_now(), "git_sha": config["git_sha"], "dirty": config["dirty"], "technical_status": "failed", "evaluation_validity": "not_run", "integrity_status": "pending", "actual_calls": calls, "retries": 0, "required_files": GENERATION_INVENTORY, "artifact_inventory_version": 1}
    _write(run_dir / "manifest.json", manifest)
    try:
        frozen = _stage(stages, "freeze_evidence", lambda: freeze_evidence(BRIEF_PAYLOAD["brief"]), calls); _write(run_dir / "frozen-evidence.json", frozen)
        wire = {"requests": 0}; client = build_dashscope_client(api_key=os.environ["DASHSCOPE_API_KEY"], base_url=qwen_base_url, counter=wire); model = build_model(model_name=qwen_model, openai_client=client)
        baseline = _stage(stages, "baseline", lambda: run_baseline(model, BRIEF_PAYLOAD["brief"], frozen), calls); calls["qwen"] += baseline[1]["requests"]; _write(run_dir / "baseline-result.json", {"parsed_output": baseline[0].model_dump(), "metrics": baseline[1]})
        guided = _stage(stages, "guided_planner", lambda: run_guided(model, BRIEF_PAYLOAD["brief"], frozen), calls); calls["qwen"] += guided[1]["requests"]; _write(run_dir / "guided-result.json", {"parsed_output": guided[0].model_dump(), "metrics": guided[1]})
        if calls["qwen"] > QWEN_BUDGET["total"]: raise Round17CContractError("QWEN_BUDGET_EXCEEDED")
        _write(run_dir / "judge-inputs.json", {"brief": BRIEF_PAYLOAD["brief"], "arms": {"baseline": baseline[0].model_dump(), "skill_guided": guided[0].model_dump()}, "candidate_mapping": {"ab": {"candidate_0": "baseline", "candidate_1": "skill_guided"}, "ba": {"candidate_0": "skill_guided", "candidate_1": "baseline"}}})
        _write(run_dir / "stage-status.json", stages); manifest["technical_status"] = "completed"; manifest["actual_calls"] = calls
        (run_dir / "manifest.json").unlink(); _write(run_dir / "manifest.json", manifest)
        seal_run(run_dir, GENERATION_INVENTORY, seal_name="generation-seal.json")
        return run_dir
    except Exception as exc:
        _write(run_dir / "stage-status.json", stages); manifest.update({"finished_at": utc_now(), "failure_stage": next((name for name in reversed(STAGES) if name in stages), "configuration"), "stable_error": getattr(exc, "code", type(exc).__name__), "actual_calls": calls})
        (run_dir / "manifest.json").unlink(); _write(run_dir / "manifest.json", manifest)
        return run_dir


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--real", action="store_true"); parser.add_argument("--check-config", action="store_true"); args = parser.parse_args()
    try:
        if args.check_config:
            print(json.dumps(resolve_config(), ensure_ascii=False, sort_keys=True)); return 0
        path = orchestrate(real_flag=args.real)
        print(path)
        return 0
    except Round17CContractError as exc:
        print(exc.code, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
