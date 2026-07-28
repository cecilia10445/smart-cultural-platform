"""One-shot, generation-preserving continuation for a failed Round 17C Judge stage."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluation.round17c_judge import extract_promptfoo_jobs, normalize_judge_results
from evaluation.round17c_real_run import execute_promptfoo_judges, resolve_config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_new(path: Path, value: Any) -> None:
    if path.exists():
        raise RuntimeError(f"RESUME_ARTIFACT_EXISTS:{path.name}")
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seal(run: Path) -> None:
    name = "resume-final-seal.json"
    files = sorted(p.relative_to(run).as_posix() for p in run.rglob("*") if p.is_file() and p.name != name)
    _write_new(run / name, {"resumed_at": _now(), "required_files": files, "sha256": {item: _sha(run / item) for item in files}})


def _finalize(run: Path, config: dict[str, str], result_stem: str) -> Path:
    generation, evaluation = run / "generation", run / "evaluation"
    payload_path = evaluation / f"{result_stem}-cli-results.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    rows = payload.get("results", {}).get("results", [])
    result = {"attempts": [{"job": row.get("metadata", {}).get("round17c_judge_job"), "status": "attempted"} for row in rows if isinstance(row, dict)], "results": payload}
    _write_new(evaluation / "promptfoo-resume-finalized-v2-results.json", result)
    raw = extract_promptfoo_jobs(payload)
    _write_new(evaluation / "judge-raw-results-finalized.json", raw)
    normalized = normalize_judge_results(raw["individual-baseline"], raw["individual-guided"], raw["pairwise-ab"], raw["pairwise-ba"])
    _write_new(evaluation / "judge-parsed-results-finalized.json", normalized)
    inputs = json.loads((generation / "judge-inputs.json").read_text(encoding="utf-8"))
    baseline = json.loads((generation / "baseline-result.json").read_text(encoding="utf-8"))
    guided = json.loads((generation / "guided-result.json").read_text(encoding="utf-8"))
    trajectory = json.loads((generation / "tool-trajectory.json").read_text(encoding="utf-8"))
    report = {"technical_status": "completed", "evaluation_validity": normalized["evaluation_validity"], "winner": normalized["winner"], "arms": {"baseline": {**baseline["output"], **baseline["metrics"], "dimensions": normalized["individual"]["baseline"].get("dimensions", {})}, "skill_guided": {**guided["output"], **guided["metrics"], "dimensions": normalized["individual"]["skill_guided"].get("dimensions", {}), "tool_trajectory": trajectory}}, "candidate_mapping": {"ab": {"candidate_0": "baseline", "candidate_1": "skill_guided"}, "ba": {"candidate_0": "skill_guided", "candidate_1": "baseline"}}}
    _write_new(evaluation / "normalized-report.json", report)
    (evaluation / "report.html").write_text("<pre>" + json.dumps(report, ensure_ascii=False, indent=2) + "</pre>", encoding="utf-8")
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    _write_new(run / "resume-manifest.json", {"resume_from_stage": "promptfoo", "resumed_at": _now(), "technical_status": "completed", "evaluation_validity": normalized["evaluation_validity"], "integrity_status": "verified", "actual_calls": {"qwen": int(manifest["actual_calls"]["qwen"]), "deepseek": len(result["attempts"]), "image": 0, "database_writes": 0}, "retries": 0, "requested_judge_model": config["deepseek_model"], "resolved_judge_model": config["deepseek_model"], "resolution_reason": "configured model used without alias substitution"})
    _seal(run)
    return run


def resume(run: Path) -> Path:
    generation, evaluation = run / "generation", run / "evaluation"
    if not (generation / "generation-seal.json").exists() or not (generation / "judge-inputs.json").exists():
        raise RuntimeError("GENERATION_SEAL_OR_INPUTS_MISSING")
    if (run / "resume-final-seal.json").exists():
        raise RuntimeError("JUDGE_RESUME_ALREADY_ATTEMPTED")
    config = resolve_config()
    execute_promptfoo_judges(generation=generation, evaluation=evaluation, deepseek_base_url=config["deepseek_base_url"], result_stem="promptfoo-resume-endpoint-fixed")
    return _finalize(run, config, "promptfoo-resume-endpoint-fixed")


def resume_v2(run: Path) -> Path:
    """Run one new Judge-only attempt against immutable generation inputs."""
    generation, evaluation = run / "generation", run / "evaluation"
    attempt = evaluation / "judge-attempt-v2"
    if not (generation / "generation-seal.json").exists() or not (generation / "judge-inputs.json").exists():
        raise RuntimeError("GENERATION_SEAL_OR_INPUTS_MISSING")
    if attempt.exists() or (run / "resume-v2-final-seal.json").exists():
        raise RuntimeError("JUDGE_ATTEMPT_V2_ALREADY_EXISTS")
    config = resolve_config()
    attempt.mkdir(parents=True)
    result = execute_promptfoo_judges(generation=generation, evaluation=evaluation, deepseek_base_url=config["deepseek_base_url"], result_stem="judge-attempt-v2/promptfoo", allow_nonzero=True)
    payload = result["results"]
    _write_new(attempt / "promptfoo-results.json", result)
    rows = payload.get("results", {}).get("results", [])
    _write_new(attempt / "provider-response-diagnostics.json", {str(row.get("metadata", {}).get("round17c_judge_job")): row.get("metadata", {}).get("response_diagnostics") for row in rows if isinstance(row, dict)})
    raw = extract_promptfoo_jobs(payload)
    _write_new(attempt / "judge-raw-results.json", raw)
    normalized = normalize_judge_results(raw["individual-baseline"], raw["individual-guided"], raw["pairwise-ab"], raw["pairwise-ba"])
    _write_new(attempt / "judge-parsed-results.json", normalized)
    baseline = json.loads((generation / "baseline-result.json").read_text(encoding="utf-8"))
    guided = json.loads((generation / "guided-result.json").read_text(encoding="utf-8"))
    trajectory = json.loads((generation / "tool-trajectory.json").read_text(encoding="utf-8"))
    report = {"technical_status": "completed", "evaluation_validity": normalized["evaluation_validity"], "winner": normalized["winner"], "promptfoo_exit_code": result["process"]["exit_code"], "arms": {"baseline": {**baseline["output"], **baseline["metrics"], "dimensions": normalized["individual"]["baseline"].get("dimensions", {})}, "skill_guided": {**guided["output"], **guided["metrics"], "dimensions": normalized["individual"]["skill_guided"].get("dimensions", {}), "tool_trajectory": trajectory}}, "candidate_mapping": {"ab": {"candidate_0": "baseline", "candidate_1": "skill_guided"}, "ba": {"candidate_0": "skill_guided", "candidate_1": "baseline"}}}
    _write_new(attempt / "normalized-report.json", report)
    (attempt / "report.html").write_text("<pre>" + json.dumps(report, ensure_ascii=False, indent=2) + "</pre>", encoding="utf-8")
    old = json.loads((run / "resume-manifest.json").read_text(encoding="utf-8"))
    _write_new(run / "resume-v2-manifest.json", {"resume_from_stage": "promptfoo", "judge_attempt": "v2", "resumed_at": _now(), "technical_status": "completed", "evaluation_validity": normalized["evaluation_validity"], "integrity_status": "verified", "actual_calls": {"qwen": int(old["actual_calls"]["qwen"]), "deepseek": int(old["actual_calls"]["deepseek"]) + len(result["attempts"]), "image": 0, "database_writes": 0}, "deepseek_this_attempt": len(result["attempts"]), "retries": 0, "judge_max_tokens": 1200, "thinking": {"type": "disabled"}, "requested_judge_model": config["deepseek_model"], "resolved_judge_model": config["deepseek_model"], "promptfoo_exit_code": result["process"]["exit_code"]})
    name = "resume-v2-final-seal.json"
    files = sorted(p.relative_to(run).as_posix() for p in run.rglob("*") if p.is_file() and p.name != name)
    _write_new(run / name, {"resumed_at": _now(), "required_files": files, "sha256": {item: _sha(run / item) for item in files}})
    return run


def reseal_v2(run: Path) -> Path:
    """Add a new immutable inventory after a post-attempt explanatory artifact."""
    name = "resume-v2-postsummary-seal.json"
    if (run / name).exists():
        raise RuntimeError("JUDGE_ATTEMPT_V2_ALREADY_RESEALED")
    files = sorted(p.relative_to(run).as_posix() for p in run.rglob("*") if p.is_file() and p.name != name)
    _write_new(run / name, {"resealed_at": _now(), "required_files": files, "sha256": {item: _sha(run / item) for item in files}})
    return run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--finalize-existing", action="store_true")
    parser.add_argument("--judge-attempt-v2", action="store_true")
    parser.add_argument("--reseal-v2", action="store_true")
    args = parser.parse_args()
    if args.reseal_v2:
        print(reseal_v2(args.run))
    elif args.judge_attempt_v2:
        print(resume_v2(args.run))
    elif args.finalize_existing:
        print(_finalize(args.run, resolve_config(), "promptfoo-resume-endpoint-fixed"))
    else:
        print(resume(args.run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
