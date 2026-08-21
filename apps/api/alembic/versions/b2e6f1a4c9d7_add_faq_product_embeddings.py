"""add faq/product embeddings

Revision ID: b2e6f1a4c9d7
Revises: 7d4b9e2f813a
Create Date: 2026-08-07 10:20:00.000000

FAQ/product retrieval was pure English keyword substring matching, so it
silently never matched anything for a non-English visitor message -- unlike
document chunks, which already moved to embedding-based (multilingual)
search. This brings FAQs and products onto the same embedding-based search,
so a business's actual FAQ answers are found regardless of the language the
question was asked in.
"""
from alembic import op
import sqlalchemy as sa


revision = 'b2e6f1a4c9d7'
down_revision = '7d4b9e2f813a'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('faqs', sa.Column('embedding_json', sa.Text(), nullable=True))
    op.add_column('products', sa.Column('embedding_json', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('products', 'embedding_json')
    op.drop_column('faqs', 'embedding_json')
