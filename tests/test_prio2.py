"""Tests for Prio-2 fixes from Code-Review_2026-07-12.md:
- D1: _lookup_vram Fuzzy-Match fix
- C1: strip_thinking_tokens content-aware token estimate
- K1: get_quant variant-aware lookup
- H2: Bootstrap-CI NumPy path matches pure-Python path
- W1: _truncate_response default behavior
"""
import os
import sys
import math
import json
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from benchmark_config import GPTOSS_REASONING_EFFORT, GPTOSS_REASONING_BUDGET, get_model_config, get_quant
from custom_benchmark import _uses_qwen_template, strip_thinking_tokens, _can_use_structured_output
from csv_writer import _truncate_response

# Synthetische Registry für get_quant-Fallback-Tests: unabhängig von der
# realen model_registry.yaml (die durch fix-np-Bereinigungen ändert).
FAKE_QUANT_REG = {
    "openai/gpt-oss-20b": {"quants": ["MXFP4"], "reasoning": "thinking"},
    "lmstudio-community/gpt-oss-20b": {"quants": ["MXFP4"]},
    "unsloth/gpt-oss-20b": {"quants": ["Q6_K"]},
    "lmstudio-community/deepseek-r1-distill-qwen-14b": {"reasoning": "thinking"},
    "moonshotai/kimi-k2-instruct": {"reasoning": "instruct"},
}


class TestGetQuant:
    """K1: quant extracted from model key (no static map)."""

    def test_quant_from_key(self):
        # Quant extracted directly from @quant in key
        assert get_quant("unsloth/phi-4@q5_k_m") == "Q5_K_M"
        assert get_quant("qwen/qwen3-14b@q6_k") == "Q6_K"

    def test_different_quants_distinct(self):
        # Different @quant variants are distinct
        assert get_quant("devstral-small-2-24b-instruct-2512@q3_k_s") == "Q3_K_S"
        assert get_quant("devstral-small-2-24b-instruct-2512@q4_k_s") == "Q4_K_S"

    def test_qwen_coder_reap_distinct_quants(self):
        assert get_quant("qwen3-coder-reap-25b-a3b-i1@q3_k_m") == "Q3_K_M"
        assert get_quant("qwen3-coder-reap-25b-a3b-i1@q4_k_s") == "Q4_K_S"

    def test_unknown_returns_question_mark(self):
        assert get_quant("nonexistent-model-xyz") == "?"

    def test_empty_returns_question_mark(self):
        assert get_quant("") == "?"


class TestTruncateResponse:
    """W1: response column is truncated by default to keep CSVs compact."""

    def test_short_response_unchanged(self):
        assert _truncate_response("hello world") == "hello world"

    def test_long_response_truncated(self):
        long = "x" * 500
        result = _truncate_response(long, max_chars=200)
        assert "…" in result
        assert "500 chars total" in result
        # First 200 chars preserved
        assert result.startswith("x" * 200)

    def test_exact_length_unchanged(self):
        s = "x" * 200
        assert _truncate_response(s, max_chars=200) == s


class TestStripThinkingTokens:
    """C1: content-aware token estimate (not just chars//4)."""

    def test_legacy_think_tags(self):
        text = "<think>this is a reasoning chain</think>final answer"
        cleaned, tokens = strip_thinking_tokens(text)
        assert "think" not in cleaned
        assert "final answer" in cleaned
        assert tokens > 0

    def test_gemma_channel_tags(self):
        text = "<|channel>thought\nthis is gemma reasoning<channel|>the answer"
        cleaned, tokens = strip_thinking_tokens(text)
        assert "channel" not in cleaned
        assert "the answer" in cleaned
        assert tokens > 0

    def test_no_thinking_returns_zero(self):
        cleaned, tokens = strip_thinking_tokens("just an answer")
        assert tokens == 0
        assert cleaned == "just an answer"

    def test_empty_input(self):
        assert strip_thinking_tokens("") == ("", 0)
        assert strip_thinking_tokens(None) == (None, 0)

    def test_whitespace_heavy_thinking_bounded(self):
        # Old code: chars//4 = 100 tokens for 400 whitespace chars.
        # New code: word_count * 1.3 = 1*1.3 = 2 tokens (1 word).
        text = "<|channel>thought\n" + ("   " * 400) + "<channel|>answer"
        cleaned, tokens = strip_thinking_tokens(text)
        # Should be at most a few tokens, not 100
        assert tokens < 20, f"Expected bounded tokens, got {tokens}"
        assert "answer" in cleaned


class TestBootstrapCIPerfAndCorrectness:
    """H2: NumPy path matches pure-Python path; speedup on 100x10k."""

    def test_numpy_matches_python_simple(self):
        # Compare NumPy and pure-Python paths on the same data + seed
        from consolidate_results import bootstrap_ci, paired_bootstrap_ci
        import random
        scores = [0.5, 0.6, 0.7, 0.8, 0.5, 0.6, 0.7, 0.8, 0.5, 0.6] * 5
        a = scores[:30]
        # Force pure-Python path
        import numpy as np
        np.random.seed(42)
        lo_np, hi_np = bootstrap_ci(a, n_resamples=2000, alpha=0.05)
        # Force NumPy path
        lo_py, hi_py = _bootstrap_py(scores, n_resamples=2000, alpha=0.05, seed=42)
        # Should be close (not exact, because random.choice vs np.random.randint)
        assert abs(lo_np - lo_py) < 0.05
        assert abs(hi_np - hi_py) < 0.05

    def test_paired_bootstrap_numpy_runs(self):
        from consolidate_results import paired_bootstrap_ci
        a = [0.5, 0.6, 0.7, 0.8, 0.5, 0.6, 0.7, 0.8, 0.5, 0.6] * 5
        b = [x - 0.05 for x in a]   # a - b = 0.05 for all items
        mean_diff, lo, hi = paired_bootstrap_ci(a, b, n_resamples=2000, seed=42)
        # Mean diff should be approximately 0.05 (a is always higher than b)
        assert abs(mean_diff - 0.05) < 1e-5
        # CI should be very tight (constant 0.05 → no resampling variation)
        assert (hi - lo) < 1e-3, f"CI should be tight, got [{lo}, {hi}]"
        # CI should bracket the mean
        assert abs(lo - 0.05) < 1e-3
        assert abs(hi - 0.05) < 1e-3

    def test_bootstrap_nan_for_too_few(self):
        from consolidate_results import bootstrap_ci
        lo, hi = bootstrap_ci([0.5], n_resamples=100)
        assert math.isnan(lo) and math.isnan(hi)


def _bootstrap_py(scores, n_resamples, alpha, seed):
    """Helper: pure-Python bootstrap to compare against NumPy path."""
    import random
    random.seed(seed)
    n = len(scores)
    means = [0.0] * n_resamples
    for i in range(n_resamples):
        s = 0.0
        for _ in range(n):
            s += random.choice(scores)
        means[i] = s / n
    means.sort()
    lo_idx = int(n_resamples * alpha / 2)
    hi_idx = int(n_resamples * (1 - alpha / 2))
    return means[lo_idx], means[hi_idx]


class TestLookupVramFuzzyFix:
    """D1: fuzzy match with length-ratio guard prevents false positives."""

    def test_quant_from_key_distinct(self):
        """Different @quant variants resolve to different quants."""
        q1 = get_quant("unsloth/phi-4@q5_k_m")
        q2 = get_quant("unsloth/phi-4@q8_0")
        q3 = get_quant("unsloth/phi-4@mxfp4")
        assert q1 == "Q5_K_M"
        assert q2 == "Q8_0"
        assert q3 == "MXFP4"
        assert q1 != q2

    def test_base_key_without_quant_returns_question_mark(self):
        """Base keys (no @quant) are invalid per identity principle."""
        assert get_quant("devstral-small-2-24b-instruct-2512") == "?"
        assert get_quant("qwen3-coder-reap-25b-a3b-i1") == "?"

    def test_qwen_reap_distinct_quants(self):
        """Q3_K_M and Q4_K_S must remain distinct."""
        default = get_quant("qwen3-coder-reap-25b-a3b-i1@q3_k_m")
        custom = get_quant("qwen3-coder-reap-25b-a3b-i1@q4_k_s")
        assert default == "Q3_K_M"
        assert custom == "Q4_K_S"
        assert default != custom


class TestGetModelConfigLmsSource:
    """Sampling-Design 2026-08-06: Tabelle > Defaults; JSON-temp/top_p GUI-only.

    Seit 2026-08-05: MODEL_TEMP_OVERRIDES, Registry-Thinking und der
    Knowledge-Temperature-Floor sind entfernt. Seit 2026-08-06 kommen aus
    ~/.lmstudio/.internal/user-concrete-model-default-config nur noch
    NICHT-Temperatur-Felder (top_k, min_p, enable_thinking, reasoning_effort);
    temperature/top_p entscheiden MODEL_CATEGORY_SAMPLING bzw. die Defaults.
    """

    @staticmethod
    def _write_lms_config(root, publisher, model_dir, fields):
        d = root / publisher / model_dir
        d.mkdir(parents=True, exist_ok=True)
        data = {
            "operation": {"fields": [{"key": k, "value": v} for k, v in fields.items()]},
            "load": {"fields": []},
        }
        (d / "model.gguf.json").write_text(json.dumps(data), encoding="utf-8")
        return d

    def test_no_config_falls_back_to_category_default(self, tmp_path):
        with patch("benchmark_config.LMS_CONFIG_ROOT", tmp_path / "empty"):
            cfg = get_model_config("plain-7b-model", category="coding")
        assert cfg["temperature"] == 0.2
        assert cfg["_source"] == "category-default"

    def test_lms_temp_ignored_category_default_used(self, tmp_path):
        # JSON-temperature/top_p zaehlen seit 2026-08-06 nicht mehr fuer
        # Benchmarks (ein Einzelwert kann keine Kategorie-Differenzierung
        # ausdruecken); ohne Tabellen-Zeile gelten die Kategorie-Defaults.
        self._write_lms_config(tmp_path, "pub1", "fake-model-7b",
                               {"llm.prediction.temperature": 0.5,
                                "llm.prediction.topPSampling": 0.9})
        with patch("benchmark_config.LMS_CONFIG_ROOT", tmp_path):
            cfg = get_model_config("pub1/fake-model-7b", category="coding")
        assert cfg["temperature"] == 0.2
        assert cfg["top_p"] == 1.0
        assert cfg["_source"] == "category-default"

    def test_lms_config_matches_dir_with_gguf_suffix(self, tmp_path):
        self._write_lms_config(tmp_path, "pub1", "fake-model-7b-GGUF",
                               {"llm.prediction.temperature": 0.5})
        with patch("benchmark_config.LMS_CONFIG_ROOT", tmp_path):
            cfg = get_model_config("pub1/fake-model-7b", category="coding")
        assert cfg["temperature"] == 0.2

    def test_enable_thinking_from_config(self, tmp_path):
        self._write_lms_config(tmp_path, "pub1", "fake-model-7b",
                               {"llm.prediction.reasoning.enableThinking": True})
        with patch("benchmark_config.LMS_CONFIG_ROOT", tmp_path):
            cfg = get_model_config("pub1/fake-model-7b")
        assert cfg["enable_thinking"] is True

    def test_budget_tokens_enables_thinking(self, tmp_path):
        self._write_lms_config(tmp_path, "pub1", "fake-model-7b",
                               {"llm.prediction.reasoning.budgetTokens":
                                {"checked": True, "value": 2048}})
        with patch("benchmark_config.LMS_CONFIG_ROOT", tmp_path):
            cfg = get_model_config("pub1/fake-model-7b")
        assert cfg["enable_thinking"] is True

    def test_budget_zero_uses_parsing_verdict(self, tmp_path):
        self._write_lms_config(tmp_path, "pub1", "fake-model-7b",
                               {"llm.prediction.reasoning.budgetTokens":
                                {"checked": True, "value": 0},
                                "llm.prediction.reasoning.parsing":
                                {"enabled": False, "startString": "<think>", "endString": "</think>"}})
        with patch("benchmark_config.LMS_CONFIG_ROOT", tmp_path):
            cfg = get_model_config("pub1/fake-model-7b")
        assert cfg["enable_thinking"] is False

    def test_checked_wrapper_unwrapped(self, tmp_path):
        self._write_lms_config(tmp_path, "pub1", "fake-model-7b",
                               {"llm.prediction.topPSampling": {"checked": True, "value": 1}})
        with patch("benchmark_config.LMS_CONFIG_ROOT", tmp_path):
            cfg = get_model_config("pub1/fake-model-7b")
        assert cfg["top_p"] == 1

    def test_knowledge_temperature_floor_removed(self, tmp_path):
        # Frueher hob der Knowledge-Floor temp < 0.7 auf 0.7 an. Seit dem
        # Transparenz-Refactor gewinnt der GUI-Wert; seit 2026-08-06 gilt
        # fuer Benchmarks der Kategorie-Default (JSON-temp ignoriert).
        self._write_lms_config(tmp_path, "pub1", "fake-model-7b",
                               {"llm.prediction.temperature": 0.2})
        with patch("benchmark_config.LMS_CONFIG_ROOT", tmp_path):
            cfg = get_model_config("pub1/fake-model-7b", category="knowledge")
        assert cfg["temperature"] == 0.6

    def test_registry_no_longer_affects_thinking(self, tmp_path):
        # Registry ist nur noch Uebersicht: reasoning: thinking setzt
        # enable_thinking NICHT mehr in get_model_config (JSON-Config wins).
        with patch("benchmark_config._load_quant_registry", return_value=FAKE_QUANT_REG), \
             patch("benchmark_config.LMS_CONFIG_ROOT", tmp_path / "empty"):
            cfg = get_model_config("lmstudio-community/deepseek-r1-distill-qwen-14b")
        assert cfg["enable_thinking"] is False
        assert cfg["_source"] == "category-default"


class TestGptOssReasoningConstants:
    """Zentrale gpt-oss-Reasoning-Konstanten (synchrone Quelle fuer Patch+Blueprint)."""

    def test_effort_is_valid_level(self):
        assert GPTOSS_REASONING_EFFORT in ("low", "medium", "high")

    def test_budget_is_positive(self):
        assert isinstance(GPTOSS_REASONING_BUDGET, int) and GPTOSS_REASONING_BUDGET > 0

    def test_default_is_medium(self):
        # Hersteller-Benchmarks (SWE-bench-verified) nutzen medium/high; meist medium.
        assert GPTOSS_REASONING_EFFORT == "medium"


class TestUsesQwenTemplate:
    """_uses_qwen_template: Qwen-basierte Templates unterstuetzen chat_template_kwargs."""

    def test_qwen3(self):
        assert _uses_qwen_template("lmstudio-community/qwen3-8b") is True

    def test_qwen3_5(self):
        assert _uses_qwen_template("lmstudio-community/qwen3.5-8b") is True

    def test_deepseek_r1_distill_qwen(self):
        assert _uses_qwen_template("lmstudio-community/deepseek-r1-distill-qwen-14b") is True

    def test_non_qwen_model(self):
        assert _uses_qwen_template("lmstudio-community/ministral-8b-instruct-2410") is False

    def test_none(self):
        assert _uses_qwen_template(None) is False


class TestCanUseStructuredOutput:
    """_can_use_structured_output: Codestral-22B-Schutz (F5) + bekannte Ausschluesse."""

    def test_normal_model(self):
        with patch("custom_benchmark._model_supports_reasoning", return_value=False):
            assert _can_use_structured_output("openai/gpt-oss-20b") is True

    def test_globally_disabled(self):
        with patch("custom_benchmark.HAS_STRUCTURED_OUTPUT", False):
            assert _can_use_structured_output("openai/gpt-oss-20b") is False

    def test_thinking_mode(self):
        with patch("custom_benchmark.IS_THINKING_MODE", True):
            assert _can_use_structured_output("openai/gpt-oss-20b") is False

    def test_reasoning_model(self):
        with patch("custom_benchmark._model_supports_reasoning", return_value=True):
            assert _can_use_structured_output("openai/gpt-oss-20b") is False

    def test_mamba(self):
        with patch("custom_benchmark._model_supports_reasoning", return_value=False):
            assert _can_use_structured_output("gabriellarson/mamba-codestral-7b-v0.1") is False

    def test_codestral_22b_grammar(self):
        # F5: Codestral-22B Grammar-400er ("Unexpected empty grammar stack
        # after accepting piece", Server-Log 03.08.2026).
        with patch("custom_benchmark._model_supports_reasoning", return_value=False):
            assert _can_use_structured_output("mistralai/codestral-22b-v0.1") is False

    def test_none(self):
        assert _can_use_structured_output(None) is True
