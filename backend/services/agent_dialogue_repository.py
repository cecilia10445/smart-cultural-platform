"""Short-transaction persistence for agent dialogue sessions.

The repository deliberately uses the project's pooled PyMySQL boundary rather
than introducing an ORM Session.  It never exposes rows as HTTP responses.
"""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator

try:
    import pymysql
except ImportError:  # pragma: no cover - production dependency is required
    pymysql = None

from backend.domain.agent_dialogue import (
    AgentPersistenceUnavailable,
    AgentSessionNotFound,
    AgentSessionStateConflict,
    AgentSessionVersionConflict,
    AgentSessionStatus,
)


class AgentDialogueRepository:
    """Repository for the three Agent dialogue tables only."""

    def __init__(self, mysql_service):
        self.mysql_service = mysql_service

    @contextmanager
    def _transaction(self) -> Iterator[Any]:
        connection = None
        try:
            if pymysql is None:
                raise RuntimeError("PyMySQL is unavailable")
            connection = self.mysql_service._borrow_connection()
            begin = getattr(connection, "begin", None)
            if callable(begin):
                begin()
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                yield cursor
            connection.commit()
        except (AgentSessionNotFound, AgentSessionStateConflict, AgentSessionVersionConflict):
            if connection:
                connection.rollback()
            raise
        except Exception as error:
            if connection:
                try:
                    connection.rollback()
                except Exception:
                    pass
            raise AgentPersistenceUnavailable() from error
        finally:
            if connection:
                connection.close()

    @staticmethod
    def _now() -> datetime:
        return datetime.now()

    @staticmethod
    def _json(value: Any) -> str | None:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")) if value is not None else None

    @staticmethod
    def _fetchone(cursor) -> dict[str, Any] | None:
        row = cursor.fetchone()
        return dict(row) if isinstance(row, dict) else None

    def _locked_owned_session(self, cursor, session_id: str, user_id: str) -> dict[str, Any]:
        cursor.execute(
            "SELECT * FROM agent_sessions WHERE id=%s AND user_id=%s FOR UPDATE",
            (session_id, user_id),
        )
        row = self._fetchone(cursor)
        if row is None:
            # Owner scope intentionally returns the same 404 for absent and foreign rows.
            raise AgentSessionNotFound()
        return row

    @staticmethod
    def _check_expected(row: dict[str, Any], expected_status: AgentSessionStatus | None, expected_version: int | None) -> None:
        if expected_status is not None and row.get("status") != expected_status.value:
            raise AgentSessionStateConflict()
        if expected_version is not None and int(row.get("version") or 0) != expected_version:
            raise AgentSessionVersionConflict()

    def create_session(self, user_id: str) -> dict[str, Any]:
        session_id, now = str(uuid.uuid4()), self._now()
        with self._transaction() as cursor:
            cursor.execute(
                """INSERT INTO agent_sessions
                (id,user_id,status,current_stage,text_revision_count,version,created_at,updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (session_id, user_id, AgentSessionStatus.CREATED.value, AgentSessionStatus.CREATED.value, 0, 1, now, now),
            )
            cursor.execute("SELECT * FROM agent_sessions WHERE id=%s AND user_id=%s", (session_id, user_id))
            row = self._fetchone(cursor)
        if row is None:  # defensive; a successful INSERT must be visible in this transaction
            raise AgentPersistenceUnavailable()
        return row

    def get_session(self, session_id: str, user_id: str) -> dict[str, Any]:
        with self._transaction() as cursor:
            cursor.execute("SELECT * FROM agent_sessions WHERE id=%s AND user_id=%s", (session_id, user_id))
            row = self._fetchone(cursor)
        if row is None:
            raise AgentSessionNotFound()
        return row

    def list_messages(self, session_id: str, user_id: str) -> list[dict[str, Any]]:
        with self._transaction() as cursor:
            self._locked_owned_session(cursor, session_id, user_id)
            cursor.execute("SELECT * FROM agent_messages WHERE session_id=%s ORDER BY sequence_no ASC", (session_id,))
            rows = cursor.fetchall()
        return [dict(row) for row in rows if isinstance(row, dict)]

    def list_steps(self, session_id: str, user_id: str) -> list[dict[str, Any]]:
        with self._transaction() as cursor:
            self._locked_owned_session(cursor, session_id, user_id)
            cursor.execute("SELECT * FROM agent_steps WHERE session_id=%s ORDER BY ordinal ASC", (session_id,))
            rows = cursor.fetchall()
        return [dict(row) for row in rows if isinstance(row, dict)]

    def has_client_turn(self, session_id: str, user_id: str, client_turn_id: str) -> bool:
        """Owner-scoped idempotency check used before rejecting a fifth revision."""
        with self._transaction() as cursor:
            self._locked_owned_session(cursor, session_id, user_id)
            cursor.execute(
                "SELECT id FROM agent_messages WHERE session_id=%s AND client_turn_id=%s LIMIT 1",
                (session_id, client_turn_id),
            )
            return self._fetchone(cursor) is not None

    def get_detail_rows(self, session_id: str, user_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        """Read an owner-scoped snapshot. Rows remain internal to the service."""
        with self._transaction() as cursor:
            session = self._locked_owned_session(cursor, session_id, user_id)
            cursor.execute("SELECT * FROM agent_messages WHERE session_id=%s ORDER BY sequence_no ASC", (session_id,))
            messages = [dict(row) for row in cursor.fetchall() if isinstance(row, dict)]
            cursor.execute("SELECT * FROM agent_steps WHERE session_id=%s ORDER BY ordinal ASC", (session_id,))
            steps = [dict(row) for row in cursor.fetchall() if isinstance(row, dict)]
        return session, messages, steps

    def append_user_message(
        self, session_id: str, user_id: str, text: str, client_turn_id: str,
        expected_status: AgentSessionStatus | None, expected_version: int | None,
    ) -> tuple[dict[str, Any], bool]:
        """Append one user message; duplicate turn IDs return the current snapshot."""
        now = self._now()
        with self._transaction() as cursor:
            session = self._locked_owned_session(cursor, session_id, user_id)
            cursor.execute(
                "SELECT id FROM agent_messages WHERE session_id=%s AND client_turn_id=%s LIMIT 1",
                (session_id, client_turn_id),
            )
            if self._fetchone(cursor) is not None:
                return session, True
            self._check_expected(session, expected_status, expected_version)
            cursor.execute("SELECT COALESCE(MAX(sequence_no), 0) + 1 AS next_sequence FROM agent_messages WHERE session_id=%s", (session_id,))
            next_sequence = int((self._fetchone(cursor) or {}).get("next_sequence") or 1)
            cursor.execute(
                """INSERT INTO agent_messages
                (id,session_id,sequence_no,role,message_type,content_text,content_json,client_turn_id,decision_id,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (str(uuid.uuid4()), session_id, next_sequence, "user", "request", text, None, client_turn_id, None, now),
            )
            # Round one may only begin the extraction stage; no model/Brief work occurs.
            if session.get("status") == AgentSessionStatus.CREATED.value:
                cursor.execute(
                    """UPDATE agent_sessions SET status=%s,current_stage=%s,version=version+1,updated_at=%s
                    WHERE id=%s AND user_id=%s AND version=%s""",
                    (AgentSessionStatus.EXTRACTING_BRIEF.value, AgentSessionStatus.EXTRACTING_BRIEF.value, now, session_id, user_id, session["version"]),
                )
                if cursor.rowcount != 1:
                    raise AgentSessionVersionConflict()
                session["status"] = AgentSessionStatus.EXTRACTING_BRIEF.value
                session["current_stage"] = AgentSessionStatus.EXTRACTING_BRIEF.value
                session["version"] = int(session["version"]) + 1
                session["updated_at"] = now
        return session, False

    def append_step(
        self, session_id: str, user_id: str, stage: str, status: str, *, tool_name: str | None = None,
        skill_id: str | None = None, skill_version: str | None = None, input_summary: dict[str, Any] | None = None,
        output_summary: dict[str, Any] | None = None, tool_result_summary: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None, error_code: str | None = None, started_at: datetime | None = None,
        finished_at: datetime | None = None, latency_ms: int | None = None, expected_version: int | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._transaction() as cursor:
            session = self._locked_owned_session(cursor, session_id, user_id)
            self._check_expected(session, None, expected_version)
            cursor.execute("SELECT COALESCE(MAX(ordinal), 0) + 1 AS next_ordinal FROM agent_steps WHERE session_id=%s", (session_id,))
            ordinal = int((self._fetchone(cursor) or {}).get("next_ordinal") or 1)
            step_id = str(uuid.uuid4())
            cursor.execute(
                """INSERT INTO agent_steps
                (id,session_id,ordinal,stage,status,tool_name,skill_id,skill_version,input_summary_json,output_summary_json,
                 tool_result_summary_json,error_json,error_code,started_at,finished_at,latency_ms,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (step_id, session_id, ordinal, stage, status, tool_name, skill_id, skill_version, self._json(input_summary),
                 self._json(output_summary), self._json(tool_result_summary), self._json(error), error_code,
                 started_at, finished_at, latency_ms, now),
            )
            cursor.execute("SELECT * FROM agent_steps WHERE id=%s", (step_id,))
            row = self._fetchone(cursor)
        if row is None:
            raise AgentPersistenceUnavailable()
        return row

    def finish_brief(self, session_id: str, user_id: str, *, brief: dict[str, Any], summary: str, step_id: str) -> None:
        """Persist only normalized Brief and visible summary after the model call."""
        now = self._now()
        with self._transaction() as cursor:
            session = self._locked_owned_session(cursor, session_id, user_id)
            cursor.execute("SELECT COALESCE(MAX(sequence_no), 0) + 1 AS next_sequence FROM agent_messages WHERE session_id=%s", (session_id,))
            sequence = int((self._fetchone(cursor) or {}).get("next_sequence") or 1)
            cursor.execute(
                """INSERT INTO agent_messages (id,session_id,sequence_no,role,message_type,content_text,content_json,created_at)
                VALUES (%s,%s,%s,'assistant','brief_summary',%s,NULL,%s)""",
                (str(uuid.uuid4()), session_id, sequence, summary, now),
            )
            cursor.execute(
                """UPDATE agent_steps SET status='completed',output_summary_json=%s,finished_at=%s
                WHERE id=%s AND session_id=%s""", (self._json({"summary": "Brief proposal ready"}), now, step_id, session_id)
            )
            cursor.execute(
                """UPDATE agent_sessions SET brief_json=%s,status=%s,current_stage=%s,version=version+1,updated_at=%s
                WHERE id=%s AND user_id=%s AND version=%s""",
                (self._json(brief), AgentSessionStatus.WAITING_BRIEF_CONFIRMATION.value,
                 AgentSessionStatus.WAITING_BRIEF_CONFIRMATION.value, now, session_id, user_id, session["version"]),
            )
            if cursor.rowcount != 1:
                raise AgentSessionVersionConflict()

    def fail_step(self, session_id: str, user_id: str, step_id: str, error: dict[str, Any]) -> None:
        with self._transaction() as cursor:
            self._locked_owned_session(cursor, session_id, user_id)
            cursor.execute("UPDATE agent_steps SET status='failed',error_json=%s,error_code=%s,finished_at=%s WHERE id=%s AND session_id=%s",
                           (self._json(error), error.get("code"), self._now(), step_id, session_id))

    def finish_step(
        self, session_id: str, user_id: str, step_id: str, output_summary: dict[str, Any],
        tool_result_summary: dict[str, Any] | None = None,
    ) -> None:
        with self._transaction() as cursor:
            self._locked_owned_session(cursor, session_id, user_id)
            cursor.execute(
                """UPDATE agent_steps SET status='completed',output_summary_json=%s,tool_result_summary_json=%s,finished_at=%s
                WHERE id=%s AND session_id=%s""",
                (self._json(output_summary), self._json(tool_result_summary), self._now(), step_id, session_id),
            )

    def finish_product_text(
        self, session_id: str, user_id: str, *, draft: dict[str, Any], summary: str,
        step_id: str, is_revision: bool,
    ) -> None:
        """Store a validated draft and visible summary after the model request ends."""
        now = self._now()
        with self._transaction() as cursor:
            session = self._locked_owned_session(cursor, session_id, user_id)
            if session.get("status") != AgentSessionStatus.GENERATING_PRODUCT_TEXT.value:
                raise AgentSessionStateConflict()
            cursor.execute("SELECT COALESCE(MAX(sequence_no), 0) + 1 AS next_sequence FROM agent_messages WHERE session_id=%s", (session_id,))
            sequence = int((self._fetchone(cursor) or {}).get("next_sequence") or 1)
            cursor.execute(
                """INSERT INTO agent_messages (id,session_id,sequence_no,role,message_type,content_text,content_json,created_at)
                VALUES (%s,%s,%s,'assistant','product_design',%s,NULL,%s)""",
                (str(uuid.uuid4()), session_id, sequence, summary, now),
            )
            cursor.execute(
                """UPDATE agent_steps SET status='completed',output_summary_json=%s,finished_at=%s
                WHERE id=%s AND session_id=%s""",
                (self._json({"summary": "Product design text ready"}), now, step_id, session_id),
            )
            cursor.execute(
                """UPDATE agent_sessions SET confirmed_text_json=%s,text_revision_count=text_revision_count+%s,
                status=%s,current_stage=%s,error_json=NULL,error_code=NULL,failure_stage=NULL,version=version+1,updated_at=%s
                WHERE id=%s AND user_id=%s AND version=%s""",
                (self._json(draft), 1 if is_revision else 0, AgentSessionStatus.WAITING_TEXT_FEEDBACK.value,
                 AgentSessionStatus.WAITING_TEXT_FEEDBACK.value, now, session_id, user_id, session["version"]),
            )
            if cursor.rowcount != 1:
                raise AgentSessionVersionConflict()

    def return_to_text_feedback(self, session_id: str, user_id: str, error: dict[str, Any]) -> None:
        """Keep the last valid draft available when a revision model call fails."""
        now = self._now()
        with self._transaction() as cursor:
            session = self._locked_owned_session(cursor, session_id, user_id)
            if session.get("status") != AgentSessionStatus.GENERATING_PRODUCT_TEXT.value:
                raise AgentSessionStateConflict()
            cursor.execute(
                """UPDATE agent_sessions SET status=%s,current_stage=%s,error_json=%s,error_code=%s,
                failure_stage=%s,version=version+1,updated_at=%s WHERE id=%s AND user_id=%s AND version=%s""",
                (AgentSessionStatus.WAITING_TEXT_FEEDBACK.value, AgentSessionStatus.WAITING_TEXT_FEEDBACK.value,
                 self._json(error), error.get("code"), "generating_product_text", now, session_id, user_id, session["version"]),
            )
            if cursor.rowcount != 1:
                raise AgentSessionVersionConflict()

    def transition(
        self, session_id: str, user_id: str, target: AgentSessionStatus,
        expected_status: AgentSessionStatus | None, expected_version: int | None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._transaction() as cursor:
            session = self._locked_owned_session(cursor, session_id, user_id)
            self._check_expected(session, expected_status, expected_version)
            cursor.execute(
                """UPDATE agent_sessions SET status=%s,current_stage=%s,version=version+1,updated_at=%s,
                completed_at=CASE WHEN %s='completed' THEN %s ELSE completed_at END
                WHERE id=%s AND user_id=%s AND version=%s""",
                (target.value, target.value, now, target.value, now, session_id, user_id, session["version"]),
            )
            if cursor.rowcount != 1:
                raise AgentSessionVersionConflict()
            session.update(status=target.value, current_stage=target.value, version=int(session["version"]) + 1, updated_at=now)
            if target is AgentSessionStatus.COMPLETED:
                session["completed_at"] = now
        return session

    def mark_failed(
        self, session_id: str, user_id: str, *, error_code: str, error: dict[str, Any],
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._transaction() as cursor:
            session = self._locked_owned_session(cursor, session_id, user_id)
            self._check_expected(session, None, expected_version)
            cursor.execute(
                """UPDATE agent_sessions SET status='failed',failure_stage=%s,error_code=%s,error_json=%s,
                version=version+1,updated_at=%s WHERE id=%s AND user_id=%s AND version=%s""",
                (session.get("current_stage"), error_code, self._json(error), now, session_id, user_id, session["version"]),
            )
            if cursor.rowcount != 1:
                raise AgentSessionVersionConflict()
            session.update(status=AgentSessionStatus.FAILED.value, failure_stage=session.get("current_stage"), error_code=error_code,
                           error_json=self._json(error), version=int(session["version"]) + 1, updated_at=now)
        return session

    def find_decision_receipt(self, session_id: str, user_id: str, decision_id: str) -> dict[str, Any] | None:
        with self._transaction() as cursor:
            self._locked_owned_session(cursor, session_id, user_id)
            cursor.execute("SELECT * FROM agent_messages WHERE session_id=%s AND decision_id=%s LIMIT 1", (session_id, decision_id))
            return self._fetchone(cursor)

    def record_unsupported_decision(
        self, session_id: str, user_id: str, decision_id: str, decision: str,
        expected_status: AgentSessionStatus, expected_version: int | None,
    ) -> bool:
        """Persist one auditable receipt without executing a product decision.

        Returning ``True`` means the idempotency receipt pre-existed.  The
        service still returns the same stable not-supported business error for
        both the original submission and any replay.
        """
        now = self._now()
        with self._transaction() as cursor:
            session = self._locked_owned_session(cursor, session_id, user_id)
            cursor.execute("SELECT id FROM agent_messages WHERE session_id=%s AND decision_id=%s LIMIT 1", (session_id, decision_id))
            if self._fetchone(cursor) is not None:
                return True
            self._check_expected(session, expected_status, expected_version)
            cursor.execute("SELECT COALESCE(MAX(sequence_no), 0) + 1 AS next_sequence FROM agent_messages WHERE session_id=%s", (session_id,))
            next_sequence = int((self._fetchone(cursor) or {}).get("next_sequence") or 1)
            cursor.execute(
                """INSERT INTO agent_messages
                (id,session_id,sequence_no,role,message_type,content_text,content_json,client_turn_id,decision_id,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (str(uuid.uuid4()), session_id, next_sequence, "system", "decision_receipt",
                 "Decision received; no decision action is enabled in this implementation round.",
                 self._json({"decision": decision, "outcome": "not_supported"}), None, decision_id, now),
            )
        return False

    def confirm_brief(self, session_id: str, user_id: str, decision_id: str, expected_version: int | None) -> bool:
        now = self._now()
        with self._transaction() as cursor:
            session = self._locked_owned_session(cursor, session_id, user_id)
            cursor.execute("SELECT id FROM agent_messages WHERE session_id=%s AND decision_id=%s LIMIT 1", (session_id, decision_id))
            if self._fetchone(cursor) is not None:
                return True
            self._check_expected(session, AgentSessionStatus.WAITING_BRIEF_CONFIRMATION, expected_version)
            if not session.get("brief_json"):
                raise AgentSessionStateConflict()
            cursor.execute("SELECT COALESCE(MAX(sequence_no), 0) + 1 AS next_sequence FROM agent_messages WHERE session_id=%s", (session_id,))
            sequence = int((self._fetchone(cursor) or {}).get("next_sequence") or 1)
            cursor.execute("""INSERT INTO agent_messages (id,session_id,sequence_no,role,message_type,content_text,content_json,decision_id,created_at)
                VALUES (%s,%s,%s,'assistant','decision_receipt',%s,NULL,%s,%s)""",
                (str(uuid.uuid4()), session_id, sequence, "需求方案已确认，下一步将生成产品设计文本。", decision_id, now))
            cursor.execute("UPDATE agent_sessions SET status=%s,current_stage=%s,version=version+1,updated_at=%s WHERE id=%s AND user_id=%s AND version=%s",
                           (AgentSessionStatus.GENERATING_PRODUCT_TEXT.value, AgentSessionStatus.GENERATING_PRODUCT_TEXT.value, now, session_id, user_id, session["version"]))
            if cursor.rowcount != 1:
                raise AgentSessionVersionConflict()
        return False

    def confirm_product_text(self, session_id: str, user_id: str, decision_id: str, expected_version: int | None) -> bool:
        now = self._now()
        with self._transaction() as cursor:
            session = self._locked_owned_session(cursor, session_id, user_id)
            cursor.execute("SELECT id FROM agent_messages WHERE session_id=%s AND decision_id=%s LIMIT 1", (session_id, decision_id))
            if self._fetchone(cursor) is not None:
                return True
            self._check_expected(session, AgentSessionStatus.WAITING_TEXT_FEEDBACK, expected_version)
            if not session.get("confirmed_text_json"):
                raise AgentSessionStateConflict()
            cursor.execute("SELECT COALESCE(MAX(sequence_no), 0) + 1 AS next_sequence FROM agent_messages WHERE session_id=%s", (session_id,))
            sequence = int((self._fetchone(cursor) or {}).get("next_sequence") or 1)
            cursor.execute(
                """INSERT INTO agent_messages (id,session_id,sequence_no,role,message_type,content_text,content_json,decision_id,created_at)
                VALUES (%s,%s,%s,'assistant','decision_receipt',%s,NULL,%s,%s)""",
                (str(uuid.uuid4()), session_id, sequence, "产品设计方案已确认，下一步将整理视觉方向和图片生成提示。", decision_id, now),
            )
            cursor.execute(
                """UPDATE agent_sessions SET status=%s,current_stage=%s,version=version+1,updated_at=%s
                WHERE id=%s AND user_id=%s AND version=%s""",
                (AgentSessionStatus.BUILDING_VISUAL_PROMPT.value, AgentSessionStatus.BUILDING_VISUAL_PROMPT.value,
                 now, session_id, user_id, session["version"]),
            )
            if cursor.rowcount != 1:
                raise AgentSessionVersionConflict()
        return False

    def finish_visual_prompt(self, session_id: str, user_id: str, *, package: dict[str, Any], summary: str, step_id: str) -> None:
        now = self._now()
        with self._transaction() as cursor:
            session = self._locked_owned_session(cursor, session_id, user_id)
            if session.get("status") != AgentSessionStatus.BUILDING_VISUAL_PROMPT.value:
                raise AgentSessionStateConflict()
            cursor.execute("SELECT COALESCE(MAX(sequence_no), 0) + 1 AS next_sequence FROM agent_messages WHERE session_id=%s", (session_id,))
            sequence = int((self._fetchone(cursor) or {}).get("next_sequence") or 1)
            cursor.execute(
                """INSERT INTO agent_messages (id,session_id,sequence_no,role,message_type,content_text,content_json,created_at)
                VALUES (%s,%s,%s,'assistant','visual_direction',%s,NULL,%s)""",
                (str(uuid.uuid4()), session_id, sequence, summary, now),
            )
            cursor.execute("UPDATE agent_steps SET status='completed',output_summary_json=%s,finished_at=%s WHERE id=%s AND session_id=%s",
                           (self._json({"summary": "Visual direction ready"}), now, step_id, session_id))
            cursor.execute(
                """UPDATE agent_sessions SET image_prompt_json=%s,status=%s,current_stage=%s,version=version+1,updated_at=%s
                WHERE id=%s AND user_id=%s AND version=%s""",
                (self._json(package), AgentSessionStatus.WAITING_IMAGE_CONFIRMATION.value,
                 AgentSessionStatus.WAITING_IMAGE_CONFIRMATION.value, now, session_id, user_id, session["version"]),
            )
            if cursor.rowcount != 1:
                raise AgentSessionVersionConflict()

    def confirm_image_generation(self, session_id: str, user_id: str, decision_id: str, expected_version: int | None) -> bool:
        """Atomically claim the only allowed final image generation for a session."""
        now = self._now()
        with self._transaction() as cursor:
            session = self._locked_owned_session(cursor, session_id, user_id)
            cursor.execute("SELECT id FROM agent_messages WHERE session_id=%s AND decision_id=%s LIMIT 1", (session_id, decision_id))
            if self._fetchone(cursor) is not None:
                return True
            self._check_expected(session, AgentSessionStatus.WAITING_IMAGE_CONFIRMATION, expected_version)
            if not session.get("image_prompt_json"):
                raise AgentSessionStateConflict()
            cursor.execute("SELECT COALESCE(MAX(sequence_no), 0) + 1 AS next_sequence FROM agent_messages WHERE session_id=%s", (session_id,))
            sequence = int((self._fetchone(cursor) or {}).get("next_sequence") or 1)
            cursor.execute(
                """INSERT INTO agent_messages (id,session_id,sequence_no,role,message_type,content_text,content_json,decision_id,created_at)
                VALUES (%s,%s,%s,'assistant','decision_receipt',%s,%s,%s,%s)""",
                (str(uuid.uuid4()), session_id, sequence,
                 "视觉方向已确认，正在生成最终产品图片。",
                 self._json({"decision": "confirm_image_generation", "outcome": "started"}), decision_id, now),
            )
            cursor.execute(
                """UPDATE agent_sessions SET status=%s,current_stage=%s,version=version+1,updated_at=%s
                WHERE id=%s AND user_id=%s AND version=%s""",
                (AgentSessionStatus.GENERATING_IMAGE.value, AgentSessionStatus.GENERATING_IMAGE.value,
                 now, session_id, user_id, session["version"]),
            )
            if cursor.rowcount != 1:
                raise AgentSessionVersionConflict()
        return False

    def finish_image_generation(
        self, session_id: str, user_id: str, *, step_id: str, image_url: str, response_payload: dict[str, Any],
        brief: dict[str, Any], title: str, content: str, generation_time: float,
    ) -> int:
        """Persist one Agent history row, bind it, and complete the session in one transaction."""
        now = self._now()
        with self._transaction() as cursor:
            session = self._locked_owned_session(cursor, session_id, user_id)
            if session.get("status") != AgentSessionStatus.GENERATING_IMAGE.value or session.get("generation_log_id") is not None:
                raise AgentSessionStateConflict()
            cursor.execute(
                """INSERT INTO generation_logs
                (user_id,event_type,timestamp,prompt,style,image_url,title,content,generation_time,content_length,
                 user_rating,download_count,user_age,user_gender,login_time,data_origin,generation_kind,
                 prompt_template_version,brief_json,response_json)
                VALUES (%s,'generate',%s,%s,%s,%s,%s,%s,%s,%s,NULL,0,NULL,NULL,NULL,'production',
                        'agent_dialogue_mvp','agent-dialogue-mvp-v1',%s,%s)""",
                (user_id, now, title, "agent-dialogue", image_url, title, content, generation_time, len(content),
                 self._json(brief), self._json(response_payload)),
            )
            log_id = int(cursor.lastrowid)
            cursor.execute("SELECT COALESCE(MAX(sequence_no), 0) + 1 AS next_sequence FROM agent_messages WHERE session_id=%s", (session_id,))
            sequence = int((self._fetchone(cursor) or {}).get("next_sequence") or 1)
            cursor.execute(
                """INSERT INTO agent_messages (id,session_id,sequence_no,role,message_type,content_text,content_json,created_at)
                VALUES (%s,%s,%s,'assistant','final_result',%s,NULL,%s)""",
                (str(uuid.uuid4()), session_id, sequence, "最终图片已生成并保存到创作记录。", now),
            )
            cursor.execute(
                """UPDATE agent_steps SET status='completed',output_summary_json=%s,finished_at=%s
                WHERE id=%s AND session_id=%s""", (self._json({"summary": "Final image generated and persisted", "log_id": log_id}), now, step_id, session_id)
            )
            cursor.execute(
                """UPDATE agent_sessions SET generation_log_id=%s,context_summary_json=%s,status=%s,current_stage=%s,
                completed_at=%s,error_json=NULL,error_code=NULL,failure_stage=NULL,version=version+1,updated_at=%s
                WHERE id=%s AND user_id=%s AND version=%s""",
                (log_id, self._json({"final_result": response_payload}), AgentSessionStatus.COMPLETED.value,
                 AgentSessionStatus.COMPLETED.value, now, now, session_id, user_id, session["version"]),
            )
            if cursor.rowcount != 1:
                raise AgentSessionVersionConflict()
        return log_id

    def record_image_persistence_failure(self, session_id: str, user_id: str, *, step_id: str, error: dict[str, Any], image_url: str | None = None) -> None:
        """Keep a locally persisted artifact discoverable without ever re-running the provider automatically."""
        now = self._now()
        with self._transaction() as cursor:
            session = self._locked_owned_session(cursor, session_id, user_id)
            if session.get("status") != AgentSessionStatus.GENERATING_IMAGE.value:
                raise AgentSessionStateConflict()
            cursor.execute("UPDATE agent_steps SET status='failed',error_json=%s,error_code=%s,finished_at=%s WHERE id=%s AND session_id=%s",
                           (self._json(error), error.get("code"), now, step_id, session_id))
            cursor.execute(
                """UPDATE agent_sessions SET context_summary_json=%s,status='failed',current_stage='failed',failure_stage='generating_image',
                error_json=%s,error_code=%s,version=version+1,updated_at=%s WHERE id=%s AND user_id=%s AND version=%s""",
                (self._json({"orphaned_image_url": image_url} if image_url else {}), self._json(error), error.get("code"), now,
                 session_id, user_id, session["version"]),
            )
            if cursor.rowcount != 1:
                raise AgentSessionVersionConflict()
