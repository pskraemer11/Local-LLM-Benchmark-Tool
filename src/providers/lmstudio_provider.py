"""LM Studio provider for native lifecycle and OpenAI-compatible inference."""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from benchmark_config import is_support_file
from utils.terminal import error, info, ok, warn

from .base import HttpProvider, ProviderCapabilities

RestRequest = Callable[..., dict | None]
SubprocessRun = Callable[..., Any]
RegistryOverrides = Callable[[], dict[str, str]]
RegistryLoader = Callable[[], dict]


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
        time_fn: Callable[[], float] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        subprocess_run: SubprocessRun | None = None,
    ) -> None:
        super().__init__(base_url)
        self.cli_timeout = cli_timeout
        self.rest_base_url = base_url[:-3] if base_url.endswith("/v1") else base_url
        self._rest_request = rest_request
        self._ensure_server_callback = ensure_server
        self._registry_overrides = registry_overrides
        self._registry_loader = registry_loader
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
    ) -> dict | None:
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
            if not base_key or is_support_file(
                item.get("path", "") or item.get("indexedModelIdentifier", ""),
                item.get("architecture", ""),
            ):
                continue
            quant = item.get("quantization", {}) or {}
            quant_name = quant.get("name", "") if isinstance(quant, dict) else ""
            selected_variant = item.get("selectedVariant") or ""
            unique_key = selected_variant if selected_variant and selected_variant != base_key else (
                f"{base_key}@{quant_name}"
                if quant_name and not base_key.lower().endswith(f"@{quant_name.lower()}")
                else base_key
            )
            if not quant_name and base_key.endswith("@?"):
                filename = (item.get("path") or "").replace("\\", "/").rsplit("/", 1)[-1]
                if filename.lower().endswith(".gguf"):
                    stem = filename[:-5]
                    if "-" in stem:
                        quant_name = stem.rsplit("-", 1)[-1]
            display = item.get("displayName", base_key)
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
                if not any(keyword in (model["key"] + " " + model["display"]).lower() for keyword in exclude_keywords)
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
        data = self._run_lms("ps", "--json")
        if not data:
            return None
        try:
            entry = data[0]
            return {
                "identifier": entry.get("identifier", ""),
                "model_identifier": entry.get("modelKey", entry.get("path", "")),
                "display_name": entry.get("displayName", ""),
                "status": entry.get("status", ""),
                "context_length": entry.get("contextLength"),
            }
        except (KeyError, TypeError, IndexError):
            return None

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
        for attempt in range(2):
            result = self._native_request("/api/v1/models/load", method="POST", payload=payload, timeout=180)
            if result is not None and result.get("status") == "loaded":
                instance_id = result.get("instance_id", model_identifier)
                load_time = result.get("load_time_seconds", 0)
                load_config = result.get("load_config", {})
                ok(f"Loaded in {load_time:.1f}s (np={load_config.get('parallel', '?')})")
                info(f"Instance ID: {instance_id}")
                return True, instance_id
            if result is not None:
                models_data = self._native_request("/api/v1/models")
                if models_data:
                    for model in models_data.get("models", []):
                        if model.get("key") == model_identifier or model_identifier in model.get("key", ""):
                            for instance in model.get("loaded_instances", []):
                                return True, instance.get("id", model_identifier)
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
