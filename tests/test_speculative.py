from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from speculative import (
    classify_lms_speculative_values,
    companion_role,
    llama_cpp_spec_type,
    normalize_speculative_profile,
)


def test_integrated_mtp_has_no_companion_role() -> None:
    profile = normalize_speculative_profile({"type": "mtp", "mode": "integrated"})

    assert profile == {"type": "mtp", "mode": "integrated"}
    assert companion_role(profile) is None
    assert llama_cpp_spec_type(profile) == "draft-mtp"


def test_separate_mtp_has_mtp_companion_role() -> None:
    profile = classify_lms_speculative_values(
        {
            "draft_mtp_sidecar": True,
            "draft_model_reference": "publisher/model/mtp-model-Q8_0.gguf",
        }
    )

    assert profile["type"] == "mtp"
    assert profile["mode"] == "separate"
    assert companion_role(profile) == "mtp"
    assert llama_cpp_spec_type(profile) == "draft-mtp"


def test_dflash_is_a_draft_llm_not_mtp() -> None:
    profile = classify_lms_speculative_values(
        {
            "draft_dflash_sidecar": True,
            "draft_model_reference": "publisher/model/dflash-q4_0.gguf",
        }
    )

    assert profile["type"] == "draft"
    assert profile["method"] == "dflash"
    assert companion_role(profile) == "draft"
    assert llama_cpp_spec_type(profile) == "draft-dflash"


def test_drafter_reference_defaults_to_simple_method() -> None:
    profile = classify_lms_speculative_values({"draft_model_reference": "publisher/small-compatible-model-Q4_K_M.gguf"})

    assert profile["type"] == "draft"
    assert profile["method"] == "simple"
    assert llama_cpp_spec_type(profile) == "draft-simple"


def test_dspark_reference_is_not_downgraded_to_generic_drafter() -> None:
    profile = classify_lms_speculative_values({"draft_model_reference": "publisher/target-DSpark2-Q4_K_M.gguf"})

    assert profile["type"] == "draft"
    assert profile["method"] == "dspark"
    assert llama_cpp_spec_type(profile) == "draft-dspark"


def test_explicit_lms_dspark_selection_overrides_helper_architecture_label() -> None:
    profile = classify_lms_speculative_values(
        {
            "draft_dspark_sidecar": True,
            "draft_model_reference": "LiquidAI/LFM2.5-8B-A1B-DSpark-Q8_0.gguf",
            "helper_architecture": "dflash",
        }
    )

    assert profile["type"] == "draft"
    assert profile["method"] == "dspark"
    assert llama_cpp_spec_type(profile) == "draft-dspark"


def test_drafter_method_alias_normalizes_to_simple() -> None:
    assert normalize_speculative_profile({"type": "draft", "method": "drafter"}) == {
        "type": "draft",
        "method": "simple",
    }


def test_legacy_cli_labels_are_normalized_without_becoming_registry_types() -> None:
    assert normalize_speculative_profile({"type": "draft-mtp"}) == {
        "type": "mtp",
        "mode": "integrated",
    }
    assert normalize_speculative_profile({"type": "draft-dflash"}) == {
        "type": "draft",
        "method": "dflash",
    }


def test_explicit_invalid_method_is_preserved_for_validation_not_guessed() -> None:
    profile = normalize_speculative_profile({"type": "draft", "method": "typo", "draft_model_reference": "dflash.gguf"})
    assert profile["method"] == "typo"
    assert companion_role(profile) == "draft"
    assert llama_cpp_spec_type(profile) is None


def test_pairing_provenance_survives_profile_normalization() -> None:
    pairing = {"evidence_path": "pair.json", "evidence_sha256": "a" * 64}
    assert (
        normalize_speculative_profile({"type": "draft", "method": "dflash", "pairing": pairing})["pairing"] == pairing
    )
