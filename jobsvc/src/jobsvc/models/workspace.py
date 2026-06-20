# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""Workspace + WorkspaceFile.

Per-user data isolation: every row has a user_id; RLS policies in 0001_init.py
filter by `user_id = current_setting('app.user_id')::uuid`.

WorkspaceFile uses a composite primary key (workspace_id, path) so a path
alone is never sufficient to identify a row — Layer 1 of the dependency stack
(`get_owned_file`) looks up by both, and Layer 2 (RLS) enforces user_id again.
"""


from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Integer,
    String,
    Text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.sql import func
from sqlmodel import Field, Relationship, SQLModel

from .enums import SourceKind

if TYPE_CHECKING:  # pragma: no cover
    from .user import User


# Path validation: max 256 chars, no '..', no leading slash, no backslash.
# NUL byte rejection is left to Postgres's UTF-8 layer (text columns can't
# hold them) plus API-layer validation. Embedding E'\x00' in a CHECK
# constraint trips psycopg3's UTF-8 encoder during DDL emit.
_PATH_CHECK = (
    "length(path) > 0 AND length(path) <= 256 "
    "AND path NOT LIKE '/%' "
    "AND path NOT LIKE '..%' "
    "AND path NOT LIKE '%..%'"
)


class Workspace(SQLModel, table=True):
    __tablename__ = "workspaces"

    id: UUID = Field(
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    )
    user_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    name: str = Field(sa_column=Column(String(120), nullable=False))
    default_target: str | None = Field(
        default=None, sa_column=Column(String(64), nullable=True)
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )

    user: "User" = Relationship(back_populates="workspaces")
    files: list["WorkspaceFile"] = Relationship(back_populates="workspace")


class WorkspaceFile(SQLModel, table=True):
    __tablename__ = "workspace_files"
    __table_args__ = (
        CheckConstraint(_PATH_CHECK, name="ck_wsfiles_path_safe"),
        CheckConstraint("octet_length(content) <= 1048576", name="ck_wsfiles_content_1mib"),
    )

    workspace_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("workspaces.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        )
    )
    path: str = Field(sa_column=Column(String(256), primary_key=True, nullable=False))
    content: str = Field(sa_column=Column(Text, nullable=False))
    source_kind: SourceKind = Field(
        sa_column=Column(SAEnum(SourceKind, name="source_kind"), nullable=False)
    )
    size_bytes: int = Field(sa_column=Column(Integer, nullable=False))
    sha256: str = Field(sa_column=Column(String(64), nullable=False))  # hex digest
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )

    workspace: Workspace = Relationship(back_populates="files")


__all__ = ["Workspace", "WorkspaceFile"]
