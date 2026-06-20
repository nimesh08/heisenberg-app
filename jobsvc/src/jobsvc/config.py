# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""jobsvc settings — pydantic-settings, env-driven.

All env vars are prefixed `HEISENBERG_`. The single hard-required setting is
`HEISENBERG_DATABASE_URL`; the app refuses to boot without it.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HEISENBERG_",
        env_file=os.environ.get("HEISENBERG_ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Database. Async SQLAlchemy URL. No default — production must set this.
    # For dev: postgresql+psycopg://heisenberg:devonly@127.0.0.1:5432/heisenberg
    database_url: str = Field(
        ...,
        description="Async SQLAlchemy URL for Postgres 16+ (postgresql+psycopg://...).",
    )

    # SQL echo (debug only).
    sql_echo: bool = False

    # Connection pool.
    db_pool_size: int = 20
    db_max_overflow: int = 10

    # Logging.
    log_json: bool = True
    log_level: str = "INFO"

    # CORS — list of allowed origins. Empty = same-origin only.
    cors_origins: list[str] = Field(default_factory=list)

    # Public URL of the platform (used for OAuth redirect URIs and email links).
    public_url: str = Field(
        default="http://localhost:3000",
        description="Public origin (no trailing slash).",
    )

    # Path where the heisenberg-ide bundle is extracted.
    ide_bundle_dir: Path = Field(
        default=Path("/var/lib/heisenberg/ide"),
        description="Where `heisenberg update-ide` extracts the IDE tarball.",
    )

    # Auth.js shared secret. Server-to-server: heisenberg-web signs JWTs with this,
    # jobsvc verifies them. Read from /etc/heisenberg/secrets/auth_secret in prod.
    auth_secret: str = Field(
        default="dev-only-not-for-production",
        description="Shared HS256 secret with the Next.js Auth.js process.",
    )

    # Spinor-submit mode: cassette (default for tests/dev) | live | local.
    spinor_submit_mode: str = "cassette"

    @field_validator("database_url")
    @classmethod
    def _require_postgres(cls, v: str) -> str:
        if not v.startswith(("postgresql+psycopg://", "postgresql+asyncpg://", "postgresql://")):
            raise ValueError(
                "HEISENBERG_DATABASE_URL must be a Postgres URL "
                "(postgresql+psycopg:// or postgresql+asyncpg://). "
                "SQLite is not supported in v1."
            )
        return v

    @field_validator("public_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Lazy-cache the settings. Tests override by clearing the cache."""
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as e:
        # Reformat the pydantic error into a one-line operator-friendly message.
        missing = [err for err in e.errors() if err["type"] == "missing"]
        if any(err["loc"] == ("database_url",) for err in missing):
            raise SystemExit(
                "FATAL: HEISENBERG_DATABASE_URL is not set. "
                "jobsvc requires Postgres 16+. Example for local dev:\n"
                "  export HEISENBERG_DATABASE_URL="
                "'postgresql+psycopg://heisenberg:devonly@127.0.0.1:5432/heisenberg'"
            ) from e
        raise


__all__ = ["Settings", "get_settings"]
