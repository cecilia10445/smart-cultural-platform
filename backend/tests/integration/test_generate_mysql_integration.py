import os
import uuid

import pytest
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
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "0001"
        create_table = connection.exec_driver_sql("SHOW CREATE TABLE generation_logs").one()[1]
    columns = {column["name"]: column for column in inspector.get_columns("generation_logs")}
    assert len(columns) == 17
    expected_nullable = {
        "id": False, "user_id": False, "event_type": False, "timestamp": False,
        "prompt": True, "style": True, "image_url": True, "title": True,
        "content": True, "generation_time": True, "content_length": True,
        "user_rating": True, "download_count": False, "user_age": True,
        "user_gender": True, "login_time": True, "data_origin": True,
    }
    assert {name: column["nullable"] for name, column in columns.items()} == expected_nullable
    expected_types = {
        "id": "BIGINT", "user_id": "VARCHAR(64)", "event_type": "VARCHAR(32)",
        "timestamp": "DATETIME", "prompt": "TEXT", "style": "VARCHAR(100)",
        "image_url": "VARCHAR(2048)", "title": "VARCHAR(255)", "content": "LONGTEXT",
        "generation_time": "DECIMAL(12, 3)", "content_length": "INTEGER",
        "user_rating": "DECIMAL(3, 2)", "download_count": "INTEGER",
        "user_age": "TINYINT", "user_gender": "TINYINT", "login_time": "DATETIME",
        "data_origin": "VARCHAR(20)",
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
    }
    table_options = inspector.get_table_options("generation_logs")
    assert table_options["mysql_engine"] == "InnoDB"
    assert table_options["mysql_collate"] == "utf8mb4_0900_ai_ci"
    assert table_options["mysql_default charset"] == "utf8mb4"
    for name in ("id", "content_length", "download_count", "user_age", "user_gender"):
        assert columns[name]["type"].unsigned is True
    assert columns["timestamp"]["type"].fsp == 6
    assert columns["login_time"]["type"].fsp == 6
    assert str(columns["download_count"]["default"]).strip("'") == "0"
    assert str(columns["data_origin"]["default"]).strip("'") == "production"
    assert columns["id"]["autoincrement"] is True
    checks = {check["name"]: check["sqltext"].lower() for check in inspector.get_check_constraints("generation_logs")}
    constraint = checks["chk_generation_logs_data_origin"]
    assert all(value in constraint for value in ("production", "synthetic", "test", "public", "is null"))
    assert "ENGINE=InnoDB" in create_table
    grant_text = " ".join(database["grants"]).upper()
    assert "SELECT, INSERT, UPDATE" in grant_text
    assert all(privilege not in grant_text for privilege in ("DELETE", "DROP", "ALTER", "GRANT OPTION"))

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
        row = connection.execute(sa.text("SELECT id,user_id,prompt,style,title,content,image_url,data_origin FROM generation_logs WHERE id=:id"), {"id": body["log_id"]}).mappings().one()
    assert row == {"id": body["log_id"], "user_id": "U1", "prompt": prompt, "style": "integration-style", "title": "integration title", "content": "integration content", "image_url": "https://example.invalid/integration.png", "data_origin": "production"}
    assert len(model_calls) == 1
    assert len(network_calls) == 1

    with pytest.raises(RuntimeError, match="baseline downgrade is disabled"):
        command.downgrade(Config("alembic.ini"), "base")
    post_downgrade_inspector = sa.inspect(database["engine"])
    assert post_downgrade_inspector.has_table("generation_logs")
    with database["engine"].connect() as connection:
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "0001"
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM generation_logs WHERE id = %s", (body["log_id"],)).scalar_one() == 1
