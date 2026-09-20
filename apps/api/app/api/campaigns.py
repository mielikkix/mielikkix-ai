"""Email Marketing Agent: campaign HTTP wrapper. See app/services/
campaign_service.py for the actual logic -- this file only maps HTTP <->
that service, the same split agents_reviews.py/agents_seo.py use for their
own services. Routes mounted under /api/businesses/me/campaigns, same
"always resolves tenant from the session cookie" convention every other
/me route (mailchimp_oauth.py, businesses.py) uses.

Mailchimp is the system of record for the campaign itself (see campaign_
service.py's own module docstring) -- send/schedule/test here are thin,
fast calls to Mailchimp's own Campaigns API (create + set content + one
action), not a slow per-recipient loop, so unlike this feature's abandoned
Option B design, none of these routes need FastAPI's BackgroundTasks.

Every route requires the "email_marketing" agent entitlement, checked via
agent_access_service.require_agent_access -- the exact same call
mailchimp_oauth.py's own /authorize already uses (see that file). Email
Marketing is purchased separately from the chat-widget plan, like every
other Force agent -- see apps/api/app/core/agent_catalog.py and
apps/agents/seo-audit/CLAUDE.md's "Standalone agent billing" decision.
"""

from dataclasses import asdict
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.dependencies import get_current_business, get_current_user
from ..models.business import Business
from ..models.campaign import Campaign
from ..models.user import User
from ..services import agent_access_service, campaign_service

router = APIRouter(prefix="/api/businesses/me/campaigns", tags=["email-marketing-campaigns"])


def _require_enabled(db: Session, business: Business) -> None:
    agent_access_service.require_agent_access(db, business, "email_marketing")


class _CampaignOut(BaseModel):
    id: str
    mailchimp_audience_id: Optional[str]
    mailchimp_audience_name: Optional[str]
    mailchimp_campaign_id: Optional[str]
    subject: Optional[str]
    from_name: Optional[str]
    from_email: Optional[str]
    reply_to: Optional[str]
    body_html: Optional[str]
    status: str
    scheduled_at: Optional[str]
    sent_at: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]

    @classmethod
    def from_orm_campaign(cls, campaign: Campaign) -> "_CampaignOut":
        return cls(
            id=str(campaign.id),
            mailchimp_audience_id=campaign.mailchimp_audience_id,
            mailchimp_audience_name=campaign.mailchimp_audience_name,
            mailchimp_campaign_id=campaign.mailchimp_campaign_id,
            subject=campaign.subject,
            from_name=campaign.from_name,
            from_email=campaign.from_email,
            reply_to=campaign.reply_to,
            body_html=campaign.body_html,
            status=campaign.status,
            scheduled_at=campaign.scheduled_at.isoformat() if campaign.scheduled_at else None,
            sent_at=campaign.sent_at.isoformat() if campaign.sent_at else None,
            created_at=campaign.created_at.isoformat() if campaign.created_at else None,
            updated_at=campaign.updated_at.isoformat() if campaign.updated_at else None,
        )


class _CampaignReportOut(BaseModel):
    emails_sent: int
    opens_total: int
    unique_opens: int
    open_rate: float
    click_rate: float
    unsubscribed: int
    hard_bounces: int
    soft_bounces: int


@router.get("", response_model=list[_CampaignOut])
def list_campaigns(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(db, business)
    campaigns = campaign_service.list_campaigns(db, str(current_user.business_id), status=status)
    return [_CampaignOut.from_orm_campaign(c) for c in campaigns]


class _CreateCampaignRequest(BaseModel):
    subject: Optional[str] = None
    from_name: Optional[str] = None
    from_email: Optional[str] = None
    reply_to: Optional[str] = None
    body_html: Optional[str] = None
    mailchimp_audience_id: Optional[str] = None
    mailchimp_audience_name: Optional[str] = None


@router.post("", response_model=_CampaignOut)
def create_campaign(
    body: _CreateCampaignRequest,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(db, business)
    campaign = campaign_service.create_draft(db, str(current_user.business_id), **body.model_dump())
    return _CampaignOut.from_orm_campaign(campaign)


@router.get("/{campaign_id}", response_model=_CampaignOut)
def get_campaign(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(db, business)
    try:
        campaign = campaign_service.get_campaign(db, str(current_user.business_id), campaign_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _CampaignOut.from_orm_campaign(campaign)


class _UpdateCampaignRequest(BaseModel):
    subject: Optional[str] = None
    from_name: Optional[str] = None
    from_email: Optional[str] = None
    reply_to: Optional[str] = None
    body_html: Optional[str] = None
    mailchimp_audience_id: Optional[str] = None
    mailchimp_audience_name: Optional[str] = None


@router.patch("/{campaign_id}", response_model=_CampaignOut)
def update_campaign(
    campaign_id: str,
    body: _UpdateCampaignRequest,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(db, business)
    # exclude_unset -- a PATCH only ever touches fields the caller actually
    # sent, same reasoning as every other partial-update endpoint in this
    # codebase; a field the caller omitted must never be overwritten with None.
    fields = body.model_dump(exclude_unset=True)
    try:
        campaign = campaign_service.update_draft(db, str(current_user.business_id), campaign_id, **fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _CampaignOut.from_orm_campaign(campaign)


@router.post("/{campaign_id}/approve", response_model=_CampaignOut)
def approve_campaign(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(db, business)
    try:
        campaign = campaign_service.approve_campaign(db, str(current_user.business_id), campaign_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _CampaignOut.from_orm_campaign(campaign)


class _SendTestEmailRequest(BaseModel):
    test_emails: list[str]


@router.post("/{campaign_id}/test", response_model=_CampaignOut)
async def send_test_email(
    campaign_id: str,
    body: _SendTestEmailRequest,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """Sends a real Mailchimp test email so a human can review actual
    rendered content before approving/sending -- never the real send."""
    _require_enabled(db, business)
    try:
        campaign = await campaign_service.send_test_email(db, str(current_user.business_id), campaign_id, body.test_emails)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except campaign_service.CampaignSendError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _CampaignOut.from_orm_campaign(campaign)


@router.post("/{campaign_id}/send", response_model=_CampaignOut)
async def send_campaign(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """Triggers an immediate, real send through Mailchimp. This creates
    (or reuses) the real Mailchimp campaign, pushes current content, and
    calls Mailchimp's own actions/send -- a few fast sequential API calls,
    not a per-recipient loop this app runs itself (see campaign_service.py's
    own module docstring), so this is a plain synchronous request/response,
    not a background task."""
    _require_enabled(db, business)
    try:
        campaign = await campaign_service.send_campaign(db, str(current_user.business_id), campaign_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except campaign_service.CampaignSendError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _CampaignOut.from_orm_campaign(campaign)


class _ScheduleCampaignRequest(BaseModel):
    scheduled_at: datetime


@router.post("/{campaign_id}/schedule", response_model=_CampaignOut)
async def schedule_campaign(
    campaign_id: str,
    body: _ScheduleCampaignRequest,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """Schedules the campaign on Mailchimp itself -- Mailchimp fires the
    actual send at scheduled_at; nothing in this app needs to."""
    _require_enabled(db, business)
    try:
        campaign = await campaign_service.schedule_campaign(db, str(current_user.business_id), campaign_id, body.scheduled_at)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except campaign_service.CampaignSendError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _CampaignOut.from_orm_campaign(campaign)


@router.get("/{campaign_id}/report", response_model=_CampaignReportOut)
async def get_campaign_report(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """Send results read LIVE from Mailchimp's own /reports endpoint --
    there is no local per-recipient table to aggregate (see campaign_
    service.py's own module docstring). Also refreshes this campaign's
    cached status as a side effect (see campaign_service.
    refresh_campaign_status) -- opening this view is what notices a
    "sending" -> "sent" transition, since no webhook/poller runs in the
    background."""
    _require_enabled(db, business)
    try:
        report = await campaign_service.get_campaign_report(db, str(current_user.business_id), campaign_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except campaign_service.CampaignSendError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _CampaignReportOut(**asdict(report))
