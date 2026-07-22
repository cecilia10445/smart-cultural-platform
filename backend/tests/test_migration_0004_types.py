import importlib.util
from pathlib import Path

from sqlalchemy.dialects import mysql
import sqlalchemy as sa


def load_migration():
    path = Path(__file__).parents[1] / "migrations" / "versions" / "0004_generation_attempt_tracking.py"
    spec = importlib.util.spec_from_file_location("migration_0004_types", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0004_uses_mysql_dialect_types_for_mysql_specific_arguments(monkeypatch):
    migration = load_migration()
    tables = []
    monkeypatch.setattr(migration.op, "create_table", lambda _name, *items: tables.append(items))
    monkeypatch.setattr(migration.op, "create_index", lambda *_args, **_kwargs: None)
    migration.upgrade()
    columns = [item for table in tables for item in table if isinstance(item, sa.Column)]
    by_name = {column.name: column.type for column in columns}
    assert isinstance(by_name["generation_log_id"], mysql.BIGINT) and by_name["generation_log_id"].unsigned
    for name in ("total_latency_ms", "latency_ms", "input_tokens", "output_tokens", "total_tokens"):
        assert isinstance(by_name[name], mysql.BIGINT) and by_name[name].unsigned
    for name in ("provider_http_status", "image_count"):
        assert isinstance(by_name[name], mysql.INTEGER) and by_name[name].unsigned
    for name in ("created_at", "finished_at"):
        assert isinstance(by_name[name], mysql.DATETIME) and by_name[name].fsp == 6
