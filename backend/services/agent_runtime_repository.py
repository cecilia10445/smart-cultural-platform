"""Short-transaction persistence for Runtime runs; separate from agent_steps."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from backend.services.agent_dialogue_repository import AgentDialogueRepository


class AgentRuntimeRepository(AgentDialogueRepository):
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
                 (final or {}).get("result", final or {}).get("kind") if final else None, self._json(final),
                 self._json(result.pending_approval.model_dump() if result.pending_approval else None),
                 error.get("code") if error else None, error.get("message") if error else None, now, run["id"]))
            cursor.execute("SELECT COALESCE(MAX(sequence_no),0)+1 AS n FROM agent_messages WHERE session_id=%s", (run["session_id"],))
            n = int((self._fetchone(cursor) or {}).get("n") or 1)
            cursor.execute("INSERT INTO agent_messages (id,session_id,sequence_no,role,message_type,content_text,content_json,client_turn_id,created_at) VALUES (%s,%s,%s,'user','runtime_request',%s,NULL,%s,%s)", (str(uuid.uuid4()),run["session_id"],n,user_content,run["client_turn_id"],now))
            cursor.execute("INSERT INTO agent_messages (id,session_id,sequence_no,role,message_type,content_text,content_json,created_at) VALUES (%s,%s,%s,'assistant','runtime_result',%s,%s,%s)", (str(uuid.uuid4()),run["session_id"],n+1,assistant_text,self._json(assistant_json),now))
            for record in result.traces:
                item = record.model_dump(mode="json")
                cursor.execute("""INSERT INTO agent_runtime_events (id,run_id,sequence_number,event_type,tool_call_id,tool_name,risk,success,error_code,duration_ms,arguments_hash,input_summary_json,output_summary_json,budget_snapshot_json,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (str(uuid.uuid4()),run["id"],item["step"],item["event_type"],item["tool_call_id"],item["tool_name"],item["risk"],item["success"],item["error_code"],item["duration_ms"],item["arguments_hash"],self._json(item["input_summary"]),self._json(item["output_summary"]),self._json(item["budget_snapshot"]),now))
            cursor.execute("SELECT * FROM agent_runtime_runs WHERE id=%s", (run["id"],))
            return self._fetchone(cursor)
