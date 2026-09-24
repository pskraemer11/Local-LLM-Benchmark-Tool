"""Regression tests for the shared identity, artifact, quant, and parameter contracts."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from artifact_resolver import ArtifactResolver
from parameter_bindings import config_sync_fields, parameter_binding
from quantization import extract_quant_from_text, normalize_quant


def test_artifact_resolver_returns_unique_normalized_match(tmp_path: Path) -> None:
    model = tmp_path / "publisher" / "model-Q4_K_M.gguf"
    model.parent.mkdir(parents=True)
    model.touch()

    result = ArtifactResolver(tmp_path).resolve("publisher/model@q4_k_m")

    assert result.is_unique
    assert result.path == model
    assert result.evidence == "unique-name-substring"


def test_artifact_resolver_fails_closed_on_same_root_ambiguity(tmp_path: Path) -> None:
    for filename in ("model-Q4_K_M.gguf", "model-q4_k_m-copy.gguf"):
        path = tmp_path / filename
        path.touch()

    result = ArtifactResolver(tmp_path).resolve("model@q4_k_m")

    assert result.status == "ambiguous"
    assert result.path is None
    assert len(result.candidates) == 2


def test_artifact_resolver_prefers_explicit_publisher_directory(tmp_path: Path) -> None:
    first = tmp_path / "qwen" / "qwen3.5-9b-Q5_K_S.gguf"
    second = tmp_path / "byteshape" / "qwen3.5-9b-Q5_K_S.gguf"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.touch()
    second.touch()

    result = ArtifactResolver(tmp_path).resolve("byteshape/qwen3.5-9b@q5_k_s")

    assert result.is_unique
    assert result.path == second


def test_quantization_vocabulary_covers_new_markers() -> None:
    assert normalize_quant("Q4-K-M") == "q4_k_m"
    assert extract_quant_from_text("gemma-4-12b-QAT-NVFP4-GGUF") == "nvfp4"
    assert extract_quant_from_text("gemma-4-26b-it-mini.gguf") == "mini"


def test_parameter_bindings_are_the_sync_and_llama_contract() -> None:
    assert parameter_binding("context_length").llama_cpp_flag == "--ctx-size"
    assert parameter_binding("k_cache").llama_cpp_flag == "--cache-type-k"
    assert config_sync_fields(context_only=True) == (("context_length", "context_length"),)
    assert config_sync_fields(experts_only=True) == (("experts", "num_experts"),)
