"""API-level tests for plan-gated business settings: custom widget branding
and multi-language support (app/api/businesses.py)."""


# ---------------------------------------------------------------------------
# Custom branding (widget color)
# ---------------------------------------------------------------------------

def test_default_color_allowed_on_free_plan(client, business):
    resp = client.patch("/api/businesses/me", headers=business["headers"], json={"primary_color": "#ff6b00"})
    assert resp.status_code == 200


def test_custom_color_rejected_on_free_plan(client, business):
    resp = client.patch("/api/businesses/me", headers=business["headers"], json={"primary_color": "#123456"})
    assert resp.status_code == 403


def test_custom_color_allowed_on_basic_plan(client, business, set_plan):
    set_plan(business["business_id"], "basic")
    resp = client.patch("/api/businesses/me", headers=business["headers"], json={"primary_color": "#123456"})
    assert resp.status_code == 200
    assert resp.json()["primary_color"] == "#123456"


def test_other_fields_unaffected_by_branding_gate(client, business):
    resp = client.patch("/api/businesses/me", headers=business["headers"], json={"name": "Renamed Co"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed Co"


# ---------------------------------------------------------------------------
# Languages
# ---------------------------------------------------------------------------

def test_single_language_allowed_on_free_plan(client, business):
    resp = client.patch("/api/businesses/me/settings", headers=business["headers"], json={"languages": ["en"]})
    assert resp.status_code == 200
    assert resp.json()["languages"] == ["en"]


def test_second_language_rejected_on_free_plan(client, business):
    resp = client.patch("/api/businesses/me/settings", headers=business["headers"], json={"languages": ["en", "es"]})
    assert resp.status_code == 402


def test_two_languages_allowed_on_basic_plan(client, business, set_plan):
    set_plan(business["business_id"], "basic")
    resp = client.patch("/api/businesses/me/settings", headers=business["headers"], json={"languages": ["en", "es"]})
    assert resp.status_code == 200


def test_many_languages_allowed_on_growth_plan(client, business, set_plan):
    set_plan(business["business_id"], "growth")
    langs = ["en", "es", "fr", "de", "hi"]
    resp = client.patch("/api/businesses/me/settings", headers=business["headers"], json={"languages": langs})
    assert resp.status_code == 200
    assert resp.json()["languages"] == langs
