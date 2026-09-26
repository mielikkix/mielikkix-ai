# AI Act register

Internal document: every AI system Mielikkix runs, how it is classified under the EU Artificial
Intelligence Act (Regulation (EU) 2024/1689), and what the code does to meet each obligation. Keep it
in step with the code: when you add an agent or change a safeguard, update this file in the same commit.
Items marked `{{VERIFY: ...}}` need the company's lawyer to confirm.

Last reviewed: 2026-09-26

## Our role

- **Provider** of the AI systems below: we build them on top of general-purpose models from OpenAI,
  Anthropic and Groq (see `files/LLM_MODELS.md` and `/subprocessors`). We do not train or fine-tune models.
- **Deployer** of the same systems on mielikkix.ai (site chat widget, agent demos, voice line).
- Our customers are **deployers** of the widget and agents on their own sites. Terms section 6 makes them
  keep the AI notices and take responsibility for AI content they publish.

## Norway

Norway is bound through the EEA Agreement once the AI Act is incorporated, and a national act (KI-loven)
names the supervisory authority. `{{VERIFY: EEA incorporation date, KI-loven status, and the Norwegian
application dates for art. 4, 5 and 50}}`. We apply the EU dates below as the baseline.

## Classification

| System | Where | Model | Risk class | Why |
|---|---|---|---|---|
| Chat Widget (RAG Q&A, lead capture) | `apps/api/app/rag/`, `services/chat_service.py` | Per business (Groq default) | Limited risk: art. 50(1) interaction | Talks directly to the public |
| Voice Receptionist | `apps/api/app/api/agents_voice.py` | OpenAI | Limited risk: art. 50(1) | Talks directly to callers |
| Support Triage | `services/support_service.py` | Anthropic | Limited risk: art. 50(1) | Talks to site visitors; priority label is internal, no legal effect |
| Booking Assistant | `services/booking_service.py` | Anthropic | Limited risk: art. 50(1) | Parses requests; a person confirms every booking |
| Review & Reputation | `services/review_service.py` | OpenAI (mini) | Minimal risk | Drafts for the business; published only after approval |
| SEO Audit & Copywriter | `services/seo_*.py` | OpenAI (mini) | Minimal risk | Drafts for the business; approved before use |

**Prohibited practices (art. 5):** none. No emotion recognition from biometric data, no manipulation or
exploitation of vulnerabilities, no social scoring, no biometric identification. Review "sentiment" is
analysis of written text about a business, not emotion recognition of a person.

**High-risk (art. 6, Annex III):** none. No use in employment, education, credit, insurance, essential
services, law enforcement or biometrics. Re-check this if an agent is ever offered for one of those uses.

## Obligations and how we meet them

| Obligation | Applies from (EU) | Status | Where |
|---|---|---|---|
| Art. 50(1): tell people they are interacting with an AI | 2 Aug 2026 | Done | Widget notice on every conversation (`ChatWindow.tsx`), optional "I agree" screen (`ConsentGate.tsx`), voice greeting (`_GREETING` in `agents_voice.py`), AI notice on the support and booking demos. Every customer-facing prompt also tells the model to say it is an AI when asked and never claim to be human (`AI_SAFETY_RULES` in `packages/agent-core`). Customers cannot switch the notice off. |
| Art. 50(2): mark AI-generated text/audio in a machine-readable way | 2 Aug 2026 | **Open** | `{{VERIFY: whether chat replies and drafts (review replies, SEO copy) need machine-readable marking, or fall under the "assistive function / not substantially altered" exception, and what the Commission's marking code of practice requires}}`. Voice uses the telephony provider's standard text-to-speech. |
| Art. 50(4): disclose AI-generated text published on matters of public interest | 2 Aug 2026 | Not applicable today | Customers' marketing copy and review replies are not public-interest publications; Terms section 6 puts publication responsibility on the customer. Revisit if we publish AI-written articles on mielikkix.ai without human editorial review. |
| Art. 4: AI literacy of staff | 2 Feb 2025 | **Open** | `{{VERIFY: short internal AI-literacy note/training for everyone who builds, sells or supports the agents}}` |
| Human oversight (good practice; required for high-risk only) | n/a | Done | Review replies need approval before publishing; SEO drafts need approval; bookings need an explicit "yes"; Support Triage escalates to a person when unsure. |

## Safeguards in the code

- **Prompt injection:** retrieved documents are wrapped in `<reference>` tags and the shared rules say
  reference material and visitor messages are information, never instructions (`AI_SAFETY_RULES`,
  `rag/providers/base.py:context_block`). Review text is fenced the same way (`review_service.py`).
- **No free general-purpose assistant:** answers only from the business's own content; off-topic requests
  are declined.
- **Cost and abuse limits:** every public LLM endpoint is rate-limited per IP and caps input size
  (chat 2,000 characters, booking 1,000, review demo 5,000, voice demo 1,000). Tests: `tests/test_ai_guards.py`.
- **Tool use:** the voice agent can only create a booking after the caller explicitly confirms; the server
  checks this itself, not only the prompt.
- **Output rendering:** AI replies are shown as text (React, `textContent`, or escaped HTML), never as
  raw HTML.
- **Tenant isolation:** retrieval is filtered by `business_id`, so one business's content never reaches
  another's assistant.
- **Data:** see `records-of-processing.md` and `retention-schedule.md`.
