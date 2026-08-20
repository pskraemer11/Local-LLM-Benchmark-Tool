"""Tests for the process-owned Unsloth server provider."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from providers.unsloth_server_provider import UnslothServerProvider

if TYPE_CHECKING:
    from pathlib import Path


class FakeController:
    def __init__(self) -> None:
        self.process: object | None = None
        self.model_identifier: str | None = None
        self.commands: list[list[str]] = []
        self.stopped = False

    def is_running(self) -> bool:
        return self.process is not None

    def start(self, command: list[str], log_path: Path, timeout: int) -> bool:
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


def test_provider_lists_only_registry_eligible_local_models(tmp_path: Path) -> None:
    model_path = tmp_path / "openai" / "gpt-oss-20b" / "gpt-oss-20b-MXFP4.gguf"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"GGUF")
    registry: dict[str, Any] = {"openai/gpt-oss-20b@mxfp4": {"display_name": "GPT-OSS 20B"}}
    provider = UnslothServerProvider(
        "http://127.0.0.1:8890/v1",
        model_root=tmp_path,
        executable=tmp_path / "llama-server.exe",
        registry_loader=lambda: registry,
    )

    models = provider.list_models(registry_only=True)

    assert len(models) == 1
    assert models[0]["model_identifier"] == "openai/gpt-oss-20b@mxfp4"
    assert models[0]["model_path"] == str(model_path)


def test_provider_starts_offline_server_with_local_model(tmp_path: Path, monkeypatch: Any) -> None:
    model_path = tmp_path / "openai" / "gpt-oss-20b" / "gpt-oss-20b-MXFP4.gguf"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"GGUF")
    executable = tmp_path / "llama-server.exe"
    executable.write_bytes(b"test executable")
    registry: dict[str, Any] = {
        "openai/gpt-oss-20b@mxfp4": {
            "context_length": 32768,
            "k_cache": "q8_0",
            "v_cache": "q4_nl",
            "useUnifiedKvCache": True,
        }
    }
    controller = FakeController()
    provider = UnslothServerProvider(
        "http://127.0.0.1:8890/v1",
        model_root=tmp_path,
        executable=executable,
        registry_loader=lambda: registry,
        runtime_loader=lambda _: {
            "context_length": 32768,
            "cache_type_k": "q8_0",
            "cache_type_v": "q4_nl",
            "kv_unified": True,
            "chat_template_file": str(tmp_path / "gpt-oss-20b-template_unsloth.jinja"),
        },
        controller=controller,
    )
    monkeypatch.setattr(provider, "wait_ready", lambda timeout: True)

    loaded, identifier = provider.load_model("openai/gpt-oss-20b@mxfp4")

    assert (loaded, identifier) == (True, "openai/gpt-oss-20b@mxfp4")
    command = controller.commands[0]
    assert command[command.index("--model") + 1] == str(model_path)
    assert "--offline" in command
    assert command[command.index("--alias") + 1] == "openai/gpt-oss-20b@mxfp4"
    assert command[command.index("--ctx-size") + 1] == "32768"
    assert command[command.index("--parallel") + 1] == "4"
    assert command[command.index("--gpu-layers") + 1] == "all"
    assert command[command.index("--cache-type-k") + 1] == "q8_0"
    assert command[command.index("--cache-type-v") + 1] == "iq4_nl"
    assert "--kv-unified" in command
    assert command[command.index("--chat-template-file") + 1].endswith(
        "gpt-oss-20b-template_unsloth.jinja"
    )
    assert "--flash-attn" in command
    assert "--cont-batching" in command
    assert provider.unload_all() is True
    assert controller.stopped is True


def test_provider_attaches_to_already_running_external_server(tmp_path: Path, monkeypatch: Any) -> None:
    model_path = tmp_path / "openai" / "gpt-oss-20b" / "gpt-oss-20b-MXFP4.gguf"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"GGUF")
    registry: dict[str, Any] = {"openai/gpt-oss-20b@mxfp4": {}}
    provider = UnslothServerProvider(
        "http://127.0.0.1:8890/v1",
        model_root=tmp_path,
        executable=tmp_path / "missing-llama-server.exe",
        registry_loader=lambda: registry,
    )
    monkeypatch.setattr(
        provider,
        "request_json",
        lambda endpoint, **kwargs: {"data": [{"id": "openai/gpt-oss-20b@mxfp4"}]}
        if endpoint == "/models" else None,
    )

    loaded, identifier = provider.load_model("openai/gpt-oss-20b@mxfp4")

    assert (loaded, identifier) == (True, "openai/gpt-oss-20b@mxfp4")
    assert provider.current_model()["external"] is True
