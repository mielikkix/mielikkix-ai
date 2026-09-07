"""add mailchimp_connections table

Revision ID: b2d6e4f0a9c1
Revises: f8a1c3e9d2b7
Create Date: 2026-09-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'b2d6e4f0a9c1'
down_revision = 'f8a1c3e9d2b7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'mailchimp_connections',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id'), nullable=False),
        sa.Column('access_token_encrypted', sa.Text(), nullable=False),
        sa.Column('server_prefix', sa.Text(), nullable=False),
        sa.Column('account_name', sa.Text(), nullable=True),
        sa.Column('login_email', sa.Text(), nullable=True),
        sa.Column('audience_id', sa.Text(), nullable=True),
        sa.Column('audience_name', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('connected_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f('ix_mailchimp_connections_business_id'),
        'mailchimp_connections',
        ['business_id'],
        unique=True,
    )


def downgrade():
    op.drop_index(op.f('ix_mailchimp_connections_business_id'), table_name='mailchimp_connections')
    op.drop_table('mailchimp_connections')
