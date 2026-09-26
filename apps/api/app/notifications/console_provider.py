from typing import Optional

from .base import NotificationProvider
from ..core.config import settings


class ConsoleNotificationProvider(NotificationProvider):
    """Free, zero-setup fallback used whenever RESEND_API_KEY isn't
    configured -- logs the notification instead of sending a real email."""

    async def send_email(self, to: str, subject: str, html: str, headers: Optional[dict[str, str]] = None) -> None:
        print(
            "[notification] RESEND_API_KEY not set -- logging instead of sending an email.\n"
            f"  To: {to}\n"
            f"  Subject: {subject}\n"
            # Bodies carry leads' names, emails and messages: only in debug.
            f"  Body: {html if settings.debug else f'[{len(html)} chars; set DEBUG=true to print]'}"
        )
