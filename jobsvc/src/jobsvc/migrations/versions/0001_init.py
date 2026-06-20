# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""init

Revision ID: 0001
Revises:
Create Date: 2026-06-20

Initial schema for heisenberg-jobsvc.

This migration is hand-curated on top of an autogenerate baseline:

- Extensions created first: pgcrypto (BYOK encrypt-at-rest), pgaudit
  (statement-level audit trail), pg_trgm (fuzzy search on email/audit).
  pgaudit is best-effort: if shared_preload_libraries doesn't include it,
  CREATE EXTENSION fails — we catch that and log so dev can boot without
  cluster restart privileges.
- All tenant-scoped tables get an RLS policy of the shape
    USING (user_id = current_setting('app.user_id', true)::uuid)
  with FORCE ROW LEVEL SECURITY so even table-owner queries are filtered
  (defense in depth).
- jobs gets the (user_id, state, queued_at) composite index for the worker's
  claim loop and the user's "my queued jobs" pane.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Tables that need per-user RLS. Each one has a `user_id` UUID column.
# `audit_log.user_id` is nullable (system events have no user) so the policy
# allows NULL too.
_RLS_USER_TABLES: tuple[str, ...] = (
    "workspaces",
    "jobs",
    "provider_credentials",
    "payments",
    "accounts",
    "sessions",
    "authenticators",
)
# Tables whose user-id column isn't called `user_id` (Auth.js camelCase).
_RLS_USERID_CAMELCASE: tuple[str, ...] = ("accounts", "sessions", "authenticators")
# audit_log: user_id is nullable; policy permits NULL
_RLS_AUDIT_TABLE: str = "audit_log"
# users itself: each user can only see their own row
_RLS_USERS_TABLE: str = "users"
# workspace_files + results: filter via the parent's user_id
_RLS_PARENT_FILTERED: tuple[tuple[str, str, str], ...] = (
    # (table, parent_table, fk_column)
    ("workspace_files", "workspaces", "workspace_id"),
    ("results", "jobs", "job_id"),
)


def _create_extensions() -> None:
    """Create required + optional Postgres extensions.

    pgcrypto and pg_trgm are required (the app's startup preflight refuses to
    boot without them). pgaudit needs `shared_preload_libraries=pgaudit` in
    postgresql.conf — if that isn't set, CREATE EXTENSION fails *and aborts
    the surrounding transaction*. So we check pg_available_extensions first
    and only attempt the create if the OS-level package is installed; we
    further skip if pgaudit isn't in shared_preload_libraries.
    """
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # pgaudit: best-effort. Only attempt when both the package is available
    # AND it's loaded in shared_preload_libraries (otherwise CREATE EXTENSION
    # raises "pgaudit must be loaded via shared_preload_libraries" and aborts
    # the migration transaction). Production runbook covers cluster setup.
    bind = op.get_bind()
    available = bind.exec_driver_sql(
        "SELECT 1 FROM pg_available_extensions WHERE name = 'pgaudit'"
    ).scalar()
    if not available:
        return
    spl = bind.exec_driver_sql("SHOW shared_preload_libraries").scalar() or ""
    if "pgaudit" not in spl:
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS pgaudit")


def upgrade() -> None:
    _create_extensions()
    _create_tables()
    _create_indexes()
    _enable_rls()


def _create_tables() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("emailVerified", sa.DateTime(timezone=True), nullable=True),
        sa.Column("image", sa.String(length=2048), nullable=True),
        sa.Column(
            "role",
            sa.Enum("user", "admin", name="user_role"),
            server_default="user",
            nullable=False,
        ),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("mfa_secret", sa.LargeBinary(), nullable=True),
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stripe_customer_id", sa.String(length=64), nullable=True),
        sa.Column("shots_paid", sa.Integer(), server_default="0", nullable=False),
        sa.Column("shots_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "run_confirm_threshold_usd",
            sa.Numeric(precision=12, scale=4),
            server_default="0.10",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "verification_tokens",
        sa.Column("identifier", sa.String(length=320), primary_key=True, nullable=False),
        sa.Column("token", sa.String(length=255), primary_key=True, nullable=False),
        sa.Column("expires", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("identifier", "token", name="uq_verification_token_idtok"),
    )

    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("userId", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("providerAccountId", sa.String(length=255), nullable=False),
        sa.Column("refresh_token", sa.String(), nullable=True),
        sa.Column("access_token", sa.String(), nullable=True),
        sa.Column("expires_at", sa.Integer(), nullable=True),
        sa.Column("token_type", sa.String(length=40), nullable=True),
        sa.Column("scope", sa.String(length=2048), nullable=True),
        sa.Column("id_token", sa.String(), nullable=True),
        sa.Column("session_state", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["userId"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("provider", "providerAccountId", name="uq_accounts_provider_acct"),
    )

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("sessionToken", sa.String(length=255), nullable=False),
        sa.Column("userId", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["userId"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "authenticators",
        sa.Column("credentialID", sa.String(length=2048), primary_key=True, nullable=False),
        sa.Column("userId", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("providerAccountId", sa.String(length=255), nullable=False),
        sa.Column("credentialPublicKey", sa.LargeBinary(), nullable=False),
        sa.Column("counter", sa.Integer(), nullable=False),
        sa.Column("credentialDeviceType", sa.String(length=40), nullable=False),
        sa.Column(
            "credentialBackedUp",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="false",
            nullable=False,
        ),
        sa.Column("transports", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["userId"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("default_target", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "workspace_files",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("path", sa.String(length=256), primary_key=True, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "source_kind",
            sa.Enum("spinor", "phonon", "photon", name="source_kind"),
            nullable=False,
        ),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(path) > 0 AND length(path) <= 256 "
            "AND path NOT LIKE '/%' "
            "AND path NOT LIKE '..%' "
            "AND path NOT LIKE '%..%'",
            name="ck_wsfiles_path_safe",
        ),
        sa.CheckConstraint("octet_length(content) <= 1048576", name="ck_wsfiles_content_1mib"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "provider_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "provider",
            sa.Enum("ibm", "aws", "azure", name="credential_provider"),
            nullable=False,
        ),
        sa.Column("prefix", sa.String(length=8), nullable=False),
        sa.Column("encrypted_key", sa.LargeBinary(), nullable=False),
        sa.Column("encrypted_extra", sa.LargeBinary(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), server_default="", nullable=False),
        sa.Column("target", sa.String(length=64), nullable=False),
        sa.Column("shots", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "source_kind",
            sa.Enum("spinor", "phonon", "photon", name="source_kind", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "state",
            sa.Enum(
                "Submitted",
                "Queued",
                "Running",
                "Completed",
                "Rejected",
                "Failed",
                name="job_state",
            ),
            server_default="Submitted",
            nullable=False,
        ),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("error_kind", sa.String(length=32), nullable=True),
        sa.Column("estimate", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("dollar_cost", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("provider_job_id", sa.String(length=128), nullable=True),
        sa.Column("byok_credential_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claimed_by", sa.String(length=64), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["byok_credential_id"], ["provider_credentials.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("provider_job_id", name="uq_jobs_provider_job_id"),
    )

    op.create_table(
        "results",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("counts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("shots", sa.Integer(), nullable=False),
        sa.Column(
            "raw_provider_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stripe_session_id", sa.String(length=255), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("shots_purchased", sa.Integer(), nullable=False),
        sa.Column("dollar_amount", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=8), server_default="usd", nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=True),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("ua", sa.String(length=255), nullable=True),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )


def _create_indexes() -> None:
    op.create_index(
        "ix_users_stripe_customer_id",
        "users",
        ["stripe_customer_id"],
        unique=True,
    )
    op.create_index("ix_accounts_provider", "accounts", ["provider"])
    op.create_index("ix_sessions_sessionToken", "sessions", ["sessionToken"], unique=True)
    op.create_index("ix_sessions_userId", "sessions", ["userId"])
    op.create_index("ix_authenticators_userId", "authenticators", ["userId"])
    op.create_index("ix_workspaces_user_id", "workspaces", ["user_id"])
    op.create_index("ix_provider_credentials_user_id", "provider_credentials", ["user_id"])
    op.create_index("ix_jobs_user_id", "jobs", ["user_id"])
    op.create_index("ix_jobs_state", "jobs", ["state"])
    # Composite index for the worker claim loop and the user's queued-jobs pane.
    op.create_index(
        "ix_jobs_user_state_queued",
        "jobs",
        ["user_id", "state", "queued_at"],
    )
    op.create_index(
        "ix_payments_stripe_session_id", "payments", ["stripe_session_id"], unique=True
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])


def _enable_rls() -> None:
    """Enable + FORCE Row-Level Security on every tenant-scoped table.

    Pattern: USING (col = NULLIF(current_setting('app.user_id', true), '')::uuid)
    where `col` is `user_id` for our app-owned tables and `userId` for the
    Auth.js adapter tables. `current_setting(name, true)` returns the empty
    string (not NULL) for an unset GUC; the NULLIF wraps the cast so that an
    unset value compares as NULL and matches no row (zero leakage when a
    request forgets to call set_app_user_id).

    FORCE ROW LEVEL SECURITY ensures even the table owner is filtered — our
    app role IS the owner in single-tenant deploys, and we don't want that
    to bypass RLS. (Postgres SUPERUSER bypasses RLS unconditionally; in
    production the heisenberg DB role is created NOSUPERUSER NOBYPASSRLS.)
    """
    expr = "NULLIF(current_setting('app.user_id', true), '')::uuid"
    bypass = "current_setting('app.bypass_rls', true) = 'on'"

    # users: a user can only see their own row.
    # The bypass guard lets the auth router do email-lookup at login (when
    # we don't yet know the user_id) and INSERT during registration. The
    # bypass is set explicitly by `set_bypass_rls(session, True)` and is
    # transaction-local — it never leaks across requests.
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY users_self_rls ON users "
        f"USING (id = {expr} OR {bypass}) "
        f"WITH CHECK (id = {expr} OR {bypass})"
    )

    # Tables with a user_id column.
    for table in ("workspaces", "jobs", "provider_credentials", "payments"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_user_rls ON {table} "
            f"USING (user_id = {expr}) "
            f"WITH CHECK (user_id = {expr})"
        )

    # Auth.js tables: column is camelCase 'userId'. The accounts table also
    # honors `app.bypass_rls` so the OAuth handshake can look up an existing
    # account by (provider, providerAccountId) before app.user_id is known.
    for table in ("accounts", "sessions", "authenticators"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f'CREATE POLICY {table}_user_rls ON {table} '
            f'USING ("userId" = {expr} OR {bypass}) '
            f'WITH CHECK ("userId" = {expr} OR {bypass})'
        )

    # audit_log: user_id is nullable. Allow read of own + system rows; insert is
    # done server-side with the explicit user_id, so the policy filters by
    # user_id matching app.user_id (system events with NULL user_id are not
    # readable by users — only by ops via direct DB access).
    op.execute("ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_log FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY audit_log_user_rls ON audit_log "
        f"USING (user_id = {expr}) "
        f"WITH CHECK (user_id = {expr})"
    )

    # workspace_files: filter via parent workspace's user_id.
    op.execute("ALTER TABLE workspace_files ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workspace_files FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY workspace_files_parent_rls ON workspace_files "
        f"USING ( "
        f"  EXISTS ( "
        f"    SELECT 1 FROM workspaces w "
        f"    WHERE w.id = workspace_files.workspace_id "
        f"      AND w.user_id = {expr} "
        f"  ) "
        f") "
        f"WITH CHECK ( "
        f"  EXISTS ( "
        f"    SELECT 1 FROM workspaces w "
        f"    WHERE w.id = workspace_files.workspace_id "
        f"      AND w.user_id = {expr} "
        f"  ) "
        f")"
    )

    # results: filter via parent job's user_id.
    op.execute("ALTER TABLE results ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE results FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY results_parent_rls ON results "
        f"USING ( "
        f"  EXISTS ( "
        f"    SELECT 1 FROM jobs j "
        f"    WHERE j.id = results.job_id "
        f"      AND j.user_id = {expr} "
        f"  ) "
        f") "
        f"WITH CHECK ( "
        f"  EXISTS ( "
        f"    SELECT 1 FROM jobs j "
        f"    WHERE j.id = results.job_id "
        f"      AND j.user_id = {expr} "
        f"  ) "
        f")"
    )

    # verification_tokens: not user-scoped; lookup is by (identifier, token)
    # which acts as a one-time secret (Auth.js Email-provider magic links).
    # No RLS — Auth.js writes/reads these server-side only.


def downgrade() -> None:
    # Drop policies first (they're attached to tables; drop_table cascades, but
    # dropping by name is explicit and safer).
    for stmt in (
        "DROP POLICY IF EXISTS results_parent_rls ON results",
        "DROP POLICY IF EXISTS workspace_files_parent_rls ON workspace_files",
        "DROP POLICY IF EXISTS audit_log_user_rls ON audit_log",
        "DROP POLICY IF EXISTS authenticators_user_rls ON authenticators",
        "DROP POLICY IF EXISTS sessions_user_rls ON sessions",
        "DROP POLICY IF EXISTS accounts_user_rls ON accounts",
        "DROP POLICY IF EXISTS payments_user_rls ON payments",
        "DROP POLICY IF EXISTS provider_credentials_user_rls ON provider_credentials",
        "DROP POLICY IF EXISTS jobs_user_rls ON jobs",
        "DROP POLICY IF EXISTS workspaces_user_rls ON workspaces",
        "DROP POLICY IF EXISTS users_self_rls ON users",
    ):
        op.execute(stmt)

    op.drop_index("ix_audit_log_action", table_name="audit_log")
    op.drop_index("ix_audit_log_user_id", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("ix_payments_user_id", table_name="payments")
    op.drop_index("ix_payments_stripe_session_id", table_name="payments")
    op.drop_table("payments")

    op.drop_table("results")

    op.drop_index("ix_jobs_user_state_queued", table_name="jobs")
    op.drop_index("ix_jobs_state", table_name="jobs")
    op.drop_index("ix_jobs_user_id", table_name="jobs")
    op.drop_table("jobs")

    op.drop_index("ix_provider_credentials_user_id", table_name="provider_credentials")
    op.drop_table("provider_credentials")

    op.drop_table("workspace_files")

    op.drop_index("ix_workspaces_user_id", table_name="workspaces")
    op.drop_table("workspaces")

    op.drop_index("ix_authenticators_userId", table_name="authenticators")
    op.drop_table("authenticators")

    op.drop_index("ix_sessions_userId", table_name="sessions")
    op.drop_index("ix_sessions_sessionToken", table_name="sessions")
    op.drop_table("sessions")

    op.drop_index("ix_accounts_provider", table_name="accounts")
    op.drop_table("accounts")

    op.drop_table("verification_tokens")

    op.drop_index("ix_users_stripe_customer_id", table_name="users")
    op.drop_table("users")

    # Drop named enums (Postgres requires explicit drop; create_table created them).
    op.execute("DROP TYPE IF EXISTS job_state")
    op.execute("DROP TYPE IF EXISTS source_kind")
    op.execute("DROP TYPE IF EXISTS credential_provider")
    op.execute("DROP TYPE IF EXISTS user_role")

    # Extensions are intentionally NOT dropped — other databases on the same
    # cluster may use them, and dropping pgcrypto is destructive (data
    # encrypted with it becomes opaque). The runbook documents manual drop
    # if a full teardown is required.
