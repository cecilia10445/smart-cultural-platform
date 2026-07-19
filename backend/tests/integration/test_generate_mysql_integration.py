import os
import uuid

import pytest
import pymysql
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from backend.services.mysql_service import MySQLService
from backend.tests.conftest import login

pytestmark = pytest.mark.skipif(os.getenv("RUN_MYSQL_INTEGRATION") != "1", reason="set RUN_MYSQL_INTEGRATION=1 to start MySQL")


class StubImageResponse:
    status_code = 503


def test_generate_uses_migrated_disposable_mysql(app_module, client, monkeypatch, mysql_container_database):
    database = mysql_container_database
    inspector = sa.inspect(database["engine"])
    assert inspector.has_table("alembic_version")
    assert inspector.has_table("generation_logs")
    with database["engine"].connect() as connection:
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "0002"
        create_table = connection.exec_driver_sql("SHOW CREATE TABLE generation_logs").one()[1]
        historical = connection.execute(sa.text(
            "SELECT id,user_id,event_type,timestamp,prompt,style,image_url,title,content,"
            "generation_time,content_length,user_rating,download_count,user_age,user_gender,"
            "login_time,data_origin,created_at,updated_at FROM generation_logs WHERE id=:id"
        ), {"id": database["historical_expected"]["id"]}).mappings().one()
    expected_historical = database["historical_expected"]
    assert historical["id"] == expected_historical["id"]
    for field in (
        "user_id", "event_type", "timestamp", "prompt", "style", "image_url", "title", "content",
        "generation_time", "content_length", "user_rating", "download_count", "user_age", "user_gender",
        "login_time", "data_origin",
    ):
        assert historical[field] == expected_historical[field]
    assert historical["created_at"] is not None and historical["updated_at"] is not None
    columns = {column["name"]: column for column in inspector.get_columns("generation_logs")}
    assert len(columns) == 19
    expected_nullable = {
        "id": False, "user_id": False, "event_type": False, "timestamp": False,
        "prompt": True, "style": True, "image_url": True, "title": True,
        "content": True, "generation_time": True, "content_length": True,
        "user_rating": True, "download_count": False, "user_age": True,
        "user_gender": True, "login_time": True, "data_origin": True,
        "created_at": False, "updated_at": False,
    }
    assert {name: column["nullable"] for name, column in columns.items()} == expected_nullable
    expected_types = {
        "id": "BIGINT", "user_id": "VARCHAR(64)", "event_type": "VARCHAR(32)",
        "timestamp": "DATETIME", "prompt": "TEXT", "style": "VARCHAR(100)",
        "image_url": "VARCHAR(2048)", "title": "VARCHAR(255)", "content": "LONGTEXT",
        "generation_time": "DECIMAL(12, 3)", "content_length": "INTEGER",
        "user_rating": "DECIMAL(3, 2)", "download_count": "INTEGER",
        "user_age": "TINYINT", "user_gender": "TINYINT", "login_time": "DATETIME",
        "data_origin": "VARCHAR(20)", "created_at": "DATETIME", "updated_at": "DATETIME",
    }
    for name, expected_type in expected_types.items():
        assert expected_type in str(columns[name]["type"]).upper()
    assert inspector.get_pk_constraint("generation_logs")["constrained_columns"] == ["id"]
    indexes = {index["name"]: index["column_names"] for index in inspector.get_indexes("generation_logs")}
    assert indexes == {
        "idx_generation_logs_user_timestamp": ["user_id", "timestamp"],
        "idx_generation_logs_timestamp": ["timestamp"],
        "idx_generation_logs_style_timestamp": ["style", "timestamp"],
        "idx_generation_logs_event_timestamp": ["event_type", "timestamp"],
        "idx_generation_logs_updated_id": ["updated_at", "id"],
    }
    table_options = inspector.get_table_options("generation_logs")
    assert table_options["mysql_engine"] == "InnoDB"
    assert table_options["mysql_collate"] == "utf8mb4_0900_ai_ci"
    assert table_options["mysql_default charset"] == "utf8mb4"
    for name in ("id", "content_length", "download_count", "user_age", "user_gender"):
        assert columns[name]["type"].unsigned is True
    assert columns["timestamp"]["type"].fsp == 6
    assert columns["login_time"]["type"].fsp == 6
    assert columns["created_at"]["type"].fsp == 6
    assert columns["updated_at"]["type"].fsp == 6
    assert str(columns["download_count"]["default"]).strip("'") == "0"
    assert str(columns["data_origin"]["default"]).strip("'") == "production"
    assert columns["id"]["autoincrement"] is True
    assert "CURRENT_TIMESTAMP(6)" in str(columns["created_at"]["default"]).upper()
    assert "CURRENT_TIMESTAMP(6)" in str(columns["updated_at"]["default"]).upper()
    assert "ON UPDATE CURRENT_TIMESTAMP(6)" in create_table.upper()
    checks = {check["name"]: check["sqltext"].lower() for check in inspector.get_check_constraints("generation_logs")}
    constraint = checks["chk_generation_logs_data_origin"]
    assert all(value in constraint for value in ("production", "synthetic", "test", "public", "is null"))
    assert "ENGINE=InnoDB" in create_table
    grant_text = " ".join(database["grants"]).upper()
    assert "SELECT, INSERT, UPDATE" in grant_text
    assert all(privilege not in grant_text for privilege in ("DELETE", "DROP", "ALTER", "GRANT OPTION"))

    assert inspector.has_table("etl_batches")
    assert inspector.has_table("data_quality_results")
    batch_columns = {column["name"]: column for column in inspector.get_columns("etl_batches")}
    assert set(batch_columns) == {
        "batch_id", "pipeline_name", "status", "watermark_start_time", "watermark_start_id",
        "watermark_end_time", "watermark_end_id", "source_count", "hive_count", "output_count",
        "started_at", "finished_at", "error_code",
    }
    assert inspector.get_pk_constraint("etl_batches")["constrained_columns"] == ["batch_id"]
    assert {index["name"]: index["column_names"] for index in inspector.get_indexes("etl_batches")} == {
        "idx_etl_batches_pipeline_started": ["pipeline_name", "started_at"],
        "idx_etl_batches_status_started": ["status", "started_at"],
    }
    batch_checks = {check["name"]: check["sqltext"].upper() for check in inspector.get_check_constraints("etl_batches")}
    assert all(status in batch_checks["chk_etl_batches_status"] for status in ("RUNNING", "SUCCEEDED", "FAILED"))

    quality_columns = {column["name"]: column for column in inspector.get_columns("data_quality_results")}
    assert set(quality_columns) == {
        "id", "batch_id", "check_name", "status", "expected_value", "actual_value", "checked_at",
    }
    assert inspector.get_pk_constraint("data_quality_results")["constrained_columns"] == ["id"]
    assert {index["name"]: index["column_names"] for index in inspector.get_indexes("data_quality_results")} == {
        "idx_data_quality_results_batch_check": ["batch_id", "check_name"],
        "idx_data_quality_results_status_checked": ["status", "checked_at"],
    }
    quality_checks = {check["name"]: check["sqltext"].upper() for check in inspector.get_check_constraints("data_quality_results")}
    assert all(status in quality_checks["chk_data_quality_results_status"] for status in ("PASSED", "FAILED"))
    foreign_keys = inspector.get_foreign_keys("data_quality_results")
    assert [(key["constrained_columns"], key["referred_table"], key["referred_columns"]) for key in foreign_keys] == [
        (["batch_id"], "etl_batches", ["batch_id"])
    ]

    service = MySQLService(host=database["host"], port=database["port"], username=database["username"], password=database["password"], database=database["database"])
    monkeypatch.setattr(app_module, "mysql_service", service)
    model_calls = []
    network_calls = []
    monkeypatch.setattr(app_module, "generate_content", lambda prompt, style: (model_calls.append((prompt, style)) or ("https://example.invalid/integration.png", "integration title", "integration content")))
    monkeypatch.setattr(app_module, "log_event", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("requests.get", lambda *_args, **_kwargs: (network_calls.append(True) or StubImageResponse()))

    prompt = f"container-integration-{uuid.uuid4()}"
    response = client.post("/api/generate", json={"prompt": prompt, "style": "integration-style"}, headers={"Authorization": f"Bearer {login(client)}"})
    body = response.get_json()
    assert response.status_code == 200 and body["status"] == "success"
    with database["engine"].connect() as connection:
        row = connection.execute(sa.text("SELECT id,user_id,prompt,style,title,content,image_url,data_origin,created_at,updated_at FROM generation_logs WHERE id=:id"), {"id": body["log_id"]}).mappings().one()
    assert {key: row[key] for key in ("id", "user_id", "prompt", "style", "title", "content", "image_url", "data_origin")} == {"id": body["log_id"], "user_id": "U1", "prompt": prompt, "style": "integration-style", "title": "integration title", "content": "integration content", "image_url": "https://example.invalid/integration.png", "data_origin": "production"}
    assert row["created_at"] is not None
    assert row["updated_at"] is not None

    with database["engine"].begin() as connection:
        connection.execute(sa.text("UPDATE generation_logs SET updated_at = updated_at - INTERVAL 1 SECOND WHERE id=:id"), {"id": body["log_id"]})
        controlled_old_updated_at = connection.execute(sa.text("SELECT updated_at FROM generation_logs WHERE id=:id"), {"id": body["log_id"]}).scalar_one()
        connection.execute(sa.text("UPDATE generation_logs SET download_count=download_count+1 WHERE id=:id"), {"id": body["log_id"]})
        automatic_updated_at = connection.execute(sa.text("SELECT updated_at FROM generation_logs WHERE id=:id"), {"id": body["log_id"]}).scalar_one()
    assert automatic_updated_at > controlled_old_updated_at
    assert len(model_calls) == 1
    assert len(network_calls) == 1

    restricted_connection = pymysql.connect(
        host=database["host"],
        port=database["port"],
        user=database["username"],
        password=database["password"],
        database=database["database"],
        autocommit=True,
    )
    try:
        with restricted_connection.cursor() as cursor:
            with pytest.raises(pymysql.err.OperationalError):
                cursor.execute("DELETE FROM data_quality_results WHERE id = -1")
            with pytest.raises(pymysql.err.OperationalError):
                cursor.execute("ALTER TABLE etl_batches COMMENT = 'forbidden privilege probe'")
            with pytest.raises(pymysql.err.OperationalError):
                cursor.execute("DROP TABLE data_quality_results")
    finally:
        restricted_connection.close()

    with pytest.raises(RuntimeError, match="analytics contract downgrade is disabled"):
        command.downgrade(Config("alembic.ini"), "0001")
    post_downgrade_inspector = sa.inspect(database["engine"])
    assert post_downgrade_inspector.has_table("generation_logs")
    with database["engine"].connect() as connection:
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "0002"
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM generation_logs WHERE id = %s", (body["log_id"],)).scalar_one() == 1
        assert connection.exec_driver_sql("SELECT download_count FROM generation_logs WHERE id = %s", (body["log_id"],)).scalar_one() == 1
    assert post_downgrade_inspector.has_table("etl_batches")
    assert post_downgrade_inspector.has_table("data_quality_results")
