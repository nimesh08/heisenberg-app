# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""HIBP Pwned Passwords k-anonymity check.

We never send the user's password (or its full hash) to the HIBP API. Instead:

1. Compute SHA-1 of the candidate password (HIBP's chosen hash; not for
   storage — just for k-anonymity lookup).
2. Send only the first 5 hex chars to api.pwnedpasswords.com/range/<prefix>.
3. HIBP returns ~600 candidate suffixes + breach counts.
4. We compare suffixes locally; if our suffix appears, the password is
   "breached" and we reject the registration / change.

The HIBP API is best-effort: a network failure must NOT block registration
(the password store is still Argon2id, and HIBP only adds defense-in-depth).
On `httpx.RequestError` or non-200 we return False and let the password
through with a structured warning log.

Reference: https://haveibeenpwned.com/API/v3#PwnedPasswords
"""

from __future__ import annotations

import hashlib
import logging

import httpx

logger = logging.getLogger(__name__)

HIBP_RANGE_URL: str = "https://api.pwnedpasswords.com/range/{prefix}"
HIBP_TIMEOUT_SECONDS: float = 2.0


async def is_password_breached(
    password: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> bool:
    """Return True iff the password appears in the HIBP corpus.

    Network failures return False (fail-open). Tests can inject a
    pre-configured `httpx.AsyncClient` (with respx mock).
    """
    if not password:
        return False

    sha1 = hashlib.sha1(password.encode("utf-8"), usedforsecurity=False).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]

    try:
        if client is None:
            async with httpx.AsyncClient(timeout=HIBP_TIMEOUT_SECONDS) as c:
                resp = await c.get(
                    HIBP_RANGE_URL.format(prefix=prefix),
                    headers={"Add-Padding": "true", "User-Agent": "heisenberg-jobsvc"},
                )
        else:
            resp = await client.get(
                HIBP_RANGE_URL.format(prefix=prefix),
                headers={"Add-Padding": "true", "User-Agent": "heisenberg-jobsvc"},
                timeout=HIBP_TIMEOUT_SECONDS,
            )
    except (httpx.RequestError, httpx.TimeoutException) as e:
        logger.warning("hibp_lookup_failed: %s; allowing password (fail-open)", e)
        return False

    if resp.status_code != 200:
        logger.warning(
            "hibp_lookup_non_200: status=%s; allowing password (fail-open)",
            resp.status_code,
        )
        return False

    for line in resp.text.splitlines():
        # Format: "<suffix>:<count>"
        parts = line.split(":", 1)
        if len(parts) != 2:
            continue
        if parts[0].strip().upper() == suffix:
            count = parts[1].strip()
            # Padding rows have count "0" — ignore them.
            if count != "0":
                logger.info(
                    "hibp_breached", extra={"breach_count": count, "prefix": prefix}
                )
                return True
    return False


__all__ = ["HIBP_RANGE_URL", "HIBP_TIMEOUT_SECONDS", "is_password_breached"]
