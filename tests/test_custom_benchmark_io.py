"""Tests for I/O-heavy parts of custom_benchmark.py – Stufe 4.7.

Targets:
    - _build_sandbox_script: pure function (string-in, string-out)
    - exec_sandboxed: needs subprocess.run mock via the conftest fixture

Stufe 4.8 (_stream_chat_completion) is deferred to a later iteration
since it requires a more elaborate mock for HTTP streaming.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import custom_benchmark as cb
from custom_benchmark import (
    _SANDBOX_BLOCKED_MODULES,
    _SANDBOX_SAFE_BUILTINS,
    _build_sandbox_script,
    _extract_reasoning_delta,
    exec_sandboxed,
)


# ─────────────────────────────────────────────────────────────────────
# _extract_reasoning_delta
# ─────────────────────────────────────────────────────────────────────

class TestExtractReasoningDelta:
    """Reasoning-Content aus Stream-Deltas extrahieren.

    DeepSeek R1 (0.3.9+): delta.reasoning_content
    gpt-oss (0.3.23+, o3-mini-konform): delta.reasoning
    """

    def test_reasoning_content_field(self):
        assert _extract_reasoning_delta({"reasoning_content": "Need to"}) == "Need to"

    def test_reasoning_field(self):
        assert _extract_reasoning_delta({"reasoning": "Need to"}) == "Need to"

    def test_reasoning_content_takes_priority(self):
        assert _extract_reasoning_delta({"reasoning": "a", "reasoning_content": "b"}) == "b"

    def test_reasoning_non_string_ignored(self):
        assert _extract_reasoning_delta({"reasoning": {"effort": "low"}}) == ""

    def test_empty_delta(self):
        assert _extract_reasoning_delta({}) == ""

    def test_only_content(self):
        assert _extract_reasoning_delta({"content": "Hello"}) == ""


# ─────────────────────────────────────────────────────────────────────
# _build_sandbox_script
# ─────────────────────────────────────────────────────────────────────

class TestBuildSandboxScript:
    """Build the sandbox Python script that runs user code safely."""

    def test_returns_string(self):
        result = _build_sandbox_script("x = 1")
        assert isinstance(result, str)
        assert len(result) > 100  # Non-trivial script

    def test_contains_code_to_execute(self):
        code = "print('hello world')"
        result = _build_sandbox_script(code)
        # The user code is JSON-encoded and embedded in the script
        assert json.dumps(code) in result

    def test_contains_sandbox_marker(self):
        result = _build_sandbox_script("x = 1")
        # The script prints a special marker to identify its output
        assert "__SANDBOX__" in result

    def test_blocks_dangerous_modules(self):
        result = _build_sandbox_script("import os")
        # The blocked modules are listed in the script
        for blocked in _SANDBOX_BLOCKED_MODULES:
            assert blocked in result

    def test_allows_safe_builtins(self):
        result = _build_sandbox_script("x = 1")
        # The safe builtins are listed
        for safe in _SANDBOX_SAFE_BUILTINS:
            assert safe in result

    def test_blocks_dangerous_builtins(self):
        result = _build_sandbox_script("x = 1")
        # The dangerous builtins are removed
        for dangerous in ("exec", "open", "input", "compile", "globals", "locals", "vars"):
            # Check the removal logic is in the script
            assert f"'{dangerous}'" in result

    def test_capture_state_adds_state_collection(self):
        without_state = _build_sandbox_script("x = 1", should_capture_state=False)
        with_state = _build_sandbox_script("x = 1", should_capture_state=True)
        # capture_state=True adds state-collection code
        assert "_state" in with_state
        assert "_state" not in without_state

    def test_tests_add_test_execution(self):
        without_tests = _build_sandbox_script("x = 1")
        with_tests = _build_sandbox_script("x = 1", tests=["assert x == 1"])
        # tests parameter adds test-execution code
        assert "_test_items" in with_tests
        assert "_test_results" in with_tests
        assert "_test_items" not in without_tests

    def test_specific_test_in_script(self):
        test_code = "assert x == 42"
        result = _build_sandbox_script("x = 42", tests=[test_code])
        # The test is JSON-encoded
        assert json.dumps(test_code) in result

    def test_handles_special_characters_in_code(self):
        # Code with quotes, newlines, etc. should be properly JSON-escaped
        code = "x = 'hello\\nworld'  # comment with \"quotes\""
        result = _build_sandbox_script(code)
        assert json.dumps(code) in result

    def test_unicode_in_code(self):
        # Code with unicode characters
        code = "x = 'über'  # Größe"
        result = _build_sandbox_script(code)
        assert json.dumps(code) in result


# ─────────────────────────────────────────────────────────────────────
# exec_sandboxed
# ─────────────────────────────────────────────────────────────────────

class TestExecSandboxed:
    """Execute Python code in a sandbox subprocess."""

    def test_successful_execution(self, mocker, tmp_path):
        # Mock subprocess.run to return a successful result
        success_json = json.dumps({"ok": True, "error": None, "state": None,
                                   "passed": 0, "total": 0, "details": []})
        mock_result = MagicMock()
        mock_result.stdout = f"__SANDBOX__{success_json}\n"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mocker.patch("subprocess.run", return_value=mock_result)
        ok, err = exec_sandboxed("x = 1")
        assert ok is True
        assert err is None

    def test_failed_execution_returns_error(self, mocker, tmp_path):
        # Mock subprocess.run to return a failure
        error_json = json.dumps({"ok": False, "error": "NameError: name 'x' is not defined",
                                 "state": None, "passed": 0, "total": 0, "details": []})
        mock_result = MagicMock()
        mock_result.stdout = f"__SANDBOX__{error_json}\n"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mocker.patch("subprocess.run", return_value=mock_result)
        ok, err = exec_sandboxed("undefined_var")
        assert ok is False
        assert "NameError" in err

    def test_no_sandbox_marker_returns_error(self, mocker, tmp_path):
        # Mock subprocess.run to return output without the __SANDBOX__ marker
        mock_result = MagicMock()
        mock_result.stdout = "regular output, no marker\n"
        mock_result.stderr = "some stderr"
        mock_result.returncode = 0
        mocker.patch("subprocess.run", return_value=mock_result)
        ok, err = exec_sandboxed("x = 1")
        # Falls back to stderr or returncode check
        assert ok is False
        assert err is not None

    def test_timeout_returns_timeout_error(self, mocker):
        # Mock subprocess.run to raise TimeoutExpired
        mocker.patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="python", timeout=30),
        )
        ok, err = exec_sandboxed("x = 1", timeout=30)
        assert ok is False
        assert "Timeout" in err

    def test_custom_timeout_passed_through(self, mocker, tmp_path):
        # The custom timeout should be passed to subprocess.run
        success_json = json.dumps({"ok": True, "error": None, "state": None,
                                   "passed": 0, "total": 0, "details": []})
        mock_result = MagicMock()
        mock_result.stdout = f"__SANDBOX__{success_json}\n"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run = mocker.patch("subprocess.run", return_value=mock_result)
        exec_sandboxed("x = 1", timeout=120)
        # Check that subprocess.run was called with timeout=120
        call_args = mock_run.call_args
        assert call_args.kwargs.get("timeout") == 120 or call_args[1].get("timeout") == 120

    def test_executable_passed_to_subprocess_run(self, mocker, tmp_path):
        # subprocess.run should be called with sys.executable
        success_json = json.dumps({"ok": True, "error": None, "state": None,
                                   "passed": 0, "total": 0, "details": []})
        mock_result = MagicMock()
        mock_result.stdout = f"__SANDBOX__{success_json}\n"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run = mocker.patch("subprocess.run", return_value=mock_result)
        exec_sandboxed("x = 1")
        call_args = mock_run.call_args
        # First positional arg should be [sys.executable, <tmpfile_path>]
        first_arg = call_args.args[0] if call_args.args else call_args[0][0]
        assert first_arg[0] == sys.executable


class TestThinkingCodeOnlyPrompts:
    """Prompt-Härtung für Thinking-Modelle (Fix 2026-07-31)."""

    def test_datascience_default_no_suffix(self):
        p = cb._make_datascience_prompt("task", "entry")
        assert "```python" not in p
        assert p.startswith("Complete the following Python code.")

    def test_datascience_code_only_adds_suffix(self):
        p = cb._make_datascience_prompt("task", "", code_only=True)
        assert "```python" in p
        assert "FINAL answer" in p
        assert p.endswith("commentary.")

    def test_codereval_default_no_suffix(self):
        p = cb._make_codereval_prompt("task", "fn")
        assert "```python" not in p
        assert "fn" in p

    def test_codereval_code_only_adds_suffix(self):
        p = cb._make_codereval_prompt("task", "fn", code_only=True)
        assert "```python" in p
        assert "FINAL answer" in p

    def test_entry_point_preserved_with_code_only(self):
        p = cb._make_codereval_prompt("task", "my_fn", code_only=True)
        assert "my_fn" in p
        assert p.index("my_fn") < p.index("```python")
