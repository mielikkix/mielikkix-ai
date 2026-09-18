"""add business_agent_access

Revision ID: f1a9c3e7b2d4
Revises: e8c3a7f1d5b2
Create Date: 2026-09-18 00:00:00.000000

"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'f1a9c3e7b2d4'
down_revision = 'e8c3a7f1d5b2'
branch_labels = None
depends_on = None

# The 4 agents that used to be bundled for free into the Business/Growth
# chat-widget plan tiers via PlanFeatures.*_enabled (see
# app/core/plans.py's removal of those fields in this same change) --
# grandfathered below so no currently-active customer silently loses
# access to something they already had. Voice Receptionist and Support
# Triage never had a plan flag to backfill from (they're still hardcoded
# single-tenant, see app/core/agent_catalog.py), so nothing to grandfather
# for them.
_GRANDFATHERED_AGENT_KEYS = [
    "booking_assistant",
    "review_reputation",
    "email_marketing",
    "seo_audit_optimization",
]


def upgrade():
    op.create_table(
        'business_agent_access',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id'), nullable=False),
        sa.Column('agent_key', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default='active'),
        sa.Column('activated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('business_id', 'agent_key', name='uq_business_agent_access'),
    )
    op.create_index('ix_business_agent_access_business_id', 'business_agent_access', ['business_id'])

    bind = op.get_bind()
    business_ids = [
        row[0]
        for row in bind.execute(sa.text("SELECT id FROM businesses WHERE plan IN ('business', 'growth')"))
    ]
    for business_id in business_ids:
        for agent_key in _GRANDFATHERED_AGENT_KEYS:
            bind.execute(
                sa.text(
                    "INSERT INTO business_agent_access (id, business_id, agent_key, status, activated_at) "
                    "VALUES (:id, :business_id, :agent_key, 'active', now())"
                ),
                {"id": str(uuid.uuid4()), "business_id": str(business_id), "agent_key": agent_key},
            )


def downgrade():
    op.drop_index('ix_business_agent_access_business_id', table_name='business_agent_access')
    op.drop_table('business_agent_access')
