# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""Integration tests for the workspaces router."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import ASGITransport
from jobsvc.db import reset_engine, session_scope, set_app_user_id
from jobsvc.main import create_app
from jobsvc.models import User
from jobsvc.security.jwt import mint_authjs_jwt
from sqlalchemy import text


def _alembic(args: list[str]) -> None:
    jobsvc_dir = Path(__file__).resolve().parents[2]
    res = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=jobsvc_dir,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        check=False,
    )
    if res.returncode != 0:
        raise AssertionError(
            f"alembic {' '.join(args)} failed:\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}"
        )


@pytest.fixture
def fresh_db() -> None:
    import psycopg

    url = os.environ["HEISENBERG_DATABASE_URL"]
    sync_url = url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    with psycopg.connect(sync_url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    _alembic(["upgrade", "head"])
    reset_engine()


async def _make_user(email: str = "alice@example.com") -> UUID:
    """Bypass-RLS insert a user; return their id. Used by tests to seed."""
    uid = uuid4()
    async with session_scope() as s:
        await s.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        s.add(User(id=uid, email=email))
    return uid


def _bearer(uid: UUID) -> dict[str, str]:
    return {"authorization": f"Bearer {mint_authjs_jwt(str(uid))}"}


@pytest.fixture
async def client_and_user(fresh_db: None):
    uid = await _make_user()
    app = create_app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c, uid


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unauthenticated_request_returns_401(fresh_db: None) -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        r = await c.get("/api/v1/workspaces")
    assert r.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_list_workspace(client_and_user) -> None:
    client, uid = client_and_user
    h = _bearer(uid)

    # Empty list initially.
    r = await client.get("/api/v1/workspaces", headers=h)
    assert r.status_code == 200
    assert r.json() == []

    # Create.
    r = await client.post(
        "/api/v1/workspaces", headers=h, json={"name": "default"}
    )
    assert r.status_code == 201, r.text
    ws_id = r.json()["id"]

    # List shows 1.
    r = await client.get("/api/v1/workspaces", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["id"] == ws_id
    assert body[0]["name"] == "default"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_put_get_delete_file_round_trip(client_and_user) -> None:
    client, uid = client_and_user
    h = _bearer(uid)

    # Create workspace.
    r = await client.post("/api/v1/workspaces", headers=h, json={"name": "default"})
    ws_id = r.json()["id"]

    # PUT a file.
    src = "target generic\nqubit q[2]\nh q[0]\ncx q[0], q[1]\n"
    r = await client.put(
        f"/api/v1/workspaces/{ws_id}/files/bell.spn",
        headers=h,
        json={"content": src},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "bell.spn"
    assert body["source_kind"] == "spinor"
    assert body["size_bytes"] == len(src.encode())

    # GET (returns content).
    r = await client.get(f"/api/v1/workspaces/{ws_id}/files/bell.spn", headers=h)
    assert r.status_code == 200
    assert r.json()["content"] == src

    # List omits content.
    r = await client.get(f"/api/v1/workspaces/{ws_id}/files", headers=h)
    assert r.status_code == 200
    files = r.json()
    assert len(files) == 1
    assert files[0]["content"] is None
    assert files[0]["path"] == "bell.spn"

    # PUT again to update.
    src2 = src + "measure q[0]\nmeasure q[1]\n"
    r = await client.put(
        f"/api/v1/workspaces/{ws_id}/files/bell.spn",
        headers=h,
        json={"content": src2},
    )
    assert r.status_code == 200
    assert r.json()["size_bytes"] == len(src2.encode())

    # DELETE.
    r = await client.delete(f"/api/v1/workspaces/{ws_id}/files/bell.spn", headers=h)
    assert r.status_code == 204

    # GET after delete -> 404.
    r = await client.get(f"/api/v1/workspaces/{ws_id}/files/bell.spn", headers=h)
    assert r.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_other_user_workspace_is_404(client_and_user) -> None:
    """RLS + ownership check: alice's workspace is not visible to bob."""
    client, alice = client_and_user

    # alice creates a workspace.
    r = await client.post(
        "/api/v1/workspaces", headers=_bearer(alice), json={"name": "alice-ws"}
    )
    ws_id = r.json()["id"]

    # bob exists separately.
    bob = await _make_user("bob@example.com")

    # bob hits alice's workspace -> 404.
    r = await client.get(f"/api/v1/workspaces/{ws_id}/files", headers=_bearer(bob))
    assert r.status_code == 404

    # bob can't even read a file in alice's ws.
    r = await client.get(
        f"/api/v1/workspaces/{ws_id}/files/something.spn", headers=_bearer(bob)
    )
    assert r.status_code == 404

    # bob's own listing is empty.
    r = await client.get("/api/v1/workspaces", headers=_bearer(bob))
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_path_rejections(client_and_user) -> None:
    client, uid = client_and_user
    h = _bearer(uid)
    r = await client.post("/api/v1/workspaces", headers=h, json={"name": "default"})
    ws_id = r.json()["id"]

    # Path traversal.
    for bad in ("../etc/passwd", "/etc/passwd", "a\\b", "a//b", "."):
        r = await client.put(
            f"/api/v1/workspaces/{ws_id}/files/{bad}",
            headers=h,
            json={"content": "x"},
        )
        assert r.status_code in (400, 404, 405), f"path {bad!r} not rejected: {r.status_code}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_content_too_large(client_and_user) -> None:
    client, uid = client_and_user
    h = _bearer(uid)
    r = await client.post("/api/v1/workspaces", headers=h, json={"name": "default"})
    ws_id = r.json()["id"]
    big = "x" * (1024 * 1024 + 1)
    r = await client.put(
        f"/api/v1/workspaces/{ws_id}/files/big.spn", headers=h, json={"content": big}
    )
    # Pydantic validates max_length first -> 422; backend backstop -> 413.
    assert r.status_code in (413, 422)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_audit_log_written_on_workspace_create(client_and_user) -> None:
    """Every mutation writes an audit_log row in the same transaction."""
    client, uid = client_and_user
    r = await client.post(
        "/api/v1/workspaces", headers=_bearer(uid), json={"name": "audited"}
    )
    assert r.status_code == 201
    ws_id = r.json()["id"]

    async with session_scope() as s:
        await set_app_user_id(s, uid)
        rows = (
            await s.execute(
                text(
                    "SELECT action, target_type, target_id "
                    "FROM audit_log WHERE user_id = :u ORDER BY at"
                ),
                {"u": str(uid)},
            )
        ).all()
    assert any(
        r[0] == "workspace.create" and r[1] == "workspace" and r[2] == ws_id
        for r in rows
    ), f"workspace.create not in audit log: {rows}"
