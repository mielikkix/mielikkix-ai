# Mielikkix — High-Level Project Document

## 1. Vision

A single, reusable AI chatbot platform that any business — retail, services, restaurants, clinics, real estate, local shops — can configure in minutes and embed on their website, without building a chatbot from scratch.

## 2. Problem

Businesses lose leads and customer trust when they can't answer questions instantly (hours, FAQs, product/service details). Custom chatbot development is too expensive and slow for them; generic chatbots don't know their specific business.

## 3. Solution

A multi-tenant SaaS chatbot where each business:
- Uploads its FAQs, documents, and product/service list.
- Gets a branded chat widget (colors, name, tone) embeddable via one `<script>` tag.
- Gets AI answers grounded in *their* content (RAG), with rule-based fallback.
- Captures leads automatically and can hand off to a human.
- Manages everything from a simple admin dashboard.

## 4. Target Users

- **Small business owners** (non-technical) — configure and use the dashboard.
- **You (operator/freelancer)** — onboard clients, customize branding, maintain the platform. Now has a dedicated tool for this: a platform-admin dashboard at `/admin` (see `files/FEATURES.md`), separate from each business's own `/dashboard`.
- **End customers** on the business's website — chat with the widget.

## 5. Core Features

### Customer-facing widget
- Responsive chat widget (desktop + mobile)
- Natural-language Q&A grounded in business data
- Product/service recommendations
- Lead capture form (name, email, phone, message)
- Human handoff
- Multi-language: configurable per business (auto-detects the visitor's language), capped by plan — none on Free, 2 languages on Basic, up to 10 on Business/Growth (see `files/FEATURES.md`); no specific language list is hardcoded

### Admin dashboard
- Business profile & branding
- FAQ and document upload (knowledge base)
- Product/service catalog management
- Chatbot tone/personality settings
- Conversation history
- Leads inbox
- Business hours & contact info

### AI capabilities
- RAG over uploaded documents, FAQs and products (multilingual embeddings in Postgres)
- Intent detection (FAQ / lead / product inquiry / support)
- Context-aware multi-turn conversation
- Confidence-based fallback to rule-based / "talk to a human" responses
- Swappable LLM provider for the chat widget (Groq / Gemini / Ollama); Force agents use OpenAI and Anthropic Claude (see `files/LLM_MODELS.md`)

## 6. Success Criteria

- MVP live within 6–8 weeks.
- Demoed to at least 3 small businesses.
- At least one business paying a monthly subscription.
- Usable as a portfolio piece for AI Engineer / AI Product Developer roles.

## 7. MVP Scope

1. Website chat widget (embed script)
2. Business-specific FAQ answering
3. AI answers from uploaded documents (RAG)
4. Lead capture
5. Admin dashboard: FAQs, documents, leads
6. Basic analytics (conversation count, lead count, top questions)
7. One-click embed script

Out of scope for MVP: human-agent live handoff (email/notification handoff is enough), billing automation (checkout is simulated — no real payment processor). Multi-language and tiered analytics, both listed here as out of scope originally, have since shipped as plan-gated features — see §8.

## 8. Roadmap

| Phase | Duration | Goal |
|---|---|---|
| Phase 0 — Setup | Week 1 | Repo, CI, Docker, base auth, DB schema |
| Phase 1 — Core backend | Weeks 2–3 | FastAPI, multi-tenant models, FAQ CRUD, document upload + embeddings |
| Phase 2 — RAG + chat API | Weeks 3–4 | LangChain pipeline, intent detection, chat endpoint |
| Phase 3 — Widget | Weeks 4–5 | React embeddable widget, connects to chat API |
| Phase 4 — Dashboard | Weeks 5–6 | React admin app: FAQs, documents, leads, settings |
| Phase 5 — Polish & deploy | Weeks 6–7 | Analytics, branding, deploy to free-tier host, embed script |
| Phase 6 — Pilot | Week 8 | Onboard 3 pilot businesses, gather feedback |

**Actual progress vs. this roadmap** (as of 2026-10-07): Phases 0–5 are built, and scope has
grown well past the original MVP:

- **Chat Widget** — RAG over FAQs/documents/products (embedding-matched), whole-website import,
  multi-language replies, lead capture, inline booking, AI notice + optional consent screen,
  conversation kept across pages, soft conversation limit with 80%/100% emails.
- **Dashboard** — English + Norwegian (Bokmål), plan/usage page, knowledge-conflict check,
  "test your chatbot", privacy settings, per-agent modules.
- **Platform admin** (`/admin`) — businesses, plans, agent access, AI usage, bookings, support
  tickets, and a blog CMS that publishes to the marketing site.
- **Mielikkix Force agents** — Voice Receptionist, Booking Assistant (per-business Google
  Calendar), Support Triage (live on mielikkix.ai), Review & Reputation (Google Business
  Profile), SEO Audit & Optimize (free + Start tier), Email Marketing (Mailchimp). Four more
  agents are queued.
- **GDPR** — consent records, account export/deletion, visitor retention/erasure, consent-gated
  analytics, legal pages in English and Norwegian, internal privacy records.

See `files/FEATURES.md` for the full, verified list and its "not yet built" footer — treat that
file as more current than this roadmap table.

## 9. Pricing Strategy

Superseded by the implemented prices — fixed NOK per month, excl. MVA (`apps/api/app/core/plans.py`,
`apps/api/app/core/agent_catalog.py`, `website/src/data/pricing.ts`; rules in
`docs/pricing-rules.md`):

- **Chat Widget**: Free / Start (490 kr) / Business (990 kr) / Growth (1 990 kr). Free is a
  permanent tier, not a trial. Yearly = 10 × monthly.
- **Force agents**: sold per agent (e.g. Booking Assistant 390 kr, Voice Receptionist 590 kr,
  Support Triage 990 kr; SEO Audit & Optimize free or Start 490 kr), or as a 3-pack / Full Crew
  bundle.
- No payment processor yet — paid plans are switched on by a platform admin and invoiced manually.

## 10. Freelance Service Angle

Offer this platform as the engine behind a "Done-for-you AI chatbot" service: you configure the tenant, upload their content, brand the widget, and hand over the dashboard — charging a setup fee plus recurring subscription, positioning the reusable platform as your unfair advantage on delivery speed.
