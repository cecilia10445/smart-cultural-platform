"""Read-only, schema-checked public DTOs for sealed Round 17C artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


RUN_ID = re.compile(r"^round-17c-clean-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{7,40}$")
MAX_BYTES = 10 * 1024 * 1024


class ReportUnavailable(ValueError):
    pass


def _json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ReportUnavailable("REPORT_UNAVAILABLE")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReportUnavailable("REPORT_UNAVAILABLE")
    return value


def _run_path(root: Path, run_id: str) -> Path:
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise ReportUnavailable("REPORT_UNAVAILABLE")
    root = root.resolve()
    result = root / run_id
    if result.is_symlink() or not result.is_dir() or result.resolve().parent != root:
        raise ReportUnavailable("REPORT_UNAVAILABLE")
    return result


def _integrity(run_dir: Path) -> bool:
    seal = _json(run_dir / "sha256sums.json")
    checksums = seal.get("sha256")
    required = seal.get("required_files")
    if seal.get("inventory_version") != 1 or not isinstance(checksums, dict) or not isinstance(required, list):
        return False
    controlled = {entry.name for entry in run_dir.iterdir() if entry.is_file() and entry.name != "sha256sums.json"}
    if set(required) != controlled or set(checksums) != controlled:
        return False
    if not {"manifest.json", "normalized-report.json", "brief.json", "frozen-evidence.json"}.issubset(controlled):
        return False
    for name, expected in checksums.items():
        if not isinstance(name, str) or not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            return False
        path = run_dir / name
        if path.parent != run_dir or not path.is_file() or path.is_symlink():
            return False
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            return False
    return True


def _arm(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReportUnavailable("REPORT_UNAVAILABLE")
    copy, spec, ids = value.get("product_copy"), value.get("image_design_spec"), value.get("used_source_ids")
    if not isinstance(copy, str) or not isinstance(spec, str) or not isinstance(ids, list):
        raise ReportUnavailable("REPORT_UNAVAILABLE")
    return {
        "product_copy": copy,
        "image_design_spec": spec,
        "used_source_ids": [item for item in ids if isinstance(item, str)],
        "latency_ms": value.get("latency_ms") if isinstance(value.get("latency_ms"), (int, float)) else None,
        "requests": value.get("requests") if isinstance(value.get("requests"), int) else None,
        "token_usage": value.get("token_usage") if isinstance(value.get("token_usage"), dict) else None,
        "tool_trajectory": value.get("tool_trajectory") if isinstance(value.get("tool_trajectory"), list) else [],
        "dimensions": value.get("dimensions") if isinstance(value.get("dimensions"), dict) else {},
    }


def public_run(root: Path, run_id: str) -> dict[str, Any]:
    run_dir = _run_path(root, run_id)
    manifest, report = _json(run_dir / "manifest.json"), _json(run_dir / "normalized-report.json")
    technical = manifest.get("technical_status")
    validity = report.get("evaluation_validity", manifest.get("evaluation_validity"))
    integrity = "verified" if _integrity(run_dir) else "failed"
    if technical not in {"not_run", "blocked", "completed", "failed"} or validity not in {"not_run", "comparable", "evaluation_inconclusive", "judge_parse_error", "judge_inconsistent", "inconclusive_position_bias"}:
        raise ReportUnavailable("REPORT_UNAVAILABLE")
    arms = report.get("arms", {})
    if not isinstance(arms, dict):
        raise ReportUnavailable("REPORT_UNAVAILABLE")
    if integrity == "failed":
        return {
            "run_id": run_id, "started_at": manifest.get("started_at"), "finished_at": manifest.get("finished_at"),
            "technical_status": technical, "evaluation_validity": "evaluation_inconclusive", "integrity_status": "failed",
            "failure_stage": "integrity", "stable_error": "INTEGRITY_CHECK_FAILED", "model": None, "judge_model": None,
            "actual_calls": {}, "arms": {}, "winner": None,
        }
    return {
        "run_id": run_id,
        "started_at": manifest.get("started_at") if isinstance(manifest.get("started_at"), str) else None,
        "finished_at": manifest.get("finished_at") if isinstance(manifest.get("finished_at"), str) else None,
        "technical_status": technical,
        "evaluation_validity": validity,
        "integrity_status": integrity,
        "failure_stage": manifest.get("failure_stage") if isinstance(manifest.get("failure_stage"), str) else None,
        "stable_error": manifest.get("stable_error") if isinstance(manifest.get("stable_error"), str) else None,
        "model": manifest.get("model", {}).get("name") if isinstance(manifest.get("model"), dict) else None,
        "judge_model": manifest.get("judge_model") if isinstance(manifest.get("judge_model"), str) else None,
        "actual_calls": manifest.get("actual_calls") if isinstance(manifest.get("actual_calls"), dict) else {},
        "arms": {key: _arm(value) for key, value in arms.items() if key in {"baseline", "skill_guided"}},
        "winner": report.get("winner") if validity == "comparable" and report.get("winner") in {"baseline", "skill_guided"} else None,
    }


def list_runs(root: Path) -> list[dict[str, Any]]:
    if not root.exists() or root.is_symlink():
        return []
    values = []
    for entry in root.iterdir():
        if not entry.is_dir() or entry.is_symlink() or not RUN_ID.fullmatch(entry.name):
            continue
        try:
            report = public_run(root, entry.name)
            values.append({key: report[key] for key in ("run_id", "started_at", "technical_status", "evaluation_validity", "integrity_status")})
        except (OSError, UnicodeError, json.JSONDecodeError, ReportUnavailable):
            values.append({"run_id": entry.name, "started_at": None, "technical_status": "failed", "evaluation_validity": "not_run", "integrity_status": "failed"})
    return sorted(values, key=lambda value: value["started_at"] or "", reverse=True)
