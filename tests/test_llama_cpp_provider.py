"""Contract tests for the direct CUDA llama.cpp provider."""

from __future__ import annotations

import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from providers.llama_cpp_provider import LlamaCppProvider


class FakeController:
    def __init__(self) -> None:
        self.process: object | None = None
        self.model_identifier: str | None = None
        self.commands: list[list[str]] = []
        self.stopped = False

    def is_running(self) -> bool:
        return self.process is not None

    def start(self, command: list[str], log_path: Any, timeout: int) -> bool:
        del log_path, timeout
        self.commands.append(command)
        self.process = object()
        return True

    def stop(self, timeout: int) -> bool:
        del timeout
        self.process = None
        self.model_identifier = None
        self.stopped = True
        return True


def test_provider_resolves_local_registry_model_and_builds_cuda_server_command(tmp_path: Any, monkeypatch: Any) -> None:
    model_path = tmp_path / "openai" / "gpt-oss-20b" / "gpt-oss-20b-Q8_0.gguf"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"GGUF")
    executable = tmp_path / "llama-server.exe"
    executable.write_bytes(b"test executable")
    draft_model_path = tmp_path / "draft" / "gemma-mtp-Q8_0.gguf"
    draft_model_path.parent.mkdir(parents=True)
    draft_model_path.write_bytes(b"GGUF draft placeholder")
    registry: dict[str, Any] = {
        "openai/gpt-oss-20b@q8_0": {
            "context_length": 32768,
            "k_cache": "q8_0",
            "v_cache": "q4_nl",
            "useUnifiedKvCache": True,
            "architecture_family": "gpt-oss",
            "experts": 32,
            "reasoning_format": "deepseek",
            "reasoning_budget": 4096,
            "reasoning_effort": "medium",
        }
    }
    controller = FakeController()
    provider = LlamaCppProvider(
        "http://127.0.0.1:18081/v1",
        model_root=tmp_path,
        executable=executable,
        registry_loader=lambda: registry,
        runtime_loader=lambda _: {
            "context_length": 32768,
            "cache_type_k": "q8_0",
            "cache_type_v": "iq4_nl",
            "kv_unified": True,
            "num_experts": 32,
            "expert_override_key": "gpt-oss.expert_used_count",
            "spec_type": "draft-mtp",
            "draft_model_path": str(draft_model_path),
            "draft_n_max": 4,
            "draft_n_min": 0,
            "draft_p_min": 0.75,
            "reasoning_format": "deepseek",
            "reasoning_budget": 4096,
            "reasoning_effort": "medium",
        },
        controller=controller,
    )
    monkeypatch.setattr(provider, "wait_ready", lambda timeout: True)
    monkeypatch.setattr(provider, "_external_server_reachable", lambda: False)

    loaded, identifier = provider.load_model("openai/gpt-oss-20b@q8_0")

    assert (loaded, identifier) == (True, "openai/gpt-oss-20b@q8_0")
    command = controller.commands[0]
    assert command[0] == str(executable)
    assert command[command.index("--model") + 1] == str(model_path)
    assert "--offline" in command
    assert command[command.index("--port") + 1] == "18081"
    assert command[command.index("--ctx-size") + 1] == "32768"
    assert command[command.index("--cache-type-k") + 1] == "q8_0"
    assert command[command.index("--cache-type-v") + 1] == "iq4_nl"
    assert command[command.index("--reasoning-format") + 1] == "deepseek"
    assert command[command.index("--reasoning-budget") + 1] == "4096"
    assert command[command.index("--reasoning-effort") + 1] == "medium"
    assert command[command.index("--override-kv") + 1] == "gpt-oss.expert_used_count=int:32"
    assert command[command.index("--spec-type") + 1] == "draft-mtp"
    assert command[command.index("--spec-draft-model") + 1] == str(draft_model_path)
    assert command[command.index("--spec-draft-n-max") + 1] == "4"
    assert command[command.index("--spec-draft-n-min") + 1] == "0"
    assert command[command.index("--spec-draft-p-min") + 1] == "0.75"
    assert "--jinja" in command
    assert provider.unload_all() is True
    assert controller.stopped is True


def test_provider_lists_registry_eligible_local_ggufs(tmp_path: Any) -> None:
    model_path = tmp_path / "publisher" / "model" / "model-Q4_K_M.gguf"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"GGUF")
    provider = LlamaCppProvider(
        "http://127.0.0.1:18082/v1",
        model_root=tmp_path,
        executable=tmp_path / "llama-server.exe",
        registry_loader=lambda: {"publisher/model@q4_k_m": {"display_name": "Model"}},
    )

    models = provider.list_models(registry_only=True)

    assert len(models) == 1
    assert models[0]["registry_key"] == "publisher/model@q4_k_m"
    assert models[0]["model_path"] == str(model_path)
