"""add seo_performance_measurements

Revision ID: e6b9d3f8a1c7
Revises: d5a8c2f4b7e9
Create Date: 2026-09-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'e6b9d3f8a1c7'
down_revision = 'd5a8c2f4b7e9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'seo_performance_measurements',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('audit_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('seo_audits.id', ondelete='CASCADE'), nullable=False),
        sa.Column('strategy', sa.Text(), nullable=False),
        sa.Column('performance_score', sa.Integer(), nullable=True),
        sa.Column('lcp_ms', sa.Integer(), nullable=True),
        sa.Column('cls', sa.Float(), nullable=True),
        sa.Column('inp_ms', sa.Integer(), nullable=True),
        sa.Column('tbt_ms', sa.Integer(), nullable=True),
        sa.Column('measured_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_seo_performance_measurements_audit_id', 'seo_performance_measurements', ['audit_id'])


def downgrade():
    op.drop_index('ix_seo_performance_measurements_audit_id', table_name='seo_performance_measurements')
    op.drop_table('seo_performance_measurements')
