"""GDPR Phase 6 guard: the retention periods written in the internal
retention schedule and the public Privacy Policy must match the code. If
this fails, update the documents (and legal review) together with the code."""
from pathlib import Path

from app.core import legal
from app.core.config import settings
from app.services.auth_service import RESET_TOKEN_TTL

REPO = Path(__file__).resolve().parents[3]
SCHEDULE = (REPO / "docs/privacy/retention-schedule.md").read_text(encoding="utf-8")
PRIVACY = (REPO / "website/src/pages/privacy.astro").read_text(encoding="utf-8")
WEBSITE_LEGAL = (REPO / "website/src/config/legal.ts").read_text(encoding="utf-8")


def test_account_deletion_grace_period():
    assert legal.DELETION_GRACE_DAYS == 30
    assert "**30-day grace period**" in SCHEDULE
    assert "after a 30-day grace period" in PRIVACY


def test_minimised_consent_retention():
    assert legal.CONSENT_RETENTION_AFTER_DELETION_DAYS == 3 * 365
    assert "**3 years** after the account is deleted" in SCHEDULE
    assert "kept in minimised form for 3 years after account deletion" in PRIVACY


def test_conversation_retention_bounds():
    assert (legal.CONVERSATION_RETENTION_DEFAULT_DAYS, legal.CONVERSATION_RETENTION_MIN_DAYS, legal.CONVERSATION_RETENTION_MAX_DAYS) == (90, 1, 365)
    assert "default **90**, allowed **1–365**" in SCHEDULE
    assert "90 days by default, and never more than 365 days" in PRIVACY


def test_token_lifetimes():
    assert RESET_TOKEN_TTL.total_seconds() == 3600 and "Usable for 1 hour" in SCHEDULE
    assert settings.access_token_expire_minutes == 24 * 60 and "| 24 hours |" in SCHEDULE


def test_consent_cookie_lifetime_and_versions_match_website():
    assert "CONSENT_MAX_AGE_SECONDS = 365 * 24 * 60 * 60" in WEBSITE_LEGAL and "12 months" in SCHEDULE
    # Sign-up records the same document versions the website publishes.
    assert f'terms: {{ version: "{legal.TERMS_VERSION}"' in WEBSITE_LEGAL
    assert f'dpa: {{ version: "{legal.DPA_VERSION}"' in WEBSITE_LEGAL
