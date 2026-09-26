# Subprocessor review

Internal document. This is the working checklist behind the public /subprocessors page, which is
generated from `SUBPROCESSORS` in `website/src/config/legal.ts`. When a vendor is added or changed,
update both, and give customers `{{VERIFY: 30}}` days' notice (DPA § 5).

Before a new vendor processes personal data, check that:
1. a DPA is signed or accepted,
2. there is a transfer mechanism for any data leaving the EEA,
3. their security is documented,
4. their API data is **not** used to train their models, and
5. the vendor is listed on /subprocessors.

Last reviewed: 2026-09-26. Everything marked `{{VERIFY}}` still needs checking against the vendor's
current terms.

| Vendor | What for | Data | Location | DPA signed? | Transfer mechanism | No training on API data? | Notes |
|---|---|---|---|---|---|---|---|
| Hostinger | VPS (app, API, Postgres) + marketing-site hosting | Everything stored | `{{VERIFY: data centre region}}` | `{{VERIFY}}` | `{{VERIFY}}` (none needed if the region is in the EEA) | n/a | Encryption at rest and backups `{{VERIFY}}` |
| Groq | Chat widget LLM (default provider) | Chat messages, knowledge-base excerpts | USA | `{{VERIFY}}` | `{{VERIFY: DPF or SCCs}}` | `{{VERIFY}}` | Default for every tenant (files/LLM_MODELS.md) |
| OpenAI | Voice Receptionist, SEO, Review & Reputation | Call transcripts, review texts, site content | USA | `{{VERIFY}}` | `{{VERIFY: DPF or SCCs}}` | `{{VERIFY}}` (API default: no training) | |
| Anthropic | Booking Assistant, Support Triage | Booking and support messages | USA | `{{VERIFY}}` | `{{VERIFY: DPF or SCCs}}` | `{{VERIFY}}` (API default: no training) | |
| Google (Gemini API) | Optional tenant LLM | Chat messages | USA | `{{VERIFY}}` | `{{VERIFY: DPF or SCCs}}` | `{{VERIFY}}` (paid tier only?) | Only if a tenant picks it. The free tier may train on data, so check which tier is used |
| Google (Calendar, Business Profile, Analytics Data, Search Console, PageSpeed) | Customer-connected integrations | Appointments, reviews, site metrics | USA | Google Cloud DPA `{{VERIFY}}` | `{{VERIFY: DPF}}` | n/a | OAuth verification under way (files/GOOGLE_OAUTH_VERIFICATION.md) |
| Google Analytics | mielikkix.ai analytics (consent-gated) | Visitor usage | USA | GA data processing terms `{{VERIFY: accepted in the GA admin?}}` | `{{VERIFY: DPF}}` | n/a | Google signals and ad personalisation are off in code. GA4 retention setting `{{VERIFY}}` |
| Twilio | Voice calls, speech-to-text | Phone numbers, call audio | USA | `{{VERIFY}}` | `{{VERIFY: DPF or SCCs}}` | `{{VERIFY}}` | No call recording is enabled (`agents_voice.py`) |
| Resend | Transactional + marketing email | Email addresses, email content | USA | `{{VERIFY}}` | `{{VERIFY: DPF or SCCs}}` | n/a | |
| Mailchimp | Email Marketing agent: the **customer's own** account | Customer audience | USA | Customer ↔ Mailchimp | Customer's responsibility | n/a | Not our subprocessor. Listed as customer-connected |
| api.frankfurter.dev | Exchange rates on the pricing pages (called from the visitor's browser) | Visitor IP address only | `{{VERIFY}}` | n/a | n/a | n/a | No cookies. Disclosed on /cookies |

## Open actions
- [ ] Fill in every `{{VERIFY}}` above and copy the results into `website/src/config/legal.ts`.
- [ ] Decide whether Cal.com (mentioned in GDPR-COMPLIANCE-CLAUDE.md) is in use. It isn't referenced in
      the code as of 2026-09-26.
- [ ] Keep signed DPAs in `{{VERIFY: where}}`.
