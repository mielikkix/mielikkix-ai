"""add content_hash to seo_crawled_pages

Revision ID: b3e7d1f9a2c6
Revises: a7d3f9c1e6b8
Create Date: 2026-09-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b3e7d1f9a2c6'
down_revision = 'a7d3f9c1e6b8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('seo_crawled_pages', sa.Column('content_hash', sa.Text(), nullable=True))
    op.create_index('ix_seo_crawled_pages_content_hash', 'seo_crawled_pages', ['content_hash'])


def downgrade():
    op.drop_index('ix_seo_crawled_pages_content_hash', table_name='seo_crawled_pages')
    op.drop_column('seo_crawled_pages', 'content_hash')
