import asyncio
import os
import re
import json
import uuid
from typing import List
from sqlalchemy.orm import Session
from fastapi import UploadFile, HTTPException
from ..models.document import Document, DocumentChunk
from ..core.config import settings
from ..core.database import SessionLocal
from ..rag.embeddings import embed_texts
from . import plan_service, web_crawl
from .url_normalizer import normalize_url
# The SSRF guard, robots/sitemap parsing, and page-discovery crawler live in
# web_crawl.py (shared with the SEO Audit agent's crawler, see apps/agents/
# seo-audit/CLAUDE.md Stage 2), so both use the same hardened fetch path.
from .web_crawl import MAX_FETCH_BYTES as MAX_URL_FETCH_BYTES


ALLOWED_TYPES = {"pdf", "docx", "txt", "csv", "xlsx", "url"}


def _extract_text(path: str, file_type: str) -> str:
    if file_type == "txt" or file_type == "csv":
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    if file_type == "pdf":
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(path)
            return "\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception:
            return ""
    if file_type == "docx":
        try:
            import docx
            doc = docx.Document(path)
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception:
            return ""
    if file_type == "xlsx":
        try:
            import openpyxl
            wb = openpyxl.load_workbook(path, data_only=True)
            lines = []
            for sheet in wb.worksheets:
                for row in sheet.iter_rows(values_only=True):
                    cells = [str(c) for c in row if c is not None]
                    if cells:
                        lines.append(" | ".join(cells))
            return "\n".join(lines)
        except Exception:
            return ""
    return ""


def _chunk_text(text: str, size: int, overlap: int) -> List[str]:
    # Chunk by line, not by a flat word list — joining an entire document's
    # words with single spaces destroys row/line structure, which silently
    # corrupts tabular data (CSV/XLSX rows bleed into each other).
    lines = text.split("\n")
    chunks: List[str] = []
    current: List[str] = []
    count = 0
    for line in lines:
        line_words = len(line.split())
        if count + line_words > size and current:
            chunks.append("\n".join(current))
            tail: List[str] = []
            tail_count = 0
            for prev_line in reversed(current):
                tail_count += len(prev_line.split())
                tail.insert(0, prev_line)
                if tail_count >= overlap:
                    break
            current, count = tail, tail_count
        current.append(line)
        count += line_words
    if current:
        chunks.append("\n".join(current))
    return chunks


# Unfilled template markers such as "{{VERIFY: org. number}}" -- QA 2026-10-02
# (D12) found them embedded from draft legal pages; never useful as knowledge.
_PLACEHOLDER_RE = re.compile(r"\{\{[^{}]*\}\}")


async def _fetch_url_text(url: str) -> str:
    text, _title, _canonical = await _fetch_url_page(url)
    return text


async def _fetch_url_page(url: str) -> tuple[str, str | None, str | None]:
    """(text, <title>, canonical URL) of a web page."""
    from bs4 import BeautifulSoup

    # fetch_with_redirects already re-validates every redirect hop with
    # assert_public_url (see web_crawl.py) -- a business-controlled public
    # URL could otherwise 302 to a private/internal address or cloud
    # metadata endpoint and have that response ingested.
    resp, _chain = await web_crawl.fetch_with_redirects(url, max_bytes=MAX_URL_FETCH_BYTES)
    if resp.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"URL returned status {resp.status_code}")

    soup = BeautifulSoup(resp.text, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else None
    canonical_tag = soup.find("link", rel=lambda v: v and "canonical" in (v if isinstance(v, list) else [v]))
    canonical = canonical_tag.get("href") if canonical_tag else None
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    lines = []
    for line in soup.get_text(separator="\n").splitlines():
        line = _PLACEHOLDER_RE.sub("", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines), (title or None), (canonical.strip() if canonical else None)


def _page_key(url: str) -> str:
    return normalize_url(url)


async def ingest_url(
    db: Session, business_id: str, user_id: str, url: str, seen_keys: set[str] | None = None
) -> Document | None:
    """Imports one web page. With `seen_keys` (a site import), a page whose
    canonical URL was already imported is skipped (returns None) -- QA
    2026-10-02 (D12): six /demo/?product=... variants of one page were
    imported separately."""
    text, title, canonical = await _fetch_url_page(url)
    if seen_keys is not None:
        keys = {_page_key(url)} | ({_page_key(canonical)} if canonical else set())
        if keys & seen_keys:
            return None
        seen_keys.update(keys)

    doc = Document(
        business_id=business_id,
        filename=url,
        file_url=url,
        file_type="url",
        status="processing",
        uploaded_by=user_id,
        title=title,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    _embed_and_store(db, doc, text)
    return doc


def is_excluded(url: str, exclude: List[str]) -> bool:
    lowered = url.lower()
    return any(p.strip().lower() in lowered for p in exclude if p and p.strip())


async def refetch_url_document(db: Session, doc: Document) -> Document:
    """Re-imports a web page document in place (fresh text, new chunks) -- E6."""
    text, title, _canonical = await _fetch_url_page(doc.file_url)
    db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).delete(synchronize_session=False)
    doc.title = title or doc.title
    doc.status = "processing"
    db.commit()
    _embed_and_store(db, doc, text)
    db.refresh(doc)
    return doc


async def crawl_and_ingest_website(business_id: str, user_id: str, urls: List[str]) -> None:
    """Background-task worker for POST /api/documents/from-website. Runs
    after the response is already sent, so it opens its own DB session --
    the request's injected session is closed by then (see get_db's
    `finally: db.close()`). Each page reuses ingest_url unchanged; a single
    bad page (404, timeout, odd encoding) is skipped rather than aborting
    the rest of the batch."""
    db = SessionLocal()
    try:
        from ..models.business import Business

        business = db.query(Business).filter(Business.id == business_id).first()
        if not business:
            return

        # Pages already in the knowledge base, by normalized address, so a
        # re-import doesn't add "https://x.com/a" next to "https://x.com/a/".
        seen_keys = {
            _page_key(row[0])
            for row in db.query(Document.file_url).filter(Document.business_id == business_id, Document.file_type == "url")
        }
        for url in urls:
            plan = plan_service.get_plan(business.plan)
            if plan.limits.max_document_uploads is not None:
                current_count = db.query(Document).filter(Document.business_id == business_id).count()
                if current_count >= plan.limits.max_document_uploads:
                    break  # plan cap reached mid-crawl -- stop, don't raise (nothing to return this to)

            if _page_key(url) in seen_keys:
                continue

            try:
                await ingest_url(db, business_id, user_id, url, seen_keys=seen_keys)
            except Exception:
                continue  # one bad page shouldn't abort the rest of the crawl

            await asyncio.sleep(0.5)  # politeness toward the target site, not a security control
    finally:
        db.close()


async def ingest_document(
    db: Session, business_id: str, user_id: str, file: UploadFile
) -> Document:
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"File type .{ext} not supported")

    existing = (
        db.query(Document)
        .filter(Document.business_id == business_id, Document.filename == file.filename)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"'{file.filename}' has already been uploaded. Delete the existing copy first if you want to replace it.",
        )

    content = await file.read()
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large")

    os.makedirs(settings.upload_dir, exist_ok=True)
    saved_name = f"{uuid.uuid4()}.{ext}"
    saved_path = os.path.join(settings.upload_dir, saved_name)
    with open(saved_path, "wb") as f:
        f.write(content)

    doc = Document(
        business_id=business_id,
        filename=file.filename,
        file_url=saved_path,
        file_type=ext,
        status="processing",
        uploaded_by=user_id,
        title=file.filename,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    _process_document(db, doc, saved_path, ext)
    return doc


def _process_document(db: Session, doc: Document, path: str, ext: str):
    text = _extract_text(path, ext)
    _embed_and_store(db, doc, text)


def _embed_and_store(db: Session, doc: Document, text: str):
    doc.char_count = len(text)
    try:
        chunks = _chunk_text(text, settings.chunk_size, settings.chunk_overlap)
        embeddings = embed_texts(chunks)

        for idx, (chunk_text, emb) in enumerate(zip(chunks, embeddings)):
            chunk = DocumentChunk(
                business_id=doc.business_id,
                document_id=doc.id,
                chunk_index=idx,
                content=chunk_text,
                embedding_json=json.dumps(emb),
            )
            db.add(chunk)

        doc.status = "embedded"
    except Exception:
        doc.status = "failed"
    finally:
        db.commit()
