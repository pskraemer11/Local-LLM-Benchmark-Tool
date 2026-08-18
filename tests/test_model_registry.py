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
    registry = {
        "unsloth/gpt-oss-20b-GGUF@q8_0": {
            "context_length": 32768,
            "k_cache": "fp16",
            "v_cache": "fp16",
            "useUnifiedKvCache": True,
            "template_policy": "explicit_file",
            "template": "gpt-oss-20b-template_unsloth.jinja",
        }
    }
    model_registry = ModelRegistry(lambda: registry, template_root=tmp_path)

    tabbyapi_runtime = model_registry.provider_runtime("unsloth/gpt-oss-20b-GGUF@q8_0", "tabbyapi")
    unsloth_runtime = model_registry.provider_runtime("unsloth/gpt-oss-20b-GGUF@q8_0", "unsloth_server")

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
