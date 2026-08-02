from datetime import datetime

import pymysql

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
    assert observed["params"] == ("U1001", 50, 0)
    assert history[0]["log_id"] == 1
    assert history[0]["image_url"] == "/static/images/image_test.png"


def test_history_query_uses_pooled_dict_cursor_and_returns_records(monkeypatch):
    row = {
        "log_id": 9, "generation_kind": "cultural_product", "prompt_template_version": "v1",
        "timestamp": datetime(2026, 7, 29, 12, 0, 0), "prompt": "青花", "style": "水墨",
        "image_url": "/static/images/image_9.png", "title": "青花器", "content": "文案",
        "generation_time": 1.2, "content_length": 2, "user_rating": None, "download_count": 0,
        "user_age": None, "user_gender": None, "brief_json": None, "response_json": None,
        "data_origin": "production",
    }

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, _query, _params): return None
        def fetchall(self): return [row]

    class Connection:
        def __init__(self): self.cursor_args = None; self.closed = False
        def cursor(self, *args): self.cursor_args = args; return Cursor()
        def close(self): self.closed = True

    connection = Connection()
    service = MySQLService()
    monkeypatch.setattr(service, "_borrow_connection", lambda: connection)

    history = service.get_user_history("U1001")

    assert history[0]["log_id"] == 9
    assert connection.cursor_args == (pymysql.cursors.DictCursor,)
    assert connection.closed is True


def test_history_query_is_owner_scoped_descending_and_paged(monkeypatch):
    service = MySQLService()
    observed = {}
    def execute_query(query, params):
        observed['query'], observed['params'] = query, params
        return []
    monkeypatch.setattr(service, 'execute_query', execute_query)
    assert service.get_user_history('U1001', limit=20, offset=40) == []
    assert observed['params'] == ('U1001', 20, 40)
    assert 'WHERE user_id = %s' in observed['query'] and 'ORDER BY timestamp DESC' in observed['query']


def test_history_count_is_owner_scoped(monkeypatch):
    service = MySQLService()
    seen = {}
    monkeypatch.setattr(service, 'execute_query', lambda query, params: seen.update(query=query, params=params) or [{'total': 5}])
    assert service.get_user_history_count('U1001') == 5
    assert seen['params'] == ('U1001',) and 'WHERE user_id = %s' in seen['query']


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


def test_text_skill_history_uses_a_dedicated_allowlisted_record_type(monkeypatch):
    service = MySQLService()
    monkeypatch.setattr(service, "execute_query", lambda query, params: [{
        "log_id": 5, "generation_kind": "round17c_text_skill", "prompt_template_version": "round17c-text-skill-v1",
        "timestamp": datetime(2026, 7, 28, 18, 37, 4), "prompt": "灯", "style": "text-skill", "image_url": None,
        "title": "阅读灯", "content": "不得直接透传", "generation_time": 2, "content_length": 0,
        "user_rating": None, "download_count": 0, "user_age": None, "user_gender": None,
        "brief_json": "{}", "response_json": '{"run_id":"round-17c-business-20260728T103655Z-04934f7","rag_status":"grounded","source_ids":["met-65625"],"selected_skill_id":"retail-product-copy","skill_version":"1.0.0","actual_calls":{"qwen":2,"database_writes":1},"product_copy":"一盏适合阅读的折叠灯。","image_design_spec":"竹木与纸罩的连续设计说明。","secret":"must-not-leak"}',
    }])

    result = service.get_user_history("A2001")[0]

    assert result["record_type"] == "text_skill_generation"
    assert result["run_id"] == "round-17c-business-20260728T103655Z-04934f7"
    assert result["detail_url"].endswith(result["run_id"])
    assert result["selected_skill_id"] == "retail-product-copy"
    assert "image_url" not in result
    assert "secret" not in result and "product_copy" not in result


def test_text_skill_history_skips_malformed_audit_payload(monkeypatch):
    service = MySQLService()
    monkeypatch.setattr(service, "execute_query", lambda query, params: [{
        "log_id": 5, "generation_kind": "round17c_text_skill", "timestamp": datetime.now(), "prompt": "", "style": "", "image_url": None,
        "title": "", "content": "", "generation_time": 0, "content_length": 0, "user_rating": None, "download_count": 0,
        "user_age": None, "user_gender": None, "brief_json": "{}", "response_json": '{"run_id":"missing-output"}',
    }])
    assert service.get_user_history("A2001") == []


def test_agent_history_uses_a_dedicated_allowlisted_record_type(monkeypatch):
    service = MySQLService()
    monkeypatch.setattr(service, "execute_query", lambda query, params: [{
        "log_id": 73, "generation_kind": "agent_dialogue_mvp", "prompt_template_version": "agent-dialogue-mvp-v1",
        "timestamp": datetime(2026, 7, 30, 12, 0, 0), "prompt": "灯", "style": "agent-dialogue", "image_url": "/static/images/image_agent.png",
        "title": "三兔环光桌面灯", "content": "不得直接透传", "generation_time": 3.2, "content_length": 0,
        "user_rating": None, "download_count": 0, "user_age": None, "user_gender": None, "brief_json": "{}",
        "response_json": '{"agent_session_id":"session-73","product_name":"三兔环光桌面灯","image_url":"/static/images/image_agent.png",'
            '"evidence_status":"creative_only","used_source_ids":["source-1"],"selected_text_skill":"retail-product-copy",'
            '"selected_visual_skill":"heritage-motif-translation","product_design_summary":"安全摘要",'
            '"visual_direction":{"product_form":"环形结构","provider_payload":"must-not-leak"},"secret":"must-not-leak"}',
    }])

    result = service.get_user_history("U1001")[0]

    assert result["record_type"] == "agent_dialogue_generation"
    assert result["agent_session_id"] == "session-73"
    assert result["history_detail_url"] == "/api/v2/agent-design/history/generation-logs/73"
    assert result["visual_direction"] == {"product_form": "环形结构"}
    assert "secret" not in result and "provider_payload" not in result["visual_direction"]


def test_f3_agent_image_and_unknown_generation_have_explicit_history_projections(monkeypatch):
    service = MySQLService()
    rows = [
        {"log_id": 91, "generation_kind": "agent_action_image", "timestamp": datetime(2026, 8, 2, 10, 0),
         "prompt": "", "style": "agent-action", "image_url": "/static/images/f3.png", "title": "图片 V2", "content": "",
         "generation_time": 0, "content_length": 0, "user_rating": None, "download_count": 0, "user_age": None, "user_gender": None,
         "brief_json": None, "response_json": '{"positive_prompt":"must-not-leak"}', "data_origin": "production"},
        {"log_id": 92, "generation_kind": "new_provider_kind", "timestamp": datetime(2026, 8, 2, 11, 0),
         "prompt": "", "style": "unknown", "image_url": "", "title": "未知", "content": "must-not-leak",
         "generation_time": 0, "content_length": 0, "user_rating": None, "download_count": 0, "user_age": None, "user_gender": None,
         "brief_json": None, "response_json": '{"secret":"must-not-leak"}', "data_origin": "production"},
    ]
    monkeypatch.setattr(service, "execute_query", lambda *_args: rows)

    agent, unknown = service.get_user_history("U1001")

    assert agent == {
        "record_type": "agent_artifact_image", "log_id": 91, "product_name": "图片 V2",
        "image_url": "/static/images/f3.png", "timestamp": "2026-08-02T10:00:00",
        "generation_kind": "agent_action_image",
        "history_detail_url": "/api/v2/agent-design/history/generation-logs/91",
    }
    assert unknown["record_type"] == "unknown_generation"
    assert unknown["generation_kind"] == "new_provider_kind"
    assert "secret" not in unknown and "content" not in unknown
