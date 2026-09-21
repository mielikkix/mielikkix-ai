"""add audit_schedule fields to seo_websites

Revision ID: c8e1f4a7b3d9
Revises: f7c2a9d4e8b1
Create Date: 2026-09-20 00:00:01.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c8e1f4a7b3d9'
down_revision = 'f7c2a9d4e8b1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('seo_websites', sa.Column('audit_schedule', sa.Text(), nullable=True))
    op.add_column('seo_websites', sa.Column('next_scheduled_audit_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('seo_websites', 'next_scheduled_audit_at')
    op.drop_column('seo_websites', 'audit_schedule')
