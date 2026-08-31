def test_register_and_login(client):
    resp = client.post("/api/auth/register", json={
        "business_name": "Test Shop",
        "business_slug": "test-shop",
        "industry": "retail",
        "full_name": "Owner One",
        "email": "owner@testshop.com",
        "password": "secret12345",
    })
    assert resp.status_code == 200
    assert resp.json()["email"] == "owner@testshop.com"
    assert resp.cookies.get("access_token")

    resp2 = client.post("/api/auth/login", json={
        "email": "owner@testshop.com",
        "password": "secret12345",
    })
    assert resp2.status_code == 200
    assert resp2.cookies.get("access_token")


def test_duplicate_email(client):
    client.post("/api/auth/register", json={
        "business_name": "Shop B",
        "business_slug": "shop-b",
        "full_name": "Owner B",
        "email": "dup@test.com",
        "password": "password123",
    })
    resp = client.post("/api/auth/register", json={
        "business_name": "Shop C",
        "business_slug": "shop-c",
        "full_name": "Owner C",
        "email": "dup@test.com",
        "password": "password123",
    })
    assert resp.status_code == 400


def test_duplicate_slug(client):
    client.post("/api/auth/register", json={
        "business_name": "Shop D",
        "business_slug": "shop-d",
        "full_name": "Owner D",
        "email": "d1@test.com",
        "password": "password123",
    })
    resp = client.post("/api/auth/register", json={
        "business_name": "Shop D Copycat",
        "business_slug": "shop-d",
        "full_name": "Owner D2",
        "email": "d2@test.com",
        "password": "password123",
    })
    assert resp.status_code == 400


def test_login_wrong_password(client, business):
    resp = client.post("/api/auth/login", json={
        "email": business["email"],
        "password": "not-the-right-password",
    })
    assert resp.status_code == 401


def test_login_unknown_email(client):
    resp = client.post("/api/auth/login", json={
        "email": "nobody@nowhere.com",
        "password": "whatever",
    })
    assert resp.status_code == 401


def test_new_business_defaults_to_free_plan(client, business):
    resp = client.get("/api/businesses/me", headers=business["headers"])
    assert resp.status_code == 200
    assert resp.json()["plan"] == "free"


def test_new_business_defaults_contact_email_to_owners_login_email(client, business):
    """So lead/booking notifications (notifications/notify_new_lead,
    notify_new_booking) have somewhere to go from the moment a business
    signs up, rather than silently going nowhere until someone visits
    Settings and fills this in by hand -- editable there afterward."""
    resp = client.get("/api/businesses/me/settings", headers=business["headers"])
    assert resp.status_code == 200
    assert resp.json()["contact_email"] == business["email"]
