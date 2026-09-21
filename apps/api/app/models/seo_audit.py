import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, DateTime, Integer, Float, Boolean, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from ..core.database import Base


class SeoAudit(Base):
    """One run of the SEO Audit & Optimization agent against a SeoWebsite.
    Deterministic crawl/analysis results attach to this row (SeoCrawledPage,
    SeoFinding, SeoKeywordOpportunity) so re-running an audit later doesn't
    overwrite history -- see this agent's CLAUDE.md, Phase 16 (audit
    history/comparison).

    No job queue exists in this codebase (see this agent's CLAUDE.md) --
    status moves pending -> running -> completed|failed via a FastAPI
    BackgroundTasks call, the same shape document_service.py's
    crawl_and_ingest_website already uses, polled by the frontend.
    """

    __tablename__ = "seo_audits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    website_id = Column(UUID(as_uuid=True), ForeignKey("seo_websites.id", ondelete="CASCADE"), nullable=False, index=True)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False, index=True)
    status = Column(Text, nullable=False, default="pending")  # "pending" | "running" | "completed" | "failed"
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    pages_discovered = Column(Integer, nullable=False, default=0)
    pages_crawled = Column(Integer, nullable=False, default=0)
    pages_blocked = Column(Integer, nullable=False, default=0)
    # Each 0-100, null until the analyzer that produces it has run -- an
    # internal diagnostic score based on this agent's own checks, NEVER
    # presented as an actual Google ranking signal (see this agent's
    # CLAUDE.md, Phase 10).
    health_technical = Column(Integer, nullable=True)
    health_on_page = Column(Integer, nullable=True)
    health_performance = Column(Integer, nullable=True)
    health_content = Column(Integer, nullable=True)
    health_internal_linking = Column(Integer, nullable=True)
    # LLM-written narrative over this audit's own already-computed findings
    # (Stage 6, seo_recommendation_service.generate_executive_summary) --
    # null if the audit found nothing to summarize or the LLM call failed;
    # never a fabricated placeholder (see that service's own docstring).
    executive_summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    website = relationship("SeoWebsite")


class SeoCrawledPage(Base):
    """One page fetched during a SeoAudit -- deterministic facts only, no
    LLM involvement (see this agent's CLAUDE.md, Phase 18's hard boundary
    between deterministic checks and LLM reasoning)."""

    __tablename__ = "seo_crawled_pages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audit_id = Column(UUID(as_uuid=True), ForeignKey("seo_audits.id", ondelete="CASCADE"), nullable=False, index=True)
    url = Column(Text, nullable=False)
    http_status = Column(Integer, nullable=True)
    title = Column(Text, nullable=True)
    meta_description = Column(Text, nullable=True)
    h1_count = Column(Integer, nullable=False, default=0)
    word_count = Column(Integer, nullable=False, default=0)
    canonical_url = Column(Text, nullable=True)
    meta_robots = Column(Text, nullable=True)
    x_robots_tag = Column(Text, nullable=True)
    is_indexable = Column(Boolean, nullable=True)
    redirect_chain = Column(JSON, nullable=True, default=list)
    internal_link_count = Column(Integer, nullable=False, default=0)
    image_count = Column(Integer, nullable=False, default=0)
    images_missing_alt = Column(Integer, nullable=False, default=0)
    # SHA-256 of the page's normalized visible text (see seo_page_analyzer.py)
    # -- null for non-HTML/broken pages, where there's no content to hash.
    # Two pages sharing a hash have byte-for-byte identical extracted text,
    # letting the Stage 4 on-page analyzer flag real duplicate content
    # instead of guessing from title/word-count alone (this agent's
    # CLAUDE.md: no fabricated findings).
    content_hash = Column(Text, nullable=True, index=True)
    # Stage 13/14 (structured data + accessibility, see this agent's
    # CLAUDE.md "Professional tier roadmap") -- all extracted the same way
    # as everything else above, at crawl time in seo_page_analyzer.py, from
    # the page's raw HTML (never re-derived later, since raw HTML itself
    # isn't persisted). structured_data_types is the list of schema.org
    # @type values found in valid JSON-LD blocks (empty list, not null, if
    # the page has none). structured_data_invalid_count counts JSON-LD
    # <script> blocks that failed to parse as JSON -- a real problem,
    # unlike simply having none. html_lang_present is null only for
    # non-HTML/broken pages (no <html> element to check at all), matching
    # is_indexable's own null-for-non-HTML convention above. heading_outline
    # is the page's heading levels in document order (e.g. [1, 2, 2, 4] --
    # the 2->4 jump is a hierarchy skip), letting the accessibility analyzer
    # explain exactly where a skip happens instead of just counting them.
    structured_data_types = Column(JSON, nullable=True, default=list)
    structured_data_invalid_count = Column(Integer, nullable=False, default=0)
    html_lang_present = Column(Boolean, nullable=True)
    heading_outline = Column(JSON, nullable=True, default=list)
    form_inputs_missing_label = Column(Integer, nullable=False, default=0)
    links_missing_accessible_name = Column(Integer, nullable=False, default=0)
    # Stage 12 (Google Analytics + Search Console, see this agent's
    # CLAUDE.md "Professional tier roadmap") -- null for every business
    # until they've both connected Google (SeoGoogleConnection) AND
    # configured which property/site to read from; also null for a
    # business that has done both but this specific URL simply has no
    # data for the window queried (e.g. a brand-new page). Never
    # backfilled with 0 -- null always means "Not measured", the same
    # "absence isn't zero" rule Stage 8's SeoPerformanceMeasurement already
    # follows for Core Web Vitals. avg_position is a float (e.g. 14.2);
    # everything else is a whole count over a trailing 28-day window.
    ga_sessions_28d = Column(Integer, nullable=True)
    gsc_impressions_28d = Column(Integer, nullable=True)
    gsc_clicks_28d = Column(Integer, nullable=True)
    gsc_avg_position_28d = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SeoFinding(Base):
    """One deterministic (or LLM-explained-but-deterministically-detected)
    issue found during a SeoAudit. `status` is the human review/action
    state -- separate from the audit's own status -- so a finding can be
    tracked through a fix independent of the audit run that discovered it."""

    __tablename__ = "seo_findings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audit_id = Column(UUID(as_uuid=True), ForeignKey("seo_audits.id", ondelete="CASCADE"), nullable=False, index=True)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False, index=True)
    # "technical" | "on_page" | "performance" | "content" | "internal_linking" | "images" | "keywords"
    category = Column(Text, nullable=False)
    rule_code = Column(Text, nullable=False)
    # "critical" | "high" | "medium" | "low" | "informational" -- always
    # from a fixed rule, never LLM opinion (this agent's CLAUDE.md, Phase 3).
    severity = Column(Text, nullable=False)
    affected_url = Column(Text, nullable=True)
    issue = Column(Text, nullable=False)
    explanation = Column(Text, nullable=True)
    recommended_fix = Column(Text, nullable=True)
    evidence = Column(JSON, nullable=True, default=dict)
    status = Column(Text, nullable=False, default="open")  # open | in_progress | approved | completed | ignored
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    audit = relationship("SeoAudit")


class SeoKeywordOpportunity(Base):
    """LLM-suggested keyword ideas for a SeoAudit -- volume/CPC/competition
    are always "Not available" unless a real keyword-data API is ever
    connected (this agent's CLAUDE.md, Phase 14 decision: no fabricated
    numbers)."""

    __tablename__ = "seo_keyword_opportunities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audit_id = Column(UUID(as_uuid=True), ForeignKey("seo_audits.id", ondelete="CASCADE"), nullable=False, index=True)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False, index=True)
    keyword = Column(Text, nullable=False)
    intent = Column(Text, nullable=True)  # "commercial" | "informational" | "local" | ...
    suggested_page = Column(Text, nullable=True)
    current_page = Column(Text, nullable=True)
    content_gap = Column(Text, nullable=True)
    recommendation = Column(Text, nullable=True)
    volume = Column(Text, nullable=False, default="Not available")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SeoPerformanceMeasurement(Base):
    """One Core Web Vitals measurement for one SeoAudit (Stage 8, see
    apps/agents/seo-audit/CLAUDE.md) -- via app/integrations/
    performance_provider.py. A row only ever exists here when a real
    measurement actually succeeded; when no provider is configured (no
    API key) or the call failed, no row is created at all, and callers
    render that absence as "Not measured" -- never a fabricated number.

    inp_ms is real-user Chrome UX Report field data ONLY, often null even
    when the rest of the row is populated (most lower-traffic sites don't
    have enough field data yet) -- tbt_ms is the always-available lab
    proxy, kept as its own separate field rather than relabeled as INP.
    """

    __tablename__ = "seo_performance_measurements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audit_id = Column(UUID(as_uuid=True), ForeignKey("seo_audits.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy = Column(Text, nullable=False)  # "mobile" | "desktop"
    performance_score = Column(Integer, nullable=True)  # Lighthouse's own 0-100 lab score
    lcp_ms = Column(Integer, nullable=True)
    cls = Column(Float, nullable=True)
    inp_ms = Column(Integer, nullable=True)
    tbt_ms = Column(Integer, nullable=True)
    measured_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
