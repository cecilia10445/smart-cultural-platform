import importlib.util
from pathlib import Path


def load_migration():
    path = Path(__file__).parents[1] / "migrations" / "versions" / "0007_agent_dialogue_sessions.py"
    spec = importlib.util.spec_from_file_location("migration_0007", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_and_protected_downgrade():
    migration = load_migration()
    assert (migration.revision, migration.down_revision) == ("0007", "0006")
    try:
        migration.downgrade()
    except RuntimeError as error:
        assert "downgrade is disabled" in str(error)
    else:
        raise AssertionError("migration must not delete persisted owner conversations")


def test_upgrade_creates_only_new_agent_tables_with_constraints_and_indexes(monkeypatch):
    migration = load_migration()
    calls = []
    monkeypatch.setattr(migration.op, "create_table", lambda *args, **kwargs: calls.append(("table", args, kwargs)))
    monkeypatch.setattr(migration.op, "create_index", lambda *args, **kwargs: calls.append(("index", args, kwargs)))

    migration.upgrade()

    tables = {args[0]: args[1:] for kind, args, _kwargs in calls if kind == "table"}
    assert set(tables) == {"agent_sessions", "agent_messages", "agent_steps"}
    session_columns = {item.name for item in tables["agent_sessions"] if hasattr(item, "name")}
    assert {"id", "user_id", "generation_log_id", "text_revision_count", "version", "brief_json", "error_json"} <= session_columns
    session_constraints = [item for item in tables["agent_sessions"] if item.__class__.__name__.endswith("Constraint")]
    assert any(getattr(item, "name", "") == "chk_agent_sessions_revision_count" for item in session_constraints)
    assert any(getattr(item, "name", "") == "fk_agent_sessions_generation_log" for item in session_constraints)
    message_constraints = [item for item in tables["agent_messages"] if item.__class__.__name__.endswith("Constraint")]
    assert {item.name for item in message_constraints if getattr(item, "name", None)} >= {
        "uq_agent_messages_session_sequence", "uq_agent_messages_session_turn", "uq_agent_messages_session_decision",
    }
    step_constraints = [item for item in tables["agent_steps"] if item.__class__.__name__.endswith("Constraint")]
    assert any(getattr(item, "name", "") == "uq_agent_steps_session_ordinal" for item in step_constraints)
    indexes = {(args[0], args[1], tuple(args[2])) for kind, args, _kwargs in calls if kind == "index"}
    assert ("idx_agent_sessions_user_updated", "agent_sessions", ("user_id", "updated_at")) in indexes
    assert ("idx_agent_messages_session_sequence", "agent_messages", ("session_id", "sequence_no")) in indexes
    assert ("idx_agent_steps_session_ordinal", "agent_steps", ("session_id", "ordinal")) in indexes
