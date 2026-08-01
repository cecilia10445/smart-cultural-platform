import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def test_0010_upgrade_downgrade_upgrade_and_generation_log_preservation(mysql_container_database):
    engine, config = mysql_container_database["engine"], Config("alembic.ini")
    command.downgrade(config, "0009")
    command.upgrade(config, "0010")
    inspector = sa.inspect(engine)
    assert {"agent_design_tasks", "agent_actions", "agent_artifacts"} <= set(inspector.get_table_names())
    session_columns = {item["name"] for item in inspector.get_columns("agent_sessions")}
    assert {"conversation_status", "active_task_id", "archived_at"} <= session_columns
    assert {"task_id"} <= {item["name"] for item in inspector.get_columns("agent_messages")}
    assert "uq_agent_actions_task_idempotency" in {item["name"] for item in inspector.get_unique_constraints("agent_actions")}
    assert "uq_agent_artifacts_task_type_version" in {item["name"] for item in inspector.get_unique_constraints("agent_artifacts")}
    before = engine.connect().execute(sa.text("SELECT COUNT(*) FROM generation_logs")).scalar_one()
    command.downgrade(config, "0009")
    after = engine.connect().execute(sa.text("SELECT COUNT(*) FROM generation_logs")).scalar_one()
    assert before == after
    command.upgrade(config, "0010")


def test_0010_downgrade_refuses_persisted_task(mysql_container_database):
    engine, config = mysql_container_database["engine"], Config("alembic.ini")
    command.upgrade(config, "0010")
    with engine.begin() as connection:
        connection.execute(sa.text("INSERT INTO agent_sessions (id,user_id,status,current_stage,text_revision_count,version,created_at,updated_at,conversation_status) VALUES ('f0-session','f0-owner','created','created',0,1,CURRENT_TIMESTAMP(6),CURRENT_TIMESTAMP(6),'active')"))
        connection.execute(sa.text("INSERT INTO agent_design_tasks (id,user_id,session_id,title,status,origin,version,created_at,updated_at) VALUES ('f0-task','f0-owner','f0-session','F0 task','exploring','native',1,CURRENT_TIMESTAMP(6),CURRENT_TIMESTAMP(6))"))
    with pytest.raises(RuntimeError, match="persisted F0 domain data"):
        command.downgrade(config, "0009")
    with engine.begin() as connection:
        connection.execute(sa.text("DELETE FROM agent_design_tasks WHERE id='f0-task'"))
        connection.execute(sa.text("DELETE FROM agent_sessions WHERE id='f0-session'"))
    command.downgrade(config, "0009")
    command.upgrade(config, "0010")
