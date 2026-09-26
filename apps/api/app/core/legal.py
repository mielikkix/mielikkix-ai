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
