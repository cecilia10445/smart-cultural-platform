import importlib.util
from pathlib import Path


def _migration():
    path = Path(__file__).parents[1] / "migrations" / "versions" / "0012_agent_action_execution_context_scope.py"
    spec = importlib.util.spec_from_file_location("migration_0012", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_0012_adds_execution_and_non_null_context_scope(monkeypatch):
    migration, calls = _migration(), []
    for name in ("add_column", "create_index", "create_unique_constraint", "create_check_constraint", "drop_constraint", "execute", "alter_column"):
        monkeypatch.setattr(migration.op, name, lambda *args, _name=name, **kwargs: calls.append((_name, args, kwargs)))
    migration.upgrade()
    additions = {(args[0], args[1].name) for kind,args,_ in calls if kind == "add_column"}
    assert (migration.revision, migration.down_revision) == ("0012", "0011")
    assert {("agent_actions", "execution_idempotency_key"), ("agent_actions", "execution_request_hash"),
            ("agent_actions", "execution_result_hash"), ("agent_context_summaries", "scope_type"),
            ("agent_context_summaries", "scope_key")} <= additions
    assert any(args[0] == "uq_agent_context_summaries_scope_version" for kind,args,_ in calls if kind == "create_unique_constraint")
