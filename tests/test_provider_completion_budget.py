"""Provider output may not silently exceed the requested completion budget."""

from __future__ import annotations

import sys

import pytest

sys.path.insert(0, "src")
from providers.base import HttpProvider, ProviderError


@pytest.mark.parametrize("method", ["chat_completions", "completions"])
@pytest.mark.parametrize("tokens", [8, 9])
def test_provider_checks_reported_budget_before_returning_response(monkeypatch, method, tokens):
    provider = HttpProvider("http://fixture/v1")
    response = {"usage": {"completion_tokens": tokens}, "choices": []}
    monkeypatch.setattr(provider, "request_json", lambda *_args, **_kwargs: response)

    if tokens > 8:
        with pytest.raises(ProviderError, match="max_tokens"):
            getattr(provider, method)({"max_tokens": 8})
    else:
        assert getattr(provider, method)({"max_tokens": 8}) is response
