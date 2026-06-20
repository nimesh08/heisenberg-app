# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""FastAPI application entry point.

This module is intentionally minimal at scaffold time. Routers, middleware,
and lifespan setup are added in later todos. For now it exposes a healthcheck
so CI can boot the app and confirm imports are clean.
"""

from __future__ import annotations

import os

from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(
        title="Heisenberg jobsvc",
        version="0.1.0",
        # Mount API under /api/v1; ops routes (/healthz, /readyz, /metrics)
        # land at the root for Kubernetes/Caddy probes.
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()


def run() -> None:
    """Console-script entry point for `jobsvc`."""
    import uvicorn

    uvicorn.run(
        "jobsvc.main:app",
        host=os.environ.get("HEISENBERG_HOST", "127.0.0.1"),
        port=int(os.environ.get("HEISENBERG_PORT", "8000")),
        log_level="info",
    )


__all__ = ["app", "create_app", "run"]
