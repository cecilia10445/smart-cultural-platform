#!/usr/bin/env python3
"""One explicitly enabled, redacted HTTP smoke for the read-only agent runtime."""
from __future__ import annotations

import json
import os
import sys
import time
import uuid

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.config import load_settings


def main() -> int:
    if os.getenv("AGENT_RUNTIME_ALLOW_REAL_MODEL", "").lower() not in {"1", "true", "yes", "on"}:
        print(json.dumps({"ok": False, "code": "RUNTIME_REAL_MODEL_DISABLED"}))
        return 2
    settings = load_settings()
    if not settings.dashscope_api_key:
        print(json.dumps({"ok": False, "code": "RUNTIME_PROVIDER_UNAVAILABLE"}))
        return 3
    # Import after the explicit guard so ordinary runs can never create a DB row.
    from backend.routes.agent_dialogue import router
    from backend.routes import api
    from backend.services.agent_runtime_repository import AgentRuntimeRepository

    # Reuse the exact application pool that the HTTP dependency resolves.
    repository = AgentRuntimeRepository(api.mysql_service)
    owner = f"agent-runtime-smoke-{uuid.uuid4()}"
    session = repository.create_session(owner)
    application = FastAPI()
    application.include_router(router)
    token = jwt.encode({"user_id": owner}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    started = time.monotonic()
    response = TestClient(application).post(
        f"/api/v2/agent-design/sessions/{session['id']}/assistant-turns",
        headers={"Authorization": f"Bearer {token}"},
        json={"client_turn_id": "controlled-real-smoke", "content": "Use the read-only tools before proposing a concise modern Dunhuang bookmark brief; avoid excessive antique imitation."},
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    body = response.json()
    run = body.get("data", {}).get("run", {}) if isinstance(body, dict) else {}
    event_rows = []
    try:
        with repository._transaction() as cursor:
            cursor.execute("SELECT tool_name, tool_call_id FROM agent_runtime_events WHERE run_id=%s ORDER BY sequence_number", (run.get("id"),))
            event_rows = [dict(row) for row in cursor.fetchall()]
    except Exception:
        pass
    summary = {
        "ok": response.status_code == 200 and run.get("status") == "completed",
        "http_status": response.status_code,
        "provider": "dashscope", "model": settings.agent_runtime_model,
        "runtime_run_id": run.get("id"), "session_id": session["id"],
        "run_status": run.get("status"), "model_request_count": run.get("model_request_count", 0),
        "tool_call_count": run.get("tool_call_count", 0),
        "tool_names": [row.get("tool_name") for row in event_rows if row.get("tool_name")],
        "tool_call_ids_present": any(row.get("tool_call_id") for row in event_rows),
        "final_output_type": run.get("final_output_type"), "duration_ms": duration_ms,
        "error_code": run.get("error_code") or body.get("code"),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["ok"] and summary["tool_call_count"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
