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

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from field_owner import FIELD_OWNERSHIP, Drift, auto_fix_fields, resolve
from model_identity import (
    MODEL_FAMILIES,
    classify_reasoning_by_family,
    match_registry_key,
    normalize_for_config,
    normalize_lms_model_name,
    normalize_model_name,
    normalize_variants,
    normalized_lms_key,
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


class TestNormalizeForConfig:
    def test_quant_suffix_stripped(self) -> None:
        assert normalize_for_config("unsloth/ernie-4.5-21b-a3b-pt@iq4_nl") == "ernie-4-5-21b-a3b-pt"
        assert normalize_for_config("mradermacher/gemma-4-19b-a4b-it-reap-i1@q4_k_m") == "gemma-4-19b-a4b-it-reap-i1"

    def test_variant_suffix_stripped(self) -> None:
        assert normalize_for_config("gemma-4-12b-it-qat") == "gemma-4-12b-it"

    def test_dir_quant_suffixes_stripped(self) -> None:
        assert normalize_for_config("ERNIE-4.5-21B-A3B-PT-GGUF") == "ernie-4-5-21b-a3b-pt"
        assert normalize_for_config("Model-MXFP4") == "model"


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
        # "GLM-REAP-..." ist Praefix von BEIDEN glm-4.7-flash Keys -> mehrdeutig
        assert match_registry_key("GLM-4.7-Flash-REAP-23B-A3B-Q4_K_S", _REGISTRY_KEYS) is None

    def test_unknown_model_returns_none(self) -> None:
        assert match_registry_key("gemma-4-26b-a4b-it", _REGISTRY_KEYS) is None

    def test_empty_inputs(self) -> None:
        assert match_registry_key("", _REGISTRY_KEYS) is None
        assert match_registry_key("glm-4.7-flash", []) is None


# ─────────────────────────────────────────────────────────────────────
# Familien-Klassifikation
# ─────────────────────────────────────────────────────────────────────


class TestFamilies:
    def test_map_order_qwen35_before_qwen3(self) -> None:
        # qwen35 MUSS vor qwen3 geprueft werden (Substring-Overlap)
        keys = [ak for fam in MODEL_FAMILIES for ak in fam.arch_keys]
        assert keys.index("qwen35") < keys.index("qwen3")

    def test_qwen35_default_thinking(self) -> None:
        assert classify_reasoning_by_family("qwen3.5-9b", "qwen35") == "thinking"

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
        assert set(auto_fix_fields()) == {"n_layers", "hidden_dim", "max_context_length", "arch", "file_size_bytes"}

    def test_config_fields_report_only(self) -> None:
        for field in ("num_parallel", "useUnifiedKvCache", "offload", "context_length"):
            assert resolve(field) is not None
            assert resolve(field).source == "config"
            assert resolve(field).auto_fix is False

    def test_resolve_unknown_returns_none(self) -> None:
        assert resolve("does_not_exist") is None

    def test_drift_report_line(self) -> None:
        d = Drift("n_layers", 32, 48, resolve("n_layers"))
        assert d.auto_fixable is True
        assert "[AUTO-FIX]" in d.report_line()
        d2 = Drift("num_parallel", 4, 1, resolve("num_parallel"))
        assert d2.auto_fixable is False
        assert "[MELDEN]" in d2.report_line()

    def test_auto_fix_rule_validation(self) -> None:
        from field_owner import FieldRule

        with pytest.raises(ValueError):
            FieldRule("config", "registry", auto_fix=True)
