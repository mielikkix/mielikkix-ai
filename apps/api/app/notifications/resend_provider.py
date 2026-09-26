from typing import Optional

import httpx
from .base import NotificationProvider
from ..core.config import settings


class ResendNotificationProvider(NotificationProvider):
    async def send_email(self, to: str, subject: str, html: str, headers: Optional[dict[str, str]] = None) -> None:
        body = {
            "from": settings.notification_from_email,
            "to": [to],
            "subject": subject,
            "html": html,
        }
        if headers:
            body["headers"] = headers
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {settings.resend_api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
