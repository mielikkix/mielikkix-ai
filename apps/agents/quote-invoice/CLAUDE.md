# CLAUDE.md — apps/agents/quote-invoice

Place this file at `mielikkix-ai/apps/agents/quote-invoice/CLAUDE.md`.

## What this agent does

Turns a customer's plain-language request ("I need 3 of these installed,
how much?") into a formal itemized quote, sends it for the customer's
review, and — once accepted — turns it into an invoice. Queued agent,
fast-follow after the 3 flagships (see root `CLAUDE.md`'s "Current
status").

## Integrations needed

- **Request parsing**: `packages/agent-core`'s LLM client — turns free text
  into itemized quote lines (same shape of problem as Booking Assistant's
  NL parsing; reuse that pattern, don't reinvent it).
- **Document generation**: a PDF for the actual quote/invoice document. No
  PDF library is a dependency yet — `apps/api/requirements.txt` has
  `python-docx` (Word documents) but nothing for PDF; adding one (e.g.
  `weasyprint` or `reportlab`) is part of this agent's own build.
- **Sending**: `apps/api/app/notifications` (Resend provider, already
  wired) — do not add a second email integration; attach the generated PDF
  to that.
- **Payment collection**: taking an actual payment against an invoice needs
  a real payment processor (e.g. Stripe) — **requires a real Stripe account
  and API keys**, a human setup step. Build quote → invoice → send first
  (none of that needs Stripe); payment collection is a later addition on
  top, deferred until that account exists.

## Data this agent stores

```
Quote
  id, business_id, customer_name, customer_email, line_items (JSON: description,
  quantity, unit_price), total, status (draft | sent | accepted | declined),
  created_at

Invoice
  id, quote_id, status (unpaid | paid), payment_reference (nullable until
  payment collection is wired up), created_at
```

## Real-time or batch?

Request/response, like Booking Assistant — a customer request comes in and
a quote comes back; no scheduled/batch component.

## Dashboard module

New "Quotes & Invoices" tab in `apps/dashboard`, gated by entitlement:
create/edit a quote manually or from a parsed request, send it, track
accept/decline, and (once payment collection exists) payment status.

## Definition of done for the 8-day sprint

- [ ] A plain-language request is parsed into an itemized quote
- [ ] Quote PDF generates and sends correctly via email
- [ ] Accepting a quote creates an invoice from it
- [ ] Quotes/invoices visible in dashboard, gated correctly by entitlement
- [ ] Deployed on the VPS, smoke-tested in production
