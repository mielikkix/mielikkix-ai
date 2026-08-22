from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import field_validator
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
# <repo>/apps/api/app/core/config.py, but the image copies apps/api to /app,
# making it /app/app/core/config.py. A hardcoded index that matches the
# checkout raises IndexError in the container, killing the app at import.
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

    # Comma-separated emails allowed into the platform-operator-only /admin
    # dashboard (see app/core/dependencies.py:require_platform_admin). Not a
    # DB flag on purpose -- this is the platform owner, not a per-tenant role,
    # so it belongs in deployment config, not a table any tenant data touches.
    platform_admin_emails: str = ""

    @property
    def platform_admin_emails_list(self) -> list[str]:
        return [e.strip().lower() for e in self.platform_admin_emails.split(",") if e.strip()]

    class Config:
        env_file = str(_ROOT_ENV_FILE)
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
