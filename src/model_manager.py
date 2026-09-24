#!/usr/bin/env python3
"""
Shared model-manager facade for the benchmark suite.
Imported by run_benchmarks.py AND custom_benchmark.py.

── Role in the system ─────────────────────────────────────────────
  The public functions remain stable for the launcher and benchmark
  subprocesses.  Provider-specific implementation is selected through
  ``LLM_PROVIDER`` for the new providers package; the default LM Studio path
  remains compatible with the existing test and runtime seams during the
  provider migration.

  1. run_benchmarks.py (Launcher)
     - CALLS load_model() and unload_all()
     - Model load/unload happens HERE ONLY
     - Uses get_current_loaded_model() for status checking

  2. custom_benchmark.py (Custom pipeline subprocess)
     - IMPORTS the constants (API_BASE, TIMEOUT_*)
     - NEVER calls load/unload (initiated by the launcher)
     - Uses is_api_available() as health-check (legacy)

── Provider-Zugriff ────────────────────────────────────────────────
  - LM Studio:   legacy lms CLI/REST lifecycle and OpenAI-compatible API
  - llama.cpp:   process-owned llama-server.exe plus OpenAI-compatible API
  - other:       provider-specific lifecycle/API implementations
  API_BASE remains a compatibility alias. New pipeline code uses
  get_api_base() so an explicit provider selected by the launcher is visible
  to every child pipeline.

── Wichtige Hinweise ───────────────────────────────────────────────
  - is_model_ready() wird vom Launcher nach load_model()
    aufgerufen, um die API-Bereitschaft aktiv zu prüfen (anstatt time.sleep(10)).
  - load_model() returns the EXACT model ID from the selected provider
    (e.g. "microsoft/phi-4@q6_k"), used by ALL pipelines as the
    model parameter in API calls.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from model_registry import ModelRegistry
from providers.base import ProviderContext
from utils.terminal import error, warn

if TYPE_CHECKING:
    from type_defs import AvailableModelInfo, LoadedModelInfo

def _configured_api_base() -> str:
    """Resolve a provider-specific base URL before the facade is imported."""
    provider = os.environ.get("LLM_PROVIDER", "lmstudio").strip().lower()
    explicit_base = os.environ.get("LLM_API_BASE")
    default_base = "http://127.0.0.1:1234/v1"
    if provider in {"tabbyapi"}:
        return os.environ.get("TABBYAPI_API_BASE") or explicit_base or "http://127.0.0.1:5000/v1"
    if provider in {"unsloth", "openai", "openai-compatible", "openai_compat"}:
        return (
            explicit_base
            if explicit_base and explicit_base != default_base
            else os.environ.get("UNSLOTH_API_BASE", default_base)
        )
    if provider in {"unsloth_server", "unsloth-local", "unsloth_local"}:
        return (
            explicit_base
            if explicit_base and explicit_base != default_base
            else os.environ.get("UNSLOTH_LOCAL_API_BASE", "http://127.0.0.1:8890/v1")
        )
    if provider in {"llama_cpp", "llama.cpp", "llama"}:
        return (
            explicit_base
            if explicit_base and explicit_base != default_base
            else os.environ.get("LLAMA_CPP_API_BASE", "http://127.0.0.1:8080/v1")
        )
    return os.environ.get("LMSTUDIO_API_BASE") or explicit_base or default_base


API_BASE = _configured_api_base()
# REST API base (without /v1 suffix) for model management endpoints
_REST_API_BASE = API_BASE.rsplit("/v1", 1)[0] if API_BASE.endswith("/v1") else API_BASE
TIMEOUT_CLI = 30
TIMEOUT_HTTP = 120
TIMEOUT_MODEL_READY = 120
TIMEOUT_LOAD_MODEL = 180
TIMEOUT_HEALTH_CHECK = 5
TIMEOUT_UNLOAD_WAIT = 2

# Magic strings (Code-Review 2026-07-18 §5.3): sentinel model name for
# the readiness health-check. Not a valid LM Studio model, so the server
# responds with HTTP 400 (no model loaded) - exactly the signal we
# need to know that the server is reachable but no model is loaded yet.
HEALTH_CHECK_SENTINEL_MODEL = "check"

SUPPORTED_PROVIDERS = {"lmstudio", "tabbyapi", "openai_compat", "unsloth_server", "llama_cpp"}

_PROVIDER_CONTEXT: ProviderContext | None = None
_PROVIDER_CONTEXT_SIGNATURE: tuple[str, ...] | None = None


def get_provider_name() -> str:
    """Return the configured provider name, defaulting to LM Studio."""
    name = os.environ.get("LLM_PROVIDER", "lmstudio").strip().lower()
    aliases = {
        "lms": "lmstudio",
        "openai": "openai_compat",
        "openai-compatible": "openai_compat",
        "unsloth": "openai_compat",
        "unsloth-local": "unsloth_server",
        "unsloth_local": "unsloth_server",
        "llama": "llama_cpp",
        "llama.cpp": "llama_cpp",
    }
    name = aliases.get(name, name)
    if name not in SUPPORTED_PROVIDERS:
        supported = ", ".join(sorted(SUPPORTED_PROVIDERS))
        raise ValueError(f"Unknown LLM_PROVIDER={name!r}; expected one of: {supported}")
    return name


def _provider_context_signature() -> tuple[str, ...]:
    """Return settings that require rebuilding the selected provider context."""
    provider = get_provider_name()
    names = (
        "LLM_API_BASE",
        "LMSTUDIO_API_BASE",
        "TABBYAPI_API_BASE",
        "UNSLOTH_API_BASE",
        "UNSLOTH_LOCAL_API_BASE",
        "LLAMA_CPP_API_BASE",
        "LLAMA_CPP_SERVER_EXE",
        "LLAMA_CPP_MODEL_ROOT",
        "GGUF_MODEL_ROOT",
        "LMSTUDIO_MODELS_DIR",
        "UNSLOTH_MODEL_ROOT",
        "UNSLOTH_SERVER_EXE",
    )
    return (provider, API_BASE, *(os.environ.get(name, "") for name in names))


def _create_provider() -> Any:
    """Create the configured provider on demand.

    Imports stay local so the legacy LM Studio path keeps its current import
    graph and tests can continue to patch ``model_manager`` seams.
    """
    from providers.llama_cpp_provider import LlamaCppProvider
    from providers.lmstudio_provider import LMStudioProvider
    from providers.openai_compat_provider import OpenAICompatProvider
    from providers.tabbyapi_provider import TabbyAPIProvider
    from providers.unsloth_server_provider import UnslothServerProvider

    provider_name = get_provider_name()
    if provider_name == "tabbyapi":
        return TabbyAPIProvider(
            API_BASE,
            runtime_loader=_tabbyapi_runtime_overrides,
            model_dir=os.environ.get("TABBYAPI_MODEL_DIR"),
        )
    if provider_name == "openai_compat":
        # "unsloth" keeps the shared OpenAI-compatible endpoint but enables
        # lifecycle extensions; the dedicated server process stays separate.
        lifecycle = os.environ.get("LLM_PROVIDER", "").strip().lower() == "unsloth"
        return OpenAICompatProvider(API_BASE, lifecycle=lifecycle)
    if provider_name == "unsloth_server":
        return UnslothServerProvider(
            API_BASE,
            model_root=(
                os.environ.get("GGUF_MODEL_ROOT")
                or os.environ.get("UNSLOTH_MODEL_ROOT")
                or os.environ.get("LMSTUDIO_MODELS_DIR")
            ),
            executable=os.environ.get("UNSLOTH_SERVER_EXE"),
            registry_loader=_load_registry_data,
            runtime_loader=_unsloth_server_runtime_overrides,
        )
    if provider_name == "llama_cpp":
        return LlamaCppProvider(
            API_BASE,
            model_root=(
                os.environ.get("LLAMA_CPP_MODEL_ROOT")
                or os.environ.get("GGUF_MODEL_ROOT")
                or os.environ.get("LMSTUDIO_MODELS_DIR")
            ),
            executable=os.environ.get("LLAMA_CPP_SERVER_EXE"),
            registry_loader=_load_registry_data,
            runtime_loader=_llama_cpp_runtime_overrides,
        )
    return LMStudioProvider(
        API_BASE,
        cli_timeout=TIMEOUT_CLI,
        rest_request=_rest_request,
        ensure_server=_is_lmstudio_running,
        registry_overrides=_registry_display_overrides,
        registry_loader=_load_registry_data,
        runtime_loader=_lmstudio_runtime_overrides,
        time_fn=time.time,
        sleep_fn=time.sleep,
        subprocess_run=subprocess.run,
    )


def get_provider_context() -> ProviderContext:
    """Return the explicit client context for the configured provider."""
    global _PROVIDER_CONTEXT, _PROVIDER_CONTEXT_SIGNATURE
    signature = _provider_context_signature()
    if _PROVIDER_CONTEXT is None or _PROVIDER_CONTEXT_SIGNATURE != signature:
        provider_name = get_provider_name()
        _PROVIDER_CONTEXT = ProviderContext(provider_name, _create_provider())
        _PROVIDER_CONTEXT_SIGNATURE = signature
    return _PROVIDER_CONTEXT


def get_provider() -> Any:
    """Return the selected provider client (legacy facade)."""
    # Keep the historical fresh-instance behavior for LM Studio compatibility
    # callers: its tests and integrations patch subprocess/REST seams per call.
    # Direct and other explicit providers retain the stable context client so
    # their lifecycle controller remains owned by one provider instance.
    if get_provider_name() == "lmstudio":
        return _create_provider()
    return get_provider_context().client


def get_provider_capabilities() -> Any:
    """Return capabilities of the configured provider without adding LMS calls."""
    return get_provider().capabilities


def get_api_base() -> str:
    """Return the current provider endpoint for child pipelines."""
    return cast("str", get_provider_context().base_url)


def configure_provider(provider: str | None = None, api_base: str | None = None) -> ProviderContext:
    """Apply explicit launcher provider options before discovery starts.

    The module-level ``API_BASE`` remains as a compatibility alias for older
    imports, while new callers can retrieve the refreshed endpoint through
    :func:`get_api_base`.
    """
    global API_BASE, _REST_API_BASE, _PROVIDER_CONTEXT, _PROVIDER_CONTEXT_SIGNATURE
    if provider:
        os.environ["LLM_PROVIDER"] = provider
    if api_base:
        os.environ["LLM_API_BASE"] = api_base
    API_BASE = _configured_api_base()
    _REST_API_BASE = API_BASE.rsplit("/v1", 1)[0] if API_BASE.endswith("/v1") else API_BASE
    _PROVIDER_CONTEXT = None
    _PROVIDER_CONTEXT_SIGNATURE = None
    return get_provider_context()


def _uses_legacy_lmstudio_path() -> bool:
    """Use the LM Studio provider while keeping its public facade stable."""
    return get_provider_name() == "lmstudio"


def has_assembled_system_prompt(model_identifier: str) -> bool | None:
    """Ask the LM Studio provider whether its JSON prompt artifact is populated."""
    if get_provider_name() != "lmstudio":
        return None
    provider = get_provider()
    checker = getattr(provider, "has_assembled_system_prompt", None)
    if callable(checker):
        return cast("bool | None", checker(model_identifier))
    return None


def _unsloth_server_runtime_overrides(model_identifier: str) -> dict[str, Any]:
    """Map provider-neutral registry runtime values to llama-server options."""
    return cast("dict[str, Any]", _registry_view().provider_runtime(model_identifier, "unsloth_server"))


def _llama_cpp_runtime_overrides(model_identifier: str) -> dict[str, Any]:
    """Map Registry values to direct llama-server arguments."""
    return cast("dict[str, Any]", _registry_view().provider_runtime(model_identifier, "llama_cpp"))


def _lmstudio_runtime_overrides(model_identifier: str) -> dict[str, Any]:
    """Map Registry-selected runtime values to LM Studio's native load API."""
    return cast("dict[str, Any]", _registry_view().provider_runtime(model_identifier, "lmstudio"))


# ── Legacy adapters ───────────────────────────────────────────────
# The concrete TabbyAPI implementation lives in providers/tabbyapi_provider.py.
# These names remain patchable for existing callers and tests.

def _tabbyapi_request(
    endpoint: str,
    method: str = "GET",
    data: dict[str, Any] | None = None,
    timeout: int = 30,
    read_body: bool = True,
) -> dict[str, Any] | None:
    from providers.tabbyapi_provider import TabbyAPIProvider

    return cast("dict[str, Any] | None", TabbyAPIProvider(API_BASE).request_json(
        endpoint,
        method=method,
        payload=data,
        timeout=timeout,
        read_body=read_body,
    ))


def _tabbyapi_loaded_name() -> str | None:
    from providers.tabbyapi_provider import TabbyAPIProvider

    current = TabbyAPIProvider(API_BASE).current_model()
    return current["model_identifier"] if current else None


def _tabbyapi_config_load_args() -> dict[str, Any]:
    from providers.tabbyapi_provider import TabbyAPIProvider

    return cast("dict[str, Any]", TabbyAPIProvider(API_BASE)._config_args())


def _tabbyapi_load_model(model_identifier: str, timeout: int = TIMEOUT_LOAD_MODEL) -> str | None:
    from providers.tabbyapi_provider import TabbyAPIProvider

    ok_loaded, loaded_name = TabbyAPIProvider(API_BASE).load_model(model_identifier, timeout=timeout)
    return loaded_name if ok_loaded else None


def _tabbyapi_unload(timeout: int = TIMEOUT_MODEL_READY) -> bool:
    from providers.tabbyapi_provider import TabbyAPIProvider

    return cast("bool", TabbyAPIProvider(API_BASE).unload_all(timeout=timeout))


# ── Pipeline-specific timeouts ──────────────────────────────────
# These values are imported by run_benchmarks.py and used as
# subprocess/scenario timeouts in each pipeline function.
# Some values (lmeval_base, evalplus_base) serve as base timeouts
# and are automatically doubled for reasoning models.
#
#   Key                     Default  Usage
#   ─────────────────────── ──────── ──────────────────────────────
#   custom_subprocess        3600    Subprocess timeout (DS1000, CoderEval)
#   evalplus_base             600    Base timeout codegen+evaluate (x2 for reasoning)
#   lmeval_base               600    Base timeout lm_eval (x2 for reasoning, x3 for MathQA)
#   mmlupro_per_subset        300    Timeout per MMLU-Pro subset
#   agentic_subprocess        3600    Total runtime timeout tool_eval_bench
#   agentic_scenario          600    Timeout per scenario (--timeout passed to tool_eval_bench)
# (Values in benchmark_config.py)


# Code-Review 2026-07-18 §6.2: central safe JSON loader. The LMS server
# is trusted, but using object_pairs_hook=OrderedDict ensures that
# all parsed objects preserve insertion order regardless of LMS
# version changes (CPython 3.7+ guarantees this for regular dicts,
# but a future JSON change with a `__getattr__`-style hook could
# cause surprises). The cost is one wrapper class per object.
def safe_json_loads(text: str) -> Any:
    """Parse JSON text into Python objects with deterministic ordering.

    Returns lists, OrderedDicts, and primitives. Top-level dicts are
    also OrderedDicts. Safe against LMS schema changes.
    """
    from collections import OrderedDict
    return json.loads(text, object_pairs_hook=OrderedDict)


def _rest_request(
    endpoint: str,
    method: str = "GET",
    data: dict[str, Any] | None = None,
    timeout: int = TIMEOUT_HTTP,
) -> dict[str, Any] | None:
    """Compatibility adapter for the provider HTTP transport."""
    from providers.base import HttpProvider

    return cast("dict[str, Any] | None", HttpProvider(_REST_API_BASE).request_json(
        endpoint,
        method=method,
        payload=data,
        timeout=timeout,
    ))


def is_api_available() -> bool:
    return cast("bool", get_provider().is_available(timeout=TIMEOUT_HEALTH_CHECK))


def get_current_loaded_model() -> LoadedModelInfo | None:
    return cast("LoadedModelInfo | None", get_provider().current_model())


def unload_all(timeout: int = TIMEOUT_MODEL_READY) -> bool:
    """Unload all models through the selected provider."""
    return cast("bool", get_provider().unload_all(timeout=timeout))


def has_unloaded_all_models() -> bool:
    """Compatibility alias for the provider-neutral unload operation."""
    return unload_all()


# ── Registry Helpers ─────────────────────────────────────────────────
_REGISTRY_CACHE: dict[str, Any] | None = None
_MODEL_REGISTRY: ModelRegistry | None = None


def _registry_view() -> ModelRegistry:
    """Return a cached registry resolver for the current process."""
    global _MODEL_REGISTRY
    if _MODEL_REGISTRY is None:
        _MODEL_REGISTRY = ModelRegistry(_load_registry_data)
    return _MODEL_REGISTRY


def _tabbyapi_runtime_overrides(model_identifier: str) -> dict[str, Any]:
    """Resolve safe TabbyAPI load arguments from the registry."""
    return cast("dict[str, Any]", _registry_view().provider_runtime(model_identifier, "tabbyapi"))

def _load_registry_data() -> dict[str, Any]:
    """Load and cache model_registry.yaml."""
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is not None:
        return _REGISTRY_CACHE
    from ruamel.yaml import YAML
    from ruamel.yaml.error import YAMLError
    rpath = Path(__file__).resolve().parent.parent / "doc-git" / "model_registry.yaml"
    if not rpath.exists():
        _REGISTRY_CACHE = {}
        return _REGISTRY_CACHE
    try:
        y = YAML()
        y.preserve_quotes = True
        with open(rpath, encoding="utf-8") as f:
            data = y.load(f) or {}
    except (YAMLError, OSError, UnicodeDecodeError) as e:
        warn(f"model_registry.yaml fehlerhaft: {e}")
        data = {}
    _REGISTRY_CACHE = cast("dict[str, Any]", data) if isinstance(data, dict) else {}
    return _REGISTRY_CACHE


def _registry_display_overrides() -> dict[str, str]:
    """Load model_registry.yaml and return {normalized_key: display_name}."""
    from model_identity import unique_normalized_index
    data = _load_registry_data()
    display_entries = {
        key: entry
        for key, entry in data.items()
        if isinstance(entry, dict) and isinstance(entry.get("display_name"), str)
    }
    overrides: dict[str, str] = {}
    for normalized, key in unique_normalized_index(list(display_entries)).items():
        display_name = display_entries[key].get("display_name")
        if isinstance(display_name, str):
            overrides[normalized] = display_name
    return overrides


def get_available_models(exclude_keywords: list[str] | None = None, registry_only: bool = False) -> list[AvailableModelInfo]:
    """List models through the selected provider."""
    models = get_provider().list_models(
        exclude_keywords=exclude_keywords,
        registry_only=registry_only,
    )
    return _attach_registry_identity(models, registry_only=registry_only)


def _attach_registry_identity(
    models: list[AvailableModelInfo],
    registry_only: bool = False,
) -> list[AvailableModelInfo]:
    """Attach the canonical Registry key without changing the API/load ID."""
    registry = _registry_view()
    data = registry.load()
    if not isinstance(data, dict):
        return [] if registry_only else models
    matched: list[AvailableModelInfo] = []
    for model in models:
        identifier = str(model.get("model_identifier") or model.get("key") or "")
        resolved = registry.resolve(identifier)
        if resolved is not None:
            model["registry_key"] = resolved.registry_key
            matched.append(model)
        elif not registry_only:
            matched.append(model)
    return matched


def parse_selection(choice: str, max_val: int) -> list[int] | None:
    """Parse user input like '1', '1,3,5', '1-5' into zero-based indices."""
    choice = choice.strip()
    if not choice:
        return None
    parts = choice.replace(" ", "").split(",")
    selected = set()
    for part in parts:
        if "-" in part:
            try:
                lo, hi = part.split("-", 1)
                lo_i, hi_i = int(lo), int(hi)
                if lo_i < 1 or hi_i > max_val or lo_i > hi_i:
                    return None
                for n in range(lo_i, hi_i + 1):
                    selected.add(n - 1)
            except ValueError:
                return None
        else:
            try:
                n = int(part)
                if n < 1 or n > max_val:
                    return None
                selected.add(n - 1)
            except ValueError:
                return None
    return sorted(selected) if selected else None


def _is_lmstudio_running() -> bool:
    """Compatibility adapter for LM Studio server startup and discovery."""
    from providers.lmstudio_provider import LMStudioProvider

    return cast("bool", LMStudioProvider(API_BASE).ensure_server())


# Code-Review 2026-07-18 §6.1: defensive model_identifier validation.
# All subprocess calls in this module already use list-form (not
# shell=True), so a malicious model_identifier cannot inject shell syntax.
# But we still validate the character set to fail early on bad data
# (typos, copy-paste errors, etc.) and to provide a clearer error
# message than the underlying subprocess errors.
# '?' ist LM Studios Platzhalter für nicht parsebare Quant-Namen
# (z.B. TQ2_0, ternär) - der modelKey ist dann z.B. "...@?".
_VALID_MODEL_KEY_RE = re.compile(r"^[A-Za-z0-9._/\-@:+=#?]{1,256}$")


def _validate_model_identifier(model_identifier: str) -> str:
    """Return model_identifier if it contains only safe characters; raise ValueError otherwise.

    Valid characters: ASCII letters/digits, `.`, `_`, `/`, `-`, `@`, `:`, `+`, `=`, `#`, `?`.
    Max length 256 (longer-than-realistic for any model name on HF).
    '?' tritt als LM-Studio-Platzhalter in modelKeys auf, deren Quant-Name
    nicht geparst werden kann.
    """
    if not isinstance(model_identifier, str) or not _VALID_MODEL_KEY_RE.match(model_identifier):
        raise ValueError(
            f"Invalid model_identifier: {model_identifier!r}. "
            f"Allowed: alphanumeric, '.', '_', '/', '-', '@', ':', '+', '=', '#', '?'; max 256 chars."
        )
    return model_identifier


def load_model(model_identifier: str, gpu_offload: float | None = None) -> tuple[bool, str | None]:
    """Load a model through the selected provider."""
    # Code-Review 2026-07-18 §6.1: validate input early.
    try:
        _validate_model_identifier(model_identifier)
    except ValueError as e:
        error(str(e))
        return False, None

    return cast("tuple[bool, str | None]", get_provider().load_model(model_identifier, gpu_offload=gpu_offload))


def load_model_via_lms(model_identifier: str, gpu_offload: float | None = None) -> tuple[bool, str | None]:
    """Compatibility alias for the provider-neutral load operation."""
    return load_model(model_identifier, gpu_offload=gpu_offload)


def is_model_ready(timeout: int = TIMEOUT_MODEL_READY) -> bool:
    """Wait for the LM Studio API to return a successful response (model loaded and serving).
    
    Unlike the previous implementation, this only considers HTTP 200 as "ready".
    Other errors (e.g. "No models loaded", 500, timeout) are retried until timeout.
    """
    return cast("bool", get_provider().wait_ready(timeout=timeout))
