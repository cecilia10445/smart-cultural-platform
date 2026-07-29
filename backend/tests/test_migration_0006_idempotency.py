import importlib.util
from pathlib import Path


def load_migration():
    path = Path(__file__).parents[1] / "migrations" / "versions" / "0006_generation_attempt_idempotency.py"
    spec = importlib.util.spec_from_file_location("migration_0006", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_and_protected_downgrade():
    migration = load_migration()
    assert migration.revision == "0006"
    assert migration.down_revision == "0005"
    try:
        migration.downgrade()
    except RuntimeError as error:
        assert "downgrade is disabled" in str(error)
    else:
        raise AssertionError("protected migration must not provide a destructive downgrade")


def test_upgrade_adds_only_attempt_idempotency_metadata(monkeypatch):
    migration = load_migration()
    calls = []
    monkeypatch.setattr(migration.op, "add_column", lambda *args, **kwargs: calls.append(("add_column", args, kwargs)))
    monkeypatch.setattr(migration.op, "create_unique_constraint", lambda *args, **kwargs: calls.append(("unique", args, kwargs)))
    migration.upgrade()
    assert calls[0][0] == "add_column" and calls[0][1][0] == "generation_attempts"
    assert calls[0][1][1].name == "idempotency_key"
    assert calls[1][0] == "unique"
    assert calls[1][1] == ("uq_generation_attempts_user_idempotency", "generation_attempts", ["user_id", "idempotency_key"])
