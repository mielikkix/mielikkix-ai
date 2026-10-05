from datetime import datetime
from html import escape as _esc

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


# Norwegian month names for _long_date (strftime's %B follows the server's
# C locale, which is English).
_MONTHS_NB = [
    "januar", "februar", "mars", "april", "mai", "juni",
    "juli", "august", "september", "oktober", "november", "desember",
]


def _nb(locale: str) -> bool:
    """Every customer-facing email below has an English and a Norwegian
    (Bokmål) version; `locale` is the recipient's dashboard language
    (users.locale, see core/locale.py)."""
    return locale == "nb"


def _long_date(when: datetime, locale: str = "en") -> str:
    if _nb(locale):
        return f"{when.day}. {_MONTHS_NB[when.month - 1]} {when.year}"
    return f"{when.strftime('%B')} {when.day}, {when.year}"


def _num(value: int, locale: str = "en") -> str:
    """1,000 in English, 1 000 (no-break space) in Norwegian."""
    return f"{value:,}".replace(",", "\u00a0" if _nb(locale) else ",")


def get_notification_provider() -> NotificationProvider:
    if settings.resend_api_key:
        return ResendNotificationProvider()
    return ConsoleNotificationProvider()


async def notify_password_reset(to_email: str, full_name: str, reset_token: str, locale: str = "en") -> None:
    provider = get_notification_provider()
    reset_url = f"{settings.frontend_url}/reset-password?token={reset_token}"
    if _nb(locale):
        subject = "Tilbakestill passordet ditt for Mielikkix"
        html = f"""
        <p>Hei {_esc(full_name)},</p>
        <p>Noen har bedt om å tilbakestille passordet ditt for Mielikkix. Hvis det var deg, klikker du nedenfor for å velge et nytt:</p>
        <p><a href="{reset_url}">Tilbakestill passordet</a></p>
        <p>Lenken utløper om 1 time. Hvis det ikke var deg, kan du se bort fra denne e-posten — ingenting blir endret.</p>
    """
    else:
        subject = "Reset your Mielikkix password"
        html = f"""
        <p>Hi {_esc(full_name)},</p>
        <p>Someone asked to reset your Mielikkix password. If that was you, click below to choose a new one:</p>
        <p><a href="{reset_url}">Reset your password</a></p>
        <p>This link expires in 1 hour. If it wasn't you, just ignore this email — nothing will change.</p>
    """
    await provider.send_email(to=to_email, subject=subject, html=html)


async def notify_new_lead(business_name: str, contact_email: str, lead: Lead, locale: str = "en") -> None:
    provider = get_notification_provider()
    if _nb(locale):
        subject = f"Ny lead fra {business_name}"
        intro = f"Du har fått en ny lead fra Mielikkix-widgeten på <strong>{_esc(business_name)}</strong>."
        labels = ("Navn", "E-post", "Telefon", "Melding")
        outro = "Logg inn på Mielikkix-dashbordet for å følge opp."
    else:
        subject = f"New lead from {business_name}"
        intro = f"You've got a new lead from your Mielikkix widget on <strong>{_esc(business_name)}</strong>."
        labels = ("Name", "Email", "Phone", "Message")
        outro = "Log in to your Mielikkix dashboard to follow up."
    # The lead's own details are the visitor's data -- never translated.
    html = f"""
        <p>{intro}</p>
        <ul>
            <li><strong>{labels[0]}:</strong> {_esc(lead.name)}</li>
            <li><strong>{labels[1]}:</strong> {_esc(lead.email or "-")}</li>
            <li><strong>{labels[2]}:</strong> {_esc(lead.phone or "-")}</li>
            <li><strong>{labels[3]}:</strong> {_esc(lead.message or "-")}</li>
        </ul>
        <p>{outro}</p>
    """
    # contact_email supports a comma-separated list (e.g. multiple stakeholders
    # for a business) -- send_email's `to` stays single-recipient, so fan out here.
    for recipient in [e.strip() for e in contact_email.split(",") if e.strip()]:
        await provider.send_email(to=recipient, subject=subject, html=html)


async def notify_quota_warning(
    to_emails: list[str], business_name: str, plan_name: str, level: int, used: int, limit: int, locale: str = "en"
) -> None:
    """80% / 100% monthly conversation quota warning (see plan_service's soft limit)."""
    provider = get_notification_provider()
    grace_cap = limit + int(limit * 0.10)
    if _nb(locale):
        name = _esc(business_name)
        if level >= 100:
            subject = f"{business_name} har brukt sine {_num(limit, locale)} AI-samtaler denne måneden"
            body = (
                f"<p>Chat-widgeten på <strong>{name}</strong> har nå hatt {_num(used, locale)} AI-samtaler "
                f"denne måneden, alle {_num(limit, locale)} som er inkludert i {_esc(plan_name)}-planen.</p>"
                f"<p>Det koster ingenting ekstra. Widgeten svarer videre opp til {_num(grace_cap, locale)} samtaler, "
                f"og viser deretter kontaktskjemaet til de besøkende til grensen nullstilles den 1.</p>"
            )
        else:
            subject = f"{business_name} har brukt {level} % av AI-samtalene denne måneden"
            body = (
                f"<p>Chat-widgeten på <strong>{name}</strong> har hatt {_num(used, locale)} av de "
                f"{_num(limit, locale)} AI-samtalene som er inkludert i {_esc(plan_name)}-planen denne måneden.</p>"
            )
        html = body + (
            f'<p>Trenger du mer? <a href="{settings.frontend_url}/dashboard/plan">Oppgrader planen</a> når som helst. '
            "Den høyere grensen gjelder med en gang, og prisforskjellen beregnes forholdsmessig.</p>"
        )
        for recipient in to_emails:
            await provider.send_email(to=recipient, subject=subject, html=html)
        return
    if level >= 100:
        subject = f"{business_name} has used its {limit:,} AI conversations this month"
        body = (
            f"<p>Your chat widget on <strong>{_esc(business_name)}</strong> has now had {used:,} AI conversations "
            f"this month, the full {limit:,} included in your {_esc(plan_name)} plan.</p>"
            f"<p>There's no extra charge. The widget keeps answering up to {grace_cap:,} conversations, "
            f"then shows visitors your contact form instead until the limit resets on the 1st.</p>"
        )
    else:
        subject = f"{business_name} has used {level}% of its AI conversations this month"
        body = (
            f"<p>Your chat widget on <strong>{_esc(business_name)}</strong> has had {used:,} of the {limit:,} "
            f"AI conversations included in your {_esc(plan_name)} plan this month.</p>"
        )
    html = body + (
        f'<p>Need more? <a href="{settings.frontend_url}/dashboard/plan">Upgrade your plan</a> any time. '
        "The higher limit applies straight away and the price difference is prorated.</p>"
    )
    for recipient in to_emails:
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
        f"<li><strong>{label}:</strong> {_esc(value)}</li>"
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
            <li><strong>Category:</strong> {_esc(ticket.category or "-")}</li>
            <li><strong>Priority:</strong> {_esc(ticket.priority or "-")}</li>
            {contact_line}
        </ul>
        <p><strong>Latest message:</strong> {_esc(last_message)}</p>
        <p>Ticket ID: {ticket.id}</p>
    """
    for recipient in settings.platform_admin_emails_list:
        await provider.send_email(to=recipient, subject=subject, html=html)


async def notify_new_booking(contact_email: str, booking: Booking, locale: str = "en") -> None:
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
    if _nb(locale):
        subject = f"Ny bestilling: {booking.meeting_type} med {booking.name}"
        when = (
            f"{_long_date(booking.start_at, locale)} · {booking.start_at.strftime('%H:%M')}"
            f"–{booking.end_at.strftime('%H:%M')} UTC"
        )
        labels = ("Du har fått en ny bestilling i kalenderen.", "Hva", "Når", "Navn", "E-post", "Telefon", "Kalenderhendelse-ID")
    else:
        subject = f"New booking: {booking.meeting_type} with {booking.name}"
        when = _format_time_range(booking.start_at, booking.end_at)
        labels = ("You've got a new booking on your calendar.", "What", "When", "Name", "Email", "Phone", "Calendar event ID")
    html = f"""
        <p>{labels[0]}</p>
        <ul>
            <li><strong>{labels[1]}:</strong> {_esc(booking.meeting_type)}</li>
            <li><strong>{labels[2]}:</strong> {when}</li>
            <li><strong>{labels[3]}:</strong> {_esc(booking.name)}</li>
            <li><strong>{labels[4]}:</strong> {_esc(booking.email)}</li>
            <li><strong>{labels[5]}:</strong> {_esc(booking.phone or "-")}</li>
        </ul>
        <p>{labels[6]}: {_esc(booking.calendar_event_id)}</p>
    """
    for recipient in [e.strip() for e in contact_email.split(",") if e.strip()]:
        await provider.send_email(to=recipient, subject=subject, html=html)


async def send_marketing_email(db, user, subject: str, html: str) -> bool:
    """The ONLY way to send Mielikkix's own non-transactional email (product
    updates, tips, newsletters) to an account holder -- GDPR Phase 3. Checks
    the user's current marketing consent first and silently skips if there
    is none (returns False), and always adds a working one-click unsubscribe
    link plus RFC 8058 List-Unsubscribe headers. Transactional emails
    (password reset, lead/booking/escalation notifications) don't go through
    here and don't need consent.

    Not to be confused with the Email Marketing agent (api/campaigns.py),
    which sends a CUSTOMER's campaigns to the customer's own audience via
    the customer's own Mailchimp account."""
    # Imported here: consent_service imports settings/models, and keeping
    # the top of this module free of DB-layer imports matches the rest of it.
    from ..services import consent_service

    if not consent_service.has_marketing_consent(db, user.id):
        return False

    token = consent_service.make_unsubscribe_token(user.id)
    unsubscribe_url = f"{settings.api_public_base_url}/api/consent/unsubscribe?token={token}"
    html = f"""{html}
        <hr>
        <p style="font-size:12px;color:#666">
          You're getting this because you opted in to product updates from Mielikkix.
          <a href="{unsubscribe_url}">Unsubscribe</a> with one click, any time.
        </p>
    """
    headers = {
        "List-Unsubscribe": f"<{unsubscribe_url}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }
    await get_notification_provider().send_email(to=user.email, subject=subject, html=html, headers=headers)
    return True


# GDPR Phase 4: account deletion emails (transactional -- no consent needed).
def _deletion_date(when: datetime) -> str:
    return f"{when.strftime('%B')} {when.day}, {when.year}"


async def notify_account_deletion_scheduled(
    to_email: str, full_name: str, business_name: str, scheduled_for: datetime, locale: str = "en"
) -> None:
    if _nb(locale):
        html = f"""
        <p>Hei {_esc(full_name)},</p>
        <p>Vi har mottatt forespørselen din om å slette Mielikkix-kontoen for <strong>{_esc(business_name)}</strong>.</p>
        <p>Kontoen og alle dataene blir slettet permanent <strong>{_long_date(scheduled_for, locale)}</strong>.
        Frem til da kan du fortsatt logge inn og avbryte under Chatbot-innstillinger &rarr; Personvern og data.</p>
        <p>Hvis det ikke var du som ba om dette, logger du inn og avbryter slettingen med en gang, og bytter passord.</p>
    """
        await get_notification_provider().send_email(
            to=to_email, subject="Mielikkix-kontoen din er satt opp for sletting", html=html
        )
        return
    html = f"""
        <p>Hi {_esc(full_name)},</p>
        <p>We've received your request to delete the Mielikkix account for <strong>{_esc(business_name)}</strong>.</p>
        <p>The account and all its data will be permanently deleted on <strong>{_deletion_date(scheduled_for)}</strong>.
        Until then you can still sign in and cancel under Chatbot Settings &rarr; Privacy &amp; data.</p>
        <p>If you didn't ask for this, sign in and cancel the deletion straight away, then change your password.</p>
    """
    await get_notification_provider().send_email(to=to_email, subject="Your Mielikkix account is scheduled for deletion", html=html)


async def notify_account_deletion_cancelled(to_email: str, full_name: str, business_name: str, locale: str = "en") -> None:
    if _nb(locale):
        html = f"""
        <p>Hei {_esc(full_name)},</p>
        <p>Slettingen av Mielikkix-kontoen for <strong>{_esc(business_name)}</strong> er avbrutt. Ingenting ble slettet.</p>
    """
        await get_notification_provider().send_email(to=to_email, subject="Sletting av konto avbrutt", html=html)
        return
    html = f"""
        <p>Hi {_esc(full_name)},</p>
        <p>The deletion of the Mielikkix account for <strong>{_esc(business_name)}</strong> has been cancelled. Nothing was deleted.</p>
    """
    await get_notification_provider().send_email(to=to_email, subject="Account deletion cancelled", html=html)


async def notify_account_deleted(to_email: str, business_name: str) -> None:
    """Sent after the account is gone, so the owner's language is no longer
    known: Norwegian and English in one email."""
    html = f"""
        <p>Hei,</p>
        <p>Mielikkix-kontoen for <strong>{_esc(business_name)}</strong> og dataene på den er nå slettet permanent.</p>
        <p>Vi tar bare vare på en minimert oversikt over avtalene og samtykkevalgene på kontoen (uten navn, bedrift
        eller IP-adresse) i 3 år for å dokumentere at regelverket er fulgt, og sletter deretter også den. Se
        <a href="https://mielikkix.ai/no/privacy/">personvernerklæringen</a>.</p>
        <hr>
        <p>Hello,</p>
        <p>The Mielikkix account for <strong>{_esc(business_name)}</strong> and its data have now been permanently deleted.</p>
        <p>We keep only a minimised record of the agreements and consent choices made on the account (no name, business
        or IP address) for 3 years, to demonstrate compliance, and then delete that too. See our
        <a href="https://mielikkix.ai/privacy">Privacy Policy</a>.</p>
    """
    await get_notification_provider().send_email(
        to=to_email, subject="Mielikkix-kontoen din er slettet / Your Mielikkix account has been deleted", html=html
    )
