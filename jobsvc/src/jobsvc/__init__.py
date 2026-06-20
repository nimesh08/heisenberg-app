# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""jobsvc — Heisenberg backend.

FastAPI + SQLModel + Postgres 16. Public surface is `jobsvc.main:app`
(the FastAPI application) and `jobsvc.worker:run` (the worker loop).
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
