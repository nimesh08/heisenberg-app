# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""Job + Result.

Job has a state-machine method `transition()` that validates the new state
against `LEGAL_TRANSITIONS` and stamps the appropriate timestamp columns.
The caller is expected to write a corresponding AuditLog row in the same
transaction (see `jobsvc/services/audit.py` in todo 6+).
"""


from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.sql import func
from sqlmodel import Field, Relationship, SQLModel

from .enums import (
    LEGAL_TRANSITIONS,
    TERMINAL_STATES,
    IllegalTransitionError,
    JobState,
    SourceKind,
)

if TYPE_CHECKING:  # pragma: no cover
    from .credential import ProviderCredential
    from .user import User


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Job(SQLModel, table=True):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("provider_job_id", name="uq_jobs_provider_job_id"),
        Index("ix_jobs_user_state_queued", "user_id", "state", "queued_at"),
    )

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

    name: str = Field(default="", sa_column=Column(String(200), nullable=False, server_default=""))
    target: str = Field(sa_column=Column(String(64), nullable=False))
    shots: int = Field(sa_column=Column(Integer, nullable=False))
    source: str = Field(sa_column=Column(Text, nullable=False))
    source_kind: SourceKind = Field(
        sa_column=Column(SAEnum(SourceKind, name="source_kind"), nullable=False)
    )

    # State machine
    state: JobState = Field(
        default=JobState.Submitted,
        sa_column=Column(
            SAEnum(JobState, name="job_state"),
            nullable=False,
            server_default="Submitted",
            index=True,
        ),
    )
    rejection_reason: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    error_kind: str | None = Field(default=None, sa_column=Column(String(32), nullable=True))

    # Resource estimate from the compiler (JSONB so we can grow the schema later).
    estimate: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    dollar_cost: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(12, 6), nullable=True)
    )

    # Provider routing
    provider: str | None = Field(default=None, sa_column=Column(String(32), nullable=True))
    provider_job_id: str | None = Field(
        default=None, sa_column=Column(String(128), nullable=True)
    )

    # BYOK credential reference (null = platform shots).
    byok_credential_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("provider_credentials.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # Worker lease
    claimed_by: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    claim_expires_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=_utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    queued_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    started_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    finished_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    user: "User" = Relationship(back_populates="jobs")
    result: "Result" = Relationship(
        back_populates="job", sa_relationship_kwargs={"uselist": False}
    )
    byok_credential: "ProviderCredential" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "Job.byok_credential_id"}
    )

    # ------- state machine -------

    def transition(
        self,
        new_state: JobState,
        *,
        reason: str | None = None,
        error_kind: str | None = None,
    ) -> None:
        """Apply a state transition; raise IllegalTransitionError on illegal."""
        cur = self.state
        if (cur, new_state) not in LEGAL_TRANSITIONS:
            raise IllegalTransitionError(
                f"illegal transition {cur.value} -> {new_state.value}"
            )
        now = _utc_now()
        self.state = new_state
        if new_state is JobState.Queued and self.queued_at is None:
            self.queued_at = now
        if new_state is JobState.Running and self.started_at is None:
            self.started_at = now
        if new_state in TERMINAL_STATES:
            self.finished_at = now
        if new_state is JobState.Rejected and reason:
            self.rejection_reason = reason
        if new_state is JobState.Failed:
            if reason:
                self.rejection_reason = reason
            if error_kind:
                self.error_kind = error_kind

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES


class Result(SQLModel, table=True):
    __tablename__ = "results"

    job_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("jobs.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    counts: dict[str, int] = Field(sa_column=Column(JSONB, nullable=False))
    shots: int = Field(sa_column=Column(Integer, nullable=False))
    raw_provider_payload: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    created_at: datetime = Field(
        default_factory=_utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )

    job: Job = Relationship(back_populates="result")


__all__ = ["Job", "Result"]
