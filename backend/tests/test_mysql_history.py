from datetime import datetime

from backend.services.mysql_service import MySQLService


def test_user_history_exposes_real_generation_log_id(monkeypatch):
    service = MySQLService()
    observed = {}

    def execute_query(query, params):
        observed["query"] = query
        observed["params"] = params
        return [{
            "log_id": 1,
            "timestamp": datetime(2026, 7, 22, 12, 0, 0),
            "prompt": "brief summary",
            "style": "青花瓷；釉下青花",
            "image_url": "/static/images/image_test.png",
            "title": "测试标题",
            "content": "测试文案",
            "generation_time": 1.25,
            "content_length": 4,
            "user_rating": None,
            "download_count": 0,
            "user_age": None,
            "user_gender": None,
        }]

    monkeypatch.setattr(service, "execute_query", execute_query)

    history = service.get_user_history("U1001")

    assert "id AS log_id" in observed["query"]
    assert observed["params"] == ("U1001",)
    assert history[0]["log_id"] == 1
    assert history[0]["image_url"] == "/static/images/image_test.png"


def test_v2_history_normalizes_nested_factual_background_and_citations(monkeypatch):
    service = MySQLService()
    monkeypatch.setattr(service, "execute_query", lambda query, params: [{
        "log_id": 2,
        "generation_kind": "cultural_product",
        "prompt_template_version": "cultural-product-rag-v2",
        "timestamp": datetime(2026, 7, 27, 12, 0, 0),
        "generation_time": 2.5,
        "image_url": "/static/images/image_2.png",
        "title": "杯垫",
        "content_length": 0,
        "user_rating": None,
        "download_count": 0,
        "user_age": None,
        "user_gender": None,
        "brief_json": '{"presentation_mode":"flat_front_back"}',
        "response_json": '{"product_name":"青花杯垫","creative_origin":"青花瓷",'
            '"design_concept":"圆形粗陶杯垫","cultural_meaning":"雅致",'
            '"selling_points":["防滑","耐热","易清洁"],'
            '"factual_background":{"text":"馆藏器物为釉下青花瓷。",'
            '"status":"grounded","citations":[{"source_id":"met-39666",'
            '"title":"Blue-and-White Dish","source_url":"https://www.metmuseum.org/art/collection/search/39666",'
            '"license":"CC0-1.0","secret":"must-not-leak"}]},'
            '"evidence_status":"insufficient_evidence","used_source_ids":["met-39666"]}',
    }])

    result = service.get_user_history("U1001")[0]

    assert result["factual_background"] == "馆藏器物为釉下青花瓷。"
    assert result["evidence_status"] == "grounded"
    assert result["citations"] == [{
        "source_id": "met-39666",
        "title": "Blue-and-White Dish",
        "source_url": "https://www.metmuseum.org/art/collection/search/39666",
        "license": "CC0-1.0",
    }]
    assert result["presentation_mode"] == "flat_front_back"


def test_v2_history_malformed_factual_background_degrades_to_empty(monkeypatch):
    service = MySQLService()
    monkeypatch.setattr(service, "execute_query", lambda query, params: [{
        "log_id": 3,
        "prompt_template_version": "cultural-product-rag-v2",
        "timestamp": datetime(2026, 7, 27, 12, 0, 0),
        "generation_time": 0,
        "image_url": None,
        "title": "异常记录",
        "content_length": 0,
        "user_rating": None,
        "download_count": 0,
        "user_age": None,
        "user_gender": None,
        "brief_json": '{"presentation_mode":"single_hero"}',
        "response_json": '{"product_name":"异常","factual_background":["not-an-object"],'
            '"evidence_status":"grounded","citations":[{"source_id":"forged"}]}',
    }])

    result = service.get_user_history("U1001")[0]

    assert result["factual_background"] == ""
    assert result["evidence_status"] == "insufficient_evidence"
    assert result["citations"] == []


def test_v2_history_does_not_leak_json_string_factual_background(monkeypatch):
    service = MySQLService()
    monkeypatch.setattr(service, "execute_query", lambda query, params: [{
        "log_id": 4,
        "prompt_template_version": "cultural-product-rag-v2",
        "timestamp": datetime(2026, 7, 27, 12, 0, 0),
        "generation_time": 0,
        "image_url": None,
        "title": "双重编码",
        "content_length": 0,
        "user_rating": None,
        "download_count": 0,
        "user_age": None,
        "user_gender": None,
        "brief_json": '{"presentation_mode":"single_hero"}',
        "response_json": '{"product_name":"双重编码","factual_background":"'
            '{\\"text\\":\\"不可泄漏\\",\\"status\\":\\"grounded\\",'
            '\\"citations\\":[]}\"}',
    }])

    result = service.get_user_history("U1001")[0]

    assert result["factual_background"] == "不可泄漏"
    assert result["evidence_status"] == "insufficient_evidence"
    assert result["citations"] == []
