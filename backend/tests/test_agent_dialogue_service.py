from copy import deepcopy
from datetime import datetime

import pytest

from backend.domain.agent_dialogue import (
    AgentDecisionNotSupported, AgentInvalidTransition, AgentSessionStateConflict,
    AgentSessionStatus, AgentSessionVersionConflict,
)
from backend.services.agent_dialogue_service import AgentDialogueService
from backend.services.agent_brief_agent import BriefAgent


def proposal(_prompt):
    return {"normalized_brief": {"product_type": "桌面氛围灯", "presentation_mode": "single_hero", "cultural_source": {"source_type": "artifact", "name": "三兔共耳", "era": None, "creator": None}, "confirmed_facts": [], "form_and_material": "环形金属结构与半透明灯罩", "use_case": "现代家居桌面照明", "target_audience": "现代家居用户", "visual_direction": {"preset_id": "modern_product", "cultural_context": "现代东方", "medium": "产品摄影", "palette": "暖白与金属灰", "composition": "单品主视图", "additional_requirements": "避免仿古"}, "front_design_requirements": "", "back_design_requirements": "", "side_design_requirements": ""}, "understanding": {"cultural_theme": "三兔共耳纹样", "product_type": "桌面氛围灯", "use_case": "现代家居桌面照明", "style": "现代", "form_and_material": "环形金属结构与半透明灯罩", "presentation_mode": "单品主视图", "design_constraints": ["避免仿古"]}, "assumptions": ["采用单品主视图展示", "默认现代产品摄影风格"], "user_facing_summary": "placeholder"}


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

    def finish_brief(self, session_id, user_id, *, brief, summary, step_id):
        row = self._row(session_id, user_id)
        self.messages[session_id].append({"id": f"message-{len(self.messages[session_id]) + 1}", "sequence_no": len(self.messages[session_id]) + 1, "role": "assistant", "message_type": "brief_summary", "content_text": summary, "created_at": self._now()})
        next(item for item in self.steps[session_id] if item["id"] == step_id).update(status="completed", output_summary_json={"summary": "Brief proposal ready"})
        row.update(brief_json=brief, status="waiting_brief_confirmation", current_stage="waiting_brief_confirmation", version=row["version"] + 1, updated_at=self._now())

    def fail_step(self, session_id, user_id, step_id, error):
        self._row(session_id, user_id)
        next(item for item in self.steps[session_id] if item["id"] == step_id).update(status="failed", error_json=error, error_code=error["code"])

    def confirm_brief(self, session_id, user_id, decision_id, expected_version):
        row = self._row(session_id, user_id)
        if any(item.get("decision_id") == decision_id for item in self.messages[session_id]): return True
        if row["status"] != "waiting_brief_confirmation": raise AgentSessionStateConflict()
        self.messages[session_id].append({"id": f"message-{len(self.messages[session_id]) + 1}", "sequence_no": len(self.messages[session_id]) + 1, "role": "assistant", "message_type": "decision_receipt", "content_text": "需求方案已确认，下一步将生成产品设计文本。", "decision_id": decision_id, "created_at": self._now()})
        row.update(status="generating_product_text", current_stage="generating_product_text", version=row["version"] + 1)
        return False

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
    return AgentDialogueService(MemoryRepository(), BriefAgent(runner=proposal))


def test_session_message_idempotency_owner_scope_and_sequence(service):
    created = service.create_session("U1")
    detail, replayed = service.append_message(created.session_id, "U1", text="设计一枚书签", client_turn_id="turn-1", expected_version=1)
    duplicate, replayed_duplicate = service.append_message(created.session_id, "U1", text="ignored", client_turn_id="turn-1", expected_version=1)

    assert detail.status is AgentSessionStatus.WAITING_BRIEF_CONFIRMATION
    assert replayed is False and replayed_duplicate is True
    assert [(item.sequence_no, item.text) for item in duplicate.messages][:1] == [(1, "设计一枚书签")]
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
    assert len(failed.messages) == 2 and len(failed.steps) == 2
    with pytest.raises(AgentSessionStateConflict):
        service.submit_decision(created.session_id, "U1", decision_id="decision-1", decision="confirm_brief", expected_status=AgentSessionStatus.FAILED)
    with pytest.raises(AgentSessionStateConflict):
        service.submit_decision(created.session_id, "U1", decision_id="decision-1", decision="confirm_brief", expected_status=AgentSessionStatus.FAILED)
    assert len(service.get_session(created.session_id, "U1").messages) == 2


def test_confirm_brief_moves_once_to_product_text_stage(service):
    created = service.create_session("U1")
    service.append_message(created.session_id, "U1", text="设计现代桌面灯", client_turn_id="turn-1")
    confirmed = service.submit_decision(created.session_id, "U1", decision_id="decision-1", decision="confirm_brief", expected_status=AgentSessionStatus.WAITING_BRIEF_CONFIRMATION)
    replay = service.submit_decision(created.session_id, "U1", decision_id="decision-1", decision="confirm_brief", expected_status=AgentSessionStatus.WAITING_BRIEF_CONFIRMATION)
    assert confirmed.status is AgentSessionStatus.GENERATING_PRODUCT_TEXT
    assert replay.status is AgentSessionStatus.GENERATING_PRODUCT_TEXT
