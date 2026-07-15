import csv
import json
import math
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import consolidate_results_v13 as cr
from benchmark_config import CAT_WEIGHTS, OVERALL_WEIGHTS, QUANT_MAP
from consolidate_results_v13 import (
    _auto_delimiter,
    _find_dir_ci,
    _normalize_model_keys,
    _percentile,
    _read_col,
    _try_float,
    bootstrap_ci,
    compare_two_quants,
    compute_category_scores,
    paired_bootstrap_ci,
    read_paired_scores,
)


# ======================================================================
# Tiny pure utilities
# ======================================================================

class TestTryFloat:
    def test_parses_int(self):
        assert _try_float("42") == 42.0

    def test_parses_float(self):
        assert _try_float("3.14") == 3.14

    def test_returns_none_on_garbage(self):
        assert _try_float("not-a-number") is None

    def test_returns_none_on_none(self):
        assert _try_float(None) is None

    def test_returns_none_on_empty(self):
        assert _try_float("") is None


class TestReadCol:
    def test_returns_value(self):
        assert _read_col({"x": "  1.5  "}, "x") == 1.5

    def test_missing_returns_none(self):
        assert _read_col({"x": "1"}, "y") is None

    def test_blank_returns_none(self):
        assert _read_col({"x": "   "}, "x") is None

    def test_non_numeric_returns_none(self):
        assert _read_col({"x": "abc"}, "x") is None


class TestPercentile:
    def test_p50_odd_count(self):
        # [1,2,3,4,5] → median = 3
        assert _percentile([1, 2, 3, 4, 5], 50) == pytest.approx(3.0)

    def test_p0_returns_min(self):
        assert _percentile([5, 1, 3, 2, 4], 0) == pytest.approx(1.0)

    def test_p100_returns_max(self):
        assert _percentile([5, 1, 3, 2, 4], 100) == pytest.approx(5.0)

    def test_single_element(self):
        # k = 0, f=0, c=1 ≥ len → c=0. f==c branch.
        assert _percentile([42.0], 50) == 42.0


# ======================================================================
# Auto-detect delimiter
# ======================================================================

class TestAutoDelimiter:
    def test_detects_semicolon(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text('a;b\n1;2\n', encoding="utf-8")
        assert _auto_delimiter(str(f)) == ";"

    def test_defaults_to_comma(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text('a,b\n1,2\n', encoding="utf-8")
        assert _auto_delimiter(str(f)) == ","


# ======================================================================
# compute_category_scores
# ======================================================================

class TestComputeCategoryScores:
    def _all_categories_with_data(self):
        # one value per benchmark across all 4 categories, weighted
        out = {}
        for cat, bench_weights in CAT_WEIGHTS.items():
            for b in bench_weights:
                out[b] = 1.0
        return out

    def test_returns_all_categories(self):
        out = compute_category_scores(self._all_categories_with_data())
        for cat in CAT_WEIGHTS:
            assert cat in out
        assert "overall" in out

    def test_perfect_score_equals_one(self):
        out = compute_category_scores(self._all_categories_with_data())
        for cat in CAT_WEIGHTS:
            assert out[cat] == pytest.approx(1.0)
        # Overall weighted sum
        expected_overall = sum(
            OVERALL_WEIGHTS[cat] * out[cat] for cat in CAT_WEIGHTS
        ) / sum(OVERALL_WEIGHTS[cat] for cat in CAT_WEIGHTS)
        assert out["overall"] == pytest.approx(expected_overall)

    def test_partial_category_gets_normalized(self):
        # Only one benchmark per category present with score 0.5
        bench_scores = {
            # coding
            list(CAT_WEIGHTS["coding"].keys())[0]: 0.5,
            # knowledge
            list(CAT_WEIGHTS["knowledge"].keys())[0]: 0.5,
            # math
            list(CAT_WEIGHTS["math"].keys())[0]: 0.5,
            # agentic
            list(CAT_WEIGHTS["agentic"].keys())[0]: 0.5,
        }
        out = compute_category_scores(bench_scores)
        # category score with single bench should equal 0.5 (since weight is 1.0
        # in normalized form)
        for cat in CAT_WEIGHTS:
            assert out[cat] == pytest.approx(0.5)
        # Overall falls back to weighted mean
        assert out["overall"] == pytest.approx(0.5)

    def test_missing_category_returns_none(self):
        bench_scores = {"SomeRandomBenchmark": 0.5}
        out = compute_category_scores(bench_scores)
        for cat in CAT_WEIGHTS:
            assert out[cat] is None
        assert out["overall"] is None

    def test_none_score_treated_as_missing(self):
        # Coding: bench but with None
        first_bench = list(CAT_WEIGHTS["coding"].keys())[0]
        out = compute_category_scores({first_bench: None})
        assert out["coding"] is None


# ======================================================================
# _normalize_model_keys
# ======================================================================

class TestNormalizeModelKeys:
    def test_dedup_case_insensitive_variant(self):
        # Two entries that differ only by case of variant
        out = _normalize_model_keys(["model@q4_k_m", "model@Q4_K_M"])
        # Should collapse to one normalized entry
        assert len(out) == 1
        assert out[0].lower() == "model@q4_k_m"

    def test_keeps_different_variants(self):
        out = _normalize_model_keys(["model@q4_k_m", "model@q5_k_m"])
        assert len(out) == 2
        keys = {x.lower() for x in out}
        assert keys == {"model@q4_k_m", "model@q5_k_m"}

    def test_empty_input(self):
        assert _normalize_model_keys([]) == []

    def test_no_variant_preserved(self):
        out = _normalize_model_keys(["model"])
        assert "model" in out

    def test_double_quant_normalized(self):
        # Legacy double-quant
        out = _normalize_model_keys(["foo@q5_0@Q5_0"])
        assert len(out) == 1
        # Should be normalized to foo@q5_0
        assert out[0].lower() == "foo@q5_0"


# ======================================================================
# _find_dir_ci
# ======================================================================

class TestFindDirCi:
    def test_finds_exact_directory(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cr, "RESULTS_DIR", str(tmp_path))
        d = tmp_path / "lmeval_my-model"
        d.mkdir()
        result = _find_dir_ci("lmeval", "my-model")
        assert result == str(d)

    def test_finds_case_insensitive(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cr, "RESULTS_DIR", str(tmp_path))
        d = tmp_path / "lmeval_MY-MODEL"
        d.mkdir()
        result = _find_dir_ci("lmeval", "my-model")
        # Compare via case-insensitive basename match (Windows preserves case)
        assert os.path.normpath(result).lower() == os.path.normpath(str(d)).lower()

    def test_returns_none_when_not_found(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cr, "RESULTS_DIR", str(tmp_path))
        assert _find_dir_ci("lmeval", "nope") is None

    def test_slash_in_model_key_replaces_with_underscore(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cr, "RESULTS_DIR", str(tmp_path))
        d = tmp_path / "lmeval_author_my-model"
        d.mkdir()
        result = _find_dir_ci("lmeval", "author/my-model")
        assert result == str(d)

    def test_falls_back_to_base_when_no_variant(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cr, "RESULTS_DIR", str(tmp_path))
        # Create only variant-less version
        d = tmp_path / "lmeval_model"
        d.mkdir()
        # Search with @variant → second candidate is base
        result = _find_dir_ci("lmeval", "model@q4_k_m")
        assert result == str(d)


# ======================================================================
# bootstrap_ci
# ======================================================================

class TestBootstrapCI:
    def test_short_input_returns_nan(self):
        lo, hi = bootstrap_ci([0.5])
        assert math.isnan(lo)
        assert math.isnan(hi)

    def test_empty_returns_nan(self):
        lo, hi = bootstrap_ci([])
        assert math.isnan(lo)
        assert math.isnan(hi)

    def test_returns_tuple_of_floats(self):
        lo, hi = bootstrap_ci([0.1, 0.2, 0.3, 0.4], n_resamples=500)
        assert isinstance(lo, float)
        assert isinstance(hi, float)
        assert lo <= hi
        # The CI should bracket the actual mean (0.25)
        # With 500 resamples the 95% CI is wide, but should still cover 0.25
        assert lo < 0.30
        assert hi > 0.20

    def test_constant_input_returns_value(self):
        # All the same value → CI should equal that value
        lo, hi = bootstrap_ci([0.5, 0.5, 0.5, 0.5], n_resamples=200)
        assert lo == pytest.approx(0.5)
        assert hi == pytest.approx(0.5)


# ======================================================================
# paired_bootstrap_ci
# ======================================================================

class TestPairedBootstrapCI:
    def test_different_length_returns_nan(self):
        result = paired_bootstrap_ci([0.1, 0.2], [0.1], n_resamples=100, seed=42)
        assert all(math.isnan(x) for x in result)

    def test_too_short_returns_nan(self):
        result = paired_bootstrap_ci([0.1], [0.2], n_resamples=100, seed=42)
        assert all(math.isnan(x) for x in result)

    def test_better_a_has_positive_diff(self):
        a = [1.0, 1.0, 1.0, 1.0, 1.0]
        b = [0.0, 0.0, 0.0, 0.0, 0.0]
        mean_diff, lo, hi = paired_bootstrap_ci(a, b, n_resamples=500, seed=42)
        assert mean_diff == pytest.approx(1.0)
        assert lo > 0
        assert hi > 0

    def test_better_b_has_negative_diff(self):
        a = [0.0, 0.0, 0.0, 0.0, 0.0]
        b = [1.0, 1.0, 1.0, 1.0, 1.0]
        mean_diff, lo, hi = paired_bootstrap_ci(a, b, n_resamples=500, seed=42)
        assert mean_diff == pytest.approx(-1.0)
        assert lo < 0
        assert hi < 0

    def test_same_scores_diff_zero(self):
        scores = [0.3, 0.5, 0.7, 0.4, 0.6]
        mean_diff, lo, hi = paired_bootstrap_ci(scores, scores, n_resamples=500, seed=42)
        assert mean_diff == pytest.approx(0.0)


# ======================================================================
# compare_two_quants
# ======================================================================

class TestCompareTwoQuants:
    def test_too_few_items_returns_nan_dict(self):
        result = compare_two_quants("a", "b", [0.5], [0.7])
        assert math.isnan(result["mean_a"])
        assert math.isnan(result["mean_diff"])
        assert result["sign"] == "~"
        assert result["n_items"] == 1

    def test_clear_winner_a(self):
        a = [1.0] * 20
        b = [0.0] * 20
        result = compare_two_quants("A", "B", a, b, n_resamples=200, seed=42)
        assert result["mean_a"] == pytest.approx(1.0)
        assert result["mean_b"] == pytest.approx(0.0)
        assert result["sign"] == "+"
        assert result["n_items"] == 20
        assert result["p_value"] == pytest.approx(0.0)

    def test_clear_winner_b(self):
        a = [0.0] * 20
        b = [1.0] * 20
        result = compare_two_quants("A", "B", a, b, n_resamples=200, seed=42)
        assert result["sign"] == "-"

    def test_returns_correct_keys(self):
        a = [0.1, 0.2, 0.3, 0.4, 0.5]
        b = [0.2, 0.3, 0.4, 0.5, 0.6]
        result = compare_two_quants("A", "B", a, b, n_resamples=100, seed=42)
        for key in ["mean_a", "mean_b", "mean_diff", "ci_lo", "ci_hi",
                    "sign", "n_items", "p_value"]:
            assert key in result


# ======================================================================
# read_paired_scores
# ======================================================================

class TestReadPairedScores:
    def test_pairs_matching_task_index(self, tmp_path):
        a = tmp_path / "a.csv"
        b = tmp_path / "b.csv"
        a.write_text(
            "task_index,score\n1,0.5\n2,0.6\n3,0.7\n",
            encoding="utf-8",
        )
        b.write_text(
            "task_index,score\n1,0.4\n2,0.55\n3,0.65\n",
            encoding="utf-8",
        )
        sa, sb = read_paired_scores(str(a), str(b))
        assert sa == pytest.approx([0.5, 0.6, 0.7])
        assert sb == pytest.approx([0.4, 0.55, 0.65])

    def test_drops_unmatched_indices(self, tmp_path):
        a = tmp_path / "a.csv"
        b = tmp_path / "b.csv"
        a.write_text(
            "task_index,score\n1,0.5\n2,0.6\n3,0.7\n",
            encoding="utf-8",
        )
        b.write_text(
            "task_index,score\n1,0.4\n",
            encoding="utf-8",
        )
        sa, sb = read_paired_scores(str(a), str(b))
        # Only idx 1 is in both
        assert sa == pytest.approx([0.5])
        assert sb == pytest.approx([0.4])

    def test_no_common_returns_empty(self, tmp_path):
        a = tmp_path / "a.csv"
        b = tmp_path / "b.csv"
        a.write_text("task_index,score\n1,0.5\n", encoding="utf-8")
        b.write_text("task_index,score\n2,0.6\n", encoding="utf-8")
        sa, sb = read_paired_scores(str(a), str(b))
        assert sa == []
        assert sb == []

    def test_handles_semicolon_delimiter(self, tmp_path):
        a = tmp_path / "a.csv"
        b = tmp_path / "b.csv"
        a.write_text(
            "task_index;score\n1;0.5\n2;0.6\n",
            encoding="utf-8",
        )
        b.write_text(
            "task_index;score\n1;0.4\n2;0.55\n",
            encoding="utf-8",
        )
        sa, sb = read_paired_scores(str(a), str(b))
        assert sa == pytest.approx([0.5, 0.6])
        assert sb == pytest.approx([0.4, 0.55])

    def test_skips_invalid_score(self, tmp_path):
        a = tmp_path / "a.csv"
        b = tmp_path / "b.csv"
        a.write_text(
            "task_index,score\n1,0.5\n2,invalid\n3,0.7\n",
            encoding="utf-8",
        )
        b.write_text(
            "task_index,score\n1,0.4\n2,0.55\n3,0.65\n",
            encoding="utf-8",
        )
        sa, sb = read_paired_scores(str(a), str(b))
        # idx 2 dropped because a has invalid score
        assert sa == pytest.approx([0.5, 0.7])
        assert sb == pytest.approx([0.4, 0.65])


# ======================================================================
# cr.read_custom_csv (delegated functions for full coverage)
# ======================================================================

class TestReadCustomCsv:
    def _make_csv(self, tmp_path, rows, delimiter=","):
        f = tmp_path / "data.csv"
        cols = ["task_index", "score", "tokens_per_sec", "latency_s",
                "cpu_during", "gpu_during", "RAM_avg", "VRAM_GB"]
        with open(f, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=cols, delimiter=delimiter)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        return str(f)

    def test_returns_score_tps_latency(self, tmp_path):
        path = self._make_csv(tmp_path, [
            {"task_index": "1", "score": "0.5", "tokens_per_sec": "10.0",
             "latency_s": "1.0", "cpu_during": "", "gpu_during": "",
             "RAM_avg": "", "VRAM_GB": ""},
            {"task_index": "2", "score": "0.7", "tokens_per_sec": "20.0",
             "latency_s": "2.0", "cpu_during": "", "gpu_during": "",
             "RAM_avg": "", "VRAM_GB": ""},
        ])
        score, tps, lat, metrics = cr.read_custom_csv(path)
        assert score == pytest.approx(0.6)
        assert tps == pytest.approx(15.0)
        assert lat == pytest.approx(3.0)
        assert metrics == {}  # no cpu/gpu/ram

    def test_computes_metrics(self, tmp_path):
        path = self._make_csv(tmp_path, [
            {"task_index": "1", "score": "0.5", "tokens_per_sec": "",
             "latency_s": "", "cpu_during": "20.0", "gpu_during": "50.0",
             "RAM_avg": "8.0", "VRAM_GB": "5.0"},
        ])
        score, *_ = cr.read_custom_csv(path)
        assert score == pytest.approx(0.5)

    def test_appends_to_out_scores(self, tmp_path):
        path = self._make_csv(tmp_path, [
            {"task_index": "1", "score": "0.5", "tokens_per_sec": "",
             "latency_s": "", "cpu_during": "", "gpu_during": "",
             "RAM_avg": "", "VRAM_GB": ""},
            {"task_index": "2", "score": "0.7", "tokens_per_sec": "",
             "latency_s": "", "cpu_during": "", "gpu_during": "",
             "RAM_avg": "", "VRAM_GB": ""},
        ])
        collected = []
        cr.read_custom_csv(path, out_scores=collected)
        assert collected == pytest.approx([0.5, 0.7])

    def test_no_scores_returns_none_tuple(self, tmp_path):
        path = self._make_csv(tmp_path, [
            {"task_index": "1", "score": "", "tokens_per_sec": "",
             "latency_s": "", "cpu_during": "", "gpu_during": "",
             "RAM_avg": "", "VRAM_GB": ""},
        ])
        result = cr.read_custom_csv(path)
        assert result == (None, None, None, {})

    def test_missing_file_returns_none_tuple(self, capsys):
        result = cr.read_custom_csv("/nonexistent/path/foo.csv")
        assert result == (None, None, None, {})

    def test_semicolon_delimiter(self, tmp_path):
        path = self._make_csv(tmp_path, [
            {"task_index": "1", "score": "0.5", "tokens_per_sec": "",
             "latency_s": "", "cpu_during": "", "gpu_during": "",
             "RAM_avg": "", "VRAM_GB": ""},
        ], delimiter=";")
        score, *_ = cr.read_custom_csv(path)
        assert score == pytest.approx(0.5)


# ======================================================================
# get_quant (variant-aware lookup)
# ======================================================================

class TestGetQuant:
    def test_exact_match_returns_quant(self):
        # Pick any key from QUANT_MAP
        sample_key = next(iter(QUANT_MAP))
        expected = QUANT_MAP[sample_key]
        result = cr.get_quant(sample_key)
        assert result == expected

    def test_unknown_returns_question_mark(self):
        assert cr.get_quant("definitely-not-in-the-map-xyz") == "?"

    def test_empty_returns_question_mark(self):
        assert cr.get_quant("") == "?"
