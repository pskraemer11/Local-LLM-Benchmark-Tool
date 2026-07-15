"""Tests for csv_writer.py – Prio 4.16 (Code-Review §4 Prio 4).

Targets: write_per_task_csv, write_per_model_csv, write_accumulative_summary,
write_konsolidiert_aktuell, write_quant_comparison, plus the helpers
_safe_slice, _truncate_response, _results_dir.

Uses the shared `tmp_results_dir` and `tmp_path` fixtures from
`conftest.py` so tests do not write to the real `ergebnisse/` dir.
"""
from __future__ import annotations

import csv
import os
import re
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import csv_writer
from csv_writer import (
    COMPARE_FIELDS,
    CONSOLIDATED_FIELDS,
    MODEL_FIELDS,
    SUMMARY_FIELDS,
    TASK_FIELDS,
    _results_dir,
    _safe_slice,
    _truncate_response,
    write_accumulative_summary,
    write_konsolidiert_aktuell,
    write_per_model_csv,
    write_per_task_csv,
    write_quant_comparison,
)


# ─────────────────────────────────────────────────────────────────────
# Helper tests
# ─────────────────────────────────────────────────────────────────────

class TestSafeSlice:
    """Tests for _safe_slice: sanitize filenames."""

    def test_short_string_unchanged(self):
        assert _safe_slice("hello") == "hello"

    def test_long_string_truncated(self):
        s = "x" * 100
        result = _safe_slice(s, n=20)
        assert result == "x" * 20

    def test_windows_unsafe_chars_replaced(self):
        # Forward slashes, backslashes, colons, asterisks, etc.
        result = _safe_slice("a/b\\c:d*e?f\"g<h>i|j")
        # All unsafe chars should become underscores
        for char in "/\\:*?\"<>|":
            assert char not in result
        # Original non-unsafe chars should remain
        for char in "abcdefghij":
            assert char in result

    def test_truncation_after_replacement(self):
        # Replacement happens before slicing, so result is <= n chars
        result = _safe_slice("a/b/c/d/e/f/g/h/i/j/k/l/m/n", n=10)
        assert len(result) <= 10
        assert "/" not in result

    def test_numeric_input_converted_to_string(self):
        # _safe_slice should handle non-string input gracefully
        result = _safe_slice(12345, n=5)
        assert result == "12345"


class TestTruncateResponse:
    """Tests for _truncate_response: keep CSVs compact."""

    def test_short_response_unchanged(self):
        assert _truncate_response("hello") == "hello"

    def test_empty_string_unchanged(self):
        assert _truncate_response("") == ""

    def test_exact_length_unchanged(self):
        s = "x" * 200
        assert _truncate_response(s, max_chars=200) == s

    def test_long_response_truncated_with_marker(self):
        s = "x" * 500
        result = _truncate_response(s, max_chars=200)
        # Marker is included
        assert "truncated" in result
        assert "500 chars total" in result
        # Original content is preserved at the start
        assert result.startswith("x" * 200)
        # The marker is on a new line
        assert "\n" in result

    def test_truncation_preserves_first_n_chars(self):
        s = "ABCDEFGHIJ" * 100  # 1000 chars
        result = _truncate_response(s, max_chars=50)
        # 50 chars = 5 × 10-char pattern
        assert result.startswith("ABCDEFGHIJ" * 5)

    def test_marker_shows_original_length(self):
        s = "x" * 1000
        result = _truncate_response(s, max_chars=100)
        assert "1000 chars total" in result


class TestResultsDir:
    """Tests for _results_dir: results path resolution."""

    def test_uses_base_dir_when_provided(self, tmp_path):
        d = _results_dir(base_dir=str(tmp_path))
        assert d == str(tmp_path / "ergebnisse")
        assert os.path.isdir(d)

    def test_creates_dir_if_not_exists(self, tmp_path):
        # tmp_path is initially empty
        target = tmp_path / "ergebnisse"
        assert not target.exists()
        _results_dir(base_dir=str(tmp_path))
        assert target.is_dir()

    def test_uses_module_path_when_no_base(self, tmp_path, monkeypatch):
        # When no base_dir is given, use the module's own directory
        # (we don't actually change the real module dir – we just verify
        # the directory contains "ergebnisse")
        d = _results_dir()
        assert d.endswith("ergebnisse")
        assert os.path.isdir(d)


# ─────────────────────────────────────────────────────────────────────
# write_per_task_csv
# ─────────────────────────────────────────────────────────────────────

def _make_task_result(**overrides):
    """Factory: a realistic per-task result dict."""
    base = {
        "task_index": 1,
        "score": 0.85,
        "score_detail": "OK",
        "latency": 5.2,
        "tokens_in": 100,
        "tokens_out": 50,
        "tokens_per_sec": 9.6,
        "thinking_tokens": 0,
        "thinking_anteil": 0,
        "cpu_during": 45,
        "gpu_during": 70,
        "ram_during": 8.5,
        "vram_during": 12.0,
        "CPU_max": 60,
        "GPU_max": 80,
        "RAM_max": 50,
        "VRAM_GB": 12.0,
        "GPU_Temp_max": 72,
        "error_type": "",
        "error_detail": "",
        "response": "print('hello')",
    }
    base.update(overrides)
    return base


class TestWritePerTaskCSV:
    """Tests for write_per_task_csv: per-task results file."""

    def test_writes_header(self, tmp_results_dir):
        path = write_per_task_csv(
            [_make_task_result()],
            benchmark_name="DS1000",
            model_display="test-model",
            model_key="test@q4_k_m",
            base_dir=tmp_results_dir,
        )
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            header = reader.fieldnames
        # Header is the TASK_FIELDS list
        assert header == TASK_FIELDS

    def test_writes_all_columns_per_row(self, tmp_results_dir):
        path = write_per_task_csv(
            [_make_task_result()],
            benchmark_name="DS1000",
            model_display="test-model",
            model_key="test@q4_k_m",
            base_dir=tmp_results_dir,
        )
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        assert len(rows) == 1
        # All TASK_FIELDS columns are present in the row
        for col in TASK_FIELDS:
            assert col in rows[0], f"Missing column: {col}"

    def test_writes_one_row_per_task(self, tmp_results_dir):
        results = [_make_task_result(task_index=i, score=0.5 + 0.1 * i) for i in range(5)]
        path = write_per_task_csv(
            results,
            benchmark_name="CoderEval",
            model_display="test-model",
            model_key="test@q4_k_m",
            base_dir=tmp_results_dir,
        )
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        assert len(rows) == 5
        assert [r["task_index"] for r in rows] == ["0", "1", "2", "3", "4"]

    def test_filename_pattern(self, tmp_results_dir):
        path = write_per_task_csv(
            [_make_task_result()],
            benchmark_name="DS1000",
            model_display="test-model",
            model_key="test@q4_k_m",
            base_dir=tmp_results_dir,
        )
        basename = os.path.basename(path)
        # Pattern: tasks_<TS>_<BENCH>_<MODEL>.csv
        assert basename.startswith("tasks_")
        assert "DS1000" in basename
        assert "test" in basename
        assert "q4_k_m" in basename
        assert basename.endswith(".csv")

    def test_response_truncated_by_default(self, tmp_results_dir):
        long_response = "x" * 1000
        path = write_per_task_csv(
            [_make_task_result(response=long_response)],
            benchmark_name="DS1000",
            model_display="test-model",
            model_key="test@q4_k_m",
            base_dir=tmp_results_dir,
            keep_response=False,
            response_max_chars=200,
        )
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        assert len(rows[0]["response"]) < 1000
        assert "truncated" in rows[0]["response"]

    def test_response_not_truncated_when_keep_true(self, tmp_results_dir):
        long_response = "x" * 1000
        path = write_per_task_csv(
            [_make_task_result(response=long_response)],
            benchmark_name="DS1000",
            model_display="test-model",
            model_key="test@q4_k_m",
            base_dir=tmp_results_dir,
            keep_response=True,
        )
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        # Full response preserved
        assert rows[0]["response"] == long_response

    def test_empty_response_handled(self, tmp_results_dir):
        path = write_per_task_csv(
            [_make_task_result(response="")],
            benchmark_name="DS1000",
            model_display="test-model",
            model_key="test@q4_k_m",
            base_dir=tmp_results_dir,
        )
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        assert rows[0]["response"] == ""

    def test_no_response_field_no_truncation(self, tmp_results_dir):
        # Task result without 'response' key should not crash
        result = _make_task_result()
        del result["response"]
        path = write_per_task_csv(
            [result],
            benchmark_name="DS1000",
            model_display="test-model",
            model_key="test@q4_k_m",
            base_dir=tmp_results_dir,
        )
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        assert rows[0]["response"] == ""

    def test_score_passes_through(self, tmp_results_dir):
        path = write_per_task_csv(
            [_make_task_result(score=0.85)],
            benchmark_name="DS1000",
            model_display="test-model",
            model_key="test@q4_k_m",
            base_dir=tmp_results_dir,
        )
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        assert rows[0]["score"] == "0.85"

    def test_task_index_uses_index_when_missing(self, tmp_results_dir):
        result = _make_task_result()
        del result["task_index"]
        path = write_per_task_csv(
            [result],
            benchmark_name="DS1000",
            model_display="test-model",
            model_key="test@q4_k_m",
            base_dir=tmp_results_dir,
        )
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        # Falls back to enumerate index
        assert rows[0]["task_index"] == "0"

    def test_returns_path_string(self, tmp_results_dir):
        path = write_per_task_csv(
            [_make_task_result()],
            benchmark_name="DS1000",
            model_display="test-model",
            model_key="test@q4_k_m",
            base_dir=tmp_results_dir,
        )
        assert isinstance(path, str)
        assert os.path.isfile(path)

    def test_empty_results_list_still_writes_header(self, tmp_results_dir):
        # Edge case: no results. Should still create a valid empty CSV.
        path = write_per_task_csv(
            [],
            benchmark_name="DS1000",
            model_display="test-model",
            model_key="test@q4_k_m",
            base_dir=tmp_results_dir,
        )
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        # Header only, no data rows
        assert content.strip().startswith("pipeline;model")
        assert content.count("\n") <= 1

    def test_metadata_columns_populated(self, tmp_results_dir):
        path = write_per_task_csv(
            [_make_task_result()],
            benchmark_name="CoderEval",
            model_display="Granite 4.1 30B",
            model_key="granite-4.1-30b@Q3_K_S",
            pipeline="custom",
            sample_size=42,
            seed="hello42",
            base_dir=tmp_results_dir,
        )
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        assert rows[0]["pipeline"] == "custom"
        assert rows[0]["model"] == "Granite 4.1 30B"
        assert rows[0]["model_key"] == "granite-4.1-30b@Q3_K_S"
        assert rows[0]["benchmark"] == "CoderEval"
        assert rows[0]["sample_size"] == "42"
        assert rows[0]["seed"] == "hello42"


# ─────────────────────────────────────────────────────────────────────
# write_per_model_csv
# ─────────────────────────────────────────────────────────────────────

def _make_model_entry(**overrides):
    """Factory: a realistic model summary entry."""
    base = {
        "category": "coding",
        "benchmark_name": "DS1000",
        "num_tasks": 10,
        "avg_score": 0.85,
        "avg_latency": 5.2,
        "avg_tps": 9.6,
        "avg_cpu": 45.0,
        "avg_gpu": 70.0,
        "avg_ram": 8.5,
        "avg_vram": 12.0,
        "cpu_max": 60.0,
        "gpu_max": 80.0,
        "ram_max": 50.0,
        "vram_gb": 12.0,
        "gpu_temp_max": 72.0,
    }
    base.update(overrides)
    return base


class TestWritePerModelCSV:
    """Tests for write_per_model_csv: per-model summary file."""

    def test_writes_header(self, tmp_results_dir):
        path = write_per_model_csv(
            [_make_model_entry()],
            model_display="test-model",
            model_key="test@q4_k_m",
            base_dir=tmp_results_dir,
        )
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            header = reader.fieldnames
        assert header == MODEL_FIELDS

    def test_writes_one_row_per_entry(self, tmp_results_dir):
        entries = [
            _make_model_entry(benchmark_name="DS1000", avg_score=0.85),
            _make_model_entry(benchmark_name="CoderEval", avg_score=0.75),
        ]
        path = write_per_model_csv(
            entries,
            model_display="test-model",
            model_key="test@q4_k_m",
            base_dir=tmp_results_dir,
        )
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        assert len(rows) == 2
        assert rows[0]["benchmark"] == "DS1000"
        assert rows[1]["benchmark"] == "CoderEval"

    def test_avg_score_pct_multiplied_by_100(self, tmp_results_dir):
        """avg_score is a 0-1 fraction in input, written as 0-100 percent."""
        path = write_per_model_csv(
            [_make_model_entry(avg_score=0.85)],
            model_display="test-model",
            model_key="test@q4_k_m",
            base_dir=tmp_results_dir,
        )
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        # 0.85 * 100 = 85.0
        assert rows[0]["avg_score_pct"] == "85.0"

    def test_avg_score_none_writes_empty(self, tmp_results_dir):
        path = write_per_model_csv(
            [_make_model_entry(avg_score=None)],
            model_display="test-model",
            model_key="test@q4_k_m",
            base_dir=tmp_results_dir,
        )
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        assert rows[0]["avg_score_pct"] == ""

    def test_numeric_formatting(self, tmp_results_dir):
        path = write_per_model_csv(
            [_make_model_entry(
                avg_latency=5.234,
                avg_tps=9.678,
                avg_cpu=45.5,
            )],
            model_display="test-model",
            model_key="test@q4_k_m",
            base_dir=tmp_results_dir,
        )
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        # All formatted to 1 decimal place
        assert rows[0]["avg_latency_s"] == "5.2"
        assert rows[0]["avg_tokens_per_sec"] == "9.7"
        assert rows[0]["avg_cpu_pct"] == "45.5"

    def test_benchmark_falls_back_to_benchmark_field(self, tmp_results_dir):
        # When "benchmark_name" is missing, fall back to "benchmark"
        entry = _make_model_entry()
        del entry["benchmark_name"]
        entry["benchmark"] = "fallback_name"
        path = write_per_model_csv(
            [entry],
            model_display="test-model",
            model_key="test@q4_k_m",
            base_dir=tmp_results_dir,
        )
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        assert rows[0]["benchmark"] == "fallback_name"

    def test_num_tasks_falls_back_to_sample_len(self, tmp_results_dir):
        entry = _make_model_entry()
        del entry["num_tasks"]
        entry["sample_len"] = 99
        path = write_per_model_csv(
            [entry],
            model_display="test-model",
            model_key="test@q4_k_m",
            base_dir=tmp_results_dir,
        )
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        assert rows[0]["num_tasks"] == "99"

    def test_missing_numeric_fields_default_to_zero(self, tmp_results_dir):
        # avg_latency, avg_tps etc. have `e.get(..., 0)` defaults,
        # so missing keys render as 0.0. avg_cpu and friends
        # are rendered as "" when their value is None.
        entry = _make_model_entry()
        # Remove some keys entirely
        for key in ["avg_latency", "avg_tps", "cpu_max", "gpu_max"]:
            entry.pop(key, None)
        # Set others to None
        for key in ["avg_cpu", "avg_gpu", "avg_ram", "avg_vram",
                    "ram_max", "vram_gb", "gpu_temp_max"]:
            entry[key] = None
        path = write_per_model_csv(
            [entry],
            model_display="test-model",
            model_key="test@q4_k_m",
            base_dir=tmp_results_dir,
        )
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        # Missing keys default to 0
        assert rows[0]["avg_latency_s"] == "0.0"
        assert rows[0]["avg_tokens_per_sec"] == "0.0"
        # None values render as empty string for fields that go through
        # the `if X is not None` branch
        assert rows[0]["avg_cpu_pct"] == ""
        assert rows[0]["gpu_temp_max"] == ""

    def test_filename_pattern(self, tmp_results_dir):
        path = write_per_model_csv(
            [_make_model_entry()],
            model_display="test-model",
            model_key="test_model@q4_k_m",
            base_dir=tmp_results_dir,
        )
        basename = os.path.basename(path)
        assert basename.startswith("model_")
        assert "test_model" in basename
        assert "q4_k_m" in basename
        assert basename.endswith(".csv")


# ─────────────────────────────────────────────────────────────────────
# write_accumulative_summary
# ─────────────────────────────────────────────────────────────────────

def _make_summary_result(**overrides):
    """Factory: a launcher-result for write_accumulative_summary."""
    base = {
        "pipeline": "custom",
        "bench": "DS1000",
        "category": "coding",
        "score": 0.85,
        "detail": "OK (DS1000-Harness)",
        "latency": 5.2,
        "tok_s": 9.6,
        "vram": 12.0,
        "thinking": False,
    }
    base.update(overrides)
    return base


class TestWriteAccumulativeSummary:
    """Tests for write_accumulative_summary: per-model summary file."""

    def test_writes_header(self, tmp_results_dir):
        path = write_accumulative_summary(
            [_make_summary_result()],
            model_info={"key": "test_model@q4_k_m", "display": "test_model"},
            base_dir=tmp_results_dir,
        )
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            header = reader.fieldnames
        assert header == SUMMARY_FIELDS

    def test_filename_pattern(self, tmp_results_dir):
        path = write_accumulative_summary(
            [_make_summary_result()],
            model_info={"key": "test_model@q4_k_m", "display": "test_model"},
            base_dir=tmp_results_dir,
        )
        basename = os.path.basename(path)
        assert basename.startswith("modell_")
        assert "test_model" in basename
        assert "q4_k_m" in basename
        assert basename.endswith(".csv")

    def test_score_passed_through_as_string(self, tmp_results_dir):
        path = write_accumulative_summary(
            [_make_summary_result(score=0.85)],
            model_info={"key": "test@q4_k_m", "display": "test"},
            base_dir=tmp_results_dir,
        )
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        assert rows[0]["score"] == "0.85"

    def test_none_score_renders_as_empty(self, tmp_results_dir):
        path = write_accumulative_summary(
            [_make_summary_result(score=None)],
            model_info={"key": "test@q4_k_m", "display": "test"},
            base_dir=tmp_results_dir,
        )
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        assert rows[0]["score"] == ""

    def test_bench_falls_back_to_benchmark(self, tmp_results_dir):
        result = _make_summary_result()
        del result["bench"]
        result["benchmark"] = "MyBench"
        path = write_accumulative_summary(
            [result],
            model_info={"key": "test@q4_k_m", "display": "test"},
            base_dir=tmp_results_dir,
        )
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        assert rows[0]["benchmark"] == "MyBench"

    def test_multiple_results_multiple_rows(self, tmp_results_dir):
        results = [
            _make_summary_result(bench="DS1000", score=0.8),
            _make_summary_result(bench="CoderEval", score=0.7),
        ]
        path = write_accumulative_summary(
            results,
            model_info={"key": "test@q4_k_m", "display": "test"},
            base_dir=tmp_results_dir,
        )
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        assert len(rows) == 2


# ─────────────────────────────────────────────────────────────────────
# write_konsolidiert_aktuell
# ─────────────────────────────────────────────────────────────────────

class TestWriteKonsolidiertAktuell:
    """Tests for write_konsolidiert_aktuell: final overview file."""

    def test_writes_header(self, tmp_results_dir):
        path = write_konsolidiert_aktuell(
            [_make_summary_result()],
            base_dir=tmp_results_dir,
        )
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            header = reader.fieldnames
        assert header == CONSOLIDATED_FIELDS

    def test_filename_is_static(self, tmp_results_dir):
        # The consolidated file has a fixed name (not timestamped)
        path1 = write_konsolidiert_aktuell(
            [_make_summary_result()],
            base_dir=tmp_results_dir,
        )
        path2 = write_konsolidiert_aktuell(
            [_make_summary_result()],
            base_dir=tmp_results_dir,
        )
        assert os.path.basename(path1) == "konsolidiert_aktuell.csv"
        assert os.path.basename(path2) == "konsolidiert_aktuell.csv"

    def test_score_serialized_as_string(self, tmp_results_dir):
        path = write_konsolidiert_aktuell(
            [_make_summary_result(score=0.5)],
            base_dir=tmp_results_dir,
        )
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        # Score is converted to str() (could be "0.5" or "0.5000...")
        assert rows[0]["score"].startswith("0.5")


# ─────────────────────────────────────────────────────────────────────
# write_quant_comparison
# ─────────────────────────────────────────────────────────────────────

def _make_quant_result(**overrides):
    """Factory: a comparison result for write_quant_comparison."""
    base = {
        "benchmark": "DS1000",
        "key_a": "model_a@q4_k_m",
        "key_b": "model_b@q4_k_m",
        "mean_a": 85.0,
        "mean_b": 75.0,
        "mean_diff": 10.0,
        "ci_lo": 5.0,
        "ci_hi": 15.0,
        "sign": "+",
        "p_value": 0.001,
        "n_items": 100,
    }
    base.update(overrides)
    return base


class TestWriteQuantComparison:
    """Tests for write_quant_comparison: CSV + MD output for paired bootstrap.

    NOTE: write_quant_comparison takes `base_dir` as the REPO ROOT
    (not the ergebnisse/ dir), unlike the other writers. The function
    calls _results_dir(base_dir) which appends "ergebnisse". So we
    pass `tmp_path` directly here.
    """

    def test_writes_csv(self, tmp_path):
        path = write_quant_comparison(
            [_make_quant_result()],
            base_dir=str(tmp_path),
        )
        assert path.endswith(".csv")
        assert os.path.isfile(path)
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        assert len(rows) == 1
        assert rows[0]["benchmark"] == "DS1000"
        assert rows[0]["key_a"] == "model_a@q4_k_m"

    def test_writes_markdown(self, tmp_path):
        # The function also writes a .md file alongside
        write_quant_comparison(
            [_make_quant_result()],
            base_dir=str(tmp_path),
        )
        # Look for the .md file
        results_dir = str(tmp_path / "ergebnisse")
        md_files = [f for f in os.listdir(results_dir) if f.endswith(".md")]
        assert len(md_files) == 1
        with open(os.path.join(results_dir, md_files[0]), "r", encoding="utf-8") as f:
            content = f.read()
        assert "Quant Comparison" in content
        assert "| Benchmark |" in content
        assert "model_a" in content
        assert "model_b" in content

    def test_csv_columns_match(self, tmp_path):
        path = write_quant_comparison(
            [_make_quant_result()],
            base_dir=str(tmp_path),
        )
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            assert reader.fieldnames == COMPARE_FIELDS

    def test_p_value_significance_stars(self, tmp_path):
        # Test all p-value ranges
        path = write_quant_comparison(
            [
                _make_quant_result(benchmark="very_high", p_value=0.0001),
                _make_quant_result(benchmark="high",      p_value=0.005),
                _make_quant_result(benchmark="medium",    p_value=0.03),
                _make_quant_result(benchmark="not_sig",   p_value=0.5),
            ],
            base_dir=str(tmp_path),
        )
        results_dir = str(tmp_path / "ergebnisse")
        md_files = [f for f in os.listdir(results_dir) if f.endswith(".md")]
        with open(os.path.join(results_dir, md_files[0]), "r", encoding="utf-8") as f:
            content = f.read()
        # very_high (p<0.001) → ***
        assert "| very_high |" in content and "***" in content
        # high (p<0.01) → **
        assert "| high |" in content and "**" in content
        # medium (p<0.05) → *
        assert "| medium |" in content and "|" in content
        # not_sig (p>=0.05) → n.s.
        assert "| not_sig |" in content and "n.s." in content

    def test_multiple_results_multiple_csv_rows(self, tmp_path):
        results = [
            _make_quant_result(benchmark="DS1000", key_a="a1@q4", key_b="a2@q4"),
            _make_quant_result(benchmark="CoderEval", key_a="b1@q4", key_b="b2@q4"),
        ]
        path = write_quant_comparison(results, base_dir=str(tmp_path))
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        assert len(rows) == 2
        assert rows[0]["benchmark"] == "DS1000"
        assert rows[1]["benchmark"] == "CoderEval"

    def test_significance_sign_falls_back(self, tmp_path):
        # If p_value is missing, default to 1 (n.s.)
        result = _make_quant_result()
        del result["p_value"]
        path = write_quant_comparison([result], base_dir=str(tmp_path))
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        assert rows[0]["p_value"] == "1.0000"
