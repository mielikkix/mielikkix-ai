"""add articles

Revision ID: a4f7c9e2b5d8
Revises: e6b9d3f8a1c7
Create Date: 2026-09-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'a4f7c9e2b5d8'
down_revision = 'e6b9d3f8a1c7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'articles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('slug', sa.Text(), nullable=False),
        sa.Column('excerpt', sa.Text(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default='draft'),
        sa.Column('deployment_status', sa.Text(), nullable=False, server_default='not_deployed'),
        sa.Column('last_deployment_error', sa.Text(), nullable=True),
        sa.Column('last_deployed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('author_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('featured_image_url', sa.Text(), nullable=True),
        sa.Column('meta_title', sa.Text(), nullable=True),
        sa.Column('meta_description', sa.Text(), nullable=True),
        sa.Column('canonical_url', sa.Text(), nullable=True),
        sa.Column('keywords', sa.JSON(), nullable=True),
        sa.Column('category', sa.Text(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint('uq_articles_slug', 'articles', ['slug'])
    op.create_index('ix_articles_slug', 'articles', ['slug'])
    op.create_index('ix_articles_status', 'articles', ['status'])


def downgrade():
    op.drop_index('ix_articles_status', table_name='articles')
    op.drop_index('ix_articles_slug', table_name='articles')
    op.drop_constraint('uq_articles_slug', 'articles', type_='unique')
    op.drop_table('articles')
