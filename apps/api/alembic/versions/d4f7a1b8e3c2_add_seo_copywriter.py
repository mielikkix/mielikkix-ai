"""add seo drafts and product seo columns

Revision ID: d4f7a1b8e3c2
Revises: ca2e62133dc7
Create Date: 2026-08-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'd4f7a1b8e3c2'
down_revision = 'ca2e62133dc7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('products', sa.Column('seo_title', sa.Text(), nullable=True))
    op.add_column('products', sa.Column('meta_description', sa.Text(), nullable=True))

    op.create_table(
        'seo_drafts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id'), nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('draft_description', sa.Text(), nullable=False),
        sa.Column('draft_seo_title', sa.Text(), nullable=False),
        sa.Column('draft_meta_description', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default='draft'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_seo_drafts_business_id', 'seo_drafts', ['business_id'])
    op.create_index('ix_seo_drafts_product_id', 'seo_drafts', ['product_id'])


def downgrade():
    op.drop_index('ix_seo_drafts_product_id', table_name='seo_drafts')
    op.drop_index('ix_seo_drafts_business_id', table_name='seo_drafts')
    op.drop_table('seo_drafts')
    op.drop_column('products', 'meta_description')
    op.drop_column('products', 'seo_title')
