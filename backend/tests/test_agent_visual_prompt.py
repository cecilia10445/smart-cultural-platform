import pytest

from backend.domain.agent_dialogue import ImagePromptPackage
from backend.services.agent_visual_prompt import build_image_prompt_package, load_visual_skill, select_visual_skill_id


BRIEF = {"product_type": "桌面灯", "presentation_mode": "single_hero", "cultural_source": {"name": "三兔共耳纹样"},
         "form_and_material": "环形金属结构", "use_case": "现代家居桌面", "visual_direction": {"palette": "暖白与深灰", "composition": "单品主视图", "additional_requirements": "避免仿古"}}
DESIGN = {"product_name": "三兔环光灯", "structure": "环形发光内圈与底座", "materials": "磨砂金属和半透明亚克力",
          "color_plan": "暖白与深灰", "usage_scene": "现代家居桌面照明", "cultural_translation": "以循环纹样转译环形动态感"}


def test_package_uses_confirmed_design_brief_constraints_and_fixed_negative_prompt():
    skill = load_visual_skill(BRIEF, DESIGN)
    package = build_image_prompt_package(BRIEF, DESIGN, [{"source_id": "met-1", "title": "Three Hares"}], skill)
    assert isinstance(package, ImagePromptPackage)
    assert DESIGN["materials"] in package.positive_prompt
    assert DESIGN["product_name"] in package.positive_prompt
    assert "避免仿古" in package.required_constraints
    assert "人物" in package.negative_prompt and "水印" in package.negative_prompt
    assert package.evidence_source_ids == ["met-1"]
    assert package.presentation_mode == "single_hero"


def test_visual_skill_selector_never_loads_text_skill_and_falls_back(monkeypatch):
    assert select_visual_skill_id(BRIEF, DESIGN) == "heritage-motif-translation"
    import backend.services.agent_visual_prompt as visual_module
    monkeypatch.setattr(visual_module, "load_skill", lambda _skill_id: (_ for _ in ()).throw(visual_module.SkillAssetError("bad asset")))
    skill = visual_module.load_visual_skill({**BRIEF, "cultural_source": {"name": "现代产品"}}, {**DESIGN, "cultural_translation": "简洁结构"})
    assert skill["skill_id"] == "commercial-product-presentation" and skill["fallback"] is True


def test_package_rejects_missing_confirmed_design_fields():
    with pytest.raises(Exception):
        build_image_prompt_package(BRIEF, {"product_name": "x"}, [], {"skill_id": "commercial-product-presentation"})
