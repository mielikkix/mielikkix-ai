# SEO Audit & Optimize — Architecture Notes (Phase 0)

Written as Phase 0 of the "make it accurate and trustworthy, then valuable
enough to sell" plan. Read-only pass — nothing in this document changes
behavior. Verified against the actual code as of 2026-09-21, not from
memory or prior docs (which do exist and are more detailed per-stage: see
"Where the deeper docs live" at the bottom).

## Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, Postgres.
  Lives in `apps/api/`.
- **Frontend**: React + TypeScript (Vite), TanStack Query, axios. Lives in
  `apps/dashboard/`. The SEO tool is one page: `src/dashboard/pages/SeoPage.tsx`
  (~1,400 lines — everything for this feature is in this one file today).
- **Marketing site**: Astro, `website/`. Has its own pricing page for this
  agent (`website/src/pages/agent-pricing.astro` + i18n JSON files) —
  separate content from the in-app dashboard, kept manually in sync.
- **LLM**: `packages/agent-core`'s `LLMClient`, OpenAI's cheap/fast tier
  (`gpt-4o-mini` by default). Used in exactly three places (see "LLM calls"
  below) — everything else is deterministic Python.
- No job queue exists generally in this codebase. One narrow exception:
  `app/services/seo_schedule_service.py` runs an in-process APScheduler
  tick for recurring audits (see "Scheduling" below) — not a general queue.

## Request flow, end to end

1. `POST /api/agents/seo/websites` registers a `SeoWebsite` row (a URL +
   crawl depth tier, NOT the same thing as `BusinessWebsite`, which is
   unrelated chat-widget config).
2. `POST /api/agents/seo/websites/{id}/audits` creates a `SeoAudit` row
   (`status=pending`) and schedules `seo_audit_service.run_audit(audit_id)`
   as a FastAPI `BackgroundTasks` call (no queue — same pattern
   `document_service.py`'s `crawl_and_ingest_website` already used).
3. `run_audit` (in `app/services/seo_audit_service.py`, ~410 lines) is the
   orchestrator. It runs every stage below in sequence, in ONE background
   task, committing to the DB as it goes so the frontend's polling
   `GET .../audits` calls see live progress.

## The crawler (`app/services/web_crawl.py`)

Shared with document ingestion (`document_service.py` re-exports these
names) — one hardened fetch path, not two crawlers.

- `assert_public_url` — SSRF guard (resolves the hostname, rejects
  private/loopback/link-local/reserved/multicast IPs).
- `discover_website_pages(url, max_pages)` — sitemap-first
  (`discover_sitemap_urls`, follows one level of `<sitemapindex>` nesting),
  falls back to `discover_by_crawling` (breadth-first link crawl, depth 2,
  same-host only) if there's no sitemap. Both paths are filtered by
  `robots.txt` and capped at `max_pages`.
- `fetch_with_redirects` — manually follows redirects (never httpx's
  built-in follower), re-validating `assert_public_url` on every hop so a
  public URL can't 302 to an internal address.
- **`app/services/url_normalizer.py`** (new, Phase 1) — `normalize_url()`
  defines equivalence for dedup purposes: scheme (http/https treated as
  one), host (lowercased, `www.` stripped), default port stripped,
  trailing slash / `index.html` stripped, tracking query params removed,
  fragment dropped. Used as a **dedup key only** — the actual URLs
  fetched/stored/returned are never rewritten to a forced scheme, to avoid
  breaking a genuinely HTTP-only site. See that module's own docstring and
  the Phase 1 summary below for why this exists.

## Per-page extraction (`app/services/seo_page_analyzer.py`)

`analyze_page(url)` fetches one page and extracts structured facts via
BeautifulSoup: title, meta description, canonical URL, meta robots/
x-robots-tag, heading outline, internal link count, image/alt-text counts,
a SHA-256 `content_hash` of the boilerplate-stripped visible text,
structured-data (JSON-LD) types + invalid-block count, `<html lang>`
presence, form-inputs-missing-label count, links-missing-accessible-name
count. All deterministic, no LLM. Results are stored one row per page in
`seo_crawled_pages`.

## The findings/rules engine (deterministic, no LLM)

Five analyzer modules, each `analyze(pages) -> List[FindingDraft]`, sharing
one `FindingDraft` dataclass and one `health_score()` function
(`app/services/seo_finding_common.py`, severity → point deduction:
critical -20, high -10, medium -5, low -2, informational 0):

| Module | Feeds into | Rules |
|---|---|---|
| `seo_technical_analyzer.py` | `health_technical` | robots.txt missing/blocks-site/no-sitemap-declared, sitemap missing/conflicts with robots, broken pages (4xx/5xx), long redirect chains, noindex, missing/foreign canonical |
| `seo_onpage_analyzer.py` | `health_on_page` | title/meta length, missing H1, thin content (<300 words), image alt-text count, **cross-page duplicate title/meta/content-hash** |
| `seo_structured_data_analyzer.py` | `health_technical` | invalid JSON-LD (per page), sitewide absence of any structured data (one finding, not per-page) |
| `seo_accessibility_analyzer.py` | `health_on_page` | missing `<html lang>`, heading-level skips, unlabeled form fields, links with no accessible name |

`run_audit` concatenates technical+structured-data findings into one list
before scoring `health_technical`, and on-page+accessibility findings
before scoring `health_on_page` — so those two "newer" analyzers don't
have their own health columns; they extend the existing two categories.

**Known gap, confirmed by inspection**: `health_performance` is populated
only if `GOOGLE_PAGESPEED_API_KEY` is configured (Stage 8,
`app/integrations/performance_provider.py` — currently NOT configured in
this environment, so it's always null/"Not measured"). `health_content`
and `health_internal_linking` have model columns
(`app/models/seo_audit.py`) but **no analyzer ever sets them** — they are
always null. `overall_health()` averages only the categories that
actually ran, so a null category doesn't drag the score down, but a
report showing 3 of 5 categories as "—" is a real, visible gap (flagged in
this plan's Phase 2).

## Scoring / severity (single source of truth — verified, not assumed)

- Each `SeoFinding` row has one fixed `severity` (never LLM-assigned) and
  a `category`.
- `finding_severity_counts()` (`seo_audit_service.py`) counts real
  `SeoFinding` rows by severity, straight from the DB.
- `seo_recommendation_service.SEVERITY_TO_PRIORITY` maps
  severity→{1,2,3} for the Action Plan's "Priority 1/2/3" grouping.
- **These two ARE consistent with each other** (both derive from the same
  `SeoFinding.severity` column) — I did not find a code path where they
  could disagree. If the UI ever shows "Priority 1 — Critical" next to a
  summary saying "Critical: 0", the most likely explanation given the
  code is that Priority 1 also includes `high`-severity findings (by
  design — see the mapping above), not that severity/priority genuinely
  disagree. Worth confirming against a live example in Phase 2 rather
  than assuming which explanation it is.

## LLM calls — exactly three, all in `seo_recommendation_service.py`,
## `seo_keyword_service.py`, and `seo_service.py`

1. **Executive summary** (`seo_recommendation_service.generate_executive_summary`)
   — fed ONLY already-computed counts/issue labels (`json_mode=True`,
   parsed into a typed shape, `None` on any failure — never a fabricated
   placeholder). Built from `build_action_plan()`'s own output, so **it
   already only sees deduplicated findings** — Phase 2's "summary must not
   mention issues not in the findings list" requirement should already
   hold structurally; worth a direct test to confirm rather than assume.
2. **Keyword ideas** (`seo_keyword_service.generate_keyword_ideas`) — LLM
   brainstorms keyword ideas grounded in the audit's own crawled page
   titles/URLs + the website's `primary_category`/`target_country`/
   `target_language`/`target_keywords`. `volume` is hardcoded to the
   literal string `"Not available"` regardless of what the LLM returns —
   there is no real search-volume/CPC data source connected anywhere.
3. **Generate fix** (`seo_service.generate_draft_for_finding`) — the
   Copywriter, dispatched by `rule_code`. Currently supports exactly 3
   finding types: `missing_title`/`title_too_long`/`title_too_short` →
   title draft, `missing_meta_description`/`*_too_long`/`*_too_short` →
   meta draft, `thin_content` → content-expansion draft. Explicitly does
   NOT support alt-text generation (no per-image data), internal-linking
   suggestions (no link graph), or duplicate-title/content fixes (needs a
   human to pick which page wins) — raises `UnsupportedFindingError` by
   design for those, not a bug.

## PDF / report generation

There is **no server-side PDF renderer**. "PDF" today means the browser's
native `window.print()` dialog (`SeoPage.tsx`'s `PrintableAuditReport`
component mounts all five detail tabs — Report, Action Plan, All Findings,
Keyword Ideas, History — invisibly, shown only in print media via Tailwind
`print:` classes, so printing captures the full report regardless of which
tab is on screen). `app/services/seo_report_service.py` builds the
underlying `SeoAuditReportOut` data structure (website identity, overall
health, executive summary, top N action-plan items, finding counts,
keyword-opportunity count) that the Report tab renders — a real PDF
renderer could consume this same structure later with no service-layer
change (already noted in that file's own docstring).

## Database (SEO-specific tables, all under `apps/api/alembic/versions/`)

`seo_websites`, `seo_audits`, `seo_crawled_pages`, `seo_findings`,
`seo_keyword_opportunities`, `seo_performance_measurements`,
`seo_google_connections`. Full column list is in
`app/models/seo_audit.py`, `seo_website.py`, `seo_google_connection.py` —
not duplicated here since those files are the actual source of truth and
this document would drift from them.

## Plan/limit/entitlement logic (verified — this is what Phase 5 will sit on top of)

- **Agent access is one on/off gate**, `agent_access_service.py`, backed
  by `BusinessAgentAccess` rows (`agent_key="seo_audit_optimization"`,
  `status="active"`). No per-feature flags today, no payment processor
  wired up anywhere — a business either has the agent or doesn't; access
  is granted manually by a platform admin.
- **`app/core/agent_catalog.py`** holds marketing/pricing COPY only (two
  `AgentTier` entries — free "SEO Audit & Optimize", paid "Professional
  SEO Audit & Optimization") — this is NOT an entitlement layer. Nothing
  in the actual audit/crawl/analyzer code checks which tier a business is
  nominally on; every business with the one on/off gate gets every stage
  described above, always. This is the thing Phase 5 needs to actually
  build (real per-feature limits, checked server-side).
- **`app/models/seo_website.py`**: `crawl_tier` (`starter`/`standard`/
  `advanced` → 25/100/500 pages, `CRAWL_TIER_PAGE_LIMITS`) is a
  **per-audit** page cap, freely selectable by any business today — not
  gated by plan/tier in code. `audit_schedule` (`weekly`/`monthly`/null) +
  `next_scheduled_audit_at` back the recurring-audit feature — also not
  gated by tier in code, and has no dashboard UI to turn on/off yet
  (API-only: `PATCH .../websites/{id}/schedule`).
- No concept of "3 Generate-fix uses per audit" or "1 re-audit per month"
  exists anywhere in the code today — these are pure Phase 5 net-new work,
  not something to adjust from an existing limit.

## Scheduling (Stage 15, already built)

`app/services/seo_schedule_service.py` — `AsyncIOScheduler` (apscheduler)
wired into `app/main.py`'s `lifespan`, ticking every 15 minutes,
re-running any website whose `next_scheduled_audit_at` has passed and
rescheduling it forward by its own interval (even if that run failed, so a
broken site doesn't retry faster than its configured cadence). This is
real, tested infrastructure Phase 5's "weekly re-audits with before/after
comparison" can build directly on top of — the before/after comparison
piece (`seo_audit_comparison_service.py`) already exists too (Stage 10).

## Google Analytics / Search Console (Stage 12, already built, backend-only)

`app/api/google_oauth.py` (per-business OAuth, one shared Google client
covering both APIs), `app/integrations/analytics_provider.py` +
`search_console_provider.py` (both return empty/None when not connected —
never a fabricated number). Feeds a `traffic_weight` into each Action Plan
item (real sessions+clicks summed across that item's affected URLs, used
only to break sort-order ties within the same priority tier — never
promotes a lower-priority item above a higher one). **No dashboard UI to
connect Google existed until very recently** — a "Connect Google" card +
property/site config form now exists on the SEO page's Websites tab.

## Existing tests and how to run them

```
cd apps/api
./.venv/Scripts/python.exe -m pytest tests/ -k "seo or crawl" -q
```

All SEO-related test files (as of this writing, non-exhaustive — run the
above to get the live list): `test_url_normalizer.py`,
`test_web_crawl.py`, `test_seo_page_analyzer.py`,
`test_seo_technical_analyzer.py`, `test_seo_onpage_analyzer.py`,
`test_seo_structured_data_analyzer.py`, `test_seo_accessibility_analyzer.py`,
`test_seo_findings.py`, `test_seo_onpage_integration.py`,
`test_seo_structured_data_integration.py`,
`test_seo_accessibility_integration.py`, `test_seo_audits.py`,
`test_seo_audit_summary.py`, `test_seo_recommendation_service.py`,
`test_seo_recommendation_integration.py`, `test_seo_performance_integration.py`,
`test_seo_keyword_service.py`, `test_seo_keyword_integration.py`,
`test_seo_audit_comparison_service.py`, `test_seo_audit_comparison_integration.py`,
`test_seo_report_service.py`, `test_seo_report_integration.py`,
`test_seo_websites.py`, `test_seo_schedule_service.py`,
`test_seo_google_integration.py`, `test_analytics_provider.py`,
`test_search_console_provider.py`, `test_google_oauth.py`,
`test_agents_seo.py` (the original Copywriter), `test_agent_access.py`.

Tests run against a real local Postgres (`mielikkix_test`), not SQLite or
mocks-all-the-way-down — `tests/conftest.py`'s `db_session` fixture does a
real `create_all()`/`drop_all()` per test function. Frontend has no test
suite for this page today (`apps/dashboard` — verified via `package.json`,
no test script beyond `tsc --noEmit` type-checking).

## Where the deeper docs live

- `apps/agents/seo-audit/CLAUDE.md` — the full staged build history
  (Stages 1-15), each with its own "definition of done" and test count.
  More detailed than this document; read it before touching any specific
  stage's code.
- `apps/api/app/core/agent_catalog.py` — the pricing/feature-copy source
  of truth (docstrings explain the "coming soon" convention this file's
  own Phase 5 rules echo).

## What this document deliberately does NOT cover

Per this phase's own scope: no behavior was changed to produce this
document, and it doesn't speculate about Phase 1+ fixes beyond noting
where I found a real, verified gap (health categories, canonical
grouping, URL dedup). Those are addressed in Phase 1 itself, summarized
separately.
