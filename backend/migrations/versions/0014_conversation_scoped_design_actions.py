"""make design actions and artifacts conversation-scope capable

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def _schema(table: str) -> tuple[set[str], set[str], set[str]]:
    """Return columns, indexes and named constraints when a live bind exists.

    MySQL DDL is auto-committing.  Guarding every additive step lets a failed
    upgrade resume safely instead of requiring a destructive manual repair.
    The fallback keeps the migration inspectable in isolated unit tests.
    """
    try:
        inspector = sa.inspect(op.get_bind())
        columns = {item["name"] for item in inspector.get_columns(table)}
        indexes = {item["name"] for item in inspector.get_indexes(table)}
        constraints = {item["name"] for item in inspector.get_unique_constraints(table)}
        constraints.update(item["name"] for item in inspector.get_check_constraints(table))
        return columns, indexes, constraints
    except Exception:
        return set(), set(), set()


def _add_scope_columns(table: str) -> None:
    columns, _indexes, _constraints = _schema(table)
    if "scope_type" not in columns:
        op.add_column(table, sa.Column("scope_type", sa.String(16), nullable=False, server_default=sa.text("'task'")))
    if "scope_key" not in columns:
        op.add_column(table, sa.Column("scope_key", sa.String(80)))
    # Existing F0-F3 rows remain Task scoped.  Conversation-scoped rows are
    # only created after this migration is the recorded head.
    op.execute(f"UPDATE {table} SET scope_key=CONCAT('task:', task_id) WHERE scope_key IS NULL")
    columns, _indexes, constraints = _schema(table)
    if not columns or "chk_" + table + "_scope_type" not in constraints:
        op.create_check_constraint(f"chk_{table}_scope_type", table, "scope_type IN ('conversation','task')")
    if not columns or "chk_" + table + "_scope_consistency" not in constraints:
        op.create_check_constraint(f"chk_{table}_scope_consistency", table,
                                   "(scope_type='conversation' AND task_id IS NULL) OR (scope_type='task' AND task_id IS NOT NULL)")
    # `scope_key` is nullable only while the legacy rows are being backfilled.
    op.alter_column(table, "scope_key", existing_type=sa.String(80), nullable=False)
    op.alter_column(table, "task_id", existing_type=sa.String(36), nullable=True)


def upgrade():
    _add_scope_columns("agent_actions")
    _add_scope_columns("agent_artifacts")

    _columns, indexes, constraints = _schema("agent_actions")
    if not indexes or "idx_agent_actions_owner_scope_status_type" not in indexes:
        op.create_index("idx_agent_actions_owner_scope_status_type", "agent_actions",
                        ["user_id", "session_id", "scope_key", "status", "action_type"])
    if not constraints or "uq_agent_actions_scope_idempotency" not in constraints:
        if not constraints or "uq_agent_actions_task_idempotency" in constraints:
            op.drop_constraint("uq_agent_actions_task_idempotency", "agent_actions", type_="unique")
        op.create_unique_constraint("uq_agent_actions_scope_idempotency", "agent_actions",
                                    ["user_id", "session_id", "scope_key", "action_type", "idempotency_key"])

    _columns, indexes, constraints = _schema("agent_artifacts")
    # The legacy composite unique key was also the only left-prefix index for
    # fk_agent_artifacts_task.  Add the dedicated FK index before removing it.
    if not indexes or "idx_agent_artifacts_task_fk" not in indexes:
        op.create_index("idx_agent_artifacts_task_fk", "agent_artifacts", ["task_id"])
    if not indexes or "idx_agent_artifacts_owner_scope_type_created" not in indexes:
        op.create_index("idx_agent_artifacts_owner_scope_type_created", "agent_artifacts",
                        ["user_id", "session_id", "scope_key", "artifact_type", "created_at"])
    if not constraints or "uq_agent_artifacts_scope_type_version" not in constraints:
        if not constraints or "uq_agent_artifacts_task_type_version" in constraints:
            op.drop_constraint("uq_agent_artifacts_task_type_version", "agent_artifacts", type_="unique")
        op.create_unique_constraint("uq_agent_artifacts_scope_type_version", "agent_artifacts",
                                    ["session_id", "scope_key", "artifact_type", "version_number"])


def downgrade():
    bind = op.get_bind()
    for table in ("agent_actions", "agent_artifacts"):
        count = bind.execute(sa.text(f"SELECT COUNT(*) FROM {table} WHERE scope_type <> 'task' OR task_id IS NULL")).scalar()
        if int(count or 0):
            raise RuntimeError("conversation-scoped design data exists; downgrade refused")

    op.drop_index("idx_agent_artifacts_owner_scope_type_created", table_name="agent_artifacts")
    op.drop_constraint("uq_agent_artifacts_scope_type_version", "agent_artifacts", type_="unique")
    op.create_unique_constraint("uq_agent_artifacts_task_type_version", "agent_artifacts", ["task_id", "artifact_type", "version_number"])
    op.drop_index("idx_agent_artifacts_task_fk", table_name="agent_artifacts")
    op.drop_constraint("chk_agent_artifacts_scope_consistency", "agent_artifacts", type_="check")
    op.drop_constraint("chk_agent_artifacts_scope_type", "agent_artifacts", type_="check")
    op.drop_column("agent_artifacts", "scope_key")
    op.drop_column("agent_artifacts", "scope_type")
    op.alter_column("agent_artifacts", "task_id", existing_type=sa.String(36), nullable=False)

    op.drop_index("idx_agent_actions_owner_scope_status_type", table_name="agent_actions")
    op.drop_constraint("uq_agent_actions_scope_idempotency", "agent_actions", type_="unique")
    op.create_unique_constraint("uq_agent_actions_task_idempotency", "agent_actions", ["user_id", "task_id", "action_type", "idempotency_key"])
    op.drop_constraint("chk_agent_actions_scope_consistency", "agent_actions", type_="check")
    op.drop_constraint("chk_agent_actions_scope_type", "agent_actions", type_="check")
    op.drop_column("agent_actions", "scope_key")
    op.drop_column("agent_actions", "scope_type")
    op.alter_column("agent_actions", "task_id", existing_type=sa.String(36), nullable=False)
