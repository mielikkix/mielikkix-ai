"""Mielikkix Admin -> Articles: the platform's blog/SEO content system.

The `articles` table (app/models/article.py) is the single source of truth
for content -- there is no Markdown-file or second-CMS system anywhere.
This module never talks to the filesystem or SSH/SFTP itself.

Deployment model (2026-09-20 decision -- Hostinger deployment stays MANUAL
for now, no automatic build/upload): publishing/unpublishing here only
ever changes the database (status + deployment_status="pending" -- a true
statement that the live site hasn't caught up yet, never a claim that it
has). `record_deployment_result()` is the one function that ever sets
deployment_status to "live" or "failed", and it's called from two places
on purpose: `app/api/admin_articles.py`'s POST .../deployment-result route
(an admin manually reporting what a real deploy did) and
`deploy_service.py`'s dormant automated build+SFTP path (unused while
deployment is manual, kept for whenever real Hostinger credentials exist
and auto-deploy is wanted again). Either way, an article only becomes
"live" because someone or something that actually attempted a deploy said
so -- never merely because Publish was clicked.

Slug handling mirrors auth_service.py's existing business-slug pattern
exactly (lowercase, non [a-z0-9-] -> "-", reject outright on collision --
no silent auto-suffixing), rather than inventing a new convention.
"""
import re
from datetime import datetime, timezone
from typing import Optional

import bleach
from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from ..models.article import Article
from ..models.user import User

_SLUG_INVALID_CHARS = re.compile(r"[^a-z0-9-]")

# bleach's strip=True removes a disallowed TAG but leaves its inner text
# behind (documented bleach behavior) -- fine for most tags, but leaving
# a <script>/<style> block's own text sitting in the article as visible
# plain text is never useful and .clean() alone won't remove it. Strip
# these two specifically, tag AND content, before the general allowlist
# pass below.
_DANGEROUS_BLOCK_TAGS = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)

# Deliberately conservative -- this is public-website HTML rendered via
# Astro's set:html, so anything not needed for a blog article's own body
# copy is left out rather than allowed "just in case". Only a platform
# admin can ever write this field (require_platform_admin gates every
# mutating route in app/api/admin_articles.py), but sanitizing at the
# trust boundary is still the right call rather than trusting a textarea
# outright -- see this feature's own security requirements.
#
# div/section/span/details/summary added 2026-09-20 when migrating the
# existing hand-written "Chatbot for Small Businesses" article into this
# table -- its FAQ section uses <details>/<summary> accordions and every
# block is wrapped in a styled <div>/<section>, and stripping those tags
# (bleach's default for anything off the allowlist) would have silently
# collapsed the FAQ accordions to flat paragraphs and destroyed the
# article's visual structure. Still no <script>/<style>/<iframe>/on*
# handlers -- those are exactly what this allowlist exists to keep out.
_ALLOWED_TAGS = [
    "p", "br", "strong", "em", "b", "i", "u",
    "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li",
    "a", "blockquote", "code", "pre",
    "img", "figure", "figcaption",
    "table", "thead", "tbody", "tr", "th", "td",
    "div", "section", "span", "details", "summary",
]
_ALLOWED_ATTRS = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "width", "height"],
    # "class" allowed on every tag (not just a fixed list) -- this site's
    # entire visual language is Tailwind utility classes, and a sanitized
    # article that lost every class would render as unstyled text. Never a
    # security concern on its own (a class name can't execute anything);
    # the actual XSS boundary is script/style tags, event-handler
    # attributes (onerror etc., not in this attrs allowlist at all), and
    # javascript: URLs (blocked via _ALLOWED_PROTOCOLS below) -- all still
    # enforced exactly as before.
    "*": ["class"],
}
_ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


def sanitize_content(raw_html: str) -> str:
    without_script_style = _DANGEROUS_BLOCK_TAGS.sub("", raw_html)
    return bleach.clean(
        without_script_style,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        protocols=_ALLOWED_PROTOCOLS,
        strip=True,
    )


def slugify(value: str) -> str:
    return _SLUG_INVALID_CHARS.sub("-", value.lower().strip().replace(" ", "-"))


def _assert_slug_available(db: Session, slug: str, exclude_id=None) -> None:
    query = db.query(Article).filter(Article.slug == slug)
    if exclude_id is not None:
        query = query.filter(Article.id != exclude_id)
    if query.first() is not None:
        raise HTTPException(status_code=409, detail=f"An article with slug '{slug}' already exists.")


def _article_query(db: Session):
    return db.query(Article).options(joinedload(Article.author))


def create_article(db: Session, author: User, data) -> Article:
    slug = slugify(data.slug) if data.slug else slugify(data.title)
    if not slug:
        raise HTTPException(status_code=400, detail="Could not derive a valid slug from the title.")
    _assert_slug_available(db, slug)

    article = Article(
        title=data.title,
        slug=slug,
        excerpt=data.excerpt,
        content=sanitize_content(data.content),
        status="draft",
        author_id=author.id,
        featured_image_url=data.featured_image_url,
        meta_title=data.meta_title,
        meta_description=data.meta_description,
        canonical_url=data.canonical_url,
        keywords=data.keywords or [],
        category=data.category,
        tags=data.tags or [],
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return article


def update_article(db: Session, article_id, data) -> Optional[Article]:
    article = _article_query(db).filter(Article.id == article_id).first()
    if article is None:
        return None

    update_fields = data.model_dump(exclude_unset=True)

    if "slug" in update_fields and update_fields["slug"]:
        new_slug = slugify(update_fields["slug"])
        if new_slug != article.slug:
            _assert_slug_available(db, new_slug, exclude_id=article.id)
        article.slug = new_slug
        update_fields.pop("slug")
    elif "slug" in update_fields:
        update_fields.pop("slug")

    if "content" in update_fields and update_fields["content"] is not None:
        update_fields["content"] = sanitize_content(update_fields["content"])

    for field, value in update_fields.items():
        setattr(article, field, value)

    db.commit()
    db.refresh(article)
    return article


def list_articles(db: Session, status: Optional[str] = None, page: int = 1, page_size: int = 20) -> dict:
    query = _article_query(db)
    if status:
        query = query.filter(Article.status == status)

    total = query.count()
    articles = (
        query.order_by(Article.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"items": articles, "total": total, "page": page, "page_size": page_size}


def get_article(db: Session, article_id) -> Optional[Article]:
    return _article_query(db).filter(Article.id == article_id).first()


def delete_article(db: Session, article_id) -> bool:
    """Permanent deletion -- same shape as seo_website_service.delete_website
    (look up, return False if missing, db.delete + commit, return True).
    Article has exactly one foreign key (author_id -> users.id, Article is
    the "many" side referencing User) and nothing else references an
    Article's id, so this needs no cascade handling and can never delete or
    modify the author's own User row -- deleting the "many" side of a
    relationship never touches the "one" side it points at. All of the
    deployment-tracking fields (deployment_status, last_deployment_error,
    last_deployed_at) live as plain columns on this same row, not a
    separate table, so they're removed along with it automatically; there
    is no separate deployment record left behind."""
    article = get_article(db, article_id)
    if article is None:
        return False
    db.delete(article)
    db.commit()
    return True


def mark_publish_intent(db: Session, article_id) -> Optional[Article]:
    """Sets status="published" + published_at (only the first time -- a
    republish after an edit keeps the original publish date, same
    convention as datePublished/dateModified in the JSON-LD this feature
    generates) and deployment_status="pending". The actual build/deploy
    happens in deploy_service.py, called separately by the route so this
    function stays a plain, fast, transactional DB write -- publishing
    the *intent* must succeed even if the deploy step that follows is
    slow or fails."""
    article = _article_query(db).filter(Article.id == article_id).first()
    if article is None:
        return None

    if article.published_at is None:
        article.published_at = datetime.now(timezone.utc)
    article.status = "published"
    article.deployment_status = "pending"
    article.last_deployment_error = None
    db.commit()
    db.refresh(article)
    return article


def mark_unpublish_intent(db: Session, article_id) -> Optional[Article]:
    """Reverts to draft -- the article stops being served by the public
    API immediately (the next request to /api/public/articles/{slug}
    404s), but the already-built static page on Hostinger only disappears
    once the triggered redeploy finishes, same as the publish direction."""
    article = _article_query(db).filter(Article.id == article_id).first()
    if article is None:
        return None

    article.status = "draft"
    article.deployment_status = "pending"
    article.last_deployment_error = None
    db.commit()
    db.refresh(article)
    return article


def record_deployment_result(db: Session, article_id, *, success: bool, message: str) -> None:
    article = db.query(Article).filter(Article.id == article_id).first()
    if article is None:
        return
    if success:
        article.deployment_status = "live" if article.status == "published" else "not_deployed"
        article.last_deployment_error = None
        article.last_deployed_at = datetime.now(timezone.utc)
    else:
        article.deployment_status = "failed"
        article.last_deployment_error = message
    db.commit()


def list_public_articles(db: Session, page: int = 1, page_size: int = 20) -> dict:
    query = (
        _article_query(db)
        .filter(Article.status == "published")
        .order_by(Article.published_at.desc())
    )
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": items, "total": total}


def get_public_article_by_slug(db: Session, slug: str) -> Optional[Article]:
    return (
        _article_query(db)
        .filter(Article.slug == slug, Article.status == "published")
        .first()
    )
