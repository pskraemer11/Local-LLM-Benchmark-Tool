"""Contract tests for the phase-one provider boundary."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import model_manager
from providers.lmstudio_provider import LMStudioProvider
from providers.openai_compat_provider import OpenAICompatProvider
from providers.tabbyapi_provider import TabbyAPIProvider
from providers.unsloth_server_provider import UnslothServerProvider

if TYPE_CHECKING:
    from pathlib import Path


def test_provider_factory_selects_explicit_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_BASE", "http://127.0.0.1:5000/v1")
    monkeypatch.setenv("LLM_PROVIDER", "tabbyapi")
    assert isinstance(model_manager.get_provider(), TabbyAPIProvider)


def test_provider_factory_accepts_openai_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    assert isinstance(model_manager.get_provider(), OpenAICompatProvider)


def test_provider_factory_selects_process_owned_unsloth_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "unsloth_server")
    monkeypatch.setenv("UNSLOTH_LOCAL_API_BASE", "http://127.0.0.1:8890/v1")
    monkeypatch.setattr(model_manager, "API_BASE", model_manager._configured_api_base())
    provider = model_manager.get_provider()
    assert isinstance(provider, UnslothServerProvider)
    assert provider.base_url == "http://127.0.0.1:8890/v1"
    assert provider.capabilities.can_load_models is True
    assert provider.capabilities.can_unload_models is True


def test_unsloth_alias_uses_provider_specific_base_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "unsloth")
    monkeypatch.setenv("UNSLOTH_API_BASE", "http://127.0.0.1:8888/v1")
    monkeypatch.setenv("UNSLOTH_API_KEY", "unsloth-key")
    monkeypatch.setattr(model_manager, "API_BASE", model_manager._configured_api_base())
    assert model_manager.get_provider_name() == "openai_compat"
    provider = model_manager.get_provider()
    assert provider.base_url == "http://127.0.0.1:8888/v1"
    assert provider.headers["Authorization"] == "Bearer unsloth-key"
    assert provider.capabilities.can_load_models is True
    assert provider.capabilities.can_unload_models is True


def test_provider_factory_rejects_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "does-not-exist")
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        model_manager.get_provider_name()


def test_lmstudio_is_default_legacy_compatibility_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert model_manager.get_provider_name() == "lmstudio"
    assert model_manager._uses_legacy_lmstudio_path() is True
    assert isinstance(model_manager.get_provider(), LMStudioProvider)


def test_facade_delegates_model_listing_to_non_lms_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProvider:
        def list_models(
            self,
            exclude_keywords: list[str] | None = None,
            registry_only: bool = False,
        ) -> list[dict[str, str]]:
            del exclude_keywords, registry_only
            return [{"key": "tabby-model", "display": "Tabby model"}]

    monkeypatch.setenv("LLM_PROVIDER", "tabbyapi")
    monkeypatch.setattr(model_manager, "get_provider", lambda: FakeProvider())
    monkeypatch.setattr(model_manager.subprocess, "run", lambda *args, **kwargs: pytest.fail("lms must not run"))
    assert model_manager.get_available_models() == [{"key": "tabby-model", "display": "Tabby model"}]


def test_facade_delegates_model_load_to_non_lms_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProvider:
        def load_model(self, model_identifier: str, gpu_offload: float | None = None) -> tuple[bool, str]:
            assert gpu_offload == 0.8
            return True, model_identifier

    monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
    monkeypatch.setattr(model_manager, "get_provider", lambda: FakeProvider())
    assert model_manager.load_model_via_lms("model-a", gpu_offload=0.8) == (True, "model-a")


def test_model_manager_separates_tabby_api_name_from_registry_key(monkeypatch: pytest.MonkeyPatch) -> None:
    models = [{"key": "google_gemma-4-26b-a4b-it", "model_identifier": "google_gemma-4-26b-a4b-it"}]
    registry = {"unsloth/gemma-4-26b-a4b-it@iq3_s": {}}
    monkeypatch.setattr(model_manager, "_load_registry_data", lambda: registry)

    resolved = model_manager._attach_registry_identity(models)

    assert resolved[0]["model_identifier"] == "google_gemma-4-26b-a4b-it"
    assert resolved[0]["registry_key"] == "unsloth/gemma-4-26b-a4b-it@iq3_s"


def test_openai_compat_list_models_maps_openai_response(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatProvider("http://127.0.0.1:1234/v1")
    monkeypatch.setattr(
        provider,
        "request_json",
        lambda *args, **kwargs: {
            "data": [
                {"id": "model-a", "loaded": True, "context_length": 8192},
                {"id": "publisher/model-b", "loaded": False, "display_name": "Model B"},
            ],
        },
    )
    models = provider.list_models()
    assert [model["model_identifier"] for model in models] == ["model-a", "publisher/model-b"]
    assert models[1]["publisher"] == "publisher"
    assert models[0]["loaded"] is True
    assert models[0]["context_length"] == 8192
    assert models[1]["display"] == "Model B"


def test_openai_compat_uses_explicit_loaded_state(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatProvider("http://127.0.0.1:1234/v1")
    monkeypatch.setattr(provider, "list_models", lambda **kwargs: [
        {"model_identifier": "loaded-model", "display": "Loaded", "loaded": True, "context_length": 4096},
        {"model_identifier": "available-model", "display": "Available", "loaded": False},
    ])
    assert provider.current_model() == {
        "identifier": "loaded-model",
        "model_identifier": "loaded-model",
        "display_name": "Loaded",
        "status": "loaded",
        "context_length": 4096,
    }
    assert provider.load_model("available-model") == (False, None)


def test_unsloth_lifecycle_loads_and_polls_explicit_model_state(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatProvider(
        "http://127.0.0.1:8888/v1",
        lifecycle=True,
        lifecycle_timeout=1,
    )
    calls: list[tuple[str, str, dict | None]] = []
    model_checks = 0

    def request_json(endpoint: str, method: str = "GET", payload: dict | None = None, **kwargs: object) -> dict:
        nonlocal model_checks
        calls.append((endpoint, method, payload))
        if endpoint == "/models":
            model_checks += 1
            return {"data": [{"id": "model-a", "loaded": model_checks > 1}]}
        return {"status": "loaded"}

    monkeypatch.setattr(provider, "request_json", request_json)
    assert provider.load_model("model-a") == (True, "model-a")
    assert calls[1] == ("/load", "POST", {"model_path": "model-a"})


def test_unsloth_lifecycle_unloads_loaded_models(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatProvider("http://127.0.0.1:8888/v1", lifecycle=True)
    calls: list[tuple[str, str, dict | None]] = []
    model_checks = 0

    def request_json(endpoint: str, method: str = "GET", payload: dict | None = None, **kwargs: object) -> dict:
        nonlocal model_checks
        calls.append((endpoint, method, payload))
        if endpoint == "/models":
            model_checks += 1
            return {"data": [{"id": "model-a", "loaded": model_checks == 1}]}
        return {"status": "unloaded", "model": "model-a"}

    monkeypatch.setattr(provider, "request_json", request_json)
    assert provider.unload_all(timeout=1) is True
    assert calls[1] == ("/unload", "POST", {"model_path": "model-a"})


def test_openai_compat_preserves_provider_auth_header_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UNSLOTH_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "generic-key")
    monkeypatch.setenv("OPENAI_API_KEY", "provider-key")
    provider = OpenAICompatProvider("http://127.0.0.1:1234/v1")
    assert provider.headers["Authorization"] == "Bearer provider-key"


def test_openai_compat_does_not_infer_current_model_from_models_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OpenAICompatProvider("http://127.0.0.1:1234/v1")
    monkeypatch.setattr(provider, "list_models", lambda **kwargs: [{"model_identifier": "model-a"}])
    assert provider.current_model() is None


def test_openai_compat_load_is_only_an_availability_check(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatProvider("http://127.0.0.1:1234/v1")
    calls: list[str] = []
    monkeypatch.setattr(provider, "list_models", lambda **kwargs: calls.append("/models") or [
        {"model_identifier": "publisher/model-a"},
    ])
    assert provider.load_model("publisher/model-a") == (True, "publisher/model-a")
    assert calls == ["/models"]


def test_openai_compat_does_not_claim_unload_support() -> None:
    provider = OpenAICompatProvider("http://127.0.0.1:1234/v1")
    assert provider.capabilities.can_unload_models is False
    assert provider.unload_all() is False


def test_runner_rejects_unload_between_for_inference_only_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    import run_benchmarks

    monkeypatch.setattr(
        run_benchmarks,
        "get_provider_capabilities",
        lambda: SimpleNamespace(can_unload_models=False),
    )
    args = SimpleNamespace(unload_between=True)
    assert run_benchmarks._run_benchmarks_for_model(
        {"key": "model-a", "model_identifier": "model-a", "display": "Model A"},
        [],
        args,
        False,
        [],
    ) == []


def test_runner_uses_readiness_check_when_current_model_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import run_benchmarks

    monkeypatch.setattr(
        run_benchmarks,
        "get_provider_capabilities",
        lambda: SimpleNamespace(can_report_current_model=False),
    )
    monkeypatch.setattr(run_benchmarks, "is_model_ready", lambda timeout: True)
    monkeypatch.setattr(
        run_benchmarks,
        "load_model",
        lambda *args, **kwargs: pytest.fail("inference-only provider must not reload blindly"),
    )
    run_benchmarks._ensure_model_still_loaded("model-a", "model-a", "HellaSwag")


def test_non_lmstudio_prompt_check_is_short_circuited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "tabbyapi")
    monkeypatch.setattr(model_manager, "get_provider", lambda: pytest.fail("must not inspect LM Studio JSON"))

    assert model_manager.has_assembled_system_prompt("model-a") is None


def test_lmstudio_provider_reports_prompt_artifact_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from providers.lmstudio_provider import LMStudioProvider

    json_path = tmp_path / "gpt-oss-20b.json"
    json_path.write_text(
        """
        {
          "operation": {
            "fields": [
              {"key": "llm.prediction.systemPrompt", "value": "assembled"}
            ]
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    config_entries = [{"dir_name": "gpt-oss-20b", "json_path": json_path}]
    monkeypatch.setattr(
        "assemble_blueprint.read_lms_configs",
        lambda *args, **kwargs: config_entries,
    )
    monkeypatch.setattr(
        "assemble_blueprint.normalize_model_name",
        lambda value: str(value).lower().split("/", 1)[-1].split("@", 1)[0],
    )

    provider = LMStudioProvider("http://127.0.0.1:1234/v1")
    assert provider.has_assembled_system_prompt("openai/gpt-oss-20b@mxfp4") is True

    json_path.write_text(
        """
        {
          "operation": {
            "fields": [
              {"key": "llm.prediction.systemPrompt", "value": "   "}
            ]
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    assert provider.has_assembled_system_prompt("openai/gpt-oss-20b@mxfp4") is False


def test_inference_contract_exposes_chat_and_text_completions(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatProvider("http://127.0.0.1:1234/v1")
    calls: list[tuple[str, str, dict]] = []

    def request_json(endpoint: str, method: str = "GET", payload: dict | None = None, **kwargs: object) -> dict:
        calls.append((endpoint, method, payload or {}))
        return {"ok": True}

    monkeypatch.setattr(provider, "request_json", request_json)
    assert provider.chat_completions({"messages": []}) == {"ok": True}
    assert provider.completions({"prompt": "ping"}) == {"ok": True}
    assert calls == [
        ("/chat/completions", "POST", {"messages": []}),
        ("/completions", "POST", {"prompt": "ping"}),
    ]


def test_tabbyapi_load_sends_provider_specific_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = TabbyAPIProvider(
        "http://127.0.0.1:5000/v1",
        config_loader=lambda: {"cache_size": 8192, "max_seq_len": 16384},
    )
    calls: list[tuple[str, str, dict | None]] = []

    def request_json(endpoint: str, method: str = "GET", payload: dict | None = None, **kwargs: object) -> dict:
        calls.append((endpoint, method, payload))
        if endpoint == "/model":
            return {}
        return {}

    monkeypatch.setattr(provider, "request_json", request_json)
    monkeypatch.setenv("TABBYAPI_LOAD_TIMEOUT", "0")
    ok, model_id = provider.load_model("model-a")
    assert (ok, model_id) == (False, None)
    assert calls[0][0] == "/model"
    assert calls[1][0] == "/model/load"
    assert calls[1][1] == "POST"
    assert calls[1][2] == {"model_name": "model-a", "cache_size": 8192, "max_seq_len": 16384}


def test_tabbyapi_separates_inference_and_admin_headers() -> None:
    provider = TabbyAPIProvider(
        "http://127.0.0.1:5000/v1",
        api_key="inference-secret",
        admin_key="admin-secret",
    )
    assert provider.headers["Authorization"] == "Bearer inference-secret"
    assert provider._admin_headers["Authorization"] == "Bearer admin-secret"


def test_tabbyapi_current_model_reads_nested_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = TabbyAPIProvider("http://127.0.0.1:5000/v1", model_dir="C:/tabby/models")
    monkeypatch.setattr(
        provider,
        "request_json",
        lambda *args, **kwargs: {
            "id": "model-folder",
            "parameters": {"max_seq_len": 32768, "cache_mode": "Q4"},
        },
    )
    current = provider.current_model()
    assert current is not None
    assert current["identifier"] == "model-folder"
    assert current["api_model_id"] == "model-folder"
    assert current["context_length"] == 32768
    assert current["model_path"].replace("\\", "/") == "C:/tabby/models/model-folder"


def test_tabbyapi_runtime_values_override_config_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = TabbyAPIProvider(
        "http://127.0.0.1:5000/v1",
        config_loader=lambda: {"cache_size": 8192, "max_seq_len": 16384, "cache_mode": "Q4"},
        runtime_loader=lambda model: {"cache_size": 32768, "max_seq_len": 32768, "cache_mode": "4,4"},
    )
    calls: list[tuple[str, dict, dict]] = []
    model_checks = 0

    def request_json(endpoint: str, method: str = "GET", payload: dict | None = None, **kwargs: object) -> dict | None:
        nonlocal model_checks
        calls.append((endpoint, payload or {}, kwargs))
        if endpoint == "/model":
            model_checks += 1
            if model_checks == 1:
                return None
            return {"id": "model-a", "parameters": {"max_seq_len": 32768}}
        return {}

    monkeypatch.setattr(provider, "request_json", request_json)
    ok, model_id = provider.load_model("model-a")
    assert (ok, model_id) == (True, "model-a")
    assert calls[0][0] == "/model"
    assert calls[1][0] == "/model/load"
    assert calls[1][1] == {
        "model_name": "model-a",
        "cache_size": 32768,
        "max_seq_len": 32768,
        "cache_mode": "4,4",
    }
    assert calls[1][2]["read_body"] is False


def test_tabbyapi_unload_is_idempotent_when_no_model_is_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = TabbyAPIProvider("http://127.0.0.1:5000/v1")
    calls: list[str] = []

    def request_json(endpoint: str, **kwargs: object) -> dict | None:
        calls.append(endpoint)
        return None if endpoint == "/model" else {}

    monkeypatch.setattr(provider, "request_json", request_json)
    assert provider.unload_all() is True
    assert calls == ["/model", "/models"]


def test_tabbyapi_unload_does_not_parse_null_success_body(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = TabbyAPIProvider("http://127.0.0.1:5000/v1")
    calls: list[tuple[str, dict[str, object]]] = []
    model_checks = 0

    def request_json(endpoint: str, **kwargs: object) -> dict[str, object] | None:
        nonlocal model_checks
        calls.append((endpoint, kwargs))
        if endpoint == "/model":
            model_checks += 1
            return {"id": "model-a"} if model_checks == 1 else None
        return {}

    monkeypatch.setattr(provider, "request_json", request_json)
    assert provider.unload_all(timeout=1) is True
    assert calls[1][0] == "/model/unload"
    assert calls[1][1]["read_body"] is False
