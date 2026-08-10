"""API-level tests for app/api/websites.py -- the newly added "websites"
resource that backs the pricing page's website-count limits."""


def test_list_websites_starts_empty(client, business):
    resp = client.get("/api/websites", headers=business["headers"])
    assert resp.status_code == 200
    assert resp.json() == []


def test_add_website_succeeds(client, business):
    resp = client.post("/api/websites", headers=business["headers"], json={"domain": "example.com", "label": "Main site"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["domain"] == "example.com"
    assert body["label"] == "Main site"


def test_free_plan_blocked_after_one_website(client, business):
    client.post("/api/websites", headers=business["headers"], json={"domain": "site-one.com"})
    resp = client.post("/api/websites", headers=business["headers"], json={"domain": "site-two.com"})
    assert resp.status_code == 402


def test_business_plan_allows_up_to_three_websites(client, business, set_plan):
    set_plan(business["business_id"], "business")
    for domain in ["a.com", "b.com", "c.com"]:
        resp = client.post("/api/websites", headers=business["headers"], json={"domain": domain})
        assert resp.status_code == 200

    resp = client.post("/api/websites", headers=business["headers"], json={"domain": "d.com"})
    assert resp.status_code == 402


def test_delete_website_frees_up_the_cap(client, business):
    created = client.post("/api/websites", headers=business["headers"], json={"domain": "site-one.com"}).json()
    assert client.post("/api/websites", headers=business["headers"], json={"domain": "site-two.com"}).status_code == 402

    client.delete(f"/api/websites/{created['id']}", headers=business["headers"])

    resp = client.post("/api/websites", headers=business["headers"], json={"domain": "site-two.com"})
    assert resp.status_code == 200


def test_websites_are_scoped_per_business(client, signup):
    biz_a = signup()
    biz_b = signup()
    client.post("/api/websites", headers=biz_a["headers"], json={"domain": "a-only.com"})

    resp = client.get("/api/websites", headers=biz_b["headers"])
    assert resp.json() == []
