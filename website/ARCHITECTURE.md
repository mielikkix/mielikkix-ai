# MielikkiX Marketing Site — Architecture

Promotion/marketing site for MielikkiX: home page, features, pricing, and free-demo booking.
Separate from `apps/dashboard/` (the admin/analytics dashboard, a React SPA) — this is a
purely static, SEO-first site with a different tech stack for a different job.

## Why a separate stack from `apps/dashboard/`

`apps/dashboard/` is a logged-in, data-heavy React SPA — SEO doesn't matter there, it's behind auth.
This site is the opposite: it's the thing small-business owners find via Google before they've
ever heard of MielikkiX, so page-load speed and crawlability are the whole game. A client-rendered
SPA is the wrong tool for that job — hence a separate static-generation project instead of adding
public routes to the dashboard app.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Framework | [Astro](https://astro.build) (static output) | Ships zero JS by default — every page here is static HTML/CSS, only the demo form has a few lines of vanilla JS. Best-in-class Lighthouse/Core Web Vitals scores, which directly affects Google ranking for local/small-business search. |
| Styling | Tailwind CSS v4 (via `@tailwindcss/vite`) | Same utility approach as `apps/dashboard/`, so styling knowledge transfers. Tailwind v4 needs no `tailwind.config.js` — theme tokens (colors, etc.) come from Tailwind's default palette plus a couple of custom CSS variables in `src/styles/global.css`. |
| Fonts | Google Fonts (Sora for headings, Inter for body), loaded via `@import` in `global.css` | Free, fast, no build step needed. |
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

```
website/
├── src/
│   ├── layouts/
│   │   └── Layout.astro       # <html> shell: meta/OG/Twitter tags, Header, Footer, slot,
│   │                           # i18n/currency bootstrap, sitewide support-chat-widget.js embed
│   ├── components/
│   │   ├── Header.astro       # Sticky nav, CSS-only (checkbox-hack) mobile menu
│   │   ├── Footer.astro
│   │   ├── PageHero.astro     # Shared hero heading/subheading block, reused on every inner page
│   │   ├── BentoCard.astro / FeatureBentoCard.astro  # Bento-grid feature cards (Home & Features)
│   │   ├── CTASection.astro   # Reusable gradient CTA banner, reused on every marketing page
│   │   ├── Price.astro        # Renders a [data-price-usd] amount, live-converted by currencyStore
│   │   ├── LanguageSwitcher.astro   # EN/NOR switcher — drives currency together (see below)
│   │   └── CurrencySwitcher.astro   # Independent currency override (view USD without switching language)
│   ├── pages/
│   │   ├── index.astro        # Home — hero, feature highlights, how-it-works, pricing teaser, CTA
│   │   ├── features.astro     # Full feature breakdown, grouped by category (mirrors files/FEATURES.md)
│   │   ├── pricing.astro      # 4-tier pricing cards + billing FAQ (mirrors files/FEATURES.md plans)
│   │   ├── agents.astro       # The 10 Mielikkix Force agents — status + live-demo links
│   │   ├── demo.astro         # Free-demo lead capture form (POSTs to PUBLIC_API_URL/api/leads)
│   │   ├── demo/               # One live, talk-to-it-now page per flagship/built agent
│   │   │   ├── voice-receptionist.astro   # + public/voice-receptionist.js (Web Speech API)
│   │   │   ├── booking-assistant.astro    # + public/booking-assistant.js
│   │   │   ├── support-triage.astro       # + public/support-triage.js
│   │   │   └── review-reputation.astro    # + public/review-reputation.js
│   │   └── privacy.astro
│   ├── lib/i18n/translationService.ts   # Client-side i18n runtime: lazy JSON, dot-path lookup, DOM apply
│   ├── stores/currencyStore.ts          # Reactive currency state + DOM apply, on top of CurrencyService
│   ├── services/CurrencyService.ts      # Exchange-rate fetch (Frankfurter) + localStorage cache/fallback
│   ├── config/currency.ts               # Supported currencies, base currency, cache TTL
│   ├── utils/currencyFormatter.ts
│   └── assets/i18n/<en|no>/*.json       # Per-page + shared (common/footer) translation namespaces —
│                                         # add a language by adding a folder here + one entry in
│                                         # SUPPORTED_LANGUAGES (translationService.ts)
├── public/
│   ├── favicon.ico / favicon.svg / og-image.png
│   ├── i18n-guard.js              # Pre-paint FOUC guard (see translationService.ts's own comment)
│   ├── demo-form.js               # /demo lead-capture form submit handler
│   ├── support-chat-widget.js     # Sitewide bubble embedded in Layout.astro on every page —
│   │                               # talks to Support Triage (app/api/agents_support.py), NOT the
│   │                               # tenant-facing product Chat Widget — see its own file comment
│   ├── voice-receptionist.js / booking-assistant.js / support-triage.js / review-reputation.js
│   │                               # One conversation-logic file per /demo/<agent> page. Kept as
│   │                               # external files (not inline <script>) because the CSP below has
│   │                               # no 'unsafe-inline' for script-src.
│   ├── reduced-motion-video.js
│   ├── flags/                     # Vendored flag-icons SVGs for LanguageSwitcher/CurrencySwitcher
│   └── robots.txt
├── .htaccess (public/) — security headers + CSP, deployed as-is to Hostinger's public_html
└── astro.config.mjs           # site URL (for sitemap), Tailwind + sitemap integrations
```

## Content source of truth

Page copy (features, pricing tiers, billing policy) is derived from `files/FEATURES.md` at the
repo root, which is the canonical, "actually built and working" feature/pricing list. When a
feature ships or a plan changes, update `files/FEATURES.md` first, then reflect it here — don't
let the two drift.

## Known gaps / before going live

- ~~`site` domain is a placeholder~~ — fixed: `astro.config.mjs`, `public/robots.txt`, and the
  dashboard's `AuthLayout.tsx` (`MARKETING_URL`) all now point at the real registered domain,
  `https://mielikkix.ai`.
- ~~No `og-image.png`~~ — fixed: `public/og-image.png` (1200×630, on-brand) now exists; social
  shares render a real preview instead of a broken image.
- ~~Demo form has no backend~~ — fixed: `src/pages/demo.astro` now `POST`s directly to the
  MielikkiX API's public `/api/leads` endpoint.
- **Analytics scaffolding is in `Layout.astro` but inactive** — a Plausible snippet is wired up
  behind `PUBLIC_PLAUSIBLE_DOMAIN`; it renders nothing until that env var is set to a real domain
  registered with a Plausible account. Sign up, add the var to `.env.production`, redeploy.
- **No testimonials/social proof yet** — the home page has a placeholder social-proof strip
  ("Built for retail shops, clinics, restaurants...") instead of real customer logos/quotes, since
  MielikkiX doesn't have paying customers yet. Replace once available — don't fabricate
  quotes/logos in the meantime.

## Commands

```bash
cd website
npm install
npm run dev       # local dev server
npm run build     # static build to dist/
npm run preview   # serve the production build locally
```
