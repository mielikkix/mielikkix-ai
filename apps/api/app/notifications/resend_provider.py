import httpx
from .base import NotificationProvider
from ..core.config import settings


class ResendNotificationProvider(NotificationProvider):
    async def send_email(self, to: str, subject: str, html: str) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {settings.resend_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": settings.notification_from_email,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                },
            )
            response.raise_for_status()
