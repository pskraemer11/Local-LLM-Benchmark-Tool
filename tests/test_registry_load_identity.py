"""The lifecycle boundary must preserve the selected identity, not an API alias."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import run_benchmarks as runner
from model_registry import ModelRegistry
from providers.lmstudio_provider import LMStudioProvider

SELECTED = "publisher/model@q6_k"


def _model_info() -> dict[str, object]:
    return {
        "key": SELECTED,
        "registry_key": SELECTED,
        "model_identifier": "publisher/model",
        "display": "Model Q6_K",
        "quant": "Q6_K",
        "variants": [SELECTED, "publisher/model@q4_k_m"],
    }


def _loaded(identity: str, instance: str = "publisher/model") -> dict[str, str]:
    return {
        "identifier": instance,
        "model_identifier": identity,
        "display_name": "Model",
    }


@pytest.mark.parametrize("identity", ["publisher/model@q4_k_m", "publisher/model", "other/model@q6_k"])
def test_launcher_reloads_an_unverified_or_different_identity(monkeypatch: pytest.MonkeyPatch, identity: str) -> None:
    states = iter([_loaded(identity), _loaded(SELECTED, "new-instance")])
    monkeypatch.setattr(runner, "get_current_loaded_model", lambda: next(states))
    unload = Mock(return_value=True)
    load = Mock(return_value=(True, "new-instance"))
    monkeypatch.setattr(runner, "unload_all", unload)
    monkeypatch.setattr(runner, "load_model", load)
    monkeypatch.setattr(runner, "is_model_ready", lambda **_kwargs: True)

    assert runner._load_model(_model_info(), SELECTED, SimpleNamespace()) == "new-instance"
    unload.assert_called_once()
    load.assert_called_once_with(SELECTED)


def test_launcher_reuses_the_proven_identity_with_an_arbitrary_instance_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "get_current_loaded_model", lambda: _loaded(SELECTED, "session-42"))
    load = Mock()
    monkeypatch.setattr(runner, "load_model", load)
    monkeypatch.setattr(runner, "is_model_ready", lambda **_kwargs: True)

    assert runner._load_model(_model_info(), SELECTED, SimpleNamespace()) == "session-42"
    load.assert_not_called()


def test_launcher_rejects_wrong_identity_even_after_successful_load(monkeypatch: pytest.MonkeyPatch) -> None:
    states = iter([None, _loaded("publisher/model@q4_k_m", "new-instance")])
    monkeypatch.setattr(runner, "get_current_loaded_model", lambda: next(states))
    monkeypatch.setattr(runner, "load_model", lambda _key: (True, "new-instance"))
    monkeypatch.setattr(runner, "is_model_ready", lambda **_kwargs: True)
    info = _model_info()

    assert runner._load_model(info, SELECTED, SimpleNamespace()) is None
    assert "_api_model" not in info


def test_launcher_post_benchmark_check_rejects_substring_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    states = iter([_loaded("publisher/model@q4_k_m"), _loaded(SELECTED, "new-instance")])
    monkeypatch.setattr(runner, "get_current_loaded_model", lambda: next(states))
    monkeypatch.setattr(runner, "get_provider_capabilities", lambda: SimpleNamespace(can_report_current_model=True))
    monkeypatch.setattr(runner, "unload_all", lambda: True)
    load = Mock(return_value=(True, "new-instance"))
    monkeypatch.setattr(runner, "load_model", load)
    monkeypatch.setattr(runner, "is_model_ready", lambda **_kwargs: True)

    runner._ensure_model_still_loaded(SELECTED, SELECTED, "MATH-500")
    load.assert_called_once_with(SELECTED)


def test_main_loads_selected_catalog_variant_instead_of_the_base(monkeypatch: pytest.MonkeyPatch) -> None:
    info = _model_info()
    monkeypatch.setattr(runner, "_parse_args", lambda: (SimpleNamespace(thinking=False), None))
    monkeypatch.setattr(runner, "_acquire_single_instance_lock", lambda: None)
    monkeypatch.setattr(runner, "get_provider_context", lambda: SimpleNamespace(name="lmstudio"))
    monkeypatch.setattr(runner, "get_available_models", lambda **_kwargs: [info])
    monkeypatch.setattr(runner, "_resolve_models", lambda _args, available: available)
    monkeypatch.setattr(runner, "_resolve_benchmarks", lambda _args: [])
    monkeypatch.setattr(runner, "_validate_comparison_manifest_for_run", lambda *_args: None)
    monkeypatch.setattr(runner, "_start_proxy_if_needed", lambda *_args: None)
    monkeypatch.setattr(runner, "_check_registry_for_model", lambda *_args: False)
    load = Mock(side_effect=RuntimeError("stop before inference"))
    monkeypatch.setattr(runner, "_load_model", load)

    with pytest.raises(RuntimeError, match="stop before inference"):
        runner.main()
    assert load.call_args.args[1] == SELECTED


def test_native_catalog_base_does_not_prove_the_loaded_quantization() -> None:
    provider = LMStudioProvider(
        "http://127.0.0.1:1234/v1",
        rest_request=lambda *_args, **_kwargs: {
            "models": [{"key": "publisher/model", "loaded_instances": [{"id": "publisher/model"}]}]
        },
        registry_loader=lambda: {SELECTED: {}},
        subprocess_run=lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout='[{"modelKey":"publisher/model","selectedVariant":"publisher/model@q6_k"}]',
        ),
    )

    assert provider.current_model()["model_identifier"] == "publisher/model"


def test_native_loaded_quant_is_not_relabelled_as_another_registry_quant() -> None:
    provider = LMStudioProvider(
        "http://127.0.0.1:1234/v1",
        rest_request=lambda *_args, **_kwargs: {
            "models": [
                {
                    "key": "publisher/model",
                    "quantization": {"name": "Q4_K_M"},
                    "loaded_instances": [{"id": "publisher/model"}],
                }
            ]
        },
        registry_loader=lambda: {SELECTED: {}},
    )

    assert provider.current_model()["model_identifier"] == "publisher/model@q4_k_m"


@pytest.mark.parametrize(
    ("native_quant", "expected"),
    [(None, SELECTED), ({"name": "Q4_K_M"}, "")],
)
def test_native_variant_is_evidence_only_when_the_loaded_row_agrees(
    native_quant: dict[str, str] | None, expected: str
) -> None:
    provider = LMStudioProvider(
        "http://127.0.0.1:1234/v1",
        rest_request=lambda *_args, **_kwargs: {
            "models": [
                {
                    "key": "publisher/model",
                    "selected_variant": SELECTED,
                    "quantization": native_quant,
                    "loaded_instances": [{"id": "session-42"}],
                }
            ]
        },
    )
    assert provider.current_model()["model_identifier"] == expected


@pytest.mark.parametrize("status", ["loaded", "error"])
def test_provider_rejects_wrong_instance_despite_success_or_fallback(status: str) -> None:
    def request(endpoint: str, **_kwargs: object) -> dict[str, object]:
        if endpoint.endswith("/load"):
            return {"status": status, "instance_id": "publisher/model"}
        return {
            "models": [
                {
                    "key": "publisher/model",
                    "quantization": {"name": "Q4_K_M"},
                    "loaded_instances": [{"id": "publisher/model"}],
                }
            ]
        }

    provider = LMStudioProvider("http://127.0.0.1:1234/v1", rest_request=request)
    assert provider.load_model(SELECTED) == (False, None)


def test_provider_verifies_selected_quant_in_actual_native_response() -> None:
    calls: list[dict[str, object]] = []

    def request(endpoint: str, **kwargs: object) -> dict[str, object]:
        calls.append({"endpoint": endpoint, **kwargs})
        if endpoint.endswith("/load"):
            return {"status": "loaded", "instance_id": "session-42", "load_time_seconds": 1.0}
        return {
            "models": [
                {
                    "key": "publisher/model",
                    "quantization": {"name": "Q6_K"},
                    "loaded_instances": [{"id": "session-42"}],
                }
            ]
        }

    provider = LMStudioProvider("http://127.0.0.1:1234/v1", rest_request=request)
    assert provider.load_model(SELECTED) == (True, "session-42")
    assert calls[0]["data"]["model"] == SELECTED
    assert calls[1]["endpoint"] == "/api/v1/models"


@pytest.mark.parametrize("publisher", ["lmstudio-community", "foreign-publisher"])
def test_namespace_load_alias_requires_the_exact_registry_publisher(publisher: str) -> None:
    selected = "lmstudio-community/qwen/model@q6_k"
    load_alias = "qwen/model@q6_k"
    registry = ModelRegistry(lambda: {selected: {}})

    def request(endpoint: str, **_kwargs: object) -> dict[str, object]:
        if endpoint.endswith("/load"):
            return {"status": "loaded", "instance_id": "session-42"}
        return {
            "models": [
                {
                    "key": "qwen/model",
                    "publisher": publisher,
                    "quantization": {"name": "Q6_K"},
                    "selected_variant": load_alias,
                    "loaded_instances": [{"id": "session-42"}],
                }
            ]
        }

    provider = LMStudioProvider(
        "http://127.0.0.1:1234/v1",
        rest_request=request,
        runtime_loader=lambda key: registry.provider_runtime(key, "lmstudio"),
        registry_loader=lambda: registry.load(),
    )
    assert provider.load_model(load_alias) == (
        (True, "session-42") if publisher == "lmstudio-community" else (False, None)
    )


def test_namespace_registry_alias_alone_cannot_prove_the_requested_load_id() -> None:
    provider = LMStudioProvider(
        "http://127.0.0.1:1234/v1",
        runtime_loader=lambda _key: {"_registry_key": "lmstudio-community/qwen/model@q6_k"},
        rest_request=lambda endpoint, **_kwargs: (
            {"status": "loaded", "instance_id": "session-42"}
            if endpoint.endswith("/load")
            else {
                "models": [
                    {
                        "key": "lmstudio-community/qwen/model",
                        "quantization": {"name": "Q6_K"},
                        "loaded_instances": [{"id": "session-42"}],
                    }
                ]
            }
        ),
    )
    assert provider.load_model("qwen/model@q6_k") == (False, None)
