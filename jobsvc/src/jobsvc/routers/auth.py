# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""Auth router — server-to-server endpoints called by Next.js + Auth.js.

These are *not* user-facing. They sit behind the same Caddy origin as the
Next.js process; in production both processes run on the same host. The
contract:

- POST /api/v1/auth/verify-credentials
    Body: {email, password}
    Auth: HMAC of the body with AUTH_SECRET in `X-Auth-Hmac` header.
    Response 200: {user_id, email_verified}
    Response 401: invalid credentials.
    Called by Auth.js's Credentials provider during username+password login.

- POST /api/v1/auth/upsert-from-oauth
    Body: {email, name?, image?, email_verified, provider, provider_account_id}
    Auth: same HMAC scheme.
    Response 200: {user_id, created: bool}
    Called by Auth.js after a successful OAuth handshake to materialise the
    FastAPI users row.

- POST /api/v1/auth/register
    Body: {email, password, accept_terms: true}
    Public. Creates a users row with password_hash; returns 201 with
    `email_verification_required: true`. The Next.js Email provider then
    sends the magic link via Auth.js's own machinery.

The HMAC scheme prevents random callers from minting users — only a process
that holds AUTH_SECRET can call upsert-from-oauth or verify-credentials.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..config import get_settings
from ..db import get_session, set_app_user_id, set_bypass_rls
from ..models import Account, User
from ..security.hibp import is_password_breached
from ..security.passwords import hash_password, verify_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# ---------------------------- HMAC dep ---------------------------------------

HMAC_HEADER: str = "x-auth-hmac"


async def _read_body_bytes(request: Request) -> bytes:
    """Cache the raw body so handlers can re-parse it as JSON after HMAC check."""
    if not hasattr(request.state, "_raw_body"):
        request.state._raw_body = await request.body()
    return request.state._raw_body


def _expected_hmac(body: bytes) -> str:
    secret = get_settings().auth_secret.encode("utf-8")
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


async def require_authjs_hmac(request: Request) -> bytes:
    """Verify `X-Auth-Hmac` header equals HMAC-SHA256(AUTH_SECRET, raw_body).

    Returns the raw body bytes for the caller to parse. Constant-time compare.
    """
    provided = request.headers.get(HMAC_HEADER, "")
    body = await _read_body_bytes(request)
    expected = _expected_hmac(body)
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid hmac"
        )
    return body


HmacBody = Annotated[bytes, Depends(require_authjs_hmac)]


# ---------------------------- request models ---------------------------------


class VerifyCredentialsRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=1024)


class VerifyCredentialsResponse(BaseModel):
    user_id: UUID
    email_verified: bool


class UpsertFromOAuthRequest(BaseModel):
    email: EmailStr
    name: str | None = Field(default=None, max_length=200)
    image: str | None = Field(default=None, max_length=2048)
    email_verified: bool = True  # OAuth providers verify email upstream
    provider: str = Field(..., min_length=1, max_length=40)
    provider_account_id: str = Field(..., min_length=1, max_length=255)


class UpsertFromOAuthResponse(BaseModel):
    user_id: UUID
    created: bool


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=12, max_length=1024)
    accept_terms: bool

    @field_validator("accept_terms")
    @classmethod
    def _must_accept(cls, v: bool) -> bool:
        if not v:
            raise ValueError("must accept terms")
        return v


class RegisterResponse(BaseModel):
    user_id: UUID
    email_verification_required: bool = True


# ---------------------------- helpers ----------------------------------------


def _parse_json(body: bytes, model: type[BaseModel]) -> BaseModel:
    """Pydantic v2 parse with a uniform 422 response on bad JSON."""
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid json: {e}",
        ) from e
    return model.model_validate(data)


# ---------------------------- routes -----------------------------------------


@router.post(
    "/verify-credentials",
    response_model=VerifyCredentialsResponse,
    response_model_exclude_none=True,
)
async def verify_credentials(
    body: HmacBody,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> VerifyCredentialsResponse:
    """Argon2id verify of (email, password). 401 on any miss.

    The Auth.js Credentials provider calls this. Failures are logged with
    structured `event=failed_login` so fail2ban can detect brute force.
    """
    req = _parse_json(body, VerifyCredentialsRequest)
    assert isinstance(req, VerifyCredentialsRequest)
    # Look up by email outside RLS (no user_id known yet). Auth lookup is the
    # only reason we need to read users without an app.user_id. We toggle
    # `app.bypass_rls=on` for the duration of this transaction, scoped to
    # the read; any write below goes through normal RLS (we set app.user_id
    # before any write).
    await set_bypass_rls(session, True)
    result = await session.execute(
        select(User).where(User.email == req.email.lower())
    )
    user = result.scalar_one_or_none()
    # Always run the verify hash even if the user is missing — constant-time
    # behaviour so probing the email enumeration vector is hard.
    placeholder_hash = (
        "$argon2id$v=19$m=65536,t=3,p=4$"
        "AAAAAAAAAAAAAAAAAAAAAA$"
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    )
    target_hash = (user.password_hash if user is not None else None) or placeholder_hash

    ok = verify_password(req.password, target_hash)
    if user is None or user.password_hash is None or not ok:
        logger.info(
            "failed_login",
            extra={"event": "failed_login", "email_present": user is not None},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials"
        )

    return VerifyCredentialsResponse(
        user_id=user.id,
        email_verified=user.emailVerified is not None,
    )


@router.post(
    "/upsert-from-oauth",
    response_model=UpsertFromOAuthResponse,
)
async def upsert_from_oauth(
    body: HmacBody,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UpsertFromOAuthResponse:
    """Upsert a users row + accounts row from a successful OAuth flow.

    Idempotent: same (provider, provider_account_id) returns the existing
    user_id. Email-only conflicts (same email, different provider) link to
    the existing user — Auth.js handles the consent UX up-front.
    """
    req = _parse_json(body, UpsertFromOAuthRequest)
    assert isinstance(req, UpsertFromOAuthRequest)

    # Bypass RLS for the lookup phase: we don't yet know the user_id and we
    # need to find any existing (provider, providerAccountId) tuple. The
    # bypass is transaction-local; we revoke it before writing.
    await set_bypass_rls(session, True)

    # Try to find by (provider, provider_account_id) first.
    acct_q = await session.execute(
        select(Account).where(
            Account.provider == req.provider,
            Account.providerAccountId == req.provider_account_id,
        )
    )
    existing_acct = acct_q.scalar_one_or_none()

    created = False
    user: User | None = None
    if existing_acct is not None:
        user_q = await session.execute(
            select(User).where(User.id == existing_acct.userId)
        )
        user = user_q.scalar_one_or_none()

    if user is None:
        # Try by email.
        email_q = await session.execute(
            select(User).where(User.email == req.email.lower())
        )
        user = email_q.scalar_one_or_none()

    if user is None:
        # Fresh user. Set RLS context to the soon-to-exist user_id so the
        # WITH CHECK clause permits the INSERT (users_self_rls only allows
        # rows where id = app.user_id). Disable bypass first — writes
        # should always go through the normal RLS path.
        new_id = uuid4()
        await set_bypass_rls(session, False)
        await set_app_user_id(session, new_id)
        user = User(
            id=new_id,
            email=req.email.lower(),
            name=req.name,
            image=req.image,
            emailVerified=datetime.now(UTC) if req.email_verified else None,
        )
        session.add(user)
        await session.flush()
        created = True
    else:
        # Update soft fields if the OAuth side has fresher data.
        await set_bypass_rls(session, False)
        await set_app_user_id(session, user.id)
        if req.name and not user.name:
            user.name = req.name
        if req.image and not user.image:
            user.image = req.image
        if req.email_verified and user.emailVerified is None:
            user.emailVerified = datetime.now(UTC)

    # set_app_user_id was called above for both branches; sanity re-set for
    # the Account write below to honour accounts_user_rls.
    await set_app_user_id(session, user.id)

    if existing_acct is None:
        session.add(
            Account(
                id=uuid4(),
                userId=user.id,
                type="oauth",
                provider=req.provider,
                providerAccountId=req.provider_account_id,
            )
        )

    return UpsertFromOAuthResponse(user_id=user.id, created=created)


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: Annotated[RegisterRequest, Body()],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RegisterResponse:
    """Email + password registration.

    Public route — no HMAC. Caddy-level rate limit applies. HIBP check is
    fail-open on network errors.
    """
    if await is_password_breached(payload.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="password_breached",
        )

    email = payload.email.lower()
    # Bypass RLS only for the duplicate-email lookup phase; the INSERT below
    # goes through the normal RLS path with app.user_id set.
    await set_bypass_rls(session, True)
    existing = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        # Don't disclose whether the email exists; return the same 201 shape
        # without inserting anything. Auth.js will trigger the magic-link
        # email which the legitimate owner will receive (or not).
        return RegisterResponse(user_id=existing.id)

    user = User(
        id=uuid4(),
        email=email,
        password_hash=hash_password(payload.password),
        terms_accepted_at=datetime.now(UTC),
    )
    # Disable bypass and set RLS context to the new user's id so the WITH
    # CHECK on users_self_rls permits the INSERT.
    await set_bypass_rls(session, False)
    await set_app_user_id(session, user.id)
    session.add(user)
    await session.flush()
    return RegisterResponse(user_id=user.id)


__all__ = ["router"]
