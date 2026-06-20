# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""Unit tests for jobsvc.security."""

from __future__ import annotations

import time

import httpx
import pytest
import respx
from jobsvc.security.hibp import HIBP_RANGE_URL, is_password_breached
from jobsvc.security.jwt import (
    JWT_AUDIENCE,
    JWT_ISSUER,
    JwtVerifyError,
    mint_authjs_jwt,
    verify_authjs_jwt,
)
from jobsvc.security.passwords import (
    hash_password,
    verify_password,
)


def test_hash_then_verify_round_trip() -> None:
    h = hash_password("correct horse battery staple")
    assert h.startswith("$argon2id$")
    assert verify_password("correct horse battery staple", h) is True


def test_verify_wrong_password_is_false() -> None:
    h = hash_password("right")
    assert verify_password("wrong", h) is False


def test_verify_empty_inputs_is_false() -> None:
    assert verify_password("", "$argon2id$irrelevant") is False
    assert verify_password("anything", "") is False


def test_hash_empty_password_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        hash_password("")


def test_verify_garbage_hash_returns_false() -> None:
    assert verify_password("hello", "not-a-valid-argon2-hash") is False


# --------------------- JWT ---------------------------------------------------


def test_mint_then_verify_roundtrip() -> None:
    token = mint_authjs_jwt("11111111-1111-1111-1111-111111111111")
    claims = verify_authjs_jwt(token)
    assert claims["iss"] == JWT_ISSUER
    assert claims["aud"] == JWT_AUDIENCE
    assert claims["sub"] == "11111111-1111-1111-1111-111111111111"


def test_verify_rejects_empty_token() -> None:
    with pytest.raises(JwtVerifyError, match="empty"):
        verify_authjs_jwt("")


def test_verify_rejects_garbage() -> None:
    with pytest.raises(JwtVerifyError):
        verify_authjs_jwt("not.a.token")


def test_verify_rejects_expired() -> None:
    # Mint with negative TTL.
    token = mint_authjs_jwt("11111111-1111-1111-1111-111111111111", ttl_seconds=-10)
    # Authlib lets us read a stale token only if validate() is skipped; ours always validates.
    with pytest.raises(JwtVerifyError, match="expired"):
        verify_authjs_jwt(token)
    # touch time to avoid "unused" linting paranoia
    _ = time.time()


def test_verify_rejects_non_uuid_sub() -> None:
    token = mint_authjs_jwt("not-a-uuid")
    with pytest.raises(JwtVerifyError, match="sub is not a valid uuid"):
        verify_authjs_jwt(token)


# --------------------- HIBP --------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_hibp_breached_password_returns_true() -> None:
    # SHA-1 of "password" = 5BAA61E4C9B93F3F0682250B6CF8331B7EE68FD8
    suffix = "1E4C9B93F3F0682250B6CF8331B7EE68FD8"
    respx.get(HIBP_RANGE_URL.format(prefix="5BAA6")).mock(
        return_value=httpx.Response(200, text=f"OTHER:1\n{suffix}:1234567\nMORE:5\n")
    )
    assert await is_password_breached("password") is True


@pytest.mark.asyncio
@respx.mock
async def test_hibp_clean_password_returns_false() -> None:
    respx.get(HIBP_RANGE_URL.format(prefix="5BAA6")).mock(
        return_value=httpx.Response(200, text="OTHER:1\nMORE:5\n")
    )
    assert await is_password_breached("password") is False


@pytest.mark.asyncio
@respx.mock
async def test_hibp_padding_count_zero_is_ignored() -> None:
    suffix = "1E4C9B93F3F0682250B6CF8331B7EE68FD8"
    respx.get(HIBP_RANGE_URL.format(prefix="5BAA6")).mock(
        return_value=httpx.Response(200, text=f"{suffix}:0\n")
    )
    # Count "0" is HIBP's padding; treat as clean.
    assert await is_password_breached("password") is False


@pytest.mark.asyncio
@respx.mock
async def test_hibp_network_error_fails_open() -> None:
    respx.get(HIBP_RANGE_URL.format(prefix="5BAA6")).mock(
        side_effect=httpx.ConnectError("boom")
    )
    assert await is_password_breached("password") is False


@pytest.mark.asyncio
@respx.mock
async def test_hibp_non_200_fails_open() -> None:
    respx.get(HIBP_RANGE_URL.format(prefix="5BAA6")).mock(
        return_value=httpx.Response(503)
    )
    assert await is_password_breached("password") is False


@pytest.mark.asyncio
async def test_hibp_empty_password_returns_false() -> None:
    assert await is_password_breached("") is False
