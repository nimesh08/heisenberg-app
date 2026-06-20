# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""AuditLog — every auth event, workspace mutation, job transition, role change."""


from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, String
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.sql import func
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:  # pragma: no cover
    from .user import User


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"

    id: UUID = Field(
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    )
    user_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    action: str = Field(sa_column=Column(String(64), nullable=False, index=True))
    target_type: str | None = Field(default=None, sa_column=Column(String(32), nullable=True))
    target_id: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    detail: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    ip: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    ua: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )

    user: "User" = Relationship(
        back_populates="audit_logs", sa_relationship_kwargs={"foreign_keys": "AuditLog.user_id"}
    )


__all__ = ["AuditLog"]
