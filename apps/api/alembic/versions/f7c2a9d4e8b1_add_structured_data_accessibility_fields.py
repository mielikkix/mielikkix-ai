"""add structured data and accessibility fields to seo_crawled_pages

Revision ID: f7c2a9d4e8b1
Revises: a4f7c9e2b5d8
Create Date: 2026-09-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f7c2a9d4e8b1'
down_revision = 'a4f7c9e2b5d8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('seo_crawled_pages', sa.Column('structured_data_types', sa.JSON(), nullable=True))
    op.add_column('seo_crawled_pages', sa.Column('structured_data_invalid_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('seo_crawled_pages', sa.Column('html_lang_present', sa.Boolean(), nullable=True))
    op.add_column('seo_crawled_pages', sa.Column('heading_outline', sa.JSON(), nullable=True))
    op.add_column('seo_crawled_pages', sa.Column('form_inputs_missing_label', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('seo_crawled_pages', sa.Column('links_missing_accessible_name', sa.Integer(), nullable=False, server_default='0'))


def downgrade():
    op.drop_column('seo_crawled_pages', 'links_missing_accessible_name')
    op.drop_column('seo_crawled_pages', 'form_inputs_missing_label')
    op.drop_column('seo_crawled_pages', 'heading_outline')
    op.drop_column('seo_crawled_pages', 'html_lang_present')
    op.drop_column('seo_crawled_pages', 'structured_data_invalid_count')
    op.drop_column('seo_crawled_pages', 'structured_data_types')
