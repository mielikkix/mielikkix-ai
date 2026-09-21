import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from ..core.database import Base


class Article(Base):
    """MielikkiX Admin -> Articles (the website's blog/SEO content system).

    No business_id -- same reasoning as Ticket/Booking: articles belong to
    the platform (Mielikkix's own marketing site), not a tenant, so this is
    platform-admin-only data (see app/core/dependencies.py:
    require_platform_admin), never tenant-scoped. This table IS the source
    of truth for published content -- the Astro site (website/) fetches
    published articles from the public read API
    (app/api/public_articles.py) at BUILD time and generates real static
    pages from it; nothing here is a second CMS or a Markdown-file system.

    Deliberately extensible for the future SEO Audit & Optimize integration
    (per this feature's own spec) without a schema change: `keywords`/`tags`
    are JSON lists an audit pass could read or append to, `category` groups
    articles into a topic cluster, and status/deployment_status separate
    "is this ready to be public" from "did the last deploy actually
    succeed" -- both real signals a future audit/recommendation feature
    would want to read.
    """

    __tablename__ = "articles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(Text, nullable=False)
    # Unique across ALL articles (not per-business -- there's no business
    # here) -- this is also the URL segment at /blog/<slug>, so uniqueness
    # is a hard requirement, enforced both at the DB level (unique index)
    # and in article_service.py before insert/update (a clean 409, not a
    # raw IntegrityError reaching the client).
    slug = Column(Text, nullable=False, unique=True, index=True)
    excerpt = Column(Text, nullable=True)
    # Sanitized HTML (see article_service.py's use of bleach on
    # create/update) -- authored as raw HTML in a textarea, not Markdown;
    # this repo has no Markdown-rendering pipeline for a stored string
    # anywhere, and adding a full rich-text editor would be overbuilding
    # this feature. Rendered on the public site via Astro's `set:html`,
    # the same directive already used for this site's JSON-LD.
    content = Column(Text, nullable=False)

    # "draft" | "published" -- see article_service.py for the exact state
    # machine. Deliberately just these two per this feature's own spec;
    # add "archived" etc. later without a migration (Text, not an enum).
    status = Column(Text, nullable=False, default="draft")

    # Tracks the LAST publish-triggered deploy attempt for this specific
    # article, separately from `status` -- an article can be
    # status="published" (the source-of-truth intent) while
    # deployment_status="failed" (the last automated build/upload attempt
    # didn't succeed), and the admin UI must show that honestly rather than
    # claiming the article is live. See app/services/deploy_service.py.
    # "not_deployed" | "pending" | "live" | "failed"
    deployment_status = Column(Text, nullable=False, default="not_deployed")
    last_deployment_error = Column(Text, nullable=True)
    last_deployed_at = Column(DateTime(timezone=True), nullable=True)

    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    featured_image_url = Column(Text, nullable=True)
    meta_title = Column(Text, nullable=True)
    meta_description = Column(Text, nullable=True)
    # Almost always left null (derived as https://mielikkix.ai/blog/<slug>/
    # by the public API/Astro) -- only set explicitly for the rare case of
    # deliberately canonicalizing to a different URL (e.g. a future
    # syndicated/duplicate piece).
    canonical_url = Column(Text, nullable=True)
    keywords = Column(JSON, nullable=True, default=list)
    category = Column(Text, nullable=True)
    tags = Column(JSON, nullable=True, default=list)

    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    author = relationship("User")
