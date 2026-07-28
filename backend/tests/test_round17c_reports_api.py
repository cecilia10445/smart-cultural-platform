import hashlib
import json


def _write_run(root, run_id, *, integrity=True, technical="completed", validity="comparable"):
    run = root / run_id
    run.mkdir()
    manifest = {"run_id": run_id, "started_at": "2026-07-28T00:00:00Z", "finished_at": "2026-07-28T00:01:00Z", "technical_status": technical, "evaluation_validity": validity, "integrity_status": "pending", "actual_calls": {"qwen": 0, "deepseek": 0, "image": 0, "database_writes": 0}, "model": {"name": "offline-qwen"}, "stable_error": None}
    report = {"evaluation_validity": validity, "winner": "baseline", "arms": {"baseline": {"product_copy": "清韵折叠阅读灯以竹木和纸罩营造温和阅读光线。", "image_design_spec": "画面展示展开的阅读灯与纸罩透光细节。", "used_source_ids": ["source-a"], "latency_ms": 10, "requests": 1, "dimensions": {"professional_readability": {"score": 4.0, "reason": "ok"}}}, "skill_guided": {"product_copy": "文创折叠阅读灯采用竹木与纸罩，适合安静阅读。", "image_design_spec": "画面强调折叠结构、竹木纹理和留白。", "used_source_ids": ["source-a"], "latency_ms": 11, "requests": 2, "tool_trajectory": []}}}
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (run / "normalized-report.json").write_text(json.dumps(report), encoding="utf-8")
    checksums = {name: hashlib.sha256((run / name).read_bytes()).hexdigest() for name in ("manifest.json", "normalized-report.json")}
    if not integrity:
        checksums["manifest.json"] = "0" * 64
    (run / "sha256sums.json").write_text(json.dumps(checksums), encoding="utf-8")
    return run


def test_round17c_api_is_admin_only_whitelisted_and_integrity_aware(app_module, client, monkeypatch, tmp_path):
    root = tmp_path / "reports"; root.mkdir()
    run_id = "round-17c-clean-20260728T000000Z-abcdef1"
    _write_run(root, run_id, integrity=False)
    monkeypatch.setattr(app_module, "ROUND17C_REPORT_ROOT", root)
    monkeypatch.setattr(app_module, "authenticate_user", lambda: {"user_id": "A1", "role": "admin"})
    listed = client.get("/api/dashboard/quality-reports").get_json()["data"]
    assert listed["runs"][0]["integrity_status"] == "failed"
    detail = client.get(f"/api/dashboard/quality-reports/{run_id}").get_json()["data"]
    assert detail["integrity_status"] == "failed"
    assert "manifest" not in detail and "sha256sums" not in detail
    assert client.get("/api/dashboard/quality-reports/../../backend/app.py").status_code in {404, 503}
    monkeypatch.setattr(app_module, "authenticate_user", lambda: {"user_id": "U1", "role": "user"})
    assert client.get("/api/dashboard/quality-reports").status_code == 403
