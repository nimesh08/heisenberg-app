# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""ProviderCredential — encrypted-at-rest BYOK credentials.

The plaintext key is encrypted with `pgcrypto` `pgp_sym_encrypt(key, $byok_master_key)`
at the route layer (jobsvc/routers/credentials.py in todo 6+); this model stores
the resulting bytea. Plaintext is never stored, never logged, returned only on POST
and immediately zeroed.
"""


from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, LargeBinary, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.sql import func
from sqlmodel import Field, Relationship, SQLModel

from .enums import CredentialProvider

if TYPE_CHECKING:  # pragma: no cover
    from .user import User


class ProviderCredential(SQLModel, table=True):
    __tablename__ = "provider_credentials"

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
    provider: CredentialProvider = Field(
        sa_column=Column(
            SAEnum(CredentialProvider, name="credential_provider"), nullable=False
        )
    )
    # Display-only prefix (first 8 chars of the user's key) for UI listings.
    # NEVER use this as a lookup key — IDs are uuid PKs.
    prefix: str = Field(sa_column=Column(String(8), nullable=False))
    encrypted_key: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    # Optional provider-specific extra fields stored as encrypted blob too
    # (AWS_DEFAULT_REGION, AZURE_QUANTUM_LOCATION, etc.). Encrypted with the
    # same byok_master_key.
    encrypted_extra: bytes | None = Field(
        default=None, sa_column=Column(LargeBinary, nullable=True)
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    last_used_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    revoked_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    user: "User" = Relationship(back_populates="credentials")


__all__ = ["ProviderCredential"]
