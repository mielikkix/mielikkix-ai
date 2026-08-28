"""API-level tests for the platform-admin endpoints in app/api/admin.py."""
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.models.llm_usage import LLMUsageLog
from app.models.booking import Booking


def _make_admin(monkeypatch, email: str):
    monkeypatch.setattr(settings, "platform_admin_emails", email)


def test_admin_routes_require_auth(client):
    resp = client.get("/api/admin/overview")
    assert resp.status_code == 401


def test_admin_routes_reject_non_admin(client, business):
    resp = client.get("/api/admin/overview", headers=business["headers"])
    assert resp.status_code == 403


def test_admin_can_see_overview(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    resp = client.get("/api/admin/overview", headers=business["headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_businesses"] >= 1
    assert body["businesses_by_plan"].get("free", 0) >= 1


def test_admin_can_list_businesses(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    resp = client.get("/api/admin/businesses", headers=business["headers"])
    assert resp.status_code == 200
    body = resp.json()
    ids = {item["id"] for item in body["items"]}
    assert business["business_id"] in ids


def test_admin_business_list_search_filters(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    resp = client.get(
        "/api/admin/businesses", params={"q": "no-such-business-xyz"}, headers=business["headers"]
    )
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_admin_can_get_business_detail(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    resp = client.get(f"/api/admin/businesses/{business['business_id']}", headers=business["headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == business["business_id"]
    assert body["plan"] == "free"
    assert len(body["owners"]) == 1
    assert body["owners"][0]["email"] == business["email"]


def test_admin_business_detail_404_for_unknown_id(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    resp = client.get(
        "/api/admin/businesses/00000000-0000-0000-0000-000000000000", headers=business["headers"]
    )
    assert resp.status_code == 404


def test_admin_can_suspend_a_business(client, business, monkeypatch, set_plan):
    _make_admin(monkeypatch, business["email"])
    set_plan(business["business_id"], "growth")

    resp = client.patch(
        f"/api/admin/businesses/{business['business_id']}/status",
        headers=business["headers"],
        json={"status": "suspended"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "suspended"
    # Suspending drops the business to Free -- no active paid plan while suspended.
    assert body["plan"] == "free"

    detail = client.get(f"/api/admin/businesses/{business['business_id']}", headers=business["headers"])
    assert detail.json()["status"] == "suspended"
    assert detail.json()["plan"] == "free"


def test_admin_can_reactivate_a_business_without_touching_plan(client, business, monkeypatch, set_plan):
    _make_admin(monkeypatch, business["email"])
    set_plan(business["business_id"], "basic")
    client.patch(
        f"/api/admin/businesses/{business['business_id']}/status",
        headers=business["headers"],
        json={"status": "suspended"},
    )

    resp = client.patch(
        f"/api/admin/businesses/{business['business_id']}/status",
        headers=business["headers"],
        json={"status": "active"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"
    assert resp.json()["plan"] == "free"  # reactivating doesn't restore the old plan


def test_admin_status_update_rejects_invalid_value(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    resp = client.patch(
        f"/api/admin/businesses/{business['business_id']}/status",
        headers=business["headers"],
        json={"status": "trial"},
    )
    assert resp.status_code == 422


def test_non_admin_cannot_change_business_status(client, business):
    resp = client.patch(
        f"/api/admin/businesses/{business['business_id']}/status",
        headers=business["headers"],
        json={"status": "suspended"},
    )
    assert resp.status_code == 403


def test_admin_can_set_a_paid_plan(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    resp = client.patch(
        f"/api/admin/businesses/{business['business_id']}/plan",
        headers=business["headers"],
        json={"plan": "growth"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"] == "growth"
    # No payment processor exists -- this is the only real signal of a
    # "purchase" today, same rule the (now Free-only) self-serve endpoint used to apply.
    assert body["status"] == "active"


def test_admin_setting_free_plan_reverts_status_to_trial(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    client.patch(
        f"/api/admin/businesses/{business['business_id']}/plan",
        headers=business["headers"],
        json={"plan": "growth"},
    )
    resp = client.patch(
        f"/api/admin/businesses/{business['business_id']}/plan",
        headers=business["headers"],
        json={"plan": "free"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "trial"


def test_admin_setting_plan_on_a_suspended_business_does_not_reactivate_it(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    client.patch(
        f"/api/admin/businesses/{business['business_id']}/status",
        headers=business["headers"],
        json={"status": "suspended"},
    )
    resp = client.patch(
        f"/api/admin/businesses/{business['business_id']}/plan",
        headers=business["headers"],
        json={"plan": "basic"},
    )
    assert resp.status_code == 200
    assert resp.json()["plan"] == "basic"
    assert resp.json()["status"] == "suspended"  # use the status endpoint to reactivate, not this one


def test_admin_plan_update_rejects_invalid_value(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    resp = client.patch(
        f"/api/admin/businesses/{business['business_id']}/plan",
        headers=business["headers"],
        json={"plan": "enterprise-plus"},
    )
    assert resp.status_code == 422


def test_non_admin_cannot_set_business_plan(client, business):
    resp = client.patch(
        f"/api/admin/businesses/{business['business_id']}/plan",
        headers=business["headers"],
        json={"plan": "growth"},
    )
    assert resp.status_code == 403


def test_admin_llm_usage_aggregates_logged_calls(client, business, monkeypatch, db_session):
    _make_admin(monkeypatch, business["email"])

    db_session.add(LLMUsageLog(
        business_id=business["business_id"],
        provider="groq",
        model="llama-3.1-8b-instant",
        kind="chat",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
    ))
    db_session.commit()

    resp = client.get("/api/admin/llm-usage", headers=business["headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["totals"]["requests"] == 1
    assert body["totals"]["total_tokens"] == 150
    assert body["by_business"][0]["business_id"] == business["business_id"]


def _make_booking(db_session, **overrides) -> Booking:
    now = datetime.now(timezone.utc)
    fields = {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "meeting_type": "consultation",
        "start_at": now + timedelta(days=1),
        "end_at": now + timedelta(days=1, minutes=30),
        "calendar_event_id": "fake-event-id",
    }
    fields.update(overrides)
    booking = Booking(**fields)
    db_session.add(booking)
    db_session.commit()
    return booking


def test_non_admin_cannot_list_bookings(client, business):
    resp = client.get("/api/admin/bookings", headers=business["headers"])
    assert resp.status_code == 403


def test_admin_can_list_bookings(client, business, monkeypatch, db_session):
    _make_admin(monkeypatch, business["email"])
    _make_booking(db_session, name="Jane Doe", email="jane@example.com")

    resp = client.get("/api/admin/bookings", headers=business["headers"])

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Jane Doe"
    assert body["items"][0]["email"] == "jane@example.com"
    assert body["items"][0]["status"] == "confirmed"


def test_admin_bookings_most_recent_first(client, business, monkeypatch, db_session):
    _make_admin(monkeypatch, business["email"])
    _make_booking(db_session, name="Booked First", email="first@example.com")
    _make_booking(db_session, name="Booked Second", email="second@example.com")

    resp = client.get("/api/admin/bookings", headers=business["headers"])

    names = [item["name"] for item in resp.json()["items"]]
    assert names == ["Booked Second", "Booked First"]


def test_admin_bookings_pagination(client, business, monkeypatch, db_session):
    _make_admin(monkeypatch, business["email"])
    for i in range(3):
        _make_booking(db_session, name=f"Booking {i}", email=f"booking{i}@example.com")

    resp = client.get("/api/admin/bookings", params={"page": 1, "page_size": 2}, headers=business["headers"])
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2

    resp2 = client.get("/api/admin/bookings", params={"page": 2, "page_size": 2}, headers=business["headers"])
    assert len(resp2.json()["items"]) == 1
