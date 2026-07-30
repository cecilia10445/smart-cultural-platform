"""Narrow final-image adapter for a confirmed collaborative design session."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.services.aigc_service import AIGCService, AIGCServiceError
from backend.services.image_storage import ImagePersistenceError, persist_generated_image


class AgentImageGenerationService:
    """Reuse the established image provider and local storage without legacy prompts."""

    def __init__(self, aigc_service: AIGCService | None = None, *, persist=persist_generated_image, images_dir: str | None = None):
        self.aigc_service = aigc_service or AIGCService()
        self.persist = persist
        self.images_dir = images_dir or str(Path(__file__).resolve().parents[2] / "static" / "images")

    def generate(self, package: dict[str, Any]) -> dict[str, Any]:
        """Generate and persist exactly one final local image from the confirmed package."""
        positive = package.get("positive_prompt")
        negative = package.get("negative_prompt")
        mode = package.get("presentation_mode")
        if not isinstance(positive, str) or not positive.strip() or not isinstance(negative, str) or not negative.strip():
            raise ValueError("IMAGE_PROMPT_PACKAGE_INVALID")
        try:
            if mode == "single_hero":
                provider_url = self.aigc_service.generate_image_from_prompt(positive, negative)
            else:
                reference_url = self.aigc_service.generate_image_from_prompt(positive, negative)
                output_size = "1200*800" if mode == "flat_front_back" else "1280*720"
                layout_instruction = (
                    f"{positive}；请严格保持同一件产品的结构、材质与色彩一致；"
                    + ("正面与背面并排展示。" if mode == "flat_front_back" else "正面、侧面与背面横向三视图展示。")
                )
                provider_url = self.aigc_service.edit_image_with_reference(reference_url, layout_instruction, negative, output_size)
            return {"image_url": self.persist(provider_url, self.images_dir), "presentation_mode": mode}
        except (AIGCServiceError, ImagePersistenceError):
            raise
