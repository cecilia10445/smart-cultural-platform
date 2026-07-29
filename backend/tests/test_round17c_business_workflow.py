from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.services import round17c_business as business
from evaluation.round17c_contract import Round17CFinalOutput


BRIEF = {
    "brief_version": "1.0",
    "brief": {
        "product_type": "折叠阅读灯", "cultural_source": {"source_type": "artifact", "name": "清代山水画意象", "era": "清代", "creator": None},
        "confirmed_facts": ["竹木灯体"], "form_and_material": "竹木灯体与半透明纸质扩散罩，便于折叠收纳。",
        "use_case": "书房阅读", "target_audience": "年轻阅读者", "presentation_mode": "single_hero",
        "visual_direction": {"preset_id": "ink-paper", "cultural_context": "山水留白", "medium": "纸墨与竹木", "palette": "米白、墨色", "composition": "主体清晰", "additional_requirements": "突出折叠关系"},
    },
}
FROZEN = {"status": "grounded", "sources": [{"source_id": "met-65625", "title": "fixture", "evidence": "fact", "license": "CC0", "source_url": "https://www.metmuseum.org/art/collection/search/65625"}]}
OUTPUT = Round17CFinalOutput(product_copy="清韵折叠阅读灯以竹木和纸罩带来温和阅读光线，适合书房静读与随行收纳。", image_design_spec="展开画面突出竹木支架、半透明纸罩和克制留白，清楚说明稳定展开与折叠收纳。", used_source_ids=["met-65625"])


def test_business_flow_uses_agent_result_and_seals_report(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(business, "freeze_evidence", lambda _: FROZEN)
    monkeypatch.setattr(business, "build_dashscope_client", lambda **kwargs: calls.append(kwargs) or object())
    monkeypatch.setattr(business, "build_model", lambda **kwargs: object())
    deps = SimpleNamespace(loaded_skill_id="museum-product-explainer", loaded_skill_sha256="a" * 64, catalog_sha256="b" * 64, trajectory=[{"tool": "load_generation_skill", "skill_id": "museum-product-explainer"}])
    monkeypatch.setattr(business, "run_guided_plan", lambda *args: (deps, {"skill_id": "museum-product-explainer"}, {"requests": 1, "latency_ms": 1}))
    monkeypatch.setattr(business, "run_guided_final", lambda *args: (OUTPUT, {"requests": 1, "latency_ms": 1}))
    result = business.generate_with_text_skill(BRIEF, api_key="test-key", model_name="qwen", base_url="https://example.invalid/v1", artifact_root=tmp_path)
    run = tmp_path / result["run_id"]
    assert result["selected_skill_id"] == "museum-product-explainer"
    assert result["experimental_text_skill"] is True
    assert calls[0]["trust_env"] is False
    assert json.loads((run / "manifest.json").read_text())["actual_calls"] == {"qwen": 0, "deepseek": 0, "image": 0, "database_writes": 0}
    assert (run / "sha256sums.json").exists()


def test_business_flow_persists_only_after_final_output_and_records_actual_write(monkeypatch, tmp_path):
    persisted = []
    monkeypatch.setattr(business, "freeze_evidence", lambda _: FROZEN)
    monkeypatch.setattr(business, "build_dashscope_client", lambda **_: object())
    monkeypatch.setattr(business, "build_model", lambda **_: object())
    deps = SimpleNamespace(loaded_skill_id="museum-product-explainer", loaded_skill_sha256="a" * 64, catalog_sha256="b" * 64, trajectory=[{"tool": "load_generation_skill", "skill_id": "museum-product-explainer"}])
    monkeypatch.setattr(business, "run_guided_plan", lambda *args: (deps, {"skill_id": "museum-product-explainer"}, {"requests": 1, "latency_ms": 1}))
    monkeypatch.setattr(business, "run_guided_final", lambda *args: (OUTPUT, {"requests": 1, "latency_ms": 1}))

    def persist(report):
        persisted.append(report)
        assert report["output"] == OUTPUT.model_dump()
        assert report["actual_calls"]["database_writes"] == 0
        return {"log_id": 42, "database_writes": 1, "transaction_status": "committed"}

    result = business.generate_with_text_skill(BRIEF, api_key="test-key", model_name="qwen", base_url="https://example.invalid/v1", artifact_root=tmp_path, persist_completed_generation=persist)
    report = json.loads((tmp_path / result["run_id"] / "normalized-report.json").read_text())
    assert len(persisted) == 1
    assert result["business_record_id"] == 42 and result["database_writes"] == 1
    assert report["business_record_id"] == 42
    assert report["actual_calls"]["database_writes"] == 1


def test_mysql_persistence_is_idempotent_and_uses_one_parameterized_insert(monkeypatch):
    from backend.services.mysql_service import MySQLService
    service = MySQLService.__new__(MySQLService)
    calls = []
    monkeypatch.setattr(service, "get_text_skill_generation_by_run_id", lambda *_: None)
    monkeypatch.setattr(service, "execute_insert", lambda query, params, max_retries: calls.append((query, params, max_retries)) or 77)
    generation = {"run_id": "round-17c-business-20260728T000000Z-abcdef1", "rag_status": "grounded", "source_ids": ["met-65625"], "selected_skill_id": "museum-product-explainer", "skill_version": "1.0.0", "skill_body_sha256": "a" * 64, "model_name": "qwen", "generation_time": 1.2, "actual_calls": {"qwen": 2}, "output": OUTPUT.model_dump()}
    assert service.persist_text_skill_generation(user_id="U1", brief=BRIEF["brief"], generation=generation) == {"log_id": 77, "database_writes": 1, "transaction_status": "committed"}
    assert len(calls) == 1 and calls[0][2] == 0 and "INSERT INTO generation_logs" in calls[0][0]
    monkeypatch.setattr(service, "get_text_skill_generation_by_run_id", lambda *_: {"log_id": 77})
    assert service.persist_text_skill_generation(user_id="U1", brief=BRIEF["brief"], generation=generation) == {"log_id": 77, "database_writes": 0, "transaction_status": "already_committed"}
    assert len(calls) == 1


def test_mysql_readback_is_allowlisted(monkeypatch):
    from backend.services.mysql_service import MySQLService
    service = MySQLService.__new__(MySQLService)
    run_id = "round-17c-business-20260728T000000Z-abcdef1"
    monkeypatch.setattr(service, "get_text_skill_generation_by_run_id", lambda *_: {"log_id": 9, "response_json": json.dumps({"run_id": run_id, "product_copy": "文案", "image_design_spec": "说明", "selected_skill_id": "museum-product-explainer", "secret": "must-not-leak"})})
    body = service.read_text_skill_generation(user_id="U1", run_id=run_id)
    assert body["log_id"] == 9 and body["product_copy"] == "文案"
    assert "secret" not in body


def test_storage_preflight_uses_existing_table_and_rolls_back(monkeypatch):
    from backend.services import mysql_service as module
    from backend.services.mysql_service import MySQLService

    events = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, query): events.append(query)
    class Connection:
        def cursor(self, *_args, **_kwargs): return Cursor()
        def begin(self): events.append("BEGIN")
        def rollback(self): events.append("ROLLBACK")
        def close(self): events.append("CLOSE")
    settings = SimpleNamespace(mysql_read_timeout_seconds=1, mysql_write_timeout_seconds=1)
    service = MySQLService.__new__(MySQLService)
    service.host, service.port, service.username, service.password, service.database, service.connect_timeout = "host", 3306, "user", "password", "test_db", 1
    monkeypatch.setattr(module, "load_settings", lambda: settings)
    monkeypatch.setattr(service, "_borrow_connection", lambda: Connection())
    assert service.preflight_text_skill_generation_storage() == {"database": "test_db", "table": "generation_logs", "transaction_status": "rolled_back"}
    assert any("generation_logs" in event for event in events) and events[-2:] == ["ROLLBACK", "CLOSE"]


def test_business_flow_blocks_before_model_when_evidence_is_not_grounded(monkeypatch, tmp_path):
    monkeypatch.setattr(business, "freeze_evidence", lambda _: {"status": "insufficient_evidence", "sources": []})
    monkeypatch.setattr(business, "build_dashscope_client", lambda **kwargs: pytest.fail("model must not be constructed"))
    with pytest.raises(business.BusinessGenerationError, match="RAG_EVIDENCE_REQUIRED"):
        business.generate_with_text_skill(BRIEF, api_key="test-key", model_name="qwen", base_url="https://example.invalid/v1", artifact_root=tmp_path)


def test_freeze_evidence_accepts_the_normalized_api_brief_without_rewrapping():
    from evaluation.round17c_runner import freeze_evidence
    from backend.domain.cultural_product_brief import validate_cultural_product_request
    frozen = freeze_evidence(validate_cultural_product_request(BRIEF))
    assert frozen["status"] == "grounded" and "met-65625" in {item["source_id"] for item in frozen["sources"]}


def test_business_report_reader_fails_closed_for_tampering(tmp_path):
    from backend.round17c_business_reports import public_business_run
    run = tmp_path / "round-17c-business-20260728T000000Z-abcdef1"; run.mkdir()
    manifest = {"run_id": run.name, "started_at": "2026-07-28T00:00:00Z", "technical_status": "completed"}
    report = {"output": OUTPUT.model_dump(), "rag_status": "grounded", "source_ids": ["met-65625"], "selected_skill_id": "museum-product-explainer", "skill_version": "1.0.0", "skill_body_sha256": "a" * 64, "tool_trajectory": [], "actual_calls": {"qwen": 2, "deepseek": 0, "image": 0, "database_writes": 0}}
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf8"); (run / "normalized-report.json").write_text(json.dumps(report), encoding="utf8")
    from evaluation.round17c_runner import seal_run
    seal_run(run)
    assert public_business_run(tmp_path, run.name)["output"]["product_copy"] == OUTPUT.product_copy
    (run / "unexpected.txt").write_text("tamper", encoding="utf8")
    assert public_business_run(tmp_path, run.name)["report"] is None


def test_experimental_api_keeps_existing_v2_route_separate(app_module, client, monkeypatch, tmp_path):
    from backend.tests.conftest import login
    token = login(client)
    called = {}
    writes = []
    def fake_generate(brief, **kwargs):
        called["brief"] = brief; called.update(kwargs)
        receipt = kwargs["persist_completed_generation"]({"run_id": "round-17c-business-20260728T000000Z-abcdef1", "output": OUTPUT.model_dump(), "actual_calls": {"qwen": 2}, "source_ids": ["met-65625"]})
        writes.append(receipt)
        return {"status": "success", "experimental_text_skill": True, "run_id": "round-17c-business-20260728T000000Z-abcdef1", "generation_time": 1.0, **OUTPUT.model_dump(), "sources": FROZEN["sources"], "selected_skill_id": "museum-product-explainer"}
    import backend.services.round17c_business as service
    monkeypatch.setattr(service, "generate_with_text_skill", fake_generate)
    monkeypatch.setattr(app_module.mysql_service, "persist_text_skill_generation", lambda **kwargs: {"log_id": 88, "database_writes": 1, "transaction_status": "committed"}, raising=False)
    monkeypatch.setattr(app_module, "ROUND17C_BUSINESS_REPORT_ROOT", tmp_path)
    response = client.post("/api/v2/cultural-products/generate-with-text-skill", json=BRIEF, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.get_json()["experimental_text_skill"] is True
    assert called["brief"]["product_type"] == "折叠阅读灯"
    assert writes == [{"log_id": 88, "database_writes": 1, "transaction_status": "committed"}]


@pytest.mark.parametrize(("field", "code"), [
    ("front_design_requirements", "INVALID_FRONT_DESIGN_REQUIREMENTS"),
    ("back_design_requirements", "INVALID_BACK_DESIGN_REQUIREMENTS"),
    ("side_design_requirements", "INVALID_SIDE_DESIGN_REQUIREMENTS"),
])
def test_three_view_brief_errors_are_client_errors_before_model(app_module, client, monkeypatch, field, code):
    from backend.tests.conftest import login
    import backend.services.round17c_business as service

    payload = json.loads(json.dumps(BRIEF))
    payload["brief"].update({
        "presentation_mode": "three_view",
        "front_design_requirements": "正面强调山水留白。",
        "back_design_requirements": "背面安排使用说明。",
        "side_design_requirements": "侧面交代厚度与连接。",
    })
    payload["brief"][field] = ""
    monkeypatch.setattr(service, "generate_with_text_skill", lambda *_args, **_kwargs: pytest.fail("model must not be called"))
    response = client.post("/api/v2/cultural-products/generate-with-text-skill", json=payload, headers={"Authorization": f"Bearer {login(client)}"})
    body = response.get_json()
    assert response.status_code == 400
    assert body["code"] == code and body["field"] == field and body["retryable"] is False


def test_three_view_preflight_validates_browser_contract_without_constructing_model(monkeypatch):
    from evaluation import round17c_three_view_preflight as preflight

    payload = json.loads(json.dumps(BRIEF))
    payload["brief"].update({
        "presentation_mode": "three_view",
        "front_design_requirements": "正面以山水留白组织核心识别图案与产品名称。",
        "back_design_requirements": "背面保留来源说明区与低饱和辅助纹样，不重复正面主体。",
        "side_design_requirements": "侧面说明折叠厚度、竹木连接和连续边饰。",
    })
    monkeypatch.setattr(preflight, "freeze_evidence", lambda _brief: FROZEN)
    storage = type("Storage", (), {"preflight_text_skill_generation_storage": lambda self: {"database": "test", "table": "generation_logs", "transaction_status": "rolled_back"}})()
    result = preflight.preflight(payload, storage)
    assert result["status"] == "ready" and result["source_ids"] == ["met-65625"]
    assert result["model_calls"] == {"qwen": 0, "deepseek": 0, "image": 0}


def test_experimental_readback_endpoint_is_owned_and_allowlisted(app_module, client, monkeypatch):
    from backend.tests.conftest import login
    token = login(client)
    run_id = "round-17c-business-20260728T000000Z-abcdef1"
    monkeypatch.setattr(app_module.mysql_service, "read_text_skill_generation", lambda **kwargs: {"log_id": 88, "run_id": run_id, "product_copy": "文案", "image_design_spec": "说明"}, raising=False)
    monkeypatch.setattr(app_module, "text_skill_artifact_integrity", lambda _run_id: "verified")
    response = client.get(f"/api/v2/cultural-products/text-skill-generations/{run_id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.get_json()["data"]["log_id"] == 88


def test_text_skill_readback_rejects_unverified_artifact(app_module, client, monkeypatch):
    from backend.tests.conftest import login
    run_id = "round-17c-business-20260728T000000Z-abcdef1"
    monkeypatch.setattr(app_module.mysql_service, "read_text_skill_generation", lambda **kwargs: {"log_id": 88, "run_id": run_id}, raising=False)
    monkeypatch.setattr(app_module, "text_skill_artifact_integrity", lambda _run_id: "failed")
    response = client.get(f"/api/v2/cultural-products/text-skill-generations/{run_id}", headers={"Authorization": f"Bearer {login(client)}"})
    assert response.status_code == 409
    assert response.get_json()["code"] == "TEXT_SKILL_ARTIFACT_UNAVAILABLE"


def test_text_skill_readback_does_not_cross_user_boundaries(app_module, client, monkeypatch):
    from backend.tests.conftest import login
    run_id = "round-17c-business-20260728T000000Z-abcdef1"
    seen = []
    def readback(*, user_id, run_id):
        seen.append(user_id)
        return {"log_id": 88, "run_id": run_id} if user_id == "U1" else None
    monkeypatch.setattr(app_module.mysql_service, "read_text_skill_generation", readback, raising=False)
    monkeypatch.setattr(app_module, "text_skill_artifact_integrity", lambda _run_id: "verified")
    owner = client.get(f"/api/v2/cultural-products/text-skill-generations/{run_id}", headers={"Authorization": f"Bearer {login(client)}"})
    other = client.get(f"/api/v2/cultural-products/text-skill-generations/{run_id}", headers={"Authorization": f"Bearer {login(client, 'admin', 'admin-password', 'admin')}"})
    assert owner.status_code == 200 and other.status_code == 404 and seen == ["U1", "A1"]


def test_history_keeps_user_ownership_and_marks_text_artifact_status(app_module, client, monkeypatch):
    from backend.tests.conftest import login
    seen = []
    def history_for_owner(user_id, **_kwargs):
        seen.append(user_id)
        return [{"log_id": 5, "record_type": "text_skill_generation", "run_id": "round-17c-business-20260728T103655Z-04934f7", "product_copy_summary": "文案", "image_design_spec_summary": "说明", "selected_skill_id": "retail-product-copy", "source_ids": ["met-65625"], "detail_url": "/api/v2/cultural-products/text-skill-generations/round-17c-business-20260728T103655Z-04934f7"}]
    monkeypatch.setattr(app_module.mysql_service, "get_user_history", history_for_owner, raising=False)
    monkeypatch.setattr(app_module, "text_skill_artifact_integrity", lambda _run_id: "verified")
    token = login(client)
    response = client.get("/api/user/history", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200 and seen == ["U1"]
    record = response.get_json()["data"][0]
    assert record["artifact_integrity"] == "verified" and "judge" not in json.dumps(record).lower()


def test_business_report_api_is_admin_only_and_fail_closed(app_module, client, monkeypatch, tmp_path):
    from backend.round17c_business_reports import public_business_run
    run = tmp_path / "round-17c-business-20260728T000000Z-abcdef1"; run.mkdir()
    (run / "manifest.json").write_text(json.dumps({"run_id": run.name, "started_at": "2026-07-28T00:00:00Z", "technical_status": "completed"}), encoding="utf8")
    (run / "normalized-report.json").write_text(json.dumps({"output": OUTPUT.model_dump(), "rag_status": "grounded", "source_ids": ["met-65625"], "selected_skill_id": "museum-product-explainer", "skill_version": "1.0.0", "skill_body_sha256": "a" * 64, "tool_trajectory": [{"tool": "load_generation_skill"}], "actual_calls": {"qwen": 2, "deepseek": 0, "image": 0, "database_writes": 0}}), encoding="utf8")
    from evaluation.round17c_runner import seal_run
    seal_run(run)
    monkeypatch.setattr(app_module, "ROUND17C_BUSINESS_REPORT_ROOT", tmp_path)
    monkeypatch.setattr(app_module, "authenticate_user", lambda: {"user_id": "A1", "role": "admin"})
    detail = client.get(f"/api/dashboard/business-generation-reports/{run.name}").get_json()["data"]
    assert detail["output"]["product_copy"] == OUTPUT.product_copy
    assert "judge" not in json.dumps(detail).lower()
    (run / "unlisted.txt").write_text("tamper", encoding="utf8")
    assert client.get(f"/api/dashboard/business-generation-reports/{run.name}").get_json()["data"]["report"] is None
    monkeypatch.setattr(app_module, "authenticate_user", lambda: {"user_id": "U1", "role": "user"})
    assert client.get("/api/dashboard/business-generation-reports").status_code == 403
