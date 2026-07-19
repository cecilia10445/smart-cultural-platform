"""analytics data contract and incremental watermark fields"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "generation_logs",
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
    )
    op.add_column(
        "generation_logs",
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"),
        ),
    )
    op.create_index("idx_generation_logs_updated_id", "generation_logs", ["updated_at", "id"])

    op.create_table(
        "etl_batches",
        sa.Column("batch_id", mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("pipeline_name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("watermark_start_time", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("watermark_start_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("watermark_end_time", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("watermark_end_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("source_count", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("hive_count", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("output_count", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("started_at", mysql.DATETIME(fsp=6), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
        sa.Column("finished_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.CheckConstraint("status IN ('RUNNING','SUCCEEDED','FAILED')", name="chk_etl_batches_status"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_etl_batches_pipeline_started", "etl_batches", ["pipeline_name", "started_at"])
    op.create_index("idx_etl_batches_status_started", "etl_batches", ["status", "started_at"])

    op.create_table(
        "data_quality_results",
        sa.Column("id", mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("batch_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("check_name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("expected_value", sa.String(255), nullable=True),
        sa.Column("actual_value", sa.String(255), nullable=True),
        sa.Column("checked_at", mysql.DATETIME(fsp=6), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
        sa.CheckConstraint("status IN ('PASSED','FAILED')", name="chk_data_quality_results_status"),
        sa.ForeignKeyConstraint(["batch_id"], ["etl_batches.batch_id"], name="fk_data_quality_results_batch"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_data_quality_results_batch_check", "data_quality_results", ["batch_id", "check_name"])
    op.create_index("idx_data_quality_results_status_checked", "data_quality_results", ["status", "checked_at"])


def downgrade():
    raise RuntimeError(
        "analytics contract downgrade is disabled: it would remove incremental watermark columns "
        "or control-table data; automatic destructive downgrade is not allowed"
    )
