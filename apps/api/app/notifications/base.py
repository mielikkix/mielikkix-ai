from abc import ABC, abstractmethod
from typing import Optional


class NotificationProvider(ABC):
    @abstractmethod
    async def send_email(self, to: str, subject: str, html: str, headers: Optional[dict[str, str]] = None) -> None:
        pass
