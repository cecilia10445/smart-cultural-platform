import importlib.util
from pathlib import Path


def load_migration():
    path = Path(__file__).parents[1] / "migrations" / "versions" / "0011_agent_action_approval_contract.py"
    spec = importlib.util.spec_from_file_location("migration_0011", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0011_is_additive_approval_and_task_idempotency_contract(monkeypatch):
    migration, calls = load_migration(), []
    for name in ("add_column", "create_index", "create_unique_constraint"):
        monkeypatch.setattr(migration.op, name, lambda *args, _name=name, **kwargs: calls.append((_name, args, kwargs)))
    migration.upgrade()
    additions = {(args[0], args[1].name) for kind, args, _ in calls if kind == "add_column"}
    assert (migration.revision, migration.down_revision) == ("0011", "0010")
    assert {("agent_design_tasks", "client_task_id"), ("agent_actions", "approval_idempotency_key"),
            ("agent_actions", "approval_hash"), ("agent_actions", "rejection_idempotency_key"),
            ("agent_actions", "rejection_hash"), ("agent_actions", "rejected_at")} <= additions
    assert any(args[0] == "uq_agent_design_tasks_client_task" for kind, args, _ in calls if kind == "create_unique_constraint")
