"""API-level tests for plan-gated products (app/api/products.py)."""


def _product(name="Widget", price=9.99, currency="USD"):
    return {"name": name, "price": price, "currency": currency}


def test_create_product_succeeds_under_cap(client, business):
    resp = client.post("/api/products", headers=business["headers"], json=_product())
    assert resp.status_code == 200
    assert resp.json()["currency"] == "USD"


def test_create_product_blocked_at_free_plan_cap(client, business):
    for i in range(10):  # Free plan cap is 10
        r = client.post("/api/products", headers=business["headers"], json=_product(name=f"Item {i}"))
        assert r.status_code == 200

    resp = client.post("/api/products", headers=business["headers"], json=_product(name="Item 11"))
    assert resp.status_code == 402


def test_non_usd_currency_rejected_on_free_plan(client, business):
    resp = client.post("/api/products", headers=business["headers"], json=_product(currency="EUR"))
    assert resp.status_code == 403


def test_non_usd_currency_allowed_on_basic_plan(client, business, set_plan):
    set_plan(business["business_id"], "basic")
    resp = client.post("/api/products", headers=business["headers"], json=_product(currency="EUR"))
    assert resp.status_code == 200
    assert resp.json()["currency"] == "EUR"


def test_updating_product_to_non_usd_currency_rejected_on_free_plan(client, business):
    created = client.post("/api/products", headers=business["headers"], json=_product()).json()
    resp = client.patch(
        f"/api/products/{created['id']}", headers=business["headers"], json={"currency": "GBP"}
    )
    assert resp.status_code == 403


def test_product_limit_unlimited_on_growth_plan(client, business, set_plan):
    set_plan(business["business_id"], "growth")
    for i in range(15):  # comfortably above the Free/Basic caps
        r = client.post("/api/products", headers=business["headers"], json=_product(name=f"Item {i}"))
        assert r.status_code == 200


def test_deleting_a_product_with_seo_drafts_succeeds_and_removes_them(client, business, db_session):
    """Production 2026-10-02: DELETE /api/products/<id> returned 500 for a product
    that had an SEO Copywriter draft -- seo_drafts.product_id is a plain foreign
    key, so Postgres refused to delete the product out from under the draft."""
    from app.models.seo_draft import SeoDraft

    created = client.post("/api/products", headers=business["headers"], json=_product()).json()
    db_session.add(SeoDraft(business_id=business["business_id"], product_id=created["id"], draft_seo_title="x"))
    db_session.commit()

    resp = client.delete(f"/api/products/{created['id']}", headers=business["headers"])

    assert resp.status_code == 200
    db_session.expire_all()
    assert db_session.query(SeoDraft).filter(SeoDraft.product_id == created["id"]).count() == 0
