"""
LeadService -- extracted from app/api/leads.py the same way
app/services/support_service.py/booking_service.py were extracted from
their own routers: business logic (dedup-by-email, Mailchimp sync, tag
mapping) lives here, in one testable place, instead of inside the route
handler.

IMPORTANT scope note: Mailchimp sync only ever runs for ONE business
record -- settings.mailchimp_sync_business_id, Mielikkix's own tenant
(the same business PUBLIC_MIELIKKIX_BUSINESS_ID in website/.env points
the marketing site's "Book a Free Demo" form at -- see
scripts/setup_local_mielikkix_business.py). Every other tenant's own
chat-widget leads (apps/dashboard/src/widget/LeadForm.tsx, any other
business_id) are saved to the database exactly as they were before this
feature existed, and are NEVER sent to Mielikkix's own Mailchimp audience
-- that audience is Mielikkix's OWN sales pipeline, not a place to leak a
tenant's own end-customers' contact details.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import mailchimp_service
from .mailchimp_service import MailchimpError, MailchimpRateLimitError, MergeFields
from ..core.config import settings
from ..models.conversation import Conversation
from ..models.lead import Lead
from ..schemas.lead import LeadCreate

logger = logging.getLogger(__name__)

# Machine-friendly tag values (Mailchimp convention: no spaces) -- keys
# match the frontend's <select> option text exactly (see demo.astro's
# INTEREST_OPTIONS/INDUSTRY_OPTIONS). An unrecognized or "Other" value
# just skips the corresponding tag; it's still stored and still synced.
INTEREST_TAGS = {
    "AI Chatbot": "AGENT_CHATBOT",
    "AI Voice Agent": "AGENT_VOICE",
    "Customer Support": "AGENT_SUPPORT",
    "Review & Reputation": "AGENT_REPUTATION",
}
INDUSTRY_TAGS = {
    "Restaurant": "INDUSTRY_RESTAURANT",
    "Retail": "INDUSTRY_RETAIL",
    "Healthcare": "INDUSTRY_HEALTHCARE",
    "Real Estate": "INDUSTRY_REAL_ESTATE",
    "Professional Services": "INDUSTRY_PROFESSIONAL_SERVICES",
}


def is_marketing_business(business_id) -> bool:
    """Whether `business_id` is Mielikkix's own configured marketing
    tenant -- the single gate for every Mailchimp-related behavior in this
    module. False (never synced) whenever mailchimp_sync_business_id isn't
    set, which is the honest default for a fresh checkout with no
    Mailchimp account configured yet."""
    return bool(settings.mailchimp_sync_business_id) and str(business_id) == settings.mailchimp_sync_business_id


def _build_tags(lead: Lead) -> list[str]:
    tags = ["LEAD", "DEMO_REQUESTED", "SOURCE_WEBSITE"]
    if lead.interest in INTEREST_TAGS:
        tags.append(INTEREST_TAGS[lead.interest])
    if lead.industry in INDUSTRY_TAGS:
        tags.append(INDUSTRY_TAGS[lead.industry])
    return tags


def create_or_update_lead(db: Session, body: LeadCreate) -> Lead:
    """Step 2-6 of the lead flow: normalize the email, find/create the
    Lead row, save it. Dedup-by-email (step 3-4: "update the existing
    lead, don't create an unnecessary duplicate") only applies to
    Mielikkix's own marketing business -- see is_marketing_business's
    docstring for why every OTHER tenant keeps today's "always insert a
    new row" behavior unchanged (a tenant's chat widget intentionally
    tracks each inbound conversation as its own lead).
    """
    conversation_id = None
    if body.session_id:
        conv = (
            db.query(Conversation)
            .filter(
                Conversation.session_id == body.session_id,
                Conversation.business_id == body.business_id,
            )
            .first()
        )
        if conv:
            conversation_id = conv.id

    email = body.email.strip().lower() if body.email else None
    marketing_lead = is_marketing_business(body.business_id)

    existing = None
    if marketing_lead and email:
        existing = (
            db.query(Lead)
            .filter(Lead.business_id == body.business_id, Lead.email == email)
            .first()
        )

    if existing:
        lead = existing
        lead.conversation_id = conversation_id or lead.conversation_id
    else:
        lead = Lead(business_id=body.business_id, conversation_id=conversation_id, status="new")
        db.add(lead)

    lead.name = body.name
    lead.email = email
    lead.phone = body.phone
    lead.message = body.message
    lead.first_name = body.first_name
    lead.last_name = body.last_name
    lead.company = body.company
    lead.industry = body.industry
    lead.interest = body.interest
    if marketing_lead:
        # Only the marketing flow gets a default source -- a generic
        # tenant's chat-widget lead has never set this column and
        # shouldn't start now just because this feature shipped.
        lead.source = body.source or "WEBSITE"
        if marketing_lead and lead.status == "new":
            # Mirrors the marketing lifecycle's first real stage (see this
            # integration's design brief, "Prepare the lead model for this
            # lifecycle") without touching the dashboard's existing
            # new/contacted/won/lost vocabulary for generic tenant leads
            # (apps/dashboard/src/dashboard/pages/LeadsPage.tsx) -- that
            # UI still renders this fine, just without a dedicated color.
            lead.status = "DEMO_REQUESTED"
    # One-way: explicit consent (checkbox checked) always records
    # marketing_consent=True + a first-consented-at timestamp. An
    # UNCHECKED box on a later resubmission is deliberately NOT treated
    # as "consent withdrawn" -- it's simply the absence of a new consent
    # action, and must never downgrade previously recorded consent back
    # to False or erase marketing_consent_at (see this integration's
    # add-on brief §8). Withdrawing consent is a distinct, explicit
    # action a future feature would implement on purpose, not an
    # incidental side effect of requesting another demo.
    if body.marketing_consent:
        lead.marketing_consent = True
        if not lead.marketing_consent_at:
            lead.marketing_consent_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(lead)
    return lead


async def sync_lead_to_mailchimp(db: Session, lead: Lead) -> None:
    """Best-effort: never raises past this function. A Mailchimp outage or
    missing configuration must not turn an already-saved lead into a
    failed request -- see this integration's design brief, 'Mailchimp
    failure does not lose a lead.' Failures are logged and leave
    mailchimp_synced False for a later manual retry
    (POST /api/leads/{id}/sync-mailchimp)."""
    if not lead.email:
        logger.info("Mailchimp sync skipped for lead %s: no email on file", lead.id)
        return
    if not mailchimp_service.is_configured():
        logger.info("Mailchimp sync skipped for lead %s: Mailchimp not configured", lead.id)
        return

    merge_fields = MergeFields(
        first_name=lead.first_name or "",
        last_name=lead.last_name or "",
        company=lead.company or "",
        phone=lead.phone or "",
        industry=lead.industry or "",
        interest=lead.interest or "",
    )

    try:
        contact_id = await mailchimp_service.add_or_update_contact(
            lead.email, merge_fields, lead.marketing_consent
        )
        await mailchimp_service.add_tags_to_contact(lead.email, _build_tags(lead))
    except MailchimpRateLimitError:
        logger.warning("Mailchimp sync deferred for lead %s: rate limited (429)", lead.id)
        return
    except MailchimpError as exc:
        logger.warning("Mailchimp sync failed for lead %s: %s", lead.id, exc)
        return

    logger.info("Mailchimp synchronization successful for lead %s", lead.id)
    lead.mailchimp_synced = True
    lead.mailchimp_contact_id = contact_id
    lead.mailchimp_last_synced_at = datetime.now(timezone.utc)
    db.commit()
