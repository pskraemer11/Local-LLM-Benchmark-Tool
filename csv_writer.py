#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared CSV writer – einheitliches Schema fuer ALLE Benchmark-Pipelines.

── Rolle im Gesamtsystem ───────────────────────────────────────────
  Dieses Modul wird von ALLEN vier Pipelines genutzt, um Ergebnisse
  in einem einheitlichen Format auszugeben:

    Pipeline             Schreibt              Liesst (Konsolidierung)
    ────────             ─────────             ──────────────────────────
    Custom               tasks_*.csv           consolidate_results_v11.py
    EvalPlus             modell_*.csv           consolidate_results_v11.py
    LM-Eval              modell_*.csv           consolidate_results_v11.py
    Agentic              modell_*.csv           consolidate_results_v11.py

  Der Launcher (run_benchmarks_v11.py) ruft write_accumulative_summary()
  fuer jede Modell-Zwischenzusammenfassung und write_konsolidiert_aktuell()
  fuer die Gesamtuebersicht am Ende.

── Konventionen ───────────────────────────────────────────────────
  - Delimiter: ; (Semikolon)
  - Encoding:  utf-8 (kein BOM)
  - Scores:    0.0–100.0 (Prozent, float)
  - Feldnamen: lowercase_with_underscores (Englisch)
  - Metadaten: pipeline, model, model_key, benchmark, timestamp, sample_size
               in JEDER Ausgabe.

── CSV-Typen ──────────────────────────────────────────────────────
  1. TASK_FIELDS    (tasks_*.csv)       – Per-Task-Rohdaten (ein Eintrag pro Aufgabe)
  2. MODEL_FIELDS   (model_*.csv)       – Aggregierte Modell-Zusammenfassung
  3. SUMMARY_FIELDS (modell_*.csv)      – Akkumulierte Uebersicht (vom Launcher)
  4. CONSOLIDATED_FIELDS (konsolidiert_aktuell.csv) – Gesamtuebersicht

── Abwaertskompatibilitaet ────────────────────────────────────────
  Die Aliase save_csv/save_model_summary leiten alte Aufrufe aus
  Vorgaenger-Skripte (custom_benchmark_v25.py) an die neuen Funktionen weiter.

Nutzung:
    from csv_writer import write_per_task_csv, write_per_model_csv, ...
"""

import csv
import os
import re
import sys
from datetime import datetime
from typing import Optional

# ── Verzeichnis ──────────────────────────────────────────────────

def _results_dir(base_dir=None):
    if base_dir:
        d = os.path.join(base_dir, "ergebnisse")
    else:
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ergebnisse")
    os.makedirs(d, exist_ok=True)
    return d


# ── Felddefinitionen ─────────────────────────────────────────────

# ACHTUNG: Die Spaltennamen muessen mit den Lesern in consolidate_results_v11.py
# (read_custom_csv, read_lmeval_per_model, try_read_evalplus) uebereinstimmen.
# Bei Aenderungen hier MUessen auch die Leser aktualisiert werden.

# Per-Task-Rohdaten (ein Eintrag pro Aufgabe)
TASK_FIELDS = [
    "pipeline",
    "model",
    "model_key",
    "benchmark",
    "timestamp",
    "sample_size",
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

# Aggregierte Modell-Zusammenfassung (ein Eintrag pro Benchmark)
MODEL_FIELDS = [
    "pipeline",
    "model",
    "model_key",
    "benchmark",
    "timestamp",
    "sample_size",
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

# Akkumulierte Uebersicht (run_benchmarks, ein Eintrag pro Pipeline/Benchmark)
SUMMARY_FIELDS = [
    "pipeline",
    "model",
    "model_key",
    "benchmark",
    "timestamp",
    "sample_size",
    "score",
    "detail",
    "latency_s",
    "tokens_per_sec",
    "vram_gb",
]

# Konsolidierte Gesamtuebersicht (alle Modelle × Benchmarks)
CONSOLIDATED_FIELDS = [
    "pipeline",
    "model",
    "model_key",
    "benchmark",
    "score",
    "timestamp",
    "sample_size",
]


# ── Hilfsfunktionen ──────────────────────────────────────────────

def _safe_slice(text: str, n: int = 40) -> str:
    return re.sub(r"[\\/:*?\"<>|]", "_", str(text))[:n]

def _now_ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def _write_csv(path: str, fieldnames: list[str], rows: list[dict], delimiter: str = ";") -> str:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: str(v) if v is not None else "" for k, v in row.items()})
    return path


# ── Oeffentliche Schreib-Funktionen ──────────────────────────────

def write_per_task_csv(results: list[dict], benchmark_name: str, model_display: str,
                       model_key: str = "", sample_size: int = 5, pipeline: str = "custom",
                       base_dir: Optional[str] = None) -> str:
    """Schreibt Per-Task-Rohdaten (ersetzt save_csv in benchmark_lmstudio)."""
    ts = _now_ts()
    # Dateiname: vollstaendiger Modell-Key (mit Quant-Variante)
    safe_m = _safe_slice(model_key if model_key else model_display, 50)
    safe_b = _safe_slice(benchmark_name, 30).replace(" ", "_")
    d = _results_dir(base_dir)
    path = os.path.join(d, f"tasks_{ts}_{safe_b}_{safe_m}.csv")
    iso = _now_iso()
    rows = []
    for i, r in enumerate(results):
        rows.append({
            "pipeline": pipeline,
            "model": model_display,
            "model_key": model_key,
            "benchmark": benchmark_name,
            "timestamp": iso,
            "sample_size": str(sample_size),
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
            "response": r.get("response", ""),
        })
    _write_csv(path, TASK_FIELDS, rows)
    print(f"[INFO] Task-Ergebnisse: {path}")
    return path


def write_per_model_csv(entries: list[dict], model_display: str, model_key: str = "",
                        pipeline: str = "custom", sample_size: int = 5,
                        base_dir: Optional[str] = None) -> str:
    """Schreibt aggregierte Modell-Zusammenfassung (ersetzt save_model_summary)."""
    ts = _now_ts()
    # Dateiname: vollstaendiger Modell-Key (mit Quant-Variante)
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
            "benchmark": e.get("benchmark_name", e.get("benchmark", "")),
            "timestamp": iso,
            "sample_size": str(sample_size),
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
    print(f"[INFO] Modell-Zusammenfassung: {path}")
    return path


def write_accumulative_summary(results: list[dict], model_info: dict,
                               sample_size: int = 5,
                               base_dir: Optional[str] = None) -> str:
    """Akkumulierende Modell-CSV – JEDER Aufruf erzeugt eine NEUE Datei mit Timestamp.
    
    Dateiname: modell_<YYYYMMDD_HHMMSS>_<model_key>.csv
    Dadurch gehen keine Ergebnisse durch Ueberschreiben/Dedup verloren.

    results: Liste von dicts mit pipeline, bench, model, score, detail, latency, tok_s, vram
    model_info: dict mit key, display
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
            "benchmark": r.get("bench", r.get("benchmark", "")),
            "timestamp": iso,
            "sample_size": str(sample_size),
            "score": r.get("score", ""),
            "detail": r.get("detail", ""),
            "latency_s": r.get("latency", ""),
            "tokens_per_sec": r.get("tok_s", ""),
            "vram_gb": r.get("vram", ""),
        })

    _write_csv(path, SUMMARY_FIELDS, rows)
    print(f"\n[INFO] Modell-Zusammenfassung: {path} ({len(rows)} Eintraege)")
    return path


def write_konsolidiert_aktuell(results: list[dict], sample_size: int = 5,
                               base_dir: Optional[str] = None) -> str:
    """Konsolidierte Gesamtuebersicht (ersetzt inline-Code in run_benchmarks main)."""
    d = _results_dir(base_dir)
    path = os.path.join(d, "konsolidiert_aktuell.csv")
    iso = _now_iso()
    rows = []
    for r in results:
        rows.append({
            "pipeline": r.get("pipeline", ""),
            "model": r.get("model", ""),
            "model_key": r.get("model_key", ""),
            "benchmark": r.get("bench", r.get("benchmark", "")),
            "score": str(r.get("score", "")),
            "timestamp": iso,
            "sample_size": str(sample_size),
        })
    _write_csv(path, CONSOLIDATED_FIELDS, rows)
    print(f"\n[INFO] Aktuelle Uebersicht: {path}")
    return path


# ── Abwaertskompatibilitaet (Aliase) ────────────────────────────

def save_csv(results, benchmark_name, model_id):
    """Altes Interface aus benchmark_lmstudio_v23 – leitet an write_per_task_csv weiter."""
    return write_per_task_csv(results, benchmark_name, model_id)

def save_model_summary(model_display, model_results, bench_name="", quiet=False):
    """Altes Interface – leitet an write_per_model_csv weiter."""
    return write_per_model_csv(model_results, model_display)

def save_model_summary_csv(results, model_info):
    """Altes Interface aus run_benchmarks – leitet an write_accumulative_summary weiter."""
    return write_accumulative_summary(results, model_info)
