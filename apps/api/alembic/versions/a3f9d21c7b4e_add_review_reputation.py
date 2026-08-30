"""add reviews table for Review & Reputation agent

Revision ID: a3f9d21c7b4e
Revises: d4f7a1b8e3c2
Create Date: 2026-08-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'a3f9d21c7b4e'
down_revision = 'd4f7a1b8e3c2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'reviews',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id'), nullable=False),
        sa.Column('platform', sa.Text(), nullable=False, server_default='manual'),
        sa.Column('external_review_id', sa.Text(), nullable=True),
        sa.Column('customer_name', sa.Text(), nullable=True),
        sa.Column('rating', sa.Integer(), nullable=True),
        sa.Column('review_text', sa.Text(), nullable=False),
        sa.Column('review_language', sa.Text(), nullable=True),
        sa.Column('review_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sentiment', sa.Text(), nullable=True),
        sa.Column('sentiment_score', sa.Float(), nullable=True),
        sa.Column('topics', postgresql.JSON(), nullable=True),
        sa.Column('positive_points', postgresql.JSON(), nullable=True),
        sa.Column('negative_points', postgresql.JSON(), nullable=True),
        sa.Column('primary_issue', sa.Text(), nullable=True),
        sa.Column('priority', sa.Text(), nullable=False, server_default='low'),
        sa.Column('requires_response', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('requires_human_review', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('escalation_reason', sa.Text(), nullable=True),
        sa.Column('analyzed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ai_response', sa.Text(), nullable=True),
        sa.Column('response_tone', sa.Text(), nullable=True),
        sa.Column('response_status', sa.Text(), nullable=False, server_default='none'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_reviews_business_id', 'reviews', ['business_id'])
    op.create_index('ix_reviews_external_review_id', 'reviews', ['external_review_id'])
    op.create_index(
        'ix_reviews_business_platform_external_id', 'reviews', ['business_id', 'platform', 'external_review_id']
    )


def downgrade():
    op.drop_index('ix_reviews_business_platform_external_id', table_name='reviews')
    op.drop_index('ix_reviews_external_review_id', table_name='reviews')
    op.drop_index('ix_reviews_business_id', table_name='reviews')
    op.drop_table('reviews')
