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


def test_legacy_cli_labels_are_normalized_without_becoming_registry_types() -> None:
    assert normalize_speculative_profile({"type": "draft-mtp"}) == {
        "type": "mtp",
        "mode": "integrated",
    }
    assert normalize_speculative_profile({"type": "draft-dflash"}) == {
        "type": "draft",
        "method": "dflash",
    }
