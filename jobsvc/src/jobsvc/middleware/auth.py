# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""ASGI middleware that authenticates the request and seeds the per-request
RLS context (`app.user_id`).

Why a middleware (not a Depends):

- Middleware runs *before* every route handler, including the ones we forget to
  decorate. RLS is the safety net — it must be set unconditionally for every
  authenticated request.
- The dependency tree (`get_current_user`, `get_owned_workspace`) takes the
  user.id from `request.state` (populated here), avoiding redundant JWT decode.

Auth sources, tried in order:
1. `Authorization: Bearer <jwt>` — preferred. Used by every route except the
   intra-cluster handshake.
2. None — request continues unauthenticated; the route's dependency is what
   raises 401, not the middleware. This is intentional: public routes
   (`/healthz`, `/readyz`, `/api/v1/billing/webhook`) work without auth.

This middleware never touches the database itself (RLS context is set by the
session dep `get_session_with_rls` on the first DB hit) — middleware can't
hold a session across the whole request without breaking FastAPI's per-request
session lifecycle.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from ..security.jwt import JwtVerifyError, verify_authjs_jwt

logger = logging.getLogger(__name__)


class AuthContextMiddleware(BaseHTTPMiddleware):
    """Decode `Authorization: Bearer ...` if present; stash `user_id` on `request.state`.

    Never raises — invalid tokens are simply not stashed. Routes that require
    auth depend on `get_current_user` which raises 401 when state is empty.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request.state.user_id = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ").strip()
            try:
                claims = verify_authjs_jwt(token)
                request.state.user_id = UUID(claims["sub"])
            except JwtVerifyError as e:
                # Don't raise — let the route's auth dep produce the 401. We
                # log at debug to avoid log floods on bot traffic.
                logger.debug("auth_jwt_invalid: %s", e)
            except (ValueError, KeyError) as e:
                logger.debug("auth_jwt_malformed: %s", e)

        return await call_next(request)


__all__ = ["AuthContextMiddleware"]
