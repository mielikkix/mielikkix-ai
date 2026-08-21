from .base import NotificationProvider


class ConsoleNotificationProvider(NotificationProvider):
    """Free, zero-setup fallback used whenever RESEND_API_KEY isn't
    configured -- logs the notification instead of sending a real email."""

    async def send_email(self, to: str, subject: str, html: str) -> None:
        print(
            "[notification] RESEND_API_KEY not set -- logging instead of sending an email.\n"
            f"  To: {to}\n"
            f"  Subject: {subject}\n"
            f"  Body: {html}"
        )
