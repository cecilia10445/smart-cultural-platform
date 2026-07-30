"""versioned session context summaries
Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
revision='0009'; down_revision='0008'; branch_labels=None; depends_on=None
def upgrade():
 op.create_table('agent_context_summaries',sa.Column('id',sa.String(36),primary_key=True),sa.Column('user_id',sa.String(64),nullable=False),sa.Column('session_id',sa.String(36),nullable=False),sa.Column('schema_version',sa.String(32),nullable=False),sa.Column('summary_json',mysql.JSON(),nullable=False),sa.Column('source_message_start_id',sa.String(36)),sa.Column('source_message_end_id',sa.String(36)),sa.Column('source_message_count',mysql.INTEGER(unsigned=True),nullable=False),sa.Column('session_version',mysql.INTEGER(unsigned=True),nullable=False),sa.Column('status',sa.String(16),nullable=False),sa.Column('created_at',mysql.DATETIME(fsp=6),nullable=False),sa.Column('updated_at',mysql.DATETIME(fsp=6),nullable=False),sa.ForeignKeyConstraint(['session_id'],['agent_sessions.id'],name='fk_agent_context_summaries_session'),mysql_engine='InnoDB',mysql_charset='utf8mb4')
 op.create_index('idx_agent_context_summaries_active','agent_context_summaries',['user_id','session_id','status','updated_at'])
def downgrade(): op.drop_table('agent_context_summaries')
