"""UI language of a dashboard user: English ("en") or Norwegian Bokmål ("nb").

Stored on users.locale (None = never chosen, treated as English) and used for
the dashboard (apps/dashboard/src/shared/i18n) and the emails sent to that
user or their business (notifications/__init__.py). This is the language of
Mielikkix's own UI, not of the business's chatbot -- that is
BusinessSettings.languages."""

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

SUPPORTED_LOCALES = ("en", "nb")
DEFAULT_LOCALE = "en"


def normalize_locale(value: Optional[str]) -> Optional[str]:
    """"nb"/"no"/"nb-NO"/"nn" -> "nb", "en"/"en-GB" -> "en", anything else -> None."""
    if not value:
        return None
    base = value.strip().lower().replace("_", "-").split("-")[0]
    if base in ("nb", "no", "nn"):
        return "nb"
    if base == "en":
        return "en"
    return None


def business_locale(db: Session, business_id: UUID | str) -> str:
    """The language for emails to a business as a whole (new lead, usage
    warning): its owner's chosen language, else English."""
    from ..models.user import User

    owner = (
        db.query(User.locale)
        .filter(User.business_id == business_id, User.role == "owner", User.locale.isnot(None))
        .order_by(User.created_at)
        .first()
    )
    return owner[0] if owner and owner[0] in SUPPORTED_LOCALES else DEFAULT_LOCALE
