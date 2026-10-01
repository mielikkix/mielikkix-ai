"""re-add business_settings.welcome_messages

Revision ID: c4f9a2e6b8d1
Revises: b3e7d1a9c5f2
Create Date: 2026-10-01 00:00:00.000000

7d4b9e2f813a dropped this because, before the visitor types anything, there
was no signal for which language to greet them in. There is one now: the
widget reads the host page's own <html lang> (see Widget.tsx's pageLanguage),
so a site switched to Norwegian can greet in Norwegian. QA 2026-10-01 (B16):
mielikkix.ai in Norsk still greeted visitors in English.
"""
from alembic import op
import sqlalchemy as sa


revision = 'c4f9a2e6b8d1'
down_revision = 'b3e7d1a9c5f2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'business_settings',
        sa.Column('welcome_messages', sa.JSON(), nullable=True, server_default='{}'),
    )


def downgrade():
    op.drop_column('business_settings', 'welcome_messages')
