# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""Auth.js v5 JWT verification (HS256, JWE, or signed JWT depending on Auth.js mode).

Auth.js v5 issues *encrypted* session tokens (JWE A256CBC-HS512 over a key
derived from AUTH_SECRET via HKDF) when used in JWT-session mode. We deliberately
do *not* mirror that crypto stack on the FastAPI side — that's fragile and
couples the two services.

Instead, FastAPI accepts a small, narrowly-scoped *signed* JWT minted by the
Next.js process every time it makes a server-to-server call to `jobsvc`:

- alg: HS256
- iss: "heisenberg-web"
- aud: "heisenberg-jobsvc"
- sub: <user uuid>
- exp: now + 60s (short-lived, regenerated per request)

The shared secret is `AUTH_SECRET` (read from /etc/heisenberg/secrets/auth_secret
in production, or HEISENBERG_AUTH_SECRET in dev). The Next.js process signs;
jobsvc verifies. This keeps the `__Secure-authjs.session-token` cookie
opaque to FastAPI and bounded to the Next.js process.

For requests that arrive directly at jobsvc (no Next.js hop — e.g. the LSP
websocket from the IDE), Next.js exposes a small `/api/internal/exchange-cookie`
route (todo 7) that accepts the cookie and returns the same short-lived JWT;
the IDE-side LSP client then sends that JWT in `Authorization: Bearer ...`.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from authlib.jose import JoseError, jwt
from authlib.jose.errors import (
    BadSignatureError,
    DecodeError,
    ExpiredTokenError,
    InvalidClaimError,
    MissingClaimError,
)

from ..config import get_settings

JWT_ISSUER: str = "heisenberg-web"
JWT_AUDIENCE: str = "heisenberg-jobsvc"
JWT_ALG: str = "HS256"


class JwtVerifyError(ValueError):
    """Raised on any JWT validation failure. The message is operator-readable;
    do *not* surface it to clients (always 401)."""


_REQUIRED_CLAIMS: dict[str, dict[str, Any]] = {
    "iss": {"essential": True, "value": JWT_ISSUER},
    "aud": {"essential": True, "value": JWT_AUDIENCE},
    "sub": {"essential": True},
    "exp": {"essential": True},
    "iat": {"essential": True},
}


def verify_authjs_jwt(token: str) -> dict[str, Any]:
    """Verify a server-to-server JWT minted by the Next.js process.

    Args:
        token: the JWT compact form.

    Returns:
        The verified claim dict (sub is a string UUID; cast at the call site).

    Raises:
        JwtVerifyError: on any signature, claim, or expiry failure.
    """
    if not token:
        raise JwtVerifyError("empty token")

    settings = get_settings()
    secret = settings.auth_secret.encode("utf-8")
    try:
        claims = jwt.decode(
            token,
            secret,
            claims_options=_REQUIRED_CLAIMS,
        )
        claims.validate()  # exp, iat, iss, aud
    except ExpiredTokenError as e:
        raise JwtVerifyError("token expired") from e
    except BadSignatureError as e:
        raise JwtVerifyError("bad signature") from e
    except (DecodeError, MissingClaimError, InvalidClaimError) as e:
        raise JwtVerifyError(f"invalid token: {e}") from e
    except JoseError as e:  # catch-all for authlib's inheritance tree
        raise JwtVerifyError(f"token validation failed: {e}") from e

    sub = claims.get("sub")
    if not isinstance(sub, str):
        raise JwtVerifyError("sub claim must be a string")
    try:
        UUID(sub)
    except ValueError as e:
        raise JwtVerifyError("sub is not a valid uuid") from e

    return dict(claims)


def mint_authjs_jwt(user_id: str | UUID, *, ttl_seconds: int = 60) -> str:
    """Mint a short-lived HS256 JWT. Used by tests and by the upsert-from-oauth
    handshake when Next.js hits jobsvc on its own behalf."""
    settings = get_settings()
    now = int(time.time())
    header = {"alg": JWT_ALG, "typ": "JWT"}
    payload = {
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "sub": str(user_id),
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(header, payload, settings.auth_secret.encode("utf-8")).decode("ascii")


__all__ = [
    "JWT_ALG",
    "JWT_AUDIENCE",
    "JWT_ISSUER",
    "JwtVerifyError",
    "mint_authjs_jwt",
    "verify_authjs_jwt",
]
