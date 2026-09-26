"""Helpers for keeping personal data out of application logs (GDPR Phase 5)."""
import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_PHONE = re.compile(r"\+?\d[\d\s().-]{6,}\d")


def redact(text: str) -> str:
    """Masks email addresses and phone-number-like digit runs, e.g. in a
    third-party API error body that echoes back what we sent it."""
    return _PHONE.sub("[phone]", _EMAIL.sub("[email]", text))
