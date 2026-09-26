# Mielikkix — Privacy & GDPR Compliance Implementation

> **How to use:** Paste this whole file into Claude Code at the root of the Mielikkix repo(s), or save it as `docs/GDPR-COMPLIANCE.md` and tell Claude Code: *"Implement docs/GDPR-COMPLIANCE.md phase by phase."*
> Fill in every `{{PLACEHOLDER}}` before starting.

---

## 0. Context for Claude Code

You are implementing privacy and data-protection features for **Mielikkix AS**, a Norwegian-registered B2B SaaS company selling an AI chat widget and AI agents (voice receptionist, booking, support triage) to businesses.

**Launch markets:** Norway first (EEA GDPR + Norwegian Electronic Communications Act / ekomloven), then the UK (UK GDPR + Data (Use and Access) Act 2025), then India (DPDP Act 2023 + DPDP Rules 2025, full compliance by May 2027).

**Surfaces:**
| Surface | URL | Notes |
|---|---|---|
| Marketing site | `https://mielikkix.ai` (+ `/no` Norwegian) | Astro |
| Customer dashboard | `https://app.mielikkix.ai` | SPA (login, register, dashboard) |
| API | `https://api.mielikkix.ai` | Backend + database |
| Chat widget | `widget.js` served from `app.mielikkix.ai` | Embedded on customers' websites |

**Company details (for legal pages):**
- Legal name: Mielikkix AS
- Org. number: `{{ORG_NUMBER}}`
- Registered address: `{{REGISTERED_ADDRESS}}`
- Privacy contact: `post@mielikkix.no` (or `{{PRIVACY_EMAIL}}`)
- Registered: 19.08.2026

**Known subprocessors (verify against the code and update):** Groq (LLM, US), Twilio (voice, US), Resend (email, US), Google (Calendar API; Analytics on marketing site), Cal.com (self-hosted), hosting provider `{{HOSTING_PROVIDER_AND_REGION}}`.

### Findings from the live audit (Sept 2026) — these are the problems to fix
1. Marketing site loads Google Analytics (`G-MLGKW5T191`) and sends a hit **before any consent**. No cookie banner exists.
2. Google Fonts are loaded from `fonts.googleapis.com` (visitor IPs sent to Google).
3. `/terms`, `/cookies`, `/dpa`, `/subprocessors`, `/security`, `/no/privacy` all return 404.
4. Privacy policy says the company is "being registered", omits analytics/cookies/fonts/hosting/Cal.com, omits international transfers and legal bases, and allows "unlimited" conversation retention.
5. `app.mielikkix.ai/register` has no Terms checkbox, no Privacy Policy link, no marketing opt-in, no age confirmation, no country field. Login/Register pages link to no legal pages.
6. No self-serve account deletion or data export (deletion is by email only).
7. Chat widget has no "you are talking to an AI" disclosure; unclear whether it writes to visitor storage on page load.

---

## 1. Ground rules

1. **Explore first.** Before changing code, map the repo(s): frameworks, routing, auth, DB schema/migrations, email sending, the widget build, existing tests. Write a short plan and **stop for my approval** before Phase 1.
2. **Work one phase at a time.** After each phase: summarize changes, list files touched, show how to test, and stop for review.
3. **No dark patterns.** "Reject" must be as easy and visible as "Accept". No pre-ticked boxes. No consent bundled into Terms acceptance.
4. **Legal text is a draft.** Write clear, plain-language legal pages, but add an HTML comment `<!-- LEGAL REVIEW REQUIRED -->` at the top of each. Do not claim certifications or transfer mechanisms you can't find evidence of — leave a `{{VERIFY: ...}}` marker instead.
5. **Bilingual.** Every user-facing page and string ships in English and Norwegian (bokmål), following the existing `/no` routing/i18n pattern.
6. **Server-side enforcement.** Anything required on the frontend (e.g. Terms acceptance) must also be validated in the API.
7. **Tests.** Add unit tests for backend logic and end-to-end tests (Playwright or the repo's existing tool) for every acceptance criterion marked 🧪.
8. **Versioning.** Legal documents have a version string (e.g. `terms-2026-10-01`). Store which version a user accepted.

---

## Phase 1 — Marketing site: cookies, analytics, fonts

### Tasks
- **Option A (preferred — simplest):** Replace Google Analytics with cookieless analytics (e.g. self-hosted Umami or Plausible) that sets no cookies/localStorage. Then no banner is needed on the marketing site. Document the choice.
- **Option B (if GA must stay):** Add a consent banner with **Accept all / Reject all / Settings** (equal prominence). Implement Google Consent Mode v2 with **all storage types `denied` by default**, set *before* `gtag` loads. GA must not send any hit until the visitor accepts analytics.
- Self-host all fonts (e.g. via Fontsource / local `@font-face`). Remove every request to `fonts.googleapis.com` and `fonts.gstatic.com`.
- Add a **"Cookie settings"** link in the footer (Option B) that reopens the banner.
- Store the consent choice in a first-party cookie for max 12 months, including a consent version; re-ask if the version changes.

### Acceptance criteria
- [ ] 🧪 On a fresh visit (cleared storage), **zero requests** go to `google-analytics.com`, `googletagmanager.com`, `fonts.googleapis.com`, `fonts.gstatic.com` before any user choice.
- [ ] 🧪 (Option B) Clicking **Reject all** results in no analytics requests on this and subsequent page loads.
- [ ] 🧪 (Option B) Clicking **Accept all** enables analytics; the choice persists across page loads.
- [ ] 🧪 (Option B) "Cookie settings" in the footer reopens the banner and allows changing the choice; withdrawing is as easy as giving.
- [ ] Banner is keyboard-accessible, readable on mobile, and translated on `/no`.
- [ ] (Option A) Analytics works and sets no cookies or localStorage (verify in DevTools → Application).

---

## Phase 2 — Legal pages

### Tasks
Create these routes in **English and Norwegian** (`/…` and `/no/…`), linked from the footer of the marketing site **and** from the Login/Register pages of the app:

| Route | Content |
|---|---|
| `/privacy` (update) | Controller identity (org no., address), what data, purposes **with legal basis per purpose** (contract / legitimate interest / consent / legal obligation), recipients & subprocessors, international transfers (US vendors: mechanism per vendor `{{VERIFY: DPF or SCCs}}`), retention periods per data type, rights (access, rectification, erasure, restriction, portability, objection, withdraw consent), how to exercise them, right to complain to **Datatilsynet** (and ICO for UK users), cookies summary, AI processing, changes/versioning. Remove "being registered" and "unlimited retention". |
| `/terms` | Terms of Service for business customers. |
| `/dpa` | Data Processing Agreement (GDPR Art. 28) — Mielikkix as **processor** for customers' end-user data (widget conversations, call data, bookings). Include subject matter, duration, data categories, security measures, subprocessor authorization, assistance with data subject requests, breach notification to customer without undue delay, deletion/return at end of contract. |
| `/subprocessors` | Table: vendor, purpose, data processed, location, transfer mechanism. Driven from one config file so it's easy to update. |
| `/cookies` | Every cookie/localStorage key on marketing site, app and widget: name, purpose, duration, first/third party, whether consent is required. |
| `/security` | Short page: hosting location, encryption in transit/at rest, access control, backups, breach process, contact. |

### Acceptance criteria
- [ ] 🧪 All routes above return 200 in both EN and NO (no 404s).
- [ ] 🧪 Footer on every marketing page and on app Login/Register links to Privacy, Terms, Cookies.
- [ ] Each page shows a "Last updated" date and version string.
- [ ] Every page starts with `<!-- LEGAL REVIEW REQUIRED -->`; unresolved facts use `{{VERIFY: …}}` markers, listed in the phase summary.
- [ ] The subprocessor list and the cookie table match what the code actually uses (Claude Code must grep the codebase for third-party SDKs/hosts and report any mismatch).

---

## Phase 3 — Sign-up (app.mielikkix.ai/register)

### Tasks
Add to the Register form, below the existing fields:
1. **Country** (select; default by browser locale, user can change). Needed for region-specific notices later.
2. **Required checkbox (unticked):** "I agree to the [Terms of Service] and [Data Processing Agreement]." (links open in new tab)
3. **Required checkbox (unticked):** "I confirm I am 18 or older and signing up on behalf of a business."
4. **Optional checkbox (unticked):** "Send me product updates and tips by email. You can unsubscribe anytime."
5. **Notice text under the button (not a checkbox):** "We process your account data to provide the service. Read our [Privacy Policy]."

Backend:
- New table (e.g. `consent_records`): `id, user_id, type (terms|dpa|age_confirmation|marketing_email), document_version, granted (bool), granted_at, withdrawn_at, source (register|settings|reaccept), ip_hash (optional)`.
- API rejects registration (HTTP 422) if Terms/DPA or age confirmation are missing — regardless of frontend.
- Marketing opt-in stored separately; default `false`.
- Email sending code must check marketing consent before any non-transactional email; every marketing email includes a working one-click unsubscribe.

### Acceptance criteria
- [ ] 🧪 "Create account" is blocked (with a clear message) until Terms/DPA and age boxes are ticked.
- [ ] 🧪 Calling the register API directly without `terms_accepted=true` returns 422 and creates no user.
- [ ] 🧪 After successful signup, `consent_records` contains rows for terms, dpa, age confirmation (with document versions) and marketing (granted true/false).
- [ ] 🧪 All boxes are unticked on page load.
- [ ] 🧪 Marketing checkbox left unticked → user receives no marketing emails; transactional emails (verification, password reset) still work.
- [ ] Privacy Policy / Terms / DPA links work from the Register page, in EN and NO.

---

## Phase 4 — Account self-service (dashboard Settings → "Privacy & data")

### Tasks
- **Export my data:** generates a JSON (and optionally CSV) download of the account's personal data: profile, business settings, consent history, and the tenant's widget/chat data. Async job if large; email link when ready.
- **Delete my account:** confirmation step (type business name), then soft-delete with a **30-day grace period** and cancellation option, then hard-delete of personal data (keep only what law requires, e.g. invoices — document which). Send confirmation emails.
- **Marketing emails toggle:** on/off, writes to `consent_records`.
- **Re-acceptance flow:** when the Terms/DPA version changes, show a modal on next login requiring acceptance before continuing; record it.
- **Consent history view:** list of what the user accepted and when.

### Acceptance criteria
- [ ] 🧪 User can download an export containing all their personal data in a machine-readable format.
- [ ] 🧪 After deletion + grace period (simulate by running the job with a date override), the user's personal data and their tenant's conversation data are gone from the DB; login fails.
- [ ] 🧪 Cancelling within the grace period restores the account.
- [ ] 🧪 Toggling marketing off creates a withdrawal record and stops marketing emails.
- [ ] 🧪 Bumping the Terms version forces the re-acceptance modal on next login.

---

## Phase 5 — Chat widget & agents (customers' end users)

### Tasks
- **No storage before interaction:** the widget must not write cookies/localStorage/sessionStorage until the visitor opens the chat or sends a message. After that, only store what's strictly needed for the conversation (e.g. conversation ID), with a documented max lifetime.
- **AI disclosure:** first message/header of every widget conversation clearly states the visitor is talking to an AI assistant, with a link to the customer's privacy policy (configurable URL per tenant) and to Mielikkix's privacy page. Voice Receptionist greeting must say it's an AI assistant and, if calls are recorded/transcribed, say so.
- **Retention setting per tenant:** default e.g. 90 days, max `{{MAX_RETENTION_DAYS}}` (no "unlimited"). Nightly job deletes expired conversations, transcripts and call recordings.
- **End-user deletion:** API endpoint + dashboard action for a customer to delete a specific visitor's conversations (to handle their end users' erasure requests).
- **Embed docs:** update the customer-facing install docs to explain what the widget stores and that customers should list it in their own cookie/privacy notices.
- **PII hygiene:** don't log full message contents or phone numbers in application logs; redact in error tracking.

### Acceptance criteria
- [ ] 🧪 Loading a page with the widget embedded (not opened) creates **no** cookies or storage keys from the widget.
- [ ] 🧪 Opening the widget shows the AI disclosure before or with the first message, in the configured language.
- [ ] 🧪 Conversations older than the tenant's retention setting are deleted by the job.
- [ ] 🧪 The retention setting cannot be set above the max or to "unlimited".
- [ ] 🧪 Deleting a visitor's conversations via API removes them from DB and search indexes.
- [ ] Grep of logs config shows message bodies/phone numbers are not logged in plaintext.

---

## Phase 6 — Internal compliance docs (in repo `docs/privacy/`)

Create Markdown documents (these are for the company, not public):
- `records-of-processing.md` — GDPR Art. 30 table: activity, purpose, legal basis, data categories, data subjects, recipients, transfers, retention, security measures. Separate sections for Mielikkix as **controller** (customer accounts, marketing site) and as **processor** (customers' end-user data).
- `breach-runbook.md` — detect → contain → assess → notify **Datatilsynet within 72 hours** (ICO for UK-affected users; Data Protection Board of India + affected individuals for Indian users) → notify affected customers without undue delay → log the incident. Include a breach log template.
- `data-subject-requests.md` — how to handle access/erasure/etc. within one month; how to verify identity; how to forward end-user requests to the relevant customer.
- `retention-schedule.md` — every data type and its retention period, matching the code.
- `subprocessor-review.md` — per vendor: DPA signed? transfer mechanism? `{{VERIFY}}` items.

### Acceptance criteria
- [ ] All five docs exist and reference actual tables/services found in the code.
- [ ] Retention periods in docs match the values in code/config (Claude Code must cross-check and report).

---

## Phase 7 — Regional readiness (UK & India) — behind feature flags

### Tasks
- **Region detection:** use the Country field (Phase 3) for account holders; browser locale/IP only as a hint for the marketing banner.
- **UK:** privacy page section for UK users (ICO complaint right, UK representative `{{UK_REPRESENTATIVE}}`). Complaints form or email flow that sends an **acknowledgement within 30 days** (auto-acknowledge immediately). If using Option B banner, a UK variant may treat first-party improvement analytics as opt-out — keep behind a flag and default to the stricter Norwegian behaviour until reviewed.
- **India (flag `INDIA_DPDP`, off by default):** for users with country = India, show a standalone consent notice before account creation that **itemises each data item and its specific purpose**, links to withdraw consent and to a **grievance officer contact** `{{GRIEVANCE_CONTACT}}`, available in English (Hindi/other Indian languages optional later). Record consent in `consent_records` with type `dpdp_notice`.

### Acceptance criteria
- [ ] 🧪 With `INDIA_DPDP` on, a user selecting India sees the itemised notice and cannot register without accepting it; the acceptance is recorded.
- [ ] 🧪 With the flag off, behaviour is unchanged for everyone.
- [ ] 🧪 Submitting a complaint sends an automatic acknowledgement email.
- [ ] UK and India sections appear on the privacy page (EN).

---

## Definition of done (whole project)

- [ ] All 🧪 tests pass in CI.
- [ ] Fresh-visit network check of `mielikkix.ai`, `/no`, `app.mielikkix.ai/login`, `/register`, and a test page embedding the widget shows **no third-party tracking requests before consent**.
- [ ] No 404s on any legal route, EN or NO.
- [ ] A final summary lists: every `{{VERIFY}}` / `LEGAL REVIEW REQUIRED` item, every third-party host the app contacts, and any decision I need to make.
- [ ] Nothing was deployed to production without my confirmation.

> ⚖️ These criteria are an engineering checklist, not legal advice. Have a Norwegian privacy lawyer review the Terms, DPA and Privacy Policy before launch.
