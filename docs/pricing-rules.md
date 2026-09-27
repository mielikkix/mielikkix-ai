# Pricing rules

How plan limits, overage, upgrades and cancellations work. The customer-facing wording is
in the pricing FAQs (`website/src/data/pricing.ts`); this file says what the app must do and
what it does today. Keep the two in step.

Last reviewed: 2026-09-27

## Prices

- One price list: `website/src/data/pricing.ts` (fixed NOK per month, excl. 25% MVA,
  business customers). The app mirrors the Chat Widget and SEO prices in
  `apps/api/app/core/plans.py` and `apps/api/app/core/agent_catalog.py` (`price_nok`).
  Change all three together.
- Tier names everywhere: Free, Start, Business, Growth. The Chat Widget plan key for Start
  is still `basic` and the SEO Start tier key is still `professional`; only the names changed,
  so no stored data needed migrating.
- Yearly billing = 10 × the monthly price ("2 months free").
- No payment processor yet (`stripePriceId: null`). Invoices are issued manually.

## Limits

| Product | Rule | In the app today |
|---|---|---|
| Chat Widget (conversations) | **Soft limit.** Email the account owner at 80% and 100% of the monthly quota. The widget keeps answering up to **10% over** the limit, then new conversations get HTTP 402 and the widget shows its contact form instead. No overage charges. Conversations already in progress are never cut off. Resets on the 1st. | **Implemented**: `plan_service.check_conversation_limit` / `claim_quota_warning`, `notify_quota_warning`, widget `ChatWindow.tsx` (402 → contact form). Tests: `test_plan_service.py`, `test_chat_conversation_limit.py` |
| Support Triage (tickets) | No overage charges; every ticket is handled. Customers who regularly exceed their plan are contacted about upgrading (manual). Target: the Chat Widget's soft limit with 80%/100% emails. | **Not automated.** Support Triage runs only on Mielikkix's own site today (no per-tenant ticket counting). The site FAQ only promises the manual rule. |
| Booking Assistant (calendars, locations) | Structural limits, not usage: more calendars/locations need an upgrade. No overage. | Multi-calendar and multi-location are not built yet (shown as "Coming soon"). |
| Review & Reputation (locations) | Structural limit, no overage. | One Google location per business today; more are "Coming soon". |
| Voice Receptionist (minutes) | **Overage billed monthly**: 4.00 / 3.50 / 3.00 kr per minute on Start / Business / Growth, itemised on the invoice. Calls are always answered. Target: 80%/100% emails like the Chat Widget. | **Not implemented**: no minute metering or overage billing yet; the site FAQ doesn't promise the emails. |
| SEO Audit & Optimize | Per website. Business/Growth are managed services (our team does the work). | Free/Start self-serve in the app; Managed is handled outside the app. |
| Custom AI agents | Minimum term `CUSTOM_AGENT_MIN_TERM_MONTHS` (12), no setup fee. | Contract, not app-enforced. Owner still deciding vs. month-to-month + setup fee (15 000–75 000 kr). |

## Plan changes and cancellation

- **Upgrades** apply immediately; the price difference is prorated.
- **Downgrades** apply from the next billing period.
- **Cancel any time** on monthly plans; access runs to the end of the paid period. Custom
  agents follow their minimum term.

These are billing policies; there is no automated billing yet, so they're applied when invoicing.

## Open questions

- Business-plan API add-on: the backend still has it at +$12/mo, but it's not on the NOK price list.
- Email Marketing agent: not on the price list; `agent_catalog.py` uses 390 kr as a placeholder.
