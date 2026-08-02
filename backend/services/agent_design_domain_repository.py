"""Owner-scoped, non-executing persistence primitives for the F0 design graph."""
from __future__ import annotations

import json
import uuid
from typing import Any

from backend.domain.agent_design_domain import (
    ActionApprovalIdempotencyConflict, ActionIdempotencyConflict, ActionNotFound, ActionRecord, ActionReferenceConflict, ActionStateConflict, ActionStatus, ActionType,
    AgentGenerationHistoryNotFound, ArtifactNotFound, ArtifactOrigin, ArtifactParentConflict, ArtifactRecord, ArtifactStatus, ArtifactType, ArtifactVersionConflict,
    DesignTaskNotFound, DesignTaskOrigin, DesignTaskRecord, DesignTaskScopeConflict, DesignTaskStatus, DesignTaskVersionConflict,
    ConversationProjection, ConversationStatus, DesignScopeType, canonical_json_hash, design_scope,
)
from backend.services.agent_dialogue_repository import AgentDialogueRepository


class AgentDesignDomainRepository(AgentDialogueRepository):
    @staticmethod
    def _json_value(value: Any, default: Any):
        if isinstance(value, str):
            try: value = json.loads(value)
            except ValueError: return default
        return default if value is None else value

    def _task(self, row):
        if row is None: raise DesignTaskNotFound()
        return DesignTaskRecord.model_validate(row)

    def _artifact(self, row):
        if row is None: raise ArtifactNotFound()
        value = dict(row); value["content_json"] = self._json_value(value.get("content_json"), {})
        return ArtifactRecord.model_validate(value)

    def _action(self, row):
        if row is None: raise ActionNotFound()
        value = dict(row); value["source_artifact_ids_json"] = self._json_value(value.get("source_artifact_ids_json"), [])
        for key in ("proposal_snapshot_json", "approval_snapshot_json", "result_json"): value[key] = self._json_value(value.get(key), None)
        return ActionRecord.model_validate(value)

    @staticmethod
    def _scope(session_id: str, task_id: str | None) -> tuple[DesignScopeType, str]:
        return ((DesignScopeType.TASK, design_scope(DesignScopeType.TASK, session_id, task_id))
                if task_id else (DesignScopeType.CONVERSATION, design_scope(DesignScopeType.CONVERSATION, session_id)))

    def _lock_scope(self, cursor, user_id: str, session_id: str, task_id: str | None):
        session = self._locked_owned_session(cursor, session_id, user_id)
        task = self._locked_task(cursor, task_id, user_id, session_id) if task_id else None
        return session, task, *self._scope(session_id, task_id)

    @staticmethod
    def _conversation_projection(row: dict[str, Any]) -> ConversationProjection:
        # ``agent_sessions`` deliberately still contains legacy workflow
        # columns (status/current_stage/brief JSON/etc.).  New domain DTOs are
        # strict, so project only the Conversation contract rather than
        # validating the physical row wholesale.  This keeps an old Session
        # readable as an active Conversation and prevents a false persistence
        # failure when an optional Design Task is absent.
        raw = dict(row)
        value = {
            "id": raw.get("id"), "user_id": raw.get("user_id"),
            "conversation_status": raw.get("conversation_status") or ConversationStatus.ACTIVE.value,
            "active_task_id": raw.get("active_task_id"), "archived_at": raw.get("archived_at"),
            "version": raw.get("version"), "created_at": raw.get("created_at"), "updated_at": raw.get("updated_at"),
            "legacy_session_status": raw.get("status"),
        }
        return ConversationProjection.model_validate(value)

    def get_conversation(self, user_id, session_id):
        with self._transaction() as cursor:
            cursor.execute("SELECT * FROM agent_sessions WHERE id=%s AND user_id=%s", (session_id, user_id)); row = self._fetchone(cursor)
        if row is None:
            from backend.domain.agent_dialogue import AgentSessionNotFound
            raise AgentSessionNotFound()
        return self._conversation_projection(row)

    def _locked_task(self, cursor, task_id, user_id, session_id):
        cursor.execute("SELECT * FROM agent_design_tasks WHERE id=%s AND user_id=%s AND session_id=%s FOR UPDATE", (task_id, user_id, session_id))
        row = self._fetchone(cursor)
        if row is None: raise DesignTaskNotFound()
        return row

    def create_task(self, user_id, session_id, *, title, client_task_id=None, status=DesignTaskStatus.EXPLORING, origin=DesignTaskOrigin.NATIVE):
        task_id, now = str(uuid.uuid4()), self._now()
        with self._transaction() as cursor:
            self._locked_owned_session(cursor, session_id, user_id)
            if client_task_id:
                cursor.execute("SELECT * FROM agent_design_tasks WHERE user_id=%s AND session_id=%s AND client_task_id=%s FOR UPDATE", (user_id, session_id, client_task_id)); existing = self._fetchone(cursor)
                if existing is not None: return self._task(existing)
            cursor.execute("""INSERT INTO agent_design_tasks (id,user_id,session_id,title,status,origin,version,client_task_id,created_at,updated_at,paused_at,closed_at)
                VALUES (%s,%s,%s,%s,%s,%s,1,%s,%s,%s,NULL,NULL)""", (task_id, user_id, session_id, title.strip(), status.value, origin.value, client_task_id, now, now))
            cursor.execute("SELECT * FROM agent_design_tasks WHERE id=%s AND user_id=%s", (task_id, user_id)); row = self._fetchone(cursor)
        return self._task(row)

    def get_task(self, task_id, user_id, session_id):
        with self._transaction() as cursor:
            cursor.execute("SELECT * FROM agent_design_tasks WHERE id=%s AND user_id=%s AND session_id=%s", (task_id, user_id, session_id)); row = self._fetchone(cursor)
        return self._task(row)

    def list_tasks(self, user_id, session_id):
        with self._transaction() as cursor:
            self._locked_owned_session(cursor, session_id, user_id)
            cursor.execute("SELECT * FROM agent_design_tasks WHERE user_id=%s AND session_id=%s ORDER BY updated_at DESC,created_at DESC,id ASC", (user_id, session_id)); rows = [dict(r) for r in cursor.fetchall() if isinstance(r, dict)]
        return [self._task(row) for row in rows]

    def select_active_task(self, user_id, session_id, task_id, *, expected_session_version=None):
        now = self._now()
        with self._transaction() as cursor:
            session = self._locked_owned_session(cursor, session_id, user_id)
            if expected_session_version is not None and int(session.get("version") or 0) != expected_session_version: raise DesignTaskVersionConflict()
            task = self._locked_task(cursor, task_id, user_id, session_id)
            if task.get("status") == DesignTaskStatus.CLOSED.value: raise DesignTaskScopeConflict("Closed design tasks cannot be selected.")
            cursor.execute("UPDATE agent_sessions SET active_task_id=%s,version=version+1,updated_at=%s WHERE id=%s AND user_id=%s AND version=%s", (task_id, now, session_id, user_id, session["version"]))
            if cursor.rowcount != 1: raise DesignTaskVersionConflict()
        return self._task(task)

    def get_active_task(self, user_id, session_id):
        with self._transaction() as cursor:
            session = self._locked_owned_session(cursor, session_id, user_id); task_id = session.get("active_task_id")
            if not task_id: return None
            cursor.execute("SELECT * FROM agent_design_tasks WHERE id=%s AND user_id=%s AND session_id=%s", (task_id, user_id, session_id)); row = self._fetchone(cursor)
            if row is None: raise DesignTaskScopeConflict()
        return self._task(row)

    def insert_artifact(self, user_id, session_id, task_id=None, *, artifact_type, content_json, status=ArtifactStatus.PROPOSED, parent_artifact_id=None, source_runtime_run_id=None, source_action_id=None, generation_log_id=None, origin=ArtifactOrigin.NATIVE, version_number=None):
        artifact_id, now = str(uuid.uuid4()), self._now()
        with self._transaction() as cursor:
            _session, _task, scope_type, scope_key = self._lock_scope(cursor, user_id, session_id, task_id)
            if parent_artifact_id:
                cursor.execute("SELECT * FROM agent_artifacts WHERE id=%s FOR UPDATE", (parent_artifact_id,)); parent = self._fetchone(cursor)
                if parent is None or (parent.get("user_id"), parent.get("session_id"), parent.get("scope_key"), parent.get("artifact_type")) != (user_id, session_id, scope_key, artifact_type.value): raise ArtifactParentConflict()
            if version_number is None:
                cursor.execute("SELECT COALESCE(MAX(version_number),0)+1 AS next_version FROM agent_artifacts WHERE session_id=%s AND scope_key=%s AND artifact_type=%s FOR UPDATE", (session_id, scope_key, artifact_type.value)); version_number = int((self._fetchone(cursor) or {}).get("next_version") or 1)
            cursor.execute("SELECT id FROM agent_artifacts WHERE session_id=%s AND scope_key=%s AND artifact_type=%s AND version_number=%s FOR UPDATE", (session_id, scope_key, artifact_type.value, version_number))
            if self._fetchone(cursor) is not None: raise ArtifactVersionConflict()
            cursor.execute("""INSERT INTO agent_artifacts (id,user_id,session_id,task_id,scope_type,scope_key,artifact_type,status,version_number,parent_artifact_id,source_runtime_run_id,source_action_id,content_json,content_hash,generation_log_id,origin,created_at,confirmed_at,superseded_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,NULL)""", (artifact_id,user_id,session_id,task_id,scope_type.value,scope_key,artifact_type.value,status.value,version_number,parent_artifact_id,source_runtime_run_id,source_action_id,self._json(content_json),canonical_json_hash(content_json),generation_log_id,origin.value,now))
            cursor.execute("SELECT * FROM agent_artifacts WHERE id=%s AND user_id=%s", (artifact_id,user_id)); row = self._fetchone(cursor)
        return self._artifact(row)

    def get_artifact(self, artifact_id, user_id, session_id, task_id=None):
        _scope_type, scope_key = self._scope(session_id, task_id)
        with self._transaction() as cursor:
            cursor.execute("SELECT * FROM agent_artifacts WHERE id=%s AND user_id=%s AND session_id=%s AND scope_key=%s", (artifact_id,user_id,session_id,scope_key)); row=self._fetchone(cursor)
        return self._artifact(row)

    def list_artifacts(self, user_id, session_id, task_id=None):
        _scope_type, scope_key = self._scope(session_id, task_id)
        with self._transaction() as cursor:
            self._locked_owned_session(cursor,session_id,user_id)
            if task_id: self._locked_task(cursor,task_id,user_id,session_id)
            cursor.execute("SELECT * FROM agent_artifacts WHERE user_id=%s AND session_id=%s AND scope_key=%s ORDER BY artifact_type,version_number,created_at", (user_id,session_id,scope_key)); rows=[dict(r) for r in cursor.fetchall() if isinstance(r,dict)]
        return [self._artifact(row) for row in rows]

    def get_generation_history_rows(self, user_id: str, generation_log_id: int) -> dict[str, Any]:
        """Read the owner-scoped rows needed for a safe Agent history projection.

        This is intentionally a read model.  It never treats a generation-log
        row as authority to write a Task, Artifact, or Action.
        """
        with self._transaction() as cursor:
            cursor.execute(
                """SELECT id, timestamp, image_url, title, generation_kind, response_json
                   FROM generation_logs
                   WHERE id=%s AND user_id=%s AND event_type='generate'""",
                (generation_log_id, user_id),
            )
            log = self._fetchone(cursor)
            if log is None:
                raise AgentGenerationHistoryNotFound()

            cursor.execute(
                "SELECT * FROM agent_actions WHERE generation_log_id=%s AND user_id=%s LIMIT 1",
                (generation_log_id, user_id),
            )
            action = self._fetchone(cursor)
            cursor.execute(
                """SELECT * FROM agent_artifacts
                   WHERE generation_log_id=%s AND user_id=%s AND artifact_type='generated_image'
                   ORDER BY version_number DESC, created_at DESC LIMIT 1""",
                (generation_log_id, user_id),
            )
            image_artifact = self._fetchone(cursor)

            legacy_session = None
            if action is None and image_artifact is None:
                cursor.execute(
                    "SELECT * FROM agent_sessions WHERE generation_log_id=%s AND user_id=%s LIMIT 1",
                    (generation_log_id, user_id),
                )
                legacy_session = self._fetchone(cursor)

        return {
            "log": log,
            "action": self._action(action) if action is not None else None,
            "image_artifact": self._artifact(image_artifact) if image_artifact is not None else None,
            "legacy_session": legacy_session,
        }

    def insert_action_request(self, user_id, session_id, task_id=None, *, action_type, idempotency_key, expected_task_version=None, source_runtime_run_id=None, source_artifact_ids=None, proposal_snapshot_json=None, retry_of_action_id=None):
        source_artifact_ids = list(source_artifact_ids or [])
        request_hash = canonical_json_hash({"action_type":action_type.value,"expected_task_version":expected_task_version,"source_runtime_run_id":source_runtime_run_id,"source_artifact_ids":source_artifact_ids,"proposal_snapshot_json":proposal_snapshot_json,"retry_of_action_id":retry_of_action_id})
        action_id, now = str(uuid.uuid4()), self._now()
        with self._transaction() as cursor:
            _session, task, scope_type, scope_key = self._lock_scope(cursor, user_id, session_id, task_id)
            if task is not None and expected_task_version is not None and int(task.get("version") or 0) != expected_task_version: raise DesignTaskVersionConflict()
            if task is None and expected_task_version is not None: raise DesignTaskVersionConflict()
            cursor.execute("SELECT * FROM agent_actions WHERE user_id=%s AND session_id=%s AND scope_key=%s AND action_type=%s AND idempotency_key=%s FOR UPDATE", (user_id,session_id,scope_key,action_type.value,idempotency_key)); existing=self._fetchone(cursor)
            if existing is not None:
                if existing.get("request_hash") != request_hash: raise ActionIdempotencyConflict()
                return self._action(existing), True
            if source_runtime_run_id:
                cursor.execute("SELECT id FROM agent_runtime_runs WHERE id=%s AND user_id=%s AND session_id=%s", (source_runtime_run_id,user_id,session_id))
                if self._fetchone(cursor) is None: raise ActionReferenceConflict()
            for artifact_id in source_artifact_ids:
                cursor.execute("SELECT id FROM agent_artifacts WHERE id=%s AND user_id=%s AND session_id=%s AND scope_key=%s", (artifact_id,user_id,session_id,scope_key))
                if self._fetchone(cursor) is None: raise ActionReferenceConflict()
            if retry_of_action_id:
                cursor.execute("SELECT id FROM agent_actions WHERE id=%s AND user_id=%s AND session_id=%s AND scope_key=%s", (retry_of_action_id,user_id,session_id,scope_key))
                if self._fetchone(cursor) is None: raise ActionReferenceConflict()
            cursor.execute("""INSERT INTO agent_actions (id,user_id,session_id,task_id,scope_type,scope_key,action_type,status,idempotency_key,request_hash,expected_task_version,source_runtime_run_id,source_artifact_ids_json,proposal_snapshot_json,approval_snapshot_json,result_json,error_code,error_summary,generation_log_id,retry_of_action_id,created_at,updated_at,approved_at,completed_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'requested',%s,%s,%s,%s,%s,%s,NULL,NULL,NULL,NULL,NULL,%s,%s,%s,NULL,NULL)""", (action_id,user_id,session_id,task_id,scope_type.value,scope_key,action_type.value,idempotency_key,request_hash,expected_task_version,source_runtime_run_id,self._json(source_artifact_ids),self._json(proposal_snapshot_json),retry_of_action_id,now,now))
            cursor.execute("SELECT * FROM agent_actions WHERE id=%s AND user_id=%s", (action_id,user_id)); row=self._fetchone(cursor)
        return self._action(row), False

    def get_action(self, action_id,user_id,session_id,task_id=None):
        _scope_type, scope_key = self._scope(session_id, task_id)
        with self._transaction() as cursor:
            cursor.execute("SELECT * FROM agent_actions WHERE id=%s AND user_id=%s AND session_id=%s AND scope_key=%s",(action_id,user_id,session_id,scope_key)); row=self._fetchone(cursor)
        return self._action(row)

    def get_action_any_owner(self, action_id, user_id):
        with self._transaction() as cursor:
            cursor.execute("SELECT * FROM agent_actions WHERE id=%s AND user_id=%s", (action_id, user_id)); row = self._fetchone(cursor)
        return self._action(row)

    def list_actions(self,user_id,session_id,task_id=None):
        _scope_type, scope_key = self._scope(session_id, task_id)
        with self._transaction() as cursor:
            self._locked_owned_session(cursor,session_id,user_id)
            if task_id: self._locked_task(cursor,task_id,user_id,session_id)
            cursor.execute("SELECT * FROM agent_actions WHERE user_id=%s AND session_id=%s AND scope_key=%s ORDER BY created_at,id",(user_id,session_id,scope_key)); rows=[dict(r) for r in cursor.fetchall() if isinstance(r,dict)]
        return [self._action(row) for row in rows]

    def get_runtime_run_for_action(self, user_id, session_id, run_id):
        with self._transaction() as cursor:
            self._locked_owned_session(cursor, session_id, user_id)
            cursor.execute("SELECT * FROM agent_runtime_runs WHERE id=%s AND user_id=%s AND session_id=%s", (run_id, user_id, session_id)); row = self._fetchone(cursor)
        if row is None: raise ActionReferenceConflict("Runtime proposal does not belong to this conversation.")
        value = dict(row); value["final_output_json"] = self._json_value(value.get("final_output_json"), None)
        return value

    def get_runtime_message_snapshot(self, user_id: str, session_id: str, task_id: str | None, *, limit: int = 12) -> list[dict[str, Any]]:
        """Read a bounded, owner-scoped source set for a frozen action snapshot.

        The snapshot persists message IDs only. Text is used transiently to
        construct the server-owned generation package and is never returned by
        the Action API as an internal prompt.
        """
        with self._transaction() as cursor:
            self._locked_owned_session(cursor, session_id, user_id)
            if task_id:
                self._locked_task(cursor, task_id, user_id, session_id)
                cursor.execute(
                    """SELECT id,role,content_text FROM agent_messages
                       WHERE session_id=%s AND task_id=%s
                       ORDER BY sequence_no DESC LIMIT %s""",
                    (session_id, task_id, limit),
                )
            else:
                cursor.execute(
                    """SELECT id,role,content_text FROM agent_messages
                       WHERE session_id=%s AND task_id IS NULL
                       ORDER BY sequence_no DESC LIMIT %s""",
                    (session_id, limit),
                )
            rows = [dict(row) for row in cursor.fetchall() if isinstance(row, dict)]
        return list(reversed(rows))

    def approve_action(self, user_id, session_id, task_id, action_id, *, expected_task_version, approval_idempotency_key, approval_snapshot_json):
        approval_hash, now = canonical_json_hash(approval_snapshot_json), self._now()
        with self._transaction() as cursor:
            _session, task, _scope_type, scope_key = self._lock_scope(cursor, user_id, session_id, task_id)
            if task is not None and expected_task_version is not None and int(task.get("version") or 0) != expected_task_version: raise DesignTaskVersionConflict()
            if task is None and expected_task_version is not None: raise DesignTaskVersionConflict()
            cursor.execute("SELECT * FROM agent_actions WHERE id=%s AND user_id=%s AND session_id=%s AND scope_key=%s FOR UPDATE", (action_id,user_id,session_id,scope_key)); row = self._fetchone(cursor)
            if row is None: raise ActionNotFound()
            if row.get("status") == ActionStatus.APPROVED.value:
                if row.get("approval_idempotency_key") == approval_idempotency_key and row.get("approval_hash") == approval_hash: return self._action(row), True
                raise ActionApprovalIdempotencyConflict()
            if row.get("status") != ActionStatus.REQUESTED.value: raise ActionStateConflict()
            cursor.execute("""UPDATE agent_actions SET status='approved',approval_snapshot_json=%s,approval_idempotency_key=%s,approval_hash=%s,
                approved_at=%s,updated_at=%s WHERE id=%s AND status='requested'""", (self._json(approval_snapshot_json),approval_idempotency_key,approval_hash,now,now,action_id))
            if cursor.rowcount != 1: raise ActionStateConflict()
            cursor.execute("SELECT * FROM agent_actions WHERE id=%s", (action_id,)); row = self._fetchone(cursor)
        return self._action(row), False

    def reject_action(self, user_id, session_id, task_id, action_id, *, rejection_idempotency_key, reason):
        snapshot, now = {"reason": reason} if reason else {}, self._now(); rejection_hash = canonical_json_hash(snapshot)
        with self._transaction() as cursor:
            _session, _task, _scope_type, scope_key = self._lock_scope(cursor, user_id, session_id, task_id)
            cursor.execute("SELECT * FROM agent_actions WHERE id=%s AND user_id=%s AND session_id=%s AND scope_key=%s FOR UPDATE", (action_id,user_id,session_id,scope_key)); row = self._fetchone(cursor)
            if row is None: raise ActionNotFound()
            if row.get("status") == ActionStatus.REJECTED.value:
                if row.get("rejection_idempotency_key") == rejection_idempotency_key and row.get("rejection_hash") == rejection_hash: return self._action(row), True
                raise ActionApprovalIdempotencyConflict()
            if row.get("status") != ActionStatus.REQUESTED.value: raise ActionStateConflict()
            cursor.execute("""UPDATE agent_actions SET status='rejected',rejection_idempotency_key=%s,rejection_hash=%s,rejection_reason=%s,
                rejected_at=%s,updated_at=%s WHERE id=%s AND status='requested'""", (rejection_idempotency_key,rejection_hash,reason,now,now,action_id))
            if cursor.rowcount != 1: raise ActionStateConflict()
            cursor.execute("SELECT * FROM agent_actions WHERE id=%s", (action_id,)); row = self._fetchone(cursor)
        return self._action(row), False

    def execute_approved_action(self, user_id, action_id, *, execution_idempotency_key, expected_task_version, command):
        """Atomically claim, apply, and complete one non-provider command."""
        request_hash, now = canonical_json_hash({"expected_task_version": expected_task_version, "command": command}), self._now()
        with self._transaction() as cursor:
            cursor.execute("SELECT * FROM agent_actions WHERE id=%s AND user_id=%s FOR UPDATE", (action_id, user_id)); action = self._fetchone(cursor)
            if action is None: raise ActionNotFound()
            self._locked_owned_session(cursor, action["session_id"], user_id)
            task = self._locked_task(cursor, action["task_id"], user_id, action["session_id"]) if action.get("task_id") else None
            if action.get("status") == ActionStatus.COMPLETED.value:
                return self._action(action), True
            if action.get("status") != ActionStatus.APPROVED.value: raise ActionStateConflict()
            if action.get("execution_idempotency_key"):
                if action.get("execution_idempotency_key") == execution_idempotency_key and action.get("execution_request_hash") == request_hash:
                    return self._action(action), True
                from backend.domain.agent_design_domain import ActionExecutionIdempotencyConflict
                raise ActionExecutionIdempotencyConflict()
            if task is not None and expected_task_version is not None and int(task.get("version") or 0) != expected_task_version: raise DesignTaskVersionConflict()
            if task is None and expected_task_version is not None: raise DesignTaskVersionConflict()
            cursor.execute("UPDATE agent_actions SET status='running',execution_idempotency_key=%s,execution_request_hash=%s,execution_started_at=%s,executor_version='f2',updated_at=%s WHERE id=%s AND status='approved'", (execution_idempotency_key,request_hash,now,now,action_id))
            if cursor.rowcount != 1: raise ActionStateConflict()
            created, superseded = [], []
            if command["kind"] == "archive_task":
                if task is None: raise ActionStateConflict()
                if task.get("status") == DesignTaskStatus.CLOSED.value: raise ActionStateConflict()
                cursor.execute("UPDATE agent_design_tasks SET status='closed',closed_at=%s,updated_at=%s,version=version+1 WHERE id=%s", (now,now,task["id"]))
                cursor.execute("UPDATE agent_sessions SET active_task_id=NULL,updated_at=%s WHERE id=%s AND user_id=%s AND active_task_id=%s", (now,action["session_id"],user_id,task["id"]))
            else:
                artifact_type = command["artifact_type"]
                cursor.execute("SELECT * FROM agent_artifacts WHERE user_id=%s AND session_id=%s AND scope_key=%s AND artifact_type=%s ORDER BY version_number DESC FOR UPDATE", (user_id,action["session_id"],action["scope_key"],artifact_type)); history=[dict(row) for row in cursor.fetchall() if isinstance(row,dict)]
                current = next((row for row in history if row.get("status") == ArtifactStatus.CONFIRMED.value), None)
                parent_id = command.get("parent_artifact_id") or (current or {}).get("id")
                if command.get("base_artifact_id"):
                    base = next((row for row in history if row.get("id") == command["base_artifact_id"]), None)
                    if base is None or base.get("status") != ArtifactStatus.CONFIRMED.value or (command.get("base_content_hash") and base.get("content_hash") != command["base_content_hash"]): raise ArtifactVersionConflict()
                    parent_id, current = base["id"], base
                version = (max([int(row.get("version_number") or 0) for row in history], default=0) + 1)
                if current is not None:
                    cursor.execute("UPDATE agent_artifacts SET status='superseded',superseded_at=%s WHERE id=%s AND status='confirmed'", (now,current["id"]))
                    superseded.append(current["id"])
                artifact_id = str(uuid.uuid4()); content = command["content_json"]
                cursor.execute("""INSERT INTO agent_artifacts (id,user_id,session_id,task_id,scope_type,scope_key,artifact_type,status,version_number,parent_artifact_id,source_runtime_run_id,source_action_id,content_json,content_hash,generation_log_id,origin,created_at,confirmed_at,superseded_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,'confirmed',%s,%s,%s,%s,%s,%s,NULL,'native',%s,%s,NULL)""", (artifact_id,user_id,action["session_id"],action.get("task_id"),action["scope_type"],action["scope_key"],artifact_type,version,parent_id,action.get("source_runtime_run_id"),action_id,self._json(content),canonical_json_hash(content),now,now))
                created.append(artifact_id)
                if task is not None: cursor.execute("UPDATE agent_design_tasks SET updated_at=%s,version=version+1 WHERE id=%s", (now,task["id"]))
            if task is not None:
                cursor.execute("SELECT version,status,closed_at,updated_at FROM agent_design_tasks WHERE id=%s", (task["id"],)); final_task=self._fetchone(cursor)
                task_version, task_status = int(final_task["version"]), final_task["status"]
            else:
                task_version, task_status = None, None
            result={"created_artifact_ids":created,"superseded_artifact_ids":superseded,"task_version":task_version,"task_status":task_status}
            cursor.execute("UPDATE agent_actions SET status='completed',result_json=%s,execution_result_hash=%s,completed_at=%s,updated_at=%s WHERE id=%s AND status='running'", (self._json(result),canonical_json_hash(result),now,now,action_id))
            if cursor.rowcount != 1: raise ActionStateConflict()
            cursor.execute("SELECT * FROM agent_actions WHERE id=%s", (action_id,)); final_action=self._fetchone(cursor)
        return self._action(final_action), False

    def mark_action_failed(self, user_id, action_id, code, summary):
        now = self._now()
        with self._transaction() as cursor:
            cursor.execute("UPDATE agent_actions SET status='failed',error_code=%s,error_summary=%s,updated_at=%s WHERE id=%s AND user_id=%s AND status='running'", (code,summary[:1000],now,action_id,user_id))

    def claim_image_action(self, user_id, action_id, *, idempotency_key, expected_task_version):
        now = self._now()
        request_hash=canonical_json_hash({"expected_task_version":expected_task_version,"action_id":action_id})
        with self._transaction() as cursor:
            cursor.execute("SELECT * FROM agent_actions WHERE id=%s AND user_id=%s FOR UPDATE", (action_id,user_id)); action=self._fetchone(cursor)
            if action is None: raise ActionNotFound()
            task=self._locked_task(cursor,action["task_id"],user_id,action["session_id"]) if action.get("task_id") else None
            if action.get("status") == ActionStatus.COMPLETED.value:
                if action.get("execution_idempotency_key") == idempotency_key and action.get("execution_request_hash") != request_hash:
                    from backend.domain.agent_design_domain import ActionExecutionIdempotencyConflict
                    raise ActionExecutionIdempotencyConflict()
                return self._action(action), True
            if action.get("status") == ActionStatus.RUNNING.value:
                from backend.domain.agent_design_domain import ActionStateConflict
                raise ActionStateConflict("ACTION_EXECUTION_RECOVERY_REQUIRED")
            if action.get("status") != ActionStatus.APPROVED.value: raise ActionStateConflict()
            if task is not None and expected_task_version is not None and int(task.get("version") or 0) != expected_task_version: raise DesignTaskVersionConflict()
            if task is None and expected_task_version is not None: raise DesignTaskVersionConflict()
            cursor.execute("UPDATE agent_actions SET status='running',execution_idempotency_key=%s,execution_request_hash=%s,execution_started_at=%s,executor_version='f3',external_outcome_status='claimed',updated_at=%s WHERE id=%s AND status='approved'", (idempotency_key,request_hash,now,now,action_id))
            cursor.execute("SELECT * FROM agent_actions WHERE id=%s",(action_id,)); action=self._fetchone(cursor)
        return self._action(action), False

    def mark_image_provider_succeeded(self, user_id, action_id, provider_request_id):
        with self._transaction() as cursor:
            cursor.execute("UPDATE agent_actions SET external_outcome_status='provider_succeeded',provider_request_id=%s,updated_at=%s WHERE id=%s AND user_id=%s AND status='running'", (provider_request_id,self._now(),action_id,user_id))

    def complete_image_action(self, user_id, action_id, result):
        now=self._now()
        with self._transaction() as cursor:
            cursor.execute("SELECT * FROM agent_actions WHERE id=%s AND user_id=%s FOR UPDATE",(action_id,user_id)); action=self._fetchone(cursor)
            if action is None: raise ActionNotFound()
            if action.get("status") == ActionStatus.COMPLETED.value: return self._action(action), True
            if action.get("status") != ActionStatus.RUNNING.value: raise ActionStateConflict()
            cursor.execute("""INSERT INTO generation_logs (user_id,event_type,timestamp,prompt,style,image_url,title,content,generation_time,content_length,user_rating,download_count,user_age,user_gender,login_time,data_origin,generation_kind,prompt_template_version,brief_json,response_json)
                VALUES (%s,'generate',%s,%s,'agent-action',%s,'Approved image action','Approved task-scoped image',0,0,NULL,0,NULL,NULL,NULL,'production','agent_action_image','agent-action-f3',NULL,%s)""", (user_id,now,"approved image snapshot",result["image_url"],self._json({"action_id":action_id,"source_type":result["source_type"],"snapshot_hash":result["snapshot_hash"]})))
            log_id=int(cursor.lastrowid)
            cursor.execute("SELECT COALESCE(MAX(version_number),0)+1 AS n FROM agent_artifacts WHERE session_id=%s AND scope_key=%s AND artifact_type='generated_image' FOR UPDATE",(action["session_id"],action["scope_key"])); version=int((self._fetchone(cursor) or {}).get("n") or 1)
            artifact_id=str(uuid.uuid4()); content={"image_url":result["image_url"],"presentation_mode":result["presentation_mode"],"generation_kind":result["source_type"],"provider_request_id":result.get("provider_request_id"),"source_type":result["source_type"],"snapshot_hash":result["snapshot_hash"]}
            cursor.execute("""INSERT INTO agent_artifacts (id,user_id,session_id,task_id,scope_type,scope_key,artifact_type,status,version_number,parent_artifact_id,source_runtime_run_id,source_action_id,content_json,content_hash,generation_log_id,origin,created_at,confirmed_at,superseded_at)
                VALUES (%s,%s,%s,%s,%s,%s,'generated_image','confirmed',%s,%s,%s,%s,%s,%s,%s,'native',%s,%s,NULL)""",(artifact_id,user_id,action["session_id"],action.get("task_id"),action["scope_type"],action["scope_key"],version,result.get("parent_image_artifact_id"),action.get("source_runtime_run_id"),action_id,self._json(content),canonical_json_hash(content),log_id,now,now))
            outcome={"created_artifact_ids":[artifact_id],"superseded_artifact_ids":[],"generation_log_id":log_id,"task_version":None}
            cursor.execute("UPDATE agent_actions SET status='completed',generation_log_id=%s,result_json=%s,execution_result_hash=%s,external_outcome_status='completed',completed_at=%s,updated_at=%s WHERE id=%s",(log_id,self._json(outcome),canonical_json_hash(outcome),now,now,action_id))
            cursor.execute("SELECT * FROM agent_actions WHERE id=%s",(action_id,)); action=self._fetchone(cursor)
        return self._action(action),False
