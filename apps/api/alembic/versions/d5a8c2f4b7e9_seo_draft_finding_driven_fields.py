"""seo_drafts: nullable product_id, add url/draft_type for finding-driven drafts

Revision ID: d5a8c2f4b7e9
Revises: c4f8a2b6e1d3
Create Date: 2026-09-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd5a8c2f4b7e9'
down_revision = 'c4f8a2b6e1d3'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('seo_drafts', 'product_id', nullable=True)
    op.alter_column('seo_drafts', 'draft_description', nullable=True)
    op.alter_column('seo_drafts', 'draft_seo_title', nullable=True)
    op.alter_column('seo_drafts', 'draft_meta_description', nullable=True)
    op.add_column('seo_drafts', sa.Column('url', sa.Text(), nullable=True))
    op.add_column('seo_drafts', sa.Column('draft_type', sa.Text(), nullable=False, server_default='full_copy'))


def downgrade():
    op.drop_column('seo_drafts', 'draft_type')
    op.drop_column('seo_drafts', 'url')
    op.alter_column('seo_drafts', 'draft_meta_description', nullable=False)
    op.alter_column('seo_drafts', 'draft_seo_title', nullable=False)
    op.alter_column('seo_drafts', 'draft_description', nullable=False)
    op.alter_column('seo_drafts', 'product_id', nullable=False)
