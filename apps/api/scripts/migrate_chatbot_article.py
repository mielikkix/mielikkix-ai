"""One-off migration: moves the existing hand-written "Chatbot for Small
Businesses" article (website/src/pages/blog/chatbot-for-small-businesses.astro)
into the Article database table, so it becomes a normal database-backed
article manageable through Mielikkix Admin -> Articles, per this feature's
"single source of truth" architecture requirement.

Content is extracted PROGRAMMATICALLY from the actual .astro file (the
<article>...</article> inner HTML, minus the <h1> -- title is a separate
DB field) rather than retyped by hand, specifically to avoid any risk of a
transcription error changing so much as a word of the original article.
The old <CTASection ... /> component call is naturally excluded since it
lives outside the <article> tag in the source file; a generic, reusable
CTASection was added to website/src/pages/blog/[slug].astro's own template
instead, so every database-backed article (this one and all future ones)
gets a closing CTA without needing per-article CTA text as a DB field.

Idempotent: running this twice does nothing the second time (checks for an
existing article with this exact slug first) -- safe to re-run, including
against a database that already has this migration applied.

Usage:
    python scripts/migrate_chatbot_article.py [--website-root <path>]

The default --website-root assumes this repo's own layout (apps/api/../../website).
"""
import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal
from app.models.article import Article
from app.models.user import User
from app.services import article_service

SLUG = "chatbot-for-small-businesses"
TITLE = "Chatbot for Small Businesses: The Complete AI Guide for 2026"
META_DESCRIPTION = (
    "Learn how a chatbot for small businesses can answer questions, capture leads, "
    "support customers, automate bookings, and help your business operate 24/7."
)
# Same string reused as the on-page excerpt (shown under the H1 and on
# /blog's card) -- this is the one deliberate, disclosed presentational
# addition from this migration: the original static page never displayed
# a sub-heading sentence under its own H1, but every database-backed
# article does (see [slug].astro), and a blog index needs *some* preview
# text per card. No article prose is touched by this -- it's the same
# sentence already used as this page's own <meta description> today.
EXCERPT = META_DESCRIPTION
# The author byline the platform admin's own user account renders as (see
# app/models/user.py: User.full_name) -- reused deliberately rather than
# inventing a person, matching how this article's own existing JSON-LD
# already attributes authorship to the Organization, not a named person.
AUTHOR_EMAIL = "karam@panthermedia.no"


def _extract_content_html(astro_source: str) -> str:
    article_match = re.search(r'<article class="mx-auto max-w-3xl px-6 py-16">(.*)</article>', astro_source, re.DOTALL)
    if not article_match:
        raise RuntimeError("Could not find the <article>...</article> block in the source file.")
    inner = article_match.group(1)

    h1_match = re.search(r"<h1\b.*?</h1>", inner, re.DOTALL)
    if not h1_match:
        raise RuntimeError("Could not find the <h1>...</h1> block to remove from the extracted content.")
    content = inner[: h1_match.start()] + inner[h1_match.end() :]
    return content.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--website-root",
        default=str(Path(__file__).resolve().parents[3] / "website"),
        help="Path to the website/ directory (default: this repo's own website/).",
    )
    args = parser.parse_args()

    old_file = Path(args.website_root) / "src" / "pages" / "blog" / "chatbot-for-small-businesses.astro"
    if not old_file.is_file():
        print(f"ERROR: source file not found at {old_file}")
        sys.exit(1)

    content_html = _extract_content_html(old_file.read_text(encoding="utf-8"))
    print(f"Extracted {len(content_html)} characters of article content from {old_file}")

    db = SessionLocal()
    try:
        existing = db.query(Article).filter(Article.slug == SLUG).first()
        if existing is not None:
            print(f"An article with slug '{SLUG}' already exists (id={existing.id}) -- nothing to do.")
            return

        author = db.query(User).filter(User.email == AUTHOR_EMAIL).first()
        if author is None:
            print(f"ERROR: no existing user found with email {AUTHOR_EMAIL!r} -- refusing to invent one.")
            sys.exit(1)

        sanitized_content = article_service.sanitize_content(content_html)

        # Real fact, not invented: this repo's own git history shows this
        # file was first committed 2026-09-20 09:34:00 +07:00 -- used as
        # published_at rather than "now", since the article has genuinely
        # existed (and been live) since that point, not from the moment
        # this migration script happens to run.
        published_at = datetime(2026, 9, 20, 2, 34, 0, tzinfo=timezone.utc)

        article = Article(
            title=TITLE,
            slug=SLUG,
            excerpt=EXCERPT,
            content=sanitized_content,
            status="published",
            author_id=author.id,
            featured_image_url=None,
            meta_title=None,  # falls back to `title`, which is this exact string anyway
            meta_description=META_DESCRIPTION,
            canonical_url=None,  # derived as https://mielikkix.ai/blog/<slug>/ -- same as before
            keywords=[],  # the original page never declared explicit SEO keywords -- not invented here
            category=None,
            tags=[],
            published_at=published_at,
            # "pending", not "not_deployed" -- this article's OLD static
            # HTML has genuinely been live on Hostinger for a while, but
            # that predates this database record entirely. The current
            # database-backed rendering (with its real byline/excerpt/CTA
            # -- see this migration's own disclosed differences) has never
            # gone through a deploy this system knows about, so it
            # honestly needs the next manual website deployment to
            # reconcile -- exactly what "pending" means (2026-09-20).
            deployment_status="pending",
        )
        db.add(article)
        db.commit()
        db.refresh(article)

        print(f"Created Article id={article.id} slug={article.slug!r} status={article.status}")
        print(f"Author: {author.full_name} <{author.email}>")
        print(f"published_at: {article.published_at.isoformat()}")
        print()
        print("Next steps (manual, deliberately not automated by this script):")
        print("  1. Verify the article in Mielikkix Admin -> Articles.")
        print("  2. Rebuild the website (npm run build in website/) and confirm")
        print("     /blog/chatbot-for-small-businesses/ renders correctly.")
        print("  3. Only once verified, delete the old .astro file:")
        print(f"     {old_file}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
