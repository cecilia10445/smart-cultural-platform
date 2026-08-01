"""add safe external outcome state for image actions

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("agent_actions", sa.Column("external_outcome_status", sa.String(32)))
    op.add_column("agent_actions", sa.Column("provider_request_id", sa.String(128)))
    op.create_index("idx_agent_actions_external_outcome", "agent_actions", ["user_id", "status", "external_outcome_status"])

def downgrade():
    bind = op.get_bind()
    changed = bind.execute(sa.text("SELECT COUNT(*) FROM agent_actions WHERE external_outcome_status IS NOT NULL OR provider_request_id IS NOT NULL")).scalar()
    if int(changed or 0): raise RuntimeError("agent image action downgrade refused: persisted F3 external outcome data exists")
    op.drop_index("idx_agent_actions_external_outcome", table_name="agent_actions")
    op.drop_column("agent_actions", "provider_request_id")
    op.drop_column("agent_actions", "external_outcome_status")
