"""non-destructive request attempts and model-call metrics"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "generation_attempts",
        sa.Column("request_id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("data_origin", sa.String(20), nullable=False),
        sa.Column("generation_kind", sa.String(48), nullable=False),
        sa.Column("prompt_template_version", sa.String(64), nullable=False),
        sa.Column("brief_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("failed_stage", sa.String(32), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("generation_log_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("total_latency_ms", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
        sa.Column("finished_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.CheckConstraint("status IN ('RUNNING','SUCCEEDED','FAILED')", name="chk_generation_attempts_status"),
        sa.CheckConstraint("data_origin IN ('production','synthetic','test','public')", name="chk_generation_attempts_data_origin"),
        sa.ForeignKeyConstraint(["generation_log_id"], ["generation_logs.id"], name="fk_generation_attempts_generation_log"),
    )
    op.create_index("idx_generation_attempts_status_created", "generation_attempts", ["status", "created_at"])
    op.create_index("idx_generation_attempts_user_created", "generation_attempts", ["user_id", "created_at"])
    op.create_table(
        "model_call_metrics",
        sa.Column("id", mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("latency_ms", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("provider_http_status", mysql.INTEGER(unsigned=True), nullable=True),
        sa.Column("provider_error_code", sa.String(128), nullable=True),
        sa.Column("input_tokens", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("output_tokens", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("total_tokens", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("image_count", mysql.INTEGER(unsigned=True), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
        sa.CheckConstraint("stage IN ('text_generation','image_generation')", name="chk_model_call_metrics_stage"),
        sa.CheckConstraint("status IN ('SUCCEEDED','FAILED')", name="chk_model_call_metrics_status"),
        sa.UniqueConstraint("request_id", "stage", name="uq_model_call_metrics_request_stage"),
        sa.ForeignKeyConstraint(["request_id"], ["generation_attempts.request_id"], name="fk_model_call_metrics_attempt"),
    )
    op.create_index("idx_model_call_metrics_request", "model_call_metrics", ["request_id"])
    op.create_index("idx_model_call_metrics_stage_created", "model_call_metrics", ["stage", "created_at"])


def downgrade():
    raise RuntimeError("generation attempt tracking downgrade is disabled: persisted observability records must not be removed")
