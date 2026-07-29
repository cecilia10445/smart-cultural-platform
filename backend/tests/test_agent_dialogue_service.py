from copy import deepcopy
from datetime import datetime

import pytest

from backend.domain.agent_dialogue import (
    AgentDecisionNotSupported, AgentInvalidTransition, AgentSessionStateConflict,
    AgentSessionStatus, AgentSessionVersionConflict,
)
from backend.services.agent_dialogue_service import AgentDialogueService


class MemoryRepository:
    """Intentional unit-test boundary; no database/model/provider is touched."""

    def __init__(self):
        self.sessions, self.messages, self.steps, self.counter = {}, {}, {}, 0

    def _now(self):
        return datetime(2026, 7, 30, 12, 0, 0)

    def _row(self, session_id, owner):
        row = self.sessions.get(session_id)
        if not row or row["user_id"] != owner:
            from backend.domain.agent_dialogue import AgentSessionNotFound
            raise AgentSessionNotFound()
        return row

    def create_session(self, user_id):
        self.counter += 1
        session_id = f"session-{self.counter}"
        row = {"id": session_id, "user_id": user_id, "status": "created", "current_stage": "created",
               "text_revision_count": 0, "generation_log_id": None, "brief_json": None, "confirmed_text_json": None,
               "image_prompt_json": None, "error_json": None, "error_code": None, "failure_stage": None,
               "version": 1, "created_at": self._now(), "updated_at": self._now()}
        self.sessions[session_id] = row
        self.messages[session_id], self.steps[session_id] = [], []
        return deepcopy(row)

    def get_session(self, session_id, user_id):
        return deepcopy(self._row(session_id, user_id))

    def get_detail_rows(self, session_id, user_id):
        self._row(session_id, user_id)
        return deepcopy(self.sessions[session_id]), deepcopy(self.messages[session_id]), deepcopy(self.steps[session_id])

    def append_user_message(self, session_id, user_id, text, client_turn_id, expected_status, expected_version):
        row = self._row(session_id, user_id)
        if any(item.get("client_turn_id") == client_turn_id for item in self.messages[session_id]):
            return deepcopy(row), True
        if expected_status and row["status"] != expected_status.value:
            raise AgentSessionStateConflict()
        if expected_version and row["version"] != expected_version:
            raise AgentSessionVersionConflict()
        self.messages[session_id].append({"id": f"message-{len(self.messages[session_id]) + 1}", "sequence_no": len(self.messages[session_id]) + 1,
                                          "role": "user", "message_type": "request", "content_text": text, "client_turn_id": client_turn_id,
                                          "created_at": self._now()})
        if row["status"] == "created":
            row.update(status="extracting_brief", current_stage="extracting_brief", version=row["version"] + 1, updated_at=self._now())
        return deepcopy(row), False

    def append_step(self, session_id, user_id, stage, status, **kwargs):
        self._row(session_id, user_id)
        row = {"id": f"step-{len(self.steps[session_id]) + 1}", "ordinal": len(self.steps[session_id]) + 1,
               "stage": stage, "status": status, "tool_name": kwargs.get("tool_name"), "output_summary_json": kwargs.get("output_summary"),
               "tool_result_summary_json": kwargs.get("tool_result_summary"), "error_json": kwargs.get("error"),
               "error_code": kwargs.get("error_code"), "started_at": kwargs.get("started_at"), "finished_at": kwargs.get("finished_at")}
        self.steps[session_id].append(row)
        return deepcopy(row)

    def transition(self, session_id, user_id, target, expected_status, expected_version):
        row = self._row(session_id, user_id)
        if expected_status and row["status"] != expected_status.value:
            raise AgentSessionStateConflict()
        if expected_version and row["version"] != expected_version:
            raise AgentSessionVersionConflict()
        row.update(status=target.value, current_stage=target.value, version=row["version"] + 1, updated_at=self._now())
        return deepcopy(row)

    def mark_failed(self, session_id, user_id, *, error_code, error, expected_version=None):
        row = self._row(session_id, user_id)
        if expected_version and row["version"] != expected_version:
            raise AgentSessionVersionConflict()
        row.update(status="failed", failure_stage=row["current_stage"], error_code=error_code, error_json=error,
                   version=row["version"] + 1, updated_at=self._now())
        return deepcopy(row)

    def record_unsupported_decision(self, session_id, user_id, decision_id, decision, expected_status, expected_version):
        row = self._row(session_id, user_id)
        if any(item.get("decision_id") == decision_id for item in self.messages[session_id]):
            return True
        if row["status"] != expected_status.value:
            raise AgentSessionStateConflict()
        if expected_version and row["version"] != expected_version:
            raise AgentSessionVersionConflict()
        self.messages[session_id].append({"id": f"message-{len(self.messages[session_id]) + 1}", "sequence_no": len(self.messages[session_id]) + 1,
                                          "role": "system", "message_type": "decision_receipt", "content_text": "unsupported",
                                          "decision_id": decision_id, "created_at": self._now()})
        return False


@pytest.fixture()
def service():
    return AgentDialogueService(MemoryRepository())


def test_session_message_idempotency_owner_scope_and_sequence(service):
    created = service.create_session("U1")
    detail, replayed = service.append_message(created.session_id, "U1", text="设计一枚书签", client_turn_id="turn-1", expected_version=1)
    duplicate, replayed_duplicate = service.append_message(created.session_id, "U1", text="ignored", client_turn_id="turn-1", expected_version=1)

    assert detail.status is AgentSessionStatus.EXTRACTING_BRIEF
    assert replayed is False and replayed_duplicate is True
    assert [(item.sequence_no, item.text) for item in duplicate.messages] == [(1, "设计一枚书签")]
    with pytest.raises(Exception) as denied:
        service.get_session(created.session_id, "U2")
    assert getattr(denied.value, "code", None) == "AGENT_SESSION_NOT_FOUND"


def test_step_order_version_conflict_and_illegal_transition(service):
    created = service.create_session("U1")
    first = service.append_step(created.session_id, "U1", stage="created", status="completed", output_summary={"summary": "one"})
    second = service.append_step(created.session_id, "U1", stage="created", status="completed", output_summary={"summary": "two"})
    assert [item.ordinal for item in second.steps] == [1, 2]
    with pytest.raises(AgentSessionVersionConflict):
        service.append_message(created.session_id, "U1", text="x", client_turn_id="turn-1", expected_version=9)
    with pytest.raises(AgentInvalidTransition):
        service.transition(created.session_id, "U1", AgentSessionStatus.COMPLETED)
    assert first.steps[0].summary == "one"


def test_failed_session_preserves_messages_steps_and_decision_receipt_is_idempotent(service):
    created = service.create_session("U1")
    service.append_message(created.session_id, "U1", text="设计一枚书签", client_turn_id="turn-1")
    service.append_step(created.session_id, "U1", stage="extracting_brief", status="failed", error={"code": "X"})
    failed = service.mark_failed(created.session_id, "U1", error_code="BRIEF_FAILED", message="Brief did not complete")
    assert failed.status is AgentSessionStatus.FAILED
    assert len(failed.messages) == 1 and len(failed.steps) == 1
    with pytest.raises(AgentDecisionNotSupported):
        service.submit_decision(created.session_id, "U1", decision_id="decision-1", decision="confirm_brief", expected_status=AgentSessionStatus.FAILED)
    with pytest.raises(AgentDecisionNotSupported):
        service.submit_decision(created.session_id, "U1", decision_id="decision-1", decision="confirm_brief", expected_status=AgentSessionStatus.FAILED)
    assert len(service.get_session(created.session_id, "U1").messages) == 2
