"""create agent dialogue session persistence

Revision ID: 0007
Revises: 0006
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


_SESSION_STATES = "'created','extracting_brief','waiting_brief_confirmation','generating_product_text','waiting_text_feedback','building_visual_prompt','waiting_image_confirmation','generating_image','completed','failed'"


def upgrade():
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(48), nullable=False),
        sa.Column("current_stage", sa.String(48), nullable=False),
        sa.Column("text_revision_count", mysql.TINYINT(unsigned=True), nullable=False, server_default=sa.text("0")),
        sa.Column("generation_log_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("brief_json", mysql.JSON(), nullable=True),
        sa.Column("confirmed_text_json", mysql.JSON(), nullable=True),
        sa.Column("image_prompt_json", mysql.JSON(), nullable=True),
        sa.Column("context_summary_json", mysql.JSON(), nullable=True),
        sa.Column("error_json", mysql.JSON(), nullable=True),
        sa.Column("failure_stage", sa.String(48), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("version", mysql.INTEGER(unsigned=True), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("completed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.CheckConstraint(f"status IN ({_SESSION_STATES})", name="chk_agent_sessions_status"),
        sa.CheckConstraint(f"current_stage IN ({_SESSION_STATES})", name="chk_agent_sessions_current_stage"),
        sa.CheckConstraint("text_revision_count BETWEEN 0 AND 4", name="chk_agent_sessions_revision_count"),
        sa.CheckConstraint("version >= 1", name="chk_agent_sessions_version"),
        sa.ForeignKeyConstraint(["generation_log_id"], ["generation_logs.id"], name="fk_agent_sessions_generation_log"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_agent_sessions_user_updated", "agent_sessions", ["user_id", "updated_at"])
    op.create_index("idx_agent_sessions_user_id", "agent_sessions", ["user_id", "id"])

    op.create_table(
        "agent_messages",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("sequence_no", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("message_type", sa.String(48), nullable=False),
        sa.Column("content_text", mysql.TEXT(), nullable=False),
        sa.Column("content_json", mysql.JSON(), nullable=True),
        sa.Column("client_turn_id", sa.String(128), nullable=True),
        sa.Column("decision_id", sa.String(128), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint("sequence_no >= 1", name="chk_agent_messages_sequence"),
        sa.CheckConstraint("role IN ('user','assistant','system')", name="chk_agent_messages_role"),
        sa.CheckConstraint("client_turn_id IS NULL OR decision_id IS NULL", name="chk_agent_messages_idempotency_source"),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], name="fk_agent_messages_session"),
        sa.UniqueConstraint("session_id", "sequence_no", name="uq_agent_messages_session_sequence"),
        # MySQL permits multiple NULLs in a UNIQUE constraint while rejecting a
        # repeated non-NULL value for the same session, which is desired here.
        sa.UniqueConstraint("session_id", "client_turn_id", name="uq_agent_messages_session_turn"),
        sa.UniqueConstraint("session_id", "decision_id", name="uq_agent_messages_session_decision"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_agent_messages_session_sequence", "agent_messages", ["session_id", "sequence_no"])

    op.create_table(
        "agent_steps",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("ordinal", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("stage", sa.String(48), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("tool_name", sa.String(80), nullable=True),
        sa.Column("skill_id", sa.String(80), nullable=True),
        sa.Column("skill_version", sa.String(64), nullable=True),
        sa.Column("input_summary_json", mysql.JSON(), nullable=True),
        sa.Column("output_summary_json", mysql.JSON(), nullable=True),
        sa.Column("tool_result_summary_json", mysql.JSON(), nullable=True),
        sa.Column("error_json", mysql.JSON(), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("started_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("finished_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("latency_ms", mysql.INTEGER(unsigned=True), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint("ordinal >= 1", name="chk_agent_steps_ordinal"),
        sa.CheckConstraint("status IN ('pending','running','completed','failed')", name="chk_agent_steps_status"),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], name="fk_agent_steps_session"),
        sa.UniqueConstraint("session_id", "ordinal", name="uq_agent_steps_session_ordinal"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_agent_steps_session_ordinal", "agent_steps", ["session_id", "ordinal"])


def downgrade():
    raise RuntimeError(
        "agent dialogue session downgrade is disabled: persisted owner-scoped conversations must not be removed"
    )
