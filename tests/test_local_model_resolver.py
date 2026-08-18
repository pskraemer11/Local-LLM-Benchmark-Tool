"""Tests for local GGUF discovery and benchmark eligibility filtering."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from local_model_resolver import LocalModelResolver

if TYPE_CHECKING:
    from pathlib import Path


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"GGUF test placeholder")


def test_resolver_reuses_central_blacklist_and_support_file_filter(tmp_path: Path) -> None:
    _touch(tmp_path / "unsloth" / "gpt-oss-20b-GGUF" / "gpt-oss-20b-MXFP4.gguf")
    _touch(tmp_path / "unsloth" / "f2llm-v2-1.7B-GGUF" / "f2llm-v2-1.7B-Q8_0.gguf")
    _touch(tmp_path / "vendor" / "ocr-model-GGUF" / "ocr-model-Q8_0.gguf")
    _touch(tmp_path / "vendor" / "valid-model-GGUF" / "mmproj-F32.gguf")
    _touch(tmp_path / "vendor" / "valid-model-GGUF" / "mtp-draft-Q8_0.gguf")

    resolver = LocalModelResolver(tmp_path)

    assert [candidate.model_identifier for candidate in resolver.candidates()] == [
        "unsloth/gpt-oss-20b-GGUF@mxfp4"
    ]


def test_resolver_keeps_standalone_mtp_model(tmp_path: Path) -> None:
    path = tmp_path / "unsloth" / "Qwen3.6-27B-MTP-GGUF" / "model.gguf"
    _touch(path)

    candidates = LocalModelResolver(tmp_path).candidates()

    assert len(candidates) == 1
    assert candidates[0].path == path


def test_resolver_maps_unsloth_hf_cache_to_logical_model_id(tmp_path: Path) -> None:
    path = (
        tmp_path
        / "hub"
        / "models--unsloth--Qwen3.6-27B-MTP-GGUF"
        / "snapshots"
        / "revision"
        / "Qwen3.6-27B-UD-Q4_K_XL.gguf"
    )
    _touch(path)

    candidates = LocalModelResolver(tmp_path).candidates()

    assert len(candidates) == 1
    assert candidates[0].model_identifier == "unsloth/Qwen3.6-27B-MTP-GGUF@q4_k_xl"
    assert candidates[0].path == path


def test_resolver_matches_registry_and_exposes_local_path(tmp_path: Path) -> None:
    path = tmp_path / "openai" / "gpt-oss-20b" / "gpt-oss-20b-MXFP4.gguf"
    _touch(path)
    registry: dict[str, Any] = {
        "openai/gpt-oss-20b@mxfp4": {"display_name": "GPT-OSS 20B"},
    }

    candidates = LocalModelResolver(tmp_path, registry_loader=lambda: registry).candidates(registry_only=True)

    assert len(candidates) == 1
    assert candidates[0].model_identifier == "openai/gpt-oss-20b@mxfp4"
    assert candidates[0].registry_key == "openai/gpt-oss-20b@mxfp4"
    assert candidates[0].display == "GPT-OSS 20B@mxfp4"
    assert candidates[0].path == path


def test_resolver_normalizes_unsloth_gguf_folder_for_registry_match(tmp_path: Path) -> None:
    path = (
        tmp_path
        / "bartowski"
        / "mistralai_Magistral-Small-2509-GGUF"
        / "mistralai-Magistral-Small-2509-Q3_K_M.gguf"
    )
    _touch(path)
    registry: dict[str, Any] = {
        "bartowski/mistralai-magistral-small-2509@q3_k_m": {},
    }

    candidates = LocalModelResolver(tmp_path, registry_loader=lambda: registry).candidates(
        registry_only=True
    )

    assert len(candidates) == 1
    assert candidates[0].registry_key == "bartowski/mistralai-magistral-small-2509@q3_k_m"
    assert candidates[0].model_identifier == "bartowski/mistralai-magistral-small-2509@q3_k_m"


def test_resolver_does_not_assign_wrong_registry_quant(tmp_path: Path) -> None:
    _touch(tmp_path / "unsloth" / "model" / "model-Q4_K_XL.gguf")
    registry: dict[str, Any] = {"unsloth/model@q8_0": {"display_name": "Model"}}

    assert LocalModelResolver(tmp_path, registry_loader=lambda: registry).candidates(registry_only=True) == []


def test_resolver_does_not_assign_wrong_quant_after_flexible_base_match(tmp_path: Path) -> None:
    _touch(
        tmp_path
        / "unsloth"
        / "Qwen3.6-27B-MTP-GGUF"
        / "Qwen3.6-27B-UD-Q4_K_XL.gguf"
    )
    registry: dict[str, Any] = {"unsloth/qwen3.6-27b-mtp@q8_0": {}}

    assert LocalModelResolver(tmp_path, registry_loader=lambda: registry).candidates(
        registry_only=True
    ) == []


def test_resolver_rejects_missing_local_model_without_remote_fallback(tmp_path: Path) -> None:
    resolver = LocalModelResolver(tmp_path)

    with pytest.raises(RuntimeError, match="Remote-Downloads"):
        resolver.resolve("unsloth/missing-model@q4_k_m")
