"""Unit tests for app/services/article_service.py -- slugging, HTML
sanitization, and the CRUD/publish state machine, independent of the HTTP
layer (see test_admin_articles_api.py for that).
"""
import pytest
from fastapi import HTTPException

from app.services import article_service as svc
from app.schemas.article import ArticleCreate, ArticleUpdate


def _author(db_session, business):
    from app.models.user import User

    return db_session.query(User).filter(User.email == business["email"]).first()


def test_slugify_lowercases_and_replaces_invalid_chars():
    assert svc.slugify("Chatbot for Small Business!") == "chatbot-for-small-business-"
    assert svc.slugify("  Spaced Out  ") == "spaced-out"


def test_sanitize_content_strips_script_tags():
    dirty = "<p>Hello</p><script>alert('xss')</script>"
    clean = svc.sanitize_content(dirty)
    assert "<script" not in clean
    assert "alert" not in clean
    assert "<p>Hello</p>" in clean


def test_sanitize_content_strips_event_handler_attributes():
    dirty = '<img src="x.png" onerror="alert(1)">'
    clean = svc.sanitize_content(dirty)
    assert "onerror" not in clean


def test_sanitize_content_preserves_div_section_and_class_attribute():
    """Added 2026-09-20 for the "Chatbot for Small Businesses" migration
    (see scripts/migrate_chatbot_article.py) -- that article's real HTML
    wraps every section in a styled <div>/<section>, which the sanitizer's
    original allowlist (before this migration) would have silently
    stripped, along with every Tailwind `class` attribute."""
    html = '<section class="mt-12"><div class="space-y-4"><p class="text-slate-700">Hello</p></div></section>'
    clean = svc.sanitize_content(html)
    assert "<section" in clean
    assert "<div" in clean
    assert 'class="mt-12"' in clean
    assert 'class="space-y-4"' in clean


def test_sanitize_content_preserves_details_summary_for_faq_accordions():
    html = '<details class="group"><summary>Question?</summary><p>Answer.</p></details>'
    clean = svc.sanitize_content(html)
    assert "<details" in clean
    assert "<summary>Question?</summary>" in clean
    assert "<p>Answer.</p>" in clean


def test_sanitize_content_still_strips_javascript_url_on_preserved_tags():
    """Extending the tag allowlist for div/section/etc. must not have
    loosened the actual security boundary -- still no javascript: URLs,
    still no event handlers, regardless of which tags are now allowed."""
    html = '<div class="x"><a href="javascript:alert(1)" onclick="steal()">click</a></div>'
    clean = svc.sanitize_content(html)
    assert "javascript:" not in clean
    assert "onclick" not in clean


def test_sanitize_content_strips_javascript_url():
    dirty = '<a href="javascript:alert(1)">click</a>'
    clean = svc.sanitize_content(dirty)
    assert "javascript:" not in clean


def test_create_article_derives_slug_from_title(db_session, business):
    author = _author(db_session, business)
    data = ArticleCreate(title="How To Add A Chatbot", content="<p>Body</p>")
    article = svc.create_article(db_session, author, data)
    assert article.slug == "how-to-add-a-chatbot"
    assert article.status == "draft"
    assert article.author_id == author.id


def test_create_article_rejects_duplicate_slug(db_session, business):
    author = _author(db_session, business)
    svc.create_article(db_session, author, ArticleCreate(title="First", slug="same-slug", content="<p>A</p>"))
    with pytest.raises(HTTPException) as exc:
        svc.create_article(db_session, author, ArticleCreate(title="Second", slug="same-slug", content="<p>B</p>"))
    assert exc.value.status_code == 409


def test_update_article_can_change_slug_if_available(db_session, business):
    author = _author(db_session, business)
    article = svc.create_article(db_session, author, ArticleCreate(title="Original", content="<p>A</p>"))
    updated = svc.update_article(db_session, article.id, ArticleUpdate(slug="new-slug"))
    assert updated.slug == "new-slug"


def test_update_article_rejects_changing_to_taken_slug(db_session, business):
    author = _author(db_session, business)
    svc.create_article(db_session, author, ArticleCreate(title="First", slug="taken", content="<p>A</p>"))
    second = svc.create_article(db_session, author, ArticleCreate(title="Second", slug="available", content="<p>B</p>"))
    with pytest.raises(HTTPException) as exc:
        svc.update_article(db_session, second.id, ArticleUpdate(slug="taken"))
    assert exc.value.status_code == 409


def test_update_article_sanitizes_new_content(db_session, business):
    author = _author(db_session, business)
    article = svc.create_article(db_session, author, ArticleCreate(title="X", content="<p>A</p>"))
    updated = svc.update_article(db_session, article.id, ArticleUpdate(content="<p>B</p><script>bad()</script>"))
    assert "<script" not in updated.content


def test_publish_sets_status_and_published_at_once(db_session, business):
    author = _author(db_session, business)
    article = svc.create_article(db_session, author, ArticleCreate(title="X", content="<p>A</p>"))
    assert article.published_at is None

    published = svc.mark_publish_intent(db_session, article.id)
    assert published.status == "published"
    assert published.published_at is not None
    assert published.deployment_status == "pending"
    assert published.deployment_status != "live"  # Publish alone must never mark an article Live

    first_published_at = published.published_at
    republished = svc.mark_publish_intent(db_session, article.id)
    assert republished.published_at == first_published_at  # unchanged on republish


def test_unpublish_reverts_to_draft(db_session, business):
    author = _author(db_session, business)
    article = svc.create_article(db_session, author, ArticleCreate(title="X", content="<p>A</p>"))
    svc.mark_publish_intent(db_session, article.id)

    unpublished = svc.mark_unpublish_intent(db_session, article.id)
    assert unpublished.status == "draft"


def test_unpublishing_a_live_article_removes_it_from_the_public_api(db_session, business):
    """Even an article that was genuinely confirmed Live disappears from
    the public API the moment it's unpublished -- the static site itself
    only catches up on the next manual deploy, but nothing should keep
    serving it as "published" from the database's point of view."""
    author = _author(db_session, business)
    article = svc.create_article(db_session, author, ArticleCreate(title="X", slug="was-live", content="<p>A</p>"))
    svc.mark_publish_intent(db_session, article.id)
    svc.record_deployment_result(db_session, article.id, success=True, message="ok")
    assert svc.get_article(db_session, article.id).deployment_status == "live"

    svc.mark_unpublish_intent(db_session, article.id)

    assert svc.get_public_article_by_slug(db_session, "was-live") is None
    slugs = {a.slug for a in svc.list_public_articles(db_session)["items"]}
    assert "was-live" not in slugs


def test_public_query_only_returns_published(db_session, business):
    author = _author(db_session, business)
    draft = svc.create_article(db_session, author, ArticleCreate(title="Draft One", content="<p>A</p>"))
    published = svc.create_article(db_session, author, ArticleCreate(title="Published One", content="<p>B</p>"))
    svc.mark_publish_intent(db_session, published.id)

    assert svc.get_public_article_by_slug(db_session, draft.slug) is None
    assert svc.get_public_article_by_slug(db_session, published.slug) is not None

    result = svc.list_public_articles(db_session)
    slugs = {a.slug for a in result["items"]}
    assert published.slug in slugs
    assert draft.slug not in slugs


def test_record_deployment_result_failure_sets_error(db_session, business):
    author = _author(db_session, business)
    article = svc.create_article(db_session, author, ArticleCreate(title="X", content="<p>A</p>"))
    svc.record_deployment_result(db_session, article.id, success=False, message="Missing: WEBSITE_REPO_PATH")

    refreshed = svc.get_article(db_session, article.id)
    assert refreshed.deployment_status == "failed"
    assert "WEBSITE_REPO_PATH" in refreshed.last_deployment_error


def test_record_deployment_result_success_marks_live_only_if_published(db_session, business):
    author = _author(db_session, business)
    article = svc.create_article(db_session, author, ArticleCreate(title="X", content="<p>A</p>"))

    # Still a draft -- a successful deploy of a draft-only site state isn't "live" for THIS article.
    svc.record_deployment_result(db_session, article.id, success=True, message="ok")
    assert svc.get_article(db_session, article.id).deployment_status == "not_deployed"

    svc.mark_publish_intent(db_session, article.id)
    svc.record_deployment_result(db_session, article.id, success=True, message="ok")
    assert svc.get_article(db_session, article.id).deployment_status == "live"
