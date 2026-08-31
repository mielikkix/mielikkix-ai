# Google OAuth Verification — Submission Draft

Draft content for the Google Cloud Console → **APIs & Services → OAuth consent
screen** verification submission, so Booking Assistant's Google Calendar
connection can leave Testing mode (100-user cap, 7-day token expiry) and go
to production (any business can connect, no manual test-user list, no
re-consent every week).

Copy each field below into the matching Console field. `[FILL IN]` marks the
only two things left for you to confirm before submitting — everything else
is drafted and ready.

---

## 1. OAuth consent screen — App information

| Field | Value |
|---|---|
| App name | `Mielikkix` |
| User support email | `post@mielikkix.no` |
| App logo | [FILL IN] — Google wants a 120×120px PNG/JPG. Use the site's existing brand mark if you have one exported; otherwise skip for now, add it later without needing re-verification. |
| Application home page | `https://mielikkix.ai` |
| Application privacy policy link | `https://mielikkix.ai/privacy` |
| Application terms of service link | [FILL IN] — optional field. Leave blank unless you already have a Terms page; it's not required for verification of these scopes. |
| Authorized domains | `mielikkix.ai` |
| Developer contact information | `post@mielikkix.no` |

---

## 2. Scopes

Add exactly these three (matching `CALENDAR_SCOPES` in
`apps/api/app/integrations/google_calendar_client.py` and the `userinfo.email`
scope in the OAuth flow):

- `https://www.googleapis.com/auth/calendar.freebusy`
- `https://www.googleapis.com/auth/calendar.events`
- `https://www.googleapis.com/auth/userinfo.email`

Google will flag `calendar.freebusy` and `calendar.events` as **sensitive
scopes** and require a written justification for each, entered directly in
the verification form.

### Justification: `calendar.freebusy`

> Mielikkix's Booking Assistant lets a business connect their own Google
> Calendar so our AI assistant can check real-time availability before
> offering appointment slots to the business's own website visitors or phone
> callers. We use `calendar.freebusy` strictly read-only, to query whether a
> candidate time slot is already busy — we never read event titles,
> descriptions, attendees, or any other event content. This is the narrowest
> scope Google offers that supports a free/busy check; `calendar.readonly` or
> the full `calendar` scope would grant us far more access than the feature
> requires.

### Justification: `calendar.events`

> Once a business's website visitor or phone caller picks an available time,
> Booking Assistant creates a new calendar event on the connected Google
> Calendar representing that appointment, with the visitor added as an
> attendee so Google sends them a calendar invite directly. We only create
> events that our own booking flow generates — we never read, list, modify,
> or delete any pre-existing event on the business's calendar. We chose
> `calendar.events` over the broader `calendar` scope specifically to avoid
> any access to the business's existing calendar data.

### Justification: `userinfo.email`

> Used only to display which Google account a business has connected in
> their own Mielikkix dashboard (e.g. "Connected as: owner@business.com"),
> so the business can confirm they authorized the correct account. Not used
> for authentication, marketing, or any purpose beyond that display.

---

## 3. Demo video (Google will very likely require one for `calendar.events`)

Google's verification form asks for a screen recording showing the OAuth
consent flow end-to-end, in context, so a reviewer can see exactly what a
real user sees and why each scope is needed. Suggested script (2–3 minutes,
no narration needed — Google just wants the on-screen flow):

1. Sign in to the Mielikkix dashboard as a business (`app.mielikkix.ai`).
2. Navigate to **Settings → Booking Assistant → Connect Google Calendar**.
3. Click connect — show the real Google consent screen, with the three
   scopes above visible in Google's own consent UI.
4. Approve — show the redirect back to Settings showing "Connected as:
   [email]".
5. Switch to the business's public chat widget or `/demo/voice-receptionist`
   page, and complete one real booking end-to-end (ask for availability,
   pick a slot, confirm) — showing the actual feature the scopes power.
6. Show the resulting event appearing on the connected Google Calendar.
7. Back in Settings, show the "Disconnect" control, to demonstrate revocation
   is available and immediate.

I can help stage this run (start the dev server, confirm the flow works end
to end) whenever you're ready to record it — recording itself needs to be
done on your machine since it's your Google account completing the consent
screen.

---

## What's still open

- [FILL IN] App logo image (optional — can submit without it and add later).
- [FILL IN] Record and upload the demo video above.
- Everything else in this document is ready to paste into the Console as-is.

Once submitted, Google's typical turnaround for this scope tier (sensitive,
not restricted) is a few days to a couple of weeks. They may come back over
email with follow-up questions about the justification text above — those
threads go to `post@mielikkix.no`.
