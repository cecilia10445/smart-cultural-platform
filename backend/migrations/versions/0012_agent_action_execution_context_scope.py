"""add action execution and task-scoped context contracts

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    for name, column in (
        ("execution_idempotency_key", sa.Column("execution_idempotency_key", sa.String(128))),
        ("execution_request_hash", sa.Column("execution_request_hash", sa.String(64))),
        ("execution_result_hash", sa.Column("execution_result_hash", sa.String(64))),
        ("execution_started_at", sa.Column("execution_started_at", mysql.DATETIME(fsp=6))),
        ("executor_version", sa.Column("executor_version", sa.String(32))),
    ):
        op.add_column("agent_actions", column)
    op.create_index("idx_agent_actions_execution_idempotency", "agent_actions", ["id", "execution_idempotency_key"])
    op.add_column("agent_context_summaries", sa.Column("scope_type", sa.String(16), nullable=False, server_default=sa.text("'session'")))
    op.add_column("agent_context_summaries", sa.Column("scope_key", sa.String(80)))
    op.execute("UPDATE agent_context_summaries SET scope_key=CONCAT('session:', session_id) WHERE scope_key IS NULL")
    op.alter_column("agent_context_summaries", "scope_key", existing_type=sa.String(80), nullable=False)
    op.create_check_constraint("chk_agent_context_summaries_scope_type", "agent_context_summaries", "scope_type IN ('session','task')")
    op.drop_constraint("uq_agent_context_summaries_session_version", "agent_context_summaries", type_="unique")
    op.create_unique_constraint("uq_agent_context_summaries_scope_version", "agent_context_summaries", ["user_id", "session_id", "scope_key", "session_version"])
    op.create_index("idx_agent_context_summaries_scope_active", "agent_context_summaries", ["user_id", "session_id", "scope_key", "status", "updated_at"])


def downgrade():
    bind = op.get_bind()
    action_data = bind.execute(sa.text("""SELECT COUNT(*) FROM agent_actions WHERE execution_idempotency_key IS NOT NULL
        OR execution_request_hash IS NOT NULL OR execution_result_hash IS NOT NULL OR execution_started_at IS NOT NULL OR executor_version IS NOT NULL""")).scalar()
    task_scope = bind.execute(sa.text("SELECT COUNT(*) FROM agent_context_summaries WHERE scope_type <> 'session' OR scope_key <> CONCAT('session:', session_id)")).scalar()
    if int(action_data or 0) or int(task_scope or 0):
        raise RuntimeError("agent execution/context downgrade refused: persisted F2 data exists")
    op.drop_index("idx_agent_context_summaries_scope_active", table_name="agent_context_summaries")
    op.drop_constraint("uq_agent_context_summaries_scope_version", "agent_context_summaries", type_="unique")
    op.create_unique_constraint("uq_agent_context_summaries_session_version", "agent_context_summaries", ["user_id", "session_id", "session_version"])
    op.drop_constraint("chk_agent_context_summaries_scope_type", "agent_context_summaries", type_="check")
    op.drop_column("agent_context_summaries", "scope_key")
    op.drop_column("agent_context_summaries", "scope_type")
    op.drop_index("idx_agent_actions_execution_idempotency", table_name="agent_actions")
    for name in ("executor_version", "execution_started_at", "execution_result_hash", "execution_request_hash", "execution_idempotency_key"):
        op.drop_column("agent_actions", name)
