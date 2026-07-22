"""Versioned, validated request model for cultural-product generation."""

from __future__ import annotations

import json


BRIEF_VERSION = "1.0"
MAX_FACTS = 8
MAX_FACT_LENGTH = 240
MAX_SHORT_TEXT = 160
MAX_LONG_TEXT = 500
ALLOWED_TOP_LEVEL = {"brief_version", "brief"}


class BriefValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _string(value, code, field, required=True, limit=MAX_SHORT_TEXT):
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise BriefValidationError(code, f"{field} must be a string.")
    value = value.strip()
    if required and not value:
        raise BriefValidationError(code, f"{field} is required.")
    if len(value) > limit:
        raise BriefValidationError(code, f"{field} is too long.")
    return value or None


def _object(value, code, field):
    if not isinstance(value, dict):
        raise BriefValidationError(code, f"{field} must be an object.")
    return value


def validate_cultural_product_request(payload):
    """Return a normalized, JSON-serializable cultural product brief.

    This deliberately accepts only the documented outer envelope so misspelled
    fields cannot silently become prompt content.
    """
    if not isinstance(payload, dict):
        raise BriefValidationError("INVALID_REQUEST_FORMAT", "Request body must be a JSON object.")
    if set(payload) - ALLOWED_TOP_LEVEL:
        raise BriefValidationError("INVALID_REQUEST_FORMAT", "Request contains unsupported fields.")
    if payload.get("brief_version") != BRIEF_VERSION:
        raise BriefValidationError("INVALID_BRIEF_VERSION", "brief_version is not supported.")

    brief = _object(payload.get("brief"), "INVALID_REQUEST_FORMAT", "brief")
    allowed_brief = {
        "product_type", "cultural_source", "confirmed_facts", "form_and_material",
        "use_case", "target_audience", "visual_direction",
    }
    if set(brief) - allowed_brief:
        raise BriefValidationError("INVALID_REQUEST_FORMAT", "brief contains unsupported fields.")

    source = _object(brief.get("cultural_source"), "INVALID_CULTURAL_SOURCE", "cultural_source")
    if set(source) - {"source_type", "name", "era", "creator"}:
        raise BriefValidationError("INVALID_CULTURAL_SOURCE", "cultural_source contains unsupported fields.")
    normalized_source = {
        "source_type": _string(source.get("source_type"), "INVALID_CULTURAL_SOURCE", "cultural_source.source_type"),
        "name": _string(source.get("name"), "INVALID_CULTURAL_SOURCE", "cultural_source.name"),
        "era": _string(source.get("era"), "INVALID_CULTURAL_SOURCE", "cultural_source.era", False),
        "creator": _string(source.get("creator"), "INVALID_CULTURAL_SOURCE", "cultural_source.creator", False),
    }

    facts = brief.get("confirmed_facts", [])
    if not isinstance(facts, list) or len(facts) > MAX_FACTS:
        raise BriefValidationError("INVALID_CONFIRMED_FACTS", "confirmed_facts must be an array within the supported limit.")
    normalized_facts = []
    for fact in facts:
        normalized = _string(fact, "INVALID_CONFIRMED_FACTS", "confirmed_facts item", True, MAX_FACT_LENGTH)
        normalized_facts.append(normalized)

    direction = _object(brief.get("visual_direction"), "INVALID_VISUAL_DIRECTION", "visual_direction")
    direction_fields = {"preset_id", "cultural_context", "medium", "palette", "composition", "additional_requirements"}
    if set(direction) - direction_fields:
        raise BriefValidationError("INVALID_VISUAL_DIRECTION", "visual_direction contains unsupported fields.")
    normalized_direction = {
        "preset_id": _string(direction.get("preset_id"), "INVALID_VISUAL_DIRECTION", "visual_direction.preset_id"),
        "cultural_context": _string(direction.get("cultural_context"), "INVALID_VISUAL_DIRECTION", "visual_direction.cultural_context"),
        "medium": _string(direction.get("medium"), "INVALID_VISUAL_DIRECTION", "visual_direction.medium"),
        "palette": _string(direction.get("palette"), "INVALID_VISUAL_DIRECTION", "visual_direction.palette"),
        "composition": _string(direction.get("composition"), "INVALID_VISUAL_DIRECTION", "visual_direction.composition"),
        "additional_requirements": _string(direction.get("additional_requirements"), "INVALID_VISUAL_DIRECTION", "visual_direction.additional_requirements", False, MAX_SHORT_TEXT),
    }
    style_text = '；'.join(value for value in (
        normalized_direction["cultural_context"], normalized_direction["medium"], normalized_direction["palette"],
        normalized_direction["composition"], normalized_direction["additional_requirements"],
    ) if value)
    if len(style_text) > 100:
        raise BriefValidationError("INVALID_VISUAL_DIRECTION", "visual_direction is too long for the current data contract.")
    return {
        "brief_version": BRIEF_VERSION,
        "product_type": _string(brief.get("product_type"), "INVALID_PRODUCT_TYPE", "product_type"),
        "cultural_source": normalized_source,
        "confirmed_facts": normalized_facts,
        "form_and_material": _string(brief.get("form_and_material"), "INVALID_REQUEST_FORMAT", "form_and_material", True, MAX_LONG_TEXT),
        "use_case": _string(brief.get("use_case"), "INVALID_REQUEST_FORMAT", "use_case"),
        "target_audience": _string(brief.get("target_audience"), "INVALID_REQUEST_FORMAT", "target_audience", False),
        "visual_direction": normalized_direction,
    }


def canonical_brief_json(brief):
    """Stable serialization used for the data boundary and persistence."""
    return json.dumps(brief, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
