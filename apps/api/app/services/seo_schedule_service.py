"""Recurring audit scheduling (Stage 15 of apps/agents/seo-audit/CLAUDE.md's
"Professional tier roadmap"). This is a narrow, single-purpose scheduler
for one recurring task -- NOT the general "shared job queue" the root
CLAUDE.md still calls aspirational; that's still true for everything else
in this codebase. See app/main.py's lifespan for where this gets ticked.

Deliberately simple: an in-process APScheduler tick (every
CHECK_INTERVAL_MINUTES) that finds SeoWebsite rows whose
next_scheduled_audit_at has passed and starts a fresh audit for each,
rescheduling forward by that website's own interval. This follows the same
"modular process, not a new container" rule every other background task in
this codebase already follows (root CLAUDE.md convention #4) -- it runs
inside the same FastAPI process as everything else, not a separate worker.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..models.seo_website import SeoWebsite
from . import seo_audit_service

SCHEDULE_INTERVALS: dict[str, timedelta] = {
    "weekly": timedelta(days=7),
    "monthly": timedelta(days=30),
}

# How often the in-process scheduler checks for due websites -- not how
# often any one website gets audited (that's SCHEDULE_INTERVALS, set per
# website). A short tick just means a due audit starts promptly rather than
# sitting queued for hours; it costs one cheap DB query when nothing is due.
CHECK_INTERVAL_MINUTES = 15


class InvalidScheduleError(Exception):
    """Raised for an interval string that isn't a key of SCHEDULE_INTERVALS
    (or None, which is the valid "turn scheduling off" value) -- the API
    layer turns this into a 400, same pattern as this agent's other
    domain-error-to-HTTP-status translations (e.g. AuditComparisonError)."""


def set_schedule(db: Session, website: SeoWebsite, interval: Optional[str]) -> SeoWebsite:
    """interval=None turns scheduling off for this website (the default
    state). Setting a new interval always recomputes next_scheduled_audit_at
    as now + that interval -- changing from weekly to monthly (or back)
    restarts the countdown rather than trying to prorate the old one, the
    same "don't guess, just recompute from what's actually true now" rule
    this agent's analyzers already follow."""
    if interval is not None and interval not in SCHEDULE_INTERVALS:
        raise InvalidScheduleError(f"Unknown schedule interval: {interval!r}")

    website.audit_schedule = interval
    website.next_scheduled_audit_at = (
        datetime.now(timezone.utc) + SCHEDULE_INTERVALS[interval] if interval else None
    )
    db.commit()
    db.refresh(website)
    return website


def due_websites(db: Session, now: Optional[datetime] = None) -> list[SeoWebsite]:
    """Websites with an active schedule whose next run has come due. Real
    DB state only -- never a guess at what "should" be due."""
    now = now or datetime.now(timezone.utc)
    return (
        db.query(SeoWebsite)
        .filter(SeoWebsite.audit_schedule.isnot(None), SeoWebsite.next_scheduled_audit_at <= now)
        .all()
    )


async def run_due_audits(db: Session) -> int:
    """Starts a fresh audit for every currently-due website and reschedules
    each one forward by its own interval, so a website's cadence is
    self-sustaining without a human re-triggering it. Returns how many
    audits were started (0 is the normal case on most ticks -- not an
    error, most ticks find nothing due).

    One website's audit failing to start doesn't stop the rest -- same
    "one bad item doesn't abort the others" rule run_audit itself already
    follows for individual crawled pages."""
    started = 0
    for website in due_websites(db):
        try:
            audit = seo_audit_service.create_audit(db, website)
            await seo_audit_service.run_audit(str(audit.id))
            started += 1
        except Exception:
            pass
        finally:
            # Reschedule regardless of whether the audit itself succeeded --
            # a website stuck failing every audit shouldn't also spam retries
            # faster than its own configured cadence.
            interval = SCHEDULE_INTERVALS.get(website.audit_schedule)
            if interval is not None:
                website.next_scheduled_audit_at = datetime.now(timezone.utc) + interval
                db.commit()
    return started
