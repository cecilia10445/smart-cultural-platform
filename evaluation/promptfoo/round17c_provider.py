"""Read-only Promptfoo adapter for sealed, schema-checked Round 17C reports."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.round17c_reports import public_run


ARMS = {"baseline", "skill_guided"}


def call_api(_prompt: str, options: dict[str, Any], _context: dict[str, Any]) -> dict[str, Any]:
    config = options.get("config", {}) if isinstance(options, dict) else {}
    root = config.get("report_root") or os.environ.get("ROUND17C_REPORT_ROOT")
    run_id = config.get("run_id") or os.environ.get("ROUND17C_RUN_ID")
    arm = config.get("arm")
    if not isinstance(root, str) or not isinstance(run_id, str) or arm not in ARMS:
        return {"output": "", "error": "ROUND17C_PROVIDER_CONFIGURATION_REQUIRED", "metadata": {"executor_type": "promptfoo_file_read_only"}}
    try:
        run = public_run(Path(root), run_id)
        value = run["arms"].get(arm)
        if not isinstance(value, dict):
            raise ValueError("ARM_UNAVAILABLE")
        # Identity is intentionally absent: Judge receives only candidate content.
        return {"output": json.dumps({"product_copy": value["product_copy"], "image_design_spec": value["image_design_spec"]}, ensure_ascii=False), "metadata": {"executor_type": "promptfoo_file_read_only", "measurement_scope": "round17c_text_only"}}
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return {"output": "", "error": "ROUND17C_REPORT_UNAVAILABLE", "metadata": {"executor_type": "promptfoo_file_read_only"}}
