"""Central settings for the app/ backend. Import this before anything reads the environment."""
from __future__ import annotations

from functools import cached_property

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Also populate os.environ so legacy modules (kb, backend_config, outbound_calls) see the same values.
load_dotenv()

_LOCAL_DEV_SECRET_KEY = "local-dev-only-secret-do-not-use-in-production"
# Zero-config local runs use the SQLite file; set DATABASE_URL for Postgres (docker compose).
_LOCAL_DATABASE_URL = "sqlite:///./avnagent.db"
_LOCAL_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    secret_key: str = ""
    database_url: str = ""
    cors_origins: str = ""
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    default_tenant_id: str = ""
    seed_admin_email: str = ""
    seed_admin_password: str = ""
    sentry_dsn: str = ""
    # Signups per IP per hour (0 = default: 10, or 1000 when APP_ENV=local so tests and demos aren't throttled)
    signup_limit_per_hour: int = 0
    # Browser-facing URL of the dashboard, used in emailed links (verify, reset, invite)
    frontend_url: str = ""
    # Public base URL of this API (e.g. https://api.example.com), used in webhook URLs; defaults to the request URL.
    public_api_url: str = ""
    # Email delivery (Resend). Until both are set, emails are logged locally / reported as not configured.
    resend_api_key: str = ""
    email_from: str = ""

    @property
    def is_local(self) -> bool:
        return self.app_env.strip().lower() == "local"

    @property
    def frontend_base_url(self) -> str:
        return (self.frontend_url or ("http://localhost:5173" if self.is_local else "")).rstrip("/")

    @property
    def signup_limit(self) -> int:
        return self.signup_limit_per_hour or (1000 if self.is_local else 10)

    @property
    def email_configured(self) -> bool:
        return bool(self.resend_api_key and self.email_from)

    @cached_property
    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins or (_LOCAL_CORS_ORIGINS if self.is_local else "")
        origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
        if "*" in origins:
            raise RuntimeError("CORS_ORIGINS must list explicit origins; '*' is not allowed.")
        return origins

    def validate_for_environment(self) -> None:
        missing = []
        if not self.secret_key:
            if not self.is_local:
                missing.append("SECRET_KEY")
            else:
                self.secret_key = _LOCAL_DEV_SECRET_KEY
        if not self.database_url:
            if not self.is_local:
                missing.append("DATABASE_URL")
            else:
                self.database_url = _LOCAL_DATABASE_URL
        if missing:
            raise RuntimeError(
                f"Missing required settings for APP_ENV={self.app_env!r}: {', '.join(missing)}. "
                "See .env.example."
            )


settings = Settings()
settings.validate_for_environment()
