"""Deterministic visual-prompt stage for a confirmed Agent product design."""

from __future__ import annotations

from typing import Any

from backend.agents.skill_registry import SKILLS, SkillAssetError, load_skill
from backend.domain.agent_dialogue import ImagePromptPackage
from backend.prompts.cultural_product_v1 import build_image_negative_prompt


DEFAULT_VISUAL_SKILL = "commercial-product-presentation"


def select_visual_skill_id(brief: dict[str, Any], design: dict[str, Any]) -> str:
    text = " ".join(str(value or "") for value in (
        (brief.get("cultural_source") or {}).get("name"), design.get("cultural_translation"),
        brief.get("form_and_material"), design.get("materials"), brief.get("presentation_mode"),
    )).lower()
    if any(term in text for term in ("纹样", "图案", "传统", "文化转译", "heritage", "motif")):
        return "heritage-motif-translation"
    if any(term in text for term in ("材质", "金属", "结构", "亚克力", "真实", "material", "metal")):
        return "product-material-realism"
    return DEFAULT_VISUAL_SKILL


def load_visual_skill(brief: dict[str, Any], design: dict[str, Any]) -> dict[str, Any]:
    requested = select_visual_skill_id(brief, design)
    try:
        skill = SKILLS.get(requested)
        if skill is None or skill.kind != "visual":
            raise SkillAssetError("VISUAL_SKILL_UNAVAILABLE")
        return {"skill_id": requested, "version": skill.version, "instruction": load_skill(requested), "fallback": False}
    except (SkillAssetError, OSError, ValueError):
        skill = SKILLS[DEFAULT_VISUAL_SKILL]
        try:
            instruction = load_skill(DEFAULT_VISUAL_SKILL)
        except (SkillAssetError, OSError, ValueError):
            instruction = "Present one complete cultural product clearly and realistically."
        return {"skill_id": DEFAULT_VISUAL_SKILL, "version": skill.version, "instruction": instruction, "fallback": True}


def _mode_constraint(mode: str) -> str:
    return {
        "flat_front_back": "同一件产品的正面与背面并排展示，比例一致，无场景与文字",
        "three_view": "同一件产品的正面、侧面、背面横向三视图，尺度一致，无场景与文字",
        "single_hero": "单件产品居中，以略带透视的产品主视角展示完整造型，无文字",
    }.get(mode, "单件产品居中展示完整造型，无文字")


def build_image_prompt_package(
    normalized_brief: dict[str, Any], confirmed_product_design: dict[str, Any],
    evidence_summary: list[dict[str, Any]] | None, visual_skill: dict[str, Any],
) -> ImagePromptPackage:
    """Build a safe package from confirmed material; no image/model provider is called."""
    required_design = ("product_name", "structure", "materials", "color_plan", "usage_scene", "cultural_translation")
    if any(not isinstance(confirmed_product_design.get(field), str) or not confirmed_product_design[field].strip() for field in required_design):
        raise ValueError("CONFIRMED_PRODUCT_DESIGN_INVALID")
    direction = normalized_brief.get("visual_direction") or {}
    source = normalized_brief.get("cultural_source") or {}
    mode = str(normalized_brief.get("presentation_mode") or "single_hero")
    constraints = [
        _mode_constraint(mode),
        "产品完整可见，材质、比例与色彩一致",
        *(value for value in (direction.get("additional_requirements"),) if isinstance(value, str) and value.strip()),
    ]
    avoid = [item.strip() for item in build_image_negative_prompt().split("，") if item.strip()]
    evidence_ids = [item.get("source_id") for item in (evidence_summary or []) if isinstance(item, dict) and isinstance(item.get("source_id"), str)]
    product_form = str(confirmed_product_design.get("structure") or normalized_brief.get("form_and_material") or normalized_brief.get("product_type") or "文创产品")
    materials = str(confirmed_product_design.get("materials") or normalized_brief.get("form_and_material") or "待确认材质")
    color_plan = str(confirmed_product_design.get("color_plan") or direction.get("palette") or "协调配色")
    composition = str(direction.get("composition") or "单品主视图")
    scene = str(confirmed_product_design.get("usage_scene") or normalized_brief.get("use_case") or "产品展示")
    parts = [
        "文创产品设计展示图，纯白或克制中性背景", f"产品名称：{confirmed_product_design.get('product_name')}",
        f"产品类型：{normalized_brief.get('product_type')}", f"产品形态与结构：{product_form}",
        f"材质：{materials}", f"色彩：{color_plan}", f"构图：{composition}", f"使用场景意象：{scene}",
        f"文化转译：{confirmed_product_design.get('cultural_translation')}", f"展示方式：{_mode_constraint(mode)}",
        f"视觉表达重点：{visual_skill.get('skill_id') or DEFAULT_VISUAL_SKILL}", *constraints,
    ]
    user_direction = (
        f"将以{product_form}为主体，呈现{materials}与{color_plan}的现代产品质感；"
        f"采用{composition}，围绕{scene}使用情境组织画面，并避免{('、'.join(avoid[:5]))}。"
    )
    return ImagePromptPackage(
        positive_prompt="；".join(str(item) for item in parts if item)[:6000], negative_prompt=build_image_negative_prompt(),
        required_constraints=constraints, product_form=product_form, materials=materials, color_plan=color_plan,
        composition=composition, scene=scene, avoid=avoid, presentation_mode=mode,
        selected_visual_skill=visual_skill.get("skill_id") if isinstance(visual_skill.get("skill_id"), str) else None,
        evidence_source_ids=evidence_ids, user_facing_direction=user_direction[:2000],
    )
