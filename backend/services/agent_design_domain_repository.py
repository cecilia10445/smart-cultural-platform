"""Owner-scoped, non-executing persistence primitives for the F0 design graph."""
from __future__ import annotations

import json
import uuid
from typing import Any

from backend.domain.agent_design_domain import (
    ActionApprovalIdempotencyConflict, ActionIdempotencyConflict, ActionNotFound, ActionRecord, ActionReferenceConflict, ActionStateConflict, ActionStatus, ActionType,
    ArtifactNotFound, ArtifactOrigin, ArtifactParentConflict, ArtifactRecord, ArtifactStatus, ArtifactType, ArtifactVersionConflict,
    DesignTaskNotFound, DesignTaskOrigin, DesignTaskRecord, DesignTaskScopeConflict, DesignTaskStatus, DesignTaskVersionConflict,
    ConversationProjection, ConversationStatus, canonical_json_hash,
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

    def get_conversation(self, user_id, session_id):
        with self._transaction() as cursor:
            cursor.execute("SELECT * FROM agent_sessions WHERE id=%s AND user_id=%s", (session_id, user_id)); row = self._fetchone(cursor)
        if row is None:
            from backend.domain.agent_dialogue import AgentSessionNotFound
            raise AgentSessionNotFound()
        value = dict(row)
        value["conversation_status"] = value.get("conversation_status") or ConversationStatus.ACTIVE.value
        value["legacy_session_status"] = value.get("status")
        return ConversationProjection.model_validate(value)

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

    def insert_artifact(self, user_id, session_id, task_id, *, artifact_type, content_json, status=ArtifactStatus.PROPOSED, parent_artifact_id=None, source_runtime_run_id=None, source_action_id=None, generation_log_id=None, origin=ArtifactOrigin.NATIVE, version_number=None):
        artifact_id, now = str(uuid.uuid4()), self._now()
        with self._transaction() as cursor:
            self._locked_owned_session(cursor, session_id, user_id); self._locked_task(cursor, task_id, user_id, session_id)
            if parent_artifact_id:
                cursor.execute("SELECT * FROM agent_artifacts WHERE id=%s FOR UPDATE", (parent_artifact_id,)); parent = self._fetchone(cursor)
                if parent is None or (parent.get("user_id"), parent.get("session_id"), parent.get("task_id"), parent.get("artifact_type")) != (user_id, session_id, task_id, artifact_type.value): raise ArtifactParentConflict()
            if version_number is None:
                cursor.execute("SELECT COALESCE(MAX(version_number),0)+1 AS next_version FROM agent_artifacts WHERE task_id=%s AND artifact_type=%s", (task_id, artifact_type.value)); version_number = int((self._fetchone(cursor) or {}).get("next_version") or 1)
            cursor.execute("SELECT id FROM agent_artifacts WHERE task_id=%s AND artifact_type=%s AND version_number=%s FOR UPDATE", (task_id, artifact_type.value, version_number))
            if self._fetchone(cursor) is not None: raise ArtifactVersionConflict()
            cursor.execute("""INSERT INTO agent_artifacts (id,user_id,session_id,task_id,artifact_type,status,version_number,parent_artifact_id,source_runtime_run_id,source_action_id,content_json,content_hash,generation_log_id,origin,created_at,confirmed_at,superseded_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,NULL)""", (artifact_id,user_id,session_id,task_id,artifact_type.value,status.value,version_number,parent_artifact_id,source_runtime_run_id,source_action_id,self._json(content_json),canonical_json_hash(content_json),generation_log_id,origin.value,now))
            cursor.execute("SELECT * FROM agent_artifacts WHERE id=%s AND user_id=%s", (artifact_id,user_id)); row = self._fetchone(cursor)
        return self._artifact(row)

    def get_artifact(self, artifact_id, user_id, session_id, task_id):
        with self._transaction() as cursor:
            cursor.execute("SELECT * FROM agent_artifacts WHERE id=%s AND user_id=%s AND session_id=%s AND task_id=%s", (artifact_id,user_id,session_id,task_id)); row=self._fetchone(cursor)
        return self._artifact(row)

    def list_artifacts(self, user_id, session_id, task_id):
        with self._transaction() as cursor:
            self._locked_task(cursor,task_id,user_id,session_id); cursor.execute("SELECT * FROM agent_artifacts WHERE user_id=%s AND session_id=%s AND task_id=%s ORDER BY artifact_type,version_number,created_at", (user_id,session_id,task_id)); rows=[dict(r) for r in cursor.fetchall() if isinstance(r,dict)]
        return [self._artifact(row) for row in rows]

    def insert_action_request(self, user_id, session_id, task_id, *, action_type, idempotency_key, expected_task_version=None, source_runtime_run_id=None, source_artifact_ids=None, proposal_snapshot_json=None, retry_of_action_id=None):
        source_artifact_ids = list(source_artifact_ids or [])
        request_hash = canonical_json_hash({"action_type":action_type.value,"expected_task_version":expected_task_version,"source_runtime_run_id":source_runtime_run_id,"source_artifact_ids":source_artifact_ids,"proposal_snapshot_json":proposal_snapshot_json,"retry_of_action_id":retry_of_action_id})
        action_id, now = str(uuid.uuid4()), self._now()
        with self._transaction() as cursor:
            self._locked_owned_session(cursor,session_id,user_id); task=self._locked_task(cursor,task_id,user_id,session_id)
            if expected_task_version is not None and int(task.get("version") or 0) != expected_task_version: raise DesignTaskVersionConflict()
            cursor.execute("SELECT * FROM agent_actions WHERE user_id=%s AND task_id=%s AND action_type=%s AND idempotency_key=%s FOR UPDATE", (user_id,task_id,action_type.value,idempotency_key)); existing=self._fetchone(cursor)
            if existing is not None:
                if existing.get("request_hash") != request_hash: raise ActionIdempotencyConflict()
                return self._action(existing), True
            if source_runtime_run_id:
                cursor.execute("SELECT id FROM agent_runtime_runs WHERE id=%s AND user_id=%s AND session_id=%s", (source_runtime_run_id,user_id,session_id))
                if self._fetchone(cursor) is None: raise ActionReferenceConflict()
            for artifact_id in source_artifact_ids:
                cursor.execute("SELECT id FROM agent_artifacts WHERE id=%s AND user_id=%s AND session_id=%s AND task_id=%s", (artifact_id,user_id,session_id,task_id))
                if self._fetchone(cursor) is None: raise ActionReferenceConflict()
            if retry_of_action_id:
                cursor.execute("SELECT id FROM agent_actions WHERE id=%s AND user_id=%s AND session_id=%s AND task_id=%s", (retry_of_action_id,user_id,session_id,task_id))
                if self._fetchone(cursor) is None: raise ActionReferenceConflict()
            cursor.execute("""INSERT INTO agent_actions (id,user_id,session_id,task_id,action_type,status,idempotency_key,request_hash,expected_task_version,source_runtime_run_id,source_artifact_ids_json,proposal_snapshot_json,approval_snapshot_json,result_json,error_code,error_summary,generation_log_id,retry_of_action_id,created_at,updated_at,approved_at,completed_at)
                VALUES (%s,%s,%s,%s,%s,'requested',%s,%s,%s,%s,%s,%s,NULL,NULL,NULL,NULL,NULL,%s,%s,%s,NULL,NULL)""", (action_id,user_id,session_id,task_id,action_type.value,idempotency_key,request_hash,expected_task_version,source_runtime_run_id,self._json(source_artifact_ids),self._json(proposal_snapshot_json),retry_of_action_id,now,now))
            cursor.execute("SELECT * FROM agent_actions WHERE id=%s AND user_id=%s", (action_id,user_id)); row=self._fetchone(cursor)
        return self._action(row), False

    def get_action(self, action_id,user_id,session_id,task_id):
        with self._transaction() as cursor:
            cursor.execute("SELECT * FROM agent_actions WHERE id=%s AND user_id=%s AND session_id=%s AND task_id=%s",(action_id,user_id,session_id,task_id)); row=self._fetchone(cursor)
        return self._action(row)

    def get_action_any_owner(self, action_id, user_id):
        with self._transaction() as cursor:
            cursor.execute("SELECT * FROM agent_actions WHERE id=%s AND user_id=%s", (action_id, user_id)); row = self._fetchone(cursor)
        return self._action(row)

    def list_actions(self,user_id,session_id,task_id):
        with self._transaction() as cursor:
            self._locked_task(cursor,task_id,user_id,session_id); cursor.execute("SELECT * FROM agent_actions WHERE user_id=%s AND session_id=%s AND task_id=%s ORDER BY created_at,id",(user_id,session_id,task_id)); rows=[dict(r) for r in cursor.fetchall() if isinstance(r,dict)]
        return [self._action(row) for row in rows]

    def get_runtime_run_for_action(self, user_id, session_id, run_id):
        with self._transaction() as cursor:
            self._locked_owned_session(cursor, session_id, user_id)
            cursor.execute("SELECT * FROM agent_runtime_runs WHERE id=%s AND user_id=%s AND session_id=%s", (run_id, user_id, session_id)); row = self._fetchone(cursor)
        if row is None: raise ActionReferenceConflict("Runtime proposal does not belong to this conversation.")
        value = dict(row); value["final_output_json"] = self._json_value(value.get("final_output_json"), None)
        return value

    def approve_action(self, user_id, session_id, task_id, action_id, *, expected_task_version, approval_idempotency_key, approval_snapshot_json):
        approval_hash, now = canonical_json_hash(approval_snapshot_json), self._now()
        with self._transaction() as cursor:
            self._locked_owned_session(cursor, session_id, user_id); task = self._locked_task(cursor, task_id, user_id, session_id)
            if expected_task_version is not None and int(task.get("version") or 0) != expected_task_version: raise DesignTaskVersionConflict()
            cursor.execute("SELECT * FROM agent_actions WHERE id=%s AND user_id=%s AND session_id=%s AND task_id=%s FOR UPDATE", (action_id,user_id,session_id,task_id)); row = self._fetchone(cursor)
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
            self._locked_owned_session(cursor, session_id, user_id); self._locked_task(cursor, task_id, user_id, session_id)
            cursor.execute("SELECT * FROM agent_actions WHERE id=%s AND user_id=%s AND session_id=%s AND task_id=%s FOR UPDATE", (action_id,user_id,session_id,task_id)); row = self._fetchone(cursor)
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
