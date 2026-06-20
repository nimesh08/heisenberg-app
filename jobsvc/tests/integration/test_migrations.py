# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""Integration tests for the 0001_init Alembic migration.

These exercise:

- alembic upgrade head -> downgrade base -> upgrade head roundtrip.
- The required extensions are present after upgrade.
- RLS policies actually isolate user A from user B's rows in `workspaces`.
- The (user_id, state, queued_at) composite index exists on `jobs`.

The tests use the same HEISENBERG_DATABASE_URL the rest of the integration
suite uses (skipped when not set).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text


def _alembic(args: list[str]) -> None:
    """Invoke alembic as a subprocess from jobsvc/."""
    jobsvc_dir = Path(__file__).resolve().parents[2]
    cmd = [sys.executable, "-m", "alembic", *args]
    env = os.environ.copy()
    res = subprocess.run(
        cmd, cwd=jobsvc_dir, capture_output=True, text=True, env=env, check=False
    )
    if res.returncode != 0:
        raise AssertionError(
            f"alembic {' '.join(args)} failed:\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}"
        )


@pytest.fixture
def fresh_schema() -> None:
    """Drop public schema and run alembic upgrade head."""
    import psycopg

    url = os.environ["HEISENBERG_DATABASE_URL"]
    sync_url = url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    with psycopg.connect(sync_url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    _alembic(["upgrade", "head"])


@pytest.mark.integration
def test_upgrade_head_creates_all_tables(fresh_schema: None) -> None:
    import psycopg

    url = os.environ["HEISENBERG_DATABASE_URL"]
    sync_url = url.replace("postgresql+psycopg://", "postgresql://")
    expected = {
        "users",
        "verification_tokens",
        "accounts",
        "sessions",
        "authenticators",
        "workspaces",
        "workspace_files",
        "provider_credentials",
        "jobs",
        "results",
        "payments",
        "audit_log",
    }
    with psycopg.connect(sync_url) as conn:
        rows = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        ).fetchall()
    have = {r[0] for r in rows}
    missing = expected - have
    assert not missing, f"missing tables: {missing}"


@pytest.mark.integration
def test_required_extensions_present(fresh_schema: None) -> None:
    import psycopg

    url = os.environ["HEISENBERG_DATABASE_URL"]
    sync_url = url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(sync_url) as conn:
        rows = conn.execute("SELECT extname FROM pg_extension").fetchall()
    have = {r[0] for r in rows}
    assert "pgcrypto" in have
    assert "pg_trgm" in have
    # pgaudit is intentionally optional — see _create_extensions().


@pytest.mark.integration
def test_jobs_composite_index_exists(fresh_schema: None) -> None:
    import psycopg

    url = os.environ["HEISENBERG_DATABASE_URL"]
    sync_url = url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(sync_url) as conn:
        row = conn.execute(
            "SELECT indexdef FROM pg_indexes "
            "WHERE schemaname='public' AND indexname='ix_jobs_user_state_queued'"
        ).fetchone()
    assert row is not None, "composite index ix_jobs_user_state_queued not created"
    indexdef = row[0]
    assert "user_id" in indexdef and "state" in indexdef and "queued_at" in indexdef


@pytest.mark.integration
def test_downgrade_then_upgrade_roundtrip(fresh_schema: None) -> None:
    """A clean down -> up roundtrip should leave us right back at head."""
    _alembic(["downgrade", "base"])
    _alembic(["upgrade", "head"])

    import psycopg

    url = os.environ["HEISENBERG_DATABASE_URL"]
    sync_url = url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(sync_url) as conn:
        rev = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    assert rev == ("0001",)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rls_isolates_two_users(fresh_schema: None) -> None:
    """Two users can both insert workspaces; each only sees their own row."""
    from jobsvc.db import reset_engine, session_scope, set_app_user_id
    from jobsvc.models import User, Workspace

    reset_engine()
    a = uuid4()
    b = uuid4()

    # Setup: insert two users and one workspace per user. We bypass RLS on
    # users by setting app.user_id to the user about to be inserted.
    async with session_scope() as s:
        await set_app_user_id(s, a)
        s.add(User(id=a, email=f"a-{a}@test.local"))
        s.add(Workspace(id=uuid4(), user_id=a, name="A's space"))
    async with session_scope() as s:
        await set_app_user_id(s, b)
        s.add(User(id=b, email=f"b-{b}@test.local"))
        s.add(Workspace(id=uuid4(), user_id=b, name="B's space"))

    # Read as A: should see exactly one workspace (A's).
    async with session_scope() as s:
        await set_app_user_id(s, a)
        rows = (await s.execute(text("SELECT name FROM workspaces"))).all()
    assert [r[0] for r in rows] == ["A's space"]

    # Read as B: should see exactly one workspace (B's).
    async with session_scope() as s:
        await set_app_user_id(s, b)
        rows = (await s.execute(text("SELECT name FROM workspaces"))).all()
    assert [r[0] for r in rows] == ["B's space"]

    # No app.user_id set: zero rows visible (RLS denies all).
    async with session_scope() as s:
        rows = (await s.execute(text("SELECT name FROM workspaces"))).all()
    assert rows == []
