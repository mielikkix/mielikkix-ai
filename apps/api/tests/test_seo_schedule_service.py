"""Tests for Stage 15 (apps/agents/seo-audit/CLAUDE.md's "Professional
tier roadmap"): recurring audit scheduling. Pure service-layer logic here
(due_websites, set_schedule, run_due_audits); the HTTP surface
(PATCH .../schedule) is covered in test_seo_websites.py.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.models.seo_audit import SeoAudit
from app.models.seo_website import SeoWebsite
from app.services import seo_audit_service, seo_schedule_service


def _website(db_session, business, **overrides):
    defaults = dict(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    defaults.update(overrides)
    website = SeoWebsite(**defaults)
    db_session.add(website)
    db_session.commit()
    db_session.refresh(website)
    return website


def test_set_schedule_weekly_sets_next_run_about_a_week_out(db_session, business):
    website = _website(db_session, business)
    before = datetime.now(timezone.utc)

    seo_schedule_service.set_schedule(db_session, website, "weekly")

    assert website.audit_schedule == "weekly"
    delta = website.next_scheduled_audit_at - before
    assert timedelta(days=6, hours=23) < delta < timedelta(days=7, hours=1)


def test_set_schedule_none_turns_scheduling_off(db_session, business):
    website = _website(db_session, business, audit_schedule="weekly", next_scheduled_audit_at=datetime.now(timezone.utc))

    seo_schedule_service.set_schedule(db_session, website, None)

    assert website.audit_schedule is None
    assert website.next_scheduled_audit_at is None


def test_set_schedule_rejects_unknown_interval(db_session, business):
    website = _website(db_session, business)
    with pytest.raises(seo_schedule_service.InvalidScheduleError):
        seo_schedule_service.set_schedule(db_session, website, "daily")


def test_set_schedule_switching_interval_restarts_the_countdown(db_session, business):
    website = _website(db_session, business)
    seo_schedule_service.set_schedule(db_session, website, "weekly")
    weekly_next = website.next_scheduled_audit_at

    seo_schedule_service.set_schedule(db_session, website, "monthly")

    assert website.audit_schedule == "monthly"
    assert website.next_scheduled_audit_at > weekly_next


def test_due_websites_finds_only_past_due_scheduled_websites(db_session, business):
    now = datetime.now(timezone.utc)
    due = _website(db_session, business, audit_schedule="weekly", next_scheduled_audit_at=now - timedelta(hours=1))
    _website(db_session, business, url="https://other.test", audit_schedule="weekly", next_scheduled_audit_at=now + timedelta(days=1))
    _website(db_session, business, url="https://unscheduled.test", audit_schedule=None, next_scheduled_audit_at=None)

    results = seo_schedule_service.due_websites(db_session, now)

    assert [w.id for w in results] == [due.id]


@pytest.mark.asyncio
async def test_run_due_audits_starts_an_audit_and_reschedules(db_session, business, monkeypatch):
    now = datetime.now(timezone.utc)
    website = _website(db_session, business, audit_schedule="weekly", next_scheduled_audit_at=now - timedelta(hours=1))

    monkeypatch.setattr(seo_audit_service, "run_audit", AsyncMock(return_value=None))

    started = await seo_schedule_service.run_due_audits(db_session)

    assert started == 1
    assert db_session.query(SeoAudit).filter(SeoAudit.website_id == website.id).count() == 1
    # Rescheduled forward, no longer due against the same "now".
    assert website.next_scheduled_audit_at > now


@pytest.mark.asyncio
async def test_run_due_audits_reschedules_even_if_the_audit_fails(db_session, business, monkeypatch):
    """A website stuck failing every audit shouldn't spam retries faster
    than its own configured cadence -- see run_due_audits' own docstring."""
    now = datetime.now(timezone.utc)
    website = _website(db_session, business, audit_schedule="weekly", next_scheduled_audit_at=now - timedelta(hours=1))

    monkeypatch.setattr(seo_audit_service, "run_audit", AsyncMock(side_effect=RuntimeError("boom")))

    started = await seo_schedule_service.run_due_audits(db_session)

    assert started == 0
    assert website.next_scheduled_audit_at > now


@pytest.mark.asyncio
async def test_run_due_audits_does_nothing_when_none_are_due(db_session, business):
    _website(db_session, business, audit_schedule="weekly", next_scheduled_audit_at=datetime.now(timezone.utc) + timedelta(days=1))
    started = await seo_schedule_service.run_due_audits(db_session)
    assert started == 0
