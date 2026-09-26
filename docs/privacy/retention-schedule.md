# Retention schedule

Internal document: how long Mielikkix keeps each kind of data, and what deletes it. Every period
here must match the code. When you change one, change the other in the same commit. Periods marked
**(judgement call)** are internal decisions that the company's lawyer should confirm.

Last reviewed: 2026-09-26 (Phase 5: conversation retention added)

## Account holders (Mielikkix is controller)

| Data | Kept for | Deleted by | Source of truth |
|---|---|---|---|
| Account: user profile, business profile, settings, uploaded FAQs/documents/products, connected-integration tokens | While the account is active, plus a **30-day grace period** after the owner asks to delete it | Nightly job `nightly_privacy_purge` (03:15) → `account_service.purge_due` hard-deletes every table scoped to the business, plus uploaded files | `DELETION_GRACE_DAYS` in `apps/api/app/core/legal.py` |
| Consent records (terms, dpa, age_confirmation, marketing_email, including withdrawals) while the account exists | Life of the account | Minimised on account deletion (see next row) | `consent_records` table |
| Consent records after account deletion, **minimised** | **3 years** after the account is deleted **(judgement call)** | Same nightly job → `consent_service.purge_expired_minimised_records` | `CONSENT_RETENTION_AFTER_DELETION_DAYS` in `apps/api/app/core/legal.py` |
| Password reset tokens | Usable for 1 hour. The row is kept until the account is deleted | Account deletion | `RESET_TOKEN_TTL` in `apps/api/app/services/auth_service.py` |
| Session cookie `access_token` | 24 hours | Browser (expiry) | `access_token_expire_minutes` in `apps/api/app/core/config.py` |
| Accounting records | 5 years after the end of the financial year (bokføringsloven) | Manual. No invoices are stored in this codebase today | n/a |

### Minimised consent records: what's kept and why

When an account is hard-deleted, its consent rows are **not** deleted with it, and they are **not**
kept forever. `consent_service.minimise_for_deleted_user` runs in the same transaction as the deletion
and turns each row into:

- **kept:** `subject_hash` (HMAC-SHA256 of the lowercased email, keyed from the server secret),
  `type`, `document_version`, `granted`, `granted_at`, `withdrawn_at`, `source`, `retain_until`.
- **removed:** `user_id` (the link to the deleted user) and `ip_hash`. The name, business name,
  email and every other profile field go with the user and business rows.

Purpose: to demonstrate compliance and defend legal claims (GDPR art. 7(1) and art. 17(3)(e)). If a
former customer later disputes what they agreed to, we hash the email they give us and look up the
matching rows. The key means nobody without the server secret can reverse the hash by trying lists
of known email addresses. **If `SECRET_KEY` is rotated, existing hashes can no longer be matched.**
Keep the old key available for 3 years, or accept that consequence.

This is covered by `tests/test_account.py::test_purge_deletes_all_tenant_data_and_minimises_consent`
(no direct identifiers remain after deletion, and the rows are gone after 3 years).

## Website visitors (mielikkix.ai)

| Data | Kept for | Deleted by |
|---|---|---|
| `mx_consent` cookie (cookie choice) | 12 months, then the visitor is asked again | Browser (expiry) |
| Google Analytics cookies `_ga`, `_ga_<ID>` (only after the visitor opts in) | 2 years, or until consent is withdrawn (then deleted by `src/lib/consent.ts`) | Browser / consent withdrawal |
| Google Analytics data in GA4 | `{{VERIFY: GA4 data retention setting}}` | Google |
| `localStorage` language/currency preferences and exchange-rate cache | Until cleared (rate cache refreshes after 24 h) | Browser |

## Customers' end users (Mielikkix is processor)

| Data | Kept for | Deleted by |
|---|---|---|
| Chat conversations and their messages | The tenant's `conversation_retention_days`, counted from the last message: default **90**, allowed **1–365** (no "unlimited"). The 365 max is a **(judgement call)** | Nightly job → `retention_service.purge_expired_conversations`. Also account deletion, single-conversation delete, and visitor erasure (`POST /api/chat/visitors/erase`) |
| Leads (contact details a visitor chose to leave) | Until the tenant deletes them. They are the tenant's customer records. Retention only unlinks them from an expired conversation | Tenant action, visitor erasure, account deletion |
| Widget `mielikkix_session` (sessionStorage) | Until the browser tab closes | Browser |
| Voice call transcripts | Only in memory during the call. Never stored | n/a |

Constants: `CONVERSATION_RETENTION_DEFAULT_DAYS` / `_MIN_DAYS` / `_MAX_DAYS` in `apps/api/app/core/legal.py`,
enforced by `BusinessSettingsUpdate` in `apps/api/app/schemas/business.py`. Tests: `apps/api/tests/test_retention.py`.
