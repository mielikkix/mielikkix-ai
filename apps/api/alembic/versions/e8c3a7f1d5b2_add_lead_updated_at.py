"""add updated_at to leads

Revision ID: e8c3a7f1d5b2
Revises: d4b8f2a6c1e9
Create Date: 2026-09-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e8c3a7f1d5b2'
down_revision = 'd4b8f2a6c1e9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('leads', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    # Existing rows have no real "last updated" history -- backfill to
    # created_at (the most honest available value: "as far as we know,
    # this row hasn't changed since it was created") rather than leaving
    # it null or defaulting every existing row to "now".
    op.execute("UPDATE leads SET updated_at = created_at WHERE updated_at IS NULL")


def downgrade():
    op.drop_column('leads', 'updated_at')
