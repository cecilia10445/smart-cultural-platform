import os

import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def test_0008_upgrade_downgrade_upgrade(mysql_container_database):
    engine = mysql_container_database["engine"]
    config = Config("alembic.ini")
    command.downgrade(config, "0007")
    inspector = sa.inspect(engine)
    assert not inspector.has_table("agent_runtime_runs")
    assert not inspector.has_table("agent_runtime_events")
    command.upgrade(config, "0008")
    inspector = sa.inspect(engine)
    assert inspector.has_table("agent_runtime_runs") and inspector.has_table("agent_runtime_events")
    unique = {item["name"] for item in inspector.get_unique_constraints("agent_runtime_runs")}
    indexes = {item["name"] for item in inspector.get_indexes("agent_runtime_events")}
    foreign = inspector.get_foreign_keys("agent_runtime_events")
    assert "uq_agent_runtime_runs_owner_turn" in unique
    assert "idx_agent_runtime_events_run_sequence" in indexes
    assert any(item["referred_table"] == "agent_runtime_runs" for item in foreign)
    command.downgrade(config, "0007")
    command.upgrade(config, "0008")
