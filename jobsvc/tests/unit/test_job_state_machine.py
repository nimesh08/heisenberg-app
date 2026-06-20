# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""Unit tests for the Job state machine + SourceKind helpers."""

from __future__ import annotations

import pytest

from jobsvc.models import (
    IllegalTransitionError,
    Job,
    JobState,
    SourceKind,
)


@pytest.fixture
def job() -> Job:
    return Job(
        user_id="00000000-0000-0000-0000-000000000001",
        target="ibm_heron_r2",
        shots=1000,
        source="target ibm_heron_r2\nqubit q[2]\nh q[0]\ncx q[0],q[1]\n",
        source_kind=SourceKind.spinor,
    )


def test_initial_state_is_submitted(job: Job) -> None:
    assert job.state is JobState.Submitted
    assert not job.is_terminal


def test_legal_path_to_completed(job: Job) -> None:
    job.transition(JobState.Queued)
    assert job.state is JobState.Queued
    assert job.queued_at is not None
    job.transition(JobState.Running)
    assert job.state is JobState.Running
    assert job.started_at is not None
    job.transition(JobState.Completed)
    assert job.is_terminal
    assert job.finished_at is not None


def test_cancel_pre_claim_is_legal(job: Job) -> None:
    job.transition(JobState.Queued)
    job.transition(JobState.Rejected, reason="user cancel")
    assert job.is_terminal
    assert job.rejection_reason == "user cancel"


def test_failed_records_error_kind(job: Job) -> None:
    job.transition(JobState.Queued)
    job.transition(JobState.Running)
    job.transition(JobState.Failed, reason="ibm 503", error_kind="provider")
    assert job.is_terminal
    assert job.error_kind == "provider"
    assert job.rejection_reason == "ibm 503"


def test_running_can_requeue_for_lease_expiry(job: Job) -> None:
    job.transition(JobState.Queued)
    job.transition(JobState.Running)
    job.transition(JobState.Queued)  # worker crashed; lease expired
    assert job.state is JobState.Queued


def test_illegal_transitions_raise(job: Job) -> None:
    # Submitted -> Running is illegal (must go through Queued).
    with pytest.raises(IllegalTransitionError):
        job.transition(JobState.Running)

    # Submitted -> Completed is illegal.
    with pytest.raises(IllegalTransitionError):
        job.transition(JobState.Completed)


def test_cant_transition_out_of_terminal(job: Job) -> None:
    job.transition(JobState.Queued)
    job.transition(JobState.Running)
    job.transition(JobState.Completed)
    with pytest.raises(IllegalTransitionError):
        job.transition(JobState.Queued)


def test_source_kind_from_path() -> None:
    assert SourceKind.from_path("foo/bar/bell.spn") is SourceKind.spinor
    assert SourceKind.from_path("circuit.phn") is SourceKind.phonon
    assert SourceKind.from_path("hello.pho") is SourceKind.photon
    with pytest.raises(ValueError, match="unknown source extension"):
        SourceKind.from_path("foo.txt")
