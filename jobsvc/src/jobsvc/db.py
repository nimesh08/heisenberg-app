# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""Async SQLAlchemy 2.0 engine + session factory + RLS context helpers.

Public surface:

- `get_engine()` — process-wide cached AsyncEngine.
- `session_scope()` — `async with` session for scripts and the worker.
- `get_session()` — FastAPI dependency.
- `set_app_user_id(session, user_id)` — sets `app.user_id` for RLS on the
  current Postgres connection. Call this on every request before any query
  runs (the `set_app_user_id` middleware in `jobsvc/middleware/rls.py` does
  this for HTTP requests; the worker does it manually per-job).
- `verify_postgres_ready()` — startup preflight. Confirms Postgres 16+ and
  required extensions (`pgcrypto`, `pg_trgm`). Optional `pgaudit` is a
  warn-only soft check.

This module is the only place where engine/session lifecycle lives. Everything
else takes the engine/session as a parameter or via FastAPI's `Depends`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import get_settings

logger = logging.getLogger(__name__)


REQUIRED_EXTENSIONS: tuple[str, ...] = ("pgcrypto", "pg_trgm")
OPTIONAL_EXTENSIONS: tuple[str, ...] = ("pgaudit",)
MIN_POSTGRES_MAJOR: int = 16


def _normalise_url(url: str) -> str:
    """Coerce `postgresql://` to `postgresql+psycopg://` for SQLAlchemy async.

    psycopg 3 supports async natively. asyncpg is also fine if the user
    explicitly specified `postgresql+asyncpg://`.
    """
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


@lru_cache(maxsize=4)
def get_engine(url: str | None = None, *, echo: bool | None = None) -> AsyncEngine:
    """Return the process-cached AsyncEngine.

    Cache key is the URL; tests can pass an alternative URL or call
    `reset_engine()` between runs.
    """
    settings = get_settings()
    target = _normalise_url(url or settings.database_url)
    return create_async_engine(
        target,
        echo=echo if echo is not None else settings.sql_echo,
        future=True,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )


def get_sessionmaker(engine: AsyncEngine | None = None) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine or get_engine(),
        expire_on_commit=False,
        class_=AsyncSession,
    )


def reset_engine() -> None:
    """Drop the cached engine. Used by tests."""
    get_engine.cache_clear()


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Standalone session context. Used by the worker, seeders, and scripts."""
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. One session per request; commits on success, rolls back on raise."""
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Strict UUID validator: prevents anything that isn't a real UUID from being
# substituted into the SET LOCAL statement (defense in depth on top of the
# typed UUID parameter — we never trust a string).
_UUID_RE = re.compile(r"\A[0-9a-fA-F-]{36}\Z")


async def set_app_user_id(session: AsyncSession, user_id: UUID | str) -> None:
    """Set the per-request RLS context.

    Called by `jobsvc/middleware/rls.py` on every HTTP request, and manually
    by the worker for each job. Uses Postgres `set_config(name, value, true)`
    where `true` makes the setting transaction-local — safe with PgBouncer
    transaction-pooling because the value never leaks across requests.

    Args:
        session: AsyncSession bound to the request's connection.
        user_id: UUID of the authenticated user.

    Raises:
        ValueError: if `user_id` is not a valid UUID.
    """
    s = str(user_id)
    if not _UUID_RE.fullmatch(s):
        raise ValueError(f"set_app_user_id: not a UUID: {s!r}")
    # Strict bind-param; never string-format. RLS policies read this via
    # current_setting('app.user_id', true)::uuid.
    await session.execute(
        text("SELECT set_config('app.user_id', :uid, true)"),
        {"uid": s},
    )


async def clear_app_user_id(session: AsyncSession) -> None:
    """Clear the RLS context. The transaction-local `set_config(..., true)`
    auto-clears at COMMIT/ROLLBACK; this helper is for paranoia in the worker."""
    await session.execute(text("SELECT set_config('app.user_id', '', true)"))


async def set_bypass_rls(session: AsyncSession, on: bool = True) -> None:
    """Toggle the `app.bypass_rls` GUC on the current transaction.

    When 'on', RLS policies that include the `bypass` disjunct (currently
    `users` and the Auth.js adapter tables: `accounts`, `sessions`,
    `authenticators`) will grant access regardless of `app.user_id`. This is
    required for the auth router's email-lookup (no user_id known yet) and
    for the OAuth-account lookup before upsert. transaction-local — never
    leaks across requests.

    Use only inside the auth router's well-bounded code paths, and prefer
    setting `app.user_id` and clearing bypass before the *write* whenever
    possible (so writes still go through the normal RLS path).
    """
    await session.execute(
        text("SELECT set_config('app.bypass_rls', :v, true)"),
        {"v": "on" if on else "off"},
    )


class StartupCheckError(RuntimeError):
    """Raised when the Postgres preflight fails. Causes the app to refuse to boot."""


async def verify_postgres_ready(engine: AsyncEngine | None = None) -> dict[str, Any]:
    """Startup preflight against the Postgres instance.

    Verifies:
    1. Postgres major version >= MIN_POSTGRES_MAJOR (16).
    2. Required extensions (`pgcrypto`, `pg_trgm`) are CREATEd in the current DB.
    3. Optional extensions (`pgaudit`) — warn-only.

    Returns a small dict the caller can log or expose at /readyz. Raises
    `StartupCheckError` on any required-check failure.
    """
    eng = engine or get_engine()
    out: dict[str, Any] = {}
    async with eng.connect() as conn:
        ver_row = (await conn.execute(text("SELECT version()"))).scalar_one()
        out["server_version"] = ver_row

        major_row = (
            await conn.execute(text("SHOW server_version_num"))
        ).scalar_one()
        # server_version_num is e.g. "160014" for 16.14.
        try:
            major = int(int(major_row) // 10000)
        except (TypeError, ValueError) as e:
            raise StartupCheckError(
                f"could not parse server_version_num: {major_row!r}"
            ) from e
        out["server_version_num"] = int(major_row)
        out["server_major"] = major
        if major < MIN_POSTGRES_MAJOR:
            raise StartupCheckError(
                f"Postgres {major}.x is not supported. jobsvc requires "
                f"Postgres {MIN_POSTGRES_MAJOR}+ (RLS, pgcrypto, native UUID, JSONB)."
            )

        present = {
            row[0]
            for row in (
                await conn.execute(
                    text("SELECT extname FROM pg_extension")
                )
            ).all()
        }
        out["extensions_present"] = sorted(present)

        missing = [ext for ext in REQUIRED_EXTENSIONS if ext not in present]
        if missing:
            raise StartupCheckError(
                f"Required Postgres extension(s) not enabled: {', '.join(missing)}. "
                f"Run: psql -d <db> -c 'CREATE EXTENSION IF NOT EXISTS pgcrypto; "
                f"CREATE EXTENSION IF NOT EXISTS pg_trgm;'"
            )

        for ext in OPTIONAL_EXTENSIONS:
            if ext not in present:
                logger.warning(
                    "Optional Postgres extension %r not enabled; auditing reduced.",
                    ext,
                )

    return out


__all__ = [
    "MIN_POSTGRES_MAJOR",
    "REQUIRED_EXTENSIONS",
    "OPTIONAL_EXTENSIONS",
    "StartupCheckError",
    "clear_app_user_id",
    "get_engine",
    "get_session",
    "get_sessionmaker",
    "reset_engine",
    "session_scope",
    "set_app_user_id",
    "set_bypass_rls",
    "verify_postgres_ready",
]
