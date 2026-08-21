"""add welcome_messages

Revision ID: 9a1c3e7d5f21
Revises: 7f3a9c1e5b02
Create Date: 2026-08-06 18:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '9a1c3e7d5f21'
down_revision = '7f3a9c1e5b02'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'business_settings',
        sa.Column('welcome_messages', sa.JSON(), nullable=True, server_default='{}'),
    )


def downgrade():
    op.drop_column('business_settings', 'welcome_messages')
