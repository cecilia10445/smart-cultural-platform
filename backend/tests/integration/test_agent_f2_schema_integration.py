import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def test_0012_upgrade_downgrade_upgrade_isolated_mysql(mysql_container_database):
    engine, config = mysql_container_database["engine"], Config("alembic.ini")
    command.downgrade(config, "0011")
    command.upgrade(config, "0012")
    inspector = sa.inspect(engine)
    action_columns = {item["name"] for item in inspector.get_columns("agent_actions")}
    summary_columns = {item["name"] for item in inspector.get_columns("agent_context_summaries")}
    assert {"execution_idempotency_key", "execution_request_hash", "execution_result_hash", "execution_started_at", "executor_version"} <= action_columns
    assert {"scope_type", "scope_key", "task_id"} <= summary_columns
    before = engine.connect().execute(sa.text("SELECT COUNT(*) FROM generation_logs")).scalar_one()
    command.downgrade(config, "0011")
    after = engine.connect().execute(sa.text("SELECT COUNT(*) FROM generation_logs")).scalar_one()
    assert before == after
    command.upgrade(config, "0012")
