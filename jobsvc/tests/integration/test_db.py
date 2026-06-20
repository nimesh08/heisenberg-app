# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""Integration tests for jobsvc.db — preflight and RLS context against a real Postgres."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_verify_postgres_ready() -> None:
    from jobsvc.db import reset_engine, verify_postgres_ready

    reset_engine()
    info = await verify_postgres_ready()
    assert info["server_major"] >= 16
    assert "pgcrypto" in info["extensions_present"]
    assert "pg_trgm" in info["extensions_present"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_set_app_user_id_round_trips() -> None:
    """SET LOCAL app.user_id sets the value visible to the same transaction."""
    from jobsvc.db import reset_engine, session_scope, set_app_user_id

    reset_engine()
    target = uuid4()
    async with session_scope() as session:
        await set_app_user_id(session, target)
        # current_setting returns text; cast to uuid in SQL.
        observed = (
            await session.execute(
                text("SELECT current_setting('app.user_id', true)::uuid")
            )
        ).scalar_one()
        assert observed == target


@pytest.mark.integration
@pytest.mark.asyncio
async def test_set_app_user_id_rejects_non_uuid() -> None:
    from jobsvc.db import reset_engine, session_scope, set_app_user_id

    reset_engine()
    async with session_scope() as session:
        with pytest.raises(ValueError, match="not a UUID"):
            await set_app_user_id(session, "definitely-not-a-uuid")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_app_user_id_is_transaction_local() -> None:
    """SET LOCAL must reset between transactions — critical for PgBouncer transaction-pool safety."""
    from jobsvc.db import get_engine, reset_engine, session_scope, set_app_user_id

    reset_engine()
    a = uuid4()
    # Tx 1: set + verify.
    async with session_scope() as s1:
        await set_app_user_id(s1, a)
        v1 = (
            await s1.execute(text("SELECT current_setting('app.user_id', true)"))
        ).scalar_one()
        assert v1 == str(a)
    # Tx 2 on a fresh connection (pool may reuse): app.user_id must be empty.
    eng = get_engine()
    async with eng.connect() as conn:
        v2 = (
            await conn.execute(text("SELECT current_setting('app.user_id', true)"))
        ).scalar_one()
        # Either empty string (the default for an unset transaction-local GUC) or NULL.
        assert v2 in ("", None)
