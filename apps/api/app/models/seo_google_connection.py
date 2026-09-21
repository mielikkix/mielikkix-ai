import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from ..core.database import Base


class SeoGoogleConnection(Base):
    """A business's own connected Google account for Analytics + Search
    Console (Stage 12, apps/agents/seo-audit/CLAUDE.md's "Professional
    tier roadmap") -- the real per-tenant counterpart CalendarConnection
    already is for Booking Assistant, same shape: one row per business,
    one OAuth client covering both APIs' read-only reporting scopes in a
    single consent screen.

    Unlike CalendarConnection, connecting the account alone isn't enough to
    fetch anything -- a Google account can have many GA4 properties and
    many verified Search Console sites, and there is no reliable way to
    guess which one belongs to a given SeoWebsite. analytics_property_id
    and search_console_site_url are set separately (PATCH .../google, once
    connected) by the business picking the right one -- both null right
    after connecting is a normal, valid state ("connected, not configured
    yet"), not an error.
    """

    __tablename__ = "seo_google_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(
        UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False, unique=True, index=True
    )
    # Encrypted at rest via core/encryption.py -- same reasoning as
    # CalendarConnection.refresh_token_encrypted: this grants ongoing read
    # access to real traffic/search data, never stored or logged plaintext.
    refresh_token_encrypted = Column(Text, nullable=False)
    google_account_email = Column(Text, nullable=True)
    # A GA4 "properties/<id>" string -- null until the business sets it.
    analytics_property_id = Column(Text, nullable=True)
    # The exact verified Search Console property URL (e.g.
    # "https://example.com/" or "sc-domain:example.com") -- null until set.
    search_console_site_url = Column(Text, nullable=True)
    connected_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
