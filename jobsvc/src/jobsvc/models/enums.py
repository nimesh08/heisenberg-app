# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""Job state machine, source-kind enum, user role enum.

Job state transitions are an explicit set; anything not listed raises
`IllegalTransitionError`. The set is small enough to grok by reading.
"""

from __future__ import annotations

import enum


class JobState(str, enum.Enum):
    """States a Job passes through.

    Members:
        Submitted: Initial state, set by the API on POST.
        Queued: Cost check passed; awaiting a worker claim.
        Running: A worker holds the job (claim_expires_at set).
        Completed: Worker stored a histogram in Result.
        Rejected: Cost check failed up front, or user cancelled.
        Failed: Worker errored — see error_kind ("our" vs "provider").
    """

    Submitted = "Submitted"
    Queued = "Queued"
    Running = "Running"
    Completed = "Completed"
    Rejected = "Rejected"
    Failed = "Failed"


class SourceKind(str, enum.Enum):
    """Which source language is being submitted. File-extension derived."""

    spinor = "spinor"
    phonon = "phonon"
    photon = "photon"

    @classmethod
    def from_path(cls, path: str) -> SourceKind:
        """Map a path's extension to a SourceKind. Raises ValueError on unknown."""
        if path.endswith(".spn"):
            return cls.spinor
        if path.endswith(".phn"):
            return cls.phonon
        if path.endswith(".pho"):
            return cls.photon
        raise ValueError(
            f"unknown source extension on {path!r}; expected .spn, .phn, or .pho"
        )


class UserRole(str, enum.Enum):
    """Authorisation role on a User.

    Members:
        user: Default. Manages own jobs / workspaces / BYOK / billing.
        admin: Operator. Reaches /admin routes; can ban users; can refund.
    """

    user = "user"
    admin = "admin"


class CredentialProvider(str, enum.Enum):
    """Cloud QPU provider for BYOK credentials. Mirrors spinor_submit's live providers."""

    ibm = "ibm"
    aws = "aws"
    azure = "azure"


# --------------- state machine ---------------

LEGAL_TRANSITIONS: frozenset[tuple[JobState, JobState]] = frozenset({
    (JobState.Submitted, JobState.Queued),
    (JobState.Submitted, JobState.Rejected),
    (JobState.Queued, JobState.Running),
    (JobState.Queued, JobState.Rejected),  # cancel pre-claim
    (JobState.Running, JobState.Completed),
    (JobState.Running, JobState.Failed),
    (JobState.Running, JobState.Rejected),  # provider-supported cancel
    (JobState.Running, JobState.Queued),    # worker crash + lease expiry
})


TERMINAL_STATES: frozenset[JobState] = frozenset({
    JobState.Completed,
    JobState.Rejected,
    JobState.Failed,
})


class IllegalTransitionError(ValueError):
    """A state transition not in LEGAL_TRANSITIONS was attempted."""


__all__ = [
    "CredentialProvider",
    "IllegalTransitionError",
    "JobState",
    "LEGAL_TRANSITIONS",
    "SourceKind",
    "TERMINAL_STATES",
    "UserRole",
]
