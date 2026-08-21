from typing import List
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.dependencies import get_current_user, get_current_business
from ..models.user import User
from ..models.business import Business
from ..models.document import Document
from ..schemas.document import DocumentOut, DocumentFromUrlRequest, WebsiteCrawlRequest, WebsiteCrawlOut
from ..services.document_service import ingest_document, ingest_url, discover_website_pages, crawl_and_ingest_website
from ..services import plan_service

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("", response_model=List[DocumentOut])
def list_documents(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Document).filter(Document.business_id == current_user.business_id).all()


@router.post("", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    plan_service.check_document_limit(db, business)
    return await ingest_document(db, str(current_user.business_id), str(current_user.id), file)


@router.post("/from-url", response_model=DocumentOut)
async def add_document_from_url(
    body: DocumentFromUrlRequest,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    plan_service.check_document_limit(db, business)
    return await ingest_url(db, str(current_user.business_id), str(current_user.id), body.url)


@router.post("/from-website", response_model=WebsiteCrawlOut)
async def add_documents_from_website(
    body: WebsiteCrawlRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """Discovers every page on the business's own website (sitemap first,
    same-domain link crawl as fallback) and imports each one through the
    same pipeline as the single-page /from-url import, in the background --
    see discover_website_pages/crawl_and_ingest_website in document_service.py."""
    plan_service.check_document_limit(db, business)

    discovered = await discover_website_pages(body.url)
    if not discovered:
        raise HTTPException(status_code=400, detail="Couldn't find any pages to import from that site.")

    queued = discovered
    plan = plan_service.get_plan(business.plan)
    if plan.limits.max_document_uploads is not None:
        current_count = db.query(Document).filter(Document.business_id == business.id).count()
        remaining = max(0, plan.limits.max_document_uploads - current_count)
        queued = discovered[:remaining]

    if not queued:
        raise HTTPException(
            status_code=402,
            detail="Your plan's document upload limit has been reached. Upgrade your plan to import more.",
        )

    background_tasks.add_task(crawl_and_ingest_website, str(business.id), str(current_user.id), queued)
    return WebsiteCrawlOut(
        discovered=len(discovered),
        queued=len(queued),
        message=f"Importing {len(queued)} page{'s' if len(queued) != 1 else ''} from your website. "
                f"They'll appear below as they're processed.",
    )


@router.delete("/{doc_id}")
def delete_document(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(
        Document.id == doc_id, Document.business_id == current_user.business_id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    db.delete(doc)
    db.commit()
    return {"ok": True}
