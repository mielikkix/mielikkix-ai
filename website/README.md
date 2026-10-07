# Mielikkix Marketing Site

Static Astro site for [mielikkix.ai](https://mielikkix.ai) — home page, features, pricing, the
AI agents with live demos, blog, legal pages and free-demo booking, in English and Norwegian (`/no/`). Separate from `apps/dashboard/` (the logged-in admin dashboard); see
`ARCHITECTURE.md` in this folder for why, the tech stack, folder structure, and the current list
of known gaps to close before going live.

## Commands

```bash
npm install
npm run dev       # local dev server at localhost:4321
npm run build     # static build to dist/
npm run preview   # serve the production build locally
npm test          # node --test (pricing, Norwegian pages, article tables)
```

## Content source of truth

Feature copy comes from `files/FEATURES.md` at the repo root; prices from `src/data/pricing.ts`
(mirrored in the app — see `docs/pricing-rules.md`). Update those first, then the pages.
