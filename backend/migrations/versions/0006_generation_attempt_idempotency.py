"""add a client idempotency key to generation attempts"""

from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "generation_attempts",
        sa.Column("idempotency_key", sa.String(128), nullable=True),
    )
    op.create_unique_constraint(
        "uq_generation_attempts_user_idempotency",
        "generation_attempts",
        ["user_id", "idempotency_key"],
    )


def downgrade():
    raise RuntimeError(
        "generation attempt idempotency downgrade is disabled: persisted request ownership must not be removed"
    )
