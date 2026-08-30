# CLAUDE.md — apps/agents/review-reputation

## What this agent does

Analyzes a customer review (sentiment, topics, priority, escalation risk), drafts a
professional public response in the business's own tone, and surfaces reputation
insights/trends across a business's stored reviews. Human approval is required before
any response is treated as final -- this agent never auto-publishes anywhere (see
"Human approval" below).

## Current state

Implemented (2026-08-30): review analysis, response generation, human approval
workflow, reputation insights, trend detection, a mock review platform for local
dev/demos, dashboard module, agent router registration, and the conversational
chat endpoint. NOT implemented: any real platform integration (Google/Facebook/
TripAdvisor/Yelp/Trustpilot) -- see "Integrations needed" below for exactly what
each would require; `integrations/review_platforms/get_review_platform()` raises
`NotImplementedError` with that requirement for any of them today, rather than
pretending to work. Scheduled/batch syncing (polling a real platform on an
interval) is also not implemented -- there's no real platform to poll yet, and this
task's own instruction was explicit: "do not implement fake integrations."

## Where the code lives

Same split every other Force agent's service uses (see apps/agents/CLAUDE.md):

- `apps/api/app/models/review.py` -- the `Review` model (tenant-scoped, one row per
  review regardless of source).
- `apps/api/app/integrations/review_platforms/` -- `ReviewPlatform` /
  `ReviewResponsePublisher` ABCs (base.py) + `get_review_platform()` factory
  (`__init__.py`, same idiom as `calendar_provider.py`/`rag/providers/`) +
  `MockReviewPlatform` (`mock_platform.py`), the one real implementation, returning
  a small fixed set of clearly-fictional reviews for local dev/demos.
- `apps/api/app/services/review_service.py` -- all the actual logic: analysis,
  response generation, approval workflow, insights, trends, import/dedup, and the
  conversational `handle_chat_message()` entry point.
- `apps/api/app/api/agents_reviews.py` -- thin HTTP wrapper (`/api/agents/reviews/...`).
- `apps/dashboard/src/dashboard/pages/ReviewsPage.tsx` -- the dashboard module.

## Integrations needed (for a REAL platform, not the mock)

- **Google Reviews**: Google Business Profile API access (OAuth + a verified
  Business Profile location).
- **Facebook Reviews**: a Facebook Page access token with
  `pages_read_user_content` permission.
- **TripAdvisor**: Content API access (partner application required).
- **Yelp**: Fusion API access (developer application required).
- **Trustpilot**: Business API access (partner application required).

Each of these, once actually connected, is a new `ReviewPlatform` (and, for posting
replies back, `ReviewResponsePublisher`) implementation in
`integrations/review_platforms/`, wired into `get_review_platform()` -- no change to
`review_service.py` or the API layer, by design.

- **LLM**: `packages/agent-core`'s client, on OpenAI's cheap/fast tier
  (`LLMClient(provider="openai", model=settings.openai_mini_model)`, per
  `apps/agents/CLAUDE.md`'s tier assignment) -- single-review analysis/response
  generation, not multi-step reasoning, so it doesn't need a higher tier's cost.

## Data this agent stores

- `reviews` (`apps/api/app/models/review.py`): the review itself (platform, external
  ID, customer name, rating, text, language, review date), its analysis (sentiment,
  sentiment score, topics, positive/negative points, primary issue, priority,
  requires_human_review, escalation_reason), and its response (ai_response,
  response_tone, response_status: `none | draft | approved | rejected | published` --
  nothing sets `published` today, reserved for a future publisher integration).
- De-duplication on import is an app-level check (query before insert on
  `business_id` + `platform` + `external_review_id`), not a DB-level UNIQUE
  constraint -- same tradeoff `models/ticket.py`'s own `session_id` comment
  documents, for the same reason.

## Human approval

Never automatic. The flow is always:

```
Review -> Analyze -> Generate response (draft) -> a human reviews it in the
dashboard -> Approve (or Reject, or edit the draft first) -> publish manually
today; a future ReviewResponsePublisher integration could publish it for real,
still only after this same human approval step.
```

`approve_response()` only ever sets `response_status = "approved"` -- there is no
code path anywhere that posts a response to an external platform.

## Prompt injection defense

Review text is always placed inside `<review>...</review>` tags in a **user**-role
message, never interpolated into the system prompt itself -- the system prompt is a
fixed template per call (business name/industry/tone only), explicitly instructing
the model to treat anything inside the tags as content to analyze, never as
instructions to itself. See `review_service.py`'s own `_ANALYSIS_SYSTEM_PROMPT_TEMPLATE`
comment, and `tests/test_agents_reviews.py::test_review_text_containing_an_injection_attempt_is_treated_as_data`
for the live proof (asserts the system message sent to the LLM is byte-identical to
the fixed template regardless of what the review text contains).

## Categories, priorities, escalation reasons

All prompt-level suggested lists (`review_service.py`'s `CATEGORIES`/`PRIORITIES`/
`ESCALATION_REASONS`), not DB enums/CHECK constraints -- a new category is addable
without a migration (`Review.topics` is a plain JSON list column).

- **Priority** (`low | medium | high | critical`): "critical" always forces
  `requires_human_review = True` server-side, even if the LLM itself said
  otherwise -- same belt-and-suspenders convention `support_service.py`'s
  confidence gate uses. This agent never attempts to resolve a legal/safety issue
  itself; it only flags it.
- **Escalation reasons**: `legal_threat | safety_issue | serious_misconduct |
  discrimination | fraud | high_reputation_risk | repeated_complaint | unknown`.

## Insights and trends -- never fabricated

`get_insights()` and `get_trends()` are pure Python computation over already-stored,
already-analyzed `Review` rows -- no LLM call, and nothing is invented. Both return
`insufficient_data = True` (rather than a misleading 0%/0% comparison) when there
isn't enough real data yet.

`generate_reputation_summary()` is the one LLM call in this area, and it's
explicitly grounded: the model is given ONLY the already-computed statistics and
told never to invent a number not present in them -- its job is phrasing and
prioritization, not counting.

## Chat interaction

`POST /api/agents/reviews/chat` -- simple keyword-based intent detection (same
idiom `rag/pipeline.py`'s own `_detect_intent` already uses elsewhere), routing to
analyze / generate-response / reputation-summary. Good enough for a conversational
entry point; the structured endpoints (`/analyze`, `/generate-response`, `/insights`,
`/trends`) are the reliable path for real dashboard use.

## Dashboard module

`/dashboard/reviews` (`ReviewsPage.tsx`), gated by `review_reputation_enabled`
(Business/Growth plans -- see `core/plans.py`): overview stats (reputation score,
average rating, total reviews, positive/negative %, reviews needing attention),
insights (top positive/negative topics, AI summary, a sudden-spike alert), a review
list with priority/sentiment/attention-needed filters, and per-review actions
(Analyze, Generate/Regenerate response, Edit, Approve, Reject). "Import sample
reviews" pulls from `MockReviewPlatform` for demo purposes.

## Testing

`apps/api/tests/test_agents_reviews.py` -- sentiment (all 4 categories),
categorization, priority + server-enforced critical escalation, response generation
(positive/negative/tone override), the approve workflow never reaching "published",
prompt injection resistance, insights/trends computed only from real supplied data
(with an explicit insufficient-data case), duplicate-import dedup, cross-tenant
isolation, and the chat entry point's three intents.

## Definition of done

- [x] A review can be analyzed (sentiment, topics, priority, escalation).
- [x] A professional response can be generated, in the business's configured tone,
      matching the review's own detected language.
- [x] Critical reviews are escalated (server-enforced) with a reason.
- [x] Human approval required before a response is considered final; nothing
      auto-publishes.
- [x] Reputation insights and trends, computed only from real stored data.
- [x] Registered with the agent router (`apps/api/app/main.py`), gated by plan.
- [x] Dashboard module, gated correctly by entitlement.
- [x] Tests passing, full existing suite passing.
- [ ] A real review platform actually connected (Google/Facebook/... -- see
      "Integrations needed").
- [ ] Deployed on the VPS, smoke-tested in production.
