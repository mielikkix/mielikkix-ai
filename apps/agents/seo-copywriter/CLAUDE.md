# CLAUDE.md — apps/agents/seo-copywriter (upgrading to SEO Audit & Optimization Agent)

Read the root `CLAUDE.md` and `apps/agents/CLAUDE.md` first. This file is
this agent's own spec — it now covers two things: the SEO Copywriter that's
already live, and the in-progress upgrade that wraps it in a full SEO Audit
& Optimization Agent. **The copywriter keeps working unchanged throughout
this upgrade** — nothing below replaces it.

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
7. **Integrate existing Copywriter** — "Generate SEO Title/Meta/Alt Text/
   Content Improvement/Internal Linking Suggestion" actions on a finding,
   writing into (extended) `SeoDraft`; SEO Draft Workspace UI (Phase 13).
8. **Performance/Core Web Vitals** — `PerformanceProvider` + PageSpeed
   Insights implementation, "Not measured" fallback.
9. **Keyword opportunities** — LLM-generated ideas only, per the Phase 14
   decision above.
10. **Audit history/comparison** — re-run audits, diff findings/counts
    between runs.
11. **Client-ready report** — report data structure + UI first; PDF export
    only after that's solid.

### UI (Phase 1/20)

**Done through Stage 5.** Sidebar nav item is a single entry
(`/dashboard/seo`, relabeled "SEO" in `Sidebar.tsx`), with in-page tabs:
**Websites** (register/list/delete + per-website "Run audit" +
`SeoHealthPanel`: overall score, per-category tiles, severity-count
drill-down, findings list with an "Ignore" action) and **Content** (the
original product-picker/draft-review flow, unchanged). No new nav item.
A **Recommendations** tab (Stage 6) and deep-linkable
`/dashboard/seo/audits/:id` route are still open, not yet needed since
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
