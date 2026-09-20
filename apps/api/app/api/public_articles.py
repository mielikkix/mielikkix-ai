"""Public, unauthenticated, read-only articles API -- consumed by the Astro
site (website/src/pages/blog/) at BUILD time via a plain fetch(), not by a
visitor's browser. No dependency on require_platform_admin or any other
auth: this deliberately never returns a draft, and never returns
deployment_status/last_deployment_error or any other admin-only field (see
schemas/article.py's PublicArticleOut, a distinct, narrower shape from the
admin ArticleOut).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..schemas.article import PublicArticleListOut, PublicArticleOut
from ..services import article_service

router = APIRouter(prefix="/api/public/articles", tags=["public-articles"])


def _to_public(article) -> PublicArticleOut:
    return PublicArticleOut(
        title=article.title,
        slug=article.slug,
        excerpt=article.excerpt,
        content=article.content,
        featured_image_url=article.featured_image_url,
        meta_title=article.meta_title,
        meta_description=article.meta_description,
        canonical_url=article.canonical_url,
        keywords=article.keywords or [],
        category=article.category,
        tags=article.tags or [],
        author_name=article.author.full_name,
        published_at=article.published_at,
        updated_at=article.updated_at,
    )


@router.get("", response_model=PublicArticleListOut)
def list_public_articles(page: int = 1, page_size: int = 50, db: Session = Depends(get_db)):
    result = article_service.list_public_articles(db, page=page, page_size=page_size)
    return PublicArticleListOut(items=[_to_public(a) for a in result["items"]], total=result["total"])


@router.get("/{slug}", response_model=PublicArticleOut)
def get_public_article(slug: str, db: Session = Depends(get_db)):
    article = article_service.get_public_article_by_slug(db, slug)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return _to_public(article)
