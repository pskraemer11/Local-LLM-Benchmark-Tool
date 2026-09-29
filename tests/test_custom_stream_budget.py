"""Bounded streaming contracts using the real consumer and a finite fake SSE transport."""

from __future__ import annotations

import json
import sys
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, "src")
import custom_benchmark as cb


class _Response:
    def __init__(self, chunks=None, *, continuous=False):
        self.chunks = chunks or []
        self.continuous = continuous
        self.closed = False
        self.consumed = 0

    def raise_for_status(self):
        pass

    def iter_lines(self, decode_unicode=True):
        if self.continuous:
            deadline = time.monotonic() + 2
            while not self.closed and time.monotonic() < deadline:
                time.sleep(0.005)
                yield 'data: {"choices":[{"delta":{"reasoning":"thinking "}}]}'
            return
        for chunk in self.chunks:
            if self.closed:
                return
            self.consumed += 1
            yield "data: " + json.dumps(chunk)

    def close(self):
        self.closed = True


class _Session:
    def __init__(self, response):
        self.response = response
        self.request = None

    def post(self, url, **kwargs):
        self.request = kwargs
        return self.response

    def close(self):
        pass


def _transport(monkeypatch, response):
    session = _Session(response)
    monkeypatch.setattr(cb.requests, "Session", lambda: session)
    return session


@pytest.mark.parametrize("usage_only", [True, False])
def test_stream_stops_at_reported_total_budget_including_reasoning(monkeypatch, usage_only):
    choices = [] if usage_only else [{"delta": {}}]
    response = _Response(
        [
            {"choices": [{"delta": {"content": "answer", "reasoning": "a thought"}}]},
            {
                "choices": choices,
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 8,
                    "completion_tokens_details": {"reasoning_tokens": 6},
                },
            },
            {"choices": [{"delta": {"content": " must not be consumed"}}]},
        ]
    )
    session = _transport(monkeypatch, response)

    result = cb._stream_chat_completion(
        "http://fixture/v1/chat/completions", {}, {"max_tokens": 8}, max_retries=1, finish_timeout=1
    )

    assert result[0] == "answer"
    assert result[2:4] == (10, 8)
    assert result[5:8] == (6, True, None)
    assert response.consumed == 2
    assert response.closed is True
    assert session.request["json"]["stream_options"]["include_usage"] is True


def test_over_budget_response_is_a_blocking_error(monkeypatch):
    response = _Response(
        [
            {"choices": [{"delta": {"content": "answer"}}]},
            {"choices": [], "usage": {"completion_tokens": 9}},
        ]
    )
    _transport(monkeypatch, response)

    result = cb._stream_chat_completion(
        "http://fixture/v1/chat/completions", {}, {"max_tokens": 8}, max_retries=1, finish_timeout=1
    )

    assert result[0] is None
    assert result[3] == 9
    assert result[6] is True
    assert result[7] == "output_budget_exceeded"


def test_continuous_reasoning_cannot_reset_the_absolute_deadline(monkeypatch):
    response = _Response(continuous=True)
    _transport(monkeypatch, response)

    result = cb._stream_chat_completion(
        "http://fixture/v1/chat/completions", {}, {"max_tokens": 8}, max_retries=3, finish_timeout=1, total_timeout=0.15
    )

    assert result[0] is None
    assert result[1] < 0.8
    assert result[7] == "timeout"
    assert response.closed is True


def test_deadline_interrupts_a_blocking_read_before_closing_response(monkeypatch):
    response = _Response(continuous=True)
    calls = []
    response.raw = SimpleNamespace(shutdown=lambda: calls.append("shutdown"))
    original_close = response.close

    def close():
        calls.append("close")
        original_close()

    response.close = close
    _transport(monkeypatch, response)

    result = cb._stream_chat_completion(
        "http://fixture/v1/chat/completions", {}, {"max_tokens": 8}, max_retries=1, total_timeout=0.15
    )

    assert result[7] == "timeout"
    assert calls[0] == "shutdown"


@pytest.mark.parametrize("error", ["timeout", "output_budget_exceeded"])
def test_generate_does_not_retry_a_blocking_stream_limit(monkeypatch, error):
    monkeypatch.setattr(
        cb,
        "_stream_chat_completion",
        lambda *_args, **_kwargs: (None, 1.0, 10, 8, 8.0, 8, True, error, "limit reached"),
    )
    monkeypatch.setattr(
        cb,
        "_non_streaming_fallback",
        lambda *_args, **_kwargs: pytest.fail("blocked stream must not start another generation"),
    )

    result = cb.generate_answer(cb.GenerationConfig(prompt="hello", max_tokens=8, reasoning_template_kwargs={}))

    assert result[7] == error


def test_generation_timeout_is_expressed_in_transport_seconds():
    assert cb.GenerationConfig().timeout == 120


def test_nonstream_over_budget_response_is_a_blocking_error(monkeypatch):
    monkeypatch.setattr(cb, "_non_streaming_fallback", lambda *_args, **_kwargs: ("answer", 10, 9, 8, True))

    result = cb.generate_answer(
        cb.GenerationConfig(prompt="hello", max_tokens=8, is_streaming=False, reasoning_template_kwargs={})
    )

    assert result[0] is None
    assert result[7] == "output_budget_exceeded"


@pytest.mark.parametrize("error", ["timeout", "output_budget_exceeded"])
@pytest.mark.parametrize("parallel", [1, 2])
def test_task_runner_does_not_repeat_a_terminal_budget_failure(monkeypatch, error, parallel):
    calls = []
    failed = {
        "response": None,
        "extracted_code": "",
        "score": 0.0,
        "score_detail": "limit reached",
        "latency": 1.0,
        "tokens_in": 10,
        "tokens_out": 8,
        "tokens_per_sec": 8.0,
        "thinking_tokens": 8,
        "truncated": True,
        "error_type": error,
        "error_detail": "limit reached",
    }

    def run(*_args, **_kwargs):
        calls.append(True)
        return failed.copy()

    resources = {"cpu": 0, "ram": 0, "gpu": 0, "vram": 0}
    monitor = SimpleNamespace(
        get_snapshot=lambda: resources, start_sampling=lambda: None, stop_sampling=lambda: resources
    )
    collector = SimpleNamespace(
        start=lambda: None, maybe_sample=lambda: None, stop=lambda: None, get_summary=lambda: {}
    )
    monkeypatch.setattr(cb, "MetricsCollector", lambda: collector)
    monkeypatch.setattr(
        cb,
        "_get_model_config",
        lambda *_args, **_kwargs: {
            "temperature": 0,
            "top_p": 1,
            "max_tokens": 8,
            "enable_thinking": False,
        },
    )
    monkeypatch.setattr(cb, "run_task", run)
    monkeypatch.setattr(cb.time, "sleep", lambda _seconds: None)

    results = cb.benchmark_model(
        {"key": "fixture/model@q4_k", "display": "fixture"},
        [{"prompt": "task"}],
        "data_science",
        "DS1000",
        monitor,
        is_quiet_mode=True,
        num_parallel=parallel,
    )[0]

    assert len(calls) == 1
    assert results[0]["error_type"] == error
