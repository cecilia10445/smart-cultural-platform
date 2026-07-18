"""generation_logs baseline"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "generation_logs",
        sa.Column("id", mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("timestamp", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("style", sa.String(100), nullable=True),
        sa.Column("image_url", sa.String(2048), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("content", mysql.LONGTEXT(), nullable=True),
        sa.Column("generation_time", sa.Numeric(12, 3), nullable=True),
        sa.Column("content_length", mysql.INTEGER(unsigned=True), nullable=True),
        sa.Column("user_rating", sa.Numeric(3, 2), nullable=True),
        sa.Column("download_count", mysql.INTEGER(unsigned=True), nullable=False, server_default=sa.text("0")),
        sa.Column("user_age", mysql.TINYINT(unsigned=True), nullable=True),
        sa.Column("user_gender", mysql.TINYINT(unsigned=True), nullable=True),
        sa.Column("login_time", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("data_origin", sa.String(20), nullable=True, server_default=sa.text("'production'")),
        sa.CheckConstraint("data_origin IS NULL OR data_origin IN ('production','synthetic','test','public')", name="chk_generation_logs_data_origin"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_generation_logs_user_timestamp", "generation_logs", ["user_id", "timestamp"])
    op.create_index("idx_generation_logs_timestamp", "generation_logs", ["timestamp"])
    op.create_index("idx_generation_logs_style_timestamp", "generation_logs", ["style", "timestamp"])
    op.create_index("idx_generation_logs_event_timestamp", "generation_logs", ["event_type", "timestamp"])


def downgrade():
    raise RuntimeError(
        "baseline downgrade is disabled: generation_logs may be an adopted existing table; "
        "automatic deletion of this table is not allowed"
    )
