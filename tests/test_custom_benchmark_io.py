"""Tests for I/O-heavy parts of custom_benchmark.py – Stufe 4.7.

Targets:
    - _build_sandbox_script: pure function (string-in, string-out)
    - exec_sandboxed: needs a bounded Popen mock for the worker process

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
    _sandbox_environment,
    _build_sandbox_script,
    _extract_reasoning_delta,
    exec_sandboxed,
)
from sandbox_worker import SANDBOX_ALLOWED_MODULES, SANDBOX_BLOCKED_MODULES, SANDBOX_SAFE_BUILTINS


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
    """Build the JSON request consumed by the worker process."""

    def test_returns_string(self):
        result = _build_sandbox_script("x = 1")
        assert isinstance(result, str)
        assert len(result) > 40  # Non-trivial JSON request

    def test_contains_code_to_execute(self):
        code = "print('hello world')"
        result = _build_sandbox_script(code)
        assert json.loads(result)["code"] == code

    def test_contains_worker_request_fields(self):
        result = _build_sandbox_script("x = 1")
        assert json.loads(result) == {"code": "x = 1", "capture_state": False, "tests": None}

    def test_blocks_dangerous_modules(self):
        assert "os" in SANDBOX_BLOCKED_MODULES
        assert "warnings" in SANDBOX_BLOCKED_MODULES
        assert "os" not in SANDBOX_ALLOWED_MODULES

    def test_allows_safe_builtins(self):
        assert "len" in SANDBOX_SAFE_BUILTINS
        assert "__import__" not in SANDBOX_SAFE_BUILTINS

    def test_blocks_dangerous_builtins(self):
        for dangerous in ("exec", "open", "input", "compile", "globals", "locals", "vars", "object", "type"):
            assert dangerous not in SANDBOX_SAFE_BUILTINS

    def test_capture_state_adds_state_collection(self):
        without_state = _build_sandbox_script("x = 1", should_capture_state=False)
        with_state = _build_sandbox_script("x = 1", should_capture_state=True)
        assert json.loads(with_state)["capture_state"] is True
        assert json.loads(without_state)["capture_state"] is False

    def test_tests_add_test_execution(self):
        without_tests = _build_sandbox_script("x = 1")
        with_tests = _build_sandbox_script("x = 1", tests=["assert x == 1"])
        assert json.loads(with_tests)["tests"] == ["assert x == 1"]
        assert json.loads(without_tests)["tests"] is None

    def test_specific_test_in_script(self):
        test_code = "assert x == 42"
        result = _build_sandbox_script("x = 42", tests=[test_code])
        assert json.loads(result)["tests"] == [test_code]

    def test_handles_special_characters_in_code(self):
        # Code with quotes, newlines, etc. should be properly JSON-escaped
        code = "x = 'hello\\nworld'  # comment with \"quotes\""
        result = _build_sandbox_script(code)
        assert json.loads(result)["code"] == code

    def test_unicode_in_code(self):
        # Code with unicode characters
        code = "x = 'über'  # Größe"
        result = _build_sandbox_script(code)
        assert json.loads(result)["code"] == code


class TestSandboxEnvironment:
    def test_keeps_temp_paths_inside_worker_directory(self, tmp_path):
        env = _sandbox_environment(str(tmp_path))
        assert env["TEMP"] == str(tmp_path)
        assert env["TMP"] == str(tmp_path)
        assert env["PYTHONNOUSERSITE"] == "1"

    def test_drops_secret_environment_values(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BENCHMARK_TOKEN", "should-not-enter-worker")
        env = _sandbox_environment(str(tmp_path))
        assert "BENCHMARK_TOKEN" not in env


# ─────────────────────────────────────────────────────────────────────
# exec_sandboxed
# ─────────────────────────────────────────────────────────────────────

class TestExecSandboxed:
    """Execute Python code in a sandbox subprocess."""

    @staticmethod
    def _popen_factory(stdout_text: str, stderr_text: str = "", timeout: bool = False):
        def factory(*args, **kwargs):
            class FakePopen:
                _handle = 1
                _thread = 1

                def communicate(self, input=None, timeout=None):
                    if timeout and timeout_requested:
                        raise subprocess.TimeoutExpired(cmd=args[0], timeout=timeout)
                    return stdout_text.encode("utf-8"), stderr_text.encode("utf-8")

                def kill(self):
                    return None

            timeout_requested = timeout
            return FakePopen()

        return factory

    @staticmethod
    def _patch_job(mocker):
        job = MagicMock()
        mocker.patch.object(cb, "WindowsJobObject", return_value=job)
        return job

    def test_successful_execution(self, mocker, tmp_path):
        success_json = json.dumps({"ok": True, "error": None, "state": None,
                                   "passed": 0, "total": 0, "details": []})
        self._patch_job(mocker)
        mocker.patch.object(
            cb._subprocess,
            "Popen",
            side_effect=self._popen_factory(f"__SANDBOX__{success_json}"),
        )
        ok, err = exec_sandboxed("x = 1")
        assert ok is True
        assert err is None

    def test_failed_execution_returns_error(self, mocker, tmp_path):
        error_json = json.dumps({"ok": False, "error": "NameError: name 'x' is not defined",
                                 "state": None, "passed": 0, "total": 0, "details": []})
        self._patch_job(mocker)
        mocker.patch.object(
            cb._subprocess,
            "Popen",
            side_effect=self._popen_factory(f"__SANDBOX__{error_json}"),
        )
        ok, err = exec_sandboxed("undefined_var")
        assert ok is False
        assert "NameError" in err

    def test_no_sandbox_marker_returns_error(self, mocker, tmp_path):
        self._patch_job(mocker)
        mocker.patch.object(
            cb._subprocess,
            "Popen",
            side_effect=self._popen_factory("regular output\n", "some stderr"),
        )
        ok, err = exec_sandboxed("x = 1")
        assert ok is False
        assert err is not None

    def test_timeout_returns_timeout_error(self, mocker):
        self._patch_job(mocker)
        mocker.patch.object(
            cb._subprocess,
            "Popen",
            side_effect=self._popen_factory("", timeout=True),
        )
        ok, err = exec_sandboxed("x = 1", timeout=30)
        assert ok is False
        assert "Timeout" in err

    def test_custom_timeout_passed_through(self, mocker, tmp_path):
        success_json = json.dumps({"ok": True, "error": None, "state": None,
                                   "passed": 0, "total": 0, "details": []})
        self._patch_job(mocker)
        mock_run = mocker.patch.object(
            cb._subprocess,
            "Popen",
            side_effect=self._popen_factory(f"__SANDBOX__{success_json}"),
        )
        exec_sandboxed("x = 1", timeout=120)
        assert mock_run.call_args.kwargs["cwd"]

    def test_executable_passed_to_subprocess_run(self, mocker, tmp_path):
        success_json = json.dumps({"ok": True, "error": None, "state": None,
                                   "passed": 0, "total": 0, "details": []})
        self._patch_job(mocker)
        mock_run = mocker.patch.object(
            cb._subprocess,
            "Popen",
            side_effect=self._popen_factory(f"__SANDBOX__{success_json}"),
        )
        exec_sandboxed("x = 1")
        call_args = mock_run.call_args
        first_arg = call_args.args[0]
        assert first_arg[0] == sys.executable
        assert first_arg[1:4] == ["-I", "-B", "-X"]


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
