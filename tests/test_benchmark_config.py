"""Tests for benchmark_config.py temperature/sampling logic (Sampling-Design 2026-08-06).

Covers MODEL_CATEGORY_SAMPLING > Kategorie-/Thinking-Defaults, JSON-temp
IGNORIERT (GUI-only), _source-Herkunft und Thinking-Klassifikation.
"""

import pytest

import benchmark_config as bc
from benchmark_config import get_model_config


@pytest.fixture(autouse=True)
def _no_real_lms_files(mocker):
    """Never touch the real LM Studio config dir in unit tests.

    Tests that need a JSON-config dict re-patch _lms_generation_config.
    """
    mocker.patch.object(bc, "_lms_generation_config", return_value=None)
    return None


class TestCategoryDefaults:
    def test_unknown_model_falls_back_to_category_defaults(self):
        cfg = get_model_config("unknown/never-heard-8b", category="coding")
        assert cfg["temperature"] == 0.2
        assert cfg["top_p"] == 1.0
        assert cfg["max_tokens"] == 4096
        assert cfg["_source"] == "category-default"

    def test_category_defaults_per_category(self):
        expected = {
            "coding": (0.2, 1.0),
            "knowledge": (0.6, 1.0),
            "agentic": (0.6, 0.95),
            "math": (0.7, 0.95),
        }
        for cat, (temp, top_p) in expected.items():
            cfg = get_model_config("unknown/never-heard-8b", category=cat)
            assert (cfg["temperature"], cfg["top_p"]) == (temp, top_p)

    def test_invalid_category_falls_back_to_coding(self):
        cfg = get_model_config("unknown/never-heard-8b", category="bogus")
        assert cfg["temperature"] == 0.2
        assert cfg["_source"] == "category-default"


class TestSamplingTable:
    def test_granite_row(self):
        cfg = get_model_config("ibm-granite/granite-4.1-8b", category="coding")
        assert (cfg["temperature"], cfg["top_p"]) == (0.0, 1.0)
        assert cfg["_source"] == "benchmark-table"

    def test_gpt_oss_row(self):
        cfg = get_model_config("openai/gpt-oss-20b", category="math")
        assert (cfg["temperature"], cfg["top_p"]) == (1.0, 1.0)
        assert cfg["_source"] == "benchmark-table"

    def test_per_category_row_glm_4_7(self):
        expected = {
            "coding": (0.7, 1.0),
            "knowledge": (1.0, 0.95),
            "agentic": (0.7, 0.95),
            "math": (1.0, 0.95),
        }
        for cat, (temp, top_p) in expected.items():
            cfg = get_model_config("unsloth/glm-4.7-flash", category=cat)
            assert (cfg["temperature"], cfg["top_p"]) == (temp, top_p)

    def test_partial_row_falls_back_to_category_default(self):
        # qwen2.5-coder: nur knowledge/agentic/math-Zellen belegt
        cfg = get_model_config("qwen/qwen2.5-coder-14b-instruct@q5_0", category="coding")
        assert (cfg["temperature"], cfg["top_p"]) == (0.2, 1.0)
        assert cfg["_source"] == "category-default"
        cfg = get_model_config("qwen/qwen2.5-coder-14b-instruct@q5_0", category="knowledge")
        assert (cfg["temperature"], cfg["top_p"]) == (0.7, 0.8)
        assert cfg["_source"] == "benchmark-table"

    def test_quant_suffix_still_matches_row(self):
        for key in (
            "qwen/qwen2.5-coder-14b-instruct",
            "qwen/qwen2.5-coder-14b-instruct@q5_0",
            "qwen/qwen2.5-coder-14b-instruct@q6_k",
        ):
            cfg = get_model_config(key, category="math")
            assert (cfg["temperature"], cfg["top_p"]) == (0.7, 0.8)

    def test_variant_suffix_still_matches_row(self):
        # -qat/-ud/-imatrix-Suffixe werden im normalisierten Key gestrippt
        for key in ("google/gemma-4-12b-it-qat", "unsloth/gemma-4-26b-a4b-it"):
            cfg = get_model_config(key, category="agentic")
            assert (cfg["temperature"], cfg["top_p"]) == (1.0, 0.95)

    def test_autoround_repack_matches_row(self):
        cfg = get_model_config("intel/qwen3-30b-a3b-instruct-2507-q2ks-mixed-autoround", category="coding")
        assert (cfg["temperature"], cfg["top_p"]) == (0.7, 0.8)
        assert cfg["_source"] == "registry-sampling"


class TestSamplingRowMatcher:
    def test_exact_and_prefix_match(self):
        assert bc._model_sampling_row("unsloth/qwen3-coder-30b-a3b-instruct") is not None
        assert bc._model_sampling_row("mradermacher/qwen3-coder-reap-25b-a3b-i1") is not None
        assert bc._model_sampling_row("lmstudio-community/deepseek-coder-v2-lite-instruct") is not None

    def test_no_match(self):
        assert bc._model_sampling_row("mistralai/unknown-3b") is None
        assert bc._model_sampling_row("") is None

    def test_row_contents(self):
        row = bc._model_sampling_row("openai/gpt-oss-20b")
        assert row["coding"] == (1.0, 1.0)
        row = bc._model_sampling_row("qwen/qwen2.5-coder-14b-instruct@q5_0")
        assert row["math"] == (0.7, 0.8)
        assert "coding" not in row


class TestRegistrySampling:
    """Reader liest Registry-`sampling:`-Block (SSOT, Variante A)."""

    def test_registry_block_reads_researched_values(self):
        # gemma-4-12b: Registry-Block 1.0/0.95 (Research), NICHT Platzhalter
        cfg = get_model_config("unsloth/gemma-4-12b-it-qat", category="coding")
        assert (cfg["temperature"], cfg["top_p"]) == (1.0, 0.95)
        assert cfg["_source"] == "registry-sampling"

    def test_registry_block_per_category_ernie(self):
        # ernie: nur knowledge/agentic/math recherchiert; coding -> Fallback
        cfg = get_model_config("noctrex/ernie-4.5-21b-a3b-pt_moe", category="knowledge")
        assert (cfg["temperature"], cfg["top_p"]) == (0.8, 1.0)
        assert cfg["_source"] == "registry-sampling"
        cfg = get_model_config("noctrex/ernie-4.5-21b-a3b-pt_moe", category="coding")
        assert (cfg["temperature"], cfg["top_p"]) == (0.2, 1.0)  # category-default
        assert cfg["_source"] == "category-default"

    def test_registry_block_partial_row_falls_back(self):
        # kimi-linear: kein agentic im Block -> Tabellen-/Kategorie-Fallback
        cfg = get_model_config("mradermacher/kimi-linear-reap-35b-a3b-instruct-i1", category="coding")
        assert (cfg["temperature"], cfg["top_p"]) == (0.6, 0.95)
        assert cfg["_source"] == "registry-sampling"

    def test_registry_glm_46v(self):
        cfg = get_model_config("zai-org/glm-4.6v-flash", category="math")
        assert (cfg["temperature"], cfg["top_p"]) == (0.8, 0.6)
        assert cfg["_source"] == "registry-sampling"

    def test_quant_suffix_matches_registry_block(self):
        cfg = get_model_config("qwen/qwen3-14b@q6_k", category="math")
        assert (cfg["temperature"], cfg["top_p"]) == (0.6, 0.95)
        assert cfg["_source"] == "registry-sampling"

    def test_no_sampling_block_falls_back_to_table(self):
        # gpt-oss: kein sampling:-Block -> Tabelle (1.0/1.0)
        cfg = get_model_config("openai/gpt-oss-20b", category="math")
        assert (cfg["temperature"], cfg["top_p"]) == (1.0, 1.0)
        assert cfg["_source"] == "benchmark-table"

    def test_unknown_model_no_registry_no_table(self):
        cfg = get_model_config("unknown/never-heard-8b", category="coding")
        assert cfg["_source"] == "category-default"


class TestThinkingRuns:
    def test_thinking_model_flat_defaults(self):
        cfg = get_model_config(
            "lmstudio-community/deepseek-r1-distill-qwen-14b",
            category="coding",
            is_thinking_enabled=True,
        )
        assert (cfg["temperature"], cfg["top_p"]) == (0.6, 0.95)
        assert cfg["enable_thinking"] is True
        assert cfg["_source"] == "thinking-default"

    def test_thinking_flat_applies_to_all_categories(self):
        for cat in ("coding", "knowledge", "agentic", "math"):
            cfg = get_model_config("qwen/qwen3-14b", category=cat, is_thinking_enabled=True)
            assert (cfg["temperature"], cfg["top_p"]) == (0.6, 0.95)

    def test_thinking_model_with_table_row(self):
        # Gemma-4: dokumentierte Ausnahme 1.0/0.95 statt flat 0.6/0.95.
        # Liegt in der Registry als sampling:-Block vor (SSOT).
        cfg = get_model_config("google/gemma-4-12b-it-qat", category="coding", is_thinking_enabled=True)
        assert (cfg["temperature"], cfg["top_p"]) == (1.0, 0.95)
        assert cfg["_source"] == "registry-sampling"

    def test_thinking_gpt_oss_row(self):
        cfg = get_model_config("openai/gpt-oss-20b", category="coding", is_thinking_enabled=True)
        assert (cfg["temperature"], cfg["top_p"]) == (1.0, 1.0)

    def test_instruct_model_not_affected_by_thinking_flag(self):
        cfg = get_model_config("unsloth/glm-4.7-flash", category="coding", is_thinking_enabled=True)
        assert (cfg["temperature"], cfg["top_p"]) == (0.7, 1.0)

    def test_thinking_named_model_detected(self):
        cfg = get_model_config(
            "intel/qwen3-30b-a3b-thinking-2507-q2ks-mixed-autoround",
            category="coding",
            is_thinking_enabled=True,
        )
        assert (cfg["temperature"], cfg["top_p"]) == (0.6, 0.95)
        assert cfg["_source"] == "thinking-default"

    def test_mirothinker_detected(self):
        cfg = get_model_config(
            "intel/mirothinker-v1.5-30b-q2ks-mixed-autoround",
            category="coding",
            is_thinking_enabled=True,
        )
        assert (cfg["temperature"], cfg["top_p"]) == (0.6, 0.95)
        assert cfg["_source"] == "thinking-default"

    def test_thinking_without_flag_uses_category_defaults(self):
        cfg = get_model_config("qwen/qwen2.5-7b-instruct", category="coding", is_thinking_enabled=False)
        assert cfg["temperature"] == 0.2
        assert cfg["_source"] == "category-default"


class TestLmsJsonMerge:
    def test_json_temp_top_p_ignored_for_benchmarks(self, mocker):
        lms = {
            "temperature": 0.9,
            "top_p": 0.5,
            "top_k": 40,
            "min_p": 0.1,
            "enable_thinking": True,
        }
        mocker.patch.object(bc, "_lms_generation_config", return_value=lms)
        cfg = get_model_config("ibm-granite/granite-4.1-8b", category="coding")
        assert (cfg["temperature"], cfg["top_p"]) == (0.0, 1.0)  # Tabellen-Zelle
        assert cfg["top_k"] == 40
        assert cfg["min_p"] == 0.1
        assert cfg["enable_thinking"] is True
        assert cfg["_source"] == "benchmark-table"

    def test_non_temp_json_fields_merge_for_category_model(self, mocker):
        lms = {"top_k": 20, "enable_thinking": False}
        mocker.patch.object(bc, "_lms_generation_config", return_value=lms)
        cfg = get_model_config("unknown/never-heard-8b", category="math")
        assert (cfg["temperature"], cfg["top_p"]) == (0.7, 0.95)
        assert cfg["top_k"] == 20
        assert cfg["enable_thinking"] is False

    def test_thinking_flag_forced_even_if_json_disables(self, mocker):
        lms = {"enable_thinking": False, "top_k": 20}
        mocker.patch.object(bc, "_lms_generation_config", return_value=lms)
        cfg = get_model_config(
            "lmstudio-community/deepseek-r1-distill-qwen-14b",
            category="coding",
            is_thinking_enabled=True,
        )
        assert cfg["enable_thinking"] is True
        assert cfg["top_k"] == 20
