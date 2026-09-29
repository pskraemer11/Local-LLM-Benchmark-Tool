"""Offline transport regressions for looping output and exact reasoning limits."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

import custom_benchmark as cb
from tests.test_custom_stream_budget import _Response, _transport
from tests.test_custom_stream_budget import (
    test_task_runner_does_not_repeat_a_terminal_budget_failure as _task_retry_check,
)

PYTHON_BLOCK = """```python
def transform_measurements(records, requested_columns, missing_value):
    normalized_records = []
    for record_index, original_record in enumerate(records):
        selected_values = {column_name: original_record.get(column_name, missing_value)
                           for column_name in requested_columns}
        selected_values['record_index'] = record_index
        normalized_records.append(selected_values)
    return normalized_records
```
"""
JS_BLOCK = """```javascript
function transformMeasurements(records, requestedColumns, missingValue) {
    const normalizedRecords = [];
    for (const [recordIndex, originalRecord] of records.entries()) {
        const selectedValues = Object.fromEntries(requestedColumns.map(
            columnName => [columnName, originalRecord[columnName] ?? missingValue]));
        selectedValues.recordIndex = recordIndex;
        normalizedRecords.push(selectedValues);
    }
    return normalizedRecords;
}
```
"""


def _chunks(text: str, channel: str, *, width: int = 37) -> list[dict[str, Any]]:
    return [
        {"choices": [{"delta": {channel: text[offset:offset + width]}}]}
        for offset in range(0, len(text), width)
    ]


@pytest.mark.parametrize("block", [PYTHON_BLOCK, JS_BLOCK])
@pytest.mark.parametrize("channel", ["reasoning", "reasoning_content", "content"])
def test_long_repetition_cancels_before_usage_at_the_end(monkeypatch, block, channel):
    chunks = _chunks(block * 50, channel)
    chunks.append({"choices": [], "usage": {"completion_tokens": 10644}})
    response = _Response(chunks)
    calls = []
    response.raw = SimpleNamespace(shutdown=lambda: calls.append("shutdown"))
    session = _transport(monkeypatch, response)
    post = session.post

    def count_post(*args: Any, **kwargs: Any) -> Any:
        calls.append("post")
        return post(*args, **kwargs)

    session.post = count_post
    monkeypatch.setattr(cb, "_non_streaming_fallback", lambda *_args, **_kwargs: pytest.fail("terminal loop retried"))

    result = cb.generate_answer(cb.GenerationConfig(prompt="task", max_tokens=20000, reasoning_template_kwargs={}))

    assert result[0] is None
    assert result[7] == "repetition_loop"
    assert response.consumed < len(chunks) // 2
    assert response.closed
    assert calls.count("post") == 1
    assert "shutdown" in calls


@pytest.mark.parametrize("opening,closing", [("<think>", "</think>"), ("<|channel>thought\n", "<channel|>")])
def test_repetition_inside_inline_thinking_tags_is_caught_across_chunks(monkeypatch, opening, closing):
    response = _Response(_chunks(opening + PYTHON_BLOCK * 12 + closing + "answer", "content", width=19))
    _transport(monkeypatch, response)

    result = cb._stream_chat_completion("http://fixture", {}, {"max_tokens": 20000}, max_retries=3)

    assert result[7] == "repetition_loop"
    assert response.closed


@pytest.mark.parametrize("text", [PYTHON_BLOCK * 2, "Check this result carefully. " * 300, "A\n" * 3000])
def test_ordinary_repetition_and_two_code_examples_are_allowed(monkeypatch, text):
    response = _Response(_chunks(text, "content"))
    _transport(monkeypatch, response)

    result = cb._stream_chat_completion("http://fixture", {}, {"max_tokens": 20000}, max_retries=1)

    assert result[0] == text
    assert result[7] is None


@pytest.mark.parametrize(
    "block",
    [
        "```python\nwhile True:\n    print(value)\n```\n",
        "```javascript\nwhile (true) { console.log(value); }\n```\n",
    ],
)
@pytest.mark.parametrize("channel", ["reasoning", "content"])
def test_short_low_diversity_code_loop_is_caught_without_usage(monkeypatch, block, channel):
    response = _Response(_chunks(block * 80, channel, width=7))
    _transport(monkeypatch, response)

    result = cb._stream_chat_completion("http://fixture", {}, {"max_tokens": 20000}, max_retries=2)

    assert result[7] == "repetition_loop"
    assert response.closed
    assert response.consumed < len(_chunks(block * 80, channel, width=7)) // 2


@pytest.mark.parametrize("text", [
    "Please consider the result and describe what it means. " * 300,
    "The phrase while True: print(value) is an example of a loop. " * 300,
])
def test_plain_prose_about_loops_is_not_classified_as_repeating_code(monkeypatch, text):
    response = _Response(_chunks(text, "content"))
    _transport(monkeypatch, response)

    result = cb._stream_chat_completion("http://fixture", {}, {"max_tokens": 20000}, max_retries=1)

    assert result[0] == text
    assert result[7] is None


@pytest.mark.parametrize("budget_key", ["max_thinking_tokens", "reasoning_budget"])
def test_reported_reasoning_over_budget_is_terminal_without_double_count(monkeypatch, budget_key):
    response = _Response([
        {"choices": [{"delta": {"reasoning": "short thought"}}]},
        {"choices": [], "usage": {
            "completion_tokens": 10644, "completion_tokens_details": {"reasoning_tokens": 8193},
        }},
        {"choices": [{"delta": {"content": "must not consume"}}]},
    ])
    _transport(monkeypatch, response)

    result = cb._stream_chat_completion(
        "http://fixture", {}, {"max_tokens": 12000, budget_key: 8192}, max_retries=3,
    )

    assert result[0] is None
    assert result[3] == 10644
    assert result[5] == 8193
    assert result[7] == "reasoning_budget_exceeded"
    assert response.consumed == 2
    assert response.closed


@pytest.mark.parametrize("error", ["repetition_loop", "reasoning_budget_exceeded"])
@pytest.mark.parametrize("parallel", [1, 2])
def test_outer_task_retries_stop_for_both_new_terminal_failures(monkeypatch, error, parallel):
    _task_retry_check(monkeypatch, error, parallel)


def test_reasoning_budget_equality_allows_the_final_answer(monkeypatch):
    response = _Response([
        {"choices": [], "usage": {
            "completion_tokens": 8192, "completion_tokens_details": {"reasoning_tokens": 8192},
        }},
        {"choices": [{"delta": {"content": "final answer"}}]},
        {"choices": [], "usage": {
            "completion_tokens": 10644, "completion_tokens_details": {"reasoning_tokens": 8192},
        }},
    ])
    _transport(monkeypatch, response)

    result = cb._stream_chat_completion("http://fixture", {}, {
        "max_tokens": 12000, "max_thinking_tokens": 8192, "reasoning_budget": 9000,
    }, max_retries=1)

    assert result[0] == "final answer"
    assert result[3] == 10644
    assert result[5] == 8192
    assert result[7] is None


def test_gemma_local_reasoning_cap_does_not_require_a_foreign_wire_field(monkeypatch):
    response = _Response([{ "choices": [], "usage": {
        "completion_tokens": 20, "completion_tokens_details": {"reasoning_tokens": 9},
    }}])
    session = _transport(monkeypatch, response)
    monkeypatch.setattr(cb, "_non_streaming_fallback", lambda *_args, **_kwargs: pytest.fail("overrun retried"))

    result = cb.generate_answer(cb.GenerationConfig(
        prompt="task", native_model_identifier="vendor/gemma@q6_k", max_tokens=40,
        max_thinking_tokens=8, reasoning_template_kwargs={},
    ))

    assert result[7] == "reasoning_budget_exceeded"
    assert "max_thinking_tokens" not in session.request["json"]


def test_nonstream_exact_reasoning_cap_is_checked_from_usage(monkeypatch):
    payload = {"choices": [{"message": {"content": "answer"}}], "usage": {
        "completion_tokens": 20, "completion_tokens_details": {"reasoning_tokens": 9},
    }}

    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: Any) -> None:
            pass

        def read(self) -> bytes:
            return json.dumps(payload).encode()

    monkeypatch.setattr(cb, "urlopen", lambda *_args, **_kwargs: Response())

    result = cb.generate_answer(cb.GenerationConfig(
        prompt="task", max_tokens=40, max_thinking_tokens=8,
        is_streaming=False, reasoning_template_kwargs={},
    ))

    assert result[7] == "reasoning_budget_exceeded"
    assert result[3] == 20
    assert result[5] == 9


def test_usage_absent_cannot_convert_text_estimate_into_a_reasoning_budget_violation(monkeypatch):
    response = _Response(_chunks("Consider the requested operation carefully. " * 100, "reasoning"))
    _transport(monkeypatch, response)

    result = cb._stream_chat_completion("http://fixture", {}, {"max_tokens": 20000, "reasoning_budget": 8}, max_retries=1)

    assert result[5] > 8
    assert result[7] is None
