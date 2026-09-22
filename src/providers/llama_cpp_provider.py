"""Process-owned provider for the project's standalone CUDA llama.cpp build.

The provider deliberately starts ``llama-server.exe`` with one concrete local
GGUF file.  It does not use ``lms.exe``, LM Studio's REST lifecycle endpoints,
the WindowsApps ``llama.exe`` wrapper, or router auto-downloads.  Inference is
then performed through the server's OpenAI-compatible local API.
"""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from benchmark_config import is_blacklisted_model_name
from local_model_resolver import LocalModelResolver, ModelResolutionError
from utils.terminal import warn

from .base import HttpProvider, ProviderCapabilities
from .llama_cpp_args import build_server_command

RuntimeLoader = Callable[[str], Mapping[str, Any] | None]
ProcessFactory = Callable[..., Any]

_DEFAULT_EXECUTABLE = Path(r"C:\Program Files\llama.cpp\llama-server.exe")
class _ServerController:
    """Own exactly one llama-server process for one API base URL."""

    def __init__(self, process_factory: ProcessFactory | None = None) -> None:
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
        controller = _ServerController()
        _CONTROLLERS[base_url] = controller
    return controller


class LlamaCppProvider(HttpProvider):
    """Direct CUDA llama.cpp server with explicit local-model lifecycle."""

    capabilities = ProviderCapabilities(
        can_list_models=True,
        can_load_models=True,
        can_unload_models=True,
        can_report_current_model=True,
        supports_chat_completions=True,
        supports_completions=True,
        max_parallel=4,
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
        super().__init__(base_url)
        self._resolver = LocalModelResolver(model_root, registry_loader=registry_loader)
        self._executable = Path(executable or os.environ.get("LLAMA_CPP_SERVER_EXE") or _DEFAULT_EXECUTABLE)
        self._runtime_loader = runtime_loader
        self._controller = controller or _controller_for(self.base_url)
        if process_factory is not None:
            self._controller._process_factory = process_factory
        self._start_timeout = int(os.environ.get("LLAMA_CPP_SERVER_START_TIMEOUT", "15"))
        self._ready_timeout = int(os.environ.get("LLAMA_CPP_SERVER_READY_TIMEOUT", "180"))
        self._stop_timeout = int(os.environ.get("LLAMA_CPP_SERVER_STOP_TIMEOUT", "30"))
        max_parallel = os.environ.get("LLAMA_CPP_MAX_PARALLEL")
        if max_parallel:
            try:
                self.capabilities = ProviderCapabilities(
                    can_list_models=True,
                    can_load_models=True,
                    can_unload_models=True,
                    can_report_current_model=True,
                    supports_chat_completions=True,
                    supports_completions=True,
                    max_parallel=max(1, int(max_parallel)),
                )
            except ValueError:
                    warn(f"Ungültiges LLAMA_CPP_MAX_PARALLEL={max_parallel!r}; verwende 4.")

    def list_models(
        self,
        exclude_keywords: list[str] | None = None,
        registry_only: bool = False,
    ) -> list[dict[str, Any]]:
        models = [
            self._resolver.as_model_info(
                candidate,
                loaded=(candidate.model_identifier == self._controller.model_identifier
                        and self._controller.is_running()),
            )
            for candidate in self._resolver.candidates(registry_only=registry_only)
        ]
        active_keywords = exclude_keywords or []
        return [
            model for model in models
            if not any(
                is_blacklisted_model_name(model[field], active_keywords)
                for field in ("key", "display")
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
            "external": False,
        }

    def _server_root(self) -> str:
        parsed = urlsplit(self.base_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _server_port(self) -> str:
        parsed = urlsplit(self.base_url)
        return str(parsed.port or 8080)

    def _external_server_reachable(self) -> bool:
        """Detect an already-running server without attaching or stopping it."""
        if self._controller.is_running():
            return False
        return isinstance(self.request_json("/models", timeout=1), dict)

    def _command(self, model_identifier: str, model_path: Path) -> list[str]:
        runtime = dict(self._runtime_loader(model_identifier) or {}) if self._runtime_loader else {}
        return build_server_command(
            self._executable,
            model_path,
            model_identifier,
            self._server_port(),
            runtime,
            warning=warn,
        )

    def _log_path(self, model_identifier: str) -> Path:
        log_dir = Path(os.environ.get(
            "LLAMA_CPP_LOG_DIR",
            Path(__file__).resolve().parents[2] / "ergebnisse" / "llama-cpp-server",
        ))
        safe = "".join(char if char.isalnum() or char in "._-" else "_" for char in model_identifier)
        return log_dir / f"llama-server_{safe}.log"

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
        if self._external_server_reachable():
            warn(
                f"llama.cpp-Port {self._server_port()} wird bereits von einem fremden "
                "Server verwendet; der Provider beendet ihn nicht."
            )
            return False, None
        if current and not self.unload_all(timeout=self._stop_timeout):
            return False, None
        if not self._executable.is_file():
            warn(f"llama-server.exe nicht gefunden: {self._executable}")
            return False, None
        log_path = self._log_path(candidate.model_identifier)
        if not self._controller.start(self._command(candidate.model_identifier, candidate.path), log_path, self._start_timeout):
            warn(f"llama-server konnte nicht gestartet werden. Log: {log_path}")
            return False, None
        self._controller.model_identifier = candidate.model_identifier
        if not self.wait_ready(timeout=self._ready_timeout):
            self.unload_all(timeout=self._stop_timeout)
            return False, None
        return True, candidate.model_identifier

    def unload_all(self, timeout: int = 120) -> bool:
        return self._controller.stop(timeout)

    def is_available(self, timeout: int = 5) -> bool:
        return isinstance(self.request_json("/models", timeout=timeout), dict)

    def wait_ready(self, timeout: int = 120) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._controller.is_running():
                return False
            health = HttpProvider(self._server_root()).request_json("/health", timeout=2)
            if isinstance(health, dict) and health.get("status") in {"ok", "loading"}:
                if self.is_available(timeout=2):
                    return True
            time.sleep(1)
        return False
