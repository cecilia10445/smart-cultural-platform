"""persist agent runtime turns separately from business state-machine steps

Revision ID: 0008
Revises: 0007
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_runtime_runs",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("client_turn_id", sa.String(128), nullable=False),
        sa.Column("agent_name", sa.String(80), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("session_status_at_start", sa.String(48), nullable=False),
        sa.Column("model_request_count", mysql.INTEGER(unsigned=True), nullable=False, server_default=sa.text("0")),
        sa.Column("tool_call_count", mysql.INTEGER(unsigned=True), nullable=False, server_default=sa.text("0")),
        sa.Column("final_output_type", sa.String(80), nullable=True),
        sa.Column("final_output_json", mysql.JSON(), nullable=True),
        sa.Column("pending_approval_json", mysql.JSON(), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_summary", sa.String(1000), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("completed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.CheckConstraint("status IN ('running','completed','pending_approval','failed')", name="chk_agent_runtime_runs_status"),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], name="fk_agent_runtime_runs_session"),
        sa.UniqueConstraint("user_id", "session_id", "client_turn_id", name="uq_agent_runtime_runs_owner_turn"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_agent_runtime_runs_owner_session", "agent_runtime_runs", ["user_id", "session_id", "created_at"])
    op.create_table(
        "agent_runtime_events",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("sequence_number", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("tool_call_id", sa.String(128), nullable=True), sa.Column("tool_name", sa.String(80), nullable=True),
        sa.Column("risk", sa.String(24), nullable=True), sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True), sa.Column("duration_ms", mysql.INTEGER(unsigned=True), nullable=True),
        sa.Column("arguments_hash", sa.String(128), nullable=True), sa.Column("input_summary_json", mysql.JSON(), nullable=True),
        sa.Column("output_summary_json", mysql.JSON(), nullable=True), sa.Column("budget_snapshot_json", mysql.JSON(), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runtime_runs.id"], name="fk_agent_runtime_events_run"),
        sa.UniqueConstraint("run_id", "sequence_number", name="uq_agent_runtime_events_sequence"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_agent_runtime_events_run_sequence", "agent_runtime_events", ["run_id", "sequence_number"])


def downgrade():
    op.drop_table("agent_runtime_events")
    op.drop_table("agent_runtime_runs")
