from .base import NotificationProvider
from .console_provider import ConsoleNotificationProvider
from .resend_provider import ResendNotificationProvider
from ..core.config import settings
from ..models.lead import Lead
from ..models.booking import Booking


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
    # contact_email supports a comma-separated list (e.g. multiple stakeholders
    # for a business) -- send_email's `to` stays single-recipient, so fan out here.
    for recipient in [e.strip() for e in contact_email.split(",") if e.strip()]:
        await provider.send_email(to=recipient, subject=subject, html=html)


async def notify_new_booking(contact_email: str, booking: Booking) -> None:
    """Tells the business a new booking landed on the calendar -- Google's
    own invite email already tells the CUSTOMER (see
    google_calendar_client.py's create_event, sendUpdates="all"); this is
    the separate notification to whoever owns the calendar, same
    "notify the business" step notify_new_lead does for leads. No
    business_name parameter (unlike notify_new_lead) -- Booking has no
    business_id yet (see models/booking.py's comment on why), so this is
    always Mielikkix's own demo booking calendar for now.
    """
    provider = get_notification_provider()
    subject = f"New booking: {booking.meeting_type} with {booking.name}"
    html = f"""
        <p>A new booking was just made through the Mielikkix Booking Assistant.</p>
        <ul>
            <li><strong>What:</strong> {booking.meeting_type}</li>
            <li><strong>When:</strong> {booking.start_at.isoformat()} - {booking.end_at.isoformat()}</li>
            <li><strong>Name:</strong> {booking.name}</li>
            <li><strong>Email:</strong> {booking.email}</li>
            <li><strong>Phone:</strong> {booking.phone or "-"}</li>
        </ul>
        <p>Calendar event ID: {booking.calendar_event_id}</p>
    """
    for recipient in [e.strip() for e in contact_email.split(",") if e.strip()]:
        await provider.send_email(to=recipient, subject=subject, html=html)
