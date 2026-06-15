# WHAT: Central place that reads configuration (DB URL, secrets, R2 creds,
#       CORS origins) from environment variables / the .env file.
# WHY:  Every other module that needs a setting imports `settings` from here
#       instead of calling os.environ directly. That gives us one source of
#       truth, type-checking/validation via Pydantic, and an easy place to
#       derive convenience values (e.g. building the asyncpg/psycopg URLs
#       and the parsed CORS origin list) without repeating logic everywhere.

import re

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Store without driver suffix: postgresql://...
    # The two properties below append the right driver for each use site.
    database_url: str = ""

    @property
    def async_database_url(self) -> str:
        # Neon's connection string includes "?sslmode=require" — that's a
        # libpq/psycopg convention asyncpg's URL parser doesn't understand
        # (it raises "connect() got an unexpected keyword argument 'sslmode'").
        # asyncpg wants SSL configured via its own `ssl` connect arg instead
        # (see core/db.py, where we pass `connect_args={"ssl": "require"}`),
        # so we strip the query param here rather than have asyncpg choke on it.
        url = self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return re.sub(r"[?&]sslmode=[^&]+", "", url)

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)

    # ── Auth (JWT) ────────────────────────────────────────────────────────────
    # Secret key used to sign/verify access + refresh tokens (HS256).
    # Generate one with: python -c "import secrets; print(secrets.token_hex(32))"
    jwt_secret: str = ""

    # ── Cloudflare R2 (S3-compatible object storage) ─────────────────────────
    # These come straight from the Cloudflare dashboard for your R2 bucket.
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = ""
    r2_endpoint: str = ""
    r2_public_url: str = ""

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Raw value straight from the .env file, e.g.
    # "http://localhost:5173,https://myapp.com"
    # We keep this as a plain string field (not list[str]) so pydantic-settings
    # doesn't try to parse it as JSON, which is what it does by default for
    # list-typed fields. `validation_alias` points this field at the
    # CORS_ORIGINS env var name (otherwise it would look for CORS_ORIGINS_RAW).
    cors_origins_raw: str = Field(default="http://localhost:5173", validation_alias="CORS_ORIGINS")

    # ── Sentry ────────────────────────────────────────────────────────────────
    # Optional — Sentry error tracking is silently disabled if this is unset.
    sentry_dsn: str | None = None

    @property
    def cors_origins(self) -> list[str]:
        """Turn the comma-separated CORS_ORIGINS string into a clean list of
        origins, e.g. "a, b ,c" -> ["a", "b", "c"]. Empty entries are dropped
        so a trailing comma or blank value doesn't produce an empty-string
        origin (which CORSMiddleware would treat as a wildcard-ish match)."""
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]

    class Config:
        env_file = ".env"


settings = Settings()
