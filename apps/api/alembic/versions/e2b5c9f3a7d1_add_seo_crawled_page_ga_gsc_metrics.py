"""add GA/Search Console metric fields to seo_crawled_pages

Revision ID: e2b5c9f3a7d1
Revises: d3f6b8a1c5e7
Create Date: 2026-09-20 00:00:03.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e2b5c9f3a7d1'
down_revision = 'd3f6b8a1c5e7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('seo_crawled_pages', sa.Column('ga_sessions_28d', sa.Integer(), nullable=True))
    op.add_column('seo_crawled_pages', sa.Column('gsc_impressions_28d', sa.Integer(), nullable=True))
    op.add_column('seo_crawled_pages', sa.Column('gsc_clicks_28d', sa.Integer(), nullable=True))
    op.add_column('seo_crawled_pages', sa.Column('gsc_avg_position_28d', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('seo_crawled_pages', 'gsc_avg_position_28d')
    op.drop_column('seo_crawled_pages', 'gsc_clicks_28d')
    op.drop_column('seo_crawled_pages', 'gsc_impressions_28d')
    op.drop_column('seo_crawled_pages', 'ga_sessions_28d')
