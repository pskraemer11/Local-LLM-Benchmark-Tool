"""Central registry resolution and runtime derivation for benchmark models."""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from model_identity import match_registry_key

RegistryLoader = Callable[[], dict[str, Any]]

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_REGISTRY_PATH = _PROJECT_ROOT / "doc-git" / "model_registry.yaml"
_DEFAULT_TEMPLATE_ROOT = _PROJECT_ROOT / "doc-git" / "Jinja-Chat-Templates"
_TABBYAPI_CACHE_MODES = {
    "fp16": "FP16",
    "f16": "FP16",
    "q8_0": "8,8",
    "q8": "8,8",
    "q6": "6,6",
    "q4": "4,4",
}
_SUPPORTED_CACHE_TYPES = frozenset({"f32", "f16", "bf16", "q8_0", "q4_0", "q4_1", "iq4_nl", "q5_0", "q5_1"})
_CACHE_TYPE_ALIASES = {"fp16": "f16", "float16": "f16", "q4_nl": "iq4_nl"}


def load_registry(path: Path | None = None) -> dict[str, Any]:
    """Load ``model_registry.yaml`` as a plain mapping."""
    registry_path = path or _DEFAULT_REGISTRY_PATH
    if not registry_path.exists():
        return {}
    yaml = YAML()
    yaml.preserve_quotes = True
    try:
        with registry_path.open(encoding="utf-8") as handle:
            data = yaml.load(handle) or {}
    except (OSError, UnicodeDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


@dataclass(frozen=True)
class ResolvedRegistryEntry:
    """One registry entry resolved from a requested model key."""

    requested_key: str
    registry_key: str
    entry: dict[str, Any]

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        if isinstance(value, int) and value > 0:
            return value
        return None

    @property
    def quant(self) -> str | None:
        """Return the quant suffix from the registry key when present."""
        if "@" in self.registry_key:
            quant = self.registry_key.rsplit("@", 1)[1].strip()
            return quant.casefold() if quant else None
        quants = self.entry.get("quants")
        if isinstance(quants, str) and quants.strip():
            return quants.strip().casefold()
        first = quants[0] if isinstance(quants, list) and quants else None
        if isinstance(first, str) and first.strip():
            return first.strip().casefold()
        return None

    def native_context_length(self) -> int | None:
        """Return the technical max context from the registry/GGUF contract."""
        return self._positive_int(self.entry.get("max_context_length"))

    def benchmark_context_length(self) -> int | None:
        """Return the benchmark context length clipped to the technical max."""
        benchmark = self._positive_int(self.entry.get("context_length"))
        native = self.native_context_length()
        if benchmark is None:
            return native
        if native is not None and benchmark > native:
            return native
        return benchmark

    def technical_boundary_issues(self) -> list[str]:
        """Report technical-boundary violations between registry and GGUF limit."""
        benchmark = self._positive_int(self.entry.get("context_length"))
        native = self.native_context_length()
        if benchmark is not None and native is not None and benchmark > native:
            return [
                f"context_length {benchmark} exceeds native max_context_length {native}",
            ]
        return []

    def benchmark_runtime(self) -> dict[str, Any]:
        """Provider-neutral runtime data derived from the registry entry."""
        runtime: dict[str, Any] = {}
        native_context_length = self.native_context_length()
        if native_context_length is not None:
            runtime["native_context_length"] = native_context_length
        benchmark_context_length = self.benchmark_context_length()
        if benchmark_context_length is not None:
            runtime["context_length"] = benchmark_context_length
        for key in ("k_cache", "v_cache"):
            value = self.entry.get(key)
            if isinstance(value, str) and value.strip():
                runtime[key] = value.strip()
        unified_kv = self.entry.get("useUnifiedKvCache")
        if isinstance(unified_kv, bool):
            runtime["useUnifiedKvCache"] = unified_kv
        reasoning = self.entry.get("reasoning")
        if isinstance(reasoning, str) and reasoning.strip():
            runtime["reasoning"] = reasoning.strip()
        sampling = self.entry.get("sampling")
        if isinstance(sampling, dict) and sampling:
            runtime["sampling"] = copy.deepcopy(sampling)
        quant = self.quant
        if quant:
            runtime["quant"] = quant
        parallel = self.entry.get("parallel")
        if isinstance(parallel, int) and parallel > 0:
            runtime["parallel"] = parallel
        issues = self.technical_boundary_issues()
        if issues:
            runtime["technical_boundary_issues"] = issues
        return runtime

    def provider_runtime(self, provider_name: str, template_root: Path | None = None) -> dict[str, Any]:
        """Return provider-specific runtime overrides derived from the registry."""
        provider = provider_name.strip().casefold().replace("-", "_")
        runtime = self.benchmark_runtime()
        explicit = self.entry.get(provider)
        if not isinstance(explicit, dict):
            explicit = {}

        if provider == "tabbyapi":
            overrides: dict[str, Any] = {}
            context_length = runtime.get("context_length")
            if isinstance(context_length, int) and context_length > 0:
                overrides["max_seq_len"] = context_length
                overrides["cache_size"] = context_length
            cache_mode = self._tabbyapi_cache_mode(
                runtime.get("k_cache"),
                runtime.get("v_cache"),
            )
            if cache_mode:
                overrides["cache_mode"] = cache_mode
            # Registry-specific provider fields win over the derived defaults.
            overrides.update({key: value for key, value in explicit.items() if value is not None})
            return overrides

        if provider == "unsloth_server":
            overrides = {}
            context_length = runtime.get("context_length")
            if isinstance(context_length, int) and context_length > 0:
                overrides["context_length"] = context_length
            k_cache = self._normalize_cache_type(runtime.get("k_cache"))
            if k_cache is not None:
                overrides["cache_type_k"] = k_cache
            v_cache = self._normalize_cache_type(runtime.get("v_cache"))
            if v_cache is not None:
                overrides["cache_type_v"] = v_cache
            unified_kv = runtime.get("useUnifiedKvCache")
            if isinstance(unified_kv, bool):
                overrides["kv_unified"] = unified_kv
            if self.entry.get("template_policy") == "explicit_file":
                template_name = self.entry.get("template")
                if isinstance(template_name, str) and template_name.strip():
                    root = template_root or _DEFAULT_TEMPLATE_ROOT
                    overrides["chat_template_file"] = str(root / template_name.strip())
            # Registry-specific provider fields win over the derived defaults.
            overrides.update({key: value for key, value in explicit.items() if value is not None})
            return overrides

        return {key: value for key, value in explicit.items() if value is not None}

    @staticmethod
    def _tabbyapi_cache_mode(k_cache: Any, v_cache: Any) -> str | None:
        if not isinstance(k_cache, str) or not isinstance(v_cache, str):
            return None
        k_norm = k_cache.strip().casefold().replace("-", "_")
        v_norm = v_cache.strip().casefold().replace("-", "_")
        if not k_norm or k_norm != v_norm:
            return None
        return _TABBYAPI_CACHE_MODES.get(k_norm)

    @staticmethod
    def _normalize_cache_type(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip().casefold().replace("-", "_")
        normalized = _CACHE_TYPE_ALIASES.get(normalized, normalized)
        return normalized if normalized in _SUPPORTED_CACHE_TYPES else None


class ModelRegistry:
    """Central registry resolver with provider-runtime derivations."""

    def __init__(
        self,
        registry_loader: RegistryLoader | None = None,
        template_root: Path | None = None,
    ) -> None:
        self._registry_loader = registry_loader or load_registry
        self._template_root = template_root or _DEFAULT_TEMPLATE_ROOT

    def load(self) -> dict[str, Any]:
        """Return the latest registry mapping."""
        data = self._registry_loader()
        return data if isinstance(data, dict) else {}

    def resolve(self, model_key: str) -> ResolvedRegistryEntry | None:
        """Resolve a model key to a concrete registry entry."""
        data = self.load()
        if not data:
            return None
        keys = list(data)
        registry_key = match_registry_key(model_key, keys)
        if registry_key is None and "/" not in model_key and "_" in model_key:
            registry_key = match_registry_key(model_key.replace("_", "/", 1), keys)
        if registry_key is None:
            return None
        entry = data.get(registry_key)
        if not isinstance(entry, dict):
            return None
        return ResolvedRegistryEntry(
            requested_key=model_key,
            registry_key=registry_key,
            entry=entry,
        )

    def benchmark_runtime(self, model_key: str) -> dict[str, Any]:
        """Return provider-neutral runtime data for one model key."""
        resolved = self.resolve(model_key)
        return resolved.benchmark_runtime() if resolved else {}

    def provider_runtime(self, model_key: str, provider_name: str) -> dict[str, Any]:
        """Return provider-specific runtime overrides for one model key."""
        resolved = self.resolve(model_key)
        return (
            resolved.provider_runtime(provider_name, template_root=self._template_root)
            if resolved
            else {}
        )
