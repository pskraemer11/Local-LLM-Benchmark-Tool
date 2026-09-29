"""LM Studio provider for native lifecycle and OpenAI-compatible inference."""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from benchmark_config import (
    guess_quant_from_filename,
    is_blacklisted_model_name,
    is_support_model_record,
)
from inventory import IdentityLink, RuntimeBinding
from model_identity import (
    UniqueMatch,
    canonicalize_source_identity,
    decompose_model_identity,
    normalize_model_reference,
    resolve_registry_match,
    same_model_identity,
)
from quantization import normalize_quant
from runtime_policy import resolve_context_length
from utils.terminal import error, info, ok, warn

from .base import HttpProvider, ProviderCapabilities

RestRequest = Callable[..., dict[str, Any] | None]
SubprocessRun = Callable[..., Any]
RegistryOverrides = Callable[[], dict[str, str]]
RegistryLoader = Callable[[], dict[str, Any]]
RuntimeLoader = Callable[[str], Mapping[str, Any] | None]

# Names from the concrete LMS config contract. They are accepted only as
# returned evidence; the native REST load endpoint has no such inputs.
_SPECULATIVE_FIELDS = {
    "draft_mtp": "draftMtp",
    "draft_simple": "draftSimple",
    "draft_dflash_sidecar": "draftDflashSidecar",
    "draft_dspark_sidecar": "draftDsparkSidecar",
    "draft_mtp_sidecar": "draftMtpSidecar",
    "draft_model_reference": "draftModel",
    "draft_n_max": "draftMaxTokens",
    "draft_n_min": "draftMinTokens",
    "draft_p_min": "draftMinContinueProbability",
}


class LMStudioProvider(HttpProvider):
    """LM Studio's native lifecycle plus OpenAI-compatible inference.

    The optional callbacks are compatibility adapters supplied by
    model_manager.py during the phase-two migration.  They keep existing
    callers and tests patchable while the implementation lives here.
    """

    capabilities = ProviderCapabilities(
        can_list_models=True,
        can_load_models=True,
        can_unload_models=True,
        can_report_current_model=True,
    )

    def __init__(
        self,
        base_url: str,
        cli_timeout: int = 30,
        rest_request: RestRequest | None = None,
        ensure_server: Callable[[], bool] | None = None,
        registry_overrides: RegistryOverrides | None = None,
        registry_loader: RegistryLoader | None = None,
        runtime_loader: RuntimeLoader | None = None,
        time_fn: Callable[[], float] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        subprocess_run: SubprocessRun | None = None,
    ) -> None:
        auth_token = os.environ.get("LMS_OpenAI_AUTH_TOKEN") or os.environ.get("LMS_OPENAI_AUTH_TOKEN")
        headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else None
        super().__init__(base_url, headers=headers)
        self.cli_timeout = cli_timeout
        self.rest_base_url = base_url[:-3] if base_url.endswith("/v1") else base_url
        self._rest_request = rest_request
        self._ensure_server_callback = ensure_server
        self._registry_overrides = registry_overrides
        self._registry_loader = registry_loader
        self._runtime_loader = runtime_loader
        self._time = time_fn or time.time
        self._sleep = sleep_fn or time.sleep
        self._subprocess_run = subprocess_run or subprocess.run

    def _run_lms(self, *args: str) -> Any | None:
        try:
            result = self._subprocess_run(
                ["lms", *args],
                capture_output=True,
                text=True,
                timeout=self.cli_timeout,
                encoding="utf-8",
                errors="replace",
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        try:
            return json.loads(result.stdout)
        except (TypeError, ValueError):
            return None

    def _native_request(
        self,
        endpoint: str,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        timeout: int = 120,
    ) -> dict[str, Any] | None:
        if self._rest_request is not None:
            return self._rest_request(endpoint, method=method, data=payload, timeout=timeout)
        original_url = self.base_url
        self.base_url = self.rest_base_url
        try:
            response = self.request_json(endpoint, method=method, payload=payload, timeout=timeout)
        finally:
            self.base_url = original_url
        return response if isinstance(response, dict) else None

    def list_models(
        self,
        exclude_keywords: list[str] | None = None,
        registry_only: bool = False,
    ) -> list[dict[str, Any]]:
        """Query installed models via lms ls --json."""
        data = self._run_lms("ls", "--json")
        if data is None:
            error("lms.exe not found. Is LM Studio installed?")
            return []
        items = data if isinstance(data, list) else data.values() if isinstance(data, dict) else []
        models: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            base_key = item.get("modelKey", "")
            if not base_key or is_support_model_record(item):
                continue
            quant = item.get("quantization", {}) or {}
            quant_name = quant.get("name", "") if isinstance(quant, dict) else ""
            quant_name = str(quant_name or "").strip()
            if quant_name.casefold() in {"?", "unknown", "none"}:
                quant_name = ""
            selected_variant = item.get("selectedVariant") or ""
            selected_variant = str(selected_variant).strip()
            selected_quant = selected_variant.rsplit("@", 1)[1] if "@" in selected_variant else ""
            if selected_quant.casefold() not in {"", "?", "unknown", "none"}:
                # A concrete selected variant is more specific than a stale or
                # absent quantization field in lms ls --json.
                quant_name = selected_quant
            if not quant_name:
                filename = str(item.get("path") or "").replace("\\", "/").rsplit("/", 1)[-1]
                quant_name = guess_quant_from_filename(filename)

            has_concrete_variant = bool(selected_variant) and not selected_variant.casefold().endswith("@?")
            if has_concrete_variant and selected_variant != base_key:
                unique_key = selected_variant
            else:
                # LM Studio can expose a placeholder modelKey/selectedVariant
                # such as ``model@?`` while its concrete GGUF path contains
                # the authoritative quant. Never turn only the last filename
                # token (e.g. ``g64``) into an identity.
                identity_base = str(base_key)
                if identity_base.casefold().endswith("@?"):
                    identity_base = identity_base[:-2]
                unique_key = (
                    identity_base
                    if not quant_name or identity_base.casefold().endswith(f"@{quant_name}".casefold())
                    else f"{identity_base}@{quant_name}"
                )
            raw_display = item.get("displayName", base_key)
            display = raw_display if isinstance(raw_display, str) else str(base_key)
            if quant_name:
                if "@" in display:
                    display = display.split("@", 1)[0]
                else:
                    display = display.removesuffix(" " + quant_name.replace("_", " "))
                display = f"{display}@{quant_name}"
            size_bytes = item.get("sizeBytes", 0) or 0
            models.append(
                {
                    "key": unique_key,
                    "model_identifier": base_key,
                    "display": display,
                    "variant": selected_variant or base_key,
                    "quant": quant_name,
                    "variants": item.get("variants") or [],
                    "identifier": item.get("indexedModelIdentifier", base_key),
                    "params": item.get("paramsString", ""),
                    "publisher": item.get("publisher", ""),
                    "vram_gb": round(size_bytes / 1e9, 2) if size_bytes else "",
                    "modelKey": base_key,
                }
            )
        if not models:
            return []

        overrides = self._registry_overrides() if self._registry_overrides else {}
        if overrides:
            from assemble_blueprint import normalize_model_name

            for model in models:
                normalized_key = normalize_model_name(model["model_identifier"])
                if normalized_key in overrides:
                    model["display"] = overrides[normalized_key]
                    if model["quant"]:
                        model["display"] = f"{model['display']}@{model['quant']}"
        if exclude_keywords:
            models = [
                model
                for model in models
                if not any(
                    is_blacklisted_model_name(model[field], exclude_keywords)
                    for field in ("key", "display")
                )
            ]
        if registry_only:
            from assemble_blueprint import normalize_model_name

            registry_data = self._registry_loader() if self._registry_loader else {}
            registry_base_keys = {
                normalize_model_name(key).split("@", 1)[0]
                for key, value in registry_data.items()
                if isinstance(value, dict)
            }
            filtered = [
                model
                for model in models
                if normalize_model_name(model["model_identifier"]).split("@", 1)[0] in registry_base_keys
            ]
            missing = len(models) - len(filtered)
            if missing:
                warn(f"{missing} Modelle nicht in Registry - mit `python registry_tool.py sync` hinzufügen. Ignoriert.")
            models = filtered
        return models

    def is_available(self, timeout: int = 5) -> bool:
        try:
            return self.request_json("/models", timeout=timeout) is not None
        except Exception:
            return False

    def current_model(self) -> dict[str, Any] | None:
        native_data = self._native_request("/api/v1/models")
        if isinstance(native_data, dict) and isinstance(native_data.get("models"), list):
            # This endpoint owns loaded_instances. An empty native result is
            # authoritative too; do not let a stale ``lms ps`` row resurrect
            # a model that the server has already unloaded.
            return self._current_model_from_native_api(native_data)

        data = self._run_lms("ps", "--json")
        if not data:
            return None
        try:
            entry = data[0]
            return self._with_runtime_context({
                "identifier": entry.get("identifier", ""),
                "model_identifier": self._registry_identity_for_native_model(
                    entry, str(entry.get("modelKey") or "")
                ),
                "display_name": entry.get("displayName", ""),
                "status": entry.get("status", ""),
                "context_length": entry.get("contextLength"),
            })
        except (KeyError, TypeError, IndexError):
            return None

    def _current_model_from_native_api(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Read LMS's authoritative loaded-instance API.

        The CLI can return an empty process list while the REST API still has
        an active instance. Treating that as unloaded made the benchmark
        launcher load the same model a second time after an inference task.
        """
        rows = data.get("models", [])
        if not isinstance(rows, list):
            return None

        for row in rows:
            if not isinstance(row, dict):
                continue
            instances = row.get("loaded_instances", [])
            if not isinstance(instances, list) or not instances:
                continue
            instance = next(
                (candidate for candidate in reversed(instances) if isinstance(candidate, dict)),
                None,
            )
            if instance is None:
                continue

            api_key = str(row.get("key") or "")
            model_identifier = self._registry_identity_for_native_model(row, api_key)
            config = instance.get("config")
            return self._with_runtime_context({
                "identifier": str(instance.get("id") or api_key),
                "model_identifier": model_identifier,
                "display_name": str(row.get("display_name") or api_key),
                "status": "loaded",
                "context_length": config.get("context_length") if isinstance(config, dict) else None,
            }, load_config=config)
        return None

    @staticmethod
    def _context_matches(value: Any, expected: int) -> bool:
        """An echoed/loaded context must be a positive integer, never a bool."""
        return isinstance(value, int) and not isinstance(value, bool) and value > 0 and value == expected

    def _with_runtime_context(
        self, current: dict[str, Any], *, load_config: Any = None
    ) -> dict[str, Any]:
        """Expose whether this already-loaded instance meets Registry policy."""
        runtime = self._runtime_loader(current["model_identifier"]) if self._runtime_loader is not None else None
        expected = runtime.get("context_length") if runtime else None
        if runtime is not None and expected is not None:
            if isinstance(expected, int) and not isinstance(expected, bool) and expected > 0:
                expected = resolve_context_length({
                    "context_length": expected,
                    "max_context_length": runtime.get("max_context_length") or runtime.get("native_context_length"),
                })
            current["runtime_matches"] = (
                isinstance(expected, int)
                and not isinstance(expected, bool)
                and expected > 0
                and self._context_matches(current.get("context_length"), expected)
            )
        speculative_expected = runtime.get("_speculative_expected") if runtime else None
        if speculative_expected is not None:
            current["runtime_matches"] = current.get("runtime_matches", True) and self._speculative_matches(
                speculative_expected, self._speculative_values(load_config)
            )
        return current

    @staticmethod
    def _speculative_values(config: Any) -> dict[str, Any]:
        """Extract recognized effective fields, retaining conflicting aliases."""
        if not isinstance(config, Mapping):
            return {}
        values: dict[str, Any] = {}
        for key, native_key in _SPECULATIVE_FIELDS.items():
            dotted_key = f"llm.load.llama.speculativeDecoding.{native_key}"
            observed = [config[field] for field in (key, dotted_key) if field in config]
            if observed:
                # An invalid sentinel makes contradictory aliases fail the
                # typed comparison, instead of silently choosing one value.
                values[key] = observed[0] if all(
                    type(value) is type(observed[0]) and value == observed[0] for value in observed
                ) else object()
        return values

    @staticmethod
    def _speculative_value_matches(key: str, actual: Any, expected: Any) -> bool:
        if isinstance(expected, bool):
            return isinstance(actual, bool) and actual is expected
        if key == "draft_model_reference":
            if not isinstance(actual, str) or not isinstance(expected, str):
                return False
            if not expected:
                return actual == ""
            # A helper is either a complete identity or the exact physical
            # artifact path. Never substitute a basename or missing quant.
            if Path(expected).is_absolute():
                return Path(actual).is_absolute() and os.path.normcase(os.path.normpath(actual)) == os.path.normcase(
                    os.path.normpath(expected)
                )
            return all(decompose_model_identity(expected)) and same_model_identity(actual, expected)
        return not isinstance(actual, bool) and type(actual) is type(expected) and actual == expected

    @classmethod
    def _speculative_matches(cls, expected: Any, *configs: Mapping[str, Any]) -> bool:
        """Require complete effective evidence and reject every contradiction.

        Saved user defaults are intentionally excluded: they can differ from
        the configuration of an existing or newly returned loaded instance.
        """
        if expected is None:
            return True
        if not isinstance(expected, Mapping) or not expected:
            return False
        required = {
            "draft_mtp", "draft_simple", "draft_dflash_sidecar", "draft_dspark_sidecar",
            "draft_mtp_sidecar", "draft_model_reference",
        }
        if not required.issubset(expected):
            return False
        for key, value in expected.items():
            if key not in _SPECULATIVE_FIELDS:
                return False
            observed = [config[key] for config in configs if key in config]
            if not observed or not all(cls._speculative_value_matches(key, actual, value) for actual in observed):
                return False
        return True

    def _registry_identity_for_native_model(self, native_model: dict[str, Any], api_key: str) -> str:
        """Canonicalize identity evidence from the loaded row itself.

        An installed catalog entry proves which artifacts are available, but
        cannot prove which quantization a base-key loaded instance uses.
        Consequently neither registry uniqueness nor catalog iteration may
        supply a missing identity component at this boundary.
        """
        publisher = str(native_model.get("publisher") or "")
        quantization = native_model.get("quantization")
        quant = str(quantization.get("name") or "") if isinstance(quantization, dict) else ""
        try:
            registry = self._registry_loader() if self._registry_loader else {}
            reference = str(native_model.get("selected_variant") or native_model.get("selectedVariant") or api_key)
            base = canonicalize_source_identity(api_key, publisher=publisher).split("@", 1)[0]
            variant_base = canonicalize_source_identity(reference, publisher=publisher).split("@", 1)[0]
            if normalize_model_reference(base) != normalize_model_reference(variant_base):
                return ""
            embedded_quant = decompose_model_identity(reference)[2]
            api_quant = decompose_model_identity(api_key)[2]
            concrete_quants = {
                normalized
                for value in (quant, embedded_quant, api_quant)
                if (normalized := normalize_quant(value)) not in {"", "?", "unknown", "none"}
            }
            if len(concrete_quants) > 1:
                return ""
            proven_quant = next(iter(concrete_quants), "")
            canonical = canonicalize_source_identity(reference, publisher=publisher, quant=proven_quant)
            matches = [key for key in registry if same_model_identity(canonical, key)]
            return matches[0] if len(matches) == 1 else canonical
        except (ImportError, TypeError, ValueError):
            return api_key

    def _loaded_binding_for_identity(
        self,
        data: dict[str, Any] | None,
        requested: str,
        instance_id: str | None = None,
        *,
        registry_key: str | None = None,
    ) -> tuple[str, IdentityLink] | None:
        """Bind one exact loaded instance and its runtime to the selected identity."""
        if not isinstance(data, dict) or not isinstance(data.get("models"), list):
            return None
        selected_identity = registry_key or requested
        complete_request = all(decompose_model_identity(selected_identity))
        is_namespace_alias = False
        if registry_key is not None and not same_model_identity(requested, registry_key):
            alias_match = resolve_registry_match(requested, [registry_key])
            is_namespace_alias = (
                isinstance(alias_match, UniqueMatch)
                and alias_match.stage == "publisher-alias-namespace-exact"
            )
            if not is_namespace_alias:
                return None
        matches: list[tuple[str, IdentityLink]] = []
        for row in data["models"]:
            if not isinstance(row, dict):
                continue
            identity = self._registry_identity_for_native_model(row, str(row.get("key") or ""))
            link = IdentityLink(registry_key=identity)
            identity_matches = (
                same_model_identity(selected_identity, link.registry_key)
                if complete_request
                else normalize_model_reference(selected_identity) == normalize_model_reference(link.registry_key)
            )
            if not identity_matches:
                continue
            instances = row.get("loaded_instances", [])
            if not isinstance(instances, list):
                continue
            for instance in instances:
                candidate = str(instance.get("id") or "") if isinstance(instance, dict) else ""
                if candidate and (instance_id is None or candidate == instance_id):
                    if is_namespace_alias:
                        # An accepted namespace alias must also occur on this
                        # exact loaded row. A registry alias alone is never
                        # evidence that the selected publisher was loaded.
                        aliases = (row.get("key"), row.get("selected_variant"), row.get("selectedVariant"), candidate)
                        if not any(
                            normalize_model_reference(requested) == normalize_model_reference(str(alias or ""))
                            for alias in aliases
                        ):
                            continue
                    config = instance.get("config")
                    link = IdentityLink(
                        registry_key=link.registry_key,
                        runtime_bindings=(RuntimeBinding(
                            context_length=config.get("context_length") if isinstance(config, dict) else None,
                            speculative=tuple(self._speculative_values(config).items()),
                        ),),
                    )
                    matches.append((candidate, link))
        return matches[0] if len(matches) == 1 else None

    def has_assembled_system_prompt(self, model_identifier: str) -> bool | None:
        """Check whether the LM Studio JSON config already contains a prompt."""
        try:
            from assemble_blueprint import normalize_model_name, read_lms_configs
        except ImportError:
            return None

        cfg_root = Path.home() / ".lmstudio" / ".internal" / "user-concrete-model-default-config"
        cfgs = read_lms_configs(cfg_root)
        cfg_key = normalize_model_name(model_identifier)
        for cfg in cfgs:
            if normalize_model_name(cfg.get("dir_name", "")) != cfg_key:
                continue
            try:
                data = json.loads(Path(cfg["json_path"]).read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError, TypeError, ValueError, KeyError):
                return None
            sys_prompt = next(
                (
                    field.get("value", "")
                    for field in data.get("operation", {}).get("fields", [])
                    if isinstance(field, dict) and field.get("key") == "llm.prediction.systemPrompt"
                ),
                "",
            )
            return bool(str(sys_prompt).strip())
        return None

    def load_model(self, model_identifier: str, gpu_offload: float | None = None) -> tuple[bool, str | None]:
        info(f"Loading '{model_identifier}'...")
        payload: dict[str, Any] = {"model": model_identifier, "echo_load_config": True}
        if gpu_offload is not None:
            payload["gpu_offload"] = gpu_offload
        requested_context: int | None = None
        selected_identity: str | None = None
        speculative_expected: Any = None
        if self._runtime_loader is not None:
            runtime = self._runtime_loader(model_identifier) or {}
            speculative_expected = runtime.get("_speculative_expected")
            registry_key = runtime.get("_registry_key")
            if registry_key is not None:
                if not isinstance(registry_key, str) or not all(decompose_model_identity(registry_key)):
                    warn(f"Invalid Registry identity for '{model_identifier}'")
                    return False, None
                selected_identity = registry_key
            context_length = runtime.get("context_length")
            if context_length is not None:
                if not isinstance(context_length, int) or isinstance(context_length, bool) or context_length <= 0:
                    warn(f"Invalid Registry context for '{model_identifier}'")
                    return False, None
                requested_context = resolve_context_length({
                    "context_length": context_length,
                    "max_context_length": runtime.get("max_context_length") or runtime.get("native_context_length"),
                })
                payload["context_length"] = requested_context
            num_experts = runtime.get("num_experts")
            if isinstance(num_experts, int) and not isinstance(num_experts, bool) and num_experts > 0:
                # This is the selected runtime value, not the immutable
                # GGUF architectural maximum.
                payload["num_experts"] = num_experts
        for attempt in range(2):
            result = self._native_request("/api/v1/models/load", method="POST", payload=payload, timeout=180)
            if result is not None and result.get("status") == "loaded":
                instance_id = result.get("instance_id", model_identifier)
                binding = None
                if (
                    all(decompose_model_identity(model_identifier))
                    or selected_identity is not None
                    or requested_context is not None
                    or speculative_expected is not None
                ):
                    binding = self._loaded_binding_for_identity(
                        self._native_request("/api/v1/models"),
                        model_identifier,
                        str(instance_id),
                        registry_key=selected_identity,
                    )
                    if binding is None:
                        warn(f"Loaded instance does not prove the selected identity '{model_identifier}'")
                        return False, None
                    instance_id = binding[0]
                load_time = result.get("load_time_seconds", 0)
                load_config = result.get("load_config", {})
                if not isinstance(load_config, dict):
                    load_config = {}
                if requested_context is not None:
                    context_matches = binding is not None and self._context_matches(
                        binding[1].runtime_bindings[0].context_length, requested_context
                    ) and (
                        "context_length" not in load_config
                        or self._context_matches(load_config["context_length"], requested_context)
                    )
                    if not context_matches:
                        warn(f"Loaded context does not match requested {requested_context} for '{model_identifier}'")
                        return False, None
                if speculative_expected is not None and (
                    binding is None
                    or not self._speculative_matches(
                        speculative_expected,
                        self._speculative_values(load_config),
                        dict(binding[1].runtime_bindings[0].speculative),
                    )
                ):
                    warn(f"Loaded speculative configuration is unverified or conflicts with Registry policy for '{model_identifier}'")
                    return False, None
                ok(f"Loaded in {load_time:.1f}s (np={load_config.get('parallel', '?')})")
                info(f"Instance ID: {instance_id}")
                return True, instance_id
            if result is not None:
                binding = self._loaded_binding_for_identity(
                    self._native_request("/api/v1/models"), model_identifier, registry_key=selected_identity
                )
                if binding is not None and (
                    requested_context is None
                    or self._context_matches(binding[1].runtime_bindings[0].context_length, requested_context)
                ) and self._speculative_matches(
                    speculative_expected, dict(binding[1].runtime_bindings[0].speculative)
                ):
                    return True, binding[0]
                status = str(result.get("status", "unknown"))
                detail = result.get("error") or result.get("message") or status
                warn(f"LM Studio rejected model load for '{model_identifier}': {detail}")
                return False, None
            if attempt == 0:
                running = self._ensure_server_callback() if self._ensure_server_callback else self.ensure_server()
                if running:
                    warn("Load failed - retrying...")
                    self._sleep(3)
                    continue
                warn("LM Studio not running")
            warn(f"Load failed (attempt {attempt + 1}/2)")
            return False, None
        return False, None

    def unload_all(self, timeout: int = 120) -> bool:
        info("Unloading all models...")
        models_data = self._native_request("/api/v1/models")
        if models_data is None:
            warn("Could not fetch model list")
            return False
        loaded_instances = [
            instance.get("id")
            for model in models_data.get("models", [])
            for instance in model.get("loaded_instances", [])
            if instance.get("id")
        ]
        if not loaded_instances:
            ok("No models loaded")
            return True
        for instance_id in loaded_instances:
            result = self._native_request("/api/v1/models/unload", method="POST", payload={"instance_id": instance_id})
            if result is not None:
                ok(f"Unloaded {instance_id}")
            else:
                warn(f"Failed to unload {instance_id}")
        poll_count = min(15, max(1, timeout // 2))
        for _ in range(poll_count):
            self._sleep(2)
            models_data = self._native_request("/api/v1/models")
            if models_data is None:
                continue
            if sum(len(model.get("loaded_instances", [])) for model in models_data.get("models", [])) == 0:
                ok("Old model fully unloaded")
                return True
        warn("Could not confirm unload - continuing")
        return False

    def wait_ready(self, timeout: int = 120) -> bool:
        start = self._time()
        print("  [INFO] Waiting for model readiness", end="", flush=True)
        while self._time() - start < timeout:
            self._sleep(2)
            print(".", end="", flush=True)
            current = self.current_model()
            response = self.chat_completions(
                {
                    # The sentinel is useful when no CLI state is available,
                    # but a real loaded identifier is required for LM Studio
                    # instances that reject unknown model names.
                    "model": current.get("identifier", "check") if current else "check",
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
                timeout=5,
            )
            if response is not None:
                print(" ready")
                return True
        print(" TIMEOUT")
        warn("Model readiness timeout")
        return False

    def ensure_server(self) -> bool:
        if self.is_available(timeout=3):
            return True
        print("  [INFO] LM Studio-Server nicht erreichbar - versuche 'lms server start'...")
        try:
            result = self._subprocess_run(
                ["lms", "server", "start"],
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="replace",
            )
            self._sleep(5)
            if self.is_available(timeout=3):
                ok("LM Studio-Server gestartet via 'lms server start'")
                return True
            warn(f"'lms server start' brachte Server nicht hoch: {result.stderr.strip()[:120]}")
        except FileNotFoundError:
            warn("lms.exe nicht im PATH - versuche llmster.exe direkt")
        except subprocess.TimeoutExpired:
            warn("'lms server start' Timeout")
        except (OSError, subprocess.SubprocessError) as exc:
            warn(f"'lms server start' Fehler: {exc}")

        llmster_root = Path(__file__).resolve().parents[2] / ".lmstudio" / "llmster"
        if llmster_root.exists():
            candidates = sorted(
                (path for path in llmster_root.iterdir() if path.is_dir()),
                key=lambda path: path.name,
                reverse=True,
            )
            for version_dir in candidates:
                executable = version_dir / "llmster.exe"
                if not executable.is_file():
                    continue
                info(f"Starte llmster {version_dir.name}...")
                try:
                    subprocess.Popen([str(executable)])
                    self._sleep(5)
                    if self.is_available(timeout=3):
                        self._subprocess_run(
                            ["lms", "server", "start"],
                            capture_output=True,
                            text=True,
                            timeout=30,
                            encoding="utf-8",
                            errors="replace",
                        )
                        self._sleep(5)
                        ok("LM Studio-Server gestartet via llmster")
                        return True
                except (OSError, subprocess.SubprocessError) as exc:
                    warn(f"llmster {version_dir.name} start fehlgeschlagen: {exc}")
        error("Konnte LM Studio-Server nicht starten")
        return False
