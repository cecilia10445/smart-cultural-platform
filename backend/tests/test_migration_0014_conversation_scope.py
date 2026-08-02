import importlib.util
from pathlib import Path


def load_migration():
    path = Path(__file__).parents[1] / "migrations" / "versions" / "0014_conversation_scoped_design_actions.py"
    spec = importlib.util.spec_from_file_location("migration_0014", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0014_adds_explicit_scope_without_rewriting_legacy_task_rows(monkeypatch):
    migration, calls = load_migration(), []
    for name in ("add_column", "alter_column", "create_check_constraint", "drop_constraint", "create_unique_constraint", "create_index"):
        monkeypatch.setattr(migration.op, name, lambda *args, _name=name, **kwargs: calls.append((_name, args, kwargs)))
    monkeypatch.setattr(migration.op, "execute", lambda statement: calls.append(("execute", (str(statement),), {})))
    migration.upgrade()
    assert (migration.revision, migration.down_revision) == ("0014", "0013")
    additions = {(args[0], args[1].name) for kind, args, _ in calls if kind == "add_column"}
    assert additions == {("agent_actions", "scope_type"), ("agent_actions", "scope_key"),
                         ("agent_artifacts", "scope_type"), ("agent_artifacts", "scope_key")}
    assert any("CONCAT('task:', task_id)" in args[0] for kind, args, _ in calls if kind == "execute")
    assert any(args[0] == "uq_agent_actions_scope_idempotency" for kind, args, _ in calls if kind == "create_unique_constraint")
    assert any(args[0] == "uq_agent_artifacts_scope_type_version" for kind, args, _ in calls if kind == "create_unique_constraint")
