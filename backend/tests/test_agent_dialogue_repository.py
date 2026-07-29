from datetime import datetime

import pytest

from backend.domain.agent_dialogue import AgentSessionNotFound, AgentSessionStatus
from backend.services.agent_dialogue_repository import AgentDialogueRepository


class Cursor:
    def __init__(self, database):
        self.database, self.one, self.rowcount = database, None, 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        normalized = " ".join(query.split()).lower()
        self.one, self.rowcount = None, 0
        if normalized.startswith("insert into agent_sessions"):
            session_id, user_id, status, stage, revision, version, created, updated = params
            self.database.sessions[session_id] = {"id": session_id, "user_id": user_id, "status": status, "current_stage": stage,
                                                  "text_revision_count": revision, "version": version, "created_at": created, "updated_at": updated,
                                                  "generation_log_id": None, "brief_json": None, "confirmed_text_json": None, "image_prompt_json": None,
                                                  "error_json": None, "error_code": None, "failure_stage": None}
        elif normalized.startswith("select * from agent_sessions"):
            session_id, user_id = params
            row = self.database.sessions.get(session_id)
            self.one = dict(row) if row and row["user_id"] == user_id else None
        elif "select id from agent_messages" in normalized:
            session_id, turn_id = params
            self.one = next(({"id": item["id"]} for item in self.database.messages if item.get("session_id") == session_id and item.get("client_turn_id") == turn_id), None)
        elif "coalesce(max(sequence_no)" in normalized:
            session_id = params[0]
            self.one = {"next_sequence": 1 + max([item["sequence_no"] for item in self.database.messages if item["session_id"] == session_id] or [0])}
        elif normalized.startswith("insert into agent_messages"):
            values = params
            self.database.messages.append({"id": values[0], "session_id": values[1], "sequence_no": values[2], "role": values[3],
                                           "message_type": values[4], "content_text": values[5], "client_turn_id": values[7], "decision_id": values[8],
                                           "created_at": values[9]})
        elif normalized.startswith("update agent_sessions set status"):
            _status, stage, updated, session_id, user_id, version = params
            row = self.database.sessions.get(session_id)
            if row and row["user_id"] == user_id and row["version"] == version:
                row.update(status=_status, current_stage=stage, updated_at=updated, version=version + 1)
                self.rowcount = 1
        elif normalized.startswith("select * from agent_messages"):
            session_id = params[0]
            self.rows = [dict(item) for item in self.database.messages if item["session_id"] == session_id]
        elif normalized.startswith("select * from agent_steps"):
            self.rows = []

    def fetchone(self):
        return self.one

    def fetchall(self):
        return getattr(self, "rows", [])


class Connection:
    def __init__(self, database):
        self.database, self.closed, self.committed, self.rolled_back, self.begun = database, False, False, False, False

    def begin(self):
        self.begun = True

    def cursor(self, *_args, **_kwargs):
        return Cursor(self.database)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class Database:
    def __init__(self):
        self.sessions, self.messages, self.connections = {}, [], []

    def borrow(self):
        connection = Connection(self)
        self.connections.append(connection)
        return connection


class MySQLStub:
    def __init__(self, database):
        self.database = database

    def _borrow_connection(self):
        return self.database.borrow()


def test_repository_create_owner_scope_message_idempotency_and_short_transactions():
    database = Database()
    repository = AgentDialogueRepository(MySQLStub(database))
    created = repository.create_session("U1")
    session_id = created["id"]
    after_first, replayed = repository.append_user_message(session_id, "U1", "设计一枚书签", "turn-1", None, 1)
    after_duplicate, duplicate_replayed = repository.append_user_message(session_id, "U1", "ignored", "turn-1", None, 1)

    assert created["status"] == "created"
    assert after_first["status"] == AgentSessionStatus.EXTRACTING_BRIEF.value
    assert replayed is False and duplicate_replayed is True
    assert len(database.messages) == 1 and database.messages[0]["sequence_no"] == 1
    assert after_duplicate["version"] == after_first["version"]
    assert all(item.closed and item.committed and item.begun for item in database.connections)
    with pytest.raises(AgentSessionNotFound):
        repository.get_session(session_id, "U2")


def test_repository_rows_need_a_separate_projection_before_http_response():
    database = Database()
    repository = AgentDialogueRepository(MySQLStub(database))
    row = repository.create_session("U1")
    row["untrusted_provider_payload"] = {"trace": "must-not-leak"}

    from backend.domain.agent_dialogue import project_agent_session_detail

    detail = project_agent_session_detail(row, [], [])
    assert "untrusted_provider_payload" not in detail.model_dump()
    assert detail.brief_summary is None and detail.messages == [] and detail.steps == []
