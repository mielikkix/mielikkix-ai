"""leads.notes

Revision ID: e5b2d8f1a3c6
Revises: d7a3c1e9f2b4
Create Date: 2026-10-02 00:00:00.000000

The owner's own notes on a lead (Leads page, QA 2026-10-02 E2).
"""
from alembic import op
import sqlalchemy as sa


revision = 'e5b2d8f1a3c6'
down_revision = 'd7a3c1e9f2b4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('leads', sa.Column('notes', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('leads', 'notes')
