# Mielikkix Marketing Site — Architecture

Promotion/marketing site for Mielikkix: home page, features, pricing, the AI agents and their live demos, blog, legal pages, and free-demo booking — in English and Norwegian.
Separate from `apps/dashboard/` (the admin/analytics dashboard, a React SPA) — this is a
purely static, SEO-first site with a different tech stack for a different job.

## Why a separate stack from `apps/dashboard/`

`apps/dashboard/` is a logged-in, data-heavy React SPA — SEO doesn't matter there, it's behind auth.
This site is the opposite: it's the thing small-business owners find via Google before they've
ever heard of Mielikkix, so page-load speed and crawlability are the whole game. A client-rendered
SPA is the wrong tool for that job — hence a separate static-generation project instead of adding
public routes to the dashboard app.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Framework | [Astro](https://astro.build) 7 (static output) | Ships zero JS by default — pages are static HTML/CSS; small vanilla-JS files handle i18n, currency, consent and the demo widgets. Best-in-class Lighthouse/Core Web Vitals scores, which directly affects Google ranking for local/small-business search. |
| Styling | Tailwind CSS v4 (via `@tailwindcss/vite`) | Same utility approach as `apps/dashboard/`, so styling knowledge transfers. Tailwind v4 needs no `tailwind.config.js` — theme tokens (colors, etc.) come from Tailwind's default palette plus a couple of custom CSS variables in `src/styles/global.css`. |
| Fonts | Open Sans, self-hosted via `@fontsource-variable/open-sans` (`@import` in `global.css`), used for both headings and body | Served from our own origin: loading from fonts.googleapis.com sent every visitor's IP to Google before consent (GDPR). |
| SEO | `@astrojs/sitemap` + per-page meta/OG/Twitter tags in `Layout.astro` + `public/robots.txt` | Sitemap and robots.txt are the baseline for organic discovery; per-page `<title>`/`<meta description>` drive click-through from search results. |
| Hosting (actual) | Hostinger shared hosting | The domain `mielikkix.ai` is registered and hosted on Hostinger; since this site builds to plain static files with no server process, the shared hosting plan already in place for the domain is sufficient — deploy by uploading `dist/` to `public_html` (no VPS needed for this piece). Vercel/Netlify/Cloudflare Pages would also work (see note below) but aren't the current plan. |

### Note on Vercel/Netlify vs. the backend

Earlier we ruled out Vercel for the FastAPI backend (heavy ML deps, stateful startup, no
persistent filesystem — see project discussion). None of that applies here: this site builds to
static files with no server process, so Vercel/Netlify/Cloudflare Pages would all work with no
changes if hosting ever moves off Hostinger. The dashboard (`apps/dashboard/` + `apps/api/`) is the piece
that needs a real VPS — see `files/ARCHITECTURE.md` §5 for that split (`app.mielikkix.ai` +
`api.mielikkix.ai` on a Hostinger VPS via `docker-compose.yml`, this site on shared hosting at the root domain).

## Folder structure

(Checked against the code 2026-10-07.)

```
website/
├── astro.config.mjs           # site URL, Tailwind, sitemap, norwegianPages(); assetsInlineLimit 0 (CSP)
├── integrations/
│   └── norwegian-pages.mjs    # After the build, writes a real Norwegian copy of every translatable
│                               # page to dist/no/<path>/ (crawlable /no/ URLs) and adds them to the sitemap
├── src/
│   ├── layouts/
│   │   └── Layout.astro       # <html> shell: meta/OG/Twitter, hreflang, JSON-LD @graph, Header, Footer,
│   │                           # ConsentBanner, i18n/currency bootstrap, and the sitewide chat bubble —
│   │                           # Mielikkix's OWN product Chat Widget (app.mielikkix.ai/widget.js, dogfooding)
│   ├── components/
│   │   ├── Header.astro / Footer.astro / PageHero.astro / CTASection.astro
│   │   ├── BentoCard.astro / FeatureBentoCard.astro / BlogPostCard.astro
│   │   ├── Price.astro        # Renders a [data-price-nok] amount; currencyStore converts to EUR/USD
│   │   ├── pricing/           # ProductPricing, PricingChart, BillingToggle (monthly/yearly), FromPrice, ...
│   │   ├── LanguageSwitcher.astro / CurrencySwitcher.astro
│   │   ├── ConsentBanner.astro    # Cookie consent; GA4 loads only after "Accept"
│   │   ├── LegalLayout.astro / Fact.astro  # Legal pages: EN + NO bodies; {{VERIFY}} facts highlighted
│   │   └── Tr.astro           # Inline EN + NO text for copy containing markup (links) that data-i18n can't carry
│   ├── pages/
│   │   ├── index.astro        # Home
│   │   ├── features.astro     # Full feature breakdown (mirrors files/FEATURES.md)
│   │   ├── pricing.astro      # Chat Widget plans + billing FAQ (from src/data/pricing.ts)
│   │   ├── agents.astro       # The Mielikkix Force agents — status + live-demo links
│   │   ├── agent-pricing.astro    # Per-agent prices and bundles
│   │   ├── about.astro / contact.astro / 404.astro
│   │   ├── demo.astro         # Free-demo lead form (POSTs to PUBLIC_API_URL/api/leads → Mailchimp sync)
│   │   ├── demo/              # One live, talk-to-it-now page per agent
│   │   │   ├── voice-receptionist.astro   # + public/voice-receptionist.js (Web Speech API)
│   │   │   ├── booking-assistant.astro    # + public/booking-assistant.js
│   │   │   ├── support-triage.astro       # + public/support-triage.js
│   │   │   ├── review-reputation.astro    # + public/review-reputation.js
│   │   │   └── whatsapp-concierge.astro   # + public/whatsapp-concierge.js — scripted, no backend
│   │   │                                   #   (WhatsApp number pending Meta approval)
│   │   ├── blog/index.astro / blog/[slug].astro   # Articles fetched at build time from
│   │   │                                           # GET /api/public/articles (admin CMS)
│   │   └── privacy / terms / dpa / subprocessors / cookies / security .astro   # Legal pages
│   ├── data/pricing.ts        # THE price list (fixed NOK excl. MVA) — app mirrors it in plans.py/agent_catalog.py
│   ├── config/
│   │   ├── currency.ts        # Supported currencies; BASE_CURRENCY = NOK
│   │   └── legal.ts           # Company facts, document versions, subprocessors, cookie table
│   ├── lib/
│   │   ├── i18n/translationService.ts   # Client-side i18n runtime
│   │   ├── articles.ts        # Build-time client for the public articles API
│   │   ├── articleTables.ts   # Styles plain CMS <table> markup at build time
│   │   ├── consent.ts         # Cookie-consent state (mx_consent cookie) + GA loader
│   │   └── offeringSchema.ts  # schema.org JSON-LD for each offering (prices from data/pricing.ts)
│   ├── stores/currencyStore.ts / services/CurrencyService.ts   # Frankfurter exchange rates + cache
│   └── assets/i18n/<en|no>/*.json   # Translation namespaces per page + common/footer/company
├── public/
│   ├── .htaccess              # Security headers + CSP for Hostinger (no 'unsafe-inline' scripts)
│   ├── i18n-guard.js          # Pre-paint FOUC guard
│   ├── widget-common.js       # Shared helpers for the demo widgets (window.MlxWidget)
│   ├── demo-form.js           # /demo form submit handler
│   ├── voice-receptionist.js / booking-assistant.js / support-triage.js /
│   │   review-reputation.js / whatsapp-concierge.js   # One logic file per /demo/<agent> page
│   ├── reduced-motion-video.js
│   ├── flags/ / images/ / favicon.png / mielikkix-logo.png / og-image.png / robots.txt
└── tests/                     # node --test: pricing, norwegianPages, articleTables
```

## Content source of truth

Feature copy is derived from `files/FEATURES.md` at the repo root (the canonical "actually built
and working" list). **Prices** come from `src/data/pricing.ts`, mirrored in the app's
`apps/api/app/core/plans.py` and `agent_catalog.py` — change all three together (see
`docs/pricing-rules.md`). Update the source first, then the pages — don't let them drift.

## Known gaps / before going live

- ~~`site` domain is a placeholder~~ — fixed: `astro.config.mjs`, `public/robots.txt`, and the
  dashboard's `AuthLayout.tsx` (`MARKETING_URL`) all now point at the real registered domain,
  `https://mielikkix.ai`.
- ~~No `og-image.png`~~ — fixed: `public/og-image.png` (1200×630, on-brand) now exists; social
  shares render a real preview instead of a broken image.
- ~~Demo form has no backend~~ — fixed: `src/pages/demo.astro` now `POST`s directly to the
  Mielikkix API's public `/api/leads` endpoint.
- **Analytics scaffolding is in `Layout.astro` but inactive** — a Plausible snippet is wired up
  behind `PUBLIC_PLAUSIBLE_DOMAIN`; it renders nothing until that env var is set to a real domain
  registered with a Plausible account. Sign up, add the var to `.env.production`, redeploy.
- **GA4 is consent-gated (GDPR / ekomloven § 2-7b)** — `components/ConsentBanner.astro` (in
  `Layout.astro`) + `src/lib/consent.ts`. Nothing is requested from Google until the visitor clicks
  "Accept all" (or enables Analytics in "Settings"); only then is the gtag loader injected, with
  Consent Mode v2 defaults all `denied` and only `analytics_storage` upgraded. The choice is stored
  in the first-party `mx_consent` cookie (12 months, carries `CONSENT_VERSION` from
  `src/config/legal.ts` — bump it to re-ask everyone). The footer's "Cookie settings" button
  (`[data-consent-open]`) reopens the banner; rejecting/withdrawing sets `ga-disable-<ID>` and deletes
  `_ga*` cookies. Banner strings live in `footer.json`'s `CONSENT` block (the always-loaded
  namespace). Needs `PUBLIC_GA_MEASUREMENT_ID`; unset = no GA at all. CSP in `public/.htaccess`
  allowlists `*.google-analytics.com`/`*.analytics.google.com`/`*.googletagmanager.com` (GA4's
  EU hits go to `region1.google-analytics.com`). website/-only — mielikkix.com/.no are not wired up.
- **Legal pages** — `/privacy`, `/terms`, `/dpa`, `/subprocessors`, `/cookies`, `/security`, all on
  `components/LegalLayout.astro`, which takes a full English and a full Norwegian body (named slots
  `en`/`no`) and shows the one matching the stored language. The shared facts (company details,
  document versions, the subprocessor list, the cookie table) live in `src/config/legal.ts`: update
  them there, not per page. Unconfirmed facts are `{{VERIFY: …}}` values, rendered highlighted by
  `components/Fact.astro`. Resolve them all, and get a lawyer's review, before launch.
- **No testimonials/social proof yet** — the home page has a placeholder social-proof strip
  ("Built for retail shops, clinics, restaurants...") instead of real customer logos/quotes, since
  Mielikkix doesn't have paying customers yet. Replace once available — don't fabricate
  quotes/logos in the meantime.

## Commands

```bash
cd website
npm install
npm run dev       # local dev server
npm run build     # static build to dist/
npm run preview   # serve the production build locally
npm test          # node --test (pricing, Norwegian pages, article tables)
```
