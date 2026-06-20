# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""Integration tests for /api/v1/auth/* against a real Postgres."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import respx
from httpx import ASGITransport
from jobsvc.config import get_settings
from jobsvc.db import reset_engine
from jobsvc.main import create_app
from jobsvc.security.hibp import HIBP_RANGE_URL


def _hmac_for(body: bytes) -> str:
    secret = get_settings().auth_secret.encode("utf-8")
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


def _alembic(args: list[str]) -> None:
    jobsvc_dir = Path(__file__).resolve().parents[2]
    res = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=jobsvc_dir,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        check=False,
    )
    if res.returncode != 0:
        raise AssertionError(
            f"alembic {' '.join(args)} failed:\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}"
        )


@pytest.fixture
def fresh_db() -> None:
    """Drop public schema + alembic upgrade head + reset cached engine."""
    import psycopg

    url = os.environ["HEISENBERG_DATABASE_URL"]
    sync_url = url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    with psycopg.connect(sync_url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    _alembic(["upgrade", "head"])
    reset_engine()


@pytest.fixture
async def client(fresh_db: None):
    app = create_app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_then_verify_credentials(client: httpx.AsyncClient) -> None:
    # Block HIBP network entirely for hermetic tests.
    with respx.mock(assert_all_mocked=False) as mock:
        mock.get(url__startswith="https://api.pwnedpasswords.com").mock(
            return_value=httpx.Response(200, text="")
        )
        # Register.
        r = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "alice@example.com",
                "password": "tr0ub4dor&3-correct-horse",
                "accept_terms": True,
            },
        )
        assert r.status_code == 201, r.text
        user_id = r.json()["user_id"]

        # Verify good credentials.
        body = json.dumps(
            {"email": "alice@example.com", "password": "tr0ub4dor&3-correct-horse"}
        ).encode()
        r2 = await client.post(
            "/api/v1/auth/verify-credentials",
            content=body,
            headers={"x-auth-hmac": _hmac_for(body), "content-type": "application/json"},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["user_id"] == user_id

        # Wrong password.
        bad_body = json.dumps(
            {"email": "alice@example.com", "password": "wrong"}
        ).encode()
        r3 = await client.post(
            "/api/v1/auth/verify-credentials",
            content=bad_body,
            headers={"x-auth-hmac": _hmac_for(bad_body), "content-type": "application/json"},
        )
        assert r3.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_verify_credentials_rejects_missing_hmac(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/verify-credentials",
        json={"email": "x@y.test", "password": "x"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid hmac"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_verify_credentials_unknown_user_constant_time(
    client: httpx.AsyncClient,
) -> None:
    body = json.dumps({"email": "ghost@example.com", "password": "anything"}).encode()
    r = await client.post(
        "/api/v1/auth/verify-credentials",
        content=body,
        headers={"x-auth-hmac": _hmac_for(body), "content-type": "application/json"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_credentials"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_upsert_from_oauth_creates_user_and_account(
    client: httpx.AsyncClient,
) -> None:
    payload = {
        "email": "bob@example.com",
        "name": "Bob",
        "image": "https://example.com/img.png",
        "email_verified": True,
        "provider": "google",
        "provider_account_id": "google-12345",
    }
    body = json.dumps(payload).encode()
    r = await client.post(
        "/api/v1/auth/upsert-from-oauth",
        content=body,
        headers={"x-auth-hmac": _hmac_for(body), "content-type": "application/json"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["created"] is True
    user_id = data["user_id"]

    # Idempotent second call.
    r2 = await client.post(
        "/api/v1/auth/upsert-from-oauth",
        content=body,
        headers={"x-auth-hmac": _hmac_for(body), "content-type": "application/json"},
    )
    assert r2.status_code == 200
    assert r2.json()["created"] is False
    assert r2.json()["user_id"] == user_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_rejects_breached_password(client: httpx.AsyncClient) -> None:
    # Compute the SHA-1 prefix the SUT will query for "Password123!".
    sha = hashlib.sha1(b"Password123!", usedforsecurity=False).hexdigest().upper()
    prefix, suffix = sha[:5], sha[5:]
    with respx.mock(assert_all_mocked=False, assert_all_called=False) as mock:
        mock.get(HIBP_RANGE_URL.format(prefix=prefix)).mock(
            return_value=httpx.Response(200, text=f"{suffix}:9999\n")
        )
        r = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "carol@example.com",
                "password": "Password123!",
                "accept_terms": True,
            },
        )
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "password_breached"
