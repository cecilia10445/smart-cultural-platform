from copy import deepcopy
from datetime import datetime

import pytest

from backend.domain.agent_dialogue import (
    AgentDecisionNotSupported, AgentInvalidTransition, AgentSessionStateConflict,
    AgentSessionStatus, AgentSessionVersionConflict, ImagePromptPackage, ProductDesignDraft, ProductTextModelTimeout,
)
from backend.services.agent_dialogue_service import AgentDialogueService
from backend.services.agent_brief_agent import BriefAgent
from backend.services.aigc_service import AIGCServiceError


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

    def has_client_turn(self, session_id, user_id, client_turn_id):
        self._row(session_id, user_id)
        return any(item.get("client_turn_id") == client_turn_id for item in self.messages[session_id])

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

    def finish_step(self, session_id, user_id, step_id, output_summary, tool_result_summary=None):
        self._row(session_id, user_id)
        next(item for item in self.steps[session_id] if item["id"] == step_id).update(
            status="completed", output_summary_json=output_summary, tool_result_summary_json=tool_result_summary,
        )

    def finish_product_text(self, session_id, user_id, *, draft, summary, step_id, is_revision):
        row = self._row(session_id, user_id)
        if row["status"] != "generating_product_text":
            raise AgentSessionStateConflict()
        self.messages[session_id].append({"id": f"message-{len(self.messages[session_id]) + 1}", "sequence_no": len(self.messages[session_id]) + 1,
                                          "role": "assistant", "message_type": "product_design", "content_text": summary, "created_at": self._now()})
        next(item for item in self.steps[session_id] if item["id"] == step_id).update(status="completed", output_summary_json={"summary": "Product design text ready"})
        row.update(confirmed_text_json=draft, text_revision_count=row["text_revision_count"] + (1 if is_revision else 0),
                   status="waiting_text_feedback", current_stage="waiting_text_feedback", error_json=None, error_code=None,
                   failure_stage=None, version=row["version"] + 1, updated_at=self._now())

    def return_to_text_feedback(self, session_id, user_id, error):
        row = self._row(session_id, user_id)
        row.update(status="waiting_text_feedback", current_stage="waiting_text_feedback", error_json=error, error_code=error["code"],
                   failure_stage="generating_product_text", version=row["version"] + 1, updated_at=self._now())

    def confirm_brief(self, session_id, user_id, decision_id, expected_version):
        row = self._row(session_id, user_id)
        if any(item.get("decision_id") == decision_id for item in self.messages[session_id]): return True
        if row["status"] != "waiting_brief_confirmation": raise AgentSessionStateConflict()
        self.messages[session_id].append({"id": f"message-{len(self.messages[session_id]) + 1}", "sequence_no": len(self.messages[session_id]) + 1, "role": "assistant", "message_type": "decision_receipt", "content_text": "需求方案已确认，下一步将生成产品设计文本。", "decision_id": decision_id, "created_at": self._now()})
        row.update(status="generating_product_text", current_stage="generating_product_text", version=row["version"] + 1)
        return False

    def confirm_product_text(self, session_id, user_id, decision_id, expected_version):
        row = self._row(session_id, user_id)
        if any(item.get("decision_id") == decision_id for item in self.messages[session_id]): return True
        if row["status"] != "waiting_text_feedback": raise AgentSessionStateConflict()
        self.messages[session_id].append({"id": f"message-{len(self.messages[session_id]) + 1}", "sequence_no": len(self.messages[session_id]) + 1,
                                          "role": "assistant", "message_type": "decision_receipt", "content_text": "产品设计方案已确认，下一步将整理视觉方向和图片生成提示。",
                                          "decision_id": decision_id, "created_at": self._now()})
        row.update(status="building_visual_prompt", current_stage="building_visual_prompt", version=row["version"] + 1, updated_at=self._now())
        return False

    def finish_visual_prompt(self, session_id, user_id, *, package, summary, step_id):
        row = self._row(session_id, user_id)
        self.messages[session_id].append({"id": f"message-{len(self.messages[session_id]) + 1}", "sequence_no": len(self.messages[session_id]) + 1,
                                          "role": "assistant", "message_type": "visual_direction", "content_text": summary, "created_at": self._now()})
        next(item for item in self.steps[session_id] if item["id"] == step_id).update(status="completed", output_summary_json={"summary": "Visual direction ready"})
        row.update(image_prompt_json=package, status="waiting_image_confirmation", current_stage="waiting_image_confirmation", version=row["version"] + 1, updated_at=self._now())

    def confirm_image_generation(self, session_id, user_id, decision_id, expected_version):
        row = self._row(session_id, user_id)
        if any(item.get("decision_id") == decision_id for item in self.messages[session_id]): return True
        if row["status"] != "waiting_image_confirmation": raise AgentSessionStateConflict()
        self.messages[session_id].append({"id": f"message-{len(self.messages[session_id]) + 1}", "sequence_no": len(self.messages[session_id]) + 1,
                                          "role": "assistant", "message_type": "decision_receipt", "content_text": "视觉方向已确认，正在生成最终产品图片。",
                                          "decision_id": decision_id, "created_at": self._now()})
        row.update(status="generating_image", current_stage="generating_image", version=row["version"] + 1, updated_at=self._now())
        return False

    def finish_image_generation(self, session_id, user_id, *, step_id, image_url, response_payload, brief, title, content, generation_time):
        row = self._row(session_id, user_id)
        if row["status"] != "generating_image" or row.get("generation_log_id") is not None:
            raise AgentSessionStateConflict()
        log_id = 800 + len(self.sessions)
        self.messages[session_id].append({"id": f"message-{len(self.messages[session_id]) + 1}", "sequence_no": len(self.messages[session_id]) + 1,
                                          "role": "assistant", "message_type": "final_result", "content_text": "最终图片已生成并保存到创作记录。", "created_at": self._now()})
        next(item for item in self.steps[session_id] if item["id"] == step_id).update(status="completed", output_summary_json={"summary": "Final image generated and persisted", "log_id": log_id})
        row.update(generation_log_id=log_id, context_summary_json={"final_result": response_payload}, status="completed", current_stage="completed", version=row["version"] + 1, updated_at=self._now())
        return log_id

    def record_image_persistence_failure(self, session_id, user_id, *, step_id, error, image_url=None):
        row = self._row(session_id, user_id)
        next(item for item in self.steps[session_id] if item["id"] == step_id).update(status="failed", error_json=error, error_code=error["code"])
        row.update(status="failed", current_stage="failed", failure_stage="generating_image", error_json=error, error_code=error["code"], context_summary_json={"orphaned_image_url": image_url} if image_url else {}, version=row["version"] + 1, updated_at=self._now())

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


class FakeProductTextService:
    def __init__(self): self.calls = 0

    def retrieve_cultural_evidence(self, _brief):
        return {"status": "creative_only", "evidence": [], "sources": [], "fallback": "no_reliable_match"}

    def select_text_skill(self, _brief):
        return {"skill_id": "retail-product-copy", "version": "1.0.0", "instruction": "test", "fallback": False}

    def generate(self, brief, evidence, skill, *, current_draft=None, feedback=None):
        self.calls += 1
        base = current_draft or {
            "product_name": "三兔环光桌面灯", "design_concept": "环形动态感", "cultural_translation": "以三兔共耳的循环关系转译为灯体环形结构",
            "structure": brief["form_and_material"], "materials": "金属与半透明亚克力", "color_plan": "暖白与深灰",
            "usage_scene": brief["use_case"], "selling_points": ["环形识别", "柔和照明", "现代材质"],
            "creative_origin": "三兔共耳的循环构图", "factual_background": "当前资料不足；作为当代设计转译。",
            "evidence_status": evidence["status"], "evidence": [], "used_source_ids": [],
            "selected_text_skill": skill["skill_id"], "revision_summary": None,
        }
        result = dict(base)
        if feedback:
            result["materials"] = "磨砂金属和半透明亚克力" if "磨砂" in feedback else result["materials"]
            result["revision_summary"] = f"已根据反馈调整：{feedback}"
        return ProductDesignDraft.model_validate(result)


def fake_visual_builder(brief, design, evidence, skill):
    return ImagePromptPackage(
        positive_prompt=f"{design['product_name']}；{design['materials']}；{brief['presentation_mode']}", negative_prompt="人物，文字",
        required_constraints=["完整产品"], product_form=design["structure"], materials=design["materials"],
        color_plan=design["color_plan"], composition=brief["visual_direction"]["composition"], scene=design["usage_scene"],
        avoid=["人物", "文字"], presentation_mode=brief["presentation_mode"], selected_visual_skill=skill["skill_id"],
        evidence_source_ids=[item["source_id"] for item in evidence], user_facing_direction="以现代产品主视图呈现材质和结构。",
    )


def fake_visual_skill(_brief, _design):
    return {"skill_id": "commercial-product-presentation", "version": "1.0.0", "instruction": "test", "fallback": False}


class FakeImageGenerationService:
    def __init__(self): self.calls = 0

    def generate(self, _package):
        self.calls += 1
        return {"image_url": "/static/images/agent-test.png"}


def ready_for_image(service):
    created = service.create_session("U1")
    service.append_message(created.session_id, "U1", text="设计现代桌面灯", client_turn_id="brief")
    service.submit_decision(created.session_id, "U1", decision_id="confirm-brief", decision="confirm_brief", expected_status=AgentSessionStatus.WAITING_BRIEF_CONFIRMATION)
    return service.submit_decision(created.session_id, "U1", decision_id="confirm-text", decision="confirm_product_text", expected_status=AgentSessionStatus.WAITING_TEXT_FEEDBACK)


@pytest.fixture()
def service():
    return AgentDialogueService(MemoryRepository(), BriefAgent(runner=proposal), FakeProductTextService(), fake_visual_builder, fake_visual_skill, FakeImageGenerationService())


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


def test_confirm_brief_generates_product_text_once(service):
    created = service.create_session("U1")
    service.append_message(created.session_id, "U1", text="设计现代桌面灯", client_turn_id="turn-1")
    confirmed = service.submit_decision(created.session_id, "U1", decision_id="decision-1", decision="confirm_brief", expected_status=AgentSessionStatus.WAITING_BRIEF_CONFIRMATION)
    replay = service.submit_decision(created.session_id, "U1", decision_id="decision-1", decision="confirm_brief", expected_status=AgentSessionStatus.WAITING_BRIEF_CONFIRMATION)
    assert confirmed.status is AgentSessionStatus.WAITING_TEXT_FEEDBACK
    assert replay.status is AgentSessionStatus.WAITING_TEXT_FEEDBACK
    assert confirmed.product_design is not None and confirmed.revision_count == 0


def test_product_text_revision_limit_and_confirmation(service):
    created = service.create_session("U1")
    service.append_message(created.session_id, "U1", text="设计现代桌面灯", client_turn_id="brief")
    service.submit_decision(created.session_id, "U1", decision_id="confirm-brief", decision="confirm_brief", expected_status=AgentSessionStatus.WAITING_BRIEF_CONFIRMATION)
    for revision in range(4):
        detail, replayed = service.append_message(created.session_id, "U1", text="材质改成磨砂金属", client_turn_id=f"revision-{revision}", expected_status=AgentSessionStatus.WAITING_TEXT_FEEDBACK)
        assert not replayed and detail.revision_count == revision + 1
        if revision == 0:
            duplicate, duplicate_replayed = service.append_message(created.session_id, "U1", text="ignored", client_turn_id="revision-0", expected_status=AgentSessionStatus.WAITING_TEXT_FEEDBACK)
            assert duplicate_replayed and duplicate.revision_count == 1
    with pytest.raises(Exception) as limited:
        service.append_message(created.session_id, "U1", text="再改一次", client_turn_id="revision-5", expected_status=AgentSessionStatus.WAITING_TEXT_FEEDBACK)
    assert getattr(limited.value, "code", None) == "TEXT_REVISION_LIMIT_REACHED"
    confirmed = service.submit_decision(created.session_id, "U1", decision_id="confirm-text", decision="confirm_product_text", expected_status=AgentSessionStatus.WAITING_TEXT_FEEDBACK)
    assert confirmed.status is AgentSessionStatus.WAITING_IMAGE_CONFIRMATION
    assert confirmed.visual_direction is not None
    image = service.submit_decision(created.session_id, "U1", decision_id="confirm-image", decision="confirm_image_generation", expected_status=AgentSessionStatus.WAITING_IMAGE_CONFIRMATION)
    replay = service.submit_decision(created.session_id, "U1", decision_id="confirm-image", decision="confirm_image_generation", expected_status=AgentSessionStatus.WAITING_IMAGE_CONFIRMATION)
    assert image.status is AgentSessionStatus.COMPLETED and image.generation_log_id is not None
    assert replay.status is AgentSessionStatus.COMPLETED and len(replay.messages) == len(image.messages)


def test_failed_revision_keeps_last_valid_design_and_does_not_increment_count():
    product = FakeProductTextService()
    service = AgentDialogueService(MemoryRepository(), BriefAgent(runner=proposal), product)
    created = service.create_session("U1")
    service.append_message(created.session_id, "U1", text="设计现代桌面灯", client_turn_id="brief")
    original = service.submit_decision(created.session_id, "U1", decision_id="confirm-brief", decision="confirm_brief", expected_status=AgentSessionStatus.WAITING_BRIEF_CONFIRMATION)

    def unavailable(*_args, **_kwargs):
        raise ProductTextModelTimeout()
    product.generate = unavailable
    with pytest.raises(ProductTextModelTimeout):
        service.append_message(created.session_id, "U1", text="颜色改深灰", client_turn_id="revision-fail", expected_status=AgentSessionStatus.WAITING_TEXT_FEEDBACK)
    restored = service.get_session(created.session_id, "U1")
    assert restored.status is AgentSessionStatus.WAITING_TEXT_FEEDBACK
    assert restored.revision_count == 0 and restored.product_design == original.product_design
    assert restored.steps[-1].status == "failed" and restored.error.code == "PRODUCT_TEXT_MODEL_TIMEOUT"


def test_final_image_decision_is_idempotent_and_writes_one_log():
    image = FakeImageGenerationService()
    service = AgentDialogueService(MemoryRepository(), BriefAgent(runner=proposal), FakeProductTextService(), fake_visual_builder, fake_visual_skill, image)
    prepared = ready_for_image(service)
    completed = service.submit_decision(prepared.session_id, "U1", decision_id="image-once", decision="confirm_image_generation", expected_status=AgentSessionStatus.WAITING_IMAGE_CONFIRMATION)
    replay = service.submit_decision(prepared.session_id, "U1", decision_id="image-once", decision="confirm_image_generation", expected_status=AgentSessionStatus.WAITING_IMAGE_CONFIRMATION)
    assert completed.status is AgentSessionStatus.COMPLETED and completed.final_result.image_url.endswith("agent-test.png")
    assert replay.generation_log_id == completed.generation_log_id and image.calls == 1


def test_image_provider_failure_marks_failed_without_a_second_attempt():
    class UnavailableImage:
        calls = 0
        def generate(self, _package):
            self.calls += 1
            raise AIGCServiceError("MODEL_REQUEST_FAILED", "unavailable", retryable=True)

    image = UnavailableImage()
    service = AgentDialogueService(MemoryRepository(), BriefAgent(runner=proposal), FakeProductTextService(), fake_visual_builder, fake_visual_skill, image)
    prepared = ready_for_image(service)
    with pytest.raises(Exception) as raised:
        service.submit_decision(prepared.session_id, "U1", decision_id="image-fail", decision="confirm_image_generation", expected_status=AgentSessionStatus.WAITING_IMAGE_CONFIRMATION)
    assert getattr(raised.value, "code", None) == "AGENT_IMAGE_GENERATION_FAILED"
    failed = service.get_session(prepared.session_id, "U1")
    assert failed.status is AgentSessionStatus.FAILED and failed.error.code == "AGENT_IMAGE_GENERATION_FAILED" and image.calls == 1
