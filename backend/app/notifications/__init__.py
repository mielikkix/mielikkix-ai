from .base import NotificationProvider
from .console_provider import ConsoleNotificationProvider
from .resend_provider import ResendNotificationProvider
from ..core.config import settings
from ..models.lead import Lead


def get_notification_provider() -> NotificationProvider:
    if settings.resend_api_key:
        return ResendNotificationProvider()
    return ConsoleNotificationProvider()


async def notify_password_reset(to_email: str, full_name: str, reset_token: str) -> None:
    provider = get_notification_provider()
    reset_url = f"{settings.frontend_url}/reset-password?token={reset_token}"
    subject = "Reset your MielikkiX password"
    html = f"""
        <p>Hi {full_name},</p>
        <p>We received a request to reset your MielikkiX password. Click the link below to choose a new one:</p>
        <p><a href="{reset_url}">Reset your password</a></p>
        <p>This link expires in 1 hour. If you didn't request this, you can safely ignore this email.</p>
    """
    await provider.send_email(to=to_email, subject=subject, html=html)


async def notify_new_lead(business_name: str, contact_email: str, lead: Lead) -> None:
    provider = get_notification_provider()
    subject = f"New lead from {business_name}"
    html = f"""
        <p>You've got a new lead from your MielikkiX widget on <strong>{business_name}</strong>.</p>
        <ul>
            <li><strong>Name:</strong> {lead.name}</li>
            <li><strong>Email:</strong> {lead.email or "-"}</li>
            <li><strong>Phone:</strong> {lead.phone or "-"}</li>
            <li><strong>Message:</strong> {lead.message or "-"}</li>
        </ul>
        <p>Log in to your MielikkiX dashboard to follow up.</p>
    """
    await provider.send_email(to=contact_email, subject=subject, html=html)
