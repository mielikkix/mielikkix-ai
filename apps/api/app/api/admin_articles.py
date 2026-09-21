"""MielikkiX Admin -> Articles. Same protection pattern as app/api/admin.py:
gated once at the router level via require_platform_admin, so a route added
here later can't be left accidentally unprotected. This is deliberately a
separate router file from admin.py (rather than more routes bolted onto
it) given how much this feature adds on its own -- same
`/api/admin/...` prefix family, same auth, just its own module.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.dependencies import get_current_user, require_platform_admin
from ..models.user import User
from ..schemas.article import (
    ArticleCreate,
    ArticleListOut,
    ArticleOut,
    ArticleUpdate,
    DeploymentResultIn,
    DeploymentTriggerOut,
)
from ..services import article_service

router = APIRouter(
    prefix="/api/admin/articles", tags=["admin-articles"], dependencies=[Depends(require_platform_admin)]
)


@router.get("", response_model=ArticleListOut)
def list_articles(
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    if status and status not in ("draft", "published"):
        raise HTTPException(status_code=400, detail="status must be 'draft' or 'published'.")
    return article_service.list_articles(db, status=status, page=page, page_size=page_size)


@router.get("/{article_id}", response_model=ArticleOut)
def get_article(article_id: str, db: Session = Depends(get_db)):
    article = article_service.get_article(db, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@router.post("", response_model=ArticleOut)
def create_article(
    body: ArticleCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return article_service.create_article(db, current_user, body)


@router.patch("/{article_id}", response_model=ArticleOut)
def update_article(article_id: str, body: ArticleUpdate, db: Session = Depends(get_db)):
    article = article_service.update_article(db, article_id, body)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@router.delete("/{article_id}", status_code=204)
def delete_article(article_id: str, db: Session = Depends(get_db)):
    """Permanent deletion, not a status change -- see article_service.
    delete_article's own docstring for exactly what does and doesn't get
    touched (the author's User row never does). Same 404-if-missing,
    204-on-success shape as the existing SEO website delete endpoint
    (app/api/agents_seo_audit.py:delete_website) -- gated by the same
    router-level require_platform_admin as every other route in this file,
    nothing new to authorize here."""
    deleted = article_service.delete_article(db, article_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Article not found")


@router.post("/{article_id}/publish", response_model=DeploymentTriggerOut)
def publish_article(article_id: str, db: Session = Depends(get_db)):
    """Publishing writes status="published" to the live database -- the
    real source of truth -- but does NOT mark the article Live and does
    NOT attempt any automated build/deploy. Website deployment is manual
    for now (2026-09-20 decision): the next time an admin actually builds
    and uploads the site by hand, Astro will pick up this article via the
    public API (see website/src/pages/blog/[slug].astro), and the admin
    then confirms that happened via POST .../deployment-result below.
    Marking this "live" just because Publish was clicked, with no real
    deploy having happened, would be a false status -- exactly what this
    endpoint must not do."""
    article = article_service.mark_publish_intent(db, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")

    return DeploymentTriggerOut(
        article=article,
        deployment_status=article.deployment_status,
        deployment_message=(
            "Article published to the database. It will go live the next time the website is built and deployed -- "
            "confirm that deployment afterward so this article's status reflects reality."
        ),
    )


@router.post("/{article_id}/unpublish", response_model=DeploymentTriggerOut)
def unpublish_article(article_id: str, db: Session = Depends(get_db)):
    """Reverts to draft immediately in the database -- the public API
    stops serving it right away -- but the currently-live static site
    (built from a PAST deploy) still has it until the next manual
    deployment actually removes it. deployment_status goes back to
    "pending" for the same reason as publish: it's a true statement
    ("this article's live state doesn't match its DB state yet"), not a
    claim that anything has already happened."""
    article = article_service.mark_unpublish_intent(db, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")

    return DeploymentTriggerOut(
        article=article,
        deployment_status=article.deployment_status,
        deployment_message=(
            "Article unpublished in the database. It will be removed from the live site the next time the "
            "website is built and deployed."
        ),
    )


@router.post("/{article_id}/deployment-result", response_model=ArticleOut)
def report_deployment_result(article_id: str, body: DeploymentResultIn, db: Session = Depends(get_db)):
    """The admin-only, credential-free mechanism for recording what
    actually happened on a manual website deployment (see this feature's
    own architecture notes -- Hostinger deployment is manual by design,
    with no callback/webhook telling this API whether the upload
    succeeded). A platform admin calls this AFTER they've built and
    uploaded the site themselves: success=true marks every currently-
    "pending" published article whose deploy this covered as genuinely
    Live; success=false records why it didn't work. This never runs a
    build, never touches SSH/FTP/SFTP, and never accepts or returns any
    credential -- it's a plain, sanitized status report the admin types
    in themselves."""
    article = article_service.get_article(db, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")

    article_service.record_deployment_result(
        db,
        article_id,
        success=body.success,
        message=body.message or ("Deployed successfully." if body.success else "Deployment reported as failed."),
    )
    return article_service.get_article(db, article_id)
