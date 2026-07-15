"""Tests for consolidate_results_v13.py – Prio 4.16 (Code-Review §4 Prio 4).

Targets the deterministic helpers first (no I/O, no LM Studio
dependency):
    - _try_float, _read_col, _percentile
    - bootstrap_ci, paired_bootstrap_ci (pure-Python path; both paths
      are also tested deterministically via seeding)
    - _normalize_model_keys (pure function)
    - compute_category_scores (pure function, all 3 Prio-2 scenarios)
    - read_custom_csv (uses tmp_path fixture for CSV fixtures)
    - _auto_delimiter (pure helper)

The LM Studio dependent paths in `_get_model_info`, `_get_display_name`,
`_lookup_vram`, `read_lmeval_per_model`, `read_data`, and
`read_agentic` are tested in part 3.5 (separately) and require the
`fake_lmeval_results` / `lms_cli` fixtures.
"""
from __future__ import annotations

import csv
import os
import sys
from typing import Any

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import consolidate_results_v13 as cr
from benchmark_config import CAT_WEIGHTS, OVERALL_WEIGHTS, QUANT_MAP
from consolidate_results_v13 import (
    _auto_delimiter,
    _normalize_model_keys,
    _percentile,
    _read_col,
    _try_float,
    bootstrap_ci,
    compute_category_scores,
    paired_bootstrap_ci,
    read_custom_csv,
)


# ─────────────────────────────────────────────────────────────────────
# Helper-function tests
# ─────────────────────────────────────────────────────────────────────

class TestTryFloat:
    """_try_float: parse float with graceful failure."""

    @pytest.mark.parametrize("value,expected", [
        ("1.0", 1.0),
        ("0", 0.0),
        ("-3.14", -3.14),
        ("1e3", 1000.0),
        ("1.5e-2", 0.015),
        ("  42  ", 42.0),  # whitespace stripped
        ("-0", 0.0),       # negative zero normalizes to 0
        (5, 5.0),           # int passthrough
        (3.14, 3.14),       # float passthrough
        (True, 1.0),        # bool (True is 1)
    ])
    def test_valid_floats_parsed(self, value, expected):
        result = _try_float(value)
        assert result == pytest.approx(expected)

    @pytest.mark.parametrize("value", [
        "",
        "abc",
        "1.2.3",
        None,
        [],
        {},
    ])
    def test_invalid_values_return_none(self, value):
        assert _try_float(value) is None


class TestReadCol:
    """_read_col: extract optional float value from a CSV row dict."""

    def test_present_float_value(self):
        assert _read_col({"x": "1.5"}, "x") == 1.5

    def test_present_zero(self):
        # Zero is a valid value, not "missing"
        assert _read_col({"x": "0"}, "x") == 0.0

    def test_missing_key_returns_none(self):
        assert _read_col({}, "missing") is None

    def test_empty_string_returns_none(self):
        # Empty string is treated as "missing" (must be truthy)
        assert _read_col({"x": ""}, "x") is None

    def test_whitespace_only_returns_none(self):
        assert _read_col({"x": "   "}, "x") is None

    def test_non_numeric_returns_none(self):
        assert _read_col({"x": "abc"}, "x") is None

    def test_string_value_is_stripped(self):
        # Leading/trailing whitespace is removed
        assert _read_col({"x": "  3.14  "}, "x") == 3.14


class TestPercentile:
    """_percentile: NIST-style linear interpolation."""

    def test_median_is_50th_percentile(self):
        # P=50 with values [1..5] = 3.0
        assert _percentile([1, 2, 3, 4, 5], 50) == 3.0

    def test_min_is_zero_percentile(self):
        assert _percentile([10, 20, 30, 40], 0) == 10

    def test_max_is_hundred_percentile(self):
        assert _percentile([10, 20, 30, 40], 100) == 40

    def test_p90_interpolated(self):
        # Linear interpolation between 9 and 10
        result = _percentile(list(range(1, 11)), 90)
        assert result == pytest.approx(9.1)

    def test_p25_interpolated(self):
        # [1..10], P=25: k = 9 * 0.25 = 2.25, f=2, c=3
        # result = 3 * (3-2.25) + 4 * (2.25-2) = 0.75*3 + 0.25*4 = 2.25 + 1 = 3.25
        result = _percentile(list(range(1, 11)), 25)
        assert result == pytest.approx(3.25)

    def test_single_value(self):
        assert _percentile([42], 50) == 42

    def test_two_values_50th(self):
        # [0, 100] P=50 → exactly 50
        assert _percentile([0, 100], 50) == 50.0

    def test_unsorted_input(self):
        # Function must sort internally
        assert _percentile([5, 1, 3, 2, 4], 50) == 3

    def test_empty_list(self):
        # Implementation: k = (-1) * 50/100 = -0.5, f = -1, c = 0
        # → sorted_v[-1] * (0 - -0.5) + sorted_v[0] * (-0.5 - -1)
        # But IndexError on sorted_v[-1]. This is a known limitation
        # of the implementation; documenting the actual behavior.
        with pytest.raises(IndexError):
            _percentile([], 50)


# ─────────────────────────────────────────────────────────────────────
# Bootstrap CI tests
# ─────────────────────────────────────────────────────────────────────

class TestBootstrapCI:
    """bootstrap_ci: NumPy + pure-Python paths, deterministic with seeds."""

    def test_too_few_scores_returns_nan(self):
        lo, hi = bootstrap_ci([0.5], n_resamples=100)
        assert lo != lo  # NaN != NaN
        assert hi != hi

    def test_too_few_scores_zero_returns_nan(self):
        lo, hi = bootstrap_ci([], n_resamples=100)
        assert lo != lo
        assert hi != hi

    def test_constant_scores_returns_value(self):
        # If all scores are equal, the bootstrap CI is degenerate
        # but should still be the constant value (not crash)
        lo, hi = bootstrap_ci([0.5, 0.5, 0.5, 0.5], n_resamples=100)
        assert lo == pytest.approx(0.5)
        assert hi == pytest.approx(0.5)

    def test_known_distribution_contains_mean(self):
        # The 95% CI should contain the actual mean of the data
        import random
        random.seed(42)
        scores = [random.gauss(0.5, 0.1) for _ in range(50)]
        lo, hi = bootstrap_ci(scores, n_resamples=1000, alpha=0.05)
        assert lo < 0.5 < hi

    def test_narrow_ci_for_deterministic_data(self):
        # 10 identical scores → CI degenerates to the score value
        lo, hi = bootstrap_ci([0.5] * 10, n_resamples=100)
        assert lo == pytest.approx(0.5)
        assert hi == pytest.approx(0.5)

    def test_n_resamples_parameter_respected(self):
        # Different n_resamples should give very similar results for
        # the same data (bootstrap is consistent for large N)
        scores = [0.5, 0.6, 0.7, 0.8, 0.5, 0.6, 0.7, 0.8, 0.5, 0.6] * 5
        lo_small, hi_small = bootstrap_ci(scores, n_resamples=200, alpha=0.05)
        lo_large, hi_large = bootstrap_ci(scores, n_resamples=2000, alpha=0.05)
        # Should converge to the same answer for large N
        assert abs(lo_small - lo_large) < 0.02
        assert abs(hi_small - hi_large) < 0.02

    def test_alpha_parameter_widens_ci(self):
        # A larger alpha (wider CI) should give a wider interval
        scores = [0.5, 0.6, 0.7, 0.8, 0.5, 0.6, 0.7, 0.8, 0.5, 0.6] * 5
        lo_95, hi_95 = bootstrap_ci(scores, n_resamples=2000, alpha=0.05)
        lo_99, hi_99 = bootstrap_ci(scores, n_resamples=2000, alpha=0.01)
        # 99% CI should contain 95% CI (with high probability)
        assert lo_99 <= lo_95
        assert hi_99 >= hi_95


class TestPairedBootstrapCI:
    """paired_bootstrap_ci: paired resampling for model comparison."""

    def test_mismatched_lengths_returns_nan(self):
        a = [0.5, 0.6, 0.7]
        b = [0.4, 0.5]  # different length
        md, lo, hi = paired_bootstrap_ci(a, b, n_resamples=100)
        assert md != md
        assert lo != lo
        assert hi != hi

    def test_too_few_items_returns_nan(self):
        a = [0.5]
        b = [0.4]
        md, lo, hi = paired_bootstrap_ci(a, b, n_resamples=100)
        assert md != md

    def test_identical_data_mean_diff_zero(self):
        # If a == b, the paired diff is 0 for every item → mean diff = 0
        data = [0.5, 0.6, 0.7, 0.8, 0.5, 0.6, 0.7, 0.8, 0.5, 0.6] * 5
        md, lo, hi = paired_bootstrap_ci(data, data, n_resamples=500, seed=42)
        assert md == pytest.approx(0.0)
        # CI is degenerate around 0
        assert abs(lo) < 0.01
        assert abs(hi) < 0.01

    def test_constant_difference(self):
        # a[i] = b[i] + 0.1 for all i → mean_diff = 0.1
        b = [0.5, 0.6, 0.7, 0.8, 0.5, 0.6, 0.7, 0.8, 0.5, 0.6] * 5
        a = [x + 0.1 for x in b]
        md, lo, hi = paired_bootstrap_ci(a, b, n_resamples=500, seed=42)
        assert md == pytest.approx(0.1)
        # CI is degenerate around 0.1
        assert abs(lo - 0.1) < 0.01
        assert abs(hi - 0.1) < 0.01

    def test_a_greater_than_b_sign_positive(self):
        a = [0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9]
        b = [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]
        md, lo, hi = paired_bootstrap_ci(a, b, n_resamples=100, seed=42)
        assert md == pytest.approx(0.8)
        assert lo > 0
        assert hi > 0

    def test_seed_makes_results_deterministic(self):
        a = [0.5, 0.6, 0.7, 0.8, 0.5, 0.6, 0.7, 0.8, 0.5, 0.6] * 5
        b = [0.4, 0.5, 0.6, 0.7, 0.4, 0.5, 0.6, 0.7, 0.4, 0.5] * 5
        md1, lo1, hi1 = paired_bootstrap_ci(a, b, n_resamples=500, seed=42)
        md2, lo2, hi2 = paired_bootstrap_ci(a, b, n_resamples=500, seed=42)
        # Identical seed → identical results
        assert md1 == md2
        assert lo1 == lo2
        assert hi1 == hi2


# ─────────────────────────────────────────────────────────────────────
# _normalize_model_keys
# ─────────────────────────────────────────────────────────────────────

class TestNormalizeModelKeys:
    """_normalize_model_keys: dedupe model keys with quant variants."""

    def test_empty_list(self):
        assert _normalize_model_keys([]) == []

    def test_single_key(self):
        assert _normalize_model_keys(["model_a"]) == ["model_a"]

    def test_slash_normalized_to_underscore(self):
        # Publisher prefix with / is converted to _
        result = _normalize_model_keys(["unsloth/model_a"])
        assert result == ["unsloth_model_a"]

    def test_double_quant_normalized(self):
        # Legacy "model@q5_0@Q5_0" → "model@q5_0"
        result = _normalize_model_keys(["model@q5_0@Q5_0"])
        assert result == ["model@q5_0"]

    def test_quant_lowercased(self):
        # Variants like @Q3_K_S and @q3_k_s should be grouped
        result = _normalize_model_keys(["model_a@Q3_K_S", "model_a@q3_k_s"])
        # Both should collapse to the same normalized key
        assert len(result) == 1
        assert result[0] == "model_a@q3_k_s"

    def test_different_quants_kept_separate(self):
        result = _normalize_model_keys(["model_a@q3_k_s", "model_a@q4_k_m"])
        assert len(result) == 2
        assert "model_a@q3_k_s" in result
        assert "model_a@q4_k_m" in result

    def test_different_models_kept_separate(self):
        result = _normalize_model_keys(["model_a", "model_b"])
        assert len(result) == 2
        assert "model_a" in result
        assert "model_b" in result

    def test_uses_quant_map_for_missing_variant(self):
        # If a key has no @variant but QUANT_MAP knows its quant.
        # The actual key in QUANT_MAP is "mistralai/codestral-22b-v0.1"
        # (the publisher-prefixed form used by `lms ls --json`).
        # _normalize_model_keys also converts "/" to "_" in the output.
        result = _normalize_model_keys(["mistralai/codestral-22b-v0.1"])
        # QUANT_MAP says IQ4_XS for that key
        assert "mistralai_codestral-22b-v0.1@iq4_xs" in result

    def test_quant_map_priority_for_exact_match(self):
        # If a key is in QUANT_MAP, that's the source of truth
        result = _normalize_model_keys(["devstral-small-2-24b-instruct-2512"])
        # Should pick up IQ3_XXS from QUANT_MAP
        assert "devstral-small-2-24b-instruct-2512@iq3_xxs" in result


# ─────────────────────────────────────────────────────────────────────
# compute_category_scores (Prio 2.1 + 2.3 + 2.4 coverage)
# ─────────────────────────────────────────────────────────────────────

class TestComputeCategoryScores:
    """compute_category_scores: weighted category aggregation."""

    def test_empty_scores_all_categories_none(self):
        cats = compute_category_scores({})
        # All category scores should be None
        for cat in ("coding", "knowledge", "math", "agentic"):
            assert cats[cat] is None
        # Overall is also None
        assert cats["overall"] is None

    def test_coding_only_with_all_benchmarks(self):
        scores = {
            "DS1000": 0.5, "CoderEval": 0.8,
            "HumanEval+_plus": 1.0, "MBPP+_plus": 0.6,
        }
        cats = compute_category_scores(scores)
        # Coding: (0.5+0.8+1.0+0.6)/4 = 0.725
        assert cats["coding"] == pytest.approx(0.725)
        # Other categories: None
        assert cats["knowledge"] is None
        assert cats["math"] is None
        assert cats["agentic"] is None
        # Overall: only coding, so overall = coding
        assert cats["overall"] == pytest.approx(0.725)

    def test_coding_partial_only_uses_normalization(self):
        # Prio 2.4: if only one coding benchmark is present, available
        # benchmarks are scaled up to total weight 1.0
        scores = {"DS1000": 0.5}
        cats = compute_category_scores(scores)
        # Only DS1000 is present (weight 0.25); scale 1/0.25 = 4
        # 0.5 * 4 = 2.0? No: the impl normalizes by total weight
        # Actually: score * 0.25 / 0.25 = 0.5, sum 0.5, divide 0.25 = 2.0?
        # No: (0.5 * 0.25) / 0.25 = 0.5
        # The sum (0.5 * 0.25) is divided by 0.25 → 0.5
        assert cats["coding"] == pytest.approx(0.5)

    def test_partial_coding_renormalizes(self):
        # If only DS1000 and HumanEval+ are present, the remaining
        # weights (CoderEval, MBPP+) are skipped, total weight is
        # scaled to 1.0
        scores = {"DS1000": 1.0, "HumanEval+_plus": 0.0}
        cats = compute_category_scores(scores)
        # (1.0 * 0.25 + 0.0 * 0.25) / 0.5 = 0.5
        assert cats["coding"] == pytest.approx(0.5)

    def test_zero_scores_renders_zero(self):
        scores = {
            "DS1000": 0.0, "CoderEval": 0.0,
            "HumanEval+_plus": 0.0, "MBPP+_plus": 0.0,
        }
        cats = compute_category_scores(scores)
        assert cats["coding"] == 0.0
        assert cats["overall"] == 0.0

    def test_fully_loaded_uses_overall_weights(self):
        # All benchmarks present, overall is weighted sum
        scores = {
            # Coding (weight 0.35)
            "DS1000": 1.0, "CoderEval": 1.0,
            "HumanEval+_plus": 1.0, "MBPP+_plus": 1.0,
            # Knowledge (weight 0.15)
            "ARC-Challenge": 1.0, "HellaSwag": 1.0, "TruthfulQA": 1.0,
            # Math (weight 0.25)
            "MATH-500": 1.0,
            # Agentic (weight 0.25)
            "Agentic": 1.0, "IFEval": 1.0,
        }
        cats = compute_category_scores(scores)
        # All categories = 1.0 (all benchmarks at 1.0)
        assert cats["coding"] == pytest.approx(1.0)
        assert cats["knowledge"] == pytest.approx(1.0)
        assert cats["math"] == pytest.approx(1.0)
        assert cats["agentic"] == pytest.approx(1.0)
        # Overall is weighted sum
        # 1.0*0.35 + 1.0*0.15 + 1.0*0.25 + 1.0*0.25 = 1.0
        assert cats["overall"] == pytest.approx(1.0)

    def test_overall_with_only_one_category(self):
        # If only coding is available, overall = coding
        scores = {"DS1000": 0.8, "CoderEval": 0.6}
        cats = compute_category_scores(scores)
        # Coding: 0.7
        assert cats["coding"] == pytest.approx(0.7)
        # Overall: 0.7 (only category, weight = 1.0 effectively)
        assert cats["overall"] == pytest.approx(0.7)

    def test_overall_uses_category_weights(self):
        # When multiple categories present, overall is the weighted
        # average of category scores using OVERALL_WEIGHTS.
        scores = {
            "DS1000": 1.0, "CoderEval": 1.0,
            "HumanEval+_plus": 1.0, "MBPP+_plus": 1.0,
            "ARC-Challenge": 0.0, "HellaSwag": 0.0, "TruthfulQA": 0.0,
            "MATH-500": 1.0,
            "Agentic": 0.0, "IFEval": 0.0,
        }
        cats = compute_category_scores(scores)
        # coding=1.0, knowledge=0.0, math=1.0, agentic=0.0
        # overall = (1.0*0.35 + 0.0*0.15 + 1.0*0.25 + 0.0*0.25) / 1.0
        #        = 0.6 / 1.0 = 0.6
        # (total_w=1.0 because all 4 categories are present, even with
        #  score=0 — the implementation does not skip them.)
        assert cats["coding"] == pytest.approx(1.0)
        assert cats["knowledge"] == pytest.approx(0.0)
        assert cats["math"] == pytest.approx(1.0)
        assert cats["agentic"] == pytest.approx(0.0)
        assert cats["overall"] == pytest.approx(0.6)

    def test_overall_uses_only_present_categories(self):
        # When only coding is available, overall = coding score
        # (not divided by 0.6 because math/agentic/knowledge are not present)
        scores = {
            "DS1000": 1.0, "CoderEval": 1.0,
            "HumanEval+_plus": 1.0, "MBPP+_plus": 1.0,
        }
        cats = compute_category_scores(scores)
        assert cats["coding"] == pytest.approx(1.0)
        # Other categories not present (None)
        assert cats["knowledge"] is None
        assert cats["math"] is None
        assert cats["agentic"] is None
        # overall = only coding present → 1.0
        assert cats["overall"] == pytest.approx(1.0)

    def test_prio_2_3_truthfulqa_mc1(self):
        # After the Prio 2.3 fix, TruthfulQA returns scores under
        # "TruthfulQA" key (not "TruthfulQA_gen"). This test documents
        # the expected behavior.
        scores = {
            "TruthfulQA": 0.5,  # via truthfulqa_mc1 metric
            "ARC-Challenge": 0.5, "HellaSwag": 0.5,
        }
        cats = compute_category_scores(scores)
        # Knowledge weights: 3 benchmarks equal weight → 0.5
        assert cats["knowledge"] == pytest.approx(0.5)

    def test_prio_2_4_mmlupro_replacement(self):
        # Prio 2.4: MMLU-Pro is REMOVED from the active benchmark set.
        # If old CSVs still have "MMLU-Pro" key, it's just ignored
        # (not in CAT_WEIGHTS anymore).
        scores = {
            "MMLU-Pro": 0.99,  # stale data
            "DS1000": 0.5, "CoderEval": 0.5,
            "HumanEval+_plus": 0.5, "MBPP+_plus": 0.5,
        }
        cats = compute_category_scores(scores)
        # MMLU-Pro 0.99 is ignored (not in CAT_WEIGHTS)
        assert cats["coding"] == pytest.approx(0.5)


# ─────────────────────────────────────────────────────────────────────
# read_custom_csv (uses tmp_path for fixture)
# ─────────────────────────────────────────────────────────────────────

class TestAutoDelimiter:
    """_auto_delimiter: detect ; or , delimiter from first line."""

    def test_semicolon(self, tmp_path):
        f = tmp_path / "test.csv"
        f.write_text("a;b;c\n1;2;3\n", encoding="utf-8")
        assert _auto_delimiter(str(f)) == ";"

    def test_comma(self, tmp_path):
        f = tmp_path / "test.csv"
        f.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
        assert _auto_delimiter(str(f)) == ","

    def test_default_to_comma_when_no_separator(self, tmp_path):
        f = tmp_path / "test.csv"
        f.write_text("no separator here\n", encoding="utf-8")
        assert _auto_delimiter(str(f)) == ","

    def test_unicode_content(self, tmp_path):
        f = tmp_path / "test.csv"
        f.write_text("name;age\nÜber;42\n", encoding="utf-8")
        assert _auto_delimiter(str(f)) == ";"


def _write_custom_csv(path: str, rows: list[dict], fieldnames: list[str],
                     delimiter: str = ";") -> None:
    """Helper: write a CSV with given fieldnames and rows."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter,
                           extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


class TestReadCustomCSV:
    """read_custom_csv: parse per-task benchmark CSVs."""

    def test_semicolon_delimiter_detected(self, tmp_path):
        path = str(tmp_path / "test.csv")
        _write_custom_csv(path,
                          [{"score": 1.0}, {"score": 0.5}],
                          ["score"])
        score, _, _, _ = read_custom_csv(path)
        assert score == pytest.approx(0.75)

    def test_comma_delimiter_detected(self, tmp_path):
        path = str(tmp_path / "test.csv")
        _write_custom_csv(path,
                          [{"score": 1.0}, {"score": 0.0}],
                          ["score"], delimiter=",")
        score, _, _, _ = read_custom_csv(path)
        assert score == pytest.approx(0.5)

    def test_out_scores_collected(self, tmp_path):
        # out_scores parameter receives the per-item scores
        path = str(tmp_path / "test.csv")
        _write_custom_csv(path,
                          [{"score": 1.0}, {"score": 0.5}, {"score": 0.0}],
                          ["score"])
        collected: list[float] = []
        read_custom_csv(path, out_scores=collected)
        assert collected == [1.0, 0.5, 0.0]

    def test_tps_collected_from_tokens_per_sec(self, tmp_path):
        path = str(tmp_path / "test.csv")
        _write_custom_csv(path,
                          [{"score": 1.0, "tokens_per_sec": 9.6},
                           {"score": 0.5, "tokens_per_sec": 9.9}],
                          ["score", "tokens_per_sec"])
        _, avg_tps, _, _ = read_custom_csv(path)
        assert avg_tps == pytest.approx(9.75)

    def test_latency_collected(self, tmp_path):
        path = str(tmp_path / "test.csv")
        _write_custom_csv(path,
                          [{"score": 1.0, "latency_s": 5.2},
                           {"score": 0.5, "latency_s": 8.1}],
                          ["score", "latency_s"])
        _, _, total_lat, _ = read_custom_csv(path)
        # latency is summed (not averaged)
        assert total_lat == pytest.approx(13.3)

    def test_cpu_during_preferred_over_cpu_pct(self, tmp_path):
        # The implementation prefers cpu_during over cpu_pct
        path = str(tmp_path / "test.csv")
        _write_custom_csv(path,
                          [{"score": 1.0, "cpu_during": 50, "cpu_pct": 999}],
                          ["score", "cpu_during", "cpu_pct"])
        _, _, _, metrics = read_custom_csv(path)
        # cpu_during = 50 is used, cpu_pct = 999 is ignored
        assert metrics["CPU_avg"] == pytest.approx(50)

    def test_cpu_pct_used_when_cpu_during_missing(self, tmp_path):
        path = str(tmp_path / "test.csv")
        _write_custom_csv(path,
                          [{"score": 1.0, "cpu_pct": 75}],
                          ["score", "cpu_pct"])
        _, _, _, metrics = read_custom_csv(path)
        assert metrics["CPU_avg"] == pytest.approx(75)

    def test_ram_and_vram_collected(self, tmp_path):
        path = str(tmp_path / "test.csv")
        _write_custom_csv(path,
                          [{"score": 1.0, "RAM_avg": 50, "VRAM_GB": 12.0}],
                          ["score", "RAM_avg", "VRAM_GB"])
        _, _, _, metrics = read_custom_csv(path)
        assert metrics["RAM_avg"] == pytest.approx(50)
        assert metrics["VRAM_GB"] == pytest.approx(12.0)

    def test_no_scores_returns_none(self, tmp_path):
        # Empty CSV: no scores → returns (None, None, None, {})
        path = str(tmp_path / "test.csv")
        _write_custom_csv(path, [], ["score"])
        score, tps, lat, metrics = read_custom_csv(path)
        assert score is None
        assert tps is None
        assert lat is None
        assert metrics == {}

    def test_missing_file(self, tmp_path):
        # Non-existent file → returns (None, None, None, {})
        score, tps, lat, metrics = read_custom_csv(
            str(tmp_path / "nonexistent.csv")
        )
        assert score is None
        assert tps is None
        assert lat is None
        assert metrics == {}

    def test_corrupt_csv_line_continues(self, tmp_path):
        # The implementation should not crash on partial corruption
        path = str(tmp_path / "test.csv")
        # Write a valid CSV
        _write_custom_csv(path,
                          [{"score": 1.0}, {"score": 0.5}],
                          ["score"])
        # Append some garbage lines (these will be silently ignored)
        with open(path, "a", encoding="utf-8") as f:
            f.write("garbage\nwith,bad\n,separators\n")
        # Should still parse the 2 valid rows
        score, _, _, _ = read_custom_csv(path)
        assert score == pytest.approx(0.75)

    def test_garbage_non_numeric_score_skipped(self, tmp_path):
        # Non-numeric scores are skipped, not crashing
        path = str(tmp_path / "test.csv")
        _write_custom_csv(path,
                          [{"score": "abc"}, {"score": 0.5}],
                          ["score"])
        # Only the numeric score is used
        score, _, _, _ = read_custom_csv(path)
        assert score == pytest.approx(0.5)

    def test_pct_calculations_aggregate_correctly(self, tmp_path):
        # RAM_max → RAM_avg/max/p90 aggregations
        path = str(tmp_path / "test.csv")
        _write_custom_csv(path,
                          [{"score": 1.0, "RAM_max": 50, "VRAM_GB": 12.0, "GPU_Temp_max": 70}],
                          ["score", "RAM_max", "VRAM_GB", "GPU_Temp_max"])
        _, _, _, metrics = read_custom_csv(path)
        # RAM metrics: mean=50, max=50, med=50, p90=50
        assert metrics["RAM_avg"] == pytest.approx(50)
        assert metrics["RAM_max"] == pytest.approx(50)
        # VRAM is averaged across rows
        assert metrics["VRAM_GB"] == pytest.approx(12.0)
        # GPU temp: max across rows
        assert metrics["GPU_Temp_max"] == pytest.approx(70)


# ─────────────────────────────────────────────────────────────────────
# p-value / sign classification (compare_two_quants behavior)
# ─────────────────────────────────────────────────────────────────────

class TestCompareTwoQuantsSign:
    """Tests for the sign classification logic in compare_two_quants().

    Tested indirectly via bootstrap_ci sign + ci_lo/ci_hi behavior.
    """

    def test_p_value_zero_for_constant_a_higher(self):
        # If a > b for every item, no resample has sign disagreement → p ≈ 0
        a = [1.0] * 50
        b = [0.0] * 50
        md, lo, hi = paired_bootstrap_ci(a, b, n_resamples=500, seed=42)
        assert md == pytest.approx(1.0)
        # With 500 resamples and 100% sign agreement, lo should be
        # very close to 1.0
        assert lo > 0.9
