"""documents.title, documents.char_count

Revision ID: b9e4c7a1d3f8
Revises: a8d3f6c2e9b5
Create Date: 2026-10-02 00:00:00.000000

Shown in the Documents list (QA 2026-10-02, E6).
"""
from alembic import op
import sqlalchemy as sa


revision = 'b9e4c7a1d3f8'
down_revision = 'a8d3f6c2e9b5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('documents', sa.Column('title', sa.Text(), nullable=True))
    op.add_column('documents', sa.Column('char_count', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('documents', 'char_count')
    op.drop_column('documents', 'title')
