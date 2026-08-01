"""Short-transaction persistence for Runtime runs; separate from agent_steps."""
from __future__ import annotations

import uuid
import json
from datetime import datetime
from typing import Any

from backend.services.agent_dialogue_repository import AgentDialogueRepository


class AgentRuntimeRepository(AgentDialogueRepository):
    # Context summaries are derived data.  They live in their own table and do
    # not modify the append-only agent_messages fact log.
    def get_active_summary(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        with self._transaction() as cursor:
            self._locked_owned_session(cursor, session_id, user_id)
            cursor.execute("""SELECT * FROM agent_context_summaries
                WHERE user_id=%s AND session_id=%s AND status='active'
                ORDER BY session_version DESC LIMIT 1""", (user_id, session_id))
            row = self._fetchone(cursor)
        return self._summary_row(row)

    def list_summary_versions(self, user_id: str, session_id: str) -> list[dict[str, Any]]:
        with self._transaction() as cursor:
            self._locked_owned_session(cursor, session_id, user_id)
            cursor.execute("""SELECT * FROM agent_context_summaries WHERE user_id=%s AND session_id=%s
                ORDER BY session_version ASC""", (user_id, session_id))
            rows = [self._summary_row(dict(row)) for row in cursor.fetchall() if isinstance(row, dict)]
        return rows

    def create_summary_version(self, user_id: str, session_id: str, summary) -> dict[str, Any]:
        """Insert and activate a version under the session row lock.

        The small transaction makes the old/new active state atomic even when
        two workers notice a compression threshold at nearly the same time.
        """
        now, summary_id = self._now(), str(uuid.uuid4())
        payload = summary.model_dump(mode="json") if hasattr(summary, "model_dump") else dict(summary)
        with self._transaction() as cursor:
            self._locked_owned_session(cursor, session_id, user_id)
            cursor.execute("SELECT COALESCE(MAX(session_version),0)+1 AS n FROM agent_context_summaries WHERE user_id=%s AND session_id=%s FOR UPDATE", (user_id, session_id))
            version = int((self._fetchone(cursor) or {}).get("n") or 1)
            cursor.execute("UPDATE agent_context_summaries SET status='inactive',updated_at=%s WHERE user_id=%s AND session_id=%s AND status='active'", (now, user_id, session_id))
            cursor.execute("""INSERT INTO agent_context_summaries
                (id,user_id,session_id,schema_version,summary_json,source_message_start_id,source_message_end_id,
                 source_message_count,session_version,status,created_at,updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'active',%s,%s)""",
                (summary_id, user_id, session_id, payload.get("schema_version", "context-summary-v2"), self._json(payload),
                 payload.get("source_message_start_id"), payload.get("source_message_end_id"), int(payload.get("source_message_count", 0)),
                 version, now, now))
            cursor.execute("SELECT * FROM agent_context_summaries WHERE id=%s AND user_id=%s AND session_id=%s", (summary_id, user_id, session_id))
            row = self._fetchone(cursor)
        return self._summary_row(row) or {}

    def activate_summary(self, user_id: str, session_id: str, summary_id: str) -> dict[str, Any]:
        """Administrative/recovery activation retaining all historical rows."""
        now = self._now()
        with self._transaction() as cursor:
            self._locked_owned_session(cursor, session_id, user_id)
            cursor.execute("SELECT id FROM agent_context_summaries WHERE id=%s AND user_id=%s AND session_id=%s FOR UPDATE", (summary_id, user_id, session_id))
            if not self._fetchone(cursor):
                from backend.domain.agent_dialogue import AgentSessionNotFound
                raise AgentSessionNotFound()
            cursor.execute("UPDATE agent_context_summaries SET status='inactive',updated_at=%s WHERE user_id=%s AND session_id=%s AND status='active'", (now, user_id, session_id))
            cursor.execute("UPDATE agent_context_summaries SET status='active',updated_at=%s WHERE id=%s AND user_id=%s AND session_id=%s", (now, summary_id, user_id, session_id))
            cursor.execute("SELECT * FROM agent_context_summaries WHERE id=%s", (summary_id,))
            row = self._fetchone(cursor)
        return self._summary_row(row) or {}

    def get_messages_after_summary(self, user_id: str, session_id: str, source_message_end_id: str | None) -> list[dict[str, Any]]:
        """Return source rows after a summary boundary without assuming UUID order."""
        with self._transaction() as cursor:
            self._locked_owned_session(cursor, session_id, user_id)
            if source_message_end_id:
                cursor.execute("SELECT sequence_no FROM agent_messages WHERE id=%s AND session_id=%s", (source_message_end_id, session_id))
                boundary = self._fetchone(cursor)
                if boundary is None:
                    return []
                cursor.execute("SELECT * FROM agent_messages WHERE session_id=%s AND sequence_no>%s ORDER BY sequence_no ASC", (session_id, boundary["sequence_no"]))
            else:
                cursor.execute("SELECT * FROM agent_messages WHERE session_id=%s ORDER BY sequence_no ASC", (session_id,))
            return [dict(row) for row in cursor.fetchall() if isinstance(row, dict)]

    @staticmethod
    def _summary_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        value = row.get("summary_json")
        if isinstance(value, str):
            value = json.loads(value)
        row["summary"] = value
        return row
    def create_or_get_run(self, session_id: str, user_id: str, client_turn_id: str, agent_name: str) -> tuple[dict[str, Any], bool]:
        now = self._now()
        with self._transaction() as cursor:
            session = self._locked_owned_session(cursor, session_id, user_id)
            cursor.execute("SELECT * FROM agent_runtime_runs WHERE user_id=%s AND session_id=%s AND client_turn_id=%s", (user_id, session_id, client_turn_id))
            existing = self._fetchone(cursor)
            if existing:
                return existing, True
            run_id = str(uuid.uuid4())
            cursor.execute("""INSERT INTO agent_runtime_runs
                (id,user_id,session_id,client_turn_id,agent_name,status,session_status_at_start,model_request_count,tool_call_count,created_at)
                VALUES (%s,%s,%s,%s,%s,'running',%s,0,0,%s)""",
                (run_id, user_id, session_id, client_turn_id, agent_name, session["status"], now))
            cursor.execute("SELECT * FROM agent_runtime_runs WHERE id=%s", (run_id,))
            return self._fetchone(cursor), False

    def get_run(self, session_id: str, user_id: str, run_id: str) -> dict[str, Any]:
        with self._transaction() as cursor:
            self._locked_owned_session(cursor, session_id, user_id)
            cursor.execute("SELECT * FROM agent_runtime_runs WHERE id=%s AND session_id=%s AND user_id=%s", (run_id, session_id, user_id))
            row = self._fetchone(cursor)
        if not row:
            from backend.domain.agent_dialogue import AgentSessionNotFound
            raise AgentSessionNotFound()
        return row

    def get_safe_run_display(self, session_id: str, user_id: str, run_id: str) -> dict[str, Any]:
        """Allow-list one persisted Runtime turn for the browser workspace.

        Raw model payloads, tool arguments and observations never leave this
        boundary; the UI only receives final structured output and completed
        tool labels plus compact context metadata.
        """
        with self._transaction() as cursor:
            self._locked_owned_session(cursor, session_id, user_id)
            cursor.execute("SELECT * FROM agent_runtime_runs WHERE id=%s AND session_id=%s AND user_id=%s", (run_id, session_id, user_id))
            run = self._fetchone(cursor)
            if run is None:
                from backend.domain.agent_dialogue import AgentSessionNotFound
                raise AgentSessionNotFound()
            cursor.execute("""SELECT event_type,tool_name,success,budget_snapshot_json
                FROM agent_runtime_events WHERE run_id=%s ORDER BY sequence_number ASC""", (run_id,))
            events = [dict(row) for row in cursor.fetchall() if isinstance(row, dict)]
        final = run.get("final_output_json")
        if isinstance(final, str):
            try: final = json.loads(final)
            except ValueError: final = None
        context_metadata: dict[str, Any] = {}
        tool_names: list[str] = []
        for event in events:
            if event.get("event_type") == "context_built":
                value = event.get("budget_snapshot_json")
                if isinstance(value, str):
                    try: value = json.loads(value)
                    except ValueError: value = {}
                if isinstance(value, dict):
                    context_metadata = {key: value[key] for key in (
                        "summary_version", "compression_triggered", "compression_reason", "estimated_tokens_before",
                        "estimated_tokens_after", "messages_summarized", "recent_messages_included", "fallback_used",
                        "rag_status", "rag_summary", "final_output_origin",
                    ) if key in value}
            if event.get("event_type") in {"tool_completed", "tool_semantic_replayed"} and event.get("success") in (True, 1):
                name = event.get("tool_name")
                if isinstance(name, str) and name not in tool_names:
                    tool_names.append(name)
        return {
            "id": run["id"], "status": run.get("status"), "final_output_type": run.get("final_output_type"),
            "output": final if isinstance(final, dict) else None,
            "retryable": run.get("status") == "failed" and run.get("error_code") in {
                "RUNTIME_OUTPUT_REPAIR_INVALID", "RUNTIME_MODEL_TIMEOUT", "RUNTIME_PROVIDER_UNAVAILABLE",
            },
            "safe_tool_events": tool_names, "context_metadata": {key: value for key, value in context_metadata.items()
                                                                      if key not in {"rag_status", "rag_summary"}},
            "rag": {"status": context_metadata.get("rag_status"), "summary": context_metadata.get("rag_summary")},
        }

    def complete_run(self, run: dict[str, Any], result, user_content: str, assistant_text: str, assistant_json: dict[str, Any]) -> dict[str, Any]:
        now = self._now()
        with self._transaction() as cursor:
            session = self._locked_owned_session(cursor, run["session_id"], run["user_id"])
            cursor.execute("SELECT * FROM agent_runtime_runs WHERE id=%s FOR UPDATE", (run["id"],))
            current = self._fetchone(cursor)
            if current and current["status"] != "running":
                return current
            final = result.final_output
            status = result.status.value
            error = result.error.model_dump() if result.error else None
            cursor.execute("""UPDATE agent_runtime_runs SET status=%s,model_request_count=%s,tool_call_count=%s,final_output_type=%s,
                final_output_json=%s,pending_approval_json=%s,error_code=%s,error_summary=%s,completed_at=%s WHERE id=%s""",
                (status, result.usage.model_requests, result.usage.requested_tool_calls,
                 ((final or {}).get("intent") or (final or {}).get("result", final or {}).get("kind")) if final else None, self._json(final),
                 self._json(result.pending_approval.model_dump() if result.pending_approval else None),
                 error.get("code") if error else None, error.get("message") if error else None, now, run["id"]))
            cursor.execute("SELECT COALESCE(MAX(sequence_no),0)+1 AS n FROM agent_messages WHERE session_id=%s", (run["session_id"],))
            n = int((self._fetchone(cursor) or {}).get("n") or 1)
            cursor.execute("INSERT INTO agent_messages (id,session_id,sequence_no,role,message_type,content_text,content_json,client_turn_id,created_at) VALUES (%s,%s,%s,'user','runtime_request',%s,NULL,%s,%s)", (str(uuid.uuid4()),run["session_id"],n,user_content,run["client_turn_id"],now))
            cursor.execute("INSERT INTO agent_messages (id,session_id,sequence_no,role,message_type,content_text,content_json,created_at) VALUES (%s,%s,%s,'assistant','runtime_result',%s,%s,%s)", (str(uuid.uuid4()),run["session_id"],n+1,assistant_text,self._json(assistant_json),now))
            cursor.execute("UPDATE agent_sessions SET updated_at=%s WHERE id=%s AND user_id=%s", (now, run["session_id"], run["user_id"]))
            for record in result.traces:
                item = record.model_dump(mode="json")
                cursor.execute("""INSERT INTO agent_runtime_events (id,run_id,sequence_number,event_type,tool_call_id,tool_name,risk,success,error_code,duration_ms,arguments_hash,input_summary_json,output_summary_json,budget_snapshot_json,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (str(uuid.uuid4()),run["id"],item["step"],item["event_type"],item["tool_call_id"],item["tool_name"],item["risk"],item["success"],item["error_code"],item["duration_ms"],item["arguments_hash"],self._json(item["input_summary"]),self._json(item["output_summary"]),self._json(item["budget_snapshot"]),now))
            context_metadata = getattr(result, "context_metadata", None) or {}
            if context_metadata:
                cursor.execute("SELECT COALESCE(MAX(sequence_number),0)+1 AS n FROM agent_runtime_events WHERE run_id=%s", (run["id"],))
                sequence = int((self._fetchone(cursor) or {}).get("n") or 1)
                cursor.execute("""INSERT INTO agent_runtime_events
                    (id,run_id,sequence_number,event_type,success,budget_snapshot_json,created_at)
                    VALUES (%s,%s,%s,'context_built',TRUE,%s,%s)""",
                    (str(uuid.uuid4()), run["id"], sequence, self._json(context_metadata), now))
            cursor.execute("SELECT * FROM agent_runtime_runs WHERE id=%s", (run["id"],))
            return self._fetchone(cursor)
