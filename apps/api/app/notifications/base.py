from abc import ABC, abstractmethod


class NotificationProvider(ABC):
    @abstractmethod
    async def send_email(self, to: str, subject: str, html: str) -> None:
        pass
