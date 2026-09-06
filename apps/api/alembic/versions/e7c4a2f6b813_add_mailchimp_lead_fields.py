"""add mailchimp lead fields

Revision ID: e7c4a2f6b813
Revises: a3f9d21c7b4e
Create Date: 2026-09-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e7c4a2f6b813'
down_revision = 'a3f9d21c7b4e'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('leads', sa.Column('first_name', sa.Text(), nullable=True))
    op.add_column('leads', sa.Column('last_name', sa.Text(), nullable=True))
    op.add_column('leads', sa.Column('company', sa.Text(), nullable=True))
    op.add_column('leads', sa.Column('industry', sa.Text(), nullable=True))
    op.add_column('leads', sa.Column('interest', sa.Text(), nullable=True))
    op.add_column('leads', sa.Column('source', sa.Text(), nullable=True))
    op.add_column(
        'leads',
        sa.Column('marketing_consent', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column('leads', sa.Column('marketing_consent_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        'leads',
        sa.Column('mailchimp_synced', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column('leads', sa.Column('mailchimp_contact_id', sa.Text(), nullable=True))
    op.add_column('leads', sa.Column('mailchimp_last_synced_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_leads_email'), 'leads', ['email'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_leads_email'), table_name='leads')
    op.drop_column('leads', 'mailchimp_last_synced_at')
    op.drop_column('leads', 'mailchimp_contact_id')
    op.drop_column('leads', 'mailchimp_synced')
    op.drop_column('leads', 'marketing_consent_at')
    op.drop_column('leads', 'marketing_consent')
    op.drop_column('leads', 'source')
    op.drop_column('leads', 'interest')
    op.drop_column('leads', 'industry')
    op.drop_column('leads', 'company')
    op.drop_column('leads', 'last_name')
    op.drop_column('leads', 'first_name')
