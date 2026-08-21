"""API-level tests for the plan/billing endpoints in app/api/businesses.py."""


def test_plan_catalog_is_public_and_has_four_plans(client):
    resp = client.get("/api/businesses/plans")
    assert resp.status_code == 200
    keys = {p["key"] for p in resp.json()}
    assert keys == {"free", "basic", "business", "growth"}


def test_plan_catalog_prices_match_pricing_page(client):
    resp = client.get("/api/businesses/plans")
    prices = {p["key"]: p["price_usd"] for p in resp.json()}
    assert prices == {"free": 0, "basic": 24, "business": 48, "growth": 96}


def test_get_my_plan_requires_auth(client):
    resp = client.get("/api/businesses/me/plan")
    assert resp.status_code in (401, 403)


def test_get_my_plan_defaults_to_free(client, business):
    resp = client.get("/api/businesses/me/plan", headers=business["headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"] == "free"
    assert body["usage"]["documents"] == 0


# ---------------------------------------------------------------------------
# Self-serve plan switching is Free-only -- no payment processor exists, so
# a business can never reach a paid plan through its own dashboard. Paid
# plans are admin-only (see test_admin_api.py's plan-set tests).
# ---------------------------------------------------------------------------

def test_self_serve_cannot_switch_to_a_paid_plan(client, business):
    resp = client.patch("/api/businesses/me/plan", headers=business["headers"], json={"plan": "growth"})
    assert resp.status_code == 403

    check = client.get("/api/businesses/me/plan", headers=business["headers"])
    assert check.json()["plan"] == "free"  # unchanged


def test_self_serve_can_switch_to_free_when_already_free(client, business):
    resp = client.patch("/api/businesses/me/plan", headers=business["headers"], json={"plan": "free"})
    assert resp.status_code == 200
    assert resp.json()["plan"] == "free"


def test_choose_unknown_plan_rejected(client, business):
    resp = client.patch("/api/businesses/me/plan", headers=business["headers"], json={"plan": "enterprise-plus"})
    assert resp.status_code == 400


def test_self_serve_switch_to_free_reverts_status_to_trial(client, business, set_plan):
    # Get onto a paid plan the only way possible today (admin/direct DB, not
    # self-serve) so there's something real to revert from.
    set_plan(business["business_id"], "growth")
    me = client.get("/api/businesses/me", headers=business["headers"])
    assert me.json()["status"] == "active"

    resp = client.patch("/api/businesses/me/plan", headers=business["headers"], json={"plan": "free"})
    assert resp.status_code == 200
    assert resp.json()["plan"] == "free"

    me = client.get("/api/businesses/me", headers=business["headers"])
    assert me.json()["status"] == "trial"


def test_switching_away_from_business_clears_api_addon(client, business, set_plan):
    set_plan(business["business_id"], "business")
    client.patch("/api/businesses/me/plan/api-access-addon", headers=business["headers"], json={"enabled": True})

    resp = client.patch("/api/businesses/me/plan", headers=business["headers"], json={"plan": "free"})
    assert resp.status_code == 200
    assert resp.json()["api_access_addon"] is False
    assert resp.json()["features"]["api_access"] is False


def test_api_addon_only_available_on_business_plan(client, business):
    # Still on Free by default.
    resp = client.patch("/api/businesses/me/plan/api-access-addon", headers=business["headers"], json={"enabled": True})
    assert resp.status_code == 403


def test_api_addon_toggle_on_business_plan(client, business, set_plan):
    set_plan(business["business_id"], "business")
    resp = client.patch("/api/businesses/me/plan/api-access-addon", headers=business["headers"], json={"enabled": True})
    assert resp.status_code == 200
    assert resp.json()["features"]["api_access"] is True


# ---------------------------------------------------------------------------
# API key
# ---------------------------------------------------------------------------

def test_create_api_key_blocked_without_access(client, business):
    resp = client.post("/api/businesses/me/api-key", headers=business["headers"])
    assert resp.status_code == 403


def test_create_api_key_succeeds_on_growth(client, business, set_plan):
    set_plan(business["business_id"], "growth")
    resp = client.post("/api/businesses/me/api-key", headers=business["headers"])
    assert resp.status_code == 200
    assert resp.json()["api_key"].startswith("an_")


def test_revoke_api_key(client, business, set_plan):
    set_plan(business["business_id"], "growth")
    client.post("/api/businesses/me/api-key", headers=business["headers"])
    resp = client.delete("/api/businesses/me/api-key", headers=business["headers"])
    assert resp.status_code == 200
    assert resp.json()["api_key"] is None


# ---------------------------------------------------------------------------
# Notification channels -- 403 (wrong plan) vs 501 (right plan, not built)
# ---------------------------------------------------------------------------

def test_whatsapp_channel_forbidden_on_free(client, business):
    resp = client.post(
        "/api/businesses/me/notification-channels",
        headers=business["headers"],
        json={"channel": "whatsapp", "enabled": True},
    )
    assert resp.status_code == 403


def test_whatsapp_channel_not_implemented_on_business(client, business, set_plan):
    set_plan(business["business_id"], "business")
    resp = client.post(
        "/api/businesses/me/notification-channels",
        headers=business["headers"],
        json={"channel": "whatsapp", "enabled": True},
    )
    assert resp.status_code == 501


def test_unknown_notification_channel_rejected(client, business):
    resp = client.post(
        "/api/businesses/me/notification-channels",
        headers=business["headers"],
        json={"channel": "carrier-pigeon", "enabled": True},
    )
    assert resp.status_code == 400
