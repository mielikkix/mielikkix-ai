from datetime import datetime

from .base import NotificationProvider
from .console_provider import ConsoleNotificationProvider
from .resend_provider import ResendNotificationProvider
from ..core.config import settings
from ..models.lead import Lead
from ..models.booking import Booking
from ..models.ticket import Ticket


def _format_time_range(start: datetime, end: datetime) -> str:
    """Human-readable, e.g. "Wednesday, September 2, 2026 · 9:30 AM - 10:00
    AM UTC" -- Booking.start_at/end_at come back from Postgres in UTC (see
    models/booking.py), and there's no per-business timezone stored
    anywhere yet to convert into instead (business_hours is interpreted
    against whatever timezone the VISITOR's own browser sends at booking
    time, not a fixed per-business one -- see agents_booking.py's
    _business_hours_window) -- labeling it UTC explicitly here is honest
    about that, rather than silently implying it's the business's own
    local time."""
    # start.day directly (not %d) avoids a leading zero on the day without
    # relying on the non-portable %-d/%#d strftime flags (the first works
    # on Linux/Mac, the second on Windows -- neither works on both).
    date_part = f"{start.strftime('%A, %B')} {start.day}, {start.year}"
    start_time = start.strftime("%I:%M %p").lstrip("0")
    end_time = end.strftime("%I:%M %p").lstrip("0")
    return f"{date_part} · {start_time} - {end_time} UTC"


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


async def notify_support_escalation(ticket: Ticket) -> None:
    """Tells Mielikkix's own team a Support Triage ticket needs a human --
    low-confidence classification, high/urgent priority, a classification
    failure, or a direct escalation from Voice Receptionist (see
    services/support_service.py's create_ticket). Sent to
    settings.platform_admin_emails_list -- the same "who runs Mielikkix"
    list app/core/dependencies.py's require_platform_admin already uses,
    since this ticket belongs to the platform itself, not a tenant business
    (see models/ticket.py's comment on why Ticket has no business_id).
    """
    provider = get_notification_provider()
    subject = f"[Support] Ticket needs follow-up ({ticket.channel})"
    contact_line = "".join(
        f"<li><strong>{label}:</strong> {value}</li>"
        for label, value in [
            ("Name", ticket.customer_name),
            ("Email", ticket.customer_email),
            ("Phone", ticket.customer_phone),
        ]
        if value
    )
    last_message = ticket.messages[-1].content if ticket.messages else "(no message recorded)"
    html = f"""
        <p>A Support Triage ticket needs a human follow-up.</p>
        <ul>
            <li><strong>Category:</strong> {ticket.category or "-"}</li>
            <li><strong>Priority:</strong> {ticket.priority or "-"}</li>
            {contact_line}
        </ul>
        <p><strong>Latest message:</strong> {last_message}</p>
        <p>Ticket ID: {ticket.id}</p>
    """
    for recipient in settings.platform_admin_emails_list:
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
            <li><strong>When:</strong> {_format_time_range(booking.start_at, booking.end_at)}</li>
            <li><strong>Name:</strong> {booking.name}</li>
            <li><strong>Email:</strong> {booking.email}</li>
            <li><strong>Phone:</strong> {booking.phone or "-"}</li>
        </ul>
        <p>Calendar event ID: {booking.calendar_event_id}</p>
    """
    for recipient in [e.strip() for e in contact_email.split(",") if e.strip()]:
        await provider.send_email(to=recipient, subject=subject, html=html)
