import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from ..core.database import Base


class MailchimpConnection(Base):
    """A business's own connected Mailchimp account -- the per-tenant Email
    Marketing Agent connection, NOT to be confused with the single global
    settings.mailchimp_* config (app/services/mailchimp_service.py) that
    syncs Mielikkix's OWN marketing leads to Mielikkix's OWN Mailchimp
    account. Those two are deliberately separate systems: this table is
    never read by mailchimp_service.py/lead_service.py, and that flow never
    reads this table. One row per business (unique business_id). Mirrors
    models/calendar_connection.py's and models/review_connection.py's own
    shape/reasoning -- read those files' comments first if this is your
    first time in any of the three.

    Mailchimp's OAuth is genuinely different from Google's (verified
    against Mailchimp's own OAuth guide, not assumed): the access token
    never expires and there is no refresh token, so there is exactly one
    credential to store, not a refresh token to rotate. In exchange,
    Mailchimp requires a separate post-exchange call (GET
    https://login.mailchimp.com/oauth2/metadata) to learn which data center
    ("server prefix", e.g. "us21") the account lives on -- every subsequent
    Marketing API call has to go to https://{server_prefix}.api.mailchimp.com,
    unlike Google's single fixed API host.
    """

    __tablename__ = "mailchimp_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(
        UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False, unique=True, index=True
    )
    # Encrypted at rest via core/encryption.py -- same reasoning as
    # CalendarConnection.refresh_token_encrypted / ReviewConnection.
    # refresh_token_encrypted: this grants ongoing access to a business's
    # real Mailchimp account, so it is never stored or logged as plaintext.
    # Read with core/encryption.decrypt() immediately before use, never
    # persisted decrypted anywhere. Named access_token (not refresh_token)
    # because that is the only token Mailchimp's OAuth actually issues.
    access_token_encrypted = Column(Text, nullable=False)
    # The data center prefix from the OAuth metadata call (e.g. "us21") --
    # required to build the API base URL for every subsequent call. Not
    # secret, but only meaningful paired with the access token above.
    server_prefix = Column(Text, nullable=False)
    # Both best-effort, captured once during the OAuth callback from the
    # metadata response so the dashboard can show "Connected as: ..."
    # without a live Mailchimp call just to render the page -- same
    # reasoning as ReviewConnection.google_account_email. Mailchimp's own
    # OAuth guide only documents `dc` as a guaranteed metadata field, so
    # these two are read defensively and left null if genuinely absent
    # rather than assumed to always be present.
    account_name = Column(Text, nullable=True)
    login_email = Column(Text, nullable=True)
    # The tenant's chosen Mailchimp audience (list) -- null until they
    # finish the "select an audience" step, which is a real, separate
    # action after OAuth connects (unlike Calendar's "primary" default,
    # Mailchimp accounts commonly have zero, one, or several audiences with
    # no meaningful default). audience_name is cached purely for display
    # (dashboard "Selected audience: ..."), never trusted as the source of
    # truth over audience_id.
    audience_id = Column(Text, nullable=True)
    audience_name = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    connected_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
