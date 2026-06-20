# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""Workspaces router — 6 endpoints.

All routes require an authenticated user (Authorization: Bearer <jwt> via the
`AuthContextMiddleware`). RLS guarantees a user only sees their own rows;
the `get_owned_workspace` and `get_owned_file` deps add a Python layer on
top so a request for a foreign workspace/file 404s rather than silently
returning empty.

Surface:
    GET    /api/v1/workspaces                       - list user's workspaces
    POST   /api/v1/workspaces                       - create a workspace
    GET    /api/v1/workspaces/{ws_id}/files         - list files
    GET    /api/v1/workspaces/{ws_id}/files/{path}  - read a single file
    PUT    /api/v1/workspaces/{ws_id}/files/{path}  - upsert a file
    DELETE /api/v1/workspaces/{ws_id}/files/{path}  - delete a file
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel, Field
from sqlmodel import select

from ..deps import CurrentUser, SessionWithRls
from ..models import SourceKind, Workspace, WorkspaceFile
from ..services.audit import audit
from ..services.paths import PATH_MAX_LEN, InvalidPath, normalise_path

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])

# 1 MiB content cap (matches the CHECK constraint in the migration).
CONTENT_MAX_BYTES: int = 1 * 1024 * 1024


# ---------------------- ownership dependencies ------------------------------


async def get_owned_workspace(
    ws_id: UUID,
    user: CurrentUser,
    session: SessionWithRls,
) -> Workspace:
    """Lookup a workspace by id; 404 if not the user's. RLS already filters,
    but the explicit check produces a cleaner 404 instead of a no-row 200."""
    res = await session.execute(
        select(Workspace).where(Workspace.id == ws_id, Workspace.user_id == user.id)
    )
    ws = res.scalar_one_or_none()
    if ws is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace_not_found")
    return ws


OwnedWorkspace = Annotated[Workspace, Depends(get_owned_workspace)]


async def get_owned_file(
    path: str,
    ws: OwnedWorkspace,
    session: SessionWithRls,
) -> WorkspaceFile:
    """Composite-PK lookup: (workspace_id, path). Path is validated by the
    FastAPI Path() dependency below; this only converts a 0-row hit to 404."""
    res = await session.execute(
        select(WorkspaceFile).where(
            WorkspaceFile.workspace_id == ws.id,
            WorkspaceFile.path == path,
        )
    )
    f = res.scalar_one_or_none()
    if f is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file_not_found")
    return f


# ---------------------- request/response models ------------------------------


class WorkspaceOut(BaseModel):
    id: UUID
    name: str
    default_target: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm(cls, w: Workspace) -> WorkspaceOut:
        return cls(
            id=w.id,
            name=w.name,
            default_target=w.default_target,
            created_at=w.created_at,
            updated_at=w.updated_at,
        )


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    default_target: str | None = Field(default=None, max_length=64)


class FileOut(BaseModel):
    path: str
    source_kind: SourceKind
    size_bytes: int
    sha256: str
    updated_at: datetime
    content: str | None = None  # None on listings, populated on single-file read.


class FilePut(BaseModel):
    content: str = Field(..., max_length=CONTENT_MAX_BYTES)


# ---------------------- helpers ----------------------------------------------


def _path_param(path: str = Path(..., min_length=1, max_length=PATH_MAX_LEN)) -> str:
    try:
        return normalise_path(path)
    except InvalidPath as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid_path: {e}",
        ) from e


PathParam = Annotated[str, Depends(_path_param)]


def _request_meta(req: Request) -> tuple[str | None, str | None]:
    ip = req.client.host if req.client else None
    return ip, req.headers.get("user-agent")


# ---------------------- routes -----------------------------------------------


@router.get("", response_model=list[WorkspaceOut])
async def list_workspaces(
    user: CurrentUser,
    session: SessionWithRls,
) -> list[WorkspaceOut]:
    res = await session.execute(
        select(Workspace).where(Workspace.user_id == user.id).order_by(Workspace.created_at)
    )
    return [WorkspaceOut.from_orm(w) for w in res.scalars().all()]


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: WorkspaceCreate,
    user: CurrentUser,
    session: SessionWithRls,
    request: Request,
) -> WorkspaceOut:
    ws = Workspace(
        id=uuid4(),
        user_id=user.id,
        name=body.name.strip(),
        default_target=body.default_target,
    )
    session.add(ws)
    ip, ua = _request_meta(request)
    await audit(
        session,
        user_id=user.id,
        action="workspace.create",
        target_type="workspace",
        target_id=str(ws.id),
        detail={"name": ws.name},
        ip=ip,
        ua=ua,
    )
    await session.flush()
    return WorkspaceOut.from_orm(ws)


@router.get("/{ws_id}/files", response_model=list[FileOut])
async def list_files(
    ws: OwnedWorkspace,
    session: SessionWithRls,
) -> list[FileOut]:
    res = await session.execute(
        select(WorkspaceFile)
        .where(WorkspaceFile.workspace_id == ws.id)
        .order_by(WorkspaceFile.path)
    )
    return [
        FileOut(
            path=f.path,
            source_kind=f.source_kind,
            size_bytes=f.size_bytes,
            sha256=f.sha256,
            updated_at=f.updated_at,
            content=None,  # listings omit content; client fetches per-file.
        )
        for f in res.scalars().all()
    ]


@router.get("/{ws_id}/files/{path:path}", response_model=FileOut)
async def get_file(
    ws_id: UUID,
    path: PathParam,
    user: CurrentUser,
    session: SessionWithRls,
) -> FileOut:
    # Resolve ownership manually (composite PK lookup needs the validated path).
    ws = await get_owned_workspace(ws_id, user, session)
    f = await get_owned_file(path, ws, session)
    return FileOut(
        path=f.path,
        source_kind=f.source_kind,
        size_bytes=f.size_bytes,
        sha256=f.sha256,
        updated_at=f.updated_at,
        content=f.content,
    )


@router.put("/{ws_id}/files/{path:path}", response_model=FileOut)
async def put_file(
    ws_id: UUID,
    path: PathParam,
    body: FilePut,
    user: CurrentUser,
    session: SessionWithRls,
    request: Request,
) -> FileOut:
    ws = await get_owned_workspace(ws_id, user, session)
    if "\x00" in body.content:
        # Postgres TEXT columns reject NUL; reject earlier with a clean 400.
        raise HTTPException(status_code=400, detail="content_has_nul_byte")
    encoded = body.content.encode("utf-8")
    if len(encoded) > CONTENT_MAX_BYTES:
        raise HTTPException(status_code=413, detail="content_too_large")
    sha = hashlib.sha256(encoded).hexdigest()
    source_kind = SourceKind.from_path(path)

    # Look up existing row (composite PK).
    existing = (
        await session.execute(
            select(WorkspaceFile).where(
                WorkspaceFile.workspace_id == ws.id,
                WorkspaceFile.path == path,
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        f = WorkspaceFile(
            workspace_id=ws.id,
            path=path,
            content=body.content,
            source_kind=source_kind,
            size_bytes=len(encoded),
            sha256=sha,
        )
        session.add(f)
        action = "file.create"
    else:
        existing.content = body.content
        existing.source_kind = source_kind
        existing.size_bytes = len(encoded)
        existing.sha256 = sha
        existing.updated_at = datetime.now(timezone.utc)
        f = existing
        action = "file.update"

    ip, ua = _request_meta(request)
    await audit(
        session,
        user_id=user.id,
        action=action,
        target_type="file",
        target_id=f"{ws.id}:{path}",
        detail={"sha256": sha, "size_bytes": len(encoded), "source_kind": source_kind.value},
        ip=ip,
        ua=ua,
    )
    await session.flush()
    return FileOut(
        path=f.path,
        source_kind=f.source_kind,
        size_bytes=f.size_bytes,
        sha256=f.sha256,
        updated_at=f.updated_at,
        content=f.content,
    )


@router.delete("/{ws_id}/files/{path:path}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    ws_id: UUID,
    path: PathParam,
    user: CurrentUser,
    session: SessionWithRls,
    request: Request,
) -> None:
    ws = await get_owned_workspace(ws_id, user, session)
    f = await get_owned_file(path, ws, session)
    await session.delete(f)
    ip, ua = _request_meta(request)
    await audit(
        session,
        user_id=user.id,
        action="file.delete",
        target_type="file",
        target_id=f"{ws.id}:{path}",
        detail={"sha256": f.sha256},
        ip=ip,
        ua=ua,
    )


__all__ = ["router"]
