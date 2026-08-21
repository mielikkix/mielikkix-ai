"""add llm_usage_logs table

Revision ID: c1d9f4a2b6e3
Revises: b2e6f1a4c9d7
Create Date: 2026-08-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'c1d9f4a2b6e3'
down_revision = 'b2e6f1a4c9d7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'llm_usage_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id'), nullable=False),
        sa.Column('provider', sa.Text(), nullable=False),
        sa.Column('model', sa.Text(), nullable=True),
        sa.Column('kind', sa.Text(), nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completion_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_llm_usage_logs_business_id', 'llm_usage_logs', ['business_id'])
    op.create_index('ix_llm_usage_logs_created_at', 'llm_usage_logs', ['created_at'])


def downgrade():
    op.drop_index('ix_llm_usage_logs_created_at', table_name='llm_usage_logs')
    op.drop_index('ix_llm_usage_logs_business_id', table_name='llm_usage_logs')
    op.drop_table('llm_usage_logs')
