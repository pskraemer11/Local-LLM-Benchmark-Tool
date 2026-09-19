"""Focused tests for the bounded worker policy."""

from __future__ import annotations

import sys

sys.path.insert(0, "src")

import pytest

from sandbox_worker import _execute


def test_standard_import_and_execution() -> None:
    result = _execute({"code": "import math\nvalue = math.sqrt(9)", "capture_state": True, "tests": None})
    assert result["ok"] is True
    assert result["state"]["value"] == "3.0"


@pytest.mark.parametrize("code", [
    "import os",
    "import warnings",
    "import sys",
    "from pathlib import Path",
])
def test_standard_library_import_is_available(code: str) -> None:
    result = _execute({"code": code, "capture_state": False, "tests": None})
    assert result["ok"] is True


@pytest.mark.parametrize("code", [
    "value = object.__subclasses__()",
    "value = ().__class__",
])
def test_dunder_syntax_is_compatible(code: str) -> None:
    result = _execute({"code": code, "capture_state": False, "tests": None})
    assert result["ok"] is True


def test_native_loader_code_reaches_runtime_boundary() -> None:
    result = _execute({
        "code": "import numpy as np\nassert hasattr(np, 'ctypeslib')",
        "capture_state": False,
        "tests": None,
    })
    assert result["ok"] is True


def test_tests_and_state_use_same_bounded_namespace() -> None:
    result = _execute({
        "code": "value = 41",
        "capture_state": True,
        "tests": ["assert value + 1 == 42"],
    })
    assert result["ok"] is True
    assert result["passed"] == 1
    assert result["total"] == 1
