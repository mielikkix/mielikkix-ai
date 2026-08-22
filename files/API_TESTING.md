# MielikkiX — Swagger API Testing Guide

A walkthrough for manually testing every backend endpoint via the interactive Swagger UI at
**http://127.0.0.1:8000/docs**. Follow it top to bottom the first time — later sections depend on
data created in earlier ones (a business, a JWT, an FAQ, etc.).

Backend must be running first (Postgres via `docker compose up -d db` from the repo root, then):
```powershell
cd C:\Pratibha2026\mielikkix-ai\apps\api
.\.venv\Scripts\uvicorn.exe app.main:app --reload --host 127.0.0.1 --port 8000
```

## Two kinds of endpoints

- **Authenticated (dashboard) endpoints** — everything under `/api/businesses` (except
  `/plans` and `/{id}/public-settings`), `/api/websites`, `/api/faqs`, `/api/products`,
  `/api/documents`, `/api/analytics`, plus `GET`/`DELETE /api/chat/conversations` and
  `GET`/`PATCH /api/leads`. These require a JWT (see step 1) and always scope data to *your*
  business via the token — never via a body/query param.
- **Public (widget-facing / pre-auth) endpoints** — `POST /api/chat/message`,
  `GET /api/chat/history/{id}`, `POST /api/leads`, `GET /api/businesses/plans`,
  `GET /api/businesses/{id}/public-settings`, `POST /api/auth/forgot-password`,
  `POST /api/auth/reset-password`. No auth required; the widget-facing ones need a real
  `business_id` passed explicitly since there's no JWT to infer it from.
- **Platform-admin (operator-only) endpoints** — everything under `/api/admin`. These need a JWT
  *and* that JWT's email must be in the `PLATFORM_ADMIN_EMAILS` env var — a normal business owner's
  token gets a **403** here even though it works fine on every other authenticated endpoint above.
  See section 10.

---

## 1. Auth — `POST /api/auth/register`

```json
{
  "business_name": "Green Leaf Cafe",
  "business_slug": "green-leaf-cafe",
  "industry": "restaurant",
  "full_name": "Priya Sharma",
  "email": "priya@greenleafcafe.com",
  "password": "TestPass123!"
}
```
`industry` must be one of: `retail`, `restaurant`, `clinic`, `real_estate`, `service`, `other`.

Expect **200** with a `UserOut` body (`id`, `email`, `full_name`, `role`, `business_id`,
`is_platform_admin`) — there's no `access_token` in the response. Auth is a JWT set server-side as
an **httpOnly cookie** (`access_token`, see `_set_auth_cookie` in `apps/api/app/api/auth.py`), not a bearer
token returned to the client.
Registering the same `email` or `business_slug` twice correctly returns **400** — that's the
duplicate check working, not a bug.

Then **`POST /api/auth/login`**:
```json
{ "email": "priya@greenleafcafe.com", "password": "TestPass123!" }
```
Same response shape.

### Auth is automatic — no Authorize step needed
Because the token is an httpOnly cookie set on `/api/auth/register` or `/api/auth/login`, Swagger's
browser tab already holds it after either call — every endpoint below that needs auth just works on
the next request, no `Authorize` button, no token to copy/paste. (There's nothing to paste in
anyway: the cookie is httpOnly, so it's not readable from JS or visible in the response body.) Use
**`POST /api/auth/logout`** to clear the cookie if you need to test as a different user.

> Tip: if you need the `business_id` for a public endpoint below and don't have it from `GET /me`
> yet, decode the cookie's JWT at jwt.io — it's in the payload.

### Password reset — `POST /api/auth/forgot-password`, `POST /api/auth/reset-password`
```json
{ "email": "priya@greenleafcafe.com" }
```
Always returns the same **200** message regardless of whether the email exists (prevents account
enumeration). If it does exist, a reset email fires as a background task (`NotificationProvider` —
logs to console with the default provider, or sends via Resend if `RESEND_API_KEY` is set) with a
raw token good for **1 hour**. Grab that raw token from the console log or email, then:
```json
{ "token": "PASTE-RAW-TOKEN-HERE", "new_password": "NewPass456!" }
```
Expect **200**. Reusing the same token again should fail — it's marked `used_at` on first use.
Both endpoints are rate-limited (5/hour and 10/hour respectively) — expect **429** if you hammer them in a test loop.

---

## 2. Business profile — `/api/businesses`

- **`GET /me`** → your business record (`name`, `slug`, `industry`, `plan`, `status`, `api_access_addon`, `api_key`, ...).
- **`PATCH /me`** → update branding:
  ```json
  { "primary_color": "#22c55e", "logo_url": "https://example.com/logo.png" }
  ```
  On the Free/Basic plan (no `custom_branding`), setting a non-default `primary_color` correctly returns **403** — that's plan enforcement working, not a bug.
- **`GET /me/settings`** → tone, welcome/fallback messages, business hours, `llm_provider`.
- **`PATCH /me/settings`** → e.g. change the widget's greeting:
  ```json
  { "welcome_message": "Hey there! How can Green Leaf Cafe help you today?", "tone": "friendly" }
  ```
- **`GET /{business_id}/public-settings`** (public, no auth) → only `welcome_message` and
  `primary_color`, the two fields the embeddable widget needs before a visitor logs in anywhere.

---

## 3. Plans & billing — `/api/businesses` + `/api/websites`

- **`GET /api/businesses/plans`** (public) → the four-plan catalog (Free/Basic/Business/Growth)
  with limits and feature flags — this is what powers the pricing/upgrade UI.
- **`GET /api/businesses/me/plan`** → your current plan, live usage counts (websites,
  conversations this month, documents, products), resolved feature flags, and
  `not_yet_implemented` (currently `["instagram_integration", "whatsapp_notifications"]`).
- **`PATCH /api/businesses/me/plan`** → self-serve, **Free-only**. `{ "plan": "free" }` works and
  sets `status` back to `"trial"` (check via `GET /api/businesses/me` — `status` isn't in the
  plan-status response). Try `{ "plan": "business" }` here and expect a **403**, not a 200 — no
  payment processor exists, so this endpoint deliberately can't put a business on a paid plan, even
  via a direct API call. To actually get a paid-plan business to test the rest of this guide with,
  use the admin endpoint in section 10 instead: `PATCH /api/admin/businesses/{id}/plan`.
- **`PATCH /api/businesses/me/plan/api-access-addon`** → `{ "enabled": true }`. Only works on the
  `business` plan — expect **403** on other plans.
- **`GET`/`POST`/`DELETE /api/businesses/me/api-key`** → issue/revoke a bearer API key. `POST`
  requires the `api_access` feature (Growth, or Business + the add-on above) — expect **403**
  otherwise.
- **`POST /api/businesses/me/notification-channels`** → `{ "channel": "whatsapp", "enabled": true }`.
  Expect **501** even on a plan that includes it — WhatsApp/Instagram are gated but not actually
  integrated yet; that 501 is correct behavior, not a bug.
- **Websites** (`/api/websites`) — the domains this business runs its widget on, capped by plan:
  - **`POST ""`** → `{ "domain": "greenleafcafe.com", "label": "Main site" }`
  - **`GET ""`** → list them.
  - **`DELETE /{id}`** → remove one.
  - Adding past your plan's `max_websites` (1 on Free/Basic) correctly returns **402** — try it
    twice on a Free-plan business to see the limit trip.

---

## 4. FAQs — `/api/faqs`

- **`POST ""`** — create a couple, since the chat/RAG step below depends on these existing:
  ```json
  { "question": "What are your opening hours?", "answer": "We're open 8am-8pm daily.", "category": "hours" }
  ```
  ```json
  { "question": "Do you have vegan options?", "answer": "Yes, our vegan menu is on page 2.", "category": "menu" }
  ```
- **`GET ""`** → list them back, note an `id` from the response.
- **`PATCH /{faq_id}`** → `{ "is_active": false }` to test soft-disabling one.
- **`DELETE /{faq_id}`** → remove it, then `GET ""` again to confirm it's gone.

---

## 5. Products/Services — `/api/products`

```json
{ "name": "Cappuccino", "description": "Espresso with steamed milk foam", "price": 3.50, "currency": "USD", "category": "drinks" }
```
Same CRUD shape as FAQs (`GET`, `POST`, `PATCH /{id}`, `DELETE /{id}`).

---

## 6. Documents — `/api/documents`

This one's a file upload, not JSON — in Swagger, `POST ""` shows a file picker instead of a body
box. Upload a small `.txt` or `.pdf` with some business info in it (e.g. a menu or policy doc).
Expect a `DocumentOut` back with `status: "pending"` or `"embedded"`.

- **`GET ""`** → confirm it's listed.
- **`POST /from-url`** → `{ "url": "https://example.com/faq" }` — fetches and ingests a web page
  directly instead of uploading a file. Try it with an internal address like
  `http://localhost:8000` or `http://169.254.169.254` too — expect a rejection, not a fetch; that's
  the SSRF guard working.
- **`POST /from-website`** → `{ "url": "https://example.com" }` — discovers every page on that
  domain (sitemap first, link crawl if there's no sitemap) and imports them all as documents.
  Expect an immediate `{ discovered, queued, message }` response, not a `DocumentOut` — the actual
  fetch+embed work happens in a background task, so `GET ""` right after will show new rows with
  `status: "processing"` that flip to `"embedded"` (or `"failed"`) a few seconds later as the crawl
  works through them. `queued` will be lower than `discovered` if your business is close to its
  plan's document-upload cap — the crawl only imports as many pages as you have room for.
- **`DELETE /{doc_id}`** → remove it.

> Known gap: the current pipeline embeds chunks into a plain `embedding_json` TEXT column and
> scores them with a naive Python cosine-similarity scan (`apps/api/app/rag/pipeline.py`), not a real
> pgvector index query — fine for testing, worth revisiting before this scales past toy data. See
> `files/DATABASE_SCHEMA.md`'s note on `document_chunks`.

---

## 7. Chat / RAG — `POST /api/chat/message` (public, no auth)

This is the one endpoint that needs your **business UUID** pasted manually (decode it from the
JWT, or copy `id` from step 2's `GET /me` response) instead of relying on Authorize.

```json
{
  "business_id": "PASTE-YOUR-BUSINESS-UUID-HERE",
  "session_id": "test-session-1",
  "message": "What are your opening hours?"
}
```
Expect a reply that pulls from the FAQ you created in step 4, plus `intent` (`faq` / `product_inquiry`
/ `lead` / `support`) and a `confidence` score. Requires `GROQ_API_KEY` set in `.env` — if you get a
provider auth error, check that key. Sending enough messages to cross your plan's monthly
conversation cap (50/mo on Free) correctly returns **402** on the next *new* session — an
in-progress conversation already over the line still keeps working.

Then (authenticated):
- **`GET /api/chat/conversations`** → your session should show up with its messages nested.
- **`DELETE /api/chat/conversations/{id}`** → remove one, then `GET` again to confirm it's gone.

---

## 8. Leads — `/api/leads`

**`POST ""`** is also public (widget submits it directly), needs `business_id` again:
```json
{
  "business_id": "PASTE-YOUR-BUSINESS-UUID-HERE",
  "name": "Test Visitor",
  "email": "visitor@example.com",
  "phone": "555-0100",
  "message": "Interested in catering for 50 people"
}
```
Then authenticated:
- **`GET ""`** → list it.
- **`PATCH /{lead_id}`** → `{ "status": "contacted" }` (valid values: `new`, `contacted`, `won`, `lost`).

---

## 9. Analytics — `GET /api/analytics/summary`

Run this last, after you've generated a bit of chat/lead activity above. Expect counts for
conversations, leads, messages, and a `top_questions` list built from repeated visitor messages.
The exact field set returned depends on your plan's `analytics_tier` (basic/standard/advanced) —
compare the response on a Free-plan business vs. one you've switched to Growth in step 3.

---

## 10. Platform Admin — `/api/admin` (operator-only)

Everything here needs a JWT for a user whose email is in `PLATFORM_ADMIN_EMAILS` (see the repo-root
`.env`) — Authorize with a token from an allowlisted account, not a regular business one, or every
call below 403s. This router intentionally queries across *every* tenant, unlike the rest of the
API — that's correct here, not a multi-tenancy leak (see `files/CLAUDE.md`'s multi-tenancy rule).

- **`GET /overview`** → platform KPIs: `total_businesses`, `businesses_by_plan`,
  `businesses_by_status`, `signups_last_30d`, and totals for conversations/leads/documents.
- **`GET /businesses`** → paginated list of every business. Optional query params: `q` (matches
  name/slug/owner email), `plan`, `status`, `page`, `page_size`.
- **`GET /businesses/{business_id}`** → full detail for one business — profile, owners, plan
  limits/usage, chatbot settings snapshot, resource counts, and a 30-day Groq usage summary.
  Expect **404** for an unknown/garbage UUID.
- **`PATCH /businesses/{business_id}/plan`** → the only way to reach a paid plan today:
  ```json
  { "plan": "growth" }
  ```
  Valid values: `"free"`, `"basic"`, `"business"`, `"growth"` — anything else correctly returns
  **422**. Also auto-syncs `status` (`"active"` for a paid plan, `"trial"` for Free), unless the
  business is currently suspended, in which case the plan changes but `status` doesn't.
- **`PATCH /businesses/{business_id}/status`** → manual status override:
  ```json
  { "status": "suspended" }
  ```
  Valid values are only `"active"` and `"suspended"` (not `"trial"` — that one's automatic, see
  section 3 above). Suspending also forces that business's `plan` back to `"free"` in the same
  call — check the response body's `plan` field to confirm. Sending `"trial"` or anything else
  correctly returns **422**.
- **`GET /llm-usage`** → Groq token usage: totals, a daily series, and a top-10-businesses-by-tokens
  breakdown. Optional `business_id` (filter to one business) and `days` (default 30) query params.
  Will be all zeros until a chat message has actually gone through a business on the Groq provider —
  run section 7 first if you want non-empty numbers here.

---

## Troubleshooting notes from our own first run-through

- **500 with no JSON body, just plain "Internal Server Error"** → check the terminal running
  uvicorn for the traceback; that's Starlette's generic fallback for any unhandled exception.
- **`ResponseValidationError` mentioning a `UUID` input where a `string` was expected** → a
  schema in `apps/api/app/schemas/*.py` typed an `id`/`business_id` field as `str` instead of `UUID`
  (already fixed across all `*Out` schemas as of this writing).
- **Two `uvicorn --reload` processes running at once** (e.g. one from an earlier terminal you
  forgot about) will fight over port 8000 and give inconsistent results request-to-request. If
  behavior seems to "flip" between fixed and broken, check for a second process:
  ```powershell
  Get-NetTCPConnection -LocalPort 8000 | Select OwningProcess
  ```
