# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""FastAPI application entry point.

Wires the lifespan that runs the Postgres preflight, the placeholder ops
routes (/healthz, /readyz, /metrics), and (in later todos) the auth, workspace,
jobs, transpile, LSP, and billing routers.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from .config import get_settings
from .db import StartupCheckError, verify_postgres_ready
from .middleware.auth import AuthContextMiddleware
from .routers import auth as auth_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Boot-time + shutdown hooks."""
    settings = get_settings()
    try:
        info = await verify_postgres_ready()
        app.state.db_ready = True
        app.state.db_info = info
        logger.info(
            "postgres_preflight_ok",
            extra={
                "server_major": info["server_major"],
                "extensions_present": info["extensions_present"],
            },
        )
    except StartupCheckError as e:
        # Re-raise so the app refuses to boot. CI / systemd will see the failure.
        logger.error("postgres_preflight_failed: %s", e)
        raise
    # Future: warm caches (chip registry from heisenberg-photon), open Stripe SDK, etc.
    _ = settings  # placeholder reference until real init lands
    yield
    # Shutdown: nothing to clean up at scaffold time.


def create_app() -> FastAPI:
    app = FastAPI(
        title="Heisenberg jobsvc",
        version="0.1.0",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(AuthContextMiddleware)
    app.include_router(auth_router.router)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Liveness — does not touch the database."""
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> dict[str, Any]:
        """Readiness — confirms Postgres + extensions on demand."""
        try:
            info = await verify_postgres_ready()
        except StartupCheckError as e:
            return {"status": "not_ready", "reason": str(e)}
        return {
            "status": "ready",
            "server_major": info["server_major"],
            "extensions_present": info["extensions_present"],
        }

    return app


app = create_app()


def run() -> None:
    """Console-script entry point for `jobsvc`."""
    import uvicorn  # noqa: PLC0415 -- lazy import keeps test-time imports cheap

    uvicorn.run(
        "jobsvc.main:app",
        host=os.environ.get("HEISENBERG_HOST", "127.0.0.1"),
        port=int(os.environ.get("HEISENBERG_PORT", "8000")),
        log_level="info",
    )


__all__ = ["app", "create_app", "run", "lifespan"]
