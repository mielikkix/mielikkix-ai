"""add calendar_connections

Revision ID: ca2e62133dc7
Revises: 08657fbb9170
Create Date: 2026-08-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'ca2e62133dc7'
down_revision = '08657fbb9170'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'calendar_connections',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id'), nullable=False),
        sa.Column('refresh_token_encrypted', sa.Text(), nullable=False),
        sa.Column('calendar_id', sa.Text(), nullable=False, server_default='primary'),
        sa.Column('google_account_email', sa.Text(), nullable=True),
        sa.Column('connected_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        'ix_calendar_connections_business_id', 'calendar_connections', ['business_id'], unique=True
    )


def downgrade():
    op.drop_index('ix_calendar_connections_business_id', table_name='calendar_connections')
    op.drop_table('calendar_connections')
