#!/usr/bin/env python3
"""Incrementally copy MySQL generation_logs into isolated Hive ODS partitions."""
import argparse
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pymysql


LOGGER = logging.getLogger("mysql_to_hive_ods")
PIPELINE_NAME = "mysql_to_hive_ods"
ALLOWED_ORIGINS = {"production", "test", "synthetic", "public"}
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
LOG_COLUMNS = (
    "id,user_id,event_type,timestamp,prompt,style,image_url,title,content,"
    "generation_time,content_length,user_rating,download_count,user_age,user_gender,"
    "login_time,data_origin,created_at,updated_at"
)
SCRIPT_DIR = Path(__file__).resolve().parent
ODS_FIELDS = LOG_COLUMNS.split(",") + ["ingested_at", "extract_date", "etl_batch_id"]


class SyncError(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def required_env(name):
    value = os.getenv(name)
    if not value:
        raise SyncError("CONFIG_INVALID")
    return value


def load_config():
    database = required_env("MYSQL_DATABASE")
    hive_database = required_env("HIVE_DATABASE")
    if not IDENTIFIER.fullmatch(hive_database):
        raise SyncError("CONFIG_INVALID")
    return {
        "host": required_env("MYSQL_HOST"), "port": int(required_env("MYSQL_PORT")),
        "user": required_env("MYSQL_USER"), "password": required_env("MYSQL_PASSWORD"),
        "database": database, "hive_database": hive_database,
        "hive_metastore_uri": required_env("HIVE_METASTORE_URI"),
        "hdfs_warehouse_dir": required_env("HDFS_WAREHOUSE_DIR"),
    }


def mysql_connection(config):
    return pymysql.connect(
        host=config["host"], port=config["port"], user=config["user"], password=config["password"],
        database=config["database"], charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def composite_clause(start, end):
    clauses, params = [], []
    if start:
        clauses.append("(updated_at > %s OR (updated_at = %s AND id > %s))")
        params.extend((start[0], start[0], start[1]))
    if end:
        clauses.append("(updated_at < %s OR (updated_at = %s AND id <= %s))")
        params.extend((end[0], end[0], end[1]))
    return (" AND ".join(clauses) or "1=1"), tuple(params)


def latest_watermark(cursor):
    cursor.execute(
        "SELECT watermark_end_time,watermark_end_id FROM etl_batches "
        "WHERE pipeline_name=%s AND status='SUCCEEDED' AND watermark_end_time IS NOT NULL "
        "ORDER BY batch_id DESC LIMIT 1", (PIPELINE_NAME,))
    row = cursor.fetchone()
    return (row["watermark_end_time"], row["watermark_end_id"]) if row else None


def frozen_end_watermark(cursor):
    cursor.execute("SELECT updated_at,id FROM generation_logs ORDER BY updated_at DESC,id DESC LIMIT 1")
    row = cursor.fetchone()
    return (row["updated_at"], row["id"]) if row else None


def create_batch(cursor, start, end):
    cursor.execute(
        "INSERT INTO etl_batches (pipeline_name,status,watermark_start_time,watermark_start_id,"
        "watermark_end_time,watermark_end_id) VALUES (%s,'RUNNING',%s,%s,%s,%s)",
        (PIPELINE_NAME, *(start or (None, None)), *(end or (None, None))),
    )
    return cursor.lastrowid


def fetch_source_rows(cursor, start, end):
    clause, params = composite_clause(start, end)
    cursor.execute(f"SELECT {LOG_COLUMNS} FROM generation_logs WHERE {clause} ORDER BY updated_at,id", params)
    return cursor.fetchall()


def record_quality(cursor, batch_id, checks):
    for name, passed, expected, actual in checks:
        cursor.execute(
            "INSERT INTO data_quality_results (batch_id,check_name,status,expected_value,actual_value) "
            "VALUES (%s,%s,%s,%s,%s)",
            (batch_id, name, "PASSED" if passed else "FAILED", str(expected), str(actual)),
        )


def quality_checks(rows, hive_count, start, end):
    ids = [row["id"] for row in rows]
    origins = [row["data_origin"] for row in rows]
    watermarks = [(row["updated_at"], row["id"]) for row in rows]
    null_updated = next((row["id"] for row in rows if row["updated_at"] is None), None)
    invalid_origin_count = sum(value not in ALLOWED_ORIGINS for value in origins)
    bounded = [value for value in watermarks if value[0] is not None]
    lower_ok = null_updated is None and (not start or all(value > start for value in bounded))
    upper_ok = null_updated is None and (not end or all(value <= end for value in bounded))
    return [
        ("source_count_equals_hive_batch_count", len(rows) == hive_count, len(rows), hive_count),
        ("id_not_null", all(value is not None for value in ids), "non-null", "non-null" if all(value is not None for value in ids) else "null"),
        ("id_unique_in_batch", len(ids) == len(set(ids)), len(ids), len(set(ids))),
        ("updated_at_not_null", null_updated is None, "non-null", "non-null" if null_updated is None else "null"),
        ("data_origin_allowed", invalid_origin_count == 0, "allowed", "allowed" if invalid_origin_count == 0 else invalid_origin_count),
        ("watermark_within_frozen_bounds", lower_ok and upper_ok, "within bounds", "within bounds" if lower_ok and upper_ok else "outside bounds"),
    ]


def rendered_hive_ddl(database):
    sql = (SCRIPT_DIR / "hive_setup.sql").read_text(encoding="utf-8")
    return sql.replace("${HIVE_DATABASE}", database)


def validate_hive_schema(spark, hive_database):
    description = spark.sql(f"DESCRIBE {hive_database}.ods_generation_logs").collect()
    rows = [(item[0], item[1]) for item in description]
    partition_marker = next((index for index, item in enumerate(rows) if item[0] == "# Partition Information"), None)
    if partition_marker is None:
        raise SyncError("HIVE_SCHEMA_MISMATCH")
    schema_rows = [(name, data_type.lower()) for name, data_type in rows[:partition_marker] if name]
    partition_rows = [(name, data_type.lower()) for name, data_type in rows[partition_marker + 2:] if name]
    names = [name for name, _ in schema_rows]
    partitions = [name for name, _ in partition_rows]
    if names != ODS_FIELDS or partitions != ["extract_date", "etl_batch_id"]:
        raise SyncError("HIVE_SCHEMA_MISMATCH")
    types = dict(schema_rows)
    expected = {"id": "bigint", "timestamp": "timestamp", "generation_time": "decimal(12,3)",
                "user_rating": "decimal(3,2)", "created_at": "timestamp", "updated_at": "timestamp",
                "extract_date": "date", "etl_batch_id": "bigint"}
    if any(types.get(name) != value for name, value in expected.items()):
        raise SyncError("HIVE_SCHEMA_MISMATCH")


def write_hive_rows(rows, batch_id, config):
    from pyspark.sql import SparkSession
    from pyspark.sql.types import (StructType, StructField, LongType, StringType, TimestampType,
                                   DecimalType, ShortType, DateType)
    hive_database = config["hive_database"]
    spark = (SparkSession.builder.appName("mysql-to-hive-ods")
             .config("spark.hadoop.hive.metastore.uris", config["hive_metastore_uri"])
             .config("spark.sql.warehouse.dir", config["hdfs_warehouse_dir"])
             .config("spark.sql.parquet.writeLegacyFormat", "true")
             .enableHiveSupport().getOrCreate())
    table = f"{hive_database}.ods_generation_logs"
    try:
        for statement in rendered_hive_ddl(hive_database).split(";"):
            if statement.strip():
                spark.sql(statement)
        validate_hive_schema(spark, hive_database)
        schema = StructType([
            StructField("id", LongType(), False), StructField("user_id", StringType()), StructField("event_type", StringType()),
            StructField("timestamp", TimestampType()), StructField("prompt", StringType()), StructField("style", StringType()),
            StructField("image_url", StringType()), StructField("title", StringType()), StructField("content", StringType()),
            StructField("generation_time", DecimalType(12, 3)), StructField("content_length", LongType()), StructField("user_rating", DecimalType(3, 2)),
            StructField("download_count", LongType()), StructField("user_age", ShortType()), StructField("user_gender", ShortType()),
            StructField("login_time", TimestampType()), StructField("data_origin", StringType()), StructField("created_at", TimestampType()),
            StructField("updated_at", TimestampType()), StructField("ingested_at", TimestampType()), StructField("extract_date", DateType()),
            StructField("etl_batch_id", LongType()),
        ])
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        extract_date = now.date()
        values = [tuple(row[column] for column in LOG_COLUMNS.split(",")) + (now, extract_date, batch_id) for row in rows]
        if values:
            frame = spark.createDataFrame(values, schema)
            LOGGER.info("Hive write stage=insert table=%s batch_id=%s spark=%s python=%s schema=%s describe=%s",
                        table, batch_id, spark.version, sys.executable, frame.schema.simpleString(),
                        [(item[0], item[1]) for item in spark.sql(f"DESCRIBE {table}").collect()])
            frame.write.mode("append").insertInto(table)
        return 0 if not values else spark.table(table).where(f"extract_date = DATE '{extract_date}' AND etl_batch_id = {batch_id}").count()
    except Exception as error:
        root = getattr(error, "java_exception", None)
        summary = next((line.strip() for line in str(root or error).splitlines() if line.strip()), repr(error))[:400]
        LOGGER.error("Hive write failed stage=insert type=%s java_type=%s summary=%s table=%s batch_id=%s spark=%s python=%s",
                     type(error).__name__, type(root).__name__ if root else "none", summary,
                     table, batch_id, spark.version, sys.executable)
        raise
    finally:
        spark.stop()


def finish_batch(cursor, batch_id, status, error_code, source_count, hive_count, end):
    cursor.execute(
        "UPDATE etl_batches SET status=%s,error_code=%s,source_count=%s,hive_count=%s,output_count=%s,"
        "watermark_end_time=%s,watermark_end_id=%s,finished_at=CURRENT_TIMESTAMP(6) WHERE batch_id=%s",
        (status, error_code, source_count, hive_count, hive_count, *(end or (None, None)), batch_id),
    )


def run_sync(config, hive_writer=write_hive_rows):
    connection = mysql_connection(config)
    batch_id = None
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version_num FROM alembic_version")
            if cursor.fetchone()["version_num"] != "0002":
                raise SyncError("MYSQL_REVISION_NOT_0002")
            start, end = latest_watermark(cursor), frozen_end_watermark(cursor)
            batch_id = create_batch(cursor, start, end)
            try:
                rows = fetch_source_rows(cursor, start, end)
            except Exception as exc:
                finish_batch(cursor, batch_id, "FAILED", "MYSQL_QUERY_FAILED", 0, 0, end)
                raise SyncError("MYSQL_QUERY_FAILED") from exc
            try:
                hive_count = hive_writer(rows, batch_id, config)
            except SyncError as error:
                finish_batch(cursor, batch_id, "FAILED", error.code, len(rows), 0, end)
                raise
            except Exception as exc:
                finish_batch(cursor, batch_id, "FAILED", "HIVE_WRITE_FAILED", len(rows), 0, end)
                raise SyncError("HIVE_WRITE_FAILED") from exc
            checks = quality_checks(rows, hive_count, start, end)
            record_quality(cursor, batch_id, checks)
            if not all(check[1] for check in checks):
                finish_batch(cursor, batch_id, "FAILED", "DATA_QUALITY_FAILED", len(rows), hive_count, end)
                raise SyncError("DATA_QUALITY_FAILED")
            finish_batch(cursor, batch_id, "SUCCEEDED", None, len(rows), hive_count, end)
            return {"batch_id": batch_id, "start": start, "end": end, "source_count": len(rows), "hive_count": hive_count}
    except SyncError:
        raise
    except Exception as exc:
        if batch_id is not None:
            with connection.cursor() as cursor:
                finish_batch(cursor, batch_id, "FAILED", "SYNC_FAILED", 0, 0, None)
        raise SyncError("SYNC_FAILED") from exc
    finally:
        connection.close()


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        result = run_sync(load_config())
        LOGGER.info("ODS batch %s completed: source=%s hive=%s", result["batch_id"], result["source_count"], result["hive_count"])
        return 0
    except SyncError as error:
        LOGGER.error("ODS sync failed: %s", error.code)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
