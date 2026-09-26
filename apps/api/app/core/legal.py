"""Versions of the legal documents a user accepts at sign-up, recorded on each
consent_records row so we can always prove WHICH text someone agreed to.

Must match LEGAL_DOCS in website/src/config/legal.ts (the published pages).
When the Terms or DPA text changes materially, bump the version in BOTH
places -- GDPR Phase 4's re-acceptance flow keys off these values.
"""

TERMS_VERSION = "terms-2026-09-25"
DPA_VERSION = "dpa-2026-09-25"

# consent_records.type values
CONSENT_TERMS = "terms"
CONSENT_DPA = "dpa"
CONSENT_AGE = "age_confirmation"
CONSENT_MARKETING = "marketing_email"

# consent_records.source values
SOURCE_REGISTER = "register"
SOURCE_SETTINGS = "settings"
SOURCE_UNSUBSCRIBE = "unsubscribe"
SOURCE_REACCEPT = "reaccept"

# GDPR Phase 4: account deletion.
# Days between "Delete my account" and the hard delete, during which the
# owner can still log in and cancel.
DELETION_GRACE_DAYS = 30
# How long pseudonymised consent records outlive a deleted account, so we can
# still demonstrate consent if a complaint arrives later (GDPR art. 7(1)).
# Decided 2026-09-26: keep 3 years, linked only to a keyed hash of the email.
CONSENT_RETENTION_AFTER_DELETION_DAYS = 3 * 365

# GDPR Phase 5: per-tenant retention of end-user chat conversations
# (business_settings.conversation_retention_days). No "unlimited": the
# nightly job deletes conversations whose last activity is older than this.
# MAX is a judgement call -- see docs/privacy/retention-schedule.md.
CONVERSATION_RETENTION_DEFAULT_DAYS = 90
CONVERSATION_RETENTION_MIN_DAYS = 1
CONVERSATION_RETENTION_MAX_DAYS = 365
