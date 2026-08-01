"""add nonlinear agent domain graph foundations

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

TASK_STATES = "'exploring','active','paused','closed'"
ARTIFACT_TYPES = "'brief','product_design_text','visual_direction','image_prompt','generated_image'"
ARTIFACT_STATES = "'proposed','confirmed','superseded'"
ACTION_TYPES = "'save_brief','save_design_text','apply_revision','build_visual_direction','generate_image_from_conversation','generate_image_from_artifact','regenerate_image','archive_task'"
ACTION_STATES = "'requested','approved','rejected','running','completed','failed','retry_requested'"


def upgrade():
    op.create_table("agent_design_tasks",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(64), nullable=False), sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(255), nullable=False), sa.Column("status", sa.String(16), nullable=False), sa.Column("origin", sa.String(24), nullable=False),
        sa.Column("version", mysql.INTEGER(unsigned=True), nullable=False, server_default=sa.text("1")), sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False), sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("paused_at", mysql.DATETIME(fsp=6)), sa.Column("closed_at", mysql.DATETIME(fsp=6)),
        sa.CheckConstraint(f"status IN ({TASK_STATES})", name="chk_agent_design_tasks_status"), sa.CheckConstraint("origin IN ('native','legacy_import')", name="chk_agent_design_tasks_origin"), sa.CheckConstraint("version >= 1", name="chk_agent_design_tasks_version"),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], name="fk_agent_design_tasks_session"), mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_0900_ai_ci")
    op.create_index("idx_agent_design_tasks_owner_session_status", "agent_design_tasks", ["user_id", "session_id", "status"])
    op.create_index("idx_agent_design_tasks_owner_session_updated", "agent_design_tasks", ["user_id", "session_id", "updated_at"])

    op.create_table("agent_actions",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(64), nullable=False), sa.Column("session_id", sa.String(36), nullable=False), sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("action_type", sa.String(48), nullable=False), sa.Column("status", sa.String(24), nullable=False), sa.Column("idempotency_key", sa.String(128), nullable=False), sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("expected_task_version", mysql.INTEGER(unsigned=True)), sa.Column("source_runtime_run_id", sa.String(36)), sa.Column("source_artifact_ids_json", mysql.JSON()), sa.Column("proposal_snapshot_json", mysql.JSON()), sa.Column("approval_snapshot_json", mysql.JSON()), sa.Column("result_json", mysql.JSON()),
        sa.Column("error_code", sa.String(80)), sa.Column("error_summary", sa.String(1000)), sa.Column("generation_log_id", mysql.BIGINT(unsigned=True)), sa.Column("retry_of_action_id", sa.String(36)),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False), sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False), sa.Column("approved_at", mysql.DATETIME(fsp=6)), sa.Column("completed_at", mysql.DATETIME(fsp=6)),
        sa.CheckConstraint(f"action_type IN ({ACTION_TYPES})", name="chk_agent_actions_type"), sa.CheckConstraint(f"status IN ({ACTION_STATES})", name="chk_agent_actions_status"), sa.CheckConstraint("expected_task_version IS NULL OR expected_task_version >= 1", name="chk_agent_actions_expected_task_version"),
        sa.ForeignKeyConstraint(["task_id"], ["agent_design_tasks.id"], name="fk_agent_actions_task"), sa.ForeignKeyConstraint(["source_runtime_run_id"], ["agent_runtime_runs.id"], name="fk_agent_actions_runtime_run"), sa.ForeignKeyConstraint(["generation_log_id"], ["generation_logs.id"], name="fk_agent_actions_generation_log"), sa.ForeignKeyConstraint(["retry_of_action_id"], ["agent_actions.id"], name="fk_agent_actions_retry"),
        sa.UniqueConstraint("user_id", "task_id", "action_type", "idempotency_key", name="uq_agent_actions_task_idempotency"), mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_0900_ai_ci")
    op.create_index("idx_agent_actions_owner_task_status_type", "agent_actions", ["user_id", "task_id", "status", "action_type"])
    op.create_index("idx_agent_actions_owner_session_created", "agent_actions", ["user_id", "session_id", "created_at"])

    op.create_table("agent_artifacts",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(64), nullable=False), sa.Column("session_id", sa.String(36), nullable=False), sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("artifact_type", sa.String(32), nullable=False), sa.Column("status", sa.String(16), nullable=False), sa.Column("version_number", mysql.INTEGER(unsigned=True), nullable=False), sa.Column("parent_artifact_id", sa.String(36)),
        sa.Column("source_runtime_run_id", sa.String(36)), sa.Column("source_action_id", sa.String(36)), sa.Column("content_json", mysql.JSON(), nullable=False), sa.Column("content_hash", sa.String(64), nullable=False), sa.Column("generation_log_id", mysql.BIGINT(unsigned=True)), sa.Column("origin", sa.String(24), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False), sa.Column("confirmed_at", mysql.DATETIME(fsp=6)), sa.Column("superseded_at", mysql.DATETIME(fsp=6)),
        sa.CheckConstraint(f"artifact_type IN ({ARTIFACT_TYPES})", name="chk_agent_artifacts_type"), sa.CheckConstraint(f"status IN ({ARTIFACT_STATES})", name="chk_agent_artifacts_status"), sa.CheckConstraint("origin IN ('native','legacy_projection','legacy_import')", name="chk_agent_artifacts_origin"), sa.CheckConstraint("version_number >= 1", name="chk_agent_artifacts_version"),
        sa.ForeignKeyConstraint(["task_id"], ["agent_design_tasks.id"], name="fk_agent_artifacts_task"), sa.ForeignKeyConstraint(["parent_artifact_id"], ["agent_artifacts.id"], name="fk_agent_artifacts_parent"), sa.ForeignKeyConstraint(["source_runtime_run_id"], ["agent_runtime_runs.id"], name="fk_agent_artifacts_runtime_run"), sa.ForeignKeyConstraint(["source_action_id"], ["agent_actions.id"], name="fk_agent_artifacts_action"), sa.ForeignKeyConstraint(["generation_log_id"], ["generation_logs.id"], name="fk_agent_artifacts_generation_log"),
        sa.UniqueConstraint("task_id", "artifact_type", "version_number", name="uq_agent_artifacts_task_type_version"), mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_0900_ai_ci")
    op.create_index("idx_agent_artifacts_owner_task_type_created", "agent_artifacts", ["user_id", "task_id", "artifact_type", "created_at"])
    op.create_index("idx_agent_artifacts_owner_session_created", "agent_artifacts", ["user_id", "session_id", "created_at"])

    op.add_column("agent_sessions", sa.Column("conversation_status", sa.String(16), nullable=False, server_default=sa.text("'active'")))
    op.add_column("agent_sessions", sa.Column("active_task_id", sa.String(36)))
    op.add_column("agent_sessions", sa.Column("archived_at", mysql.DATETIME(fsp=6)))
    op.create_check_constraint("chk_agent_sessions_conversation_status", "agent_sessions", "conversation_status IN ('active','archived')")
    op.create_foreign_key("fk_agent_sessions_active_task", "agent_sessions", "agent_design_tasks", ["active_task_id"], ["id"])
    op.create_index("idx_agent_sessions_owner_conversation_status", "agent_sessions", ["user_id", "conversation_status", "updated_at"])
    for table, index, columns in (("agent_messages", "idx_agent_messages_session_task_sequence", ["session_id", "task_id", "sequence_no"]), ("agent_runtime_runs", "idx_agent_runtime_runs_owner_task_created", ["user_id", "task_id", "created_at"]), ("agent_context_summaries", "idx_agent_context_summaries_owner_task_updated", ["user_id", "task_id", "updated_at"])):
        op.add_column(table, sa.Column("task_id", sa.String(36)))
        op.create_foreign_key(f"fk_{table}_task", table, "agent_design_tasks", ["task_id"], ["id"])
        op.create_index(index, table, columns)


def downgrade():
    bind = op.get_bind()
    checks = ("SELECT COUNT(*) FROM agent_design_tasks", "SELECT COUNT(*) FROM agent_artifacts", "SELECT COUNT(*) FROM agent_actions", "SELECT COUNT(*) FROM agent_sessions WHERE active_task_id IS NOT NULL OR archived_at IS NOT NULL OR conversation_status <> 'active'", "SELECT COUNT(*) FROM agent_messages WHERE task_id IS NOT NULL", "SELECT COUNT(*) FROM agent_runtime_runs WHERE task_id IS NOT NULL", "SELECT COUNT(*) FROM agent_context_summaries WHERE task_id IS NOT NULL")
    if any(int(bind.execute(sa.text(query)).scalar() or 0) for query in checks):
        raise RuntimeError("agent domain graph downgrade refused: persisted F0 domain data exists")
    for table, index in (("agent_context_summaries", "idx_agent_context_summaries_owner_task_updated"), ("agent_runtime_runs", "idx_agent_runtime_runs_owner_task_created"), ("agent_messages", "idx_agent_messages_session_task_sequence")):
        op.drop_index(index, table_name=table); op.drop_constraint(f"fk_{table}_task", table, type_="foreignkey"); op.drop_column(table, "task_id")
    op.drop_index("idx_agent_sessions_owner_conversation_status", table_name="agent_sessions")
    op.drop_constraint("fk_agent_sessions_active_task", "agent_sessions", type_="foreignkey")
    op.drop_constraint("chk_agent_sessions_conversation_status", "agent_sessions", type_="check")
    op.drop_column("agent_sessions", "archived_at"); op.drop_column("agent_sessions", "active_task_id"); op.drop_column("agent_sessions", "conversation_status")
    op.drop_table("agent_artifacts"); op.drop_table("agent_actions"); op.drop_table("agent_design_tasks")
