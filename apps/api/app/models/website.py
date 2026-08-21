import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from ..core.database import Base


class BusinessWebsite(Base):
    """A domain a business has registered to embed its widget on.

    Didn't exist before this feature -- the app previously had no way to
    represent "how many websites is this business running the widget on",
    even though the pricing plans (1 / 1 / 3 / 10 websites) depend on it.
    """

    __tablename__ = "business_websites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False, index=True)
    domain = Column(Text, nullable=False)
    label = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    business = relationship("Business", back_populates="websites")
