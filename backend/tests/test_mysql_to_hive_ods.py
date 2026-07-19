from datetime import datetime

import pytest

from scripts import mysql_to_hive_ods as ods


NOW = datetime(2026, 1, 1, 12, 0, 0)


def row(identifier=1, origin="test", updated_at=NOW):
    return {
        "id": identifier, "user_id": "test-user", "event_type": "generate", "timestamp": NOW,
        "prompt": "prompt", "style": "style", "image_url": None, "title": "title", "content": "content",
        "generation_time": 1.0, "content_length": 7, "user_rating": None, "download_count": 0,
        "user_age": None, "user_gender": None, "login_time": None, "data_origin": origin,
        "created_at": NOW, "updated_at": updated_at,
    }


def test_composite_boundary_is_strict_at_start_and_inclusive_at_end():
    start, end = (NOW, 4), (NOW, 8)
    clause, params = ods.composite_clause(start, end)
    assert "id > %s" in clause and "id <= %s" in clause
    assert params == (NOW, NOW, 4, NOW, NOW, 8)


def test_quality_checks_accept_empty_batch_and_reject_bad_origin_or_duplicate_id():
    assert all(item[1] for item in ods.quality_checks([], 0, None, None))
    failed = {item[0] for item in ods.quality_checks([row(1, "invalid"), row(1)], 2, None, (NOW, 1)) if not item[1]}
    assert {"data_origin_allowed", "id_unique_in_batch"} <= failed


def test_quality_checks_report_invalid_origin_count_and_null_updated_at_without_type_error():
    rows = [row(1, "invalid"), row(2, "also-invalid", updated_at=None)]
    checks = {name: (passed, expected, actual) for name, passed, expected, actual in ods.quality_checks(rows, 2, None, (NOW, 2))}
    assert checks["data_origin_allowed"] == (False, "allowed", 2)
    assert checks["updated_at_not_null"] == (False, "non-null", "null")
    assert checks["watermark_within_frozen_bounds"] == (False, "within bounds", "outside bounds")


class FakeCursor:
    def __init__(self, rows, fail_source=False):
        self.rows, self.fail_source, self.lastrowid, self.quality, self.updates = rows, fail_source, 41, [], []
        self.current = None

    def execute(self, query, params=()):
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT version_num"):
            self.current = {"version_num": "0002"}
        elif "WHERE pipeline_name" in normalized:
            self.current = None
        elif normalized.startswith("SELECT updated_at,id FROM generation_logs"):
            self.current = {"updated_at": NOW, "id": max([item["id"] for item in self.rows], default=0)} if self.rows else None
        elif normalized.startswith("SELECT id,user_id"):
            if self.fail_source:
                raise RuntimeError("source unavailable")
            self.current = self.rows
        elif normalized.startswith("INSERT INTO data_quality_results"):
            self.quality.append(params)
        elif normalized.startswith("UPDATE etl_batches"):
            self.updates.append(params)

    def fetchone(self):
        return self.current

    def fetchall(self):
        return self.current


class FakeConnection:
    def __init__(self, cursor): self.cursor_value, self.closed = cursor, False
    def cursor(self):
        class Context:
            def __enter__(inner): return self.cursor_value
            def __exit__(inner, *args): return False
        return Context()
    def close(self): self.closed = True


def test_run_sync_creates_successful_empty_batch(monkeypatch):
    cursor, connection = FakeCursor([]), None
    connection = FakeConnection(cursor)
    monkeypatch.setattr(ods, "mysql_connection", lambda _config: connection)
    result = ods.run_sync({"hive_database": "round10a_test"}, hive_writer=lambda rows, *_: len(rows))
    assert result["source_count"] == result["hive_count"] == 0
    assert len(cursor.quality) == 6
    assert cursor.updates[-1][0] == "SUCCEEDED"


def test_run_sync_marks_failed_when_source_or_hive_write_fails(monkeypatch):
    source_cursor = FakeCursor([row()], fail_source=True)
    monkeypatch.setattr(ods, "mysql_connection", lambda _config: FakeConnection(source_cursor))
    with pytest.raises(ods.SyncError, match="MYSQL_QUERY_FAILED"):
        ods.run_sync({"hive_database": "round10a_test"})
    assert source_cursor.updates[-1][0:2] == ("FAILED", "MYSQL_QUERY_FAILED")

    hive_cursor = FakeCursor([row()])
    monkeypatch.setattr(ods, "mysql_connection", lambda _config: FakeConnection(hive_cursor))
    with pytest.raises(ods.SyncError, match="HIVE_WRITE_FAILED"):
        ods.run_sync({"hive_database": "round10a_test"}, hive_writer=lambda *_: (_ for _ in ()).throw(RuntimeError()))
    assert hive_cursor.updates[-1][0:2] == ("FAILED", "HIVE_WRITE_FAILED")


def test_quality_failure_never_marks_batch_succeeded(monkeypatch):
    cursor = FakeCursor([row(origin="invalid")])
    monkeypatch.setattr(ods, "mysql_connection", lambda _config: FakeConnection(cursor))
    with pytest.raises(ods.SyncError, match="DATA_QUALITY_FAILED"):
        ods.run_sync({"hive_database": "round10a_test"}, hive_writer=lambda rows, *_: len(rows))
    assert cursor.updates[-1][0:2] == ("FAILED", "DATA_QUALITY_FAILED")
