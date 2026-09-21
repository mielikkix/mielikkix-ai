from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class SeoWebsiteCreate(BaseModel):
    url: str
    name: Optional[str] = None
    target_country: Optional[str] = None
    target_language: Optional[str] = None
    primary_category: Optional[str] = None
    target_keywords: List[str] = Field(default_factory=list)
    crawl_tier: str = "starter"


class SeoWebsiteOut(BaseModel):
    id: str
    url: str
    name: Optional[str]
    target_country: Optional[str]
    target_language: Optional[str]
    primary_category: Optional[str]
    target_keywords: List[str]
    crawl_tier: str
    # Stage 15 (recurring audits) -- null/null means no schedule, the
    # default. See seo_schedule_service.py.
    audit_schedule: Optional[str]
    next_scheduled_audit_at: Optional[datetime]
    created_at: datetime

    @classmethod
    def from_orm_website(cls, website) -> "SeoWebsiteOut":
        return cls(
            id=str(website.id),
            url=website.url,
            name=website.name,
            target_country=website.target_country,
            target_language=website.target_language,
            primary_category=website.primary_category,
            target_keywords=website.target_keywords or [],
            crawl_tier=website.crawl_tier,
            audit_schedule=website.audit_schedule,
            next_scheduled_audit_at=website.next_scheduled_audit_at,
            created_at=website.created_at,
        )


class SeoWebsiteScheduleUpdate(BaseModel):
    # None turns scheduling off. Validated against
    # seo_schedule_service.SCHEDULE_INTERVALS at the API layer (400 on an
    # unknown value), not here, so the error message can list the actual
    # valid set instead of duplicating it in this schema.
    interval: Optional[str] = None
