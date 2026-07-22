"""One-case, explicit-opt-in real business smoke for the v2 persistence path.

This entry is deliberately separate from component evaluation.  It logs in the
configured local smoke identity and calls the Flask v2 endpoint once, so a
successful run is persisted to the dedicated demo database with data_origin
set by the server to ``test``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_DATABASE = "aigc_platform_demo"
REQUIRED_USERNAME = "user1"


class BusinessSmokeConfigurationError(RuntimeError):
    """Raised before any login or provider request when a gate is not met."""


def validate_business_smoke_settings(settings):
    """Validate the complete opt-in boundary without exposing configuration values."""
    if not settings.run_real_business_smoke:
        raise BusinessSmokeConfigurationError("RUN_REAL_BUSINESS_SMOKE_REQUIRED")
    if settings.mysql_database != REQUIRED_DATABASE:
        raise BusinessSmokeConfigurationError("SMOKE_DATABASE_NOT_ALLOWED")
    if settings.smoke_test_username != REQUIRED_USERNAME:
        raise BusinessSmokeConfigurationError("SMOKE_USERNAME_NOT_ALLOWED")
    if not settings.smoke_test_password:
        raise BusinessSmokeConfigurationError("SMOKE_PASSWORD_REQUIRED")
    if not settings.dashscope_api_key:
        raise BusinessSmokeConfigurationError("DASHSCOPE_API_KEY_REQUIRED")


def smoke_request_payload():
    """Return a fixed, non-sensitive, one-case CulturalProductBrief."""
    return {
        "brief_version": "1.0",
        "brief": {
            "product_type": "书签",
            "cultural_source": {
                "source_type": "artifact",
                "name": "青花瓷纹样",
                "era": None,
                "creator": None,
            },
            "confirmed_facts": ["用户确认：本次设计以青花瓷纹样为灵感来源。"],
            "form_and_material": "长条形纸质书签，配棉质流苏",
            "use_case": "博物馆文创商店",
            "target_audience": "年轻游客",
            "visual_direction": {
                "preset_id": "blue-white-pattern",
                "cultural_context": "青花瓷",
                "medium": "釉下青花",
                "palette": "靛青瓷白",
                "composition": "中心纹样",
                "additional_requirements": "避免人物",
            },
        },
    }


def safe_response_summary(response):
    body = response.get_json(silent=True) or {}
    return {
        "http_status": response.status_code,
        "api_status": body.get("status"),
        "stable_error_category": body.get("code"),
        "log_id": body.get("log_id") if response.status_code == 200 else None,
        "generation_kind": body.get("generation_kind") if response.status_code == 200 else None,
        "prompt_template_version": body.get("prompt_template_version") if response.status_code == 200 else None,
    }


def run_business_smoke(app_module):
    """Login and submit exactly one v2 request through Flask's API boundary."""
    validate_business_smoke_settings(app_module.settings)
    client = app_module.app.test_client()
    login_response = client.post(
        "/api/login",
        json={
            "username": app_module.settings.smoke_test_username,
            "password": app_module.settings.smoke_test_password,
            "role": "user",
        },
    )
    if login_response.status_code != 200:
        return {"status": "failed", "stage": "login", **safe_response_summary(login_response)}
    token = (login_response.get_json(silent=True) or {}).get("token")
    if not isinstance(token, str) or not token:
        return {"status": "failed", "stage": "login", "stable_error_category": "SMOKE_LOGIN_TOKEN_MISSING"}
    response = client.post(
        "/api/v2/cultural-products/generate",
        json=smoke_request_payload(),
        headers={"Authorization": f"Bearer {token}"},
    )
    summary = safe_response_summary(response)
    return {
        "status": "passed" if response.status_code == 200 and summary["log_id"] else "failed",
        "stage": "v2_generate",
        **summary,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--executor", choices=("real",), required=True)
    parser.add_argument("--allow-real-model", action="store_true")
    parser.add_argument("--max-real-cases", type=int)
    args = parser.parse_args()
    if not args.allow_real_model or args.max_real_cases != 1:
        parser.error("business smoke requires --allow-real-model --max-real-cases 1")

    from backend import app as app_module

    try:
        result = run_business_smoke(app_module)
    except BusinessSmokeConfigurationError as error:
        result = {"status": "blocked", "stage": "preflight", "stable_error_category": str(error)}
    report = {
        "executor_type": "real",
        "data_origin": "test",
        "measurement_scope": "real_business_smoke",
        "sample_size": 1,
        **result,
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
