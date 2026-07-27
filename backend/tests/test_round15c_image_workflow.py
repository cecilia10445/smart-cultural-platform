from types import SimpleNamespace

import pytest

from backend.domain.cultural_product_brief import BriefValidationError, validate_cultural_product_request
from backend.prompts.cultural_product_v1 import build_image_edit_prompt, build_image_negative_prompt
from backend.services.aigc_service import AIGCService
from backend.services.aigc_service import AIGCServiceError


def brief(mode="flat_front_back", back="背面粗陶，无纹样，防滑磨砂处理"):
    return validate_cultural_product_request({"brief_version": "1.0", "brief": {
        "product_type": "杯垫", "presentation_mode": mode,
        "back_design_requirements": back,
        "cultural_source": {"source_type": "artifact", "name": "青花瓷", "era": "明代", "creator": ""},
        "confirmed_facts": [], "form_and_material": "粗陶", "use_case": "家居", "target_audience": "成人",
        "visual_direction": {"preset_id": "x", "cultural_context": "青花", "medium": "陶瓷", "palette": "蓝白", "composition": "圆形", "additional_requirements": ""},
    }})


def test_flat_requires_explicit_back_requirements():
    with pytest.raises(BriefValidationError, match="required"):
        value = brief().copy()
        value["back_design_requirements"] = ""
        # explicit empty is rejected by the request validator; this assertion
        # documents the API boundary without invoking any provider.
        validate_cultural_product_request({"brief_version": "1.0", "brief": {
            "product_type": "杯垫", "presentation_mode": "flat_front_back", "back_design_requirements": "",
            "cultural_source": {"source_type": "artifact", "name": "青花瓷"}, "confirmed_facts": [],
            "form_and_material": "粗陶", "use_case": "家居", "visual_direction": {
                "preset_id": "x", "cultural_context": "青花", "medium": "陶瓷", "palette": "蓝白", "composition": "圆形"
            }
        }})


def test_edit_prompt_carries_back_requirement_and_forbids_copying_pattern():
    prompt = build_image_edit_prompt(brief(), "国风陶瓷杯垫")
    assert "背面粗陶" in prompt
    assert "不得复制正面纹样" in prompt
    assert "纯白背景横向" in prompt
    assert "重复正面" in build_image_negative_prompt()


def test_edit_adapter_uses_one_text_and_one_image(monkeypatch):
    settings = SimpleNamespace(
        dashscope_api_key="x", dashscope_openai_base_url="https://text.invalid", dashscope_api_base_url="https://api.invalid",
        dashscope_text_model="text", dashscope_text_reasoning_effort="none", dashscope_image_model="wan2.6-t2i",
        dashscope_image_edit_model="wan2.6-image", dashscope_image_size="1280*1280",
        dashscope_text_connect_timeout_seconds=1, dashscope_text_read_timeout_seconds=1,
        dashscope_image_connect_timeout_seconds=1, dashscope_image_read_timeout_seconds=1,
    )
    captured = {}
    class Response:
        status_code = 200
        def json(self):
            return {"output": {"choices": [{"message": {"content": [{"image": "https://provider.invalid/final"}]}}]}}
    monkeypatch.setattr("backend.services.aigc_service.requests.post", lambda *args, **kwargs: (captured.update(kwargs) or Response()))
    service = AIGCService(settings, text_client=object())
    assert service.edit_image_with_reference("https://provider.invalid/ref", "edit", "negative", "1200*800") == "https://provider.invalid/final"
    content = captured["json"]["input"]["messages"][0]["content"]
    assert len(content) == 2 and {"text"} == set(content[0]) and {"image"} == set(content[1])
    assert captured["json"]["model"] == "wan2.6-image"
    assert captured["json"]["parameters"]["enable_interleave"] is False


def test_edit_failure_uses_edit_stage_start_and_does_not_persist_log(app_module, client, monkeypatch):
    from backend.tests.test_cultural_product_contract import payload as contract_payload
    from backend.tests.conftest import login

    class Tracker:
        instances = []
        def __init__(self, *_args):
            self.metrics = []
            self.failed = None
            self.__class__.instances.append(self)
        def start(self):
            return None
        def record_metric(self, stage, model, status, started, **kwargs):
            self.metrics.append((stage, status, started))
        def fail(self, stage, code):
            self.failed = (stage, code)

    class Rag:
        def retrieve(self, _brief):
            return SimpleNamespace(status="insufficient_evidence")
        def evidence_block(self, _retrieval):
            return []
        def verified_sources(self, *_args):
            return []

    class Model:
        text_model = "stub-text"
        image_model = "wan2.6-t2i"
        image_edit_model = "wan2.6-image"
        def generate_cultural_product_text_with_evidence(self, _brief, _context):
            return ({"product_name": "测试杯垫", "factual_background": "", "creative_origin": "青花瓷",
                     "design_concept": "粗陶杯垫", "cultural_meaning": "雅致生活",
                     "selling_points": ["粗陶", "正反面", "防滑"], "used_source_ids": [],
                     "evidence_status": "insufficient_evidence"}, {})
        def generate_image_from_prompt(self, *_args):
            return "https://provider.invalid/reference"
        def edit_image_with_reference(self, *_args):
            raise AIGCServiceError("MODEL_REQUEST_FAILED", "edit failed")

    database = SimpleNamespace(connect=lambda: True)
    monkeypatch.setattr(app_module, "mysql_service", database)
    monkeypatch.setattr(app_module, "GenerationTracker", Tracker)
    monkeypatch.setattr(app_module, "get_cultural_rag_service", lambda: Rag())
    monkeypatch.setattr(app_module, "aigc_service", Model())
    item = contract_payload()
    item["brief"]["back_design_requirements"] = "素色粗陶背面，无青花纹样，防滑磨砂处理"
    response = client.post("/api/v2/cultural-products/generate", json=item, headers={"Authorization": f"Bearer {login(client)}"})
    assert response.status_code == 502
    tracker = Tracker.instances[-1]
    assert tracker.failed == ("image_layout_edit", "MODEL_REQUEST_FAILED")
    assert [(stage, status) for stage, status, _ in tracker.metrics] == [
        ("text_generation", "SUCCEEDED"), ("image_reference_generation", "SUCCEEDED"), ("image_layout_edit", "FAILED")
    ]
    assert tracker.metrics[2][2] > tracker.metrics[1][2]
