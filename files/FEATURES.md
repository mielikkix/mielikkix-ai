# Mielikkix — Features Built So Far

A snapshot of what's actually implemented and verified working, as of this point in development. Useful as source material for promotional/marketing copy — everything listed here is real and tested, not aspirational. Each "*Current scope*" note says honestly where a feature stops today.

*Last reviewed against the code: 2026-10-07.*

## Customer-Facing Chat Widget

- **One-line embed** — businesses add a single `<script>` tag to their site; no iframe hassle, no app to install.
- **Fully style-isolated** — mounts inside a Shadow DOM, so it never clashes with or is broken by the host site's own CSS.
- **On-brand** — configurable accent color and bot name per business.
- **Custom greeting** — the welcome message shown is pulled live from the business's own dashboard settings, not a generic default (one per configured language).
- **Formatted replies** — bot answers render real bold text and bullet/numbered lists, not raw markdown asterisks.
- **Built-in lead capture** — a contact form appears inline in the chat automatically when the bot can't fully answer or detects buying intent (English and Norwegian intent keywords).
- **Books appointments inline** — a booking-shaped message ("can I book a time on Tuesday?") opens the Booking Assistant flow right inside the chat (see Booking Assistant below).
- **Keeps the conversation across pages** — the chat survives navigating around the host site and only resets when the browser tab is closed.
- **Tells visitors they're talking to an AI** — an always-visible AI notice (EU AI Act Art. 50), plus the bot itself says it's an AI if asked mid-conversation.
- **Optional "I agree" screen** — per business, the widget can ask visitors to accept the business's privacy policy before the first message.
- **Abuse-resistant** — rate-limited per visitor so one bad actor can't spam a business's AI costs or flood their leads inbox; shared AI safety rules make the bot ignore prompt-injection attempts in visitor messages or documents, never reveal its instructions, and stay on the business's topic.

## AI That Actually Knows the Business

- **Retrieval-grounded answers (RAG)** — the bot answers from a business's own FAQs, uploaded documents, and product/service catalog, matched by meaning (multilingual embeddings), not generic web knowledge.
- **Upload almost anything** — PDF, Word, Excel, CSV, and plain text documents are all supported out of the box.
- **Import directly from a web page** — paste a URL (e.g. an existing About or FAQ page) and the bot learns from it immediately; re-fetch it later with one click when the page changes.
- **Import your whole website** — enter just a domain and every page gets discovered (sitemap, or a link crawl if there's no sitemap) and imported automatically, capped by plan and filtered by `robots.txt`, running in the background so pages appear on the Documents page as they finish.
- **Speaks the visitor's language** — replies in the language the visitor writes in (auto-detected per message), up to the number of languages the plan allows; fallback messages are translated automatically.
- **Remembers the conversation** — follow-up questions like "and the cappuccino?" after "what's the price of a latte?" are understood in context.
- **Won't make things up** — explicitly instructed to say "I don't know" rather than invent plausible-sounding but false details (hours, prices, policies) when it lacks real grounding.
- **Spots contradictions in your own knowledge base** — the dashboard flags FAQs that look like near-duplicates with different answers, so the owner can fix them before the bot picks one at random.
- **Test it before going live** — a "Test your chatbot" card in the dashboard runs the real answer pipeline without counting against the plan or creating a conversation/lead.
- **Swappable AI engine** — works with Groq (default), Google Gemini, or a self-hosted Ollama model, chosen per business.
- **Adjustable personality** — friendly, formal, concise, or playful tone, chosen per business and genuinely reflected in every reply.
- **Custom fallback message** — businesses write their own "I don't have that info" wording instead of a generic canned response.
- **Automatic intent detection** — distinguishes FAQ questions, product inquiries, support issues, booking requests, and lead-generating moments.

## The Mielikkix Force — AI Agents

Sold per agent, on top of (or without) a Chat Widget plan. Prices are fixed NOK/month excl. MVA, from `apps/api/app/core/agent_catalog.py` (which mirrors `website/src/data/pricing.ts`). A platform admin switches an agent on per business; every agent route and dashboard module checks that access on the server (`apps/api/app/services/agent_access_service.py`).

| Agent | Price | Status |
|---|---|---|
| Voice Receptionist | 590 kr | Built — Mielikkix's own number/demo only (not per-tenant yet) |
| Booking Assistant | 390 kr | Built — per-business Google Calendar |
| Support Triage | 990 kr | Built — live demo on mielikkix.ai (Mielikkix's own support, not per-tenant yet) |
| Review & Reputation | 390 kr | Built — per-business Google Business Profile connection |
| SEO Audit & Optimize | Free / Start 490 kr | Built |
| Email Marketing | 390 kr (placeholder price) | Built — per-business Mailchimp |
| Social Media, Feedback & Survey, Loyalty & Re-engagement, Quote & Invoice | — | Queued, not built |

Bundles shown on the site: any 3 agents, or the Full Crew (all of them) — `THREE_PACK_PRICE_USD` / `FULL_CREW_PRICE_USD` in `agent_catalog.py`, still placeholder prices.

### Booking Assistant

- **Books real appointments from plain language** — a visitor can type something like "I'd like to book a consultation next Tuesday afternoon" straight into the chat widget; an LLM (Claude Sonnet) parses that into a real availability search, no separate booking form to fill out first. Time-of-day words ("morning", "afternoon") actually narrow the slots offered.
- **Each business connects its own Google Calendar** — one-click "Connect Google Calendar" in dashboard Settings → Booking (OAuth, least-privilege `calendar.events` scope); the refresh token is stored encrypted. Bookings land on the business owner's own calendar. A business that hasn't connected a calendar is told so honestly — it never falls back to someone else's calendar.
- **Real availability, not guessed slots** — checks the connected calendar's actual busy times and only offers open slots inside that business's own opening hours (set in the dashboard).
- **Double-booking is impossible** — availability is re-checked at the moment of confirmation, not just when slots were first shown.
- **Real calendar event + real invite** — confirming a slot creates an actual Google Calendar event and Google emails the customer a real calendar invite automatically.
- **The business gets notified too** — a booking notification email (English or Norwegian) fires the moment a booking is confirmed.
- **Asks instead of guessing** — if a request is too vague to search a date for, it asks a clarifying question rather than inventing a date.
- **Works from voice and support chat too** — Voice Receptionist callers and Support Triage chat visitors can book through the same booking service.
- *Current scope: no cancel/reschedule yet; bookings appear in the platform-admin Bookings page, not yet in a tenant-facing Bookings tab; one calendar per business.*

### Voice Receptionist

- **Answers real inbound phone calls** — a Twilio phone number, not a demo widget; the AI (OpenAI) holds a natural spoken conversation grounded in the business's own FAQs/documents/products via the same RAG layer the chat widget uses. English and Norwegian (nb-NO) speech.
- **Books appointments by voice** — confirmation is deterministic, not left to the LLM to improvise: the agent reads back the proposed slot, name, and email ("Is that correct?") before anything is actually booked.
- **Hands off to Support Triage** — an issue that needs human follow-up becomes a support ticket mid-call.
- **Secure webhooks** — Twilio request signatures are validated, so forged webhook calls are rejected.
- **Try it in the browser** — the public `/demo/voice-receptionist` page talks to the same agent using the browser's speech recognition.
- *Current scope: verified via test calls and the public browser demo; a purchased Twilio number for live production calls is not provisioned yet, and there's no per-tenant number or dashboard call log.*

### Support Triage

- **Live on mielikkix.ai** (`/demo/support-triage`) — answers visitor questions about Mielikkix's own product; classifies each message (Claude Sonnet), answers what it's confident about, and escalates the rest.
- **Escalates to a human by email** — low-confidence or high/urgent-priority messages notify a human instead of the bot guessing, and the widget asks for the visitor's email when it doesn't have one yet.
- **Hands booking requests to Booking Assistant** — "can I book a call" opens a real booking flow instead of becoming a generic ticket.
- **Resists prompt injection** — attempts to override its instructions are declined, not answered or escalated.
- **Platform-admin ticket inbox** — every ticket and its conversation is visible to the Mielikkix operator at `/admin/tickets`.

### Review & Reputation

- **Connect Google Business Profile** — per-business OAuth, pick which location to manage, import its real Google reviews (de-duplicated on re-import).
- **Analyzes any review** — sentiment, topics, priority, risk reasons, and escalation, for imported reviews or ones pasted in directly.
- **Drafts a reply in the business's own tone** — matches the review's detected language automatically; regenerate or edit freely.
- **Human approval always required** — nothing is ever posted automatically. A person approves, and only an explicit "Publish" sends the approved reply to Google.
- **Critical reviews escalate** — legal threats, safety issues etc. are forced to human review on the server, whatever the AI said.
- **Reputation insights, never fabricated** — score, rating, positive/negative %, top topics, trends and spike alerts are computed only from real stored reviews, and honestly say "not enough data yet" instead of showing a misleading percentage.
- **Ask about your reviews** — a chat box answers questions about the business's own reviews.
- *Current scope: one Google location per business; Facebook/TripAdvisor/Yelp/Trustpilot are not built; Google API access for a real business is pending Google's verification.*

### SEO Audit & Optimize

- **Full website audit** — register a site and crawl it (starter / standard / advanced, up to 500 pages; robots.txt-aware, SSRF-safe), then get health scores for technical, on-page, performance, content and internal linking.
- **Deterministic findings engine** — technical (status codes, redirects, canonicals, indexability, sitemap coverage), on-page (titles, meta descriptions, headings, thin/duplicate content, alt text), structured-data validation, and accessibility checks — rule-based, no AI guessing.
- **Core Web Vitals** — Google PageSpeed Insights (LCP, CLS, INP, TBT, mobile + desktop) when `GOOGLE_PAGESPEED_API_KEY` is set; shows "Not measured" otherwise.
- **Prioritized action plan + AI executive summary** — findings ranked by impact, with a plain-language summary (OpenAI).
- **Keyword opportunity ideas** — AI-suggested keywords with intent and the page they belong on (search volume shown as "Not available" rather than invented).
- **Fix it with AI drafts** — generate a draft title/meta/description fix for a finding, or bulk-generate product SEO copy; every draft needs explicit human approval before it touches a live product listing.
- **History & comparison** — compare any two audits to see what improved or got worse; track each finding's status (open → in progress → completed / ignored).
- **Client-ready report** — printable report with PDF export.
- **Start tier (490 kr)**: Google Analytics + Search Console integration (per-business Google OAuth) and scheduled weekly/monthly re-audits.

### Email Marketing

- **Connect your own Mailchimp account** — per-business OAuth, then pick which audience to send to.
- **Draft → approve → send** — write a campaign (subject, sender, reply-to, HTML body), approve it, send a test email, then send now or schedule for later. Nothing goes out without a human approving it first.
- **Mailchimp does the delivery** — the campaign is created on Mailchimp and sent by Mailchimp; the dashboard shows Mailchimp's own live report (sent, opens, clicks).
- *Current scope: no AI copywriting yet (drafts are written by the user); status updates come from opening the report (polling), not a webhook.*

## Business Dashboard (`app.mielikkix.ai`)

- **Multi-tenant from the ground up** — every business's data (FAQs, documents, leads, conversations, agent data) is fully isolated from every other business's.
- **English and Norwegian (Bokmål)** — the whole dashboard, plus the emails Mielikkix sends, in the user's chosen language (switcher top right, remembered per user).
- **FAQ management** — add, edit, delete, and categorize FAQs, with a "possible conflicts" card.
- **Product/service catalog** — name, description, price, category — and the chatbot can answer questions from it (e.g. exact pricing).
- **Document library** — upload files or import from URL/website, with live embedding-status tracking (processing → embedded) and re-fetch.
- **Conversation history** — browse every visitor chat session, read the full back-and-forth, close/reopen, delete.
- **Leads inbox** — every captured lead in one place, with status tracking (new / contacted / won / lost), sorted by most recently updated.
- **Analytics overview** — conversation count, lead count, message count, and a "top visitor questions" ranking, with more detail on higher plans.
- **One-click embed snippet** — the exact `<script>` tag for a business's widget, ready to copy.
- **Full chatbot customization** — appearance, personality/tone, welcome and fallback messages (per language), languages, AI provider/model, booking calendar and opening hours, privacy settings (consent screen, conversation retention).
- **Agent modules appear only when switched on** — SEO, Reviews and Email Marketing pages are gated by the business's agent access.
- **Website management** — register the domain(s) a business runs its widget on, capped by plan; adding past the cap is blocked server-side, not just hidden in the UI.
- **Usage meter and quota emails** — the plan page shows live usage; the owner is emailed at 80% and 100% of the monthly conversation quota.
- **Currency display** — prices shown in NOK, with EUR/USD conversion selectable.
- **Self-serve password reset** — "forgot password" emails a time-limited reset link (1 hour); only the token's hash is stored.

## Privacy & GDPR

- **Sign-up consent** — Terms/Privacy acceptance recorded with the document version, country, and a separate, optional marketing opt-in.
- **Account self-service** — download all your data (export), change marketing consent, request account deletion (with a grace period you can cancel), and re-accept updated legal terms.
- **Visitor rights for your customers** — businesses set how long visitor conversations are kept (retention runs automatically) and can erase a specific visitor's data on request.
- **One-click unsubscribe** — marketing emails carry a working unsubscribe link.
- **Personal data kept out of logs** — emails/phone numbers are redacted from logged third-party errors.
- **Marketing site** — Google Analytics only after cookie consent (Consent Mode v2), self-hosted fonts, and full legal pages (privacy, terms, DPA, subprocessors, cookies, security) in English and Norwegian.
- **Internal records** — records of processing, retention schedule, data-subject-request and breach runbooks, AI Act register, subprocessor review (`docs/privacy/`).

## Platform Admin Dashboard

- **Operator-only `/admin` area** — gated by a `PLATFORM_ADMIN_EMAILS` allowlist checked server-side; anyone else is bounced back to their own `/dashboard`.
- **Every registered business, one place** — searchable/filterable/paginated list with plan, status, owner, and live usage; a detail page per business shows owners, plan limits/usage, settings, resource counts, and lets the operator switch agents on/off.
- **Platform KPIs** — total businesses, breakdown by plan and status, and a 30-day signups chart.
- **AI usage** — token usage for every LLM call (Groq chat widget, plus OpenAI/Claude agent calls tagged by feature), with totals, a daily chart, and a top-businesses ranking.
- **Bookings and Support tickets** — every booking and every Support Triage ticket/conversation.
- **Articles (blog CMS)** — write, edit and publish blog posts for mielikkix.ai (HTML sanitized on the server); publishing rebuilds the static site and uploads it to Hostinger over SFTP, with the deployment result shown per article.
- **Business lifecycle status** — `active` / `trial` / `suspended`, auto-synced with the plan; an operator can manually Suspend/Reactivate a business (suspending drops it to Free).
- **Paid plans are admin-only, on purpose** — a business's own dashboard can only self-serve down to Free (`PATCH /api/businesses/me/plan` rejects anything else with `403`), since no payment processor exists yet. Only a platform admin can set a paid plan, from the business detail page.

## Runs the Business Side Too

- **Automatic lead email notifications** — the business owner gets emailed the moment a new lead comes in.
- **Marketing-site leads sync to Mailchimp** — "Book a Free Demo" leads go to Mielikkix's own Mailchimp audience with double opt-in respected.
- **Pluggable notification delivery** — works with zero setup (logs locally) or with a real email provider (Resend) once configured.

## Marketing Website (`mielikkix.ai`)

- **Mielikkix uses its own Chat Widget** — the chat bubble on every page is the same widget customers embed, running on Mielikkix's own knowledge base.
- **Static, fast, SEO-first** — Astro site with sitemap, per-page meta tags, and schema.org structured data (JSON-LD) for answer engines.
- **Real Norwegian pages** — every page has a crawlable `/no/` version generated at build time, plus an in-page EN/NO switcher.
- **Live agent demos** — talk to Voice Receptionist, Booking Assistant, Support Triage and Review & Reputation for real; a WhatsApp Concierge demo (scripted, pending Meta approval).
- **Pricing in NOK, EUR or USD** — fixed NOK prices with live currency conversion.
- **Blog** — articles from the admin CMS, built into static pages.

## Security & Reliability

- **Tenant data isolation enforced everywhere** — every query is scoped to the authenticated business; a client's `business_id` alone is never enough to see or touch another tenant's data.
- **Encrypted third-party tokens** — Google, Mailchimp and review-platform OAuth tokens are encrypted at rest (Fernet).
- **Smart CORS** — the public widget can be embedded on any client website, while the dashboard API stays locked to known origins.
- **Rate limiting** on public chat, lead capture, auth and agent endpoints.
- **SSRF-safe URL import and crawling** — rejects attempts to fetch internal/private network addresses.
- **Security headers / CSP** on the marketing site and dashboard.
- **Automated tests in CI** — API test suite, migration check, and dashboard/widget/website builds on every push (GitHub Actions).

## Pricing Plans (Chat Widget)

Four plans. `apps/api/app/core/plans.py` and `website/src/data/pricing.ts` are the source of truth — if this table and the code ever disagree, the code wins. Prices are fixed NOK per month, excl. 25% MVA; yearly = 10 × monthly. See `docs/pricing-rules.md`.

| | Free | Start | Business ⭐ | Growth |
|---|---|---|---|---|
| Price | 0 kr | 490 kr/mo | 990 kr/mo | 1 990 kr/mo |
| Websites | 1 | 1 | 3 | 10 |
| AI conversations | 50/mo | 1,000/mo | 5,000/mo | 20,000/mo |
| Knowledge base | ✓ | ✓ | ✓ | ✓ |
| Document upload | 2 | 20 | Unlimited | Unlimited |
| Lead capture | ✓ | ✓ | ✓ | ✓ |
| Analytics | Basic | Standard | Advanced | Advanced |
| Product catalog | 10 | 100 | Unlimited | Unlimited |
| Conversation history | 7 days | 90 days | 365 days | 365 days |
| Email notifications | ✓ | ✓ | ✓ | ✓ |
| WhatsApp notifications | ✗ | ✗ | ✓* | ✓* |
| Instagram integration | ✗ | ✗ | ✓* | ✓* |
| Languages | 1 | 2 | Up to 10 | Up to 10 |
| Multi-currency | ✗ | ✓ | ✓ | ✓ |
| Custom branding | ✗ | ✓ | ✓ | ✓ |
| API access | ✗ | ✗ | ✗ | ✓ |
| Priority support | ✗ | ✗ | ✓ | ✓ |

\* *Plan-gated and toggleable from Settings, but the underlying WhatsApp Business API / Meta Instagram integration isn't built yet — enabling one returns a "coming soon" (501) response rather than pretending it works. See `NOT_YET_IMPLEMENTED_FEATURES` in `plans.py`.*

The plan key for Start is still `basic` in code; only the display name changed.

### How plan enforcement actually works

- **Conversations are a soft limit** — the owner is emailed at 80% and 100%; the widget keeps answering up to 10% over the quota, then new conversations get HTTP 402 and the widget shows its contact form instead. Conversations already in progress are never cut off. No overage charges. Resets on the 1st.
- **Other limits are hard caps** — documents, products, and websites return HTTP 402 at the cap.
- **Plan changes take effect immediately** (admin-set paid plans; self-serve only to Free).
- **Custom branding is enforced server-side**: setting a non-default widget color on a plan without `custom_branding` is rejected with a 403.
- **API access**: Growth only. A business on Growth can generate/revoke a bearer API key from the dashboard.

### Checkout

There is no payment processor (Stripe etc.). Choosing a paid plan in the dashboard shows a "payment coming soon" message; paid plans are activated by a platform admin and invoiced manually.

---

*Not yet built (known gaps, tracked separately): a real payment processor, live human-agent handoff mid-conversation, per-tenant Voice Receptionist numbers and Support Triage, booking cancel/reschedule, Facebook/TripAdvisor/Yelp/Trustpilot reviews, AI copywriting for Email Marketing, WhatsApp/Instagram channels, a signup abuse guard (one free business per verified email+phone), and the four queued agents (Social Media, Feedback & Survey, Loyalty & Re-engagement, Quote & Invoice).*
