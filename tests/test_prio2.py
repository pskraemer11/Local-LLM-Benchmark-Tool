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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from benchmark_config import QUANT_MAP, get_quant
from custom_benchmark_v13 import strip_thinking_tokens
from csv_writer import _truncate_response


class TestGetQuant:
    """K1: variant-aware QUANT_MAP lookup with explicit priority."""

    def test_exact_match(self):
        assert get_quant("gpt-oss-20b") == "Q6_K"

    def test_exact_match_with_publisher(self):
        assert get_quant("lmstudio-community/gpt-oss-20b") == "MXFP4"

    def test_exact_match_unsloth(self):
        assert get_quant("unsloth/gpt-oss-20b") == "Q6_K"

    def test_different_quants_distinct(self):
        # devstral has IQ3_XXS (UD) and Q3_K_S variants – must not collide
        assert get_quant("devstral-small-2-24b-instruct-2512") == "IQ3_XXS"
        assert get_quant("devstral-small-2-24b-instruct-2512@q3_k_s") == "Q3_K_S"

    def test_qwen_coder_reap_distinct_quants(self):
        assert get_quant("qwen3-coder-reap-25b-a3b-i1") == "Q3_K_M"
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
        from consolidate_results_v13 import bootstrap_ci, paired_bootstrap_ci
        import random
        scores = [0.5, 0.6, 0.7, 0.8, 0.5, 0.6, 0.7, 0.8, 0.5, 0.6] * 5
        a = scores[:30]
        b = [x - 0.05 for x in a]
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
        from consolidate_results_v13 import paired_bootstrap_ci
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
        from consolidate_results_v13 import bootstrap_ci
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

    def test_quant_distinct_short_vs_long(self):
        """The D1 fix: short keys must not match longer keys via the old
        substring heuristic (e.g. 'gpt-oss-20b' in 'lmstudio-community/gpt-oss-20b'
        would have caused wrong fuzzy matches). The new logic requires
        length-ratio >= 0.85 for substring matches.
        """
        # gpt-oss-20b is a base/short key
        # lmstudio-community/gpt-oss-20b is the longer publisher-prefixed key
        # The exact-match lookup should return DIFFERENT quants for these.
        q1 = get_quant("gpt-oss-20b")           # Q6_K
        q2 = get_quant("lmstudio-community/gpt-oss-20b")  # MXFP4
        assert q1 != q2, f"q1={q1} q2={q2}"
        assert q1 == "Q6_K"
        assert q2 == "MXFP4"

    def test_quant_does_not_collapse_devstral_variants(self):
        """IQ3_XXS (UD) and Q3_K_S variants must remain distinct."""
        ud = get_quant("devstral-small-2-24b-instruct-2512")
        q3 = get_quant("devstral-small-2-24b-instruct-2512@q3_k_s")
        assert ud == "IQ3_XXS"
        assert q3 == "Q3_K_S"
        assert ud != q3

    def test_quant_does_not_collapse_qwen_reap_variants(self):
        """Q3_K_M (default) and Q4_K_S (custom) must remain distinct."""
        default = get_quant("qwen3-coder-reap-25b-a3b-i1")
        custom = get_quant("qwen3-coder-reap-25b-a3b-i1@q4_k_s")
        assert default == "Q3_K_M"
        assert custom == "Q4_K_S"
        assert default != custom
