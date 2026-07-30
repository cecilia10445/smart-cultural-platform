import pytest

from backend.domain.agent_dialogue import ProductTextOutputInvalid
from backend.services.agent_product_text import ProductTextService, select_text_skill_id


BRIEF = {
    "product_type": "桌面氛围灯",
    "cultural_source": {"source_type": "artifact", "name": "三兔共耳", "era": None, "creator": None},
    "confirmed_facts": [],
    "form_and_material": "环形金属结构与半透明灯罩",
    "use_case": "现代家居桌面照明",
    "target_audience": "现代家居用户",
    "presentation_mode": "single_hero",
    "front_design_requirements": "", "back_design_requirements": "", "side_design_requirements": "",
    "visual_direction": {"preset_id": "modern_product", "cultural_context": "现代东方", "medium": "产品摄影", "palette": "暖白与金属灰", "composition": "单品主视图", "additional_requirements": "避免仿古"},
}


def draft(status="creative_only", used=None):
    return {
        "product_name": "三兔环光桌面灯", "design_concept": "以环形动态感组织柔和照明。",
        "cultural_translation": "将三兔共耳的循环关系转译为现代灯体结构。",
        "structure": "环形底座、发光内圈与半透明灯罩。", "materials": "磨砂金属和半透明亚克力",
        "color_plan": "暖白与深灰", "usage_scene": "现代家居桌面照明",
        "selling_points": ["环形识别", "柔和照明", "现代材质"], "creative_origin": "三兔共耳的循环构图",
        "factual_background": "当前资料不足；此处仅作当代设计转译。", "evidence_status": status,
        "evidence": [], "used_source_ids": used or [], "selected_text_skill": None, "revision_summary": None,
    }


class MatchedDecision:
    status = "matched"
    results = ()


class GroundedRag:
    def retrieve(self, _brief): return MatchedDecision()

    def evidence_block(self, _decision):
        return [{"source_id": "met-1", "title": "Three Hares", "facts": ["A compact verified fact."]}]


class EmptyRag:
    def retrieve(self, _brief):
        return type("NoMatch", (), {"status": "no_match"})()


def test_product_text_grounded_path_validates_citations_and_projects_safe_evidence():
    service = ProductTextService(runner=lambda _payload: draft("grounded", ["met-1"]), rag_factory=GroundedRag)
    evidence = service.retrieve_cultural_evidence(BRIEF)
    skill = service.select_text_skill(BRIEF)
    result = service.generate(BRIEF, evidence, skill)

    assert evidence["status"] == "grounded"
    assert result.evidence_status == "grounded"
    assert result.used_source_ids == ["met-1"]
    assert result.evidence == [{"source_id": "met-1", "title": "Three Hares"}]
    assert result.selected_text_skill == "retail-product-copy"


def test_product_text_creative_only_for_no_match_and_rag_error():
    service = ProductTextService(runner=lambda _payload: draft(), rag_factory=EmptyRag)
    evidence = service.retrieve_cultural_evidence(BRIEF)
    result = service.generate(BRIEF, evidence, service.select_text_skill(BRIEF))
    assert evidence["status"] == "creative_only" and evidence["fallback"] == "no_reliable_match"
    assert result.evidence == [] and result.used_source_ids == []

    failed_rag = ProductTextService(runner=lambda _payload: draft(), rag_factory=lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    assert failed_rag.retrieve_cultural_evidence(BRIEF)["fallback"] == "rag_unavailable"


def test_product_text_rejects_invalid_grounded_citation_and_selects_only_text_skills(monkeypatch):
    service = ProductTextService(runner=lambda _payload: draft("grounded", ["unknown"]), rag_factory=GroundedRag)
    with pytest.raises(ProductTextOutputInvalid):
        service.generate(BRIEF, service.retrieve_cultural_evidence(BRIEF), service.select_text_skill(BRIEF))
    assert select_text_skill_id({**BRIEF, "use_case": "博物馆展陈衍生品"}) == "museum-product-explainer"
    assert select_text_skill_id({**BRIEF, "use_case": "社交活动文化传播"}) == "social-cultural-story"

    import backend.services.agent_product_text as product_module
    monkeypatch.setattr(product_module, "load_skill", lambda _skill_id: (_ for _ in ()).throw(product_module.SkillAssetError("bad asset")))
    fallback = ProductTextService(runner=lambda _payload: draft()).select_text_skill({**BRIEF, "use_case": "博物馆展陈衍生品"})
    assert fallback["skill_id"] == "retail-product-copy" and fallback["fallback"] is True
