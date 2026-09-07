# Mailchimp OAuth Setup — Email Marketing Agent (per-tenant)

This is the customer-facing Mailchimp integration: a Mielikkix TENANT
connects THEIR OWN Mailchimp account so the Email Marketing Agent can read
their audiences. This is a completely separate system from
`files/MAILCHIMP_SETUP.md` (Mielikkix's own marketing-lead sync to
Mielikkix's own Mailchimp account via a static API key) — the two never
share configuration, code, or state. Do not confuse `MAILCHIMP_API_KEY`
(that flow) with `MAILCHIMP_OAUTH_CLIENT_ID`/`MAILCHIMP_OAUTH_CLIENT_SECRET`
(this one).

Phase 1 scope: connect → select an audience → see basic audience/contact
info in the dashboard. No campaigns yet (see `apps/agents/email-marketing/
CLAUDE.md` for the roadmap — Resend is the documented next provider,
plugged into the same `EmailMarketingProvider` abstraction, not built yet).

## 1. Register a Mailchimp OAuth app

1. Log in to the Mailchimp account you want to test with (this can be any
   Mailchimp account for local dev — it does NOT have to be Mielikkix's own
   `post@mielikkix.no` account, unlike the other Mailchimp integration).
2. Go to **Account → Extras → Registered Apps** (or directly:
   `https://admin.mailchimp.com/account/oauth2/`).
3. Click **Register An App**.
4. Fill in:
   - **App Name**: e.g. "Mielikkix Email Marketing (dev)" — shown to a
     customer on Mailchimp's consent screen.
   - **Company/organization** and **Website**: any real values Mailchimp
     requires (Mielikkix's own for production).
   - **Redirect URI** — **must exactly match** what the backend builds
     (`settings.api_public_base_url` + `/api/businesses/me/mailchimp/callback`):
     - Local dev: `http://localhost:8000/api/businesses/me/mailchimp/callback`
     - Production: `https://api.mielikkix.ai/api/businesses/me/mailchimp/callback`
5. Save. Mailchimp shows a **Client ID** and **Client Secret** — this is
   the only time the secret is shown in full.

## 2. Configure the backend

Add to your `.env` (repo root):

```
MAILCHIMP_OAUTH_CLIENT_ID=<from step 1>
MAILCHIMP_OAUTH_CLIENT_SECRET=<from step 1>
```

Left empty, the dashboard's "Connect Mailchimp" button still renders, but
clicking it (or calling `GET /api/businesses/me/mailchimp/authorize`
directly) returns a clean `503` instead of attempting a broken OAuth
redirect — no crash, no raw error page.

Never commit real values — only `.env.example`/`.env.production.example`
(placeholders) are tracked in git.

## 3. Run the migration

```
cd apps/api
alembic upgrade head
```

This creates the `mailchimp_connections` table (see
`apps/api/alembic/versions/b2d6e4f0a9c1_add_mailchimp_connections.py`) —
does not touch the existing `leads` table or its own `mailchimp_*` columns
used by the separate lead-sync flow.

## 4. Plan gating

This feature is gated behind the `email_marketing_enabled` plan feature
(`apps/api/app/core/plans.py`) — same gating mechanism as Booking
Assistant/SEO Copywriter/Review & Reputation. Free and Basic plans do not
include it; Business and Growth do. To test locally on a Free-plan test
business, bump its plan directly in the database the same way this
project's own test fixtures do:

```sql
UPDATE businesses SET plan = 'business', status = 'active' WHERE id = '<your test business id>';
```

## 5. Perform a real end-to-end connection test

1. Start the backend (`uvicorn app.main:app --reload` from `apps/api/`)
   and the dashboard (`npm run dev` from `apps/dashboard/`).
2. Log in to the dashboard as a business on a plan with
   `email_marketing_enabled` (see step 4).
3. Go to **Email Marketing** in the sidebar.
4. Click **Connect Mailchimp** — you should land on Mailchimp's own
   `login.mailchimp.com/oauth2/authorize` consent screen.
5. Log in with the Mailchimp account from step 1 and approve access.
6. Expect to land back on the dashboard's Email Marketing page with a
   green "Mailchimp connected!" banner.
7. If the connected account has more than one audience, you should see a
   picker showing each audience's name and contact count. Select one —
   expect the page to then show "Selected audience: <name>".
8. Click **Change Audience** to confirm you can pick a different one
   later, and **Disconnect** to confirm the connection is fully removed
   (refresh the page — it should show "Connect Mailchimp" again, and
   reconnecting should work cleanly).
9. To verify tenant isolation: log in as a second business (a different
   account) and confirm its Email Marketing page shows "not connected" —
   it must never see the first business's connection or audience.

## 6. If something goes wrong

- **"Mailchimp connection isn't configured on this server yet" (503)**:
  `MAILCHIMP_OAUTH_CLIENT_ID`/`MAILCHIMP_OAUTH_CLIENT_SECRET` aren't set.
- **Redirects back with `?mailchimp=error`**: check the API logs for
  `Mailchimp OAuth token exchange failed` or `Mailchimp OAuth metadata
  lookup failed` — the most common cause is a redirect URI mismatch
  between what's registered on the Mailchimp app (step 1) and
  `settings.api_public_base_url` in your `.env`.
- **"Couldn't reach Mailchimp" when listing audiences**: the stored access
  token may have been revoked from Mailchimp's own side (Account → Extras
  → Registered Apps → your app → Disconnect) — disconnect and reconnect
  in the Mielikkix dashboard to get a fresh token.

## Notes on Mailchimp's OAuth (verified, not assumed)

- Mailchimp Marketing OAuth access tokens **do not expire** and there is
  **no refresh token** — unlike Google's Calendar/Reviews connections,
  there is nothing to refresh or rotate. A stored connection stays valid
  until the customer disconnects it (from Mielikkix or from Mailchimp's
  own Registered Apps page).
- A second call to `https://login.mailchimp.com/oauth2/metadata` (using
  the freshly-issued access token) is required right after token exchange
  to learn the account's data center (`dc`, e.g. `us21`) — every
  subsequent Marketing API call goes to `https://{dc}.api.mailchimp.com`,
  a different host per account.
- Marketing API calls made with an OAuth access token use the header
  `Authorization: OAuth {access_token}` — **not** `Bearer`.
