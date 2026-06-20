# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""Shared FastAPI dependencies.

The auth dependency tree:

    get_current_user_id     <-- reads request.state (populated by AuthContextMiddleware)
        |
        +--> get_session_with_rls   <-- AsyncSession with `app.user_id` set
        |
        +--> get_current_user       <-- ORM User row (guarantees row exists + lookup-by-RLS)

`get_session` (from db.py) is intentionally separate: routes that don't need
auth (the Stripe webhook, healthchecks) use the bare session.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from .db import get_sessionmaker, set_app_user_id
from .models import User, UserRole


def get_current_user_id(request: Request) -> UUID:
    """Return the authenticated user's UUID.

    `request.state.user_id` is set by `AuthContextMiddleware` after JWT verify.
    Empty state => 401.
    """
    uid = getattr(request.state, "user_id", None)
    if uid is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
            headers={"WWW-Authenticate": 'Bearer realm="heisenberg"'},
        )
    if not isinstance(uid, UUID):
        # Defensive: middleware always stores a UUID; never trust state shape.
        try:
            return UUID(str(uid))
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=500, detail="auth state corrupt") from e
    return uid


CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]


async def get_session_with_rls(
    user_id: CurrentUserId,
) -> AsyncIterator[AsyncSession]:
    """A session that has `app.user_id` set on its connection.

    This dep is the standard one for *authenticated* routes. The route gets
    an AsyncSession ready for ORM/SQL queries; every SELECT/INSERT/UPDATE
    is RLS-filtered by user_id.
    """
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            await set_app_user_id(session, user_id)
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


SessionWithRls = Annotated[AsyncSession, Depends(get_session_with_rls)]


async def get_current_user(
    user_id: CurrentUserId,
    session: SessionWithRls,
) -> User:
    """Load and return the authenticated user's ORM row.

    Because `app.user_id` is already set by `get_session_with_rls`, the
    SELECT below is RLS-filtered: a token with a foreign user_id (which
    shouldn't ever happen with a valid signature, but defense-in-depth)
    returns zero rows.
    """
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_verified_user(user: CurrentUser) -> User:
    """Block protected routes until the user has verified their email."""
    if user.emailVerified is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="email_verification_required",
        )
    return user


VerifiedUser = Annotated[User, Depends(require_verified_user)]


async def require_admin(user: CurrentUser) -> User:
    if user.role is not UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


__all__ = [
    "AdminUser",
    "CurrentUser",
    "CurrentUserId",
    "SessionWithRls",
    "VerifiedUser",
    "get_current_user",
    "get_current_user_id",
    "get_session_with_rls",
    "require_admin",
    "require_verified_user",
]
