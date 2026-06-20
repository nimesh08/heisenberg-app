# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""Shared pytest fixtures.

Integration tests use a real Postgres pointed at by HEISENBERG_DATABASE_URL.
On CI this is the postgres:16 service container; locally it's whatever the
operator set up. If the URL isn't set, integration tests are skipped.
"""

from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-skip @pytest.mark.integration tests when no database is configured."""
    if not os.environ.get("HEISENBERG_DATABASE_URL"):
        skip = pytest.mark.skip(reason="HEISENBERG_DATABASE_URL not set; integration test skipped")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)
