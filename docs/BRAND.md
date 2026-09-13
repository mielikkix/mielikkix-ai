# Mielikkix Brand Definition

Status: fully populated 2026-09-13. This is now the source of truth other docs
(`files/CLAUDE.md`, `website/ARCHITECTURE.md`) should point back to.

## 1. Purpose

To make responsive, always-on customer service affordable for businesses too
small to staff a support team.

## 2. Vision (5–10 year direction)

A world where no small business loses a customer just because no one was
there to answer.

## 3. Mission (daily/actionable steps toward the vision)

We build AI chat agents trained on each business's own content, so every
customer question gets answered instantly — set up in minutes, not months.

## 4. Values (3–5 core beliefs)

Accessibility, Honesty (no fabricated social proof — already our practice),
Reliability (24/7, never misses a message), Simplicity (plain setup, plain
language).

## 5. Positioning Statement

For small businesses who can't staff round-the-clock customer support,
Mielikkix is an AI chat widget trained on your own FAQs, documents, and
product catalog that never misses a customer inquiry — delivered through
affordable, self-serve setup instead of an enterprise sales process.

## 6. Competitor Differentiation

Where Chatbase and Tidio require technical setup and price for scale,
Mielikkix is built for the SMB owner with no IT team — trained on your own
content in minutes, priced below comparable tiers, and honest about what it
can't do yet (no fabricated social proof, no vague "AI-powered everything"
claims).

## 7. Brand Personality

Competence + Sincerity (reliable, honest, straightforward, always-on) —
explicitly not Sophistication/luxury.

## 8. Brand Voice

Direct and plain-spoken, talking to a busy SMB owner — no corporate jargon,
no hype.

See the punch list (below / in conversation) for copy across the site,
dashboard, and notification templates that currently clashes with this voice
and still needs rewriting.

## 9. Brand Story (hero framework)

Hero = SMB owner losing leads after hours → Problem = can't afford 24/7
support staff → Guide = Mielikkix → Change = every inquiry answered
instantly → New life = no lost customers, no new headcount.

Not yet delivered anywhere in copy (home.json's `SOCIAL_PROOF.TEXT` is still
a placeholder list of target industries, not this narrative) — an implementation
gap for a future pass, and still blocked on a real `/about` page existing at all.

## 10. Name

**Resolved.** "Mielikkix" is canonical for all plain text — domain, code, env
vars, meta tags, docs, emails, API responses, prose. "MielikkiX" (gradient
"X") is reserved for the visual logo/wordmark treatment only, and appears
nowhere else now.

Repo-wide sweep completed 2026-09-13 (37 files). The wordmark itself
(`Header.astro`, `Footer.astro`, dashboard `Sidebar.tsx`/`AuthLayout.tsx`) was
left untouched by design.

No old-brand ("AgentNexus"/"ChatBiz") references remain anywhere, including on
disk — `marketing/Mielikkix-AI-FAQ.pdf` (the one inert leftover with stale
"AgentNexus" text) has been deleted.

## 11. Tagline

**Resolved.** "Never Miss a Customer" (and its established Norwegian
translation, "Gå aldri glipp av en kunde", already used at `home.json`
`HERO.EYEBROW`) is canonical.

Propagated to: `website/src/assets/i18n/{en,no}/footer.json`'s
`FOOTER.TAGLINE` (previously a 27-word feature sentence), the homepage meta
description (`home.json` `SEO.DESCRIPTION`, both locales), and the dashboard's
Leads/Conversations empty-states.

## 12. Brand Colors (current — already consistent, no fix needed)

Identical between `apps/dashboard/tailwind.config.js` and
`website/src/styles/global.css`:

| Role | Name | Hex (500) |
|---|---|---|
| Primary | Royal Orange (`brand` / `violet`) | `#ff6b00` |
| Secondary | Warm Gold (`gold` / `indigo`) | `#f5a623` |
| Neutral | Deep Charcoal / Soft Cream (`slate`, custom ramp) | `#1a1a1a` (900) / `#fff8f0` (50) |

Full 50–900 ramps for all three exist in both files, byte-for-byte identical.
This is the one element in the audit already fully defined — no decision
needed here.

## 13. Fonts

**Resolved.** Open Sans is the committed, real font stack — it's what
actually loads today (`website/src/styles/global.css:1`, Google Fonts).
`website/ARCHITECTURE.md` has been corrected to document Open Sans instead of
the previously-documented (and never-implemented) Sora/Inter pairing.

The declared Tailwind `fontFamily` stacks in `apps/dashboard/tailwind.config.js`
and `website/src/styles/global.css` still list `Colfax`/`Proxima Nova` ahead
of `Open Sans` as unused fallback entries — harmless (they're never fetched,
so Open Sans renders regardless) but worth trimming in a future cleanup pass;
not changed here since it wasn't part of this round's scope.

## 14. Logo

Asset: `website/public/favicon.png` — combination mark (serif "M" lettermark
+ laurel-leaf sprigs + sparkle + circuit-node motif, on a solid orange
circle, transparent background). 1283×1226px, ~940KB. The mark itself is
explicitly out of scope for now — a separate design decision.

Fixed this round:
- `apps/dashboard/index.html` now references a favicon (previously had none).
- Wordmark "X" styling is now consistent everywhere the gradient treatment is
  used: `Header.astro`, `Footer.astro`, dashboard `Sidebar.tsx`, and
  `AuthLayout.tsx` all use `.brand-gradient-text`.

Still open (technical, not brand-strategy, decisions):
- No resized favicon set (16×16 / 32×32 / 180×180 apple-touch-icon) — the
  full-detail 940KB original is reused as-is everywhere.
- `website/ARCHITECTURE.md` claims a `favicon.ico` and `favicon.svg` exist;
  they don't — only this one `.png`.
