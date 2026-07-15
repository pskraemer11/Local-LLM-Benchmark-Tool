#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared CSV writer – unified schema for ALL benchmark pipelines.

── Role in the system ─────────────────────────────────────────────
  This module is used by ALL four pipelines to output results
  in a unified format:

    Pipeline             Writes                Read by (consolidation)
    ────────             ─────────             ──────────────────────────
    Custom               tasks_*.csv           consolidate_results_v13.py
    EvalPlus             modell_*.csv           consolidate_results_v13.py
    LM-Eval              modell_*.csv           consolidate_results_v13.py
    Agentic              modell_*.csv           consolidate_results_v13.py

  The launcher (run_benchmarks_v13.py) calls write_accumulative_summary()
  for each model's interim summary and write_konsolidiert_aktuell()
  for the final overview at the end.

── Conventions ────────────────────────────────────────────────────
  - Delimiter: ; (semicolon)
  - Encoding:  utf-8 (no BOM)
  - Scores:    0.0–100.0 (percent, float)
  - Field names: lowercase_with_underscores (English)
  - Metadata: pipeline, model, model_key, benchmark, timestamp, sample_size
              in EVERY output.

── CSV types ──────────────────────────────────────────────────────
  1. TASK_FIELDS    (tasks_*.csv)       – Per-task raw data (one entry per task)
  2. MODEL_FIELDS   (model_*.csv)       – Aggregated model summary
  3. SUMMARY_FIELDS (modell_*.csv)      – Accumulated overview (from launcher)
  4. CONSOLIDATED_FIELDS (konsolidiert_aktuell.csv) – Final overview

── Backward compatibility ─────────────────────────────────────────
  The aliases save_csv/save_model_summary forward old calls from
  predecessor scripts to the new functions.

Usage:
    from csv_writer import write_per_task_csv, write_per_model_csv, ...
"""

import csv
import os
import re
import sys
from datetime import datetime
from typing import Optional

# ── Directory ────────────────────────────────────────────────────

def _results_dir(base_dir=None):
    if base_dir:
        d = os.path.join(base_dir, "ergebnisse")
    else:
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ergebnisse")
    os.makedirs(d, exist_ok=True)
    return d


# ── Field definitions ────────────────────────────────────────────

# WARNING: Column names must match the readers in consolidate_results_v13.py
# (read_custom_csv, read_lmeval_per_model, try_read_evalplus).
# Any changes here MUST also update the readers.

# Per-task raw data (one entry per task)
TASK_FIELDS = [
    "pipeline",
    "model",
    "model_key",
    "benchmark",
    "timestamp",
    "sample_size",
    "seed",
    "exclude_benchmarks",
    "no_structured_output",
    "no_unload_between",
    "task_index",
    "score",
    "score_detail",
    "latency_s",
    "tokens_in",
    "tokens_out",
    "tokens_per_sec",
    "thinking_tokens",
    "thinking_pct",
    "cpu_pct",
    "gpu_pct",
    "ram_gb",
    "vram_gb",
    "cpu_pct_max",
    "gpu_pct_max",
    "ram_pct_max",
    "vram_gb_avg",
    "gpu_temp_max",
    "error_type",
    "error_detail",
    "response",
]

# Aggregated model summary (one entry per benchmark)
MODEL_FIELDS = [
    "pipeline",
    "model",
    "model_key",
    "category",
    "benchmark",
    "timestamp",
    "sample_size",
    "seed",
    "exclude_benchmarks",
    "no_structured_output",
    "no_unload_between",
    "num_tasks",
    "avg_score_pct",
    "avg_latency_s",
    "avg_tokens_per_sec",
    "avg_cpu_pct",
    "avg_gpu_pct",
    "avg_ram_gb",
    "avg_vram_gb",
    "cpu_pct_max",
    "gpu_pct_max",
    "ram_pct_max",
    "vram_gb_avg",
    "gpu_temp_max",
]

# Accumulated overview (run_benchmarks, one entry per pipeline/benchmark)
SUMMARY_FIELDS = [
    "pipeline",
    "model",
    "model_key",
    "category",
    "benchmark",
    "timestamp",
    "sample_size",
    "seed",
    "exclude_benchmarks",
    "no_structured_output",
    "no_unload_between",
    "thinking",
    "score",
    "detail",
    "latency_s",
    "tokens_per_sec",
    "vram_gb",
]

# Consolidated overview (all models × benchmarks)
CONSOLIDATED_FIELDS = [
    "pipeline",
    "model",
    "model_key",
    "category",
    "benchmark",
    "score",
    "timestamp",
    "sample_size",
    "seed",
    "exclude_benchmarks",
    "no_structured_output",
    "no_unload_between",
    "thinking",
]


# ── Helper functions ─────────────────────────────────────────────

def _safe_slice(text: str, n: int = 40) -> str:
    return re.sub(r"[\\/:*?\"<>|]", "_", str(text))[:n]

def _now_ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def _now_iso() -> str:
    # ISO 8601 with colons is invalid on Windows file systems.
    # We use the "compact" ISO format (T replaced with _, colons
    # dropped) for use in CSV filenames while still being
    # chronologically sortable.
    return datetime.now().strftime("%Y-%m-%dT%H-%M-%S")

def _truncate_response(response: str, max_chars: int = 200) -> str:
    """Truncate LLM response to ``max_chars`` characters for compact CSV output.

    Adds a marker showing the original length so consumers know the
    response was truncated. Use keep_response=True in write_per_task_csv
    to disable truncation entirely (e.g. for debugging).
    """
    if len(response) <= max_chars:
        return response
    return f"{response[:max_chars]}\n[…truncated, {len(response)} chars total]"


def _write_csv(path: str, fieldnames: list[str], rows: list[dict], delimiter: str = ";") -> str:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: str(v) if v is not None else "" for k, v in row.items()})
    return path


# ── Public write functions ───────────────────────────────────────

def write_per_task_csv(results: list[dict], benchmark_name: str, model_display: str,
                       model_key: str = "", sample_size: int = 5, pipeline: str = "custom",
                       seed: str = "", exclude_benchmarks: str = "",
                       no_structured_output: str = "", no_unload_between: str = "",
                       keep_response: bool = False, response_max_chars: int = 200,
                       base_dir: Optional[str] = None) -> str:
    """Writes per-task raw data (replaces save_csv in benchmark_lmstudio).

    The full model response (raw LLM output) is only written to the CSV
    when ``keep_response=True``. By default, responses are truncated to
    ``response_max_chars`` characters (default 200) with a marker showing
    the original length. This prevents 5MB+ CSV files for 100-task runs
    (see Review-Report 12.07.2026, W1: response-Spalte).
    """
    ts = _now_ts()
    # Filename: full model key (including quant variant)
    safe_m = _safe_slice(model_key if model_key else model_display, 50)
    safe_b = _safe_slice(benchmark_name, 30).replace(" ", "_")
    d = _results_dir(base_dir)
    path = os.path.join(d, f"tasks_{ts}_{safe_b}_{safe_m}.csv")
    iso = _now_iso()
    rows = []
    for i, r in enumerate(results):
        response = r.get("response", "")
        if response and not keep_response:
            response = _truncate_response(str(response), response_max_chars)
        rows.append({
            "pipeline": pipeline,
            "model": model_display,
            "model_key": model_key,
            "benchmark": benchmark_name,
            "timestamp": iso,
            "sample_size": str(sample_size),
            "seed": str(seed) if seed else "",
            "exclude_benchmarks": exclude_benchmarks,
            "no_structured_output": no_structured_output,
            "no_unload_between": no_unload_between,
            "task_index": r.get("task_index", i),
            "score": r.get("score", ""),
            "score_detail": r.get("score_detail", ""),
            "latency_s": r.get("latency", ""),
            "tokens_in": r.get("tokens_in", ""),
            "tokens_out": r.get("tokens_out", ""),
            "tokens_per_sec": r.get("tokens_per_sec", ""),
            "thinking_tokens": r.get("thinking_tokens", ""),
            "thinking_pct": r.get("thinking_anteil", ""),
            "cpu_pct": r.get("cpu_during", ""),
            "gpu_pct": r.get("gpu_during", ""),
            "ram_gb": r.get("ram_during", ""),
            "vram_gb": r.get("vram_during", ""),
            "cpu_pct_max": r.get("CPU_max", ""),
            "gpu_pct_max": r.get("GPU_max", ""),
            "ram_pct_max": r.get("RAM_max", ""),
            "vram_gb_avg": r.get("VRAM_GB", ""),
            "gpu_temp_max": r.get("GPU_Temp_max", ""),
            "error_type": r.get("error_type", ""),
            "error_detail": r.get("error_detail", ""),
            "response": response,
        })
    _write_csv(path, TASK_FIELDS, rows)
    print(f"[INFO] Task results: {path}")
    return path


def write_per_model_csv(entries: list[dict], model_display: str, model_key: str = "",
                        pipeline: str = "custom", sample_size: int = 5,
                        seed: str = "", exclude_benchmarks: str = "",
                        no_structured_output: str = "", no_unload_between: str = "",
                        base_dir: Optional[str] = None) -> str:
    """Writes aggregated model summary (replaces save_model_summary)."""
    ts = _now_ts()
    # Filename: full model key (including quant variant)
    safe_m = _safe_slice(model_key if model_key else model_display, 50)
    d = _results_dir(base_dir)
    path = os.path.join(d, f"model_{ts}_{safe_m}.csv")
    iso = _now_iso()
    rows = []
    for e in entries:
        rows.append({
            "pipeline": pipeline,
            "model": model_display,
            "model_key": model_key,
            "category": e.get("category", ""),
            "benchmark": e.get("benchmark_name", e.get("benchmark", "")),
            "timestamp": iso,
            "sample_size": str(sample_size),
            "seed": str(seed) if seed else "",
            "exclude_benchmarks": exclude_benchmarks,
            "no_structured_output": no_structured_output,
            "no_unload_between": no_unload_between,
            "num_tasks": e.get("num_tasks", e.get("sample_len", "")),
            "avg_score_pct": f"{e.get('avg_score', 0) * 100:.1f}" if e.get("avg_score") is not None else "",
            "avg_latency_s": f"{e.get('avg_latency', e.get('avg_latency_s', 0)):.1f}",
            "avg_tokens_per_sec": f"{e.get('avg_tps', e.get('avg_tokens_per_sec', 0)):.1f}",
            "avg_cpu_pct": f"{e.get('avg_cpu', 0):.1f}" if e.get("avg_cpu") is not None else "",
            "avg_gpu_pct": f"{e.get('avg_gpu', 0):.1f}" if e.get("avg_gpu") is not None else "",
            "avg_ram_gb": f"{e.get('avg_ram', 0):.1f}" if e.get("avg_ram") is not None else "",
            "avg_vram_gb": f"{e.get('avg_vram', 0):.1f}" if e.get("avg_vram") is not None else "",
            "cpu_pct_max": f"{e.get('cpu_max', 0):.1f}" if e.get("cpu_max") is not None else "",
            "gpu_pct_max": f"{e.get('gpu_max', 0):.1f}" if e.get("gpu_max") is not None else "",
            "ram_pct_max": f"{e.get('ram_max', 0):.1f}" if e.get("ram_max") is not None else "",
            "vram_gb_avg": f"{e.get('vram_gb', 0):.1f}" if e.get("vram_gb") is not None else "",
            "gpu_temp_max": f"{e.get('gpu_temp_max', 0):.1f}" if e.get("gpu_temp_max") is not None else "",
        })
    _write_csv(path, MODEL_FIELDS, rows)
    print(f"[INFO] Model summary: {path}")
    return path


def write_accumulative_summary(results: list[dict], model_info: dict,
                               sample_size: int = 5,
                               seed: str = "", exclude_benchmarks: str = "",
                               no_structured_output: str = "", no_unload_between: str = "",
                               base_dir: Optional[str] = None) -> str:
    """Accumulating model CSV – EACH call creates a NEW file with timestamp.
    
    Filename: modell_<YYYYMMDD_HHMMSS>_<model_key>.csv
    This prevents data loss through overwriting/dedup.

    results: list of dicts with pipeline, bench, model, score, detail, latency, tok_s, vram
    model_info: dict with key, display
    """
    ts = _now_ts()
    safe_key = model_info["key"].replace("/", "_").replace("\\", "_")
    short = safe_key[:50] if len(safe_key) > 50 else safe_key
    d = _results_dir(base_dir)
    path = os.path.join(d, f"modell_{ts}_{short}.csv")
    iso = _now_iso()

    rows = []
    for r in results:
        rows.append({
            "pipeline": r.get("pipeline", ""),
            "model": r.get("model", ""),
            "model_key": model_info["key"],
            "category": r.get("category", ""),
            "benchmark": r.get("bench", r.get("benchmark", "")),
            "timestamp": iso,
            "sample_size": str(sample_size),
            "seed": str(seed) if seed else "",
            "exclude_benchmarks": exclude_benchmarks,
            "no_structured_output": no_structured_output,
            "no_unload_between": no_unload_between,
            "thinking": r.get("thinking", ""),
            "score": r.get("score", ""),
            "detail": r.get("detail", ""),
            "latency_s": r.get("latency", ""),
            "tokens_per_sec": r.get("tok_s", ""),
            "vram_gb": r.get("vram", ""),
        })

    _write_csv(path, SUMMARY_FIELDS, rows)
    print(f"\n[INFO] Model summary: {path} ({len(rows)} entries)")
    return path


def write_konsolidiert_aktuell(results: list[dict], sample_size: int = 5,
                               seed: str = "", exclude_benchmarks: str = "",
                               no_structured_output: str = "", no_unload_between: str = "",
                               base_dir: Optional[str] = None) -> str:
    """Consolidated overview (replaces inline code in run_benchmarks main)."""
    d = _results_dir(base_dir)
    path = os.path.join(d, "konsolidiert_aktuell.csv")
    iso = _now_iso()
    rows = []
    for r in results:
        rows.append({
            "pipeline": r.get("pipeline", ""),
            "model": r.get("model", ""),
            "model_key": r.get("model_key", ""),
            "category": r.get("category", ""),
            "benchmark": r.get("bench", r.get("benchmark", "")),
            "score": str(r.get("score", "")),
            "timestamp": iso,
            "sample_size": str(sample_size),
            "seed": str(seed) if seed else "",
            "exclude_benchmarks": exclude_benchmarks,
            "no_structured_output": no_structured_output,
            "no_unload_between": no_unload_between,
            "thinking": r.get("thinking", ""),
        })
    _write_csv(path, CONSOLIDATED_FIELDS, rows)
    print(f"\n[INFO] Current overview: {path}")
    return path


# ── Quant-Vergleich (Paired Bootstrap) ──────────────────────────

COMPARE_FIELDS = [
    "benchmark", "key_a", "key_b",
    "mean_a", "mean_b", "mean_diff",
    "ci_lo", "ci_hi", "sign", "p_value", "n_items",
]


def write_quant_comparison(results: list, base_dir: str) -> str:
    """Write paired-bootstrap comparison results to CSV + MD.

    Args:
        results: list of dicts from compare_two_quants() + 'benchmark' key
        base_dir: project root (for results/ path)

    Returns:
        Path to written CSV file.
    """
    d = _results_dir(base_dir)
    iso = _now_iso()
    csv_rows = []
    for r in results:
        csv_rows.append({
            "benchmark": r.get("benchmark", ""),
            "key_a": r.get("key_a", ""),
            "key_b": r.get("key_b", ""),
            "mean_a": f"{r.get('mean_a', 0):.2f}",
            "mean_b": f"{r.get('mean_b', 0):.2f}",
            "mean_diff": f"{r.get('mean_diff', 0):+.2f}",
            "ci_lo": f"{r.get('ci_lo', 0):+.2f}",
            "ci_hi": f"{r.get('ci_hi', 0):+.2f}",
            "sign": r.get("sign", "~"),
            "p_value": f"{r.get('p_value', 1):.4f}",
            "n_items": str(r.get("n_items", 0)),
        })
    csv_path = os.path.join(d, f"quant_comparison_{iso}.csv")
    _write_csv(csv_path, COMPARE_FIELDS, csv_rows)

    md_path = os.path.join(d, f"quant_comparison_{iso}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Quant Comparison ({iso})\n\n")
        f.write("| Benchmark | Model A | Model B | Diff | 95% CI | p-value | Sign | n |\n")
        f.write("|-----------|---------|---------|------|--------|---------|------|---|\n")
        for r in results:
            sig = "***" if r.get("p_value", 1) < 0.001 else "**" if r.get("p_value", 1) < 0.01 else "*" if r.get("p_value", 1) < 0.05 else "n.s."
            f.write(f"| {r.get('benchmark','')} | {r.get('key_a','')} | {r.get('key_b','')} "
                    f"| {r.get('mean_diff',0):+.2f}% | [{r.get('ci_lo',0):+.2f}, {r.get('ci_hi',0):+.2f}] "
                    f"| {r.get('p_value',1):.4f} | {sig} | {r.get('n_items',0)} |\n")
    print(f"\n[INFO] Quant comparison:  {csv_path}")
    print(f"[INFO] Quant comparison:  {md_path}")
    return csv_path


# ── NOTE: Legacy-Aliase (save_csv, save_model_summary, save_model_summary_csv)
# wurden am 12.07.2026 entfernt (Code-Review_2026-07-12.md §3.1 D5).
# Die offiziellen Funktionsnamen sind jetzt:
#   - write_per_task_csv(...)
#   - write_per_model_csv(...)
#   - write_accumulative_summary(...)
#   - write_konsolidiert_aktuell(...)
