"""business_settings.require_chat_consent (widget "I agree" screen)

Revision ID: a6d2f8c4e1b9
Revises: d5f9b3e7a1c2
Create Date: 2026-09-26 00:00:02.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a6d2f8c4e1b9'
down_revision = 'd5f9b3e7a1c2'
branch_labels = None
depends_on = None


def upgrade():
    # Off for every existing tenant -- their widgets behave exactly as before.
    op.add_column(
        'business_settings',
        sa.Column('require_chat_consent', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column('business_settings', 'require_chat_consent')
