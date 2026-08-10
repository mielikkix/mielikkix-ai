# AgentNexus — High-Level Project Document

## 1. Vision

A single, reusable AI chatbot platform that any small business — retail, services, restaurants, clinics, real estate, local shops — can configure in minutes and embed on their website, without building a chatbot from scratch.

## 2. Problem

Small businesses lose leads and customer trust when they can't answer questions instantly (hours, FAQs, product/service details). Custom chatbot development is too expensive and slow for them; generic chatbots don't know their specific business.

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
- Multi-language: English at launch, Thai and Hindi planned

### Admin dashboard
- Business profile & branding
- FAQ and document upload (knowledge base)
- Product/service catalog management
- Chatbot tone/personality settings
- Conversation history
- Leads inbox
- Business hours & contact info

### AI capabilities
- RAG over uploaded documents (pgvector)
- Intent detection (FAQ / lead / product inquiry / support)
- Context-aware multi-turn conversation
- Confidence-based fallback to rule-based / "talk to a human" responses
- Swappable LLM provider (free-tier first: Groq / Gemini / Ollama; OpenAI/Claude optional upgrade)

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

Out of scope for MVP: multi-language beyond English, human-agent live handoff (email/notification handoff is enough), advanced analytics, billing automation.

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

**Actual progress vs. this roadmap**: backend, RAG chat, widget, and dashboard (Phases 0–4) are
built. Scope has grown past the original Phase 5 polish step — plan-based feature gating, a
(simulated) checkout flow, multi-website management, and self-serve password reset all now exist,
none of which were in the original MVP scope below. See `files/FEATURES.md` for what's actually
built and working, and its "not yet built" footer for real remaining gaps (payment processing,
human handoff, multi-language, etc.) — treat that file as more current than this roadmap table.

## 9. Pricing Strategy

Superseded by the actual implemented plans — `files/FEATURES.md`'s pricing table (sourced from
`backend/app/core/plans.py`) is the current source of truth: **Free / Basic ($24/mo) / Business
($48/mo) / Growth ($96/mo)**, no free trial period (Free is a permanent tier, not a 14-day trial),
and no separate "Custom/Freelance" tier has been built. Checkout exists in the dashboard but is a
simulated flow — no real payment processor is connected yet (see `files/FEATURES.md`).

## 10. Freelance Service Angle

Offer this platform as the engine behind a "Done-for-you AI chatbot" service: you configure the tenant, upload their content, brand the widget, and hand over the dashboard — charging a setup fee plus recurring subscription, positioning the reusable platform as your unfair advantage on delivery speed.
