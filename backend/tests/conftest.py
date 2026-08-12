import itertools
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import Base, get_db
from app.core.limiter import limiter

# Counter to keep auto-generated business slugs/emails unique across tests
# within a run, without every test having to invent its own unique string.
_seq = itertools.count(1)

# Tests run against a real Postgres database (a separate one from dev/prod
# data), not SQLite. The app's models use Postgres-specific types
# (dialects.postgresql.UUID, JSON columns backed by pgvector in prod), and
# SQLite's stricter UUID bind-processor doesn't match how psycopg2 handles
# plain-string UUID comparisons -- that mismatch caused confusing, backend-
# specific failures unrelated to the actual business logic under test.
# Override via TEST_DATABASE_URL if your Postgres isn't on localhost:5432.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://mielikkix:mielikkix@localhost:5432/mielikkix_test"
)
_engine = create_engine(TEST_DATABASE_URL)


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    # The Limiter's in-memory storage is a module-level singleton (see
    # core/limiter.py), so without this every test shares one "testclient"
    # rate-limit bucket -- tests that call a limited endpoint (e.g.
    # /api/auth/register via the `signup` fixture) start failing with 429
    # partway through a run purely because of test order/count, not because
    # of anything the test itself is checking.
    limiter.reset()
    yield


@pytest.fixture()
def db_session():
    """A fresh, isolated schema per test function on the shared Postgres
    test database -- tables are dropped and recreated each time so tests
    can never see another test's data or leak state between runs."""
    Base.metadata.create_all(bind=_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def mock_embeddings(monkeypatch):
    """Document ingestion normally calls the real sentence-transformers
    model (slow to load, and not something a unit test should depend on).
    Tests that need a document to actually reach 'embedded' status opt into
    this fixture instead of loading the real model."""
    def fake_embed_texts(texts):
        return [[0.0, 0.0, 0.0] for _ in texts]

    monkeypatch.setattr("app.services.document_service.embed_texts", fake_embed_texts)
    return fake_embed_texts


@pytest.fixture()
def signup(client):
    """Factory fixture: registers a new business + owner user and returns
    a dict with the auth headers and IDs tests need. Each call gets a
    unique slug/email so a test can register multiple businesses."""

    def _signup(**overrides):
        n = next(_seq)
        payload = {
            "business_name": f"Test Biz {n}",
            "business_slug": f"test-biz-{n}",
            "industry": "retail",
            "full_name": "Test Owner",
            "email": f"owner{n}@example.com",
            "password": "supersecret123",
        }
        payload.update(overrides)
        resp = client.post("/api/auth/register", json=payload)
        assert resp.status_code == 200, resp.text
        token = resp.cookies.get("access_token")
        headers = {"Authorization": f"Bearer {token}"}

        me = client.get("/api/businesses/me", headers=headers)
        assert me.status_code == 200, me.text

        return {
            "token": token,
            "headers": headers,
            "business_id": me.json()["id"],
            "email": payload["email"],
            "password": payload["password"],
        }

    return _signup


@pytest.fixture()
def business(signup):
    """A single ready-to-use business (Free plan by default)."""
    return signup()


@pytest.fixture()
def set_plan(db_session):
    """Directly sets a business's plan for test setup, bypassing HTTP.

    PATCH /api/businesses/me/plan is Free-only now (see
    api/businesses.py:choose_plan) -- no payment processor exists, so
    self-serve can't reach a paid plan anymore. Tests that need a business
    already sitting on a paid plan to exercise some *other* gated feature
    (document limits, API access, etc.) use this instead of the admin
    endpoint, to keep that setup a one-liner unrelated to admin auth."""
    from app.models.business import Business

    def _set(business_id, plan):
        biz = db_session.query(Business).filter(Business.id == business_id).first()
        biz.plan = plan
        biz.status = "trial" if plan == "free" else "active"
        db_session.commit()
        return biz

    return _set
