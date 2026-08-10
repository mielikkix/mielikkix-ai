# AgentNexus — Features Built So Far

A snapshot of what's actually implemented and verified working, as of this point in development. Useful as source material for promotional/marketing copy — everything listed here is real and tested, not aspirational.

## Customer-Facing Chat Widget

- **One-line embed** — businesses add a single `<script>` tag to their site; no iframe hassle, no app to install.
- **Fully style-isolated** — mounts inside a Shadow DOM, so it never clashes with or is broken by the host site's own CSS.
- **On-brand** — configurable accent color and bot name per business.
- **Custom greeting** — the welcome message shown is pulled live from the business's own dashboard settings, not a generic default.
- **Formatted replies** — bot answers render real bold text and bullet/numbered lists, not raw markdown asterisks.
- **Built-in lead capture** — a contact form appears inline in the chat automatically when the bot can't fully answer or detects buying intent.
- **Abuse-resistant** — rate-limited per visitor so one bad actor can't spam a business's AI costs or flood their leads inbox.

## AI That Actually Knows the Business

- **Retrieval-grounded answers (RAG)** — the bot answers from a business's own FAQs, uploaded documents, and product/service catalog — not generic web knowledge.
- **Upload almost anything** — PDF, Word, Excel, CSV, and plain text documents are all supported out of the box.
- **Import directly from a web page** — paste a URL (e.g. an existing About or FAQ page) and the bot learns from it immediately, no copy-pasting content into forms.
- **Import your whole website** — enter just a domain and every page gets discovered (sitemap, or a link crawl if there's no sitemap) and imported automatically, capped by plan and filtered by `robots.txt`, running in the background so pages appear on the Documents page as they finish.
- **Remembers the conversation** — follow-up questions like "and the cappuccino?" after "what's the price of a latte?" are understood in context, not answered as an isolated, disconnected question.
- **Won't make things up** — explicitly instructed to say "I don't know" rather than invent plausible-sounding but false details (hours, prices, policies) when it lacks real grounding.
- **Swappable AI engine** — works with Groq, Google Gemini, or a self-hosted Ollama model; free-tier friendly by default.
- **Adjustable personality** — friendly, formal, concise, or playful tone, chosen per business and genuinely reflected in every reply.
- **Custom fallback message** — businesses write their own "I don't have that info" wording instead of a generic canned response.
- **Automatic intent detection** — distinguishes FAQ questions, product inquiries, support issues, and lead-generating moments.

## Admin Dashboard

- **Multi-tenant from the ground up** — every business's data (FAQs, documents, leads, conversations) is fully isolated from every other business's.
- **FAQ management** — add, edit, delete, and categorize FAQs.
- **Product/service catalog** — name, description, price, category — and the chatbot can actually answer questions from it (e.g. exact pricing).
- **Document library** — upload files or import from URL, with live embedding-status tracking (processing → embedded).
- **Conversation history** — browse every visitor chat session, expand to read the full back-and-forth, delete individual sessions.
- **Leads inbox** — every captured lead in one place, with status tracking (new / contacted / won / lost).
- **Analytics overview** — conversation count, lead count, message count, and a "top visitor questions" ranking, so a business can see what people actually ask.
- **One-click embed snippet** — the exact `<script>` tag for a business's widget, ready to copy.
- **Full chatbot customization** — tone, welcome message, fallback message, AI provider/model, and contact info, all editable from Settings.
- **Website management** — register the domain(s) a business runs its widget on, capped by plan (1 on Free/Basic, 3 on Business, 10 on Growth); adding past the cap is blocked server-side, not just hidden in the UI.
- **Self-serve password reset** — "forgot password" emails a time-limited reset link (1 hour); the raw token is never stored, only its hash, so a database read alone can't produce a usable link.

## Platform Admin Dashboard

- **Operator-only `/admin` area** — reachable at `app.agentnexus.tech/admin` (or `/admin` on the local dev server), visually distinct from the tenant dashboard, gated by a `PLATFORM_ADMIN_EMAILS` allowlist checked server-side — a business owner who isn't on the list is bounced straight back to their own `/dashboard`, no error page, no data leak.
- **Every registered business, one place** — searchable/filterable/paginated list of every business on the platform with plan, status, owner, and live usage counts; a drill-down page per business shows its owners, plan limits/usage, chatbot settings, and resource counts.
- **Platform KPIs** — total businesses, breakdown by plan and status, and a 30-day signups chart.
- **Groq API token usage** — per-call token counts are now logged for every Groq-backed chat reply, rolled up into totals, a daily chart, and a top-businesses-by-usage ranking, filterable to a single business.
- **Business lifecycle status** — `active` / `trial` / `suspended` now means something: a paid plan sets a business to `active`, dropping back to Free reverts it to `trial`. An operator can also manually **Suspend**/**Reactivate** a business from its detail page — suspending also drops it to the Free plan, mirroring what a failed/cancelled payment would do once real billing exists (it doesn't yet, so this stays a manual admin action for now).
- **Paid plans are admin-only, on purpose** — a business's own dashboard can only ever self-serve down to Free (`PATCH /api/businesses/me/plan` rejects anything else with a `403`). Since no payment processor is connected anywhere in the app, letting that endpoint accept paid values would mean anyone who called the API directly (not just through the website) could hand themselves a free Growth plan. Only a platform admin can put a business on a paid plan — a **"Set plan…"** control on the business detail page — for testing, demos, or manually activating a customer who paid another way until real billing is wired up.

## Runs the Business Side Too

- **Automatic lead email notifications** — the business owner gets emailed the moment a new lead comes in, instead of needing to check the dashboard manually.
- **Pluggable notification delivery** — works with zero setup (logs locally) or with a real email provider (Resend) once configured.

## Security & Reliability

- **Tenant data isolation enforced everywhere** — every query is scoped to the authenticated business; a client's `business_id` alone is never enough to see or touch another tenant's data.
- **Smart CORS** — the public widget can be embedded on literally any client website, while the admin dashboard API stays locked to known origins.
- **Rate limiting** on both the public chat and lead-capture endpoints.
- **SSRF-safe URL import** — rejects attempts to fetch internal/private network addresses.
- **Fast, reliable startup** — the AI model warms up in ~5 seconds, not the 90+ seconds it took before a caching fix.

## Pricing Plans

Four plans: a genuinely usable free tier to let customers experience the product, plus three paid tiers to convert and grow them. `app/core/plans.py` is the single source of truth these numbers are pulled from — if the two ever disagree, the code wins.

| | Free | Basic | Business ⭐ | Growth |
|---|---|---|---|---|
| Price | $0 | $24/mo | $48/mo | $96/mo |
| Websites | 1 | 1 | 3 | 10 |
| AI conversations | 50/mo | 1,000/mo | 5,000/mo | 20,000/mo |
| Knowledge base | ✓ | ✓ | ✓ | ✓ |
| Document upload | 2 | 20 | Unlimited | Unlimited |
| Lead capture | ✓ | ✓ | ✓ | ✓ |
| Analytics | Basic | Standard | Advanced | Advanced |
| Product catalog | 10 | 100 | Unlimited | Unlimited |
| Conversation history | 7 days | 90 days | Unlimited | Unlimited |
| Email notifications | ✓ | ✓ | ✓ | ✓ |
| WhatsApp notifications | ✗ | ✗ | ✓* | ✓* |
| Instagram integration | ✗ | ✗ | ✓* | ✓* |
| Multi-language | ✗ | 2 languages | Up to 10 languages | Up to 10 languages |
| Multi-currency | ✗ | ✓ | ✓ | ✓ |
| Custom branding | ✗ | ✓ | ✓ | ✓ |
| API access | ✗ | ✗ | +$12/mo add-on | ✓ |
| Priority support | ✗ | ✗ | ✓ | ✓ |

\* *Plan-gated and toggleable from Settings, but the underlying WhatsApp Business API / Meta Instagram integration isn't built yet — attempting to actually enable one currently returns a "coming soon" (501) response rather than pretending it works. See `NOT_YET_IMPLEMENTED_FEATURES` in `app/core/plans.py`.*

### How plan enforcement actually works

- **Limits are hard caps, on every plan, including paid ones.** Hitting a monthly conversation/document/product/website cap returns HTTP 402 and blocks the action — there's currently no overage billing or grace period on any tier. An in-progress conversation that started before the cap was hit is never cut off mid-thread, but a *new* one won't start.
- **Plan changes take effect immediately** — choosing a new plan (or the free tier) updates `business.plan` in the same request, no waiting for a billing cycle boundary.
- **Custom branding is enforced server-side**, not just hidden in the UI: setting a non-default widget color on a plan without `custom_branding` is rejected with a 403.
- **API access**: available outright on Growth; on Business only via a toggleable "+$12/mo" add-on (`business.api_access_addon`). Once enabled, a business can generate/revoke a bearer API key from the dashboard.

### Checkout

Choosing a paid plan opens a checkout modal (card name/number/expiry/CVC with client-side Luhn + expiry validation) before switching plans — **this is a simulated payment flow**: no processor (Stripe, PayPal, etc.) is connected, no card details are sent or stored anywhere, and the "payment" is just a UI delay before the same plan-switch endpoint the free tier uses. The modal says as much to the user. Wiring up a real payment processor is tracked below as not yet built.

---

*Not yet built (known gaps, tracked separately): live human-agent handoff mid-conversation, business-hours-aware responses, multi-language support beyond the plan gate itself, a real payment processor (checkout is simulated — see above), conversation overage billing, usage-threshold nudge emails, annual billing, and a signup abuse guard (one free business per verified email+phone) for the free tier. WhatsApp/Instagram notification channels are plan-gated in the UI but have no real integration behind them yet.*
