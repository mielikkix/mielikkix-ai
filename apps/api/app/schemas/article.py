from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator

ArticleStatus = Literal["draft", "published"]
DeploymentStatus = Literal["not_deployed", "pending", "live", "failed"]


class ArticleAuthorOut(BaseModel):
    id: UUID
    full_name: str
    email: str

    class Config:
        from_attributes = True


class ArticleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    # Optional -- article_service.py slugifies `title` when omitted, the
    # same "derive from a human-entered field" pattern auth_service.py
    # already uses for a business's own slug.
    slug: Optional[str] = None
    excerpt: Optional[str] = None
    content: str = Field(min_length=1)
    featured_image_url: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    canonical_url: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    # A new article always starts as a draft -- publishing is its own
    # explicit action (POST .../publish), never a side effect of create.
    status: Literal["draft"] = "draft"

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("title must not be blank")
        return v.strip()

    @field_validator("content")
    @classmethod
    def _content_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be blank")
        return v


class ArticleUpdate(BaseModel):
    """All fields optional -- PATCH semantics, only send what changed.
    Status is intentionally NOT settable here -- publish/unpublish are their
    own endpoints so the "set status=published" path always also runs the
    publish flow (published_at, slug re-check, deploy trigger) rather than
    silently skipping it via a plain field update."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    slug: Optional[str] = None
    excerpt: Optional[str] = None
    content: Optional[str] = Field(default=None, min_length=1)
    featured_image_url: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    canonical_url: Optional[str] = None
    keywords: Optional[List[str]] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None


class ArticleOut(BaseModel):
    """Admin-facing shape -- includes deployment_status/errors, never
    returned to anyone but require_platform_admin (see app/api/
    admin_articles.py)."""

    id: UUID
    title: str
    slug: str
    excerpt: Optional[str]
    content: str
    status: ArticleStatus
    deployment_status: DeploymentStatus
    last_deployment_error: Optional[str]
    last_deployed_at: Optional[datetime]
    author: ArticleAuthorOut
    featured_image_url: Optional[str]
    meta_title: Optional[str]
    meta_description: Optional[str]
    canonical_url: Optional[str]
    keywords: List[str]
    category: Optional[str]
    tags: List[str]
    published_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ArticleListOut(BaseModel):
    items: List[ArticleOut]
    total: int
    page: int
    page_size: int


class PublicArticleOut(BaseModel):
    """Public-facing shape (app/api/public_articles.py) -- deliberately
    excludes deployment_status/last_deployment_error/id-as-admin-detail;
    nothing here reveals anything about drafts or admin/internal state.
    Consumed by the Astro site at build time (website/src/pages/blog/)."""

    title: str
    slug: str
    excerpt: Optional[str]
    content: str
    featured_image_url: Optional[str]
    meta_title: Optional[str]
    meta_description: Optional[str]
    canonical_url: Optional[str]
    keywords: List[str]
    category: Optional[str]
    tags: List[str]
    author_name: str
    published_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PublicArticleListOut(BaseModel):
    items: List[PublicArticleOut]
    total: int


class DeploymentTriggerOut(BaseModel):
    """Returned by publish/unpublish -- the article plus a plain-language
    note on what happens next, so the admin UI never has to guess whether
    "published" also means "live" (it never does -- see
    app/services/article_service.py's own module docstring)."""

    article: ArticleOut
    deployment_status: DeploymentStatus
    deployment_message: str


class DeploymentResultIn(BaseModel):
    """Body for POST .../articles/{id}/deployment-result -- how a platform
    admin manually reports what a real (manual) website deployment
    actually did, since Hostinger deployment has no callback/webhook to
    report this automatically. `message` is admin-typed, human-readable
    status text -- never a place to paste a credential, and never
    returned anywhere except back to other platform admins reading this
    same article."""

    success: bool
    message: Optional[str] = Field(default=None, max_length=2000)
