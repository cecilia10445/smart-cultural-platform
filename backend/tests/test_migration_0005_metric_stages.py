import importlib.util
from pathlib import Path


def load_migration():
    path = Path(__file__).parents[1] / "migrations" / "versions" / "0005_expand_model_call_metric_stages.py"
    spec = importlib.util.spec_from_file_location("migration_0005", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_and_protected_downgrade():
    migration = load_migration()
    assert migration.revision == "0005"
    assert migration.down_revision == "0004"
    try:
        migration.downgrade()
    except RuntimeError as error:
        assert "downgrade is disabled" in str(error)
    else:
        raise AssertionError("protected migration must not provide a destructive downgrade")


def test_upgrade_replaces_only_named_stage_constraint(monkeypatch):
    migration = load_migration()
    calls = []
    monkeypatch.setattr(migration.op, "drop_constraint", lambda *args, **kwargs: calls.append(("drop", args, kwargs)))
    monkeypatch.setattr(migration.op, "create_check_constraint", lambda *args, **kwargs: calls.append(("create", args, kwargs)))
    migration.upgrade()
    assert calls[0][0] == "drop" and calls[0][1][:2] == ("chk_model_call_metrics_stage", "model_call_metrics")
    assert calls[1][0] == "create" and calls[1][1][:2] == ("chk_model_call_metrics_stage", "model_call_metrics")
    predicate = str(calls[1][1][2])
    assert all(stage in predicate for stage in ("text_generation", "image_generation", "image_reference_generation", "image_layout_edit"))
