"""Marketing-email unsubscribe (GDPR Phase 3).

One-click: GET (the link in the email body) and POST (RFC 8058
List-Unsubscribe-Post, sent by mail clients' own "Unsubscribe" button) both
withdraw consent immediately -- no login, no confirmation step, so
withdrawing is as easy as giving. The token only identifies whose marketing
consent to withdraw; it grants no other access (see
consent_service._unsubscribe_key).
"""
from html import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.legal import SOURCE_UNSUBSCRIBE
from ..core.limiter import limiter
from ..models.user import User
from ..services import consent_service

router = APIRouter(prefix="/api/consent", tags=["consent"])


def _page(title: str, body: str, status_code: int = 200) -> HTMLResponse:
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(title)} · Mielikkix</title></head>
<body style="font-family:system-ui,sans-serif;max-width:32rem;margin:4rem auto;padding:0 1rem;color:#1a1a1a">
<h1 style="font-size:1.5rem">{escape(title)}</h1><p>{body}</p></body></html>"""
    return HTMLResponse(html, status_code=status_code)


def _unsubscribe(token: str, db: Session) -> HTMLResponse:
    user_id = consent_service.read_unsubscribe_token(token)
    if not user_id or not db.get(User, user_id):
        raise HTTPException(status_code=400, detail="Invalid unsubscribe link")
    consent_service.set_marketing_consent(db, user_id, granted=False, source=SOURCE_UNSUBSCRIBE)
    return _page(
        "You're unsubscribed",
        "You won't receive product updates or tips from Mielikkix any more. "
        "Account emails such as password resets and booking notifications are not affected.",
    )


@router.get("/unsubscribe", response_class=HTMLResponse)
@limiter.limit("30/minute")
def unsubscribe_link(request: Request, token: str, db: Session = Depends(get_db)):
    return _unsubscribe(token, db)


@router.post("/unsubscribe", response_class=HTMLResponse)
@limiter.limit("30/minute")
def unsubscribe_one_click(request: Request, token: str, db: Session = Depends(get_db)):
    return _unsubscribe(token, db)
