"""API-level tests for plan-gated document uploads (app/api/documents.py)."""
import io


def _upload(client, headers, name="doc.txt", content=b"hello world"):
    return client.post(
        "/api/documents",
        headers=headers,
        files={"file": (name, io.BytesIO(content), "text/plain")},
    )


def test_upload_succeeds_under_free_plan_cap(client, business, mock_embeddings):
    resp = _upload(client, business["headers"])
    assert resp.status_code == 200
    assert resp.json()["status"] == "embedded"


def test_upload_blocked_once_free_plan_cap_reached(client, business, mock_embeddings):
    # Free plan cap is 2 documents.
    _upload(client, business["headers"], name="doc1.txt")
    _upload(client, business["headers"], name="doc2.txt")

    resp = _upload(client, business["headers"], name="doc3.txt")
    assert resp.status_code == 402
    assert "document uploads" in resp.json()["detail"]

    listing = client.get("/api/documents", headers=business["headers"])
    assert len(listing.json()) == 2  # the 3rd upload was never created


def test_upload_unblocked_after_upgrading_plan(client, business, mock_embeddings, set_plan):
    _upload(client, business["headers"], name="doc1.txt")
    _upload(client, business["headers"], name="doc2.txt")
    assert _upload(client, business["headers"], name="doc3.txt").status_code == 402

    set_plan(business["business_id"], "basic")

    resp = _upload(client, business["headers"], name="doc3.txt")
    assert resp.status_code == 200


def test_deleting_a_document_frees_up_the_cap(client, business, mock_embeddings):
    doc1 = _upload(client, business["headers"], name="doc1.txt").json()
    _upload(client, business["headers"], name="doc2.txt")
    assert _upload(client, business["headers"], name="doc3.txt").status_code == 402

    client.delete(f"/api/documents/{doc1['id']}", headers=business["headers"])

    resp = _upload(client, business["headers"], name="doc3.txt")
    assert resp.status_code == 200
