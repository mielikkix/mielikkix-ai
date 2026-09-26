"""business_settings.privacy_policy_url + conversation_retention_days (GDPR Phase 5)

Revision ID: d5f9b3e7a1c2
Revises: c4e8a2d6f1b3
Create Date: 2026-09-26 00:00:01.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd5f9b3e7a1c2'
down_revision = 'c4e8a2d6f1b3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('business_settings', sa.Column('privacy_policy_url', sa.Text(), nullable=True))
    # Existing tenants get the default 90 days. Their conversations older
    # than that are deleted on the first nightly run after deploy.
    op.add_column(
        'business_settings',
        sa.Column('conversation_retention_days', sa.Integer(), nullable=False, server_default='90'),
    )


def downgrade():
    op.drop_column('business_settings', 'conversation_retention_days')
    op.drop_column('business_settings', 'privacy_policy_url')
