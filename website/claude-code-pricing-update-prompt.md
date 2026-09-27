# Claude Code Prompt — Mielikkix NOK Pricing Model Update

Paste everything below into Claude Code from the root of the `mielikkix-ai` marketing-site repo (Astro + React islands).

---

## Role and goal

You are updating the pricing model on the Mielikkix marketing site (mielikkix.ai). Replace the current euro/USD-converted pricing with **fixed NOK monthly prices, excluding MVA**. Use **one unified tier naming scheme** across every product. Give every AI agent its own **pricing chart** (tier cards + comparison table + price/usage chart). Work in small commits and report what you changed at the end.

## Step 0 — Discover before editing

Before changing anything, find and list:

1. Every place a price appears: hardcoded `€` strings, the currency-conversion component, the homepage pricing teaser, `/pricing`, `/agent-pricing`, `/agents`, each `/demo/*` page, FAQ blocks, JSON-LD, and the Norwegian `/no/*` routes.
2. The i18n setup (how EN/NO strings are stored).
3. Any existing pricing data file or types.

Print a short inventory, then continue. Do not ask for approval unless something blocks you.

## Step 1 — Single source of truth

Create `src/data/pricing.ts` as the **only** place prices live. Every page and component must read from it. After this change, no page may contain a hardcoded price string.

```ts
export type TierId = 'free' | 'start' | 'business' | 'growth';
export type ProductId =
  | 'chat-widget' | 'voice-receptionist' | 'booking-assistant'
  | 'support-triage' | 'review-reputation' | 'seo-audit' | 'custom-agents';

export interface Tier {
  id: TierId;
  priceNokMonthly: number | null;   // null = free
  priceFrom?: boolean;              // true → render "from 14 900 kr"
  recommended?: boolean;            // ⭐ badge (always the Business tier)
  managed?: boolean;                // SEO Business/Growth → "Managed" label
  included: { label: { en: string; no: string }; value: number | string }[];
  overage?: { unit: { en: string; no: string }; priceNok: number } | null;
  features: { en: string; no: string }[];
  minTermMonths?: number;           // custom agents: 12
  stripePriceId?: string | null;    // placeholder, keep null for now
}

export interface Product {
  id: ProductId;
  name: { en: string; no: string };
  emoji: string;
  usageUnit: { en: string; no: string };   // used as the chart's second axis
  tiers: Tier[];
}
```

Also export `addons`, `bundles`, and a `PRICING_META` object with:

- `currency: 'NOK'`
- `vatRate: 0.25`
- `pricesExcludeVat: true`
- `yearlyMonthsCharged: 10` ("2 months free")
- `audience: 'business'`

## Step 2 — The price data (enter exactly)

All prices are NOK per month, excluding 25% MVA. The tier names are the same everywhere: **Free → Start → Business ⭐ → Growth**. Free exists only for Chat Widget and SEO.

| Product | Free | Start | Business ⭐ | Growth |
|---|---|---|---|---|
| AI Chat Widget | 0 · 50 conversations, 1 website | 490 · 1,000 conversations, 1 website | 990 · 5,000 conversations, 3 websites | 1,990 · 20,000 conversations, 10 websites, API included |
| 📞 Voice Receptionist | — | 590 · 100 min, 1 Norwegian number, overage 4.00 kr/min | 1,790 · 500 min, call summaries, transfer to staff, overage 3.50 kr/min | 3,990 · 1,500 min, 3 numbers/locations, overage 3.00 kr/min |
| 📅 Booking Assistant | — | 390 · 1 calendar, chat booking | 890 · up to 5 staff calendars, SMS/email reminders | 1,790 · up to 15 calendars, 3 locations |
| 💬 Support Triage | — | 990 · 500 tickets, 3 seats, auto-classify + route | 2,490 · 2,000 tickets, 10 seats, AI-drafted replies | 4,990 · 6,000 tickets, unlimited seats, SLA rules |
| ⭐ Review & Reputation | — | 390 · 1 location, Google reviews, AI reply drafts | 890 · 3 locations, Google + Facebook + Trustpilot, review requests | 1,990 · 10 locations, sentiment reports |
| 🔎 SEO Audit & Optimize | 0 · self-serve audit (keep current Free features) | 490 · self-serve + Google Analytics + Search Console, scheduled audits (was "Professional") | 5,900 · **Managed**: monthly done-for-you fixes, local business | 9,900 · **Managed**: larger sites, content plan, monthly report |
| 🧠 Custom AI Agents | — | 2,990 · one agent, one integration, 12-month term, no setup fee | 6,990 · multi-step agent, up to 3 integrations, 12-month term | from 14,900 · multi-agent system, SLA, dedicated support, 12-month term |

**Add-on:** WhatsApp Concierge, 490/month, available on any Chat Widget plan. Remove its "Demo only" label only if the feature is live; otherwise show "Coming soon" with no price.

**Bundles:** compute the price and the saving from the data. Never hardcode them.

- **Front Desk:** Chat Business + Voice Business + Booking Business = 2,990/month (list sum 3,670).
- **Visibility:** SEO Start + Review Business + Chat Start = 1,590/month (list sum 1,870). Put it behind a feature flag `SHOW_VISIBILITY_BUNDLE = false`.

**Custom agents contract term:** put the 12-month minimum behind a config value `CUSTOM_AGENT_MIN_TERM_MONTHS = 12`. The owner is still deciding between this and month-to-month with a setup fee (15,000–75,000 kr).

## Step 3 — Pages to build or update

1. **`/pricing` (hub).** Add a product switcher (tabs or segmented control) with the Chat Widget selected by default. Put a Monthly / Yearly toggle beside it. Yearly shows the full yearly price (monthly × 10) and "2 months free". Below that, add a "Bundles" section and a short "All prices" note (see Step 5).
2. **Per-agent pricing: build a pricing chart for EVERY agent.** Create a reusable `<ProductPricing productId="…" />` React island and use it on `/agent-pricing` (one section per agent, with anchor links) and on each agent's demo or detail page. For each product the island renders:
   - **Tier cards**: name, price ("990 kr/mnd eks. mva."), included usage, overage, 4–6 key features, CTA, ⭐ badge on Business, "Managed" label on SEO Business/Growth, "from" prefix on Custom Growth.
   - **Comparison table**: one row per feature or limit, one column per tier, ✓ / — / values. Make it horizontally scrollable on mobile.
   - **Price vs included usage chart**: a small bar chart. Bars show the monthly price per tier; the label on each bar shows the included units (minutes, conversations, tickets, calendars, locations). Also show the **effective price per unit** in the caption (e.g. voice: 5.90 / 3.58 / 2.66 kr per minute). Build it as a lightweight accessible SVG (no new chart library unless one is already installed). Give it an `aria-label`, and hide the decorative bars from screen readers when the same numbers are in the table.
   - **Product FAQ**: 3–4 questions, including what happens at the limit (see Step 4).
3. **`/agents`**: replace every "Custom Pricing" badge with "From X kr/mnd" read from the data (lowest paid tier). Link each card to its section on `/agent-pricing`.
4. **Homepage pricing teaser**: show the Chat Widget tiers in NOK, read from the data.
5. **Norwegian routes (`/no/...`)**: build the same pages with Norwegian strings. Use Norwegian number formatting with a non-breaking space as thousands separator: `1 990 kr/mnd`, `eks. mva.`. English pages use `NOK 1,990/month excl. VAT`.
6. **JSON-LD**: add `Product` + `Offer` schema per tier, with `priceCurrency: "NOK"`, `price`, and `priceSpecification.valueAddedTaxIncluded: false`.

## Step 4 — Resolve the known FAQ contradictions

The current pricing spreadsheet and the live FAQ disagree. Apply one consistent rule everywhere:

- **Chat Widget, Support Triage, Booking, Reviews:** soft limit. The customer gets an email at 80% and 100% of their quota, and is asked to upgrade. There are **no surprise overage charges**, and the bot keeps answering up to 10% over the limit, then shows the contact form.
- **Voice Receptionist:** the overage per minute is **shown on the card** (4.00 / 3.50 / 3.00 kr/min), and billed monthly.
- **Upgrades** take effect immediately, and the difference is prorated. **Downgrades** take effect from the next billing period.
- **Cancel anytime** on monthly plans, and access runs to the end of the paid period. Custom agents follow their minimum term.

## Step 5 — Norwegian pricing-rule compliance (must do)

- Next to every price, state that it excludes MVA: "eks. mva." (NO) / "excl. VAT" (EN). Add one line on each pricing page: "Prices are for businesses and exclude 25% MVA." Optionally show the MVA-inclusive amount on hover or in the table footnote.
- **Complete prices.** Every recurring fee, overage rate, setup fee, and minimum term must be visible on the pricing page itself, not only in the Terms page.
- **No invented "before" prices.** Don't show crossed-out or "was" prices. Savings text (bundles, yearly) must be calculated from the current list prices in `pricing.ts`.
- **Remove the text "converted from USD using current exchange rates"** for NOK. The NOK prices are fixed. If EUR/USD display stays for international visitors, use fixed price tables per currency (add `priceEurMonthly` later), not live conversion.
- **Don't name competitors** on the site. The competitor research is internal only.
- Keep the links to Terms, DPA, Privacy and Subprocessors in the pricing page footer.

## Step 6 — Acceptance criteria

- `grep -rn "€" src/` returns no pricing strings. All prices come from `src/data/pricing.ts`.
- Changing one number in `pricing.ts` updates every card, table, chart, bundle saving, the yearly price, and the JSON-LD.
- Every agent (Voice, Booking, Support Triage, Review & Reputation, SEO, Custom Agents) plus the Chat Widget has tier cards, a comparison table, and a price/usage chart.
- Tier names are only Free / Start / Business / Growth. Search the codebase for "Basic", "Professional", "Solo", "Team", "Pro", "Scale", "Multi", "Lite" and "Enterprise" used as tier names, and remove them.
- EN and NO pages both render. NO uses `1 990 kr/mnd eks. mva.`
- Lighthouse accessibility ≥ 95 on `/pricing` and `/agent-pricing`. The charts have text alternatives.
- `astro build` passes with no type errors. Add a unit test that checks every product has 3–4 tiers, that exactly one tier is `recommended`, and that bundle prices are lower than their list sums.

## Out of scope (leave placeholders)

- Stripe products/prices (`stripePriceId: null`) and checkout.
- Quota enforcement in app.mielikkix.ai (document the rules from Step 4 in `docs/pricing-rules.md` so the app team can implement them).

## Final report

When done, list the files changed, the routes added or updated, screenshots or descriptions of one pricing chart per agent, and any open questions (for example the custom-agent contract term).
