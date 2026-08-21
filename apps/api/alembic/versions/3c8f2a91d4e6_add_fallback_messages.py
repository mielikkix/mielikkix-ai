"""add fallback_messages

Revision ID: 3c8f2a91d4e6
Revises: 9a1c3e7d5f21
Create Date: 2026-08-06 15:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '3c8f2a91d4e6'
down_revision = '9a1c3e7d5f21'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'business_settings',
        sa.Column('fallback_messages', sa.JSON(), nullable=True, server_default='{}'),
    )


def downgrade():
    op.drop_column('business_settings', 'fallback_messages')
