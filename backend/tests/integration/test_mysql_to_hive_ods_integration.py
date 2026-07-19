import os
import subprocess
import sys
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import pymysql
import sqlalchemy as sa


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "mysql_to_hive_ods.py"
HIVE_DATABASE_PREFIX = "aigc_platform_round10a_test"
SOURCE_COLUMNS = "id,user_id,event_type,timestamp,prompt,style,image_url,title,content,generation_time,content_length,user_rating,download_count,user_age,user_gender,login_time,data_origin,created_at,updated_at"
SOURCE_FIELD_NAMES = SOURCE_COLUMNS.split(",")
HIVE_ROW_FIELDS = SOURCE_FIELD_NAMES + ["ingested_at", "extract_date", "etl_batch_id"]
INTEGER_FIELDS = {"id", "content_length", "download_count", "user_age", "user_gender", "etl_batch_id"}
DECIMAL_FIELDS = {"generation_time", "user_rating"}
TIMESTAMP_FIELDS = {"timestamp", "login_time", "created_at", "updated_at", "ingested_at"}
QUALITY_CHECK_NAMES = {
    "source_count_equals_hive_batch_count",
    "id_not_null",
    "id_unique_in_batch",
    "updated_at_not_null",
    "data_origin_allowed",
    "watermark_within_frozen_bounds",
}

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_HIVE_INTEGRATION") != "1",
    reason="set RUN_HIVE_INTEGRATION=1 to use real HDFS, HiveServer2, and system Spark",
)


def run_ingestion(database, hive_database):
    env = os.environ.copy()
    env.update({
        "MYSQL_HOST": database["host"], "MYSQL_PORT": str(database["port"]),
        "MYSQL_USER": database["etl_username"], "MYSQL_PASSWORD": database["etl_password"],
        "MYSQL_DATABASE": database["database"], "HIVE_DATABASE": hive_database,
        "HIVE_METASTORE_URI": "thrift://localhost:9083",
        "HDFS_WAREHOUSE_DIR": "hdfs://localhost:9000/user/hive/warehouse",
    })
    env.pop("PYSPARK_PYTHON", None)
    env.pop("PYSPARK_DRIVER_PYTHON", None)
    return subprocess.run(["/opt/spark/bin/spark-submit", str(SCRIPT)], cwd=ROOT, env=env, capture_output=True, text=True, check=False, timeout=300)


def hive_batch_count(hive_database, batch_id):
    result = subprocess.run(
        ["/opt/hive/bin/beeline", "-u", "jdbc:hive2://localhost:10000/default", "-n", "lily",
         "--silent=true", "--showHeader=false", "--outputformat=tsv2",
         "-e", f"SELECT COUNT(*) FROM {hive_database}.ods_generation_logs WHERE etl_batch_id={batch_id}"],
        env={**os.environ, "HADOOP_HOME": "/opt/hadoop", "HADOOP_PREFIX": "/opt/hadoop"},
        capture_output=True, text=True, check=False, timeout=60,
    )
    assert result.returncode == 0, result.stderr[-1000:]
    return int(result.stdout.strip().splitlines()[-1])


def hive_batch_rows(hive_database, batch_id):
    result = subprocess.run(
        ["/opt/hive/bin/beeline", "-u", "jdbc:hive2://localhost:10000/default", "-n", "lily",
         "--silent=true", "--showHeader=false", "--outputformat=tsv2",
         "-e", f"SELECT user_id,prompt,style,title,content,data_origin,download_count "
               f"FROM {hive_database}.ods_generation_logs WHERE etl_batch_id={batch_id}"],
        env={**os.environ, "HADOOP_HOME": "/opt/hadoop", "HADOOP_PREFIX": "/opt/hadoop"},
        capture_output=True, text=True, check=False, timeout=60,
    )
    assert result.returncode == 0, result.stderr[-1000:]
    return {tuple(line.split("\t")) for line in result.stdout.splitlines() if "\t" in line}


def hive_identifier(field):
    return f"`{field}`" if field == "timestamp" else field


def parse_hive_value(field, value):
    if value == "NULL":
        return None
    if field in INTEGER_FIELDS:
        return int(value)
    if field in DECIMAL_FIELDS:
        return Decimal(value)
    if field in TIMESTAMP_FIELDS:
        if "." in value:
            seconds, fraction = value.split(".", 1)
            value = f"{seconds}.{fraction.ljust(6, '0')}"
        return datetime.fromisoformat(value)
    if field == "extract_date":
        return date.fromisoformat(value)
    return value


def hive_batch_records(hive_database, batch_id):
    projection = ",".join(hive_identifier(field) for field in HIVE_ROW_FIELDS)
    result = subprocess.run(
        ["/opt/hive/bin/beeline", "-u", "jdbc:hive2://localhost:10000/default", "-n", "lily",
         "--silent=true", "--showHeader=false", "--outputformat=tsv2",
         "-e", f"SET hive.fetch.task.conversion=more; SELECT {projection} "
               f"FROM {hive_database}.ods_generation_logs WHERE etl_batch_id={batch_id}"],
        env={**os.environ, "HADOOP_HOME": "/opt/hadoop", "HADOOP_PREFIX": "/opt/hadoop"},
        capture_output=True, text=True, check=False, timeout=60,
    )
    assert result.returncode == 0, result.stderr[-1000:]
    records = []
    for line in result.stdout.splitlines():
        values = line.split("\t")
        if len(values) == len(HIVE_ROW_FIELDS):
            records.append({field: parse_hive_value(field, value) for field, value in zip(HIVE_ROW_FIELDS, values)})
    return sorted(records, key=lambda record: record["id"])


def source_snapshot(connection):
    return connection.execute(sa.text(f"SELECT {SOURCE_COLUMNS} FROM generation_logs ORDER BY id")).mappings().all()


def assert_successful_quality_checks(connection, batch_id):
    checks = connection.execute(sa.text(
        "SELECT check_name,status,expected_value,actual_value FROM data_quality_results "
        "WHERE batch_id=:batch_id ORDER BY check_name"
    ), {"batch_id": batch_id}).mappings().all()
    assert len(checks) == 6
    assert {check["check_name"] for check in checks} == QUALITY_CHECK_NAMES
    assert {check["status"] for check in checks} == {"PASSED"}
    assert all(check["expected_value"] is not None and check["actual_value"] is not None for check in checks)


def assert_hive_matches_source(records, source_rows, batch_id):
    expected_by_id = {row["id"]: row for row in source_rows}
    assert {record["id"] for record in records} == set(expected_by_id)
    assert all(record["ingested_at"] is not None for record in records)
    assert all(record["extract_date"] == record["ingested_at"].date() for record in records)
    assert all(record["etl_batch_id"] == batch_id for record in records)
    for record in records:
        expected = expected_by_id[record["id"]]
        for field in SOURCE_FIELD_NAMES:
            assert record[field] == expected[field], field


def test_incremental_mysql_to_real_hive_ods(mysql_container_database):
    database = mysql_container_database
    hive_database = f"{HIVE_DATABASE_PREFIX}_{uuid.uuid4().hex[:12]}"
    restricted = pymysql.connect(host=database["host"], port=database["port"], user=database["etl_username"],
                                 password=database["etl_password"], database=database["database"], autocommit=True)
    try:
        with restricted.cursor() as cursor:
            allowed = (
                "SELECT COUNT(*) FROM generation_logs",
                "SELECT COUNT(*) FROM etl_batches",
                "SELECT COUNT(*) FROM data_quality_results",
            )
            for statement in allowed:
                cursor.execute(statement)
            cursor.execute(
                "INSERT INTO etl_batches (pipeline_name,status) VALUES ('permission_probe','RUNNING')"
            )
            permission_batch_id = cursor.lastrowid
            cursor.execute(
                "UPDATE etl_batches SET status='FAILED',error_code='PERMISSION_PROBE' WHERE batch_id=%s",
                (permission_batch_id,),
            )
            cursor.execute(
                "INSERT INTO data_quality_results (batch_id,check_name,status,expected_value,actual_value) "
                "VALUES (%s,'permission_probe','PASSED','allowed','allowed')",
                (permission_batch_id,),
            )
            for statement in (
                "INSERT INTO generation_logs (user_id,event_type,timestamp,prompt,style) VALUES ('forbidden','generate',CURRENT_TIMESTAMP(6),'forbidden','forbidden')",
                "UPDATE generation_logs SET download_count=1 WHERE id=-1",
                "DELETE FROM generation_logs WHERE id=-1",
                "DELETE FROM etl_batches WHERE batch_id=-1",
                "ALTER TABLE generation_logs ADD COLUMN forbidden_column INT",
                "DROP TABLE data_quality_results",
                "GRANT SELECT ON *.* TO 'nobody'@'%'",
            ):
                with pytest.raises(pymysql.err.OperationalError):
                    cursor.execute(statement)
    finally:
        restricted.close()
    with database["engine"].begin() as connection:
        before = connection.exec_driver_sql("SELECT COUNT(*) FROM generation_logs").scalar_one()
        connection.execute(sa.text(
            "INSERT INTO generation_logs (user_id,event_type,timestamp,prompt,style,title,content,"
            "generation_time,content_length,download_count,data_origin) VALUES "
            "('round10a-a','generate',CURRENT_TIMESTAMP(6),'one','style','title','content',1.000,7,0,'test'),"
            "('round10a-b','generate',CURRENT_TIMESTAMP(6),'two','style','title','content',1.000,7,0,'test')"
        ))
        source_count = connection.exec_driver_sql("SELECT COUNT(*) FROM generation_logs").scalar_one()
        original_snapshot = source_snapshot(connection)
    first = run_ingestion(database, hive_database)
    assert first.returncode == 0, first.stdout
    with database["engine"].connect() as connection:
        batch = connection.execute(sa.text(
            "SELECT batch_id,status,source_count,hive_count FROM etl_batches "
            "WHERE pipeline_name='mysql_to_hive_ods' ORDER BY batch_id DESC LIMIT 1"
        )).mappings().one()
        assert batch["status"] == "SUCCEEDED"
        assert batch["source_count"] == batch["hive_count"] == source_count
        assert hive_batch_count(hive_database, batch["batch_id"]) == source_count
        first_records = hive_batch_records(hive_database, batch["batch_id"])
        assert_hive_matches_source(first_records, original_snapshot, batch["batch_id"])
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM generation_logs").scalar_one() == source_count
        assert source_snapshot(connection) == original_snapshot
        assert source_count == before + 2
        assert_successful_quality_checks(connection, batch["batch_id"])
    second = run_ingestion(database, hive_database)
    assert second.returncode == 0, second.stderr[-1000:]
    with database["engine"].begin() as connection:
        empty_batch = connection.execute(sa.text(
            "SELECT source_count,status FROM etl_batches WHERE pipeline_name='mysql_to_hive_ods' ORDER BY batch_id DESC LIMIT 1"
        )).mappings().one()
        assert empty_batch == {"source_count": 0, "status": "SUCCEEDED"}
        assert source_snapshot(connection) == original_snapshot
        empty_batch_id = connection.execute(sa.text(
            "SELECT batch_id FROM etl_batches WHERE pipeline_name='mysql_to_hive_ods' "
            "ORDER BY batch_id DESC LIMIT 1"
        )).scalar_one()
        assert_successful_quality_checks(connection, empty_batch_id)
        connection.execute(sa.text("UPDATE generation_logs SET download_count=download_count+1 WHERE user_id='round10a-a'"))
        updated_snapshot = source_snapshot(connection)
    third = run_ingestion(database, hive_database)
    assert third.returncode == 0, third.stderr[-1000:]
    with database["engine"].connect() as connection:
        updated_batch = connection.execute(sa.text(
            "SELECT source_count,status FROM etl_batches WHERE pipeline_name='mysql_to_hive_ods' ORDER BY batch_id DESC LIMIT 1"
        )).mappings().one()
        assert updated_batch == {"source_count": 1, "status": "SUCCEEDED"}
        assert source_snapshot(connection) == updated_snapshot
        updated_batch_id = connection.execute(sa.text(
            "SELECT batch_id FROM etl_batches WHERE pipeline_name='mysql_to_hive_ods' "
            "ORDER BY batch_id DESC LIMIT 1"
        )).scalar_one()
        assert_successful_quality_checks(connection, updated_batch_id)
        third_records = hive_batch_records(hive_database, updated_batch_id)
        assert len(third_records) == 1
        updated_row = next(row for row in updated_snapshot if row["user_id"] == "round10a-a")
        assert third_records[0]["id"] == updated_row["id"]
        assert third_records[0]["download_count"] == 1
        assert third_records[0]["updated_at"] == updated_row["updated_at"]
        assert_hive_matches_source(third_records, [updated_row], updated_batch_id)
        assert hive_batch_count(hive_database, batch["batch_id"]) == source_count
