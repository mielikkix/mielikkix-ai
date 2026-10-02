"""seo_audits.pages_in_sitemap

Revision ID: f2c8a4d6b1e3
Revises: e5b2d8f1a3c6
Create Date: 2026-10-02 00:00:00.000000

How many page URLs the audited site's sitemap lists, shown next to pages
crawled (QA 2026-10-02, E7).
"""
from alembic import op
import sqlalchemy as sa


revision = 'f2c8a4d6b1e3'
down_revision = 'e5b2d8f1a3c6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('seo_audits', sa.Column('pages_in_sitemap', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('seo_audits', 'pages_in_sitemap')
