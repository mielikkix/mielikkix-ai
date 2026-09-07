import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from ..core.database import Base


class ReviewConnection(Base):
    """A business's own connected Google Business Profile location -- the
    real per-tenant counterpart to the single global settings.google_reviews_*
    config the mock/legacy path uses. One row per business (unique
    business_id): a business either has no connection yet
    (review_platforms/__init__.get_review_platform treats that as "not
    configured for this business", never falling back to Mielikkix's own
    settings.google_reviews_* values) or has exactly one. Mirrors
    models/calendar_connection.py's own shape/reasoning -- read that file's
    comments first if this is your first time in either.
    """

    __tablename__ = "review_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(
        UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False, unique=True, index=True
    )
    # Encrypted at rest via core/encryption.py -- same reasoning as
    # CalendarConnection.refresh_token_encrypted: this grants ongoing
    # access to a business's real Google Business Profile, so it's never
    # stored or logged as plaintext. Read with core/encryption.decrypt()
    # immediately before use, never persisted decrypted anywhere.
    refresh_token_encrypted = Column(Text, nullable=False)
    # Unlike Calendar (always "primary"), a Business Profile connection
    # genuinely needs an operator-chosen account AND location -- there's no
    # equivalent default. account_id is set as soon as the OAuth callback
    # succeeds (a login with zero Business Profile accounts is treated as a
    # failed connection, see review_oauth.py's callback()); location_id
    # stays null for a business with more than one location under that
    # account until they finish the separate "choose your location" step
    # (POST .../select-location) -- a real, first-class "connected, needs a
    # location" state, not a hack. get_review_platform() (review_platforms/
    # __init__.py) treats a connection with location_id still null the same
    # as no connection at all.
    account_id = Column(Text, nullable=False)
    location_id = Column(Text, nullable=True)
    # Both best-effort, captured once during the OAuth callback so the
    # dashboard can show "Connected as: <email> -- <location>" without
    # needing to decrypt the token or make a live Google call just to
    # render the Settings/Reviews page.
    google_account_email = Column(Text, nullable=True)
    location_title = Column(Text, nullable=True)
    connected_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
