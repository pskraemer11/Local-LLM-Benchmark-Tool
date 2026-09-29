"""Runtime context is the requested load contract, not the architecture maximum."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

import run_benchmarks as runner
from model_registry import ModelRegistry
from providers.lmstudio_provider import LMStudioProvider

IDENTITY = "publisher/model@q6_k"


def _native_models(context: object = 32768) -> dict[str, Any]:
    return {
        "models": [
            {
                "key": "publisher/model",
                "quantization": {"name": "Q6_K"},
                "max_context_length": 262144,
                "loaded_instances": [{"id": "session-42", "config": {"context_length": context}}],
            }
        ]
    }


@pytest.mark.parametrize("requested,maximum,expected", [(32768, 262144, 32768), (65536, 16384, 16384)])
def test_lms_runtime_derives_the_same_clipped_context_as_other_providers(
    requested: int, maximum: int, expected: int
) -> None:
    registry = ModelRegistry(lambda: {IDENTITY: {"context_length": requested, "max_context_length": maximum}})
    assert registry.provider_runtime(IDENTITY, "lmstudio")["context_length"] == expected
    assert registry.provider_runtime(IDENTITY, "llama_cpp")["context_length"] == expected


def test_lms_provider_override_cannot_exceed_the_native_limit() -> None:
    registry = ModelRegistry(
        lambda: {
            IDENTITY: {
                "context_length": 8192,
                "max_context_length": 16384,
                "lmstudio": {"context_length": 65536},
            }
        }
    )
    assert registry.provider_runtime(IDENTITY, "lmstudio")["context_length"] == 16384


def test_native_current_model_reports_instance_context_not_architecture_maximum() -> None:
    provider = LMStudioProvider("http://127.0.0.1:1234/v1", rest_request=lambda *_args, **_kwargs: _native_models(4096))
    assert provider.current_model()["context_length"] == 4096


@pytest.mark.parametrize("echo", [32768, 4096, "32768", True, 0])
def test_actual_lms_load_payload_and_echo_obey_the_context_contract(echo: object) -> None:
    calls: list[dict[str, Any]] = []
    registry = ModelRegistry(lambda: {IDENTITY: {"context_length": 32768, "max_context_length": 262144}})

    def request(endpoint: str, **kwargs: Any) -> dict[str, Any]:
        calls.append({"endpoint": endpoint, **kwargs})
        if endpoint.endswith("/load"):
            return {"status": "loaded", "instance_id": "session-42", "load_config": {"context_length": echo}}
        return _native_models()

    provider = LMStudioProvider(
        "http://127.0.0.1:1234/v1",
        rest_request=request,
        runtime_loader=lambda key: registry.provider_runtime(key, "lmstudio"),
    )
    assert provider.load_model(IDENTITY) == ((True, "session-42") if echo == 32768 else (False, None))
    assert calls[0]["data"]["context_length"] == 32768


@pytest.mark.parametrize("loaded_context", [32768, 4096, None, True, "32768"])
def test_missing_echo_requires_matching_loaded_instance_context(loaded_context: object) -> None:
    def request(endpoint: str, **_kwargs: Any) -> dict[str, Any]:
        if endpoint.endswith("/load"):
            return {"status": "loaded", "instance_id": "session-42"}
        return _native_models(loaded_context)

    provider = LMStudioProvider(
        "http://127.0.0.1:1234/v1",
        rest_request=request,
        runtime_loader=lambda _key: {"context_length": 32768},
    )
    assert provider.load_model(IDENTITY) == ((True, "session-42") if loaded_context == 32768 else (False, None))


def test_matching_identity_with_wrong_instance_context_is_not_reusable() -> None:
    provider = LMStudioProvider(
        "http://127.0.0.1:1234/v1",
        rest_request=lambda *_args, **_kwargs: _native_models(4096),
        runtime_loader=lambda _key: {"context_length": 32768},
    )
    current = provider.current_model()
    assert current["context_length"] == 4096
    assert current["runtime_matches"] is False


def test_matching_identity_is_reloaded_when_instance_context_is_wrong(monkeypatch: pytest.MonkeyPatch) -> None:
    states = iter(
        [
            {"model_identifier": IDENTITY, "identifier": "old-instance", "runtime_matches": False},
            {"model_identifier": IDENTITY, "identifier": "new-instance", "runtime_matches": True},
        ]
    )
    monkeypatch.setattr(runner, "get_current_loaded_model", lambda: next(states))
    monkeypatch.setattr(runner, "unload_all", lambda: True)
    monkeypatch.setattr(runner, "is_model_ready", lambda **_kwargs: True)
    load = Mock(return_value=(True, "new-instance"))
    monkeypatch.setattr(runner, "load_model", load)
    model = {"key": IDENTITY, "display": "Model"}

    assert runner._load_model(model, IDENTITY, SimpleNamespace()) == "new-instance"
    load.assert_called_once_with(IDENTITY)


def test_valid_echo_cannot_hide_a_conflicting_loaded_instance_context() -> None:
    def request(endpoint: str, **_kwargs: Any) -> dict[str, Any]:
        if endpoint.endswith("/load"):
            return {"status": "loaded", "instance_id": "session-42", "load_config": {"context_length": 32768}}
        return _native_models(4096)

    provider = LMStudioProvider(
        "http://127.0.0.1:1234/v1",
        rest_request=request,
        runtime_loader=lambda _key: {"context_length": 32768},
    )
    assert provider.load_model(IDENTITY) == (False, None)


def test_native_limit_clamps_context_returned_by_a_runtime_adapter() -> None:
    calls: list[dict[str, Any]] = []

    def request(endpoint: str, **kwargs: Any) -> dict[str, Any]:
        calls.append({"endpoint": endpoint, **kwargs})
        if endpoint.endswith("/load"):
            return {"status": "loaded", "instance_id": "session-42"}
        return _native_models(16384)

    provider = LMStudioProvider(
        "http://127.0.0.1:1234/v1",
        rest_request=request,
        runtime_loader=lambda _key: {"context_length": 65536, "native_context_length": 16384},
    )
    assert provider.load_model(IDENTITY) == (True, "session-42")
    assert calls[0]["data"]["context_length"] == 16384
