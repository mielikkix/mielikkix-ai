"""add seo_google_connections table

Revision ID: d3f6b8a1c5e7
Revises: c8e1f4a7b3d9
Create Date: 2026-09-20 00:00:02.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'd3f6b8a1c5e7'
down_revision = 'c8e1f4a7b3d9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'seo_google_connections',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id'), nullable=False, unique=True),
        sa.Column('refresh_token_encrypted', sa.Text(), nullable=False),
        sa.Column('google_account_email', sa.Text(), nullable=True),
        sa.Column('analytics_property_id', sa.Text(), nullable=True),
        sa.Column('search_console_site_url', sa.Text(), nullable=True),
        sa.Column('connected_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_seo_google_connections_business_id', 'seo_google_connections', ['business_id'])


def downgrade():
    op.drop_index('ix_seo_google_connections_business_id', table_name='seo_google_connections')
    op.drop_table('seo_google_connections')
