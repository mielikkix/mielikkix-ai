"""add review publish tracking, risk_reasons, and review_connections

Revision ID: f8a1c3e9d2b7
Revises: e7c4a2f6b813
Create Date: 2026-09-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'f8a1c3e9d2b7'
down_revision = 'e7c4a2f6b813'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('reviews', sa.Column('risk_reasons', postgresql.JSON(), nullable=True))
    op.add_column('reviews', sa.Column('published_response', sa.Text(), nullable=True))
    op.add_column('reviews', sa.Column('published_at', sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        'review_connections',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id'), nullable=False, unique=True),
        sa.Column('refresh_token_encrypted', sa.Text(), nullable=False),
        sa.Column('account_id', sa.Text(), nullable=False),
        sa.Column('location_id', sa.Text(), nullable=True),
        sa.Column('google_account_email', sa.Text(), nullable=True),
        sa.Column('location_title', sa.Text(), nullable=True),
        sa.Column('connected_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f('ix_review_connections_business_id'), 'review_connections', ['business_id'], unique=True)


def downgrade():
    op.drop_index(op.f('ix_review_connections_business_id'), table_name='review_connections')
    op.drop_table('review_connections')
    op.drop_column('reviews', 'published_at')
    op.drop_column('reviews', 'published_response')
    op.drop_column('reviews', 'risk_reasons')
