import json
import pytest

from backend.domain.cultural_product_brief import validate_cultural_product_request
from backend.services.generation_tracking import GenerationTracker
from evaluation.generation_quality_report import build_quality_report, load_report_rows
import evaluation.generation_quality_report as quality_report


def brief():
    return validate_cultural_product_request({"brief_version": "1.0", "brief": {
        "product_type": "书签", "cultural_source": {"source_type": "artifact", "name": "青花纹样", "era": None, "creator": None},
        "confirmed_facts": [], "form_and_material": "纸质", "use_case": "商店", "target_audience": None,
        "visual_direction": {"preset_id": "blue-white-pattern", "cultural_context": "青花瓷", "medium": "釉下青花", "palette": "靛青瓷白", "composition": "中心纹样", "additional_requirements": None},
    }})


class Database:
    def __init__(self):
        self.inserts, self.updates = [], []

    def execute_insert(self, query, params):
        self.inserts.append((query, params))
        return len(self.inserts)

    def execute_query(self, query, params, max_retries=0):
        self.updates.append((query, params, max_retries))
        return 1


def test_tracker_uses_one_attempt_two_metrics_and_content_free_hash():
    database = Database()
    tracker = GenerationTracker(database, "request-a", "U1", "test", brief(), "cultural-product-v1")
    tracker.start()
    tracker.record_metric("text_generation", "qwen", "SUCCEEDED", tracker.started_at, usage={"input_tokens": 2, "output_tokens": 3, "total_tokens": 5})
    tracker.record_metric("image_generation", "wan", "SUCCEEDED", tracker.started_at, image_count=1)
    tracker.succeed(99)
    assert len(database.inserts) == 3
    assert len(database.updates) == 1
    serialized = json.dumps(database.inserts, ensure_ascii=False)
    assert "青花纹样" not in serialized
    assert len(database.inserts[0][1][-1]) == 64
    assert database.updates[0][1][0] == "SUCCEEDED"
    assert database.updates[0][1][3] == 99


def test_tracker_hash_is_stable_and_distinct_request_ids_do_not_share_rows():
    first = GenerationTracker(Database(), "request-one", "U1", "test", brief(), "cultural-product-v1")
    second = GenerationTracker(Database(), "request-two", "U1", "test", brief(), "cultural-product-v1")
    assert first.brief_sha256(brief()) == second.brief_sha256(brief())
    assert first.request_id != second.request_id


def test_quality_report_is_content_free_and_keeps_missing_usage_null():
    attempts = [
        {"request_id": "r1", "status": "SUCCEEDED", "failed_stage": None, "error_code": None, "brief_sha256": "a" * 64},
        {"request_id": "r2", "status": "FAILED", "failed_stage": "image_generation", "error_code": "MODEL_REQUEST_FAILED", "brief_sha256": "b" * 64},
    ]
    metrics = [{"request_id": "r1", "stage": "text_generation", "latency_ms": 21, "input_tokens": None, "output_tokens": None, "total_tokens": None}]
    report = build_quality_report(attempts, metrics)
    assert report["failed_count"] == 1
    assert report["failure_distribution"] == {"image_generation:MODEL_REQUEST_FAILED": 1}
    assert report["token_usage"] == {"input_tokens": None, "output_tokens": None, "total_tokens": None}
    assert "prompt" not in json.dumps(report).lower()


def test_report_loader_only_queries_observability_tables():
    class Service:
        def execute_query(self, query, _params, max_retries=0):
            assert "generation_attempts" in query or "model_call_metrics" in query
            assert max_retries == 0
            return []
    assert load_report_rows(Service()) == ([], [])


def test_quality_report_cli_writes_sanitized_report_and_candidates(monkeypatch, tmp_path):
    class Service:
        def __init__(self, *_args, **_kwargs): pass
        def connect(self): return True
        def execute_query(self, query, _params, max_retries=0):
            if "generation_attempts" in query:
                return [{"request_id": "r1", "status": "FAILED", "failed_stage": "text_generation", "error_code": "MODEL_REQUEST_FAILED", "brief_sha256": "a" * 64}]
            return [{"request_id": "r1", "stage": "text_generation", "latency_ms": 4, "input_tokens": 1, "output_tokens": 2, "total_tokens": 3}]
    class Settings:
        mysql_host = "localhost"; mysql_port = 3306; mysql_user = "user"; mysql_password = "secret"; mysql_database = "test"
    monkeypatch.setattr("backend.services.mysql_service.MySQLService", Service)
    monkeypatch.setattr("backend.config.load_settings", lambda: Settings())
    output, candidates = tmp_path / "report.json", tmp_path / "candidates.json"
    quality_report.main(["--output", str(output), "--failure-candidates", str(candidates)])
    rendered = output.read_text(encoding="utf-8") + candidates.read_text(encoding="utf-8")
    assert "MODEL_REQUEST_FAILED" in rendered and "secret" not in rendered and "prompt" not in rendered.lower()


def test_quality_report_cli_exits_stably_when_database_unavailable(monkeypatch, tmp_path):
    class Service:
        def __init__(self, *_args, **_kwargs): pass
        def connect(self): return False
    monkeypatch.setattr("backend.services.mysql_service.MySQLService", Service)
    with pytest.raises(SystemExit, match="database unavailable"):
        quality_report.main(["--output", str(tmp_path / "nope.json")])
