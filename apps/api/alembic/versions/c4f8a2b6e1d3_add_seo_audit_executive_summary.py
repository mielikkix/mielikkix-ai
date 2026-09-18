"""add executive_summary to seo_audits

Revision ID: c4f8a2b6e1d3
Revises: b3e7d1f9a2c6
Create Date: 2026-09-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c4f8a2b6e1d3'
down_revision = 'b3e7d1f9a2c6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('seo_audits', sa.Column('executive_summary', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('seo_audits', 'executive_summary')
