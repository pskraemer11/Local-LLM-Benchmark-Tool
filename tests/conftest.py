"""Shared pytest fixtures and mocking helpers for the LLM Benchmark Suite.

Prio 4.16 (Code-Review_2026-07-12.md) – Mocking infrastructure.

The benchmark code talks to a real LM Studio server via HTTP and
spawns subprocesses for `lm_eval`, `evalplus`, `tool_eval_bench`,
and `lms`. We can't run those for real in CI (no GPU, no time).
This conftest provides reusable fixtures that mock all those externals.

Available fixtures (auto-discovered by pytest):
    lms_cli (function scope)
        Mocks `lms` CLI subprocess calls (load, unload, ps, ls).
        Configure via fixture.set_response().

    lms_http (function scope)
        Mocks LM Studio REST API (/v1/chat/completions,
        /v1/models, /api/v1/models). Uses the `responses` library.

    sandbox_subprocess (function scope)
        Mocks `subprocess.run` for the custom_benchmark sandbox
        (the temp-directory Python execution). Returns scripted
        results.

    mock_lmeval_subprocess (function scope)
        Mocks `python -m lm_eval` subprocess invocations and provides
        fake results_*.json + raw_*.jsonl files on demand.

    mock_model_loaded (session scope)
        Combines the above to simulate a fully-loaded model. Tests
        that need a running model state use this fixture.

Usage example::

    def test_evaluate_code(lms_http, sandbox_subprocess):
        # lms_http: POST /v1/chat/completions is mocked
        # sandbox_subprocess: _run_sandbox is mocked
        ...
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any
from unittest.mock import MagicMock

import pytest


# Make repo root importable for all tests
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# ─────────────────────────────────────────────────────────────────────
# LM Studio CLI mocking
# ─────────────────────────────────────────────────────────────────────

class LMSCliMocker:
    """Mock for the `lms` CLI tool (lms load, unload, ps, ls).

    Configures subprocess.run to return scripted responses for
    `lms` commands. Designed to be combined with mocker.patch
    on subprocess.run.

    Usage:
        mocker.patch("subprocess.run", side_effect=lms_cli.set_response([
            ("lms ls --json", {"returncode": 0, "stdout": "[...]"}),
            ("lms load <key> --yes", {"returncode": 0, "stdout": "Loaded"}),
        ]))
    """

    def __init__(self) -> None:
        self._responses: list[dict[str, Any]] = []
        self._default: dict[str, Any] = {
            "returncode": 0,
            "stdout": "",
            "stderr": "",
        }

    def set_response(self, *args: tuple[str, dict[str, Any]]) -> "LMSCliMocker":
        """Register responses for specific lms commands.

        Each entry is (cmd_substring, response_dict). cmd_substring is
        matched against the first element of subprocess.run call args.
        """
        for cmd, resp in args:
            self._responses.append((cmd, resp))
        return self

    def set_default(self, response: dict[str, Any]) -> "LMSCliMocker":
        """Set the default response for unmatched commands."""
        self._default = response
        return self

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        # First positional arg is the command list (subprocess.run)
        cmd = args[0] if args else kwargs.get("args", [])
        if isinstance(cmd, (list, tuple)):
            cmd_str = " ".join(str(c) for c in cmd)
        else:
            cmd_str = str(cmd)
        for needle, response in self._responses:
            if needle in cmd_str:
                return MagicMock(**response)
        return MagicMock(**self._default)


@pytest.fixture
def lms_cli(mocker) -> LMSCliMocker:
    """Fixture returning an LMSCliMocker helper.

    Combine with `mocker.patch("subprocess.run", side_effect=lms_cli)`
    in your test, then call `lms_cli.set_response(...)` to script
    the desired lms CLI output.
    """
    return LMSCliMocker()


# ─────────────────────────────────────────────────────────────────────
# LM Studio HTTP API mocking (uses `responses` library)
# ─────────────────────────────────────────────────────────────────────

class LMSHttpMocker:
    """Mock for LM Studio REST API endpoints.

    Wraps the `responses` library to provide pre-canned answers
    for /v1/chat/completions, /v1/models, /api/v1/models.

    Usage:
        lms_http.add_chat_completion("Hello, world!")
        result = requests.post("http://127.0.0.1:1234/v1/chat/completions", ...)
        # result.json() == {"choices": [{"message": {"content": "Hello, world!"}}]}
    """

    def __init__(self) -> None:
        try:
            import responses
        except ImportError as e:
            raise ImportError(
                "responses library required. Run: pip install responses"
            ) from e
        self._mock = responses.RequestsMock(assert_all_requests_are_fired=False)
        self._started = False

    def __enter__(self) -> "LMSHttpMocker":
        self._mock.start()
        self._started = True
        return self

    def __exit__(self, *args: Any) -> None:
        if self._started:
            self._mock.stop()
            self._mock.reset()
            self._started = False

    def add_chat_completion(
        self,
        content: str = "print('hello')",
        model: str = "test-model",
        prompt_tokens: int = 10,
        completion_tokens: int = 5,
        url: str = "http://127.0.0.1:1234/v1/chat/completions",
        status: int = 200,
    ) -> "LMSHttpMocker":
        """Mock a chat completion response."""
        body = {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1_700_000_000,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }
        self._mock.add(
            responses.POST,
            url,
            json=body,
            status=status,
        )
        return self

    def add_models(
        self,
        models: list[str] | None = None,
        url: str = "http://127.0.0.1:1234/v1/models",
    ) -> "LMSHttpMocker":
        """Mock a /v1/models response."""
        models = models or ["test-model"]
        body = {
            "object": "list",
            "data": [{"id": m, "object": "model"} for m in models],
        }
        self._mock.add(responses.GET, url, json=body, status=200)
        return self

    def add_chat_error(
        self,
        error_msg: str = "internal error",
        status: int = 500,
    ) -> "LMSHttpMocker":
        """Mock a chat completion error response."""
        self._mock.add(
            responses.POST,
            "http://127.0.0.1:1234/v1/chat/completions",
            json={"error": error_msg},
            status=status,
        )
        return self


@pytest.fixture
def lms_http() -> LMSHttpMocker:
    """Fixture returning an LMSHttpMocker helper.

    Use as a context manager::

        def test_foo(lms_http):
            with lms_http as m:
                m.add_chat_completion("response content")
                # ... test code that calls requests.post ...
    """
    return LMSHttpMocker()


# ─────────────────────────────────────────────────────────────────────
# Subprocess mocking for sandbox + lm_eval
# ─────────────────────────────────────────────────────────────────────

class SubprocessScriptMocker:
    """Mock `subprocess.run` for the custom_benchmark sandbox
    and the `python -m lm_eval` invocations.

    Each script in the test is matched by its argv[0] or argv[1]
    (typically `sys.executable` + script path).
    """

    def __init__(self) -> None:
        self._by_argv0: dict[str, Any] = {}
        self._by_argv1: dict[str, Any] = {}
        self._fallback: Any = MagicMock(returncode=0, stdout="", stderr="")

    def when_argv0(self, exe: str, response: Any) -> "SubprocessScriptMocker":
        """Register response for a specific executable (e.g. sys.executable)."""
        self._by_argv0[exe] = response
        return self

    def when_argv1(self, script: str, response: Any) -> "SubprocessScriptMocker":
        """Register response for a specific script (e.g. custom_benchmark_v13.py)."""
        self._by_argv1[script] = response
        return self

    def set_fallback(self, response: Any) -> "SubprocessScriptMocker":
        self._fallback = response
        return self

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        cmd = args[0] if args else kwargs.get("args", [])
        if isinstance(cmd, (list, tuple)) and cmd:
            argv0 = str(cmd[0])
            if argv0 in self._by_argv0:
                return self._by_argv0[argv0]
            if len(cmd) > 1:
                argv1 = str(cmd[1])
                if argv1 in self._by_argv1:
                    return self._by_argv1[argv1]
        return self._fallback


@pytest.fixture
def subprocess_scripts() -> SubprocessScriptMocker:
    """Fixture for scripting multiple subprocess.run calls in a test.

    Usage::

        def test_foo(subprocess_scripts, mocker):
            mocker.patch(
                "subprocess.run",
                side_effect=subprocess_scripts
                    .when_argv1("custom_benchmark_v13.py", MagicMock(
                        returncode=0, stdout="Average score: 50%"
                    ))
                    .when_argv0("lms", MagicMock(returncode=0, stdout="Loaded"))
            )
    """
    return SubprocessScriptMocker()


# ─────────────────────────────────────────────────────────────────────
# LM Eval results mocking
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def fake_lmeval_results(tmp_path) -> str:
    """Factory fixture: write fake lm_eval results_*.json files.

    Returns the path to the fake results directory. Tests can then
    point `read_lmeval_per_model()` at this directory.

    Usage::

        def test_foo(fake_lmeval_results):
            # fake_lmeval_results is a path to a directory containing
            # results_<timestamp>.json with realistic schema
            data = {
                "results": {
                    "arc_challenge_chat": {
                        "exact_match,remove_whitespace": 0.75,
                    }
                }
            }
            results_dir = os.path.join(fake_lmeval_results, "task_name")
            os.makedirs(results_dir, exist_ok=True)
            with open(os.path.join(results_dir, "results_20260101.json"), "w") as f:
                json.dump(data, f)
    """
    return str(tmp_path)


# ─────────────────────────────────────────────────────────────────────
# Bench Config fixture
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_results_dir(tmp_path) -> str:
    """Standardized tmp_path for tests that write CSVs."""
    results = tmp_path / "ergebnisse"
    results.mkdir()
    return str(results)
