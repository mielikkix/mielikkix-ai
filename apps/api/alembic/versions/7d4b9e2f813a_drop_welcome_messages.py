"""drop welcome_messages

Revision ID: 7d4b9e2f813a
Revises: 3c8f2a91d4e6
Create Date: 2026-08-07 09:10:00.000000

The greeting is now always shown in the business's primary configured
language (see Widget.tsx) -- there's no message yet at that point to detect
a visitor's language from, so a per-language welcome message can never
actually be shown. Only fallback_messages (picked per-message, after there's
something to detect from) stays per-language.
"""
from alembic import op
import sqlalchemy as sa


revision = '7d4b9e2f813a'
down_revision = '3c8f2a91d4e6'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('business_settings', 'welcome_messages')


def downgrade():
    op.add_column(
        'business_settings',
        sa.Column('welcome_messages', sa.JSON(), nullable=True, server_default='{}'),
    )
