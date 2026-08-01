"""add explicit approval idempotency to agent actions

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agent_design_tasks", sa.Column("client_task_id", sa.String(128)))
    op.create_unique_constraint("uq_agent_design_tasks_client_task", "agent_design_tasks", ["user_id", "session_id", "client_task_id"])
    op.add_column("agent_actions", sa.Column("approval_idempotency_key", sa.String(128)))
    op.add_column("agent_actions", sa.Column("approval_hash", sa.String(64)))
    op.add_column("agent_actions", sa.Column("rejection_idempotency_key", sa.String(128)))
    op.add_column("agent_actions", sa.Column("rejection_hash", sa.String(64)))
    op.add_column("agent_actions", sa.Column("rejected_at", mysql.DATETIME(fsp=6)))
    op.add_column("agent_actions", sa.Column("rejection_reason", sa.String(1000)))
    op.create_index("idx_agent_actions_approval_idempotency", "agent_actions", ["id", "approval_idempotency_key"])


def downgrade():
    bind = op.get_bind()
    changed = bind.execute(sa.text("""SELECT COUNT(*) FROM agent_actions
        WHERE approval_idempotency_key IS NOT NULL OR approval_hash IS NOT NULL
           OR rejection_idempotency_key IS NOT NULL OR rejection_hash IS NOT NULL
           OR rejected_at IS NOT NULL OR rejection_reason IS NOT NULL""")).scalar()
    if int(changed or 0):
        raise RuntimeError("agent action approval downgrade refused: persisted F1 approval data exists")
    task_ids = bind.execute(sa.text("SELECT COUNT(*) FROM agent_design_tasks WHERE client_task_id IS NOT NULL")).scalar()
    if int(task_ids or 0):
        raise RuntimeError("agent action approval downgrade refused: persisted F1 task idempotency data exists")
    op.drop_index("idx_agent_actions_approval_idempotency", table_name="agent_actions")
    op.drop_column("agent_actions", "rejection_reason")
    op.drop_column("agent_actions", "rejected_at")
    op.drop_column("agent_actions", "rejection_hash")
    op.drop_column("agent_actions", "rejection_idempotency_key")
    op.drop_column("agent_actions", "approval_hash")
    op.drop_column("agent_actions", "approval_idempotency_key")
    op.drop_constraint("uq_agent_design_tasks_client_task", "agent_design_tasks", type_="unique")
    op.drop_column("agent_design_tasks", "client_task_id")
