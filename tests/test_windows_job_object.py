"""Focused tests for the cross-platform bounded evaluator launcher."""

from __future__ import annotations

import subprocess
import sys

import pytest

from windows_job_object import run_bounded_subprocess


def test_bounded_subprocess_captures_output_and_returns_success() -> None:
    result = run_bounded_subprocess(
        [sys.executable, "-c", "print(42)"],
        timeout=10,
        memory_limit_bytes=128 * 1024 * 1024,
        max_processes=4,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode == 0
    assert result.stdout.strip() == "42"


def test_bounded_subprocess_terminates_on_timeout() -> None:
    with pytest.raises(subprocess.TimeoutExpired):
        run_bounded_subprocess(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            timeout=0.2,
            memory_limit_bytes=128 * 1024 * 1024,
            max_processes=4,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
