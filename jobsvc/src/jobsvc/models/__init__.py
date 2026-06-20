# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""SQLModel re-exports.

Importing `from jobsvc.models import *` gives you everything; SQLModel.metadata
includes every table.
"""

from __future__ import annotations

from .audit import AuditLog
from .billing import Payment
from .credential import ProviderCredential

# Import order matters for SQLAlchemy's mapper registry: parent tables must
# be imported before tables that reference them via string-form relationships.
from .enums import (
    LEGAL_TRANSITIONS,
    TERMINAL_STATES,
    CredentialProvider,
    IllegalTransitionError,
    JobState,
    SourceKind,
    UserRole,
)
from .job import Job, Result
from .user import Account, Authenticator, Session, User, VerificationToken
from .workspace import Workspace, WorkspaceFile

__all__ = [
    "Account",
    "AuditLog",
    "Authenticator",
    "CredentialProvider",
    "IllegalTransitionError",
    "Job",
    "JobState",
    "LEGAL_TRANSITIONS",
    "Payment",
    "ProviderCredential",
    "Result",
    "Session",
    "SourceKind",
    "TERMINAL_STATES",
    "User",
    "UserRole",
    "VerificationToken",
    "Workspace",
    "WorkspaceFile",
]
