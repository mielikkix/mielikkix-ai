import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from ..core.database import Base


class Campaign(Base):
    """Email Marketing Agent's core record -- one row per draft/sent
    campaign. Mailchimp is the SYSTEM OF RECORD for the campaign itself
    here: it drafts (content), sends, and reports on it natively via its
    own Campaigns API (see app/integrations/mailchimp_client.py's
    create_campaign/set_campaign_content/send_campaign/schedule_campaign/
    get_campaign/get_campaign_report). This table is a local draft
    workspace plus a thin cache of Mailchimp's own state -- it never
    tracks individual recipients or delivery itself (there is no
    CampaignSend table; that per-recipient tracking belongs to Mailchimp's
    own /reports endpoint, read live via campaign_service.get_campaign_
    report). Mirrors models/review.py's own shape/reasoning (tenant-scoped,
    free-text status, human-approval workflow) -- read that file's
    comments first if this is your first time in either.
    """

    __tablename__ = "campaigns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False, index=True)

    # The Mailchimp audience this campaign targets -- copied from the
    # business's MailchimpConnection at campaign-create/update time (not a
    # live FK to that row), same "cache for display, never trusted over the
    # real source" reasoning MailchimpConnection.audience_name itself
    # already uses. Required before this campaign can actually be created
    # on Mailchimp (see campaign_service.approve_campaign).
    mailchimp_audience_id = Column(Text, nullable=True)
    mailchimp_audience_name = Column(Text, nullable=True)

    # Mailchimp's own campaign id -- null until campaign_service.send_
    # campaign() actually creates this campaign on Mailchimp (create_
    # campaign + set_campaign_content). Required for every call after
    # that: send_test_email, send_campaign/schedule_campaign, get_campaign,
    # get_campaign_report all take this, not this row's own `id`.
    mailchimp_campaign_id = Column(Text, nullable=True)

    subject = Column(Text, nullable=True)
    from_name = Column(Text, nullable=True)
    # Stored for reference/display only -- Mailchimp's Campaigns API has no
    # per-campaign "from_email" field (verified against Mailchimp's own
    # settings schema; the actual sending address is controlled by the
    # audience's own "Campaign Defaults", configured inside Mailchimp
    # itself against a verified domain). This value is NEVER sent to
    # Mailchimp -- see mailchimp_client.py's create_campaign docstring.
    from_email = Column(Text, nullable=True)
    reply_to = Column(Text, nullable=True)
    body_html = Column(Text, nullable=True)

    # "draft" | "approved" are this app's own LOCAL-ONLY states, before
    # any Mailchimp campaign exists -- the human-approval gate this agent
    # requires (see apps/agents/email-marketing/CLAUDE.md: "A human
    # reviews/approves each campaign before it sends") happens entirely
    # here, before Mailchimp is ever touched. Every status after that is a
    # direct passthrough of Mailchimp's OWN documented campaign status
    # value, refreshed live via get_campaign()/get_campaign_report()
    # rather than a parallel vocabulary invented here: "save" (created on
    # Mailchimp, not yet sent/scheduled) | "paused" | "schedule" |
    # "sending" | "sent" | "canceled" | "canceling" | "archived". Free
    # text, not a DB enum, same reasoning Review.priority/response_status
    # already gives (Mailchimp could add a new status value without this
    # needing a migration).
    status = Column(Text, nullable=False, default="draft")

    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    business = relationship("Business")
