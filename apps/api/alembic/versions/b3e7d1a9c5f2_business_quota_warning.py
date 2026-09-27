"""businesses.quota_warning_month/level (soft conversation limit warnings)

Revision ID: b3e7d1a9c5f2
Revises: a6d2f8c4e1b9
Create Date: 2026-09-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b3e7d1a9c5f2'
down_revision = 'a6d2f8c4e1b9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('businesses', sa.Column('quota_warning_month', sa.Text(), nullable=True))
    op.add_column('businesses', sa.Column('quota_warning_level', sa.Integer(), nullable=False, server_default='0'))


def downgrade():
    op.drop_column('businesses', 'quota_warning_level')
    op.drop_column('businesses', 'quota_warning_month')
