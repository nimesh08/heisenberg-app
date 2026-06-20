# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""User, ApiKey-not-shipped-in-v1, Authenticator (passkey), Account (OAuth link), Session.

The Auth.js Postgres adapter writes to `accounts`, `sessions`, `users`,
`verification_tokens`, `authenticators` — the schema in this module follows
that contract exactly so the adapter works without monkey-patching.

Reference: https://authjs.dev/getting-started/adapters/pg
"""

# NOTE: do NOT `from __future__ import annotations` here. SQLModel's
# Relationship introspection requires the annotation types to be real
# (not strings) at class-definition time so it can resolve list[X] generics.

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Integer, Numeric, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, LargeBinary
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.sql import func
from sqlmodel import Field, Relationship, SQLModel

from .enums import UserRole

if TYPE_CHECKING:  # pragma: no cover
    from .audit import AuditLog
    from .billing import Payment
    from .credential import ProviderCredential
    from .job import Job
    from .workspace import Workspace


# ---------- Auth.js adapter tables ----------
#
# These four classes match the @auth/pg-adapter schema verbatim. We extend
# `User` with our own application columns. The Auth.js adapter only uses the
# columns it knows about and ignores the rest, so this is safe.
#
# Auth.js columns (don't rename):
#   accounts: id, userId, type, provider, providerAccountId, refresh_token,
#             access_token, expires_at, token_type, scope, id_token, session_state
#   sessions: id, sessionToken, userId, expires
#   users: id, name, email, emailVerified, image
#   verification_tokens: identifier, token, expires
#   authenticators (Passkey/WebAuthn): credentialID, userId, providerAccountId,
#             credentialPublicKey, counter, credentialDeviceType, credentialBackedUp, transports


class User(SQLModel, table=True):
    """A Heisenberg user account.

    Auth.js adapter columns are required and named in the camelCase form
    Auth.js expects (`emailVerified`, not `email_verified`). Our app columns
    use snake_case. RLS policy: every row is filtered by `id = app.user_id`
    via the dependency middleware.
    """

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    # Auth.js columns
    id: UUID = Field(
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    )
    name: str | None = Field(default=None, sa_column=Column(String(200), nullable=True))
    email: str = Field(sa_column=Column(String(320), nullable=False, unique=True))
    emailVerified: datetime | None = Field(  # noqa: N815 — Auth.js name
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    image: str | None = Field(default=None, sa_column=Column(String(2048), nullable=True))

    # Our app columns
    role: UserRole = Field(
        default=UserRole.user,
        sa_column=Column(SAEnum(UserRole, name="user_role"), nullable=False, server_default="user"),
    )
    password_hash: str | None = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )  # Argon2id hash for the Credentials provider; None for pure-OAuth users
    mfa_secret: bytes | None = Field(
        default=None, sa_column=Column(LargeBinary, nullable=True)
    )  # Base32-encoded TOTP secret, encrypted with byok_master_key. None until enabled.
    onboarding_completed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    terms_accepted_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    # Stripe + billing
    stripe_customer_id: str | None = Field(
        default=None, sa_column=Column(String(64), nullable=True, unique=True, index=True)
    )
    shots_paid: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, server_default="0")
    )
    shots_used: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, server_default="0")
    )

    # Cost-confirm threshold (item #5). Below this, Run skips the modal.
    run_confirm_threshold_usd: Decimal = Field(
        default=Decimal("0.10"),
        sa_column=Column(Numeric(12, 4), nullable=False, server_default="0.10"),
    )

    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )

    # Relationships (lazy-loaded to keep imports cheap)
    workspaces: list["Workspace"] = Relationship(back_populates="user")
    jobs: list["Job"] = Relationship(back_populates="user")
    credentials: list["ProviderCredential"] = Relationship(back_populates="user")
    payments: list["Payment"] = Relationship(back_populates="user")
    audit_logs: list["AuditLog"] = Relationship(back_populates="user")


class Account(SQLModel, table=True):
    """OAuth provider link. One row per (provider, provider_account_id) per user."""

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("provider", "providerAccountId", name="uq_accounts_provider_acct"),
    )

    id: UUID = Field(
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    )
    userId: UUID = Field(  # noqa: N815
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    type: str = Field(sa_column=Column(String(40), nullable=False))  # 'oauth' | 'oidc' | 'email'
    provider: str = Field(sa_column=Column(String(40), nullable=False, index=True))
    providerAccountId: str = Field(  # noqa: N815
        sa_column=Column(String(255), nullable=False)
    )
    refresh_token: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    access_token: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    expires_at: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    token_type: str | None = Field(default=None, sa_column=Column(String(40), nullable=True))
    scope: str | None = Field(default=None, sa_column=Column(String(2048), nullable=True))
    id_token: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    session_state: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))


class Session(SQLModel, table=True):
    """Auth.js DB-backed session. Lookup by sessionToken; expires drives revocation."""

    __tablename__ = "sessions"

    id: UUID = Field(
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    )
    sessionToken: str = Field(  # noqa: N815
        sa_column=Column(String(255), nullable=False, unique=True, index=True)
    )
    userId: UUID = Field(  # noqa: N815
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    expires: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class VerificationToken(SQLModel, table=True):
    """Auth.js Email-provider verification tokens (magic links + email verification)."""

    __tablename__ = "verification_tokens"
    __table_args__ = (
        UniqueConstraint("identifier", "token", name="uq_verification_token_idtok"),
    )

    identifier: str = Field(
        sa_column=Column(String(320), nullable=False, primary_key=True)
    )
    token: str = Field(sa_column=Column(String(255), nullable=False, primary_key=True))
    expires: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class Authenticator(SQLModel, table=True):
    """Passkey / WebAuthn authenticator. Auth.js's Passkey provider writes here."""

    __tablename__ = "authenticators"

    credentialID: str = Field(  # noqa: N815
        sa_column=Column(String(2048), primary_key=True)
    )
    userId: UUID = Field(  # noqa: N815
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    providerAccountId: str = Field(  # noqa: N815
        sa_column=Column(String(255), nullable=False)
    )
    credentialPublicKey: bytes = Field(  # noqa: N815
        sa_column=Column(LargeBinary, nullable=False)
    )
    counter: int = Field(sa_column=Column(Integer, nullable=False))
    credentialDeviceType: str = Field(  # noqa: N815
        sa_column=Column(String(40), nullable=False)
    )
    credentialBackedUp: bool = Field(  # noqa: N815
        sa_column=Column(JSONB, nullable=False, server_default="false")
    )
    transports: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))


__all__ = [
    "Account",
    "Authenticator",
    "Session",
    "User",
    "VerificationToken",
]
