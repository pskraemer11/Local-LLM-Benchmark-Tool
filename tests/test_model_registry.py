"""Tests for the central model-registry resolver and runtime derivation."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from model_registry import ModelRegistry

if TYPE_CHECKING:
    from pathlib import Path


def test_model_registry_resolves_registry_aliases_and_neutral_runtime(tmp_path: Path) -> None:
    registry = {
        "unsloth/gemma-4-26b-a4b-it@iq3_s": {
            "context_length": 32768,
            "max_context_length": 262144,
            "k_cache": "fp16",
            "v_cache": "fp16",
            "useUnifiedKvCache": True,
            "reasoning": "thinking",
            "sampling": {
                "coding": {"temperature": 0.6, "top_p": 0.95},
            },
        }
    }
    model_registry = ModelRegistry(lambda: registry, template_root=tmp_path)

    resolved = model_registry.resolve("google_gemma-4-26b-a4b-it")

    assert resolved is not None
    assert resolved.registry_key == "unsloth/gemma-4-26b-a4b-it@iq3_s"
    assert resolved.quant == "iq3_s"
    runtime = resolved.benchmark_runtime()
    assert runtime["context_length"] == 32768
    assert runtime["native_context_length"] == 262144
    assert runtime["useUnifiedKvCache"] is True
    assert runtime["reasoning"] == "thinking"
    assert runtime["quant"] == "iq3_s"
    assert runtime["sampling"]["coding"]["temperature"] == 0.6
    runtime["sampling"]["coding"]["temperature"] = 0.1
    assert registry["unsloth/gemma-4-26b-a4b-it@iq3_s"]["sampling"]["coding"]["temperature"] == 0.6
    assert resolved.technical_boundary_issues() == []


def test_model_registry_clips_context_to_native_limit(tmp_path: Path) -> None:
    registry = {
        "unsloth/gemma-4-26b-a4b-it@iq3_s": {
            "context_length": 65536,
            "max_context_length": 32768,
            "k_cache": "fp16",
            "v_cache": "fp16",
        }
    }
    model_registry = ModelRegistry(lambda: registry, template_root=tmp_path)

    resolved = model_registry.resolve("unsloth/gemma-4-26b-a4b-it@iq3_s")

    assert resolved is not None
    assert resolved.benchmark_context_length() == 32768
    assert resolved.technical_boundary_issues() == [
        "context_length 65536 exceeds native max_context_length 32768",
    ]
    runtime = resolved.benchmark_runtime()
    assert runtime["context_length"] == 32768
    assert runtime["native_context_length"] == 32768
    assert runtime["technical_boundary_issues"] == [
        "context_length 65536 exceeds native max_context_length 32768",
    ]


def test_model_registry_derives_provider_specific_runtime(tmp_path: Path) -> None:
    draft_path = tmp_path / "draft" / "dflash-q4_0.gguf"
    draft_path.parent.mkdir(parents=True)
    draft_path.write_bytes(b"GGUF draft placeholder")
    registry = {
        "unsloth/gpt-oss-20b-GGUF@q8_0": {
            "context_length": 32768,
            "k_cache": "fp16",
            "v_cache": "fp16",
            "useUnifiedKvCache": True,
            "template_policy": "explicit_file",
            "template": "gpt-oss-20b-template_unsloth.jinja",
            "architecture_family": "gpt-oss",
            "experts": 32,
            "max_experts": 32,
            "reasoning_format": "deepseek",
            "llama_cpp": {"reasoning_effort": "medium"},
            "local": {
                "companions": {"draft": str(draft_path)},
                "llama_cpp": {
                    "speculative": {
                        "type": "draft",
                        "method": "dflash",
                        "companion_role": "draft",
                        "draft_n_max": 3,
                        "draft_n_min": 0,
                        "draft_p_min": 0.75,
                    }
                },
            },
        }
    }
    model_registry = ModelRegistry(lambda: registry, template_root=tmp_path)

    tabbyapi_runtime = model_registry.provider_runtime("unsloth/gpt-oss-20b-GGUF@q8_0", "tabbyapi")
    unsloth_runtime = model_registry.provider_runtime("unsloth/gpt-oss-20b-GGUF@q8_0", "unsloth_server")
    llama_runtime = model_registry.provider_runtime("unsloth/gpt-oss-20b-GGUF@q8_0", "llama_cpp")

    assert tabbyapi_runtime["max_seq_len"] == 32768
    assert tabbyapi_runtime["cache_size"] == 32768
    assert tabbyapi_runtime["cache_mode"] == "FP16"
    assert unsloth_runtime["context_length"] == 32768
    assert unsloth_runtime["cache_type_k"] == "f16"
    assert unsloth_runtime["cache_type_v"] == "f16"
    assert unsloth_runtime["kv_unified"] is True
    assert unsloth_runtime["chat_template_file"] == str(
        tmp_path / "gpt-oss-20b-template_unsloth.jinja"
    )
    assert llama_runtime["context_length"] == 32768
    assert llama_runtime["cache_type_k"] == "f16"
    assert llama_runtime["kv_unified"] is True
    assert llama_runtime["reasoning_format"] == "deepseek"
    assert llama_runtime["reasoning_effort"] == "medium"
    assert llama_runtime["num_experts"] == 32
    assert llama_runtime["expert_override_key"] == "gpt-oss.expert_used_count"
    assert llama_runtime["spec_type"] == "draft-dflash"
    assert llama_runtime["spec_kind"] == "draft"
    assert llama_runtime["spec_method"] == "dflash"
    assert llama_runtime["draft_model_path"] == str(draft_path)
    assert llama_runtime["draft_n_max"] == 3
    assert llama_runtime["draft_n_min"] == 0
    assert llama_runtime["draft_p_min"] == 0.75
    assert llama_runtime["chat_template_file"] == str(
        tmp_path / "gpt-oss-20b-template_unsloth.jinja"
    )
    assert model_registry.provider_runtime(
        "unsloth/gpt-oss-20b-GGUF@q8_0", "lmstudio"
    )["num_experts"] == 32


def test_model_registry_quant_list_falls_back_safely(tmp_path: Path) -> None:
    registry = {
        "example/model@q4_k_m": {
            "quants": ["Q4_K_M"],
        },
        "example/model-empty": {
            "quants": [],
        },
    }
    model_registry = ModelRegistry(lambda: registry, template_root=tmp_path)

    resolved_list = model_registry.resolve("example/model@q4_k_m")
    resolved_empty = model_registry.resolve("example/model-empty")

    assert resolved_list is not None
    assert resolved_list.quant == "q4_k_m"
    assert resolved_empty is not None
    assert resolved_empty.quant is None


def test_model_registry_keeps_integrated_mtp_without_draft_path(tmp_path: Path) -> None:
    registry = {
        "unsloth/qwen3.6-35b-a3b-mtp@iq2_m": {
            "local": {
                "llama_cpp": {
                    "speculative": {
                        "type": "mtp",
                        "mode": "integrated",
                    }
                }
            }
        }
    }
    model_registry = ModelRegistry(lambda: registry, template_root=tmp_path)

    runtime = model_registry.provider_runtime(
        "unsloth/qwen3.6-35b-a3b-mtp@iq2_m", "llama_cpp"
    )

    assert runtime["spec_kind"] == "mtp"
    assert runtime["spec_mode"] == "integrated"
    assert runtime["spec_type"] == "draft-mtp"
    assert "draft_model_path" not in runtime


def test_model_registry_resolves_separate_mtp_companion(tmp_path: Path) -> None:
    mtp_path = tmp_path / "mtp-gemma-Q8_0.gguf"
    mtp_path.write_bytes(b"GGUF placeholder")
    registry = {
        "unsloth/gemma-4-12b-it@q6_k": {
            "local": {
                "companions": {"mtp": str(mtp_path)},
                "llama_cpp": {
                    "speculative": {
                        "type": "mtp",
                        "mode": "separate",
                        "companion_role": "mtp",
                    }
                },
            }
        }
    }
    model_registry = ModelRegistry(lambda: registry, template_root=tmp_path)

    runtime = model_registry.provider_runtime(
        "unsloth/gemma-4-12b-it@q6_k", "llama_cpp"
    )

    assert runtime["spec_kind"] == "mtp"
    assert runtime["spec_mode"] == "separate"
    assert runtime["spec_type"] == "draft-mtp"
    assert runtime["draft_model_path"] == str(mtp_path)


def test_model_registry_does_not_emit_companion_cli_without_companion_path(tmp_path: Path) -> None:
    registry = {
        "gguf-org/muse-glimmer-30b@nvfp4": {
            "local": {
                "llama_cpp": {
                    "speculative": {
                        "type": "draft",
                        "method": "dflash",
                        "companion_role": "draft",
                    }
                }
            }
        }
    }
    model_registry = ModelRegistry(lambda: registry, template_root=tmp_path)

    runtime = model_registry.provider_runtime(
        "gguf-org/muse-glimmer-30b@nvfp4", "llama_cpp"
    )

    assert runtime["spec_kind"] == "draft"
    assert runtime["spec_method"] == "dflash"
    assert "spec_type" not in runtime
    assert "draft_model_path" not in runtime


def test_model_registry_never_first_wins_on_publisher_collision(tmp_path: Path) -> None:
    registry = {
        "qwen/qwen3.5-9b@q5_k_s": {"context_length": 8192},
        "byteshape/qwen3.5-9b@q5_k_s": {"context_length": 16384},
    }
    model_registry = ModelRegistry(lambda: registry, template_root=tmp_path)

    explicit = model_registry.resolve("byteshape/qwen3.5-9b@q5_k_s")
    publisherless = model_registry.resolve("qwen3.5-9b@q5_k_s")

    assert explicit is not None
    assert explicit.registry_key == "byteshape/qwen3.5-9b@q5_k_s"
    assert publisherless is None
