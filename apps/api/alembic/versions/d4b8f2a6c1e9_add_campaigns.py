"""add campaigns

Revision ID: d4b8f2a6c1e9
Revises: b2d6e4f0a9c1
Create Date: 2026-09-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'd4b8f2a6c1e9'
down_revision = 'b2d6e4f0a9c1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'campaigns',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id'), nullable=False),
        sa.Column('mailchimp_audience_id', sa.Text(), nullable=True),
        sa.Column('mailchimp_audience_name', sa.Text(), nullable=True),
        sa.Column('mailchimp_campaign_id', sa.Text(), nullable=True),
        sa.Column('subject', sa.Text(), nullable=True),
        sa.Column('from_name', sa.Text(), nullable=True),
        sa.Column('from_email', sa.Text(), nullable=True),
        sa.Column('reply_to', sa.Text(), nullable=True),
        sa.Column('body_html', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False, server_default='draft'),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f('ix_campaigns_business_id'), 'campaigns', ['business_id'])


def downgrade():
    op.drop_index(op.f('ix_campaigns_business_id'), table_name='campaigns')
    op.drop_table('campaigns')
