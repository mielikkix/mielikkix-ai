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
│   │   └── Layout.astro       # <html> shell: meta/OG/Twitter tags, Header, Footer, slot
│   ├── components/
│   │   ├── Header.astro       # Sticky nav, CSS-only (checkbox-hack) mobile menu
│   │   ├── Footer.astro
│   │   ├── FeatureCard.astro  # icon + title + description card, reused on Home & Features
│   │   └── CTASection.astro   # Reusable gradient CTA banner, reused on all 3 marketing pages
│   ├── pages/
│   │   ├── index.astro        # Home — hero, feature highlights, how-it-works, pricing teaser, CTA
│   │   ├── features.astro     # Full feature breakdown, grouped by category (mirrors files/FEATURES.md)
│   │   ├── pricing.astro      # 4-tier pricing cards + billing FAQ (mirrors files/FEATURES.md plans)
│   │   └── demo.astro         # Free-demo lead capture form
│   └── styles/
│       └── global.css         # Tailwind import, Google Fonts import, brand gradient utilities
├── public/
│   ├── favicon.ico / favicon.svg
│   └── robots.txt
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
- **No `og-image.png`** yet — `Layout.astro` references `/og-image.png` for social share previews;
  add a real 1200×630 image to `public/` before launch or social shares will show a broken image.
- ~~Demo form has no backend~~ — fixed: `src/pages/demo.astro` now `POST`s directly to the
  MielikkiX API's public `/api/leads` endpoint.
- **No analytics** wired up yet (e.g. Plausible, GA4, or Vercel Analytics) — needed to actually
  measure organic traffic and demo-request conversion once live.
- **No testimonials/social proof yet** — the home page has a placeholder social-proof strip
  ("Built for retail shops, clinics, restaurants...") instead of real customer logos/quotes, since
  MielikkiX doesn't have paying customers yet. Replace once available.

## Commands

```bash
cd website
npm install
npm run dev       # local dev server
npm run build     # static build to dist/
npm run preview   # serve the production build locally
```
