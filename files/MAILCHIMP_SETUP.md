# Mailchimp Setup — Marketing Lead Sync

Mielikkix's own marketing site (`website/`) has a "Book a Free Demo" form
(`website/src/pages/demo.astro`) that posts to `POST /api/leads` — the same
endpoint every tenant's chat widget uses — using Mielikkix's own
`business_id`. `apps/api/app/services/lead_service.py` syncs leads for that
ONE configured business to Mielikkix's existing Mailchimp account
(`post@mielikkix.no`), and ONLY that one — see `files/ARCHITECTURE.md` §2.6.1
and `files/DATABASE_SCHEMA.md`'s `leads` table for the full design.

This uses the Mailchimp account that already exists. **Do not create a new
Mailchimp account.**

## 1. Get your account values

1. Log in to the existing Mailchimp account (post@mielikkix.no).
2. **Server prefix**: after logging in, the URL looks like
   `https://usXX.admin.mailchimp.com/...` — `usXX` is `MAILCHIMP_SERVER_PREFIX`.
   Also visible under Account → Extras → API keys.
3. **API key**: Account → Extras → API keys → "Create A Key" (or reuse an
   existing one). This is `MAILCHIMP_API_KEY`.
4. **Audience**: use an existing audience, or create one for Mielikkix's own
   leads (Audience → Create Audience). Then Audience → Settings → Audience
   name and defaults → "Audience ID" is `MAILCHIMP_AUDIENCE_ID`.
5. Confirm `post@mielikkix.no` is verified as this audience's "from" email
   (Audience → Settings → sender). If not, verify it (Mailchimp emails a
   confirmation link) and authenticate the sending domain (mielikkix.no) under
   Account → Domains for best deliverability.

## 2. Create the merge fields this integration sends

Audience → Settings → Audience fields and \*|MERGE|\* tags → Add A Field.
`FNAME`/`LNAME` already exist on every audience by default; add these four:

| Merge tag | Field type | Field label |
|---|---|---|
| COMPANY | Text | Company |
| PHONE | Text | Phone |
| INDUSTRY | Text | Industry |
| INTEREST | Text | Interest |

If a tag doesn't exist, Mailchimp rejects the sync request with an "Invalid
Resource" error — `apps/api/app/services/mailchimp_service.py`'s
`MergeFields.to_payload()` only sends tags that have a non-empty value, but
every tag it MIGHT send still needs to exist on the audience first.

## 3. Configure the backend

Add to your `.env` (repo root, read regardless of which directory the API is
started from — see `apps/api/app/core/config.py`):

```
MAILCHIMP_API_KEY=<from step 1>
MAILCHIMP_SERVER_PREFIX=<from step 1>
MAILCHIMP_AUDIENCE_ID=<from step 1>
MAILCHIMP_FROM_EMAIL=post@mielikkix.no
MAILCHIMP_FROM_NAME=Mielikkix
MAILCHIMP_SYNC_BUSINESS_ID=<Mielikkix's own business_id — see below>
```

`MAILCHIMP_SYNC_BUSINESS_ID` must be the SAME business_id `website/.env`'s
`PUBLIC_MIELIKKIX_BUSINESS_ID` points at:
- **Local dev**: run `python scripts/setup_local_mielikkix_business.py` from
  `apps/api/` (server must already be running) — it prints the business_id to
  use for both `VOICE_AGENT_BUSINESS_ID` and this value.
- **Production**: the real `app.mielikkix.ai` business_id `website/.env`'s
  `PUBLIC_MIELIKKIX_BUSINESS_ID` already points at. Do not guess this — look
  it up from the production database/dashboard.

Never commit real values — only `.env.example`/`.env.production.example`
(placeholders) are tracked in git.

## 4. Run the migration

```
cd apps/api
alembic upgrade head
```

This adds the marketing-lead columns to the existing `leads` table (see
`apps/api/alembic/versions/e7c4a2f6b813_add_mailchimp_lead_fields.py`) — no
existing data is touched, every new column is nullable or defaults to false.

## 5. Start the backend and submit a test lead

1. `uvicorn app.main:app --reload` (from `apps/api/`).
2. Open the marketing site's `/demo` page (or `curl`/Postman `POST /api/leads`
   directly — see `files/API_TESTING.md` §8) with `business_id` set to the
   value from step 3, and a real email you can check.
3. Expect `201 {"success": true, "message": "..."}`.

## 6. Verify in Mailchimp

1. **Contact appears**: Audience → All contacts — your test email should
   appear within seconds (sync runs as a background task on the same
   request, not a queued job).
2. **Merge fields**: click the contact — First Name/Last Name/Company/Phone/
   Industry/Interest should match what you submitted (fields you left blank
   are simply absent, not blanked-out placeholders).
3. **Tags**: the contact should have `LEAD`, `DEMO_REQUESTED`,
   `SOURCE_WEBSITE`, plus one `AGENT_*` tag matching the "interest" you chose
   and one `INDUSTRY_*` tag matching the industry (see
   `apps/api/app/services/lead_service.py`'s `INTEREST_TAGS`/`INDUSTRY_TAGS`
   for the exact mapping — "Other" intentionally has no dedicated tag).
4. **Consent + Double Opt-In**: submit once WITH the marketing-consent checkbox
   checked (using a real inbox you can check) and once without.
   - The non-consented contact's status should be "Transactional" — never
     "Subscribed", with or without the checkbox.
   - The consented contact's status should be **"Pending"**, not
     "Subscribed" — and a confirmation email from Mailchimp should land in
     that inbox within a minute or two. This is intentional: this
     integration always requests `status_if_new: "pending"` for a new,
     consenting contact rather than `"subscribed"`, specifically so
     Mailchimp's own Double Opt-In confirmation email fires (setting
     `"subscribed"` directly from the API bypasses Double Opt-In entirely,
     regardless of the audience's own configuration). Click the confirm
     link in that email — the contact's status should then flip to
     "Subscribed" on Mailchimp's own side, with no further action from
     this app. **Do not disable Double Opt-In on this audience** to make
     that first "Pending" state go away — it's the correct, expected state
     for an unconfirmed new subscriber.
   - Re-submit the SAME email with the box unchecked afterward — status
     must stay whatever it already was (never gets reset to
     "Transactional" or "Unsubscribed" by a later unchecked submission).
5. **Automation trigger**: if you've built a Mailchimp Customer Journey/
   Automation on the `DEMO_REQUESTED` tag (see `files/ARCHITECTURE.md`'s
   automation plan), confirm it actually fires for a new tagged contact.
   These journeys are configured manually inside Mailchimp — this
   integration only ever guarantees the contact + tags are correct;
   building/tuning the journey itself is a Mailchimp-side task.

## 7. Verify a previously-unsubscribed contact stays protected

1. Pick a test contact and manually mark them "Unsubscribed" in Mailchimp
   (Audience → All contacts → open the contact → Unsubscribe), or use one
   who already clicked a real unsubscribe link previously.
2. Submit the demo form again with that same email, checkbox UNCHECKED.
   Expect: demo request succeeds, contact's Mailchimp status is untouched
   ("Unsubscribed").
3. Submit again with the checkbox CHECKED this time. Expect: the contact's
   status is **still "Unsubscribed"** — this app never sends a bare
   `status` field to Mailchimp (only `status_if_new`, which Mailchimp only
   consults when creating a brand-new member), so it can never silently
   flip an existing contact's status in either direction. A real
   resubscribe has to go through Mailchimp's own re-permission flow (e.g.
   a "Yes, add me back" campaign with its own confirm link), not this
   integration.

## 8. If a sync fails

Check the API logs for `Mailchimp sync failed for lead <id>: ...` — the lead
is still saved in the database either way (`mailchimp_synced=false`).
Retry it once the underlying issue (bad credentials, missing merge field,
Mailchimp outage) is fixed:

```
POST /api/leads/{lead_id}/sync-mailchimp
```
(authenticated — log in as the Mielikkix business account first; see
`files/API_TESTING.md` for how to get a token).
