# CLAUDE.md — apps/agents/support-triage

Read `apps/agents/CLAUDE.md` first (shared conventions across the three
flagship agents) — this file covers only what's specific to this one.

## What this agent does

Powers a chat widget, classifies incoming messages, answers what it
confidently can, drafts replies for the rest, and escalates to a human by
email when it should. It was the fix for a gap flagged in the site review on
Aug 22, 2026 (`website/` then had only a static chat-widget mockup, no live
widget) — that gap is closed: `public/support-chat-widget.js` now runs live
sitewide, embedded via `Layout.astro`.

**Not the same thing as the product's existing chat widget**
(`apps/dashboard/src/widget`, embedded on tenant businesses' own sites for
their customers). This widget lives on `website/` and talks to visitors of
mielikkix.ai itself.

## Integrations needed

- **LLM**: `packages/agent-core`'s client, on Anthropic Claude Sonnet
  (`LLMClient(provider="anthropic")`, per `apps/agents/CLAUDE.md`'s tier
  assignment) — classification (category, priority, confidence) and reply
  drafting.
- **Database**: `packages/db` — tickets, messages, escalation state
  (tenant-scoped like everything else; here the "tenant" is the platform
  itself, since this widget serves mielikkix.ai's own visitors).
- **Escalation email**: `apps/api/app/notifications` (Resend provider) — do
  not add a second Resend integration.
- **Booking Assistant handoff**: direct call into
  `apps/agents/booking-assistant`'s `create_booking(...)` (same process —
  see `apps/agents/CLAUDE.md`) when a chat visitor asks to book/reschedule.
- **Voice Receptionist handoff**: accepts a direct function call from Voice
  Receptionist when a caller has an issue needing human follow-up (see that
  agent's `CLAUDE.md`).
- **Chat widget UI**: a small React component embedded in `website/` as an
  Astro `client:load` island — talks to this agent's public
  `/api/agents/support/chat/message` route.

## Data this agent stores

```
Ticket
  id, session_id, created_at, channel (web | voice), status (open | escalated | resolved),
  category, priority (low | medium | high | urgent), confidence,
  customer_name, customer_email, customer_phone

TicketMessage
  id, ticket_id, role (user | agent | human), content, created_at
```

(`TicketMessage`, not `Message` — `apps/api/app/models/conversation.py`
already has a `Message` class/table for the product's own tenant-facing
chat widget; this is a different, platform-level concept and needed its
own name to avoid colliding with it.)

## Real-time or batch?

Request/response, like Booking Assistant — not real-time in the way Voice
Receptionist is. No special load-testing concerns beyond the normal path.

## Flow

1. Visitor opens the chat widget on `website/` (or Voice Receptionist calls
   this agent's ticket function on a caller's behalf) → a `Ticket` + first
   `Message` are created.
2. The LLM classifies the message: `category`, `priority`, and a
   `confidence` score for whether it can be answered directly.
3. **High confidence, FAQ-answerable** → the agent drafts and sends a reply
   itself; ticket stays `open` (or auto-closes if it's a simple resolved
   question).
4. **Low confidence** (below `ESCALATION_CONFIDENCE_THRESHOLD`) **or**
   high/urgent priority (billing disputes, outages, anything sensitive) →
   escalate: mark the ticket `escalated`, email the support inbox via
   Resend with the full thread, tell the visitor a human will follow up.
5. **Booking-related message** ("I need to reschedule", "can I book a
   call") → call Booking Assistant's `create_booking(...)` and relay the
   result instead of triaging it as a support issue.
6. Every message is persisted, so the full conversation is visible to
   whoever picks up the escalation.

## Ticket function (for Voice Receptionist to call)

Exposed as a plain importable function, not an HTTP endpoint:

```
support_triage.service.create_ticket(
    channel: str, customer_name: str, customer_phone: str, issue_description: str,
) -> TicketResult  # ticket_id, status: "open" | "escalated"
```

## Widget embed contract

```
POST /api/agents/support/chat/message
Body: { "session_id": str, "message": str, "customer_email": str | null }
Response: { "reply": str, "escalated": bool, "ticket_id": str }
```

- CORS locked to the marketing site's own domains — this endpoint should not
  be openly callable from anywhere.
- `session_id` ties a visitor's messages together into one `Ticket` without
  requiring login.

## Development phases

1. **Phase 0 — Skeleton**: `Ticket`/`Message` tables in `packages/db`, a
   bare `/api/agents/support/chat/message` route that just echoes back (no
   AI yet) — prove the plumbing and CORS setup work from a local `website/`
   dev server.
2. **Phase 1 — Classification + FAQ**: add agent-core-backed classification
   and direct answering for confidently-known questions.
3. **Phase 2 — Escalation**: implement the confidence/priority threshold
   logic and the Resend escalation email.
4. **Phase 3 — Booking handoff**: wire the direct call into Booking
   Assistant's `create_booking(...)`.
5. **Phase 4 — Widget**: build the chat widget component and embed it in
   `website/`, replacing the static mockup on the homepage.
6. **Phase 5 — Voice integration**: implement `create_ticket(...)` for Voice
   Receptionist to call.
7. **Phase 6 — Deploy**: wire into the shared modular agent process behind
   Caddy at `api.mielikkix.ai/api/agents/support/...`, point the production
   widget at it.
8. **Phase 7 — Tests**: classification edge cases, the escalation
   threshold, and CORS restrictions.

## Dashboard module

New "Support" tab in `apps/dashboard` (platform-admin scope, not per-tenant
— see `apps/api/app/core/dependencies.py`'s `require_platform_admin`, since
this widget serves mielikkix.ai's own visitors, not tenant customers):
ticket inbox, escalation status, conversation view.

## Definition of done for the 8-day sprint

- [ ] Escalation actually fires (and only fires) when it should — test both
      a confident FAQ answer and a low-confidence/urgent one
- [ ] Widget CORS rejects requests from origins outside the allowed list
- [ ] A booking-shaped message is correctly routed to Booking Assistant
      instead of being triaged as a generic ticket
- [ ] Voice Receptionist handoff creates a ticket end-to-end
- [ ] Widget live on `website/`, replacing the static mockup
- [ ] Deployed on the VPS, smoke-tested in production
