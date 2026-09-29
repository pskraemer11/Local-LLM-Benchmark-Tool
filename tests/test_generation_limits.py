"""Evidence checks shared by streaming consumers and HTTP providers."""

from __future__ import annotations

import pytest

from generation_limits import RepetitionGuard, generation_usage_violation
from providers.base import HttpProvider, ProviderError
from tests.test_custom_stream_repetition import PYTHON_BLOCK


@pytest.mark.parametrize("method", ["chat_completions", "completions"])
@pytest.mark.parametrize("key", ["max_thinking_tokens", "reasoning_budget"])
def test_http_provider_rejects_reported_reasoning_overrun(monkeypatch, method, key):
    provider = HttpProvider("http://fixture/v1")
    response = {"usage": {
        "completion_tokens": 12, "completion_tokens_details": {"reasoning_tokens": 9},
    }}
    monkeypatch.setattr(provider, "request_json", lambda *_args, **_kwargs: response)

    with pytest.raises(ProviderError, match="reasoning_budget_exceeded"):
        getattr(provider, method)({"max_tokens": 20, key: 8})


@pytest.mark.parametrize("reasoning", [None, True, "9", -1])
def test_unreported_or_invalid_reasoning_cannot_prove_a_token_overrun(reasoning):
    assert generation_usage_violation({"max_tokens": 20, "reasoning_budget": 8}, {
        "completion_tokens": 12, "completion_tokens_details": {"reasoning_tokens": reasoning},
    }) is None


def test_smallest_positive_reasoning_budget_is_the_contract():
    usage = {"completion_tokens": 12, "completion_tokens_details": {"reasoning_tokens": 9}}
    violation = generation_usage_violation(
        {"max_tokens": 20, "max_thinking_tokens": 15, "reasoning_budget": 10}, usage, reasoning_budget=8,
    )
    assert violation.error_type == "reasoning_budget_exceeded"
    assert "requested 8" in violation.detail
    assert generation_usage_violation({"max_tokens": 20, "max_thinking_tokens": True}, usage) is None


def test_completion_total_is_not_added_to_its_reasoning_breakdown():
    assert generation_usage_violation({"max_tokens": 12, "reasoning_budget": 9}, {
        "completion_tokens": 12, "completion_tokens_details": {"reasoning_tokens": 9},
    }) is None


def test_final_partial_interval_and_one_character_chunks_preserve_detection():
    guard = RepetitionGuard()
    detected = False
    for character in PYTHON_BLOCK * 4:
        detected |= guard.feed(character)
    assert detected or guard.finish()


def test_repetition_normalizes_chunk_split_whitespace():
    blocks = [PYTHON_BLOCK, PYTHON_BLOCK.replace("\n", " \n "), PYTHON_BLOCK.replace(" ", "  "), PYTHON_BLOCK]
    guard = RepetitionGuard()
    detected = False
    for character in "".join(blocks):
        detected |= guard.feed(character)
    assert detected or guard.finish()


def test_guard_retains_a_bounded_window_for_long_unique_output():
    guard = RepetitionGuard()
    for index in range(3000):
        assert not guard.feed(f"measurement_{index}: a distinct recorded observation {index}\n")
    assert len(guard._tail) <= 32768
