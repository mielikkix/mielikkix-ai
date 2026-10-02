"""conversations.language

Revision ID: a8d3f6c2e9b5
Revises: f2c8a4d6b1e3
Create Date: 2026-10-02 00:00:00.000000

Language of the visitor's latest message, shown in the Conversations list
(QA 2026-10-02, E3).
"""
from alembic import op
import sqlalchemy as sa


revision = 'a8d3f6c2e9b5'
down_revision = 'f2c8a4d6b1e3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('conversations', sa.Column('language', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('conversations', 'language')
