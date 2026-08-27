from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import field_validator, model_validator
from functools import lru_cache

# Known placeholder values from .env.example / older defaults. If the running
# config still has one of these, SECRET_KEY was never actually set — signing
# tokens with a value visible in this repo would let anyone forge a valid
# JWT for any user, so we fail fast at startup instead of running insecurely.
_INSECURE_SECRET_KEYS = {
    "change-me-in-production",
    "change-me-to-a-random-64-char-string",
    "",
}

# Anchored absolutely (not relative to cwd) so settings load correctly
# whether the app is started from the repo root, from apps/api/, or via
# Docker — pydantic-settings otherwise resolves env_file relative to the
# process's working directory, which silently falls back to these classes'
# defaults if that directory doesn't happen to contain a .env of its own.
#
# Found by walking up rather than by a fixed parents[N], because how deep
# this file sits depends on where it's running: on a checkout it's
# <repo>/apps/api/app/core/config.py, but the Docker image copies apps/api
# to /repo/apps/api, making it /repo/apps/api/app/core/config.py. A
# hardcoded index that matches the checkout raises IndexError in the
# container, killing the app at import.
def _find_root_env_file() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / ".env"
        if candidate.is_file():
            return candidate
    # None found -- normal in Docker, where compose's `env_file:` injects the
    # values as real environment variables and no .env exists in the image.
    # Return a path that simply doesn't exist; pydantic-settings ignores a
    # missing env_file and reads the environment, which is what we want.
    return here.parents[-1] / ".env"


_ROOT_ENV_FILE = _find_root_env_file()


class Settings(BaseSettings):
    app_name: str = "MielikkiX API"
    debug: bool = False

    database_url: str = "postgresql://mielikkix:mielikkix@localhost:5432/mielikkix"

    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    @field_validator("secret_key")
    @classmethod
    def _reject_insecure_secret_key(cls, v: str) -> str:
        if v in _INSECURE_SECRET_KEYS or len(v) < 32:
            raise ValueError(
                "SECRET_KEY is missing, a known placeholder, or too short. "
                "Set a real random value (32+ chars, e.g. `python -c "
                "\"import secrets; print(secrets.token_urlsafe(48))\"`) in your .env."
            )
        return v

    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 10

    default_llm_provider: str = "groq"
    groq_api_key: str = ""
    gemini_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # Default model per provider, used when a business hasn't set its own
    # business_settings.llm_model. Configurable via env on purpose: providers
    # retire models on their own schedule (Groq dropped llama-3.1-8b-instant,
    # which 404'd every chat request until this was changed), and recovering
    # from that should be an env change + restart, not a code deploy.
    # Check what a key can actually serve: GET https://api.groq.com/openai/v1/models
    groq_model: str = "openai/gpt-oss-120b"
    gemini_model: str = "gemini-2.0-flash"
    ollama_model: str = "llama3"
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    resend_api_key: str = ""
    # mielikkix.no is verified on Resend (see files/CLAUDE.md's notification
    # setup). Default to the real sender, not Resend's sandbox address
    # (onboarding@resend.dev) -- the sandbox only ever delivers to the Resend
    # account owner, so a deployment that forgot to set
    # NOTIFICATION_FROM_EMAIL would silently never reach real customers/leads.
    notification_from_email: str = "post@mielikkix.no"

    # Where dashboard-facing links in emails (e.g. password reset) should point.
    frontend_url: str = "http://localhost:5173"

    # Multilingual so retrieval works for non-English visitor questions against
    # (typically English) source documents -- all-MiniLM-L6-v2 is English-only,
    # which made cross-lingual queries score near zero and fall through to the
    # generic fallback message almost every time. Same 384-dim output, so no
    # storage/schema changes -- but existing chunks were embedded with the old
    # model and must be re-embedded, see scripts/reembed_documents.py.
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    chunk_size: int = 600
    chunk_overlap: int = 50
    retrieval_top_k: int = 4

    # Plain str (not list[str]): pydantic-settings tries to JSON-decode
    # list-typed fields at the source level, before any validator runs,
    # which breaks the comma-separated format .env documents for this.
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # Voice Receptionist agent (apps/agents/voice-receptionist). Empty
    # twilio_auth_token is treated as "not configured yet" and skips webhook
    # signature validation (see app/api/agents_voice.py) -- convenient for a
    # first local run, but this MUST be set before the number goes anywhere
    # near production, or anyone who finds the webhook URL can post fake
    # call events at it.
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    # The public URL Twilio actually calls -- your ngrok/cloudflared URL
    # while testing locally, the real api.mielikkix.ai URL in production.
    # Needed because Twilio signs its request against the exact URL it
    # dialed, and that's not always what request.url reports on this end
    # once a tunnel/proxy sits in front of the server.
    voice_agent_public_base_url: str = "http://localhost:8000"
    # Which business's FAQs/documents/products the voice agent's replies are
    # grounded against -- a stand-in for real multi-tenant routing (looking
    # this up from the dialed phone number), which doesn't exist yet since
    # the agent only has one number's worth of traffic to handle so far.
    # Empty means ungrounded (Phase 1 behavior: honest "I don't know").
    voice_agent_business_id: str = ""
    # Deliberately NOT settings.debug -- debug also controls auth.py's
    # cookie `secure` flag (secure=not settings.debug), so flipping it on
    # in production to unlock the public demo would silently make every
    # login session cookie on the live dashboard non-Secure. This flag only
    # affects agents_voice.py's /dev/start and /dev/gather JSON routes (the
    # ones the public marketing-site demo page calls) -- NOT /dev/voice-test,
    # the internal HTML test harness, which stays debug-only either way.
    voice_agent_public_demo: bool = False

    # Comma-separated emails allowed into the platform-operator-only /admin
    # dashboard (see app/core/dependencies.py:require_platform_admin). Not a
    # DB flag on purpose -- this is the platform owner, not a per-tenant role,
    # so it belongs in deployment config, not a table any tenant data touches.
    platform_admin_emails: str = ""

    # Booking Assistant agent (apps/agents/booking-assistant) -- books
    # directly against Google Calendar (not Cal.com -- see that agent's
    # CLAUDE.md for why that plan was reversed). Each real tenant will
    # eventually connect their OWN calendar via OAuth from the dashboard
    # (Phase 5); these three settings are Phase 1 scope only -- ONE
    # hardcoded test calendar's credentials, obtained by running
    # scripts/connect_google_calendar.py once locally (opens a browser for
    # you to sign in, then prints the values below to paste into .env).
    #
    # google_calendar_client_id/secret identify OUR APP to Google, not any
    # one tenant -- created once in Google Cloud Console (Phase 0: a new
    # project, Calendar API enabled, an OAuth 2.0 Client ID of type "Web
    # application"). The SAME client_id/secret is reused for every tenant's
    # OAuth connection later; only the refresh token differs per tenant.
    google_calendar_client_id: str = ""
    google_calendar_client_secret: str = ""
    # The one test calendar's long-lived refresh token (Phase 1 only -- a
    # real per-tenant one replaces this in Phase 5). Python note: unlike an
    # API key, this alone can't authenticate a request -- app/integrations/
    # google_calendar_client.py exchanges it for a short-lived access token
    # on demand (google-auth's Credentials class does this refresh
    # automatically), the same reason a Refresh/Access token pair works in
    # any OAuth2-based TS auth library you've used.
    google_calendar_refresh_token: str = ""
    # Which calendar to check/book against for that connected account --
    # "primary" is Google's own special ID for "this account's default
    # calendar", not a placeholder needing to be filled in with a real ID.
    google_calendar_id: str = "primary"

    # Support Triage agent (apps/agents/support-triage) -- unlike every
    # other agent, this one's "tenant" is the platform itself: it powers
    # the chat widget on website/ (Mielikkix's OWN marketing site), talking
    # to ITS visitors, not a tenant business's customers. This is Mielikkix's
    # own Business record in packages/db, the same one
    # scripts/setup_local_mielikkix_business.py creates -- a separate
    # setting from voice_agent_business_id (not reused, even though it'll
    # often point at that exact same business record locally) so each
    # agent's grounding can be pointed elsewhere independently later.
    # Empty means ungrounded (honest "I don't know" instead of guessing).
    support_agent_business_id: str = ""
    # Below this confidence (0-1, from the LLM's own classification call --
    # see app/api/agents_support.py), Phase 1 does not attempt a direct
    # answer. Phase 2 (this agent's CLAUDE.md) will additionally escalate
    # to a human below this same threshold; Phase 1 just declines to guess.
    support_agent_confidence_threshold: float = 0.6

    @property
    def platform_admin_emails_list(self) -> list[str]:
        return [e.strip().lower() for e in self.platform_admin_emails.split(",") if e.strip()]

    # A Twilio account/number configured with no auth token means
    # agents_voice.py's _assert_valid_twilio_request silently skips signature
    # checking -- fine for a fresh local checkout (nothing configured at
    # all), but if TWILIO_ACCOUNT_SID or TWILIO_PHONE_NUMBER is set while
    # TWILIO_AUTH_TOKEN isn't, that's a half-finished deployment leaving the
    # /incoming and /gather webhooks open to anyone who finds the URL. Only
    # checked outside debug mode, and only once the voice agent is actually
    # being turned on -- not a blanket requirement, since apps/api is one
    # shared process for every feature (see root CLAUDE.md convention #4)
    # and most deployments won't have Twilio configured at all yet.
    @model_validator(mode="after")
    def _require_twilio_auth_token_if_voice_configured(self) -> "Settings":
        voice_configured = bool(self.twilio_account_sid or self.twilio_phone_number)
        if not self.debug and voice_configured and not self.twilio_auth_token:
            raise ValueError(
                "TWILIO_AUTH_TOKEN is empty but TWILIO_ACCOUNT_SID/"
                "TWILIO_PHONE_NUMBER is set -- that leaves the voice agent's "
                "Twilio webhooks unauthenticated. Set TWILIO_AUTH_TOKEN, or "
                "clear the other Twilio settings if it isn't deployed yet."
            )
        return self

    class Config:
        env_file = str(_ROOT_ENV_FILE)
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
