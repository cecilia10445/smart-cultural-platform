import os
import uuid

import pytest
from dotenv import dotenv_values

from backend.services.mysql_service import MySQLService
from backend.tests.conftest import login


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MYSQL_INTEGRATION") != "1",
    reason="set RUN_MYSQL_INTEGRATION=1 to run the local MySQL integration test",
)


class StubImageResponse:
    status_code = 503


def mysql_service_for(database, config):
    return MySQLService(
        host=config["MYSQL_HOST"],
        port=int(config["MYSQL_PORT"]),
        username=config["MYSQL_USER"],
        password=config["MYSQL_PASSWORD"],
        database=database,
    )


def test_generate_persists_real_mysql_id_and_cleans_up(app_module, client, monkeypatch):
    config = dotenv_values("backend/.env")
    required = {"MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE"}
    if not required.issubset(config) or not all(config[key] for key in required):
        pytest.fail("RUN_MYSQL_INTEGRATION=1 requires complete local MySQL settings")

    production_database = config["MYSQL_DATABASE"]
    test_database = "aigc_platform_test"
    if production_database != "aigc_platform":
        pytest.fail("MYSQL_DATABASE must identify the production database for this integration test")
    assert production_database != test_database

    production_service = mysql_service_for("aigc_platform", config)
    test_service = mysql_service_for(test_database, config)
    monkeypatch.setattr(app_module, "mysql_service", test_service)

    model_stub_calls = []

    def deterministic_model_stub(_prompt, _style):
        model_stub_calls.append(True)
        return "https://example.invalid/integration.png", "integration title", "integration content"

    blocked_image_requests = []

    def image_download_stub(*_args, **_kwargs):
        blocked_image_requests.append(True)
        return StubImageResponse()

    monkeypatch.setattr(app_module, "generate_content", deterministic_model_stub)
    monkeypatch.setattr(app_module, "log_event", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("requests.get", image_download_stub)

    prompt = f"mysql-integration-{uuid.uuid4()}"
    style = "integration-style"
    production_before = production_service.execute_query(
        "SELECT COUNT(*) AS row_count FROM generation_logs"
    )[0]["row_count"]
    test_before = test_service.execute_query(
        "SELECT COUNT(*) AS row_count FROM generation_logs"
    )[0]["row_count"]

    response = None
    body = {}
    log_id = None
    persisted_rows = []
    test_during = None
    deleted_rows = 0
    production_after = None
    test_after = None

    try:
        token = login(client)
        response = client.post(
            "/api/generate",
            json={"prompt": prompt, "style": style},
            headers={"Authorization": f"Bearer {token}"},
        )
        body = response.get_json(silent=True) or {}
        log_id = body.get("log_id")
    finally:
        persisted_rows = test_service.execute_query(
            """
            SELECT id, user_id, prompt, style, title, content, image_url, data_origin
            FROM generation_logs
            WHERE prompt = %s AND style = %s
            """,
            (prompt, style),
        )
        test_during = test_service.execute_query(
            "SELECT COUNT(*) AS row_count FROM generation_logs"
        )[0]["row_count"]
        for persisted_row in persisted_rows:
            deleted_rows += test_service.execute_query(
                """
                DELETE FROM generation_logs
                WHERE id = %s AND prompt = %s AND style = %s
                """,
                (persisted_row["id"], prompt, style),
            )
        test_after = test_service.execute_query(
            "SELECT COUNT(*) AS row_count FROM generation_logs"
        )[0]["row_count"]
        production_after = production_service.execute_query(
            "SELECT COUNT(*) AS row_count FROM generation_logs"
        )[0]["row_count"]

    assert response is not None
    assert response.status_code == 200
    assert body["status"] == "success"
    assert isinstance(log_id, int) and log_id > 0
    assert len(persisted_rows) == 1
    assert test_during == test_before + 1
    row = persisted_rows[0]
    assert row["id"] == log_id
    assert row["user_id"] == "U1"
    assert row["prompt"] == prompt
    assert row["style"] == style
    assert row["title"] == "integration title"
    assert row["content"] == "integration content"
    assert row["image_url"] == "https://example.invalid/integration.png"
    assert row["data_origin"] == "production"
    assert len(model_stub_calls) == 1
    assert len(blocked_image_requests) == 1
    assert deleted_rows == 1
    assert test_after == test_before
    assert production_after == production_before
