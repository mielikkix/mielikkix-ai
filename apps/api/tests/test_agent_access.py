"""Tests for the standalone Force-agent entitlement system (see
app/services/agent_access_service.py). This replaced the old
PlanFeatures.booking_enabled/seo_copywriter_enabled/
review_reputation_enabled/email_marketing_enabled booleans -- every agent
is purchased separately from the chat-widget plan, never bundled into it.
Per-agent gating on the actual agent routes (SEO Copywriter, Booking
Assistant, Review & Reputation, Email Marketing) is covered by each of
those features' own test files; this file covers the entitlement
mechanism itself: the catalog, the access-status endpoint, and admin
grant/revoke.
"""
from app.core.agent_catalog import AGENTS


def test_agent_catalog_lists_every_agent(client):
    resp = client.get("/api/businesses/agents")
    assert resp.status_code == 200
    keys = {item["key"] for item in resp.json()}
    assert keys == set(AGENTS.keys())


def test_my_agent_access_defaults_to_nothing_active(client, business):
    resp = client.get("/api/businesses/me/agents", headers=business["headers"])
    assert resp.status_code == 200
    assert resp.json() == {key: False for key in AGENTS}


def test_seo_agent_catalog_entry_has_free_and_professional_tiers(client):
    """SEO Audit & Optimization is the one agent sold as free-vs-paid tiers
    (see agent_catalog.py) rather than a single flat price -- everything
    else in the catalog keeps tiers=None."""
    resp = client.get("/api/businesses/agents")
    assert resp.status_code == 200
    by_key = {item["key"]: item for item in resp.json()}

    seo = by_key["seo_audit_optimization"]
    assert [t["key"] for t in seo["tiers"]] == ["free", "professional"]
    free, pro = seo["tiers"]
    assert free["name"] == "SEO Audit & Optimize"
    assert free["price_usd"] == 0 and free["price_nok"] == 0
    assert pro["name"] == "Professional SEO Audit & Optimization"
    assert pro["price_nok"] == 29901

    for key, item in by_key.items():
        if key != "seo_audit_optimization":
            assert item["tiers"] is None


def test_my_agent_access_reflects_a_granted_agent(client, business, grant_agent):
    grant_agent(business["business_id"], "seo_audit_optimization")

    resp = client.get("/api/businesses/me/agents", headers=business["headers"])

    body = resp.json()
    assert body["seo_audit_optimization"] is True
    assert body["booking_assistant"] is False


def test_agent_access_is_independent_of_chat_widget_plan(client, business, set_plan):
    """The whole point of this system: being on a paid chat-widget plan
    grants no agent access on its own -- see apps/agents/seo-audit/
    CLAUDE.md's "Standalone agent billing" decision."""
    set_plan(business["business_id"], "growth")

    resp = client.get("/api/businesses/me/agents", headers=business["headers"])

    assert resp.json() == {key: False for key in AGENTS}


def test_agent_access_is_scoped_per_business(client, business, signup, grant_agent):
    other = signup()
    grant_agent(other["business_id"], "seo_audit_optimization")

    resp = client.get("/api/businesses/me/agents", headers=business["headers"])

    assert resp.json()["seo_audit_optimization"] is False


def _make_admin(monkeypatch, email: str):
    from app.core.config import settings

    monkeypatch.setattr(settings, "platform_admin_emails", email)


def test_admin_can_grant_agent_access(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])

    resp = client.patch(
        f"/api/admin/businesses/{business['business_id']}/agents/booking_assistant",
        headers=business["headers"],
        json={"active": True},
    )

    assert resp.status_code == 200
    assert resp.json()["agent_access"]["booking_assistant"] is True

    status_resp = client.get("/api/businesses/me/agents", headers=business["headers"])
    assert status_resp.json()["booking_assistant"] is True


def test_admin_can_revoke_agent_access(client, business, monkeypatch, grant_agent):
    _make_admin(monkeypatch, business["email"])
    grant_agent(business["business_id"], "booking_assistant")

    resp = client.patch(
        f"/api/admin/businesses/{business['business_id']}/agents/booking_assistant",
        headers=business["headers"],
        json={"active": False},
    )

    assert resp.status_code == 200
    assert resp.json()["agent_access"]["booking_assistant"] is False


def test_admin_grant_unknown_agent_400s(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])

    resp = client.patch(
        f"/api/admin/businesses/{business['business_id']}/agents/not-a-real-agent",
        headers=business["headers"],
        json={"active": True},
    )

    assert resp.status_code == 400


def test_non_admin_cannot_grant_agent_access(client, business):
    resp = client.patch(
        f"/api/admin/businesses/{business['business_id']}/agents/booking_assistant",
        headers=business["headers"],
        json={"active": True},
    )
    assert resp.status_code == 403
