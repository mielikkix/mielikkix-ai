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
            created_at=website.created_at,
        )
