"""Email Marketing Agent: campaign drafting, approval, and sending.
Mailchimp is the SYSTEM OF RECORD for the campaign itself -- this module
drafts locally (subject/from_name/from_email/reply_to/body_html against a
Campaign row), then on send/schedule creates the real campaign on
Mailchimp (create_campaign + set_campaign_content) and lets Mailchimp
actually deliver and track it (send_campaign/schedule_campaign,
get_campaign, get_campaign_report). There is no local per-recipient
send loop and no CampaignSend table -- Mailchimp's own /reports endpoint
is the only source of delivery/open/click data, read live, never
aggregated from rows this app wrote itself.

Mirrors the shape review_service.py already uses for its own draft ->
approve -> publish human-approval workflow (plain importable functions,
called by app/api/campaigns.py's thin HTTP wrapper, ValueError for state
errors a caller maps to 400, a dedicated exception for an upstream call
that was actually attempted and failed) -- read that file first if this is
your first time here.

Status lifecycle: "draft" and "approved" are this app's own LOCAL-ONLY
states, before any Mailchimp campaign exists -- the human-approval gate
this agent requires (apps/agents/email-marketing/CLAUDE.md: "A human
reviews/approves each campaign before it sends") happens entirely here.
Every status after that is Mailchimp's OWN campaign status, copied
straight through (see models/campaign.py's own comment on the full
vocabulary) rather than invented separately.

No job queue or webhook receiver exists anywhere in this codebase (see
this feature's own audit). Status updates therefore come from POLLING,
not a webhook: refresh_campaign_status() live-queries Mailchimp's
GET /campaigns/{id}, and is called from GET /{campaign_id}/report (see
campaigns.py) -- opening a campaign's report is what picks up a
"sending" -> "sent" transition. A campaign's list/detail view does NOT
poll on every request (that would mean one live Mailchimp call per row
rendered); its status may lag reality until the report view is opened
or another send/schedule action runs. A real Mailchimp webhook
(https://mailchimp.com/developer/marketing/docs/webhooks/) would remove
this lag but is out of scope for this phase.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..integrations.email_marketing_providers import CampaignReport, EmailMarketingProviderError, get_email_marketing_provider
from ..models.campaign import Campaign

logger = logging.getLogger(__name__)

DRAFT_FIELDS = ("subject", "from_name", "from_email", "reply_to", "body_html", "mailchimp_audience_id", "mailchimp_audience_name")

# Local-only statuses (no Mailchimp campaign exists yet) vs. Mailchimp's own
# vocabulary, copied verbatim once a campaign is created there -- see this
# module's own docstring and models/campaign.py's status comment.
_PRE_MAILCHIMP_STATUSES = ("draft", "approved")
# Mailchimp states in which a campaign's content/settings can still be
# changed and (re)sent -- "save" (created, untouched since) and "paused"
# (Mailchimp's own state for a schedule/send that was interrupted or
# manually paused). send_campaign()/schedule_campaign()/send_test_email()
# are all safe to call again from any of these without creating a
# duplicate Mailchimp campaign.
_RESENDABLE_STATUSES = ("approved", "save", "paused")


class CampaignSendError(Exception):
    """Raised when a Mailchimp call this module made on the tenant's behalf
    (create/content/test/send/schedule/report) actually failed -- no
    Mailchimp connection, the connection/audience no longer exists, or the
    live API call itself errored. Distinct from ValueError (a state error:
    this campaign was never eligible for the requested action in the
    first place) -- callers (campaigns.py) map this to a 502, since the
    request was valid and simply needs a retry once the underlying issue
    clears."""


def _parse_mailchimp_datetime(value: Optional[str]) -> Optional[datetime]:
    """Mailchimp's own timestamps are ISO 8601 (e.g.
    "2026-04-01T14:00:00+00:00") -- read defensively (never trust an
    upstream string blindly) rather than letting a malformed/unexpected
    value raise and break an otherwise-successful status refresh."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def create_draft(
    db: Session,
    business_id: str,
    subject: Optional[str] = None,
    from_name: Optional[str] = None,
    from_email: Optional[str] = None,
    reply_to: Optional[str] = None,
    body_html: Optional[str] = None,
    mailchimp_audience_id: Optional[str] = None,
    mailchimp_audience_name: Optional[str] = None,
) -> Campaign:
    """A brand-new local draft -- nothing is created on Mailchimp yet.
    Every field is optional here -- a human may start a campaign with just
    a subject and fill in the rest before approving (approve_campaign() is
    what actually enforces everything required is present, not this)."""
    campaign = Campaign(
        business_id=business_id,
        subject=subject,
        from_name=from_name,
        from_email=from_email,
        reply_to=reply_to,
        body_html=body_html,
        mailchimp_audience_id=mailchimp_audience_id,
        mailchimp_audience_name=mailchimp_audience_name,
        status="draft",
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    logger.info("campaign_created campaign_id=%s business_id=%s", campaign.id, business_id)
    return campaign


def update_draft(db: Session, business_id: str, campaign_id: str, **fields) -> Campaign:
    """Edits an existing draft in place. Only callable while status ==
    "draft" -- once approved (and especially once a real Mailchimp
    campaign exists), changing subject/content here would silently
    diverge from what Mailchimp actually has; send_campaign() is what
    pushes edited content to Mailchimp for an "approved"/"save"/"paused"
    campaign, not this. Unknown keys in `fields` are ignored rather than
    raising, so a caller can pass a partial update dict straight from a
    request body without pre-filtering it."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.business_id == business_id).first()
    if campaign is None:
        raise ValueError("Campaign not found")
    if campaign.status != "draft":
        raise ValueError(f"Campaign is {campaign.status!r} -- only a draft campaign can be edited")

    for key, value in fields.items():
        if key in DRAFT_FIELDS:
            setattr(campaign, key, value)

    db.commit()
    db.refresh(campaign)
    return campaign


def list_campaigns(db: Session, business_id: str, status: Optional[str] = None) -> list[Campaign]:
    query = db.query(Campaign).filter(Campaign.business_id == business_id)
    if status:
        query = query.filter(Campaign.status == status)
    return query.order_by(Campaign.created_at.desc()).all()


def get_campaign(db: Session, business_id: str, campaign_id: str) -> Campaign:
    """A plain local read -- does NOT live-poll Mailchimp (see this
    module's own docstring on why: one call per row would make listing/
    viewing campaigns as slow as the slowest Mailchimp response). Status
    may lag reality until refresh_campaign_status() runs (via GET
    .../report, or another send/schedule action)."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.business_id == business_id).first()
    if campaign is None:
        raise ValueError("Campaign not found")
    return campaign


def approve_campaign(db: Session, business_id: str, campaign_id: str) -> Campaign:
    """Marks a draft ready to send -- does NOT create or send anything on
    Mailchimp yet (matches review_service.approve_response's own "approve
    is not publish" separation). `reply_to` is required (Mailchimp always
    needs a genuine reply address for a campaign); `from_email` is
    deliberately NOT required here even though it's a real field on this
    model -- see Campaign.from_email's own comment: Mailchimp has no way
    to use it, so requiring it before approval would imply it does
    something it doesn't."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.business_id == business_id).first()
    if campaign is None:
        raise ValueError("Campaign not found")
    if campaign.status != "draft":
        raise ValueError(f"Campaign is {campaign.status!r} -- only a draft campaign can be approved")

    missing = [
        field
        for field, value in (
            ("subject", campaign.subject),
            ("body_html", campaign.body_html),
            ("reply_to", campaign.reply_to),
            ("mailchimp_audience_id", campaign.mailchimp_audience_id),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"Cannot approve -- missing required field(s): {', '.join(missing)}")

    campaign.status = "approved"
    db.commit()
    db.refresh(campaign)
    logger.info("campaign_approved campaign_id=%s", campaign_id)
    return campaign


def _get_provider_or_raise(db: Session, business_id: str):
    provider = get_email_marketing_provider("mailchimp", db, business_id)
    if provider is None:
        raise CampaignSendError("No Mailchimp connection for this business -- connect Mailchimp first")
    return provider


async def _ensure_created_on_mailchimp(db: Session, campaign: Campaign, provider) -> None:
    """Creates the real Mailchimp campaign the first time this campaign is
    sent/scheduled/test-sent; a retry (campaign.mailchimp_campaign_id
    already set, status still one of _RESENDABLE_STATUSES) reuses the
    existing Mailchimp campaign instead of creating a duplicate. Always
    (re)pushes body_html -- a human may have edited content between an
    earlier failed attempt and this retry, and Mailchimp itself has no way
    to know that without this call."""
    try:
        if not campaign.mailchimp_campaign_id:
            info = await provider.create_campaign(
                campaign.mailchimp_audience_id, campaign.subject, from_name=campaign.from_name, reply_to=campaign.reply_to
            )
            campaign.mailchimp_campaign_id = info.id
            db.commit()
        await provider.set_campaign_content(campaign.mailchimp_campaign_id, campaign.body_html)
    except EmailMarketingProviderError as exc:
        raise CampaignSendError(f"Couldn't create/update this campaign on Mailchimp: {exc}") from exc


def _check_sendable(campaign: Campaign) -> None:
    if campaign.status not in _RESENDABLE_STATUSES:
        raise ValueError(
            f"Campaign is {campaign.status!r} -- only an approved campaign (or one still saved/paused on "
            "Mailchimp) can be sent, scheduled, or test-sent"
        )
    missing = [
        field
        for field, value in (
            ("subject", campaign.subject),
            ("body_html", campaign.body_html),
            ("reply_to", campaign.reply_to),
            ("mailchimp_audience_id", campaign.mailchimp_audience_id),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"Cannot send -- missing required field(s): {', '.join(missing)}")


async def send_test_email(db: Session, business_id: str, campaign_id: str, test_emails: list[str]) -> Campaign:
    """Sends a real Mailchimp test message to the given addresses so a
    human can review actual rendered content before approving/sending for
    real -- never counts as the real send (campaign.status is untouched
    here). Creates the campaign on Mailchimp on first use, same as
    send_campaign/schedule_campaign (see _ensure_created_on_mailchimp)."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.business_id == business_id).first()
    if campaign is None:
        raise ValueError("Campaign not found")
    _check_sendable(campaign)
    if not test_emails:
        raise ValueError("test_emails must include at least one address")

    provider = _get_provider_or_raise(db, business_id)
    await _ensure_created_on_mailchimp(db, campaign, provider)
    try:
        await provider.send_test_email(campaign.mailchimp_campaign_id, test_emails)
    except EmailMarketingProviderError as exc:
        raise CampaignSendError(f"Mailchimp test send failed: {exc}") from exc

    logger.info("campaign_test_sent campaign_id=%s recipient_count=%s", campaign_id, len(test_emails))
    return campaign


async def send_campaign(db: Session, business_id: str, campaign_id: str) -> Campaign:
    """The real, immediate send. Callable on "approved" (first real send)
    or "save"/"paused" (a Mailchimp campaign already exists from an
    earlier attempt or test send -- see _RESENDABLE_STATUSES) -- both
    reuse _ensure_created_on_mailchimp so this never creates a duplicate
    Mailchimp campaign for the same row. Ends by reading the campaign's
    real status back from Mailchimp (immediately after actions/send this
    is "sending") rather than assuming a local "sent" -- Mailchimp's own
    status is always the source of truth (see this module's own docstring)."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.business_id == business_id).first()
    if campaign is None:
        raise ValueError("Campaign not found")
    _check_sendable(campaign)

    provider = _get_provider_or_raise(db, business_id)
    await _ensure_created_on_mailchimp(db, campaign, provider)
    try:
        await provider.send_campaign(campaign.mailchimp_campaign_id)
        info = await provider.get_campaign(campaign.mailchimp_campaign_id)
    except EmailMarketingProviderError as exc:
        raise CampaignSendError(f"Mailchimp send failed: {exc}") from exc

    campaign.status = info.status
    campaign.sent_at = _parse_mailchimp_datetime(info.send_time) or datetime.now(timezone.utc)
    db.commit()
    db.refresh(campaign)
    logger.info("campaign_sent campaign_id=%s mailchimp_campaign_id=%s status=%s", campaign_id, campaign.mailchimp_campaign_id, campaign.status)
    return campaign


async def schedule_campaign(db: Session, business_id: str, campaign_id: str, scheduled_at: datetime) -> Campaign:
    """Schedules the campaign to send at a future time -- Mailchimp itself
    fires the actual send at that time; no local scheduler/cron is needed
    for this to work (unlike this app's abandoned Option B design, where
    nothing existed to fire a locally-scheduled send). Same creation/reuse
    rule as send_campaign (see _ensure_created_on_mailchimp)."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.business_id == business_id).first()
    if campaign is None:
        raise ValueError("Campaign not found")
    _check_sendable(campaign)
    if scheduled_at <= datetime.now(timezone.utc):
        raise ValueError("scheduled_at must be in the future -- use send_campaign for an immediate send")

    provider = _get_provider_or_raise(db, business_id)
    await _ensure_created_on_mailchimp(db, campaign, provider)
    try:
        await provider.schedule_campaign(campaign.mailchimp_campaign_id, scheduled_at)
        info = await provider.get_campaign(campaign.mailchimp_campaign_id)
    except EmailMarketingProviderError as exc:
        raise CampaignSendError(f"Mailchimp schedule failed: {exc}") from exc

    campaign.status = info.status  # "schedule"
    campaign.scheduled_at = scheduled_at
    db.commit()
    db.refresh(campaign)
    logger.info("campaign_scheduled campaign_id=%s scheduled_at=%s", campaign_id, scheduled_at)
    return campaign


async def refresh_campaign_status(db: Session, business_id: str, campaign_id: str) -> Campaign:
    """Live-polls Mailchimp for this campaign's real status and updates the
    local cache. Best-effort: a campaign with no Mailchimp campaign yet, no
    active Mailchimp connection, or a transient upstream failure all just
    return the campaign with its existing (possibly stale) local status
    rather than raising -- this is a background refresh, not an action the
    caller is trying to perform, so it should never turn "view a campaign"
    into an error page. Called from GET /{campaign_id}/report (see
    campaigns.py) so opening a campaign's report is what actually notices
    a "sending" -> "sent" transition (see this module's own docstring on
    why polling, not a webhook, is v1's mechanism)."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.business_id == business_id).first()
    if campaign is None:
        raise ValueError("Campaign not found")
    if not campaign.mailchimp_campaign_id:
        return campaign

    provider = get_email_marketing_provider("mailchimp", db, business_id)
    if provider is None:
        return campaign

    try:
        info = await provider.get_campaign(campaign.mailchimp_campaign_id)
    except EmailMarketingProviderError as exc:
        logger.warning("campaign_status_refresh_failed campaign_id=%s error=%s", campaign_id, exc)
        return campaign

    campaign.status = info.status
    if info.send_time:
        campaign.sent_at = _parse_mailchimp_datetime(info.send_time)
    db.commit()
    db.refresh(campaign)
    return campaign


async def get_campaign_report(db: Session, business_id: str, campaign_id: str) -> CampaignReport:
    """Aggregated send results, read LIVE from Mailchimp's own /reports
    endpoint -- there is no local per-recipient table to aggregate
    instead (see this module's own docstring). Refreshes the local status
    cache first (see refresh_campaign_status) so a campaign that just
    finished sending is correctly recognized as reportable without
    requiring a separate manual refresh first."""
    campaign = await refresh_campaign_status(db, business_id, campaign_id)
    if campaign.status not in ("sending", "sent"):
        raise ValueError(f"Campaign is {campaign.status!r} -- reports are only available once a campaign has been sent")
    if not campaign.mailchimp_campaign_id:
        raise ValueError("Campaign hasn't been created on Mailchimp yet")

    provider = _get_provider_or_raise(db, business_id)
    try:
        return await provider.get_campaign_report(campaign.mailchimp_campaign_id)
    except EmailMarketingProviderError as exc:
        raise CampaignSendError(f"Couldn't fetch this campaign's report from Mailchimp: {exc}") from exc
