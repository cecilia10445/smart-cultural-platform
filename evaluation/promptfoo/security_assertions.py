import json, sys
from pathlib import Path
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path: sys.path.insert(0, str(REPOSITORY_ROOT))
from backend.domain.cultural_product_brief import BriefValidationError, validate_cultural_product_request
METADATA = {"executor_type": "stub", "data_origin": "test",
            "measurement_scope": "harness_self_test", "latency_scope": "harness_runtime_only"}
POLICY_CASES = {"malicious-url", "xss", "unicode", "fake-origin", "fake-source",
                "malformed-evidence", "out-of-bounds-source", "grounded-empty-citation",
                "insufficient-with-citation", "prompt-leak", "credential-leak",
                "authorization-leak", "fake-era", "fake-author", "fake-endorsement",
                "fake-collection", "fake-history", "web-as-museum"}
def evaluate_security_case(case_id):
    """Exercise request validation or a deterministic output-policy rejection."""
    category = case_id.removeprefix("security-")
    brief = {"product_type": "杯垫", "presentation_mode": "single_hero",
             "cultural_source": {"source_type": "artifact", "name": "青花瓷"},
             "confirmed_facts": [], "form_and_material": "粗陶", "use_case": "茶席",
             "target_audience": "成人", "visual_direction": {"preset_id": "x",
             "cultural_context": "青花", "medium": "陶瓷", "palette": "蓝白", "composition": "居中"}}
    payload = {"brief_version": "1.0", "brief": brief}
    code = "SECURITY_BOUNDARY_REJECTED"
    if category == "unknown-field":
        brief["unexpected"] = "ignored"
    elif category == "invalid-json":
        code = "INVALID_REQUEST_FORMAT"
    elif category == "field-type":
        brief["confirmed_facts"] = {"not": "array"}
    elif category == "long-input":
        brief["form_and_material"] = "x" * 501
    elif category == "long-facts":
        brief["confirmed_facts"] = ["x"] * 9
    elif category not in POLICY_CASES:
        return {"accepted": True, "stable_code": "UNKNOWN_SECURITY_CASE",
                "security_category": category, "evaluation_metadata": METADATA}
    if category in {"unknown-field", "field-type", "long-input", "long-facts"}:
        try:
            validate_cultural_product_request(payload)
            return {"accepted": True, "stable_code": "VALIDATION_BYPASSED",
                    "security_category": category, "evaluation_metadata": METADATA}
        except BriefValidationError as error:
            code = error.code
    return {"accepted": False, "stable_code": code, "security_category": category,
            "evaluation_metadata": METADATA}


def get_assert(output, context):
    try:
        value = json.loads(output)
    except (TypeError, json.JSONDecodeError):
        return {"pass": False, "score": 0, "reason": "security response is not JSON"}
    expected = context.get("vars", {}).get("case_id", "")
    if not expected.startswith("security-"):
        return {"pass": False, "score": 0, "reason": "security assertion used by non-security case"}
    safe = value.get("accepted") is False and isinstance(value.get("stable_code"), str) and bool(value["stable_code"])
    safe = safe and value.get("security_category") == expected.removeprefix("security-")
    safe = safe and value.get("evaluation_metadata") == METADATA
    return {"pass": safe, "score": 1 if safe else 0, "reason": "deterministic boundary rejection" if safe else "unsafe security response"}
