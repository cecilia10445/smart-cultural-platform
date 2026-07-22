from backend.services.aigc_service import AIGCServiceError
from evaluation.real_cultural_product_smoke import run_smoke


def test_real_smoke_reports_only_schema_and_usage_for_success():
    class Service:
        def generate_cultural_product_text_with_metadata(self, _brief):
            return {"product_name": "标题", "design_interpretation": "解读", "product_copy": "文案"}, {"total_tokens": 3}

    result = run_smoke({"request": {"brief_version": "1.0", "brief": {"product_type": "书签", "cultural_source": {"source_type": "artifact", "name": "纹样", "era": None, "creator": None}, "confirmed_facts": [], "form_and_material": "纸", "use_case": "商店", "target_audience": None, "visual_direction": {"preset_id": "x", "cultural_context": "东方", "medium": "平面", "palette": "蓝白", "composition": "中心", "additional_requirements": None}}}}, Service())
    assert result["status"] == "passed" and result["schema_valid"] is True
    assert "product_name" not in str(result)


def test_real_smoke_keeps_only_safe_error_fields():
    class Service:
        def generate_cultural_product_text_with_metadata(self, _brief):
            raise AIGCServiceError("MODEL_RESPONSE_INCOMPLETE", "private", http_status=200, response_summary={"status": "incomplete"})

    result = run_smoke({"request": {"brief_version": "1.0", "brief": {"product_type": "书签", "cultural_source": {"source_type": "artifact", "name": "纹样", "era": None, "creator": None}, "confirmed_facts": [], "form_and_material": "纸", "use_case": "商店", "target_audience": None, "visual_direction": {"preset_id": "x", "cultural_context": "东方", "medium": "平面", "palette": "蓝白", "composition": "中心", "additional_requirements": None}}}}, Service())
    assert result["stable_error_category"] == "MODEL_RESPONSE_INCOMPLETE"
    assert "private" not in str(result)
