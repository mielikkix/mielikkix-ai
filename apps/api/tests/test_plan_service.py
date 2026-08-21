"""Unit tests for app/services/plan_service.py -- the core plan-gating
business logic -- exercised directly against a DB session, with no HTTP
layer involved."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.services import plan_service
from app.models.business import Business
from app.models.document import Document
from app.models.product import Product
from app.models.conversation import Conversation
from app.models.website import BusinessWebsite


def make_business(db_session, plan="free", **overrides) -> Business:
    biz = Business(name="Unit Test Co", slug=f"unit-test-{uuid.uuid4().hex[:8]}", plan=plan, **overrides)
    db_session.add(biz)
    db_session.commit()
    db_session.refresh(biz)
    return biz


def add_documents(db_session, business_id, count):
    for i in range(count):
        db_session.add(Document(
            business_id=business_id, filename=f"doc{i}.txt", file_url=f"./doc{i}.txt", file_type="txt",
        ))
    db_session.commit()


def add_products(db_session, business_id, count, currency="USD"):
    for i in range(count):
        db_session.add(Product(business_id=business_id, name=f"Product {i}", currency=currency))
    db_session.commit()


def add_websites(db_session, business_id, count):
    for i in range(count):
        db_session.add(BusinessWebsite(business_id=business_id, domain=f"site{i}.example.com"))
    db_session.commit()


def add_conversation(db_session, business_id, started_at=None):
    conv = Conversation(business_id=business_id, session_id=uuid.uuid4().hex)
    if started_at is not None:
        conv.started_at = started_at
    db_session.add(conv)
    db_session.commit()
    return conv


# ---------------------------------------------------------------------------
# get_usage / get_plan_status
# ---------------------------------------------------------------------------

def test_get_usage_counts_resources(db_session):
    biz = make_business(db_session)
    add_documents(db_session, biz.id, 3)
    add_products(db_session, biz.id, 2)
    add_websites(db_session, biz.id, 1)

    usage = plan_service.get_usage(db_session, biz.id)
    assert usage["documents"] == 3
    assert usage["products"] == 2
    assert usage["websites"] == 1
    assert usage["conversations_this_month"] == 0


def test_get_usage_only_counts_current_month_conversations(db_session):
    biz = make_business(db_session)
    now = datetime.now(timezone.utc)
    add_conversation(db_session, biz.id, started_at=now)
    add_conversation(db_session, biz.id, started_at=now - timedelta(days=45))  # last month

    usage = plan_service.get_usage(db_session, biz.id)
    assert usage["conversations_this_month"] == 1


def test_get_plan_status_shape(db_session):
    biz = make_business(db_session, plan="basic")
    status = plan_service.get_plan_status(db_session, biz)
    assert status["plan"] == "basic"
    assert status["plan_name"] == "Basic"
    assert status["limits"]["max_document_uploads"] == 20
    assert status["features"]["multi_currency"] is True
    assert "usage" in status


# ---------------------------------------------------------------------------
# resolve_features -- the Business-tier API-access-addon override
# ---------------------------------------------------------------------------

def test_growth_plan_gets_api_access_without_addon(db_session):
    biz = make_business(db_session, plan="growth")
    assert plan_service.resolve_features(biz)["api_access"] is True


def test_business_plan_needs_addon_for_api_access(db_session):
    biz = make_business(db_session, plan="business", api_access_addon=False)
    assert plan_service.resolve_features(biz)["api_access"] is False

    biz.api_access_addon = True
    assert plan_service.resolve_features(biz)["api_access"] is True


def test_free_plan_never_gets_api_access_even_with_addon_flag_set(db_session):
    # api_access_addon only means something on the Business tier -- setting
    # it on a Free-plan business (e.g. after a downgrade) must not leak access.
    biz = make_business(db_session, plan="free", api_access_addon=True)
    assert plan_service.resolve_features(biz)["api_access"] is False


# ---------------------------------------------------------------------------
# Limit checks -- boundary behavior
# ---------------------------------------------------------------------------

def test_document_limit_passes_under_cap(db_session):
    biz = make_business(db_session, plan="free")  # cap = 2
    add_documents(db_session, biz.id, 1)
    plan_service.check_document_limit(db_session, biz)  # should not raise


def test_document_limit_raises_at_cap(db_session):
    biz = make_business(db_session, plan="free")  # cap = 2
    add_documents(db_session, biz.id, 2)
    with pytest.raises(HTTPException) as exc:
        plan_service.check_document_limit(db_session, biz)
    assert exc.value.status_code == 402


def test_document_limit_unlimited_on_business_plan(db_session):
    biz = make_business(db_session, plan="business")
    add_documents(db_session, biz.id, 500)
    plan_service.check_document_limit(db_session, biz)  # should not raise


def test_product_limit_raises_at_cap(db_session):
    biz = make_business(db_session, plan="free")  # cap = 10
    add_products(db_session, biz.id, 10)
    with pytest.raises(HTTPException) as exc:
        plan_service.check_product_limit(db_session, biz)
    assert exc.value.status_code == 402


def test_website_limit_raises_at_cap(db_session):
    biz = make_business(db_session, plan="free")  # cap = 1
    add_websites(db_session, biz.id, 1)
    with pytest.raises(HTTPException) as exc:
        plan_service.check_website_limit(db_session, biz)
    assert exc.value.status_code == 402


def test_conversation_limit_raises_at_cap(db_session):
    biz = make_business(db_session, plan="free")  # cap = 50
    for _ in range(50):
        add_conversation(db_session, biz.id)
    with pytest.raises(HTTPException) as exc:
        plan_service.check_conversation_limit(db_session, biz)
    assert exc.value.status_code == 402


def test_conversation_limit_ignores_conversations_from_prior_months(db_session):
    biz = make_business(db_session, plan="free")  # cap = 50
    old = datetime.now(timezone.utc) - timedelta(days=40)
    for _ in range(50):
        add_conversation(db_session, biz.id, started_at=old)
    plan_service.check_conversation_limit(db_session, biz)  # none count this month -- should not raise


def test_language_limit_raises_over_cap(db_session):
    biz = make_business(db_session, plan="free")  # max_languages = 1
    with pytest.raises(HTTPException) as exc:
        plan_service.check_language_limit(biz, ["en", "es"])
    assert exc.value.status_code == 402


def test_language_limit_passes_at_cap(db_session):
    biz = make_business(db_session, plan="free")  # max_languages = 1
    plan_service.check_language_limit(biz, ["en"])  # should not raise


def test_language_limit_unlimited_on_business_plan(db_session):
    biz = make_business(db_session, plan="business")
    plan_service.check_language_limit(biz, ["en", "es", "fr", "de", "hi"])  # should not raise


# ---------------------------------------------------------------------------
# require_feature -- locked (403) vs not-yet-implemented (501)
# ---------------------------------------------------------------------------

def test_require_feature_raises_403_when_plan_lacks_it(db_session):
    biz = make_business(db_session, plan="free")
    with pytest.raises(HTTPException) as exc:
        plan_service.require_feature(biz, "custom_branding")
    assert exc.value.status_code == 403


def test_require_feature_raises_501_for_not_yet_implemented(db_session):
    # Business plan *includes* whatsapp_notifications, but the feature
    # itself was never built -- this must be distinguishable from "locked".
    biz = make_business(db_session, plan="business")
    with pytest.raises(HTTPException) as exc:
        plan_service.require_feature(biz, "whatsapp_notifications")
    assert exc.value.status_code == 501


def test_require_feature_passes_for_implemented_included_feature(db_session):
    biz = make_business(db_session, plan="basic")
    plan_service.require_feature(biz, "custom_branding")  # should not raise


# ---------------------------------------------------------------------------
# Analytics tier resolution
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("plan,expected_tier", [
    ("free", "basic"),
    ("basic", "standard"),
    ("business", "advanced"),
    ("growth", "advanced"),
])
def test_resolve_analytics_tier(db_session, plan, expected_tier):
    biz = make_business(db_session, plan=plan)
    assert plan_service.resolve_analytics_tier(biz) == expected_tier


def test_unknown_plan_falls_back_to_free(db_session):
    # get_plan() defaults unknown/legacy plan values to "free" rather than KeyError-ing.
    biz = make_business(db_session, plan="some-deleted-legacy-plan")
    status = plan_service.get_plan_status(db_session, biz)
    assert status["plan"] == "free"
