import os

import pytest

from scripts import init_hive


def set_hive_env(monkeypatch, database=None):
    for key, value in {
        "HIVE_HOST": "hive.example", "HIVE_PORT": "10000", "HIVE_USERNAME": "etl",
        "HIVE_DATABASE": database,
    }.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


def test_missing_hive_database_fails(monkeypatch):
    set_hive_env(monkeypatch)
    with pytest.raises(RuntimeError, match="HIVE_DATABASE"):
        init_hive.init_hive_tables(dry_run=True)


def test_invalid_hive_database_is_rejected(monkeypatch):
    set_hive_env(monkeypatch, "bad-name")
    with pytest.raises(RuntimeError, match="simple Hive identifier"):
        init_hive.init_hive_tables(dry_run=True)


def test_valid_database_replaces_both_ddl_placeholders(monkeypatch):
    set_hive_env(monkeypatch, "analytics_2026")
    statements = init_hive.read_statements("analytics_2026")
    assert "CREATE DATABASE IF NOT EXISTS analytics_2026" in statements[0]
    assert any("CREATE TABLE IF NOT EXISTS analytics_2026.ods_generation_logs" in statement for statement in statements)


def test_dry_run_does_not_connect(monkeypatch):
    set_hive_env(monkeypatch, "analytics_2026")
    monkeypatch.setattr(init_hive.hive, "connect", lambda **kwargs: pytest.fail("Hive connected during dry-run"))
    assert init_hive.init_hive_tables(dry_run=True) is True
