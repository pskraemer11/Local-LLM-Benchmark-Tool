"""Tests for benchmark_config.py temperature/sampling logic (Registry SSOT).

Covers Registry-Sampling > Kategorie-/Thinking-Defaults, JSON-temp
IGNORIERT (GUI-only), _source-Herkunft und Thinking-Klassifikation.
"""

from typing import Any

import pytest

import benchmark_config as bc
from benchmark_config import get_model_config


@pytest.fixture(autouse=True)
def _no_real_lms_files(mocker: Any) -> None:
    """Never touch the real LM Studio config dir in unit tests.

    Tests that need a JSON-config dict re-patch _lms_generation_config.
    """
    mocker.patch.object(bc, "_lms_generation_config", return_value=None)
    # Machine-local web refreshes must not change unit-test expectations.
    # These synthetic profiles test precedence, not manufacturer recommendations.
    def profile(temperature, top_p, **extra):
        return {category: {"temperature": temperature, "top_p": top_p, **extra}
                for category in ("coding", "knowledge", "agentic", "math")}

    qwen = profile(0.7, 0.8)
    qwen.update(sampling_research_status="confirmed", thinking={"temperature": 0.6, "top_p": 0.95})
    mocker.patch.object(bc, "_load_quant_registry", return_value={
        "byteshape/qwen3.8-27b@iq4_xs": {"reasoning": "thinking", "sampling": qwen},
        "ibm-granite/granite-4.2-8b@q6_k": {"sampling": profile(1.0, 0.95)},
        "noctrex/ernie-4.5-21b-a3b-pt_moe@iq4_nl": {"sampling": profile(0.8, 0.95)},
        "qwen/qwen3-14b@q6_k": {"reasoning": "thinking", "sampling": profile(0.6, 0.95)},
        "unsloth/gemma-4-12b-it@q6_k": {
            "reasoning": "thinking", "architecture_family": "gemma4", "blueprint": "gemma_reasoning",
            "sampling": {**profile(1.0, 0.95, top_k=64), "sampling_research_status": "confirmed",
                         "thinking": {"temperature": 0.6, "top_p": 0.95}},
        },
        "lmstudio-community/qwen/qwen3.5-9b@q6_k": {"reasoning": "thinking"},
        "unsloth/gemma-4-26b-a4b-it@iq3_xxs": {"reasoning": "thinking"},
        "intel/qwen3-30b-a3b-instruct-2507-q2ks-mixed-autoround@q2_k_s": {"sampling": profile(0.7, 0.8)},
    })
    return None


def _gpt_oss_test_entry() -> dict[str, Any]:
    """Return the minimal GPT-OSS policy needed by registry-backed tests."""
    sampling = {
        category: {"temperature": 1.0, "top_p": 1.0}
        for category in ("coding", "knowledge", "agentic", "math")
    }
    return {
        "blueprint": "gptoss_reasoning",
        "reasoning": "thinking",
        "sampling_source": "web-research",
        "sampling": sampling,
    }


class TestCategoryDefaults:
    def test_unknown_model_falls_back_to_category_defaults(self):
        cfg = get_model_config("unknown/never-heard-8b", category="coding")
        assert cfg["temperature"] == 0.6
        assert cfg["top_p"] == 0.95
        assert cfg["max_tokens"] == 4096
        assert cfg["_source"] == "category-default"

    def test_category_defaults_per_category(self):
        expected = {
            "coding": (0.6, 0.95),
            "knowledge": (0.6, 0.95),
            "agentic": (0.6, 0.95),
            "math": (0.7, 0.95),
        }
        for cat, (temp, top_p) in expected.items():
            cfg = get_model_config("unknown/never-heard-8b", category=cat)
            assert (cfg["temperature"], cfg["top_p"]) == (temp, top_p)

    def test_invalid_category_falls_back_to_coding(self):
        cfg = get_model_config("unknown/never-heard-8b", category="bogus")
        assert cfg["temperature"] == 0.6
        assert cfg["_source"] == "category-default"


class TestRegistrySamplingIsHistoryNotRuntime:
    """The Registry `sampling` block keeps the research history.

    Since 19.10.2026 the block stays readable and documented, but it no longer
    decides the runtime parameters: the fixed class policy does
    (docs/Benchmark-Sampling-Policy_en.md). The per-model research covered
    about 30 percent of the models with usable values, and greedy decoding is
    unsuitable for the local low-bit quantization.
    """

    def test_registry_block_does_not_override_the_class_policy(self):
        # gemma-4-12b carries a researched 1.0/0.95 profile in the Registry.
        # The runtime uses the class policy instead.
        cfg = get_model_config("unsloth/gemma-4-12b-it-qat", category="coding")
        assert (cfg["temperature"], cfg["top_p"]) == (0.6, 0.95)
        assert cfg["_source"] == "category-default"

    def test_registry_block_does_not_set_optional_sampling_fields(self):
        # top_k and min_p belong to the class policy, not to the researched
        # Registry block.
        cfg = get_model_config("unsloth/gemma-4-12b-it-qat", category="coding")
        assert cfg["top_k"] == 20
        assert cfg["min_p"] == 0.0

    def test_class_policy_applies_to_every_category(self):
        expected = {
            "coding": 0.6,
            "math": 0.7,
            "knowledge": 0.6,
            "agentic": 0.6,
        }
        for category, temperature in expected.items():
            cfg = get_model_config("unsloth/gemma-4-12b-it-qat", category=category)
            assert cfg["temperature"] == temperature, category
            assert cfg["_source"] == "category-default"

    def test_registry_block_remains_readable_for_audit(self, mocker):
        # The research history stays available in the Registry itself.
        mocker.patch.object(
            bc,
            "_load_quant_registry",
            return_value={
                "unsloth/gemma-4-12b-it-qat": {
                    "sampling": {"coding": {"temperature": 1.0, "top_p": 0.95}}
                }
            },
        )
        entry = bc._load_quant_registry().get("unsloth/gemma-4-12b-it-qat", {})
        sampling = entry.get("sampling")
        assert isinstance(sampling, dict)
        assert sampling["coding"]["temperature"] == 1.0

    def test_gpt_oss_registry_block_does_not_override_the_class_policy(self, mocker):
        registry = {"openai/gpt-oss-20b@mxfp4": _gpt_oss_test_entry()}
        mocker.patch.object(bc, "_load_quant_registry", return_value=registry)
        cfg = get_model_config("openai/gpt-oss-20b", category="math")
        assert (cfg["temperature"], cfg["top_p"]) == (0.7, 0.95)
        assert cfg["_source"] == "category-default"

    def test_no_sampling_block_falls_back_to_category_defaults(self):
        cfg = get_model_config(
            "intel/qwen3-30b-a3b-thinking-2507-q2ks-mixed-autoround",
            category="coding",
        )
        assert (cfg["temperature"], cfg["top_p"]) == (0.6, 0.95)
        assert cfg["_source"] == "category-default"


class TestBlacklistIdentityScope:
    def test_publisher_keywords_do_not_blacklist_model(self):
        model_key = "peculiar-ragdoll/tiel-coder-35b-a3b@iq3_xxs"

        assert not bc.is_blacklisted_model_name(model_key)
        assert bc.is_registry_candidate({"type": "llm", "modelKey": model_key})

    def test_basis_name_keywords_still_blacklist_models(self):
        assert bc.is_blacklisted_model_name("publisher/rag-retriever-7b@q4_k_m")
        assert bc.is_blacklisted_model_name("publisher/ocr-model-7b@q8_0")
        assert bc.is_blacklisted_model_name("publisher/embed-model-7b@q8_0")

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
        assert cfg["max_tokens"] == 4096
        assert cfg["_source"] == "thinking-default"

    def test_registry_thinking_model_defaults_to_4096_even_without_forcing_thinking(self):
        cfg = get_model_config(
            "lmstudio-community/qwen/qwen3.5-9b@q6_k",
            category="coding",
            is_thinking_enabled=False,
        )
        assert cfg["enable_thinking"] is False
        assert cfg["max_tokens"] == 4096

    def test_thinking_flat_applies_to_all_categories(self):
        for cat in ("coding", "knowledge", "agentic", "math"):
            cfg = get_model_config("qwen/qwen3-14b", category=cat, is_thinking_enabled=True)
            assert (cfg["temperature"], cfg["top_p"]) == (0.6, 0.95)

    def test_thinking_model_with_table_row(self):
        # Die explizite -qat-Variante wird jetzt deterministisch auf den
        # eindeutigen QAT-Registry-Key aufgeloest; dessen bestaetigtes Coding-
        # Profil ist 0.6/0.95. Ein unsloth-Basismodell ohne -qat bleibt bei
        # 1.0/0.95 (siehe TestRegistrySampling).
        cfg = get_model_config("google/gemma-4-12b-it-qat", category="coding", is_thinking_enabled=True)
        assert (cfg["temperature"], cfg["top_p"]) == (0.6, 0.95)
        assert cfg["_source"] == "thinking-default"

    def test_thinking_gpt_oss_row(self, mocker):
        registry = {"openai/gpt-oss-20b@mxfp4": _gpt_oss_test_entry()}
        mocker.patch.object(bc, "_load_quant_registry", return_value=registry)
        cfg = get_model_config("openai/gpt-oss-20b", category="coding", is_thinking_enabled=True)
        assert (cfg["temperature"], cfg["top_p"]) == (0.6, 0.95)

    def test_instruct_model_not_affected_by_thinking_flag(self, mocker):
        mocker.patch.object(bc, "_load_quant_registry", return_value={"unsloth/glm-4.7-flash@q3_k_s": {
            "reasoning": "instruct", "sampling": {"coding": {"temperature": 0.7, "top_p": 1.0}},
        }})
        cfg = get_model_config("unsloth/glm-4.7-flash", category="coding", is_thinking_enabled=True)
        assert (cfg["temperature"], cfg["top_p"]) == (0.6, 0.95)

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
        assert cfg["temperature"] == 0.6
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
        cfg = get_model_config("ibm-granite/granite-4.2-8b", category="coding")
        assert (cfg["temperature"], cfg["top_p"]) == (0.6, 0.95)  # Klassen-Policy
        assert cfg["top_k"] == 20
        assert cfg["min_p"] == 0.0
        assert cfg["enable_thinking"] is True
        assert cfg["_source"] == "category-default"

    def test_registry_optional_sampling_fields_override_gui_values(self, mocker):
        mocker.patch.object(
            bc,
            "_load_quant_registry",
            return_value={
                "example/model@q4_k_m": {
                    "sampling": {
                        "coding": {
                            "temperature": 0.7,
                            "top_p": 0.9,
                            "top_k": 40,
                            "min_p": 0.05,
                        }
                    }
                }
            },
        )
        mocker.patch.object(bc, "_lms_generation_config", return_value={"top_k": 20, "min_p": 0.1})

        cfg = get_model_config("example/model@q4_k_m", category="coding")

        # The class policy owns the sampling fields; neither the researched
        # Registry block nor the GUI artifact may override them.
        assert cfg["top_k"] == 20
        assert cfg["min_p"] == 0.0

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


class TestGemmaThinkingByCategory:
    """Kategorie-basierte Thinking-Steuerung via Blueprint-Feld
    enable_thinking_by_category (Fix 15.08.): Gemma hat in JSON-Configs
    budgetTokens=2048 (checked) -> ohne die Kategorie-Steuerung waere
    enable_thinking in ALLEN Kategorien True. Erwartung: Coding/Agentic
    False, Math/Knowledge True.
    """

    def test_gemma_coding_off(self):
        cfg = get_model_config("unsloth/gemma-4-12b-it@q6_k", category="coding")
        assert cfg["enable_thinking"] is False

    def test_gemma_agentic_off(self):
        cfg = get_model_config("unsloth/gemma-4-12b-it@q6_k", category="agentic")
        assert cfg["enable_thinking"] is False

    def test_gemma_math_on(self):
        cfg = get_model_config("unsloth/gemma-4-12b-it@q6_k", category="math")
        assert cfg["enable_thinking"] is True

    def test_gemma_knowledge_on(self):
        cfg = get_model_config("unsloth/gemma-4-12b-it@q6_k", category="knowledge")
        assert cfg["enable_thinking"] is True

    def test_gemma_thinking_flag_forces_on(self):
        # --thinking-Flag gewinnt ueber die Kategorie-Steuerung (coding=False):
        # der Force-Override steht NACH dem bp_thinking-Block.
        cfg = get_model_config(
            "unsloth/gemma-4-12b-it@q6_k",
            category="coding",
            is_thinking_enabled=True,
        )
        assert cfg["enable_thinking"] is True

    def test_gemma_budget_config_overridden_by_category(self, mocker):
        # JSON-Config mit budgetTokens=2048 (checked) wuerde enable_thinking
        # setzen; die Kategorie-Steuerung (coding=False) muss das ueberschreiben.
        lms = {
            "enable_thinking": True,
            "top_k": 20,
            "llm.prediction.reasoning.budgetTokens": {"checked": True, "value": 2048},
        }
        mocker.patch.object(bc, "_lms_generation_config", return_value=lms)
        cfg = get_model_config("unsloth/gemma-4-12b-it@q6_k", category="coding")
        assert cfg["enable_thinking"] is False
        # top_k belongs to the class policy, not to the GUI artifact.
        assert cfg["top_k"] == 20
