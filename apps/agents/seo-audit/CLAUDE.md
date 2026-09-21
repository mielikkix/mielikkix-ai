# CLAUDE.md — apps/agents/seo-audit (SEO Audit & Optimization Agent; folder renamed from seo-copywriter)

Read the root `CLAUDE.md` and `apps/agents/CLAUDE.md` first. This file is
this agent's own spec — it now covers two things: the SEO Copywriter that's
already live, and the SEO Audit & Optimization Agent it was upgraded into
(the whole reason the folder was renamed from `seo-copywriter`). **The
copywriter keeps working unchanged throughout this upgrade** — nothing
below replaces it.

## Pricing (resolved)

Sold in two tiers under the single `seo_audit_optimization` entitlement key
(access is still on/off — the tiers are a pricing/feature-copy distinction,
not a second entitlement gate; see `app/core/agent_catalog.py`):

- **Free — "SEO Audit & Optimize"**: every capability built through Stage 11
  below (crawl + technical/on-page findings, action plan, executive summary,
  keyword ideas, history/comparison, client report with PDF export).
- **Paid — "Professional SEO Audit & Optimization"**, 29 901 kr: everything
  in Free, plus a longer roadmap of enterprise crawler capabilities (crawl
  scheduling, JS rendering, GA/Search Console/PageSpeed integrations,
  structured-data/accessibility checks, etc.) modeled on Screaming Frog's
  feature set. **Most of these are marketing roadmap items, not built** —
  each one is labeled `(coming soon)` in `agent_catalog.py`, the same
  convention `PlanPage.tsx` already uses for `PlanFeatures` that are sold
  but not yet wired (WhatsApp notifications, Instagram integration). Do not
  remove the `(coming soon)` suffix from one of these until it's actually
  implemented — the whole point of that convention is that this repo never
  lets priced copy imply a capability that doesn't exist yet (this file's
  own "no fabricated findings" rule, applied to sales copy instead of audit
  data).

## Professional tier roadmap (business direction, 2026-09-20)

**The strategic problem this section answers**: SEO Audit & Optimize's crawl
itself is not the product — Screaming Frog (free up to 500 URLs, £199/yr for
more) and Ahrefs Webmaster Tools (free forever for a verified site) already
do deterministic crawling better and cheaper than a small team can ever
match. Building Professional as "more crawler, like Screaming Frog" is a
losing strategy — it chases feature-parity with a 10+-year-old dedicated
crawler aimed at technical SEO consultants, a different buyer than
Mielikkix's actual customer (a small-business owner with no SEO expertise).

**The actual differentiator, and the one to build toward**: neither
Screaming Frog nor Ahrefs turns a finding into an *actual fix* — they stop
at diagnosis. This agent already has the one thing they don't: the SEO
Copywriter integration (Part 1 below, wired to findings since Stage 7) that
generates the real replacement title/meta/content for a human to approve.
Professional's roadmap should sharpen that gap — AI-driven remediation and
richer, real business-data-informed prioritization — not chase raw crawler
configurability that this agent's actual buyer would never touch anyway.

Every "(coming soon)" item on the Professional tier (`app/core/
agent_catalog.py`) was re-sorted against that lens:

**Building now:**
- Google Analytics integration + Search Console integration — real traffic
  and search-performance data (impressions/clicks/position) per crawled
  page, so the action plan can prioritize by "losing traffic AND broken"
  instead of severity alone. This is the biggest lever for making the
  action plan/executive summary smarter, and the first thing being built
  (see the staged plan below, continuing from Stage 11).

**Planned next, in priority order (not started):**
- Scheduled recurring audits — turns a one-time report into ongoing
  monitoring; also the natural tie-in to the "Ongoing SEO" retainer already
  on the marketing site (`website/src/pages/agent-pricing.astro`).
- Structured data validation, Accessibility auditing — deterministic
  on-page checks (same shape as the existing technical/on-page analyzers)
  that feed richer findings into the AI summary/action plan.
- PageSpeed Insights integration is **already built** (Stage 8,
  `GooglePageSpeedProvider`) and already listed under the *Free* tier, not
  Professional — it just needs `GOOGLE_PAGESPEED_API_KEY` configured to stop
  returning "Not measured". Not a Professional-exclusive item; don't
  re-list it there.

**Not being built — remove from Professional's marketing copy rather than
leaving as `(coming soon)` forever, and removed from `agent_catalog.py`**
(crawler feature-parity with Screaming Frog, aimed at a technical operator
this agent's buyer isn't): Custom crawl configuration, Save & reopen past
crawls, JavaScript rendering, Near-duplicate content detection, Custom
robots.txt testing, Mobile usability checks, AMP crawling & validation,
Spelling & grammar checks, Custom source code search, Custom extraction,
Custom JavaScript, Link metrics integration, Forms-based authentication,
Segmentation, Looker Studio crawl report, **and "Crawl with OpenAI &
Gemini"** (resolved 2026-09-20: dropped as redundant with what this agent
already does — the LLM executive summary and keyword ideas are already
"crawling with AI" in a targeted way; a generic per-page LLM-classification
pass didn't have a concrete use case). `(coming soon)` is a promise to
eventually ship it — leaving a permanently-not-planned item labeled that
way is the same kind of overselling this file's own "no fabricated
findings" rule already forbids for audit data; it applies to sales copy too.

**Resolved 2026-09-20 — kept:** "Priority technical support" stays on the
Professional tier. This is an ops/staffing commitment, not something to
build in code — there is a real intent to actually staff it for paying
customers, so it's not subject to the "(coming soon)" removal rule above
the same way a missing feature is. If that intent ever changes, drop it
from `agent_catalog.py` rather than leaving an unfulfillable promise.

## Part 1 — SEO Copywriter (live, unchanged)

Bulk-generates product descriptions and SEO metadata (title tag, meta
description) for a business's existing product catalog
(`apps/api/app/models/product.py`), written to actually target real search
intent rather than keyword-stuffed filler. A human reviews and approves
each draft before it overwrites anything live.

- Service/API/UI: `apps/api/app/services/seo_service.py`,
  `apps/api/app/api/agents_seo.py` (`/api/agents/seo/...`),
  `apps/dashboard/src/dashboard/pages/SeoPage.tsx`.
- Data: `SeoDraft` (`apps/api/app/models/seo_draft.py`) — a separate table
  from `Product`, never written to directly on generation. Only
  `approve_draft` copies onto the real `Product` row (and re-embeds it for
  RAG). `Product.seo_title`/`Product.meta_description` were added by this
  agent's own migration (`d4f7a1b8e3c2_add_seo_copywriter.py`).
- Entitlement: `PlanFeatures.seo_copywriter_enabled`
  (`apps/api/app/core/plans.py`), checked via `plan_service.require_feature`
  — the only gate, nowhere else (root convention #2).
- LLM: OpenAI cheap/fast tier (`LLMClient(provider="openai",
  model=openai_mini_model)`) — routine generation from a product's own
  fields, no multi-step reasoning.
- Tests: `apps/api/tests/test_agents_seo.py` — entitlement, generate,
  cross-tenant isolation, malformed/failed LLM response handling, list
  filter, approve (copies + re-embeds), reject (no-op on live data), 404s.
  **All of these must keep passing after every stage of the upgrade below.**

## Part 2 — Upgrade: SEO Audit & Optimization Agent

### Goal

Extend the Copywriter into a broader agent that can technically audit a
business's website(s) — crawlability, indexability, on-page SEO, internal
linking, images, performance, keyword opportunities — and turn findings
into prioritized, human-approved recommendations, using the *existing*
Copywriter to actually fix what it finds (rewrite a bad title, generate alt
text, etc.). Designed to eventually manage 13+ websites for one business
(an agency-style account), not just one tenant's own site.

**Non-negotiable, repeated because it's the whole point of this feature:**
every number the UI shows must come from a real deterministic check or a
real measurement. No fabricated Core Web Vitals, no invented keyword
volume/CPC, no placeholder findings. Where we have no real data source,
label the value `"Not measured"` / `"Not available"` — never estimate.

### What already exists that this reuses (found by inspection — don't rebuild)

- **A working, security-hardened website crawler already exists**, built
  for "import my website into the knowledge base"
  (`apps/api/app/services/document_service.py`):
  `_assert_public_url` (SSRF guard: resolves the hostname and rejects
  private/loopback/link-local/reserved/multicast IPs), a manual
  redirect-follow loop that re-validates every hop (so a public URL can't
  302 to an internal address), `_get_robot_parser`/`discover_website_pages`
  (sitemap-first, link-crawl fallback, `robots.txt`-filtered, capped at
  `MAX_CRAWL_PAGES`), `_fetch_sitemap_xml` (handles `<sitemapindex>`
  nesting, bounded), and `_fetch_url_text` (strips script/style/nav/
  footer/header, byte-size capped). This is Phase 24's security
  requirements already solved once — **extract the low-level fetch/SSRF/
  robots/sitemap pieces into a shared module both document ingestion and
  the SEO crawler call**, rather than writing a second crawler. The SEO
  crawler needs more per-page structured extraction (title, meta, headings,
  canonical, internal links, images) than document ingestion does, so it
  gets its own analyzer layer on top of the shared fetch layer — but the
  fetch/SSRF/robots/sitemap layer itself is not duplicated.
- **No job queue exists anywhere in this codebase** (root `CLAUDE.md`'s
  "shared job queue" is aspirational, not built). The existing pattern for
  "long-running background fetch triggered by a request" is
  `crawl_and_ingest_website` — a FastAPI `BackgroundTasks` call that opens
  its own DB session and updates row status as it goes, polled by the
  frontend. Audits follow the same pattern: `SeoAudit.status` moves
  `pending → running → completed | failed`, no new infra required for
  Stage 1-2.
- **`BusinessWebsite` (`apps/api/app/models/website.py`) is NOT the same
  concept and should NOT be reused for audit targets.** It's a thin record
  ("what domain do you run the chat widget on") that exists purely to count
  against `PlanLimits.max_websites` (the 1/1/3/10-website pricing tiers).
  Conflating it with "sites this business wants SEO-audited" would silently
  change what that plan limit means for every existing tenant. This upgrade
  needs its own model (`SeoWebsite`, see below) and, if/when it needs a
  count limit, its own limit field — not `max_websites`.
- **Provider-abstraction pattern to copy** for the Phase 9 performance
  integration: `apps/api/app/integrations/calendar_provider.py`'s
  `CalendarProvider` ABC + `get_calendar_provider()` factory. A
  `PerformanceProvider` ABC (`get_lab_metrics(url) -> PerformanceResult |
  None`) with a Google PageSpeed Insights implementation follows the same
  shape. If no API key is configured, the provider returns `None` and every
  caller renders "Not measured" — never a fabricated number.
- **Structured-LLM-output pattern to copy**: `seo_service.py`'s own
  `_generate_one` — `json_mode=True`, parse into a typed dataclass, catch
  and skip on bad JSON rather than trusting it. Every new LLM call
  (recommendation explanations, executive summary, keyword ideas) follows
  this, validated into a Pydantic model before it's stored.

### Data model (additive only — see root convention #6/7, no existing table loses columns)

```
SeoWebsite            business_id, url, name, target_country, target_language,
                      primary_category, target_keywords (json), crawl_tier
                      ("starter"|"standard"|"advanced" -> 25/100/500 page cap),
                      created_at

SeoAudit              website_id, business_id, status (pending|running|
                      completed|failed), started_at, completed_at,
                      pages_discovered, pages_crawled, pages_blocked,
                      health_technical, health_on_page, health_performance,
                      health_content, health_internal_linking (0-100 each,
                      explicitly labeled as an internal diagnostic score,
                      never presented as a Google ranking signal),
                      created_at

SeoCrawledPage        audit_id, url, http_status, title, meta_description,
                      h1_count, word_count, canonical_url, meta_robots,
                      x_robots_tag, is_indexable, redirect_chain (json),
                      internal_link_count, image_count, images_missing_alt

SeoFinding            audit_id, business_id, category (technical|on_page|
                      performance|content|internal_linking|images|
                      keywords), rule_code, severity (critical|high|medium|
                      low|informational), affected_url, issue, explanation,
                      recommended_fix, evidence (json), status (open|
                      in_progress|approved|completed|ignored), created_at

SeoKeywordOpportunity audit_id, keyword, intent, suggested_page,
                      current_page, content_gap, recommendation,
                      volume ("Not available" unless a real data source is
                      ever connected — see Phase 14 below)
```

`SeoDraft` gains one nullable `finding_id` FK (not a breaking change — see
Phase 12) so a draft generated from "Generate SEO Title" on a specific
finding is traceable back to what it fixes; drafts generated from the
existing product-picker flow leave it null exactly as today.

### Entitlement/plan decisions (resolved) and still-open ones

1. **Resolved.** Every Force agent (including this one) is sold standalone
   via `BusinessAgentAccess`/`agent_access_service.py`
   (`seo_audit_optimization` key) — never bundled into the chat-widget
   plan. See this section's earlier "Standalone agent billing" writeup.
2. **Resolved.** `SeoWebsite` has its own limit, independent of
   `PlanLimits.max_websites`: `DEFAULT_SEO_WEBSITE_LIMIT = 10`
   (`app/core/agent_catalog.py`), raised per-business via
   `Business.seo_website_limit_override` for the 13+-website agency case.
3. **Still open.** Phase 9 (Core Web Vitals) needs a real data source —
   Google PageSpeed Insights API is free (quota-limited) and the natural
   first choice; needs an API key in `.env`. Confirm before Stage 8.
4. **Still open.** Phase 14 (keyword opportunities) has **no real search-
   volume/CPC/competition data source connected anywhere in this repo.**
   Without budget for DataForSEO/Ahrefs/SEMrush/etc., that stage ships
   keyword *ideas* only, with volume/CPC/competition always literally
   labeled "Not available" — confirmed acceptable; revisit only if a
   client asks for real numbers.

### Deterministic vs. LLM — hard boundary (Phase 18)

```
Crawler (shared fetch/SSRF/robots/sitemap layer)
  -> Technical + On-Page + Image + Internal-Link analyzers (pure functions,
     no LLM, over SeoCrawledPage rows -- severity comes from fixed rules,
     never LLM opinion)
  -> Performance analyzer (PerformanceProvider or "Not measured")
  -> SeoFinding rows (deterministic facts + a fixed severity)
  -> LLM pass: turns findings into human-readable explanations/priority
     narrative, and (existing) SEO Copywriter turns a finding into an
     actual title/meta/alt-text/content draft
  -> Human approval (existing SeoDraft workflow, extended, never bypassed)
```

The LLM never decides *whether* something is broken — only explains *why it
matters* and *drafts the fix*, both always subject to approval.

### Staged implementation order (commit after each stage; regression-test the Copywriter every time)

1. **DONE — Architecture + DB.** `SeoWebsite`, `SeoAudit`, `SeoCrawledPage`,
   `SeoFinding`, `SeoKeywordOpportunity` models + migration
   (`a7d3f9c1e6b8`); CRUD API for websites
   (`app/api/agents_seo_audit.py`, `app/services/seo_website_service.py`).
   Also resolved the two entitlement/limit questions below: agent access
   goes through `agent_access_service` (`seo_audit_optimization` key,
   see the "Standalone agent billing" section above), and
   `Business.seo_website_limit_override` + `DEFAULT_SEO_WEBSITE_LIMIT`
   (10, in `app/core/agent_catalog.py`) resolve the website-count-limit
   question. 13 tests in `tests/test_seo_websites.py`.
2. **DONE — Crawler extraction.** `app/services/web_crawl.py` now holds
   the shared fetch/SSRF/robots/sitemap layer (`document_service.py`
   re-exports the old names, unaffected); `app/services/
   seo_page_analyzer.py` does per-page structured extraction (title/meta/
   canonical/meta-robots/headings/links/images/`content_hash`) on top of
   `web_crawl.fetch_with_redirects`. `app/services/seo_audit_service.py`
   orchestrates the crawl into `SeoCrawledPage` rows via `run_audit`
   (a `BackgroundTasks` worker, same shape as `crawl_and_ingest_website`).
   41 tests (`test_web_crawl.py`, `test_seo_page_analyzer.py`,
   `test_seo_audits.py`).
3. **DONE — Technical SEO analyzer.** `app/services/
   seo_technical_analyzer.py` — robots.txt (missing/blocks-entire-site/
   missing sitemap declaration), sitemap (missing/blocked-by-robots
   conflict), and per-page (broken page, long redirect chain, noindex,
   canonical) checks, all fixed-severity. Wired into `run_audit`, sets
   `SeoAudit.health_technical`. 22 unit + 9 integration tests.
4. **DONE — On-page analyzer.** `app/services/seo_onpage_analyzer.py` —
   title/meta-description length checks, missing H1 (high) vs. multiple H1
   (informational, per this file's own "don't assume it's wrong" rule),
   thin content, image alt-text counts, and cross-page duplicate title/
   meta/content checks (content duplication via a real SHA-256
   `content_hash` of each page's cleaned text, not guessed). Shared
   `FindingDraft`/`health_score` factored into `seo_finding_common.py`.
   Sets `SeoAudit.health_on_page`. 21 unit + 3 integration tests.
5. **DONE — Audit dashboard.** `seo_audit_service.overall_health` (average
   of whichever `health_*` categories have actually run — never treats an
   unrun category as 0) and `finding_severity_counts` (real counts, zero-
   filled) surfaced on every `SeoAuditOut` response. Dashboard's
   `SeoHealthPanel` shows the composite score (explicitly captioned "not a
   Google ranking signal"), a per-category tile row, and clickable
   severity counts that drill into `FindingsList` filtered by that
   severity. 8 tests (`test_seo_audit_summary.py`).
6. **DONE — Recommendation engine.** `app/services/
   seo_recommendation_service.py` — the FIRST LLM call in this pipeline.
   `build_action_plan()` is entirely deterministic: groups an audit's
   `SeoFinding` rows by `rule_code` into one item per issue type (all
   affected URLs listed together), maps severity → Priority 1/2/3 and two
   fixed lookup tables → `expected_benefit`/`implementation_difficulty` —
   no LLM guessing on those fields. `generate_executive_summary()` is the
   one LLM call: a 3-5 sentence narrative fed ONLY the audit's own real
   counts/issue labels (`json_mode`, validated, returns `None` — never a
   fabricated placeholder — on any parse/call failure). Stored on
   `SeoAudit.executive_summary` (migration `c4f8a2b6e1d3`). New endpoint
   `GET .../audits/{id}/action-plan`. Dashboard shows the summary inline
   on `SeoHealthPanel` and a new "Action Plan" tab grouped by priority.
   23 tests (`test_seo_recommendation_service.py`,
   `test_seo_recommendation_integration.py`).
7. **DONE (partial, by design) — Integrate existing Copywriter.**
   `SeoDraft` extended: `product_id` now nullable, added `url` and
   `draft_type` (`full_copy` | `title` | `meta_description` | `content`),
   the three `draft_*` fields now nullable (migration `d5a8c2f4b7e9`) --
   exactly one is populated per finding-driven draft, all three for the
   original product-picker flow. `seo_service.generate_draft_for_finding()`
   dispatches by `rule_code`: title findings → `draft_seo_title`, meta
   findings → `draft_meta_description`, `thin_content` → a content-
   expansion suggestion in `draft_description`. New endpoints
   `POST/GET .../findings/{id}/generate-draft|drafts`; reuses the
   existing `/drafts/{id}/approve|reject` endpoints unchanged (approve
   already only writes to a Product when one is actually linked -- a
   finding-driven draft never is, so approving just marks it ready to use,
   see that function's own docstring).
   **Deliberately NOT implemented** (`UnsupportedFindingError`, by design,
   not an oversight): **Generate Alt Text** -- Stage 4's on-page analyzer
   only stores a per-page COUNT of images missing alt text, never each
   image's own src/context, so there is no real image to generate alt
   text FROM without fabricating what it shows. **Internal Linking
   Suggestions** -- Stage 4 only counts internal links per page; making a
   real suggestion needs an actual link graph (which page links to which,
   with what anchor text), a data model and analyzer that don't exist.
   **Duplicate title/duplicate content findings** -- fixing these means a
   human choosing which of several pages keeps which copy, not a single
   generated answer for one page in isolation. All three would need
   guessing past what the audit actually knows -- exactly what this
   agent's "no fabricated findings" rule forbids. Dashboard: a "Generate
   fix" button appears on every supported finding, showing the result
   inline with Approve/Reject, reusing the same review pattern as the
   Content tab. 17 tests (`test_seo_copywriter_finding_integration.py`).
8. **DONE — Performance/Core Web Vitals.** `app/integrations/
   performance_provider.py` -- `PerformanceProvider` ABC +
   `GooglePageSpeedProvider` (Google PageSpeed Insights v5, free, no
   OAuth) + `get_performance_provider()` factory, same shape as
   `calendar_provider.py`. Needs `GOOGLE_PAGESPEED_API_KEY` (`.env.example`,
   `core/config.py`) -- **no key is configured in this repo/environment**,
   so every measurement returns `None` immediately (no network call at
   all) and `health_performance` stays null, rendered as "Not measured" --
   exactly the intended honest fallback, not a gap to "fix" without a real
   key. New `SeoPerformanceMeasurement` model (migration `e6b9d3f8a1c7`):
   one row per strategy (mobile/desktop) that actually succeeded, storing
   `performance_score`, `lcp_ms`, `cls`, `tbt_ms` (lab-measured, always
   present when the call succeeds) and `inp_ms` (real-user CrUX field
   data ONLY -- often null even on a successful measurement, deliberately
   never backfilled from `tbt_ms` since they're different metrics).
   `run_audit` measures the website's root URL ONLY (never every crawled
   page -- each Lighthouse run is slow), on both strategies; a strategy
   that fails or has no data simply gets no row, not a placeholder.
   `health_performance` = average of whichever strategies' scores
   succeeded. New endpoint `GET .../audits/{id}/performance`. 24 tests
   (`test_performance_provider.py`, `test_seo_performance_integration.py`).
9. **DONE — Keyword opportunities.** `app/services/seo_keyword_service.py` —
   the second (and last, so far) LLM call in this pipeline, per the Phase 14
   decision above: LLM-generated keyword *ideas* only, grounded in the
   audit's own crawled pages (title + URL of up to `MAX_PAGES_IN_PROMPT`
   = 30 pages, plus the website's `primary_category`/`target_country`/
   `target_language`/`target_keywords`), never a real search-volume/CPC/
   competition source. The JSON response schema the LLM fills in has no
   volume/cpc/competition field at all — nothing to hallucinate a number
   into — and `persist_keyword_opportunities()` always writes the literal
   string `"Not available"` into `SeoKeywordOpportunity.volume`,
   independent of anything the LLM returns. Capped at `MAX_KEYWORD_IDEAS`
   = 15 ideas per audit; a malformed individual entry is skipped, not
   fatal; total call failure or unparseable JSON raises
   `KeywordGenerationError`, which `run_audit`'s keyword pass catches so a
   down LLM/bad response degrades to "no keyword ideas this run" rather
   than failing the whole audit. `content_gap` is a free-text description
   (e.g. "No existing page discusses roasting"), not a boolean flag — it
   was modeled as one initially and corrected against the actual DB column.
   New endpoint `GET .../audits/{id}/keyword-opportunities`. Dashboard: a
   third "Keyword Ideas" tab on `WebsiteCard` (next to Action Plan/All
   Findings) via `KeywordOpportunitiesList`, which surfaces the "Not
   available" volume caveat explicitly rather than hiding the column.
   15 tests (`test_seo_keyword_service.py`, `test_seo_keyword_integration.py`).
10. **DONE — Audit history/comparison.** `app/services/
    seo_audit_comparison_service.py` — entirely deterministic, no LLM.
    `compare_audits()` takes any two audit IDs (business_id-scoped),
    orders them chronologically by `created_at` internally (so it doesn't
    matter which one the caller passes first), and requires both belong
    to the same website (`AuditComparisonError`, 400) and be different
    audits. `SeoFinding` rows have no stable identity across separate audit
    runs — every run persists brand-new rows — so findings are matched
    between the two audits by `(rule_code, affected_url)`: same issue type
    on the same URL (or the same site-wide check with no URL, e.g. a
    missing sitemap). A match present only in the earlier audit is
    `resolved_findings`; only in the later one, `new_findings`; in both,
    `persisting_findings`. Also returns each audit's `overall_health` and
    the delta (`None` if either audit hadn't computed any health category
    yet — never a fabricated 0). New endpoint
    `GET .../audits/{id}/compare?against=<other_audit_id>` (`ValueError` →
    404 "not found"/cross-tenant, `AuditComparisonError` → 400 "can't be
    compared"). Dashboard: a fourth "History" tab on `WebsiteCard` listing
    completed audits with a "Compare to previous" toggle per row, showing
    resolved/new/persisting counts and the health delta inline
    (`AuditHistoryList`/`AuditComparisonPanel`). 17 tests
    (`test_seo_audit_comparison_service.py`,
    `test_seo_audit_comparison_integration.py`).
11. **DONE (data + UI; PDF explicitly deferred) — Client-ready report.**
    `app/services/seo_report_service.py` — does no new analysis or LLM call
    of its own; `build_report()` just assembles data already computed by
    earlier stages (website identity, `overall_health`, the Stage 6
    `executive_summary`, the top `top_n` (default 5) priority-sorted
    action-plan items, real `finding_severity_counts`, and the Stage 9
    keyword-opportunity count) into one structure meant to be shown to (or
    shared with) the tenant's own client. Raises `ReportNotReadyError`
    (→ 400) for a pending/running/failed audit — a client report over an
    incomplete run would show misleading data — and a plain `ValueError`
    (→ 404) for an unknown/cross-tenant audit ID, same pattern as Stage 10.
    New endpoint `GET .../audits/{id}/report`. Dashboard: a fifth "Report"
    tab (`ReportView`) rendering a clean, presentational summary with a
    "Print / Save as PDF" button — this is the browser's own native
    `window.print()` dialog, NOT a generated PDF, so it doesn't cross the
    "PDF export deferred" line while still giving a genuinely useful
    client-facing output today; a real PDF renderer can consume this exact
    same `SeoAuditReportOut` structure later with no service-layer change.
    10 tests (`test_seo_report_service.py`, `test_seo_report_integration.py`).
12. **DONE (backend; no dashboard "Connect Google" UI yet) — Google
    Analytics + Search Console integration.** First stage of the
    Professional tier roadmap above (business-data integrations, not
    crawler feature-parity). `app/models/seo_google_connection.py`
    (`SeoGoogleConnection`, migration `d3f6b8a1c5e7`) — one row per
    business, one Google OAuth client covering BOTH APIs' read-only scopes
    in a single consent screen (unlike Calendar's per-agent client, since
    these two reporting APIs always travel together for this feature).
    `app/api/google_oauth.py` (`/api/businesses/me/google/...`) —
    structurally identical Authorization Code flow to
    `calendar_oauth.py`'s (signed state, `/authorize` → Google consent →
    `/callback` → encrypted refresh token stored), plus `PATCH .../config`
    to set `analytics_property_id`/`search_console_site_url` (can't be
    inferred automatically — a Google account can own many GA4 properties
    and verified Search Console sites; see `SeoGoogleConnection`'s own
    docstring). Two provider integrations, same ABC-+-factory shape as
    `calendar_provider.py`/`performance_provider.py`:
    `app/integrations/analytics_provider.py` (`AnalyticsProvider`/
    `GoogleAnalyticsProvider`, GA4 Data API, matches by URL path) and
    `app/integrations/search_console_provider.py` (`SearchConsoleProvider`/
    `GoogleSearchConsoleProvider`, Search Console API v3, matches by full
    URL) — both share `app/integrations/google_oauth_client.py`'s token-
    refresh helper, both follow the existing "no key/no auth → return
    empty, caller renders 'Not measured'" pattern (Stage 8) — never a
    fabricated number. New `SeoCrawledPage` columns (migration
    `e2b5c9f3a7d1`): `ga_sessions_28d`, `gsc_impressions_28d`,
    `gsc_clicks_28d`, `gsc_avg_position_28d`, all null until both connected
    AND configured. `run_audit` fetches both once per audit (batched
    across every crawled URL, not per-page) right after the crawl; either
    provider raising or returning nothing just leaves those fields null,
    never fails the audit. The actual payoff:
    `seo_recommendation_service.build_action_plan()` now takes an optional
    `crawled_pages` argument and computes each item's `traffic_weight`
    (real sessions + clicks summed across its own affected URLs, `None` if
    none have data) — used ONLY to break ties within the same priority
    tier (a real critical issue still always outranks a highly-trafficked
    low-severity one; see that function's own docstring), so a business
    with nothing connected sees byte-identical ordering to before this
    stage. 58 tests (`test_google_oauth.py`, `test_analytics_provider.py`,
    `test_search_console_provider.py`, `test_seo_google_integration.py`,
    plus the `build_action_plan` traffic-weight cases added to
    `test_seo_recommendation_service.py`).
    **Not built**: a dashboard "Connect Google" button/Settings UI (the
    calendar equivalent lives in Settings — this needs the same, plus a
    small form for `analytics_property_id`/`search_console_site_url` since
    there's no property/site picker either). Until that UI exists, this
    stage is only reachable by calling the API directly. Needs
    `GOOGLE_ANALYTICS_OAUTH_CLIENT_ID`/`_SECRET` in `.env` (see
    `.env.example`'s own setup comment) before it does anything at all.
13. **DONE — Structured data analyzer.** `app/services/
    seo_structured_data_analyzer.py` — deterministic, category="technical"
    (folded into `health_technical`, no new health_* column — see that
    module's own docstring for why). Extraction happens at crawl time in
    `seo_page_analyzer.py` (new `SeoCrawledPage` columns
    `structured_data_types`/`structured_data_invalid_count`, migration
    `f7c2a9d4e8b1`) since raw HTML is only ever available then. Two rules:
    a JSON-LD block that's present but fails to parse (medium, per page —
    a real, fixable problem) and the sitewide absence of ANY structured
    data across the whole audit (low, ONE finding, not per-page — simply
    having none isn't flagged per page, since most pages legitimately have
    none and that would be noise). Wired into `run_audit` right alongside
    the Stage 3 technical pass. 26 tests (`test_seo_page_analyzer.py`'s
    structured-data cases, `test_seo_structured_data_analyzer.py`,
    `test_seo_structured_data_integration.py`).
14. **DONE — Accessibility analyzer.** `app/services/
    seo_accessibility_analyzer.py` — deterministic, category="on_page"
    (folded into `health_on_page`, extending this agent's existing
    accessibility-adjacent on-page check, `images_missing_alt`). Static-
    HTML analysis only — no headless-browser rendering (matching this
    agent's existing crawl-time limitation), which honestly rules out
    color-contrast checks entirely rather than faking one. New
    `SeoCrawledPage` columns (`html_lang_present`, `heading_outline`,
    `form_inputs_missing_label`, `links_missing_accessible_name`, same
    migration `f7c2a9d4e8b1`), extracted in `seo_page_analyzer.py`
    alongside Stage 13's fields. Four rules: missing `<html lang>` (low),
    a heading-level skip e.g. h2→h4 (informational — going back UP a level
    is normal document structure, not flagged), form fields with no
    associated label (medium), and links with no accessible name — e.g. an
    icon-only button with no alt/aria-label (medium). 27 tests
    (`test_seo_page_analyzer.py`'s accessibility cases,
    `test_seo_accessibility_analyzer.py`,
    `test_seo_accessibility_integration.py`).
15. **DONE — Recurring audit scheduling.** `app/services/
    seo_schedule_service.py` — the first scheduled/recurring job in this
    codebase (see that module's own docstring: a narrow, single-purpose
    in-process tick, explicitly NOT the general "shared job queue" the
    root CLAUDE.md still calls aspirational). New `SeoWebsite` columns
    `audit_schedule` (`null`|`"weekly"`|`"monthly"`) and
    `next_scheduled_audit_at` (migration `c8e1f4a7b3d9`). `AsyncIOScheduler`
    (new dependency, `apscheduler`) wired into `app/main.py`'s `lifespan`,
    ticking every `CHECK_INTERVAL_MINUTES` (15) to run
    `run_due_audits()`, which starts a fresh audit for every past-due
    website and reschedules it forward by its own interval regardless of
    whether that audit succeeded (so a website stuck failing doesn't spam
    retries faster than its configured cadence). New endpoint `PATCH
    .../websites/{id}/schedule` (`SeoWebsiteScheduleUpdate`). Not gated to
    a pricing tier in code (same as everything else — tiers are catalog
    copy only, see this file's own "Pricing" section). 21 tests
    (`test_seo_schedule_service.py`, schedule cases in
    `test_seo_websites.py`). **Not built**: any dashboard UI to turn
    scheduling on/off (same gap as Stage 12 — API-only for now).

### UI (Phase 1/20)

**Done through Stage 11 (the whole staged upgrade).** Sidebar nav item is a
single entry (`/dashboard/seo`, relabeled "SEO" in `Sidebar.tsx`), with
in-page tabs: **Websites** (register/list/delete + per-website "Run audit"
+ `SeoHealthPanel`: overall score, per-category tiles, severity-count
drill-down, Core Web Vitals) and **Content** (the original product-picker/
draft-review flow, plus Stage 7's inline "Generate fix" action on
supported findings). Each `WebsiteCard`'s "View SEO Health" panel has five
detail tabs — **Action Plan** (Stage 6, grouped by priority),
**All Findings** (severity-filterable), **Keyword Ideas** (Stage 9,
`KeywordOpportunitiesList`), **History** (Stage 10, `AuditHistoryList` +
`AuditComparisonPanel` — past completed audits with an on-demand
resolved/new/persisting-findings + health-delta comparison against the
previous run), **Report** (Stage 11, `ReportView` — a clean client-facing
summary with a browser-native "Print / Save as PDF" button) — all rendered
inline, no separate route yet. No new sidebar nav item. A deep-linkable
`/dashboard/seo/audits/:id` route is still open, not yet needed since
everything so far lives inline on the Websites tab.

### Testing (Phase 23)

Every new deterministic analyzer (crawler, robots parser, sitemap parser,
metadata/heading/link/image checks) gets unit tests against fixed HTML/
robots/sitemap fixtures — this is currently a gap even for the *existing*
crawler in `document_service.py` (only `test_document_limits.py` exists
today, no crawler-behavior tests), so extracting the shared crawler is also
the point to finally add that coverage. All existing
`test_agents_seo.py` tests must keep passing unmodified throughout.

## Definition of done for this upgrade

Tracked per-stage in the implementation order above, not as one checklist —
see each stage's own PR/commit for its specific done-criteria. The overall
upgrade is done when Phase 22's dogfood test (auditing `mielikkix.ai`
itself and getting real, non-mocked findings) passes end to end.
