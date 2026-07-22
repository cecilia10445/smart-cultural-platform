"""non-destructive cultural product request and response contract"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("generation_logs", sa.Column("generation_kind", sa.String(48), nullable=True))
    op.add_column("generation_logs", sa.Column("prompt_template_version", sa.String(64), nullable=True))
    op.add_column("generation_logs", sa.Column("brief_json", mysql.JSON(), nullable=True))
    op.add_column("generation_logs", sa.Column("response_json", mysql.JSON(), nullable=True))


def downgrade():
    raise RuntimeError(
        "cultural product contract downgrade is disabled: it would remove persisted request and response records; "
        "automatic destructive downgrade is not allowed"
    )
