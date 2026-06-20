# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""Argon2id password hashing via pwdlib.

Default parameters (m=64 MiB, t=3, p=1) target ~150 ms per verify on a t3.large
core. Hashing is intentionally slow — never call from a hot path.

The hasher is module-level cached because constructing it allocates the Argon2
parameters object; reusing it across requests is safe and ~free.
"""

from __future__ import annotations

from functools import lru_cache

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher


@lru_cache(maxsize=1)
def _hasher() -> PasswordHash:
    # PasswordHash supports verify-and-rehash transparently when params change.
    return PasswordHash((Argon2Hasher(),))


def hash_password(plaintext: str) -> str:
    """Return an Argon2id hash string. Never log the plaintext arg."""
    if not plaintext:
        raise ValueError("password must not be empty")
    return _hasher().hash(plaintext)


def verify_password(plaintext: str, hash_str: str) -> bool:
    """Constant-time verify. Returns False on any decode/compare failure.

    Does not raise on malformed hashes; callers should treat False as
    "invalid credentials" without distinguishing why.
    """
    if not plaintext or not hash_str:
        return False
    try:
        return _hasher().verify(plaintext, hash_str)
    except Exception:  # noqa: BLE001 -- pwdlib raises a few internal errors
        return False


def needs_rehash(hash_str: str) -> bool:
    """True if the hash uses outdated parameters and should be re-hashed on next login."""
    try:
        return _hasher().verify_and_update(b"", hash_str)[1] is not None  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001
        return False


__all__ = ["hash_password", "needs_rehash", "verify_password"]
