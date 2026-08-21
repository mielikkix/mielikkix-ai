"""add plan-related columns and business_websites table

Revision ID: 7f3a9c1e5b02
Revises: 48d57a17b8ea
Create Date: 2026-08-01 15:05:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '7f3a9c1e5b02'
down_revision = '48d57a17b8ea'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('businesses', sa.Column('api_access_addon', sa.Boolean(), server_default=sa.false(), nullable=True))
    op.add_column('businesses', sa.Column('api_key', sa.Text(), nullable=True))

    op.create_table(
        'business_websites',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id'), nullable=False),
        sa.Column('domain', sa.Text(), nullable=False),
        sa.Column('label', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_business_websites_business_id', 'business_websites', ['business_id'])


def downgrade():
    op.drop_index('ix_business_websites_business_id', table_name='business_websites')
    op.drop_table('business_websites')
    op.drop_column('businesses', 'api_key')
    op.drop_column('businesses', 'api_access_addon')
