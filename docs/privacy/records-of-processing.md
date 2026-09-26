# Records of processing activities (GDPR art. 30)

Internal document. Mielikkix AS, org. no. `{{VERIFY: org. number}}`, `{{VERIFY: registered address}}`, Norway.
Contact for privacy matters: post@mielikkix.no. No DPO has been appointed `{{VERIFY: is a DPO required?}}`.

Last reviewed: 2026-09-26. Review this document whenever a table, integration or vendor is added.
Retention periods are listed in [retention-schedule.md](retention-schedule.md). Vendors are listed in
[subprocessor-review.md](subprocessor-review.md).

Common security measures for everything below (details on the public /security page):
- TLS for all traffic, with HSTS.
- bcrypt password hashes.
- Fernet-encrypted OAuth tokens (`apps/api/app/core/encryption.py`).
- httpOnly SameSite session cookie.
- Every API query scoped to the signed-in tenant.
- Rate limiting (slowapi).
- No personal data in application logs (`apps/api/app/core/log_redaction.py`, `tests/test_retention.py`).
- Open questions: encryption at rest and backups `{{VERIFY}}`.

## Part A: Mielikkix as controller

| # | Activity | Purpose | Legal basis | Data subjects | Data categories | Recipients | Transfers outside EEA | Where in code |
|---|---|---|---|---|---|---|---|---|
| A1 | Customer accounts | Provide the service under contract | Contract 6(1)(b) | Account holders (business owners/staff) | Name, email, bcrypt password hash, country, business profile, plan | Hostinger (hosting), Resend (email) | Resend (USA) | `users`, `businesses`, `business_settings`; `auth_service.py` |
| A2 | Sign-up agreements and consent log | Demonstrate acceptance and consent (art. 7(1)) | Legal obligation 6(1)(c) / legitimate interest 6(1)(f) | Account holders; former account holders (minimised) | Consent type, document version, timestamps, source, keyed IP hash; after deletion only a keyed email hash | Hostinger | None | `consent_records`; `consent_service.py` |
| A3 | Marketing email to account holders | Product updates and tips | Consent 6(1)(a) | Account holders who opted in | Email, name | Resend | USA | `notifications.send_marketing_email` (consent-gated, one-click unsubscribe) |
| A4 | Transactional email | Password resets, account deletion notices | Contract 6(1)(b) | Account holders | Email, name | Resend | USA | `notifications/__init__.py` |
| A5 | Website analytics (mielikkix.ai) | Understand site usage | Consent 6(1)(a) + ekomloven § 2-7b | Website visitors who accept | GA cookie IDs, pages viewed, approximate location, device | Google | USA | `website/src/lib/consent.ts` |
| A6 | Demo requests / contact | Answer enquiries | Steps before contract 6(1)(b) / legitimate interest 6(1)(f) | Prospects | Name, email, phone, company, message | Hostinger, Resend | USA (Resend) | `website/src/pages/demo.astro` → `POST /api/leads` |
| A7 | Mielikkix's own chatbot and support desk on mielikkix.ai | Answer visitors' questions | Legitimate interest 6(1)(f) | Website visitors who chat | Chat messages, optional contact details | Groq / OpenAI / Anthropic (LLM), Hostinger | USA | Mielikkix's own tenant in `conversations`; `tickets`, `ticket_messages`, `bookings` |
| A8 | Security and abuse prevention | Protect the service | Legitimate interest 6(1)(f) | All users of the API | IP address (rate limiting, in memory), server logs | Hostinger | None | `core/limiter.py`; server logs `{{VERIFY: log retention}}` |
| A9 | Accounting | Bookkeeping | Legal obligation 6(1)(c) | Paying customers | Invoicing details | `{{VERIFY: accounting system}}` | `{{VERIFY}}` | Not in this codebase |

## Part B: Mielikkix as processor (for each customer business)

Controller: the customer business. The instructions are the Terms, the DPA (/dpa) and the customer's own settings.

| # | Activity | Data subjects | Data categories | Sub-processors | Transfers outside EEA | Retention | Where in code |
|---|---|---|---|---|---|---|---|
| B1 | Chat widget conversations (RAG answers) | The customer's website visitors | Chat messages, widget session ID, optional contact details | Groq (default), Gemini (if chosen), Hostinger | USA | Customer setting: 1–365 days, default 90 | `conversations`, `messages`; `chat_service.py`; `retention_service.py` |
| B2 | Lead capture | Visitors who leave details | Name, email, phone, message, marketing-consent flag | Hostinger; Mailchimp if the customer connects it | USA (Mailchimp) | Until the customer deletes them | `leads`; `lead_service.py` |
| B3 | Voice Receptionist | Callers | Phone number, call audio (transcribed in real time, not stored), booking details | Twilio, OpenAI, Anthropic | USA | Transcripts are held only in memory during the call | `agents_voice.py` |
| B4 | Booking Assistant | People booking appointments | Name, email, phone, appointment time | Anthropic, Google Calendar (customer-connected) | USA | Calendar events sit in the customer's own calendar | `booking_service.py`, `calendar_connections` |
| B5 | Support Triage | The customer's customers | Support messages | Anthropic | USA | With the account | `support_service.py` |
| B6 | Review & Reputation | Public reviewers | Reviewer name, review text, reply drafts | OpenAI, Google Business Profile (customer-connected) | USA | With the account | `reviews`, `review_connections` |
| B7 | SEO Audit | Mostly none (website content) | Website content and metrics, GA/Search Console data | OpenAI, Google APIs (customer-connected) | USA | With the account | `seo_*` tables |
| B8 | Email Marketing | The customer's audience | Email addresses, campaign content | Mailchimp (customer's own account) | USA | In the customer's Mailchimp account | `campaigns`, `mailchimp_connections` |

Data subject requests for Part B go to the customer. See [data-subject-requests.md](data-subject-requests.md).
