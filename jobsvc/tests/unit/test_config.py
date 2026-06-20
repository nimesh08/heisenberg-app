# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""Unit tests for jobsvc.config — env parsing and validation."""

from __future__ import annotations

import pytest


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """Booting without HEISENBERG_DATABASE_URL must SystemExit with a clear message."""
    monkeypatch.delenv("HEISENBERG_DATABASE_URL", raising=False)
    monkeypatch.setenv("HEISENBERG_ENV_FILE", "/dev/null")
    from jobsvc.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(SystemExit) as exc:
        get_settings()
    assert "HEISENBERG_DATABASE_URL" in str(exc.value)


def test_database_url_must_be_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HEISENBERG_DATABASE_URL", "sqlite:///./bad.db")
    monkeypatch.setenv("HEISENBERG_ENV_FILE", "/dev/null")
    from jobsvc.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(Exception) as exc:
        get_settings()
    assert "Postgres" in str(exc.value) or "postgresql" in str(exc.value)


def test_database_url_accepts_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "HEISENBERG_DATABASE_URL",
        "postgresql+psycopg://heisenberg:devonly@127.0.0.1:5432/heisenberg",
    )
    monkeypatch.setenv("HEISENBERG_ENV_FILE", "/dev/null")
    from jobsvc.config import get_settings

    get_settings.cache_clear()
    s = get_settings()
    assert s.database_url.startswith("postgresql+psycopg://")
    assert s.public_url == "http://localhost:3000"


def test_public_url_strips_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "HEISENBERG_DATABASE_URL",
        "postgresql+psycopg://heisenberg:devonly@127.0.0.1:5432/heisenberg",
    )
    monkeypatch.setenv("HEISENBERG_PUBLIC_URL", "https://example.com/")
    monkeypatch.setenv("HEISENBERG_ENV_FILE", "/dev/null")
    from jobsvc.config import get_settings

    get_settings.cache_clear()
    s = get_settings()
    assert s.public_url == "https://example.com"
