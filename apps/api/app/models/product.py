import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, DateTime, Boolean, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from ..core.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False, index=True)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Numeric(10, 2), nullable=True)
    currency = Column(Text, default="USD")
    image_url = Column(Text, nullable=True)
    category = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    # Populated only by approving an SEO Copywriter draft (see
    # models/seo_draft.py and services/seo_service.py) -- nullable/blank
    # until a business actually reviews and approves a generated draft, so
    # nothing here is ever silently auto-published.
    seo_title = Column(Text, nullable=True)
    meta_description = Column(Text, nullable=True)
    # Embedding of name + category + description, computed on create/update --
    # see product_embedding_text below and api/products.py.
    embedding_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    business = relationship("Business", back_populates="products")


def product_embedding_text(product: Product) -> str:
    """What gets embedded into Product.embedding_json for RAG search --
    shared by api/products.py's own create/update routes and
    services/seo_service.py's approve_draft (which must re-embed after
    overwriting description), so the exact text fed to the embedding model
    can't drift between the two call sites. Lives here, not in either
    caller, since a service module importing from an api module (or vice
    versa) would invert this codebase's normal layering."""
    return f"{product.name} {product.category or ''} {product.description or ''}".strip()
