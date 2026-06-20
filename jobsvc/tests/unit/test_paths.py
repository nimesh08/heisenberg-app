# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""Unit tests for jobsvc.services.paths."""

from __future__ import annotations

import pytest
from jobsvc.services.paths import PATH_MAX_LEN, InvalidPath, normalise_path


def test_simple_path_passes() -> None:
    assert normalise_path("bell.spn") == "bell.spn"


def test_subdir_path_passes() -> None:
    assert normalise_path("examples/bell.spn") == "examples/bell.spn"


def test_trailing_slash_is_stripped() -> None:
    assert normalise_path("examples/bell.spn/") == "examples/bell.spn"


def test_empty_path_rejected() -> None:
    with pytest.raises(InvalidPath, match="empty"):
        normalise_path("")


def test_too_long_rejected() -> None:
    with pytest.raises(InvalidPath, match="exceeds"):
        normalise_path("x" * (PATH_MAX_LEN + 1))


def test_leading_slash_rejected() -> None:
    with pytest.raises(InvalidPath, match="must not start"):
        normalise_path("/etc/passwd")


def test_dotdot_rejected() -> None:
    with pytest.raises(InvalidPath, match="'..'"):
        normalise_path("../etc/passwd")


def test_dotdot_in_middle_rejected() -> None:
    with pytest.raises(InvalidPath, match="'..'"):
        normalise_path("a/../b")


def test_single_dot_segment_rejected() -> None:
    with pytest.raises(InvalidPath, match="'..'"):
        normalise_path("./bell.spn")


def test_double_slash_rejected() -> None:
    with pytest.raises(InvalidPath, match="'//'"):
        normalise_path("a//b")


def test_backslash_rejected() -> None:
    with pytest.raises(InvalidPath, match="backslash"):
        normalise_path("a\\b")


def test_nul_byte_rejected() -> None:
    with pytest.raises(InvalidPath, match="NUL"):
        normalise_path("a\x00b")


def test_control_char_rejected() -> None:
    with pytest.raises(InvalidPath, match="control"):
        normalise_path("a\nb")


def test_del_byte_rejected() -> None:
    with pytest.raises(InvalidPath, match="control"):
        normalise_path("a\x7fb")
