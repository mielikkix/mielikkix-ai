"""add seo audit tables

Revision ID: a7d3f9c1e6b8
Revises: f1a9c3e7b2d4
Create Date: 2026-09-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'a7d3f9c1e6b8'
down_revision = 'f1a9c3e7b2d4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'seo_websites',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id'), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('target_country', sa.Text(), nullable=True),
        sa.Column('target_language', sa.Text(), nullable=True),
        sa.Column('primary_category', sa.Text(), nullable=True),
        sa.Column('target_keywords', postgresql.JSON(), nullable=True),
        sa.Column('crawl_tier', sa.Text(), nullable=False, server_default='starter'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_seo_websites_business_id', 'seo_websites', ['business_id'])

    op.create_table(
        'seo_audits',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('website_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('seo_websites.id', ondelete='CASCADE'), nullable=False),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id'), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default='pending'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pages_discovered', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('pages_crawled', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('pages_blocked', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('health_technical', sa.Integer(), nullable=True),
        sa.Column('health_on_page', sa.Integer(), nullable=True),
        sa.Column('health_performance', sa.Integer(), nullable=True),
        sa.Column('health_content', sa.Integer(), nullable=True),
        sa.Column('health_internal_linking', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_seo_audits_website_id', 'seo_audits', ['website_id'])
    op.create_index('ix_seo_audits_business_id', 'seo_audits', ['business_id'])

    op.create_table(
        'seo_crawled_pages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('audit_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('seo_audits.id', ondelete='CASCADE'), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('http_status', sa.Integer(), nullable=True),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('meta_description', sa.Text(), nullable=True),
        sa.Column('h1_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('word_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('canonical_url', sa.Text(), nullable=True),
        sa.Column('meta_robots', sa.Text(), nullable=True),
        sa.Column('x_robots_tag', sa.Text(), nullable=True),
        sa.Column('is_indexable', sa.Boolean(), nullable=True),
        sa.Column('redirect_chain', postgresql.JSON(), nullable=True),
        sa.Column('internal_link_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('image_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('images_missing_alt', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_seo_crawled_pages_audit_id', 'seo_crawled_pages', ['audit_id'])

    op.create_table(
        'seo_findings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('audit_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('seo_audits.id', ondelete='CASCADE'), nullable=False),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id'), nullable=False),
        sa.Column('category', sa.Text(), nullable=False),
        sa.Column('rule_code', sa.Text(), nullable=False),
        sa.Column('severity', sa.Text(), nullable=False),
        sa.Column('affected_url', sa.Text(), nullable=True),
        sa.Column('issue', sa.Text(), nullable=False),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('recommended_fix', sa.Text(), nullable=True),
        sa.Column('evidence', postgresql.JSON(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False, server_default='open'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_seo_findings_audit_id', 'seo_findings', ['audit_id'])
    op.create_index('ix_seo_findings_business_id', 'seo_findings', ['business_id'])

    op.create_table(
        'seo_keyword_opportunities',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('audit_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('seo_audits.id', ondelete='CASCADE'), nullable=False),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id'), nullable=False),
        sa.Column('keyword', sa.Text(), nullable=False),
        sa.Column('intent', sa.Text(), nullable=True),
        sa.Column('suggested_page', sa.Text(), nullable=True),
        sa.Column('current_page', sa.Text(), nullable=True),
        sa.Column('content_gap', sa.Text(), nullable=True),
        sa.Column('recommendation', sa.Text(), nullable=True),
        sa.Column('volume', sa.Text(), nullable=False, server_default='Not available'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_seo_keyword_opportunities_audit_id', 'seo_keyword_opportunities', ['audit_id'])
    op.create_index('ix_seo_keyword_opportunities_business_id', 'seo_keyword_opportunities', ['business_id'])

    op.add_column('seo_drafts', sa.Column('finding_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('seo_findings.id', ondelete='SET NULL'), nullable=True))
    op.create_index('ix_seo_drafts_finding_id', 'seo_drafts', ['finding_id'])

    # Per-business override for how many SeoWebsite rows a business may
    # register -- default cap lives in code (app/core/agent_catalog.py's
    # DEFAULT_SEO_WEBSITE_LIMIT), not the database; this column exists only
    # for the agency-style account that legitimately needs more (e.g. the
    # original 13-website client) without raising the default for everyone
    # else. Same "admin sets it directly, no payment processor" shape as
    # Business.api_access_addon.
    op.add_column('businesses', sa.Column('seo_website_limit_override', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('businesses', 'seo_website_limit_override')
    op.drop_index('ix_seo_drafts_finding_id', table_name='seo_drafts')
    op.drop_column('seo_drafts', 'finding_id')
    op.drop_index('ix_seo_keyword_opportunities_business_id', table_name='seo_keyword_opportunities')
    op.drop_index('ix_seo_keyword_opportunities_audit_id', table_name='seo_keyword_opportunities')
    op.drop_table('seo_keyword_opportunities')
    op.drop_index('ix_seo_findings_business_id', table_name='seo_findings')
    op.drop_index('ix_seo_findings_audit_id', table_name='seo_findings')
    op.drop_table('seo_findings')
    op.drop_index('ix_seo_crawled_pages_audit_id', table_name='seo_crawled_pages')
    op.drop_table('seo_crawled_pages')
    op.drop_index('ix_seo_audits_business_id', table_name='seo_audits')
    op.drop_index('ix_seo_audits_website_id', table_name='seo_audits')
    op.drop_table('seo_audits')
    op.drop_index('ix_seo_websites_business_id', table_name='seo_websites')
    op.drop_table('seo_websites')
