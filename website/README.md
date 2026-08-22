# MielikkiX Marketing Site

Static Astro site for [mielikkix.ai](https://mielikkix.ai) — home page, features, pricing, and
free-demo booking. Separate from `apps/dashboard/` (the logged-in admin dashboard); see
`ARCHITECTURE.md` in this folder for why, the tech stack, folder structure, and the current list
of known gaps to close before going live.

## Commands

```bash
npm install
npm run dev       # local dev server at localhost:4321
npm run build     # static build to dist/
npm run preview   # serve the production build locally
```

## Content source of truth

Page copy (features, pricing tiers, billing policy) is derived from `files/FEATURES.md` at the
repo root. Update that file first when a feature ships or a plan changes, then reflect it here.
