"""add consent_records table and users.country (GDPR Phase 3)

Revision ID: b7d2e4f6a8c1
Revises: e2b5c9f3a7d1
Create Date: 2026-09-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'b7d2e4f6a8c1'
down_revision = 'e2b5c9f3a7d1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('country', sa.Text(), nullable=True))
    op.create_table(
        'consent_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('type', sa.Text(), nullable=False),
        sa.Column('document_version', sa.Text(), nullable=True),
        sa.Column('granted', sa.Boolean(), nullable=False),
        sa.Column('granted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('ip_hash', sa.Text(), nullable=True),
    )
    op.create_index('ix_consent_records_user_type', 'consent_records', ['user_id', 'type'])


def downgrade():
    op.drop_index('ix_consent_records_user_type', table_name='consent_records')
    op.drop_table('consent_records')
    op.drop_column('users', 'country')
