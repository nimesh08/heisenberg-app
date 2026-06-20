# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""Audit-log writer.

Every user-initiated mutation (workspace create, file write/delete, job submit,
BYOK add/revoke, role change, etc.) writes an `audit_log` row in the SAME
transaction as the mutation itself. That keeps the audit trail
all-or-nothing: a rolled-back mutation never leaves an orphaned audit row.

Usage:

    from jobsvc.services.audit import audit
    await audit(
        session, user_id=user.id, action="workspace.create",
        target_type="workspace", target_id=str(ws.id), detail={...},
        ip=request.client.host, ua=request.headers.get("user-agent"),
    )

The `detail` dict is stored as JSONB and may include any non-PII metadata
that helps reconstruct what happened. Never include passwords, BYOK keys, or
the full source of a circuit (paths and sha256 are fine).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AuditLog


async def audit(
    session: AsyncSession,
    *,
    user_id: UUID | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict[str, Any] | None = None,
    ip: str | None = None,
    ua: str | None = None,
) -> None:
    """Insert an audit_log row in the current session/transaction."""
    session.add(
        AuditLog(
            id=uuid4(),
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
            ip=ip,
            ua=ua[:255] if ua else None,
        )
    )


__all__ = ["audit"]
