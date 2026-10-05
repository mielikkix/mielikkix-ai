"""users.locale

Revision ID: c5d2e8a1f4b6
Revises: b9e4c7a1d3f8
Create Date: 2026-10-05 00:00:00.000000

The dashboard's UI language per user, "en" or "nb" (NULL = not chosen yet,
treated as English). See app/core/locale.py.
"""
from alembic import op
import sqlalchemy as sa


revision = 'c5d2e8a1f4b6'
down_revision = 'b9e4c7a1d3f8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('locale', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('users', 'locale')
