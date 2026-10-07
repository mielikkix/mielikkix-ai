# CLAUDE.md — apps/agents/email-marketing

Read `apps/agents/CLAUDE.md` first (shared conventions across the Force
agents) — this file covers only what's specific to this one.

## What this agent does

Lets a business send newsletters and promo campaigns to its own Mailchimp
audience, with a human approving every campaign before it sends — this agent
never emails a tenant's list unsupervised. **Built** (Sept 2026), sold at
390 kr/month (placeholder price — see `docs/pricing-rules.md`).

Design change from the original plan: sending goes through the **business's
own Mailchimp account**, not Mielikkix's Resend. Mailchimp handles the
contact list, unsubscribes, delivery and reporting, which a business's
marketing list needs and Resend (transactional email) doesn't provide.

## Where the code is

All in `apps/api` (this folder holds only this spec and a stub):

- **Connect Mailchimp** — `app/api/mailchimp_oauth.py`
  (`/api/businesses/me/mailchimp`: authorize, callback, status, audiences,
  select-audience, disconnect). Token encrypted in `mailchimp_connections`.
  Setup: `files/MAILCHIMP_OAUTH_SETUP.md`.
- **Provider abstraction** — `app/integrations/email_marketing_providers/`
  (ABC + `get_email_marketing_provider()`; Mailchimp implemented, Resend
  listed but not built).
- **Campaigns** — `app/api/campaigns.py` → `app/services/campaign_service.py`
  → `app/integrations/mailchimp_client.py`; table `campaigns`.
- **Dashboard** — `apps/dashboard/src/dashboard/pages/EmailMarketingPage.tsx`
  (`/dashboard/email-marketing`), shown only to businesses with the agent.
- **Access** — `agent_access_service.require_agent_access(..., "email_marketing")`.

Not to be confused with the marketing-site lead sync (`leads.mailchimp_*`,
`files/MAILCHIMP_SETUP.md`), which pushes Mielikkix's *own* demo leads to
Mielikkix's own Mailchimp audience.

## Campaign lifecycle

```
draft ──approve──▶ approved ──send / schedule──▶ (created on Mailchimp)
                       │                         save / schedule / sending / sent / ...
                       └──test──▶ test email via Mailchimp
```

- `draft` and `approved` are local-only; the human-approval gate is here.
- On send/schedule the campaign is created on Mailchimp (`create_campaign` +
  `set_campaign_content`), then sent or scheduled by Mailchimp. After that,
  `status` is Mailchimp's own value, copied through.
- `GET /{id}/report` reads Mailchimp's live report (sent, opens, clicks) and
  refreshes the status. There is no webhook, so status can lag until the
  report is opened.
- `from_email` is display-only: Mailchimp sends from the audience's own
  verified "Campaign Defaults" address.

## Data

```
Campaign (campaigns)
  id, business_id, mailchimp_audience_id, mailchimp_audience_name,
  mailchimp_campaign_id, subject, from_name, from_email, reply_to,
  body_html, status, scheduled_at, sent_at, created_at, updated_at
```

No per-recipient table — Mailchimp's reports are the only source of
delivery data.

## Tests

`apps/api/tests/test_campaign_service.py`, `test_campaigns_api.py`,
`test_mailchimp_client.py`, `test_mailchimp_client_campaigns.py`,
`test_mailchimp_oauth.py` (Mailchimp mocked).

## Definition of done

- [x] Human can write and edit a draft before approving it
- [x] Approved campaign actually sends to the business's real audience
      (via the business's own Mailchimp)
- [x] A campaign can be scheduled for later, not just sent immediately
- [x] Test send before the real send
- [x] Campaigns and send stats visible in the dashboard, gated by entitlement
- [ ] Campaign copy drafted by AI from a plain-language brief (no LLM call yet)
- [ ] Mailchimp webhook for live status (polling today)
- [ ] Cart-recovery campaigns (needs a "cart abandoned" event that doesn't exist)
- [ ] Deployed on the VPS, smoke-tested in production with a real business
