"""llm_usage_logs.business_id nullable

Revision ID: d7a3c1e9f2b4
Revises: c4f9a2e6b8d1
Create Date: 2026-10-02 00:00:00.000000

The AI Usage page now also records Claude/OpenAI calls from the Force
agents (core/llm_usage.py). The public demo pages (Support Triage, Voice,
Booking, Review demos) run with no logged-in business, so those rows have
no business_id.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'd7a3c1e9f2b4'
down_revision = 'c4f9a2e6b8d1'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('llm_usage_logs', 'business_id', existing_type=postgresql.UUID(as_uuid=True), nullable=True)


def downgrade():
    op.execute("DELETE FROM llm_usage_logs WHERE business_id IS NULL")
    op.alter_column('llm_usage_logs', 'business_id', existing_type=postgresql.UUID(as_uuid=True), nullable=False)
