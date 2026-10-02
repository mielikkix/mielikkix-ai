from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class DocumentFromUrlRequest(BaseModel):
    url: str


class WebsiteCrawlRequest(BaseModel):
    url: str
    # Pages to leave out: any page whose address contains one of these
    # (e.g. "/privacy", "/blog/") -- QA 2026-10-02, E6.
    exclude: List[str] = Field(default_factory=list, max_length=50)


class WebsiteCrawlOut(BaseModel):
    discovered: int
    queued: int
    message: str


class DocumentOut(BaseModel):
    id: UUID
    business_id: UUID
    filename: str
    file_url: str
    file_type: str
    status: str
    created_at: datetime
    title: Optional[str] = None
    char_count: Optional[int] = None

    class Config:
        from_attributes = True
