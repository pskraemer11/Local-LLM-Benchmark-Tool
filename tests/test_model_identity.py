"""Tests for model_identity.py + field_owner.py (Fix 2026-08-09).

Deckt ab:
  - Konsolidierte Normalisierer verhalten sich identisch zur Vorgaenger-Logik
    (Regression: @quant bleibt in normalize_model_name, wird in
    normalize_for_config gestrippt, ...)
  - Deterministisches Registry-Matching (Fix-1-Faelle: @quant-Keys)
  - Familien-Klassifikation (qwen3/qwen35-Reihenfolge, Sonderlogik)
  - Feld-Ownership-Tabelle (jedes Registry-Feld hat eine Regel,
    auto_fix nur bei gguf/lms)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from field_owner import FIELD_OWNERSHIP, Drift, auto_fix_fields, resolve
from model_identity import (
    ArtifactIdentityEvidence,
    MODEL_FAMILIES,
    AmbiguousMatch,
    UniqueMatch,
    build_model_identity,
    canonicalize_source_identity,
    classify_reasoning_by_family,
    decompose_model_identity,
    family_for_arch,
    find_match_collisions,
    match_registry_key,
    normalize_for_config,
    normalize_lms_model_name,
    normalize_model_name,
    normalize_model_reference,
    normalize_variants,
    normalized_lms_key,
    resolve_registry_match,
)

# ─────────────────────────────────────────────────────────────────────
# Normalisierer (identisches Verhalten zur Vorgaenger-Logik)
# ─────────────────────────────────────────────────────────────────────


class TestNormalizeModelName:
    def test_lowercase_publisher_strip(self) -> None:
        assert normalize_model_name("Unsloth/GLM-4.7-Flash") == "glm-4-7-flash"

    def test_gguf_mxfp4_suffix_strip(self) -> None:
        assert normalize_model_name("model.gguf") == "model"
        assert normalize_model_name("Model-MXFP4") == "model"

    def test_dots_underscores_to_hyphens(self) -> None:
        assert normalize_model_name("Qwen2.5_Coder-14B") == "qwen2-5-coder-14b"

    def test_quant_suffix_kept(self) -> None:
        # @quant bleibt in normalize_model_name (Vorgaenger-Verhalten!)
        assert normalize_model_name("unsloth/ernie-4.5-21b-a3b-pt@iq4_nl") == "ernie-4-5-21b-a3b-pt@iq4-nl"

    def test_middle_gguf_strip(self) -> None:
        assert (
            normalize_model_name("JetBrains/Mellum2-12B-A2.5B-Thinking-GGUF-MXFP4_MOE")
            == "mellum2-12b-a2-5b-thinking-mxfp4-moe"
        )


def test_source_identity_preserves_namespaced_lms_model_key() -> None:
    assert canonicalize_source_identity(
        "qwen/qwen3.5-9b",
        publisher="lmstudio-community",
        quant="Q6_K",
    ) == "lmstudio-community/qwen/qwen3.5-9b@q6_k"


def test_artifact_identity_evidence_keeps_full_path_and_components(tmp_path: Path) -> None:
    path = tmp_path / "lmstudio-community" / "qwen" / "qwen3.5-9b" / "model-Q6_K.gguf"
    evidence = ArtifactIdentityEvidence.from_reference(
        path,
        "lmstudio-community/qwen/qwen3.5-9b",
        "Q6_K",
    )

    assert evidence.identity == "lmstudio-community/qwen/qwen3.5-9b@q6_k"
    assert evidence.publisher == "lmstudio-community"
    assert evidence.model_name == "qwen/qwen3.5-9b"
    assert evidence.quant == "q6_k"
    assert evidence.path == path
    assert evidence.is_complete


def test_model_reference_normalization_preserves_namespace_slash() -> None:
    assert normalize_model_reference("qwen/qwen3.5-9b") == "qwen/qwen3-5-9b"


class TestNormalizeForConfig:
    def test_quant_suffix_stripped(self) -> None:
        assert normalize_for_config("unsloth/ernie-4.5-21b-a3b-pt@iq4_nl") == "ernie-4-5-21b-a3b-pt"
        assert normalize_for_config("mradermacher/gemma-4-19b-a4b-it-reap-i1@q4_k_m") == "gemma-4-19b-a4b-it-reap-i1"

    def test_variant_suffix_stripped(self) -> None:
        assert normalize_for_config("gemma-4-12b-it-qat") == "gemma-4-12b-it"

    def test_dir_quant_suffixes_stripped(self) -> None:
        assert normalize_for_config("ERNIE-4.5-21B-A3B-PT-GGUF") == "ernie-4-5-21b-a3b-pt"
        assert normalize_for_config("Model-MXFP4") == "model"
        assert (
            normalize_for_config("FreedomAISVR/Gemma-4-12B-it-QAT-NVFP4-GGUF")
            == "gemma-4-12b-it"
        )

    def test_dir_three_part_quant_suffix_stripped(self) -> None:
        # JetBrains-Naming: "...-GGUF-Q4_K_M" -> "-q4-k-m" (3-teilig)
        assert (
            normalize_for_config("JetBrains/Mellum2-12B-A2.5B-Instruct-GGUF-Q4_K_M")
            == "mellum2-12b-a2-5b-instruct"
        )
        assert (
            normalize_for_config("Model-Q3_K_S")
            == "model"
        )


class TestNormalizeLmsModelName:
    def test_quant_suffix_stripped(self) -> None:
        assert normalize_lms_model_name("qwen/qwen3-14b@q4_0") == "qwen3-14b"

    def test_lms_quant_regex(self) -> None:
        assert normalize_lms_model_name("model@q4_k_s?") == "model"
        assert normalize_lms_model_name("model@iq4_xs") == "model"


class TestNormalizedLmsKey:
    def test_variant_suffix_stripped(self) -> None:
        assert normalized_lms_key("gemma-4-12b-it-qat") == "gemma-4-12b-it"

    def test_reap_kept(self) -> None:
        # reap ist KEIN Variant-Suffix - bleibt erhalten
        assert normalized_lms_key("glm-4-7-flash-reap-23b-a3b") == "glm-4-7-flash-reap-23b-a3b"


class TestNormalizeVariants:
    def test_publisher_variants(self) -> None:
        assert normalize_variants("unsloth/x") == {"x"}

    def test_quant_stripped_for_variants(self) -> None:
        assert normalize_variants("unsloth/ernie-4.5-21b-a3b-pt@iq4_nl") == {"ernie-4-5-21b-a3b-pt"}


# ─────────────────────────────────────────────────────────────────────
# Deterministisches Registry-Matching (Fix-1-Regression)
# ─────────────────────────────────────────────────────────────────────

_REGISTRY_KEYS = [
    "unsloth/glm-4.7-flash",
    "unsloth/glm-4.7-flash-reap-23b-a3b",
    "unsloth/ernie-4.5-21b-a3b-pt@iq4_nl",
    "qwen/qwen2.5-coder-14b-instruct@q5_0",
    "jetbrains/mellum2-12b-a2.5b-thinking_moe",
    "zai-org/glm-4.6v-flash",
]


class TestMatchRegistryKey:
    def test_exact_match(self) -> None:
        assert match_registry_key("glm-4.7-flash", _REGISTRY_KEYS) == "unsloth/glm-4.7-flash"

    def test_quant_broad_match(self) -> None:
        # Fix-1-Fall: @quant-Key matcht auf Verzeichnisnamen ohne Quant
        assert match_registry_key("ERNIE-4.5-21B-A3B-PT", _REGISTRY_KEYS) == "unsloth/ernie-4.5-21b-a3b-pt@iq4_nl"
        assert match_registry_key("qwen2.5-coder-14b-instruct", _REGISTRY_KEYS) == "qwen/qwen2.5-coder-14b-instruct@q5_0"

    def test_variant_suffix_match(self) -> None:
        assert match_registry_key("Mellum2-12B-A2.5B-Thinking-GGUF-MXFP4_MOE", _REGISTRY_KEYS) == (
            "jetbrains/mellum2-12b-a2.5b-thinking_moe"
        )

    def test_publisher_mismatch_resolved(self) -> None:
        # GLM-4.6V: GGUF unter lmstudio-community, Registry unter zai-org
        assert match_registry_key("GLM-4.6V-Flash", _REGISTRY_KEYS) == "zai-org/glm-4.6v-flash"

    def test_ambiguous_prefix_returns_none(self) -> None:
        # "GLM-REAP-..." (ohne Quant) ist Praefix von BEIDEN glm-4.7-flash Keys -> mehrdeutig
        assert match_registry_key("GLM-4.7-Flash-REAP", _REGISTRY_KEYS) is None

    def test_ambiguous_prefix_with_quant_resolves_exact(self) -> None:
        # Quant-Suffix wird gestrippt -> eindeutig der REAP-Key (kein Praefix-Fallback)
        assert match_registry_key("GLM-4.7-Flash-REAP-23B-A3B-Q4_K_S", _REGISTRY_KEYS) == (
            "unsloth/glm-4.7-flash-reap-23b-a3b"
        )

    def test_unknown_model_returns_none(self) -> None:
        assert match_registry_key("gemma-4-26b-a4b-it", _REGISTRY_KEYS) is None

    def test_empty_inputs(self) -> None:
        assert match_registry_key("", _REGISTRY_KEYS) is None
        assert match_registry_key("glm-4.7-flash", []) is None

    def test_explicit_publisher_wins_over_publisherless_collision(self) -> None:
        keys = [
            "qwen/qwen3.5-9b@q5_k_s",
            "byteshape/qwen3.5-9b@q5_k_s",
        ]
        result = resolve_registry_match("byteshape/qwen3.5-9b@q5_k_s", keys)
        assert isinstance(result, UniqueMatch)
        assert result.key == "byteshape/qwen3.5-9b@q5_k_s"

    def test_publisherless_collision_is_ambiguous_not_first_wins(self) -> None:
        keys = [
            "qwen/qwen3.5-9b@q5_k_s",
            "byteshape/qwen3.5-9b@q5_k_s",
        ]
        result = resolve_registry_match("qwen3.5-9b@q5_k_s", keys)
        assert isinstance(result, AmbiguousMatch)
        assert result.candidates == tuple(keys)
        assert match_registry_key("qwen3.5-9b@q5_k_s", keys) is None

    def test_specific_variant_is_resolved_without_first_wins(self) -> None:
        keys = [
            "unsloth/gemma-4-12b-it@q6_k",
            "freedomaisvr/gemma-4-12b-it-qat@nvfp4",
        ]
        result = resolve_registry_match("google/gemma-4-12b-it-qat", keys)
        assert isinstance(result, UniqueMatch)
        assert result.key == "freedomaisvr/gemma-4-12b-it-qat@nvfp4"
        assert result.stage == "publisherless-variant-base"

        explicit = resolve_registry_match("unsloth/gemma-4-12b-it-qat", keys)
        assert isinstance(explicit, UniqueMatch)
        assert explicit.key == "unsloth/gemma-4-12b-it@q6_k"
        assert explicit.stage == "publisher-aware-base"

    def test_collision_report_uses_normalized_match_namespace(self) -> None:
        keys = [
            "qwen/qwen3.5-9b@q5_k_s",
            "byteshape/qwen3.5-9b@q5_k_s",
        ]
        collisions = find_match_collisions(keys)
        assert collisions["qwen3-5-9b@q5-k-s"] == tuple(keys)

    def test_namespaced_lms_qwen_is_not_collided_with_byteshape_qwen(self) -> None:
        keys = [
            "lmstudio-community/qwen/qwen3.5-9b@q6_k",
            "qwen/qwen3.5-9b@q6_k",
            "byteshape/qwen3.5-9b@q5_k_s",
        ]

        assert find_match_collisions(keys) == {}


# ─────────────────────────────────────────────────────────────────────
# Familien-Klassifikation
# ─────────────────────────────────────────────────────────────────────


class TestFamilies:
    @pytest.mark.parametrize(
        "arch",
        [
            "deepseek2",
            "ernie4_5-moe",
            "gemma2",
            "gemma3",
            "gemma4",
            "glm4",
            "gpt-oss",
            "granite",
            "granitehybrid",
            "internlm2",
            "kimi-linear",
            "lfm2",
            "lfm2moe",
            "llama",
            "mellum",
            "mistral3",
            "muse-glimmer",
            "qwen2",
            "qwen3",
            "qwen35",
            "qwen3moe",
            "qwen35moe",
            "starcoder2",
        ],
    )
    def test_lms_architecture_families_are_centralized(self, arch: str) -> None:
        assert family_for_arch(arch) is not None

    def test_map_order_qwen35_before_qwen3(self) -> None:
        # qwen35 MUSS vor qwen3 geprueft werden (Substring-Overlap)
        keys = [ak for fam in MODEL_FAMILIES for ak in fam.arch_keys]
        assert keys.index("qwen35") < keys.index("qwen3")

    def test_qwen35_default_thinking(self) -> None:
        assert classify_reasoning_by_family("qwen3.5-9b", "qwen35") == "thinking"

    def test_qwen38_default_thinking(self) -> None:
        assert classify_reasoning_by_family("qwen3.8-27b", "qwen38") == "thinking"

    def test_qwen3_default_instruct(self) -> None:
        assert classify_reasoning_by_family("qwen3-14b", "qwen3") == "instruct"

    def test_qwen3_name_thinking_overrides(self) -> None:
        assert classify_reasoning_by_family("qwen3-30b-a3b-thinking-2507", "qwen3") == "thinking"

    def test_qwen3_instruct_name(self) -> None:
        assert classify_reasoning_by_family("qwen3-coder-7b", "qwen3") == "instruct"

    def test_gpt_oss_thinking(self) -> None:
        assert classify_reasoning_by_family("gpt-oss-20b", "gpt-oss") == "thinking"

    def test_unknown_arch(self) -> None:
        assert classify_reasoning_by_family("unknown-model", "somearch") is None


# ─────────────────────────────────────────────────────────────────────
# Feld-Ownership-Tabelle
# ─────────────────────────────────────────────────────────────────────


class TestFieldOwnership:
    def test_every_field_has_rule(self) -> None:
        # Alle Registry-Felder aus model_registry.yaml muessen eine Regel haben
        import yaml

        reg = yaml.safe_load(
            open(os.path.join(os.path.dirname(__file__), "..", "doc-git", "model_registry.yaml"), encoding="utf-8")
        )
        reg_fields = set()
        for v in reg.values():
            if isinstance(v, dict):
                reg_fields.update(v.keys())
        missing = reg_fields - set(FIELD_OWNERSHIP)
        assert not missing, f"Felder ohne Ownership-Regel: {sorted(missing)}"

    def test_auto_fix_only_gguf_lms(self) -> None:
        for field, rule in FIELD_OWNERSHIP.items():
            if rule.auto_fix:
                assert rule.source in ("gguf", "lms"), f"{field}: auto_fix mit Quelle {rule.source}"

    def test_auto_fix_fields(self) -> None:
        assert set(auto_fix_fields()) == {
            "n_layers",
            "hidden_dim",
            "max_context_length",
            "arch",
            "architecture_family",
            "file_size_bytes",
            "max_experts",
        }

    def test_config_fields_report_only(self) -> None:
        # Since 2026-08-11: Registry is SSOT, these fields have source="registry"
        # (num_parallel ist seit 13.08. feste Policy und kein Registry-Feld mehr)
        for field in ("useUnifiedKvCache", "offload", "context_length"):
            assert resolve(field) is not None
            assert resolve(field).source == "registry"
            assert resolve(field).auto_fix is False

    def test_resolve_unknown_returns_none(self) -> None:
        assert resolve("does_not_exist") is None

    def test_drift_report_line(self) -> None:
        d = Drift("n_layers", 32, 48, resolve("n_layers"))
        assert d.auto_fixable is True
        assert "[AUTO-FIX]" in d.report_line()
        d2 = Drift("useUnifiedKvCache", True, False, resolve("useUnifiedKvCache"))
        assert d2.auto_fixable is False
        assert "[MELDEN]" in d2.report_line()

    def test_auto_fix_rule_validation(self) -> None:
        from field_owner import FieldRule

        with pytest.raises(ValueError):
            FieldRule("config", "registry", auto_fix=True)


def test_identity_build_and_parse_round_trip():
    key = build_model_identity("Publisher", "Model-Basis", "Q4_K_M")

    assert key == "publisher/model-basis@q4_k_m"
    assert decompose_model_identity(key) == ("publisher", "model-basis", "q4_k_m")
