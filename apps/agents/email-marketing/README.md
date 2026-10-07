# apps/agents/email-marketing

Built Force agent. A business connects its own Mailchimp account, picks an
audience, writes a campaign, approves it, sends a test, then sends now or
schedules it — Mailchimp delivers it and the dashboard shows Mailchimp's live
report. Nothing sends without a human approving it.

The code lives in `apps/api` (`app/api/campaigns.py`, `app/api/mailchimp_oauth.py`,
`app/services/campaign_service.py`); the dashboard page is
`apps/dashboard/src/dashboard/pages/EmailMarketingPage.tsx`. This folder holds the
spec — see [`CLAUDE.md`](./CLAUDE.md) for the lifecycle, data model, tests and what's
still missing (AI copywriting, webhook).
