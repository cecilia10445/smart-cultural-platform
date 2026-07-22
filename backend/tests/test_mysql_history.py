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
