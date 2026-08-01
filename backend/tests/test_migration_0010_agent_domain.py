import importlib.util
from pathlib import Path


def load_migration():
    path = Path(__file__).parents[1] / "migrations" / "versions" / "0010_agent_domain_graph.py"
    spec = importlib.util.spec_from_file_location("migration_0010", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_and_additive_schema_contract(monkeypatch):
    migration, calls = load_migration(), []
    for name in ("create_table", "create_index", "add_column", "create_check_constraint", "create_foreign_key"):
        monkeypatch.setattr(migration.op, name, lambda *args, _name=name, **kwargs: calls.append((_name, args, kwargs)))
    migration.upgrade()
    tables = {args[0]: args[1:] for kind, args, _ in calls if kind == "create_table"}
    assert (migration.revision, migration.down_revision) == ("0010", "0009")
    assert set(tables) == {"agent_design_tasks", "agent_actions", "agent_artifacts"}
    task_names = {item.name for item in tables["agent_design_tasks"] if hasattr(item, "name")}
    action_names = {item.name for item in tables["agent_actions"] if hasattr(item, "name")}
    artifact_names = {item.name for item in tables["agent_artifacts"] if hasattr(item, "name")}
    assert {"id", "user_id", "session_id", "status", "origin", "version"} <= task_names
    assert {"idempotency_key", "request_hash", "source_runtime_run_id", "generation_log_id", "retry_of_action_id"} <= action_names
    assert {"version_number", "parent_artifact_id", "content_json", "content_hash", "generation_log_id"} <= artifact_names
    additions = {(args[0], args[1].name) for kind, args, _ in calls if kind == "add_column"}
    assert {("agent_sessions", "conversation_status"), ("agent_sessions", "active_task_id"), ("agent_sessions", "archived_at"), ("agent_messages", "task_id"), ("agent_runtime_runs", "task_id"), ("agent_context_summaries", "task_id")} <= additions
    unique = [item for item in tables["agent_actions"] if item.__class__.__name__ == "UniqueConstraint"]
    assert any(item.name == "uq_agent_actions_task_idempotency" for item in unique)
    artifact_unique = [item for item in tables["agent_artifacts"] if item.__class__.__name__ == "UniqueConstraint"]
    assert any(item.name == "uq_agent_artifacts_task_type_version" for item in artifact_unique)
    assert not any(args and args[0] == "generation_logs" for kind, args, _ in calls if kind in {"add_column", "create_table"})


class Scalar:
    def __init__(self, value): self.value = value
    def scalar(self): return self.value


class Bind:
    def __init__(self, values): self.values = list(values)
    def execute(self, _query): return Scalar(self.values.pop(0))


def test_downgrade_refuses_any_persisted_f0_domain_data(monkeypatch):
    migration = load_migration()
    monkeypatch.setattr(migration.op, "get_bind", lambda: Bind([0, 0, 1]))
    try:
        migration.downgrade()
    except RuntimeError as error:
        assert str(error) == "agent domain graph downgrade refused: persisted F0 domain data exists"
    else:
        raise AssertionError("downgrade must retain F0 data")
