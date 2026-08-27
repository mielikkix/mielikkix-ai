# CLAUDE.md — apps/agents/social-media

Place this file at `mielikkix-ai/apps/agents/social-media/CLAUDE.md`.

## What this agent does

Turns a business update ("we're running 20% off this weekend", a new
product, a plain-language description of an offer) into ready-to-post
social captions for Instagram/Facebook, in the business's own voice. A
human reviews/edits each draft and approves it to post or schedule — this
agent never posts unsupervised. Queued agent, fast-follow after the 3
flagships (see root `CLAUDE.md`'s "Current status").

## Integrations needed

- **Caption drafting**: `packages/agent-core`'s LLM client only — no
  separate integration needed for this part.
- **Image generation**: explicitly OUT of scope for the first version — no
  self-hosted image models on this VPS (root `CLAUDE.md` convention #5), and
  no external image-gen API chosen yet. The business supplies their own
  image/video for each post; this agent only writes the caption/copy.
- **Actual posting**: Meta Graph API (Instagram + Facebook Page posting).
  **Requires a per-tenant Meta OAuth connection** (business connects their
  own Instagram/Facebook Page, same OAuth-per-tenant shape as Booking
  Assistant's Google Calendar connection — see that agent's `CLAUDE.md` for
  the pattern to copy) plus a registered Meta developer app for this
  product. Both are human setup steps requiring a real Meta account —
  **defer until that account/app exists**; build draft generation and the
  approval flow first, since neither needs Meta access.

## Data this agent stores

```
SocialPost
  id, business_id, platform (instagram | facebook), source_text (what the
  business described), draft_caption, status (draft | approved | scheduled | posted | failed),
  scheduled_for, posted_at, external_post_id (Meta's own post ID once posted)
```

## Real-time or batch?

Draft generation is request/response (a business asks for a caption, gets
one back immediately). Scheduled posting is batch/scheduled work through
the shared job queue (root `CLAUDE.md`) — a standing poller checks for
`SocialPost` rows due to post, not a dedicated always-on daemon.

## Dashboard module

New "Social" tab in `apps/dashboard`, gated by entitlement: draft a post
from a plain-language description, edit/approve the generated caption,
schedule or post now, and a simple calendar/list view of past and upcoming
posts.

## Definition of done for the 8-day sprint

- [ ] Caption drafted from a plain-language business update
- [ ] Human can edit a draft before approving it
- [ ] Approved posts visible on a calendar/list view in the dashboard
- [ ] Actual Meta posting only attempted once a tenant has connected their
      account via OAuth (never silently fails for lack of connection —
      surfaces a clear "connect your account" prompt instead)
- [ ] Posts/drafts visible in dashboard, gated correctly by entitlement
- [ ] Deployed on the VPS, smoke-tested in production
