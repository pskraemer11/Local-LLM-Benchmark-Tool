"""Provider that owns a local Unsloth-bundled llama-server process."""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from local_model_resolver import LocalModelResolver, ModelResolutionError
from utils.terminal import warn

from .base import HttpProvider, ProviderCapabilities

RuntimeLoader = Callable[[str], Mapping[str, Any] | None]
ProcessFactory = Callable[..., Any]

# Benchmark policy: keep all four GPU slots busy unless an explicit runtime
# override says otherwise. Throughput matters more here than minimal VRAM.
_DEFAULT_SERVER_PARALLEL = 4
_DEFAULT_GPU_LAYERS = "all"
_SUPPORTED_CACHE_TYPES = frozenset({"f32", "f16", "bf16", "q8_0", "q4_0", "q4_1", "iq4_nl", "q5_0", "q5_1"})
_CACHE_TYPE_ALIASES = {"fp16": "f16", "float16": "f16", "q4_nl": "iq4_nl"}


class _ServerController:
    """Own one server process and its current model state."""

    def __init__(self, base_url: str, process_factory: ProcessFactory | None = None) -> None:
        self.base_url = base_url
        self._process_factory = process_factory or subprocess.Popen
        self.process: Any | None = None
        self.model_identifier: str | None = None
        self.log_path: Path | None = None

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, command: list[str], log_path: Path, timeout: int) -> bool:
        if self.is_running():
            return False
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = log_path.open("a", encoding="utf-8")
        try:
            self.process = self._process_factory(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        except (OSError, subprocess.SubprocessError):
            log_file.close()
            self.process = None
            return False
        finally:
            log_file.close()
        self.log_path = log_path
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.is_running():
                return False
            time.sleep(0.1)
        return self.is_running()

    def stop(self, timeout: int) -> bool:
        process = self.process
        if process is None:
            self.model_identifier = None
            return True
        if process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=timeout)
            except (OSError, subprocess.SubprocessError, TimeoutError):
                try:
                    process.kill()
                    process.wait(timeout=5)
                except (OSError, subprocess.SubprocessError, TimeoutError):
                    return False
        self.process = None
        self.model_identifier = None
        return True


_CONTROLLERS: dict[str, _ServerController] = {}


def _controller_for(base_url: str) -> _ServerController:
    controller = _CONTROLLERS.get(base_url)
    if controller is None:
        controller = _ServerController(base_url)
        _CONTROLLERS[base_url] = controller
    return controller


class UnslothServerProvider(HttpProvider):
    """Local OpenAI-compatible inference with process-owned lifecycle."""

    capabilities = ProviderCapabilities(
        can_list_models=True,
        can_load_models=True,
        can_unload_models=True,
        can_report_current_model=True,
    )

    def __init__(
        self,
        base_url: str,
        model_root: str | Path | None = None,
        executable: str | Path | None = None,
        registry_loader: Callable[[], dict[str, Any]] | None = None,
        runtime_loader: RuntimeLoader | None = None,
        process_factory: ProcessFactory | None = None,
        controller: _ServerController | None = None,
    ) -> None:
        api_key = os.environ.get("UNSLOTH_SERVER_API_KEY") or os.environ.get("LLM_API_KEY")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        super().__init__(base_url, headers)
        self._resolver = LocalModelResolver(model_root, registry_loader=registry_loader)
        self._executable = Path(
            executable
            or os.environ.get("UNSLOTH_SERVER_EXE")
            or Path.home() / ".unsloth" / "llama.cpp" / "build" / "bin" / "Release" / "llama-server.exe"
        )
        self._runtime_loader = runtime_loader
        self._controller = controller or _controller_for(self.base_url)
        if process_factory is not None:
            self._controller._process_factory = process_factory
        self._start_timeout = int(os.environ.get("UNSLOTH_SERVER_START_TIMEOUT", "15"))
        self._ready_timeout = int(os.environ.get("UNSLOTH_SERVER_READY_TIMEOUT", "180"))
        self._stop_timeout = int(os.environ.get("UNSLOTH_SERVER_STOP_TIMEOUT", "30"))

    def list_models(
        self,
        exclude_keywords: list[str] | None = None,
        registry_only: bool = False,
    ) -> list[dict[str, Any]]:
        models = [
            self._resolver.as_model_info(
                candidate,
                loaded=candidate.model_identifier == self._controller.model_identifier
                and self._controller.is_running(),
            )
            for candidate in self._resolver.candidates(registry_only=registry_only)
        ]
        if not exclude_keywords:
            return models
        return [
            model
            for model in models
            if not any(
                keyword in f"{model['key']} {model['display']}".lower()
                for keyword in exclude_keywords
            )
        ]

    def current_model(self) -> dict[str, Any] | None:
        if not self._controller.is_running() or not self._controller.model_identifier:
            return None
        model_identifier = self._controller.model_identifier
        return {
            "identifier": model_identifier,
            "model_identifier": model_identifier,
            "display_name": model_identifier,
            "status": "loaded",
            "context_length": None,
        }

    def _server_port(self) -> str:
        return self.base_url.rsplit(":", 1)[-1].removesuffix("/v1")

    def _runtime_args(self, model_identifier: str) -> list[str]:
        runtime = dict(self._runtime_loader(model_identifier) or {}) if self._runtime_loader else {}
        args: list[str] = []
        context_length = runtime.get("context_length")
        if isinstance(context_length, int) and context_length > 0:
            args.extend(["--ctx-size", str(context_length)])
        # The registry can lower this, but the benchmark default is the
        # speed-first 4-slot policy used throughout the local suite.
        parallel = os.environ.get("UNSLOTH_SERVER_PARALLEL") or runtime.get("parallel")
        args.extend(["--parallel", str(int(parallel or _DEFAULT_SERVER_PARALLEL))])
        for key, option in (("cache_type_k", "--cache-type-k"), ("cache_type_v", "--cache-type-v")):
            value = self._normalize_cache_type(runtime.get(key))
            if value is not None:
                args.extend([option, value])
        unified_kv = runtime.get("kv_unified", True)
        args.append("--kv-unified" if unified_kv else "--no-kv-unified")
        template_file = runtime.get("chat_template_file")
        if isinstance(template_file, str) and template_file.strip():
            args.extend(["--chat-template-file", template_file.strip()])
        # The local benchmark prefers full GPU offload unless the runtime
        # explicitly narrows it for a model family.
        gpu_layers = os.environ.get("UNSLOTH_SERVER_GPU_LAYERS", _DEFAULT_GPU_LAYERS)
        args.extend(["--gpu-layers", gpu_layers])
        args.extend(["--flash-attn", "on", "--cont-batching"])
        return args

    @staticmethod
    def _normalize_cache_type(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip().casefold().replace("-", "_")
        normalized = _CACHE_TYPE_ALIASES.get(normalized, normalized)
        return normalized if normalized in _SUPPORTED_CACHE_TYPES else None

    def _command(self, model_identifier: str, model_path: Path) -> list[str]:
        return [
            str(self._executable),
            "--model",
            str(model_path),
            "--offline",
            "--host",
            "127.0.0.1",
            "--port",
            self._server_port(),
            "--alias",
            model_identifier,
            "--no-webui",
            *self._runtime_args(model_identifier),
        ]

    def load_model(self, model_identifier: str, gpu_offload: float | None = None) -> tuple[bool, str | None]:
        del gpu_offload
        try:
            candidate = self._resolver.resolve(model_identifier)
        except ModelResolutionError as exc:
            warn(str(exc))
            return False, None
        current = self.current_model()
        if current and current["model_identifier"] == candidate.model_identifier:
            return True, candidate.model_identifier
        if current and not self.unload_all(timeout=self._stop_timeout):
            return False, None
        if not self._executable.is_file():
            warn(f"Unsloth llama-server nicht gefunden: {self._executable}")
            return False, None
        log_dir = Path(os.environ.get("UNSLOTH_SERVER_LOG_DIR", Path(__file__).resolve().parents[2] / "logs"))
        log_path = log_dir / "unsloth_server.log"
        if not self._controller.start(
            self._command(candidate.model_identifier, candidate.path),
            log_path,
            self._start_timeout,
        ):
            warn(f"Unsloth llama-server konnte nicht gestartet werden. Log: {log_path}")
            return False, None
        self._controller.model_identifier = candidate.model_identifier
        if not self.wait_ready(timeout=self._ready_timeout):
            self.unload_all(timeout=self._stop_timeout)
            return False, None
        return True, candidate.model_identifier

    def unload_all(self, timeout: int = 120) -> bool:
        return self._controller.stop(timeout)

    def is_available(self, timeout: int = 5) -> bool:
        try:
            return self.request_json("/models", timeout=timeout) is not None
        except Exception:
            return False

    def wait_ready(self, timeout: int = 120) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._controller.is_running():
                return False
            if self.is_available(timeout=min(5, max(1, int(deadline - time.monotonic())))):
                return True
            time.sleep(1)
        return False
