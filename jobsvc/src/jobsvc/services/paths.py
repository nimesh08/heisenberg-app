# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""Path validation for workspace files.

Mirrors the CHECK constraint in the migration:
- 1..256 characters.
- No NUL byte (Postgres rejects it for text columns; we reject earlier with a
  cleaner error).
- No leading slash (paths are workspace-relative).
- No `..` anywhere (block path traversal in any segment).
- No backslash (Windows-style separators are not allowed; we use POSIX).
- No control characters (0x00..0x1F + 0x7F).
"""

from __future__ import annotations

PATH_MAX_LEN: int = 256


class InvalidPath(ValueError):
    """Raised by `normalise_path` when the candidate fails any rule."""


def normalise_path(raw: str) -> str:
    """Validate and return a canonical workspace-relative path.

    Strips any trailing slash but otherwise preserves the input verbatim.
    Raises `InvalidPath` for any rule violation.
    """
    if not isinstance(raw, str):
        raise InvalidPath("path must be a string")
    if len(raw) == 0:
        raise InvalidPath("path is empty")
    if len(raw) > PATH_MAX_LEN:
        raise InvalidPath(f"path exceeds {PATH_MAX_LEN} characters")
    if raw.startswith("/"):
        raise InvalidPath("path must not start with '/'")
    if "\\" in raw:
        raise InvalidPath("backslash not allowed in path")
    if "\x00" in raw:
        raise InvalidPath("NUL byte not allowed in path")
    # Reject every C0 control char and DEL.
    for ch in raw:
        if ord(ch) < 0x20 or ord(ch) == 0x7F:
            raise InvalidPath("control characters not allowed in path")
    # Strip a single trailing slash before segment validation; otherwise the
    # split produces a final empty segment that would (incorrectly) fail the
    # `//` check below.
    canonical = raw.rstrip("/") or raw
    parts = canonical.split("/")
    for part in parts:
        if part in ("..", "."):
            raise InvalidPath("path must not contain '..' or '.' segments")
        if part == "":
            # Disallow `//` (empty segment) which would normalise oddly.
            raise InvalidPath("path must not contain '//'")
    return canonical


__all__ = ["InvalidPath", "PATH_MAX_LEN", "normalise_path"]
