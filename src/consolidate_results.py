#!/usr/bin/env python3
"""Consolidate all benchmark results from a dense run into a single table.

── Role in the Overall System ─────────────────────────────────────
  This script is the last step of the benchmark pipeline.
  It reads CSV files from ergebnisse/ (written by
  csv_writer.py in run_benchmarks_v13.py) and consolidates them into:

    1. Overall ranking (CSV + MD) with score per benchmark
    2. Category scores: Coding (35%), Math (25%), Agentic (25%), Knowledge (15%)
    3. Overall score (normalized)
    4. TOP/BOTTOM 5 and category rankings

── Relationship to Other Scripts ──────────────────────────────────
  run_benchmarks_v13.py         -> writes model_*.csv (per model)
  custom_benchmark_v13.py       -> writes tasks_*.csv (per task)
  csv_writer.py                 -> unified CSV schema
  consolidate_results_v13.py    -> READS these CSVs

Computes weighted category scores + efficiency.
"""
from __future__ import annotations

import argparse
import csv, itertools, json, os, sys, re, random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from statistics import mean, median
from typing import Any, Dict, List, Optional, Tuple

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
# Make `src` importable regardless of the working directory
# (python -m src.consolidate_results from the repo root). Fix for
# Code-Review_2026-08-03.md F4.
sys.path.insert(0, SRC_DIR)
PROJECT_ROOT = os.path.dirname(SRC_DIR)
RESULTS_DIR = os.path.join(PROJECT_ROOT, "ergebnisse")
INSTALLED_CACHE = None

from utils.terminal import ok, warn, error, info
from benchmark_config import (MMLU_PRO_SUBSETS, LB_MEANS_BLACKLIST,
                             CAT_WEIGHTS, OVERALL_WEIGHTS, QUANT_MAP, get_quant)

# --- Model info cache (from lms ls --json) ---
_MODEL_INFO_CACHE = None

def _get_model_info() -> Dict[str, Any]:
    """Cached map model_key -> display metadata from lms ls (via get_available_models).

    Each entry contains displayName (without @quant suffix), vram_gb,
    params, quant and the raw modelKey. Falls back to {} on error.
    """
    global _MODEL_INFO_CACHE
    if _MODEL_INFO_CACHE is not None:
        return _MODEL_INFO_CACHE
    info = {}
    try:
        from model_manager import get_available_models
        models = get_available_models()
        for m in models:
            unique_key = m["key"]
            display = m["display"]
            if "@" in display:
                display = display.split("@")[0]
            info[unique_key] = {
                "displayName": display,
                "vram_gb": m.get("vram_gb", ""),
                "params": m.get("params", "?") or "?",
                "quant": m.get("quant", "?") or "?",
                "modelKey": m.get("modelKey", m["model_identifier"]),
            }
    except Exception:
        print("[WARN] _get_model_info: could not query available models", file=sys.stderr)
    _MODEL_INFO_CACHE = info
    return info


def _get_installed_model_keys() -> set:
    """Cached set of normalized installed model keys ("publisher/model@quant").

    Used by the installed-only filter so historical results of models
    that are no longer installed are excluded from consolidation.
    """
    global INSTALLED_CACHE
    if INSTALLED_CACHE is not None:
        return INSTALLED_CACHE
    installed = set()
    try:
        from model_manager import get_available_models
        models = get_available_models()
        for m in models:
            norm = m["model_identifier"].replace("/", "_")
            quant = m.get("quant", "")
            if quant:
                norm = f"{norm}@{quant.lower()}"
            installed.add(norm)
    except Exception:
        print("[WARN] _get_installed_model_keys: could not query available models", file=sys.stderr)
    INSTALLED_CACHE = installed
    return installed


def _normalize_model_keys(model_keys: List[str]) -> List[str]:
    """Normalize and deduplicate model keys.

    1. Lowercase the @variant part consistently
    2. If a base model appears both with and without @variant (same variant),
       keep only the version with @variant (use QUANT_MAP to infer missing quant)
    3. Keep multiple quant variants as separate entries (e.g. @q3_k_m vs @q4_k_s)
    """
    groups: dict[tuple[str, str], list[str]] = {}
    for mk in model_keys:
        # Look up QUANT_MAP BEFORE the "/" → "_" replacement because
        # the keys in QUANT_MAP use the publisher-prefixed form
        # (e.g. "mistralai/codestral-22b-v0.1"), not the normalized form.
        # Fixed 12.07.2026 as part of the test-coverage expansion (Prio 4.16).
        if "@" in mk:
            parts = mk.split("@")
            if len(parts) > 2:
                mk = f"{parts[0]}@{parts[-1]}"
            base_pre, variant = mk.split("@", 1)
            variant_lower = variant.lower()
        else:
            base_pre = mk
            # Try both: original (with /) and normalized (with _)
            variant_lower = QUANT_MAP.get(mk, "").lower() or \
                QUANT_MAP.get(mk.replace("/", "_"), "").lower()
        # Normalize publisher/key separator: "/" → "_" (directory convention)
        mk = mk.replace("/", "_")
        base = base_pre.replace("/", "_")
        key = (base, variant_lower)
        groups.setdefault(key, []).append(mk)

    result: list[str] = []
    seen: set[str] = set()
    for (base, v_lower), originals in groups.items():
        normalized = f"{base}@{v_lower}" if v_lower else base
        if normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result


def _get_display_name(model_key: str) -> str:
    """Resolve model_key -> human-readable display name, appending @variant if present."""
    # Fix legacy double-quant (e.g. "model@q5_0@Q5_0" -> "model@Q5_0")
    parts = model_key.split("@")
    if len(parts) > 2:
        model_key = f"{parts[0]}@{parts[-1]}"
    variant = ""
    if "@" in model_key:
        base_key, variant = model_key.split("@", 1)
        variant = variant.lower()  # consistent lowercase
    else:
        base_key = model_key
    info = _get_model_info()
    if model_key in info:
        dn = info[model_key].get("displayName")
        if dn:
            return f"{dn}@{variant}" if variant else dn
    # Search by stored modelKey field (variant-aware)
    for mk, meta in info.items():
        if meta.get("modelKey") == model_key:
            dn = meta.get("displayName")
            if dn:
                return f"{dn}@{variant}" if variant else dn
    # Fuzzy: strip publisher prefix
    import re as _re
    mk_norm = _re.sub(r"^[a-z0-9_-]+/", "", model_key.lower())
    for mk, meta in info.items():
        mk_stripped = _re.sub(r"^[a-z0-9_-]+/", "", mk.lower())
        if mk_norm == mk_stripped:
            dn = meta.get("displayName")
            if dn:
                return f"{dn}@{variant}" if variant else dn
    # Fallback: prettify base_key only (without variant), then append @variant
    display = base_key.replace("/", " ").replace("_", " ").replace("-", " ").title()
    return f"{display}@{variant}" if variant else display


def _lookup_vram(model_key: str) -> Optional[Dict[str, Any]]:
    """Try to find VRAM + quant for a model_key.

    Priority for quant: QUANT_MAP (static) > lms ls --json (dynamic)
    Priority for vram_gb: lms ls --json only (dynamic – deleted models have no file)
    """
    # Step 1: Get quant from QUANT_MAP via variant-aware get_quant() (primary
    # – works for deleted models too). This prevents the previous behaviour
    # where `QUANT_MAP.get(model_key)` returned None for `gpt-oss-20b` if the
    # caller passed `lmstudio-community/gpt-oss-20b`, leading to a wrong
    # quant from lms_match.
    quant_from_map = get_quant(model_key) or None

    # Step 2: Get VRAM + quant from lms ls --json (dynamic – only installed models)
    info = _get_model_info()
    lms_match = None
    if model_key in info:
        lms_match = info[model_key]
    elif not lms_match:
        # Search by stored modelKey field (variant-aware)
        for mk, meta in info.items():
            if meta.get("modelKey") == model_key:
                lms_match = meta
                break
    if not lms_match:
        # Fuzzy match. Previous implementation used substring matching
        # `dk_norm in mk_base_norm` which produced FALSE POSITIVES for short
        # keys (e.g. `gemma412b` in `gemma419ba4bitreap`). The fix:
        #   1. Strip ONLY the known publisher prefix from the model_key,
        #      not from the matched candidates.
        #   2. Require either EXACT normalized equality OR a minimum length
        #      ratio (>=0.85) when one string is a prefix of the other.
        import re as _re
        PUB_PREFIXES = r"^(?:ibm|google|microsoft|mistralai|essentialai|"
        PUB_PREFIXES += r"qwen|lmstudio-community|openai|mradermacher|"
        PUB_PREFIXES += r"jetbrains|unsloth|modelgraft|fb|meta|deepseek|"
        PUB_PREFIXES += r"cerebras|moonshotai|zai-org|baidu|alibaba)[/\\]"
        dk_stripped = _re.sub(PUB_PREFIXES, "", model_key.lower(), count=1)
        dk_norm = _re.sub(r"[-_./\\@]", "", dk_stripped)
        # Also strip trailing @quant for length comparison
        dk_base = _re.sub(r"@.*$", "", dk_stripped)
        dk_base_norm = _re.sub(r"[-_./\\@]", "", dk_base)
        best_match = None
        best_score = 0.0
        for mk in info:
            mk_stripped = _re.sub(PUB_PREFIXES, "", mk.lower(), count=1)
            mk_base = _re.sub(r"@.*$", "", mk_stripped)
            mk_base_norm = _re.sub(r"[-_./\\@]", "", mk_base)
            if not mk_base_norm:
                continue
            # Exact match (normalized)
            if dk_base_norm == mk_base_norm:
                best_match = info[mk]
                best_score = 1.0
                break
            # Substring match with length-ratio guard to prevent the
            # `gemma412b in gemma419ba4bitreap` false-positive
            if dk_base_norm in mk_base_norm or mk_base_norm in dk_base_norm:
                shorter, longer = sorted([dk_base_norm, mk_base_norm], key=len)
                ratio = len(shorter) / len(longer) if longer else 0.0
                if ratio >= 0.85 and ratio > best_score:
                    best_score = ratio
                    best_match = info[mk]
        lms_match = best_match

    # Step 3: Merge – QUANT_MAP wins for quant, lms wins for vram_gb
    if lms_match:
        return {
            "vram_gb": lms_match.get("vram_gb", ""),
            "params": lms_match.get("params", "?"),
            "quant": quant_from_map or lms_match.get("quant", "?"),
        }
    elif quant_from_map:
        return {"vram_gb": "", "params": "?", "quant": quant_from_map}
    return None

# (CAT_WEIGHTS, OVERALL_WEIGHTS in benchmark_config.py)


def _try_float(v: Any) -> Optional[float]:
    """Parse a value as float, returning None for missing/non-numeric inputs."""
    try:
        return float(v)
    except (ValueError, TypeError):
        return None

def _read_col(row: Dict[str, str], col: str) -> Optional[float]:
    """Read and parse a numeric column value from a CSV row (None if empty/invalid)."""
    v = row.get(col, "").strip()
    if v:
        fv = _try_float(v)
        if fv is not None:
            return fv
    return None

def _percentile(values: List[float], p: float) -> float:
    """Linear-interpolated percentile (0-100) of a value list."""
    sorted_v = sorted(values)
    k = (len(sorted_v) - 1) * p / 100.0
    f = int(k)
    c = f + 1 if f + 1 < len(sorted_v) else f
    if f == c:
        return sorted_v[f]
    return sorted_v[f] * (c - k) + sorted_v[c] * (k - f)

def bootstrap_ci(scores: List[float], n_resamples: int = 10000, alpha: float = 0.05) -> Tuple[float, float]:
    """Bootstrap 95% confidence interval for the mean.

    Draws n_resamples samples with replacement from scores,
    computes the mean each time, and returns the (alpha/2)-th and
    (1-alpha/2)-th percentile of the distribution.

    NumPy-accelerated: ~100x faster than the previous pure-Python
    loop (1M random.choice calls for N=100 / 10k resamples).
    Falls back to pure Python if NumPy is unavailable.
    """
    if len(scores) < 2:
        return (float('nan'), float('nan'))
    try:
        import numpy as np
        arr = np.asarray(scores, dtype=np.float64)
        n = arr.shape[0]
        # Sampling with replacement: n_resamples × n indices
        idx = np.random.randint(0, n, size=(n_resamples, n))
        means = arr[idx].mean(axis=1)
        lo_idx = int(n_resamples * alpha / 2)
        hi_idx = int(n_resamples * (1 - alpha / 2))
        # np.partition is O(n) and faster than full sort when we only
        # need the two boundary percentiles
        boundary = np.partition(means, (lo_idx, hi_idx))
        return (float(boundary[lo_idx]), float(boundary[hi_idx]))
    except ImportError:
        # Fallback: pure-Python
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
        return (means[lo_idx], means[hi_idx])

def paired_bootstrap_ci(scores_a: List[float], scores_b: List[float],
                        n_resamples: int = 10000, alpha: float = 0.05,
                        seed: Optional[int] = None) -> Tuple[float, float, float]:
    """Paired bootstrap CI for the mean difference (A - B).

    Both score lists must have the same length (same items, same order).
    Returns (mean_diff, ci_lo, ci_hi).  Positive means A > B.

    NumPy-accelerated with deterministic seed support.
    Falls back to pure Python if NumPy is unavailable.
    """
    if len(scores_a) != len(scores_b) or len(scores_a) < 2:
        return (float('nan'), float('nan'), float('nan'))
    try:
        import numpy as np
        if seed is not None:
            np.random.seed(seed)
        a = np.asarray(scores_a, dtype=np.float64)
        b = np.asarray(scores_b, dtype=np.float64)
        n = a.shape[0]
        idx = np.random.randint(0, n, size=(n_resamples, n))
        diffs = (a[idx] - b[idx]).mean(axis=1)
        mean_diff = float((a - b).mean())
        lo_idx = int(n_resamples * alpha / 2)
        hi_idx = int(n_resamples * (1 - alpha / 2))
        boundary = np.partition(diffs, (lo_idx, hi_idx))
        return (mean_diff, float(boundary[lo_idx]), float(boundary[hi_idx]))
    except ImportError:
        # Fallback: pure-Python
        rng = random.Random(seed) if seed is not None else random.Random()
        n = len(scores_a)
        diffs = [0.0] * n_resamples
        for i in range(n_resamples):
            s = 0.0
            for _ in range(n):
                idx = rng.randrange(n)
                s += scores_a[idx] - scores_b[idx]
            diffs[i] = s / n
        diffs.sort()
        lo_idx = int(n_resamples * alpha / 2)
        hi_idx = int(n_resamples * (1 - alpha / 2))
        mean_diff = sum(scores_a[i] - scores_b[i] for i in range(n)) / n
        return (mean_diff, diffs[lo_idx], diffs[hi_idx])


def read_paired_scores(path_a: str, path_b: str) -> Tuple[List[float], List[float]]:
    """Read two benchmark CSVs and return paired per-item scores.

    Matches rows by task_index. Both CSVs must have been generated with
    the same --seed so they contain the same tasks in the same order.
    Unmatched rows are dropped.
    """
    def _read_scores_by_index(path):
        """Read a benchmark CSV into {task_index: score} for pairing."""
        out = {}
        delim = _auto_delimiter(path)
        with open(path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter=delim):
                idx = row.get("task_index", "").strip()
                sc = row.get("score", "").strip()
                if idx and sc:
                    fv = _try_float(sc)
                    if fv is not None:
                        out[idx] = fv
        return out
    sa = _read_scores_by_index(path_a)
    sb = _read_scores_by_index(path_b)
    common = sorted(set(sa.keys()) & set(sb.keys()))
    if not common:
        return ([], [])
    return ([sa[k] for k in common], [sb[k] for k in common])


def compare_two_quants(name_a: str, name_b: str,
                       scores_a: List[float], scores_b: List[float],
                       n_resamples: int = 10000, seed: int = 42) -> Dict[str, Any]:
    """Compare two quants using paired bootstrap.

    Returns a dict with:
      mean_a, mean_b, mean_diff, ci_lo, ci_hi,
      sign: '+' if A better, '-' if B better, '~' if overlapping,
      n_items, p_value (proportion of bootstrap resamples where sign disagrees)
    """
    n = len(scores_a)
    if n < 2:
        return {
            "mean_a": float('nan'), "mean_b": float('nan'),
            "mean_diff": float('nan'), "ci_lo": float('nan'), "ci_hi": float('nan'),
            "sign": "~", "n_items": n, "p_value": float('nan'),
        }
    mean_a = sum(scores_a) / n
    mean_b = sum(scores_b) / n
    mean_diff, ci_lo, ci_hi = paired_bootstrap_ci(scores_a, scores_b,
                                                   n_resamples=n_resamples, seed=seed)
    if ci_lo > 0:
        sign = "+"
    elif ci_hi < 0:
        sign = "-"
    else:
        sign = "~"
    # p-value: proportion of bootstrap resamples where sign disagrees
    rng = random.Random(seed)
    disagree = 0
    for _ in range(n_resamples):
        s = 0.0
        for __ in range(n):
            idx = rng.randrange(n)
            s += scores_a[idx] - scores_b[idx]
        boot_diff = s / n
        if (boot_diff > 0 and sign == "-") or (boot_diff < 0 and sign == "+"):
            disagree += 1
    p_value = disagree / n_resamples
    return {
        "mean_a": mean_a, "mean_b": mean_b,
        "mean_diff": mean_diff, "ci_lo": ci_lo, "ci_hi": ci_hi,
        "sign": sign, "n_items": n, "p_value": p_value,
    }


def _auto_delimiter(path: str) -> str:
    """Detect the CSV delimiter (";" vs ",") from the first line."""
    with open(path, "r", encoding="utf-8") as f:
        first = f.readline()
    if ";" in first:
        return ";"
    return ","

def read_custom_csv(path: str, out_scores: Optional[List[float]] = None) -> Tuple[Optional[float], Optional[float], Optional[float], Dict[str, Any]]:
    """Read benchmark CSV; collect per-item scores in out_scores (for Bootstrap)."""
    scores = []
    tok_speeds = []
    latencies = []
    cpu_per_task, gpu_per_task = [], []
    ram_vals, temp_vals, vram_vals = [], [], []
    # Wrap the entire file-handling in try/except so that a missing
    # file (FileNotFoundError), a permission error, or an unreadable
    # directory gracefully returns (None, None, None, {}) instead of
    # crashing. The previous version only wrapped the `with open(...)`
    # block, but `_auto_delimiter(path)` also opens the file and is
    # called *before* the try block, so a missing file would raise
    # FileNotFoundError that propagated to the caller. Fixed 12.07.2026
    # as part of the test-coverage expansion (Prio 4.16).
    try:
        delim = _auto_delimiter(path)
    except (OSError, IOError) as e:
        print(f"  [WARN] {os.path.basename(path)}: {e}", file=sys.stderr)
        return None, None, None, {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=delim)
            for row in reader:
                sc = row.get("score", "").strip()
                if sc:
                    fv = _try_float(sc)
                    if fv is not None:
                        scores.append(fv)
                tps = row.get("tokens_per_sec", "") or row.get("tokens_per_sec", "")
                if isinstance(tps, str):
                    tps = tps.strip()
                if tps:
                    fv = _try_float(tps)
                    if fv is not None:
                        tok_speeds.append(fv)
                lat = row.get("latency_s", "") or row.get("latency", "")
                if isinstance(lat, str):
                    lat = lat.strip()
                if lat:
                    fv = _try_float(lat)
                    if fv is not None:
                        latencies.append(fv)
                # CPU/GPU: use per-task peak values (cpu_during/gpu_during),
                # NOT the pre-computed CPU_avg/GPU_avg which can be wrong
                v = _read_col(row, "cpu_during") or _read_col(row, "cpu_pct")
                if v is not None:
                    cpu_per_task.append(v)
                v = _read_col(row, "gpu_during") or _read_col(row, "gpu_pct")
                if v is not None:
                    gpu_per_task.append(v)
                for col, lst in [("RAM_avg", ram_vals), ("RAM_max", ram_vals),
                                 ("VRAM_GB", vram_vals), ("GPU_Temp_max", temp_vals)]:
                    v = _read_col(row, col)
                    if v is not None:
                        lst.append(v)
    except Exception as e:
        print(f"  [WARN] {os.path.basename(path)}: {e}", file=sys.stderr)
    if not scores:
        return None, None, None, {}
    if out_scores is not None:
        out_scores.extend(scores)
    total_latency = sum(latencies) if latencies else None
    metrics = {}
    if cpu_per_task:
        metrics["CPU_avg"] = mean(cpu_per_task)
        metrics["CPU_max"] = max(cpu_per_task)
        metrics["CPU_med"] = median(cpu_per_task)
        metrics["CPU_p90"] = _percentile(cpu_per_task, 90)
    if gpu_per_task:
        metrics["GPU_avg"] = mean(gpu_per_task)
        metrics["GPU_max"] = max(gpu_per_task)
        metrics["GPU_med"] = median(gpu_per_task)
        metrics["GPU_p90"] = _percentile(gpu_per_task, 90)
    if ram_vals:
        metrics["RAM_avg"] = mean(ram_vals)
        metrics["RAM_max"] = max(ram_vals)
        metrics["RAM_med"] = median(ram_vals)
        metrics["RAM_p90"] = _percentile(ram_vals, 90)
    if vram_vals:
        metrics["VRAM_GB"] = mean(vram_vals)
    if temp_vals:
        metrics["GPU_Temp_max"] = max(temp_vals)
        metrics["GPU_Temp_p90"] = _percentile(temp_vals, 90)
    return mean(scores), mean(tok_speeds) if tok_speeds else None, total_latency, metrics


def _ts_filter(ts: str, since: Optional[str], until: Optional[str]) -> bool:
    """Filter CSV timestamps by optional since/until range.
    Supports formats: YYYYMMDD_HHMMSS or YYYYMMDD (expanded to full-day range).
    """
    if since:
        # Normalize: if only YYYYMMDD given, append _000000
        since_full = since if "_" in since else f"{since}_000000"
        if ts < since_full:
            return False
    if until:
        until_full = until if "_" in until else f"{until}_235959"
        if ts > until_full:
            return False
    return True


def _extract_csv_sizes(mapping: Dict[str, Any], path_ss: Dict[str, int]) -> Dict[str, int]:
    """Map model_key -> sample_size for a selected {model_key: path-or-(ts,path)} mapping."""
    out: Dict[str, int] = {}
    for mk, val in mapping.items():
        p = val[1] if isinstance(val, tuple) else val
        ss = path_ss.get(p)
        if ss:
            out[mk] = ss
    return out


def find_latest_csvs(min_sample_size: int = 0, since: Optional[str] = None,
                     until: Optional[str] = None, all_runs: bool = False,
                     merge_runs: int = 0
                     ) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, Dict[str, int]]]:
    """Find CSV files for DS1000 and CoderEval, with time + run filtering.
    
    Args:
        min_sample_size: If > 0, only include CSVs with sample_size >= this.
        since: Only include CSVs with timestamp >= this (YYYYMMDD_HHMMSS or YYYYMMDD).
        until: Only include CSVs with timestamp <= this.
        all_runs: If True, keep latest CSV per model (all historical runs).
                  If False (default), only keep CSVs from the latest timestamp overall.
        merge_runs: If > 0, keep only the N newest timestamp clusters (runs),
                    per model the newest CSV. Overrides all_runs.
    
    Returns (ds1000, codereval, custom_sizes): the first two are dicts keyed by
    model_key (from CSV content) -> path, the third maps "DS1000"/"CoderEval"
    -> {model_key: sample_size} for the selected CSVs.
    """
    # Pattern: (optional tasks_) + YYYYMMDD_HHMMSS + DS1000|CoderEval + _ModelName.csv
    pat = re.compile(
        r"^(?:tasks_)?(\d{8}_\d{6})_(DS1000|CoderEval)_(.+)\.csv$"
    )
    # Collect all valid entries: list of (ts, btype, lookup_key, fpath)
    all_entries: list[tuple[str, str, str, str]] = []
    path_ss: Dict[str, int] = {}  # fpath -> sample_size
    for fname in os.listdir(RESULTS_DIR):
        m = pat.match(fname)
        if not m:
            continue
        ts = m.group(1)
        btype = m.group(2)
        model_name_from_file = m.group(3)
        
        # Time range filter
        if not _ts_filter(ts, since, until):
            continue
        
        fpath = os.path.join(RESULTS_DIR, fname)
        model_key_from_csv = None
        file_sample_size = 0
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    mk = row.get("model_key", "")
                    if mk:
                        model_key_from_csv = mk
                    ss = row.get("sample_size", "")
                    if ss:
                        try:
                            file_sample_size = int(ss)
                        except ValueError:
                            pass
                    break
        except Exception:
            print(f"  [WARN] find_latest_csvs: skipping unreadable {fname}", file=sys.stderr)
        path_ss[fpath] = file_sample_size
        
        if min_sample_size > 0 and file_sample_size < min_sample_size:
            continue
        
        lookup_key = model_key_from_csv or model_name_from_file
        lookup_key = lookup_key.replace("/", "_")
        parts = lookup_key.split("@")
        if len(parts) > 2:
            lookup_key = f"{parts[0]}@{parts[-1]}"
        if "@" in lookup_key:
            base, variant = lookup_key.split("@", 1)
            lookup_key = f"{base}@{variant.lower()}"
        
        all_entries.append((ts, btype, lookup_key, fpath))
    
    if not all_entries:
        return {}, {}, {}
    
    if merge_runs > 0:
        # Merge N newest model runs. DS1000 and CoderEval CSVs for the same
        # model have slightly different timestamps (written seconds apart), so
        # grouping by timestamp alone would split pairs → keep only 1 CSV per model.
        # Fix: group by model_key, use max(DS_ts, CE_ts) as run timestamp.
        model_groups: dict[str, dict] = {}
        for ts, btype, lookup_key, fpath in all_entries:
            if lookup_key not in model_groups:
                model_groups[lookup_key] = {"max_ts": ts, "ds1000": None, "codereval": None}
            mg = model_groups[lookup_key]
            if ts > mg["max_ts"]:
                mg["max_ts"] = ts
            if btype == "DS1000":
                if mg["ds1000"] is None or ts > mg["ds1000"][0]:
                    mg["ds1000"] = (ts, fpath)
            else:
                if mg["codereval"] is None or ts > mg["codereval"][0]:
                    mg["codereval"] = (ts, fpath)
        # Sort model runs by max timestamp descending, keep N newest
        sorted_runs = sorted(model_groups.items(),
                             key=lambda x: x[1]["max_ts"], reverse=True)[:merge_runs]
        ds1000: dict[str, str] = {}
        codereval: dict[str, str] = {}
        for mk, mg in sorted_runs:
            if mg["ds1000"]:
                ds1000[mk] = mg["ds1000"][1]
            if mg["codereval"]:
                codereval[mk] = mg["codereval"][1]
        custom_sizes = {"DS1000": _extract_csv_sizes(ds1000, path_ss),
                        "CoderEval": _extract_csv_sizes(codereval, path_ss)}
        return ds1000, codereval, custom_sizes
    elif all_runs:
        # Keep latest per model (all historical runs)
        ds1000: dict[str, tuple[str, str]] = {}
        codereval: dict[str, tuple[str, str]] = {}
        for ts, btype, lookup_key, fpath in all_entries:
            target = ds1000 if btype == "DS1000" else codereval
            if lookup_key not in target or ts > target[lookup_key][0]:
                target[lookup_key] = (ts, fpath)
        custom_sizes = {"DS1000": _extract_csv_sizes(ds1000, path_ss),
                        "CoderEval": _extract_csv_sizes(codereval, path_ss)}
        return {k: v[1] for k, v in ds1000.items()}, {k: v[1] for k, v in codereval.items()}, custom_sizes
    else:
        # Only keep CSVs from the latest timestamp overall (single benchmark run)
        latest_ts = max(ts for ts, _, _, _ in all_entries)
        ds1000: dict[str, tuple[str, str]] = {}
        codereval: dict[str, tuple[str, str]] = {}
        for ts, btype, lookup_key, fpath in all_entries:
            if ts != latest_ts:
                continue
            target = ds1000 if btype == "DS1000" else codereval
            if lookup_key not in target or ts > target[lookup_key][0]:
                target[lookup_key] = (ts, fpath)
        custom_sizes = {"DS1000": _extract_csv_sizes(ds1000, path_ss),
                        "CoderEval": _extract_csv_sizes(codereval, path_ss)}
        return {k: v[1] for k, v in ds1000.items()}, {k: v[1] for k, v in codereval.items()}, custom_sizes


def _find_newest_by_mtime(prefix: str, model_key: str) -> Optional[str]:
    """Find the newest {prefix}_{model_key} result directory by mtime.
    
    Falls back through:
    1. Case-insensitive prefix + model_key match (handles double-@ variants)
    2. Base key without @variant
    Returns the directory with the newest modification time, or None.
    """
    safe = model_key.replace("/", "_").lower()
    target_prefix = f"{prefix}_"
    candidates: list[tuple[float, str]] = []
    seen: set[str] = set()

    for dname in os.listdir(RESULTS_DIR):
        dpath = os.path.join(RESULTS_DIR, dname)
        if not os.path.isdir(dpath):
            continue
        if not dname.lower().startswith(target_prefix):
            continue
        rest = dname[len(target_prefix):]
        if rest.lower().startswith(safe):
            candidates.append((os.path.getmtime(dpath), dpath))
            seen.add(dname.lower())

    # Fallback: ohne @variant – nur EXAKTE Base-Matches oder Base@variant.
    # Fix 2026-07-31: Vorher matchte `startswith(base)` auch Modelle mit
    # gleichem Präfix und anderem Suffix (z.B. "qwen3-30b-a3b-instruct-2507"
    # matchte "qwen3-30b-a3b-instruct-2507-q2ks-mixed-autoround@Q2_K_S").
    # Bei neuerer mtime gewann dann das falsche Verzeichnis (leer) und
    # read_lmeval_per_model() lieferte None für alle LM-Eval-Benchmarks.
    base = model_key.split("@")[0].replace("/", "_").lower()
    if base != safe:
        for dname in os.listdir(RESULTS_DIR):
            dpath = os.path.join(RESULTS_DIR, dname)
            if not os.path.isdir(dpath) or dname.lower() in seen:
                continue
            if not dname.lower().startswith(target_prefix):
                continue
            rest = dname[len(target_prefix):].lower()
            if rest == base or rest.startswith(base + "@"):
                candidates.append((os.path.getmtime(dpath), dpath))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _pick_newest_eval_file(dpath: str) -> Optional[str]:
    """Pick the newest .eval_results.json in dpath by mtime."""
    candidates = []
    for fname in os.listdir(dpath):
        if fname.endswith(".eval_results.json"):
            fpath = os.path.join(dpath, fname)
            candidates.append((os.path.getmtime(fpath), fpath))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def try_read_evalplus(model_key: str) -> Optional[Dict[str, float]]:
    """Read EvalPlus (HumanEval+/MBPP+) results for a model.

    Finds the newest evalplus result directory for the model and returns
    {humaneval_base, humaneval_plus, mbpp_base, mbpp_plus} as pass rates,
    or None when no readable results exist.
    """
    root = _find_newest_by_mtime("evalplus", model_key)
    if not root:
        return None
    results = {}
    for dataset in ["humaneval", "mbpp"]:
        dpath = os.path.join(root, dataset)
        if not os.path.isdir(dpath):
            continue
        eval_file = _pick_newest_eval_file(dpath)
        if eval_file is None:
            continue
        try:
            with open(eval_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            print(f"  [WARN] Skipping corrupt eval file: {os.path.basename(eval_file)}", file=sys.stderr)
            continue
        ev = data.get("eval", {})
        total = len(ev)
        base_pass = sum(1 for v in ev.values() if v[0].get("base_status") == "pass")
        plus_pass = sum(1 for v in ev.values() if v[0].get("plus_status") == "pass")
        if total:
            results[f"{dataset}_base"] = base_pass / total
            results[f"{dataset}_plus"] = plus_pass / total
    return results if results else None


def _read_results_json(search_dir: str, task_name: str, metric_priority: List[str]) -> Any:
    """Read a single results_*.json and return the first matching metric value for task_name."""
    if not os.path.isdir(search_dir):
        return None
    for fname in os.listdir(search_dir):
        if not (fname.startswith("results_") and fname.endswith(".json")):
            continue
        try:
            with open(os.path.join(search_dir, fname), "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            print(f"  [WARN] _read_results_json: skipping corrupt {fname}", file=sys.stderr)
            continue
        td = data.get("results", {}).get(task_name, {})
        for metric in metric_priority:
            if metric in td:
                return td[metric]
    return None

def read_lmeval_per_model(model_key: str) -> Optional[Dict[str, float]]:
    """Read LM-Eval results for a model into a {benchmark: score} dict.

    Scans all results_*.json files (newest first) under the model's
    lmeval directory and picks the first metric available per task from
    the METRICS priority list. MMLU-Pro subsets are skipped.
    """
    root = _find_newest_by_mtime("lmeval", model_key)
    if not root:
        return None
    results = {}

    METRICS = ["exact_match,custom-extract", "exact_match,remove_whitespace",
               "exact_match,flexible-extract", "bleu_acc,none", "rouge1_acc,none",
               "exact_match,none", "math_verify,none",
               "prompt_level_strict_acc,none", "inst_level_strict_acc,none",
               "prompt_level_loose_acc,none", "inst_level_loose_acc,none"]

    # Collect all results_*.json files across all subdirectories, sorted by
    # modification time (newest first) so stale data from old runs is
    # overridden by fresh results when multiple runs exist for the same model.
    json_files = []
    for item in os.listdir(root):
        sub = os.path.join(root, item)
        if os.path.isdir(sub) and item not in MMLU_PRO_SUBSETS:
            for fname in os.listdir(sub):
                if fname.startswith("results_") and fname.endswith(".json"):
                    fpath = os.path.join(sub, fname)
                    json_files.append(fpath)
    # Sort by modification time descending (newest first) so stale data
    # from old runs is overridden by fresh results.
    json_files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    for fpath in json_files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            print(f"  [WARN] Skipping corrupt JSON: {os.path.basename(fpath)}", file=sys.stderr)
            continue
        for task_name, task_data in data.get("results", {}).items():
            alias = {"arc_challenge_chat": "ARC-Challenge",
                      "hellaswag_gen": "HellaSwag",
                      "truthfulqa_gen": "TruthfulQA",
                      "truthfulqa_mc1": "TruthfulQA",
                      "truthfulqa_mc2": "TruthfulQA",
                      "ifeval": "IFEval",
                      "bbh_zeroshot": "BBH",
                      "minerva_math500": "MATH-500"}.get(task_name, task_name)
            if alias in results:
                continue  # keep the newest (first encountered) value
            for metric in METRICS:
                if metric in task_data:
                    results[alias] = task_data[metric]
                    break

    # MMLU-Pro (ARCHIVIERT): The 14-subset aggregation is no longer
    # performed here. If you re-enable MMLU-Pro via
    # `Archiv/run_mmlupro_benchmark.py`, the per-model results will be
    # saved as a separate file `mmlupro_archived_*.csv` and can be
    # merged in post-processing. See Code-Review_2026-07-12.md §3.1 D4.

    return results if results else None


def read_agentic(model_key: str) -> Optional[float]:
    """Read the newest agentic-tool-eval final score (0.0-1.0) for a model.

    Falls back to the average of scenario results when no final_score
    field is present; None when nothing can be read.
    """
    root = _find_newest_by_mtime("agentic", model_key)
    if not root:
        return None
    # Recursively find all .json files
    all_json = []
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            if fname.endswith(".json"):
                all_json.append(os.path.join(dirpath, fname))
    if not all_json:
        return None
    all_json.sort(key=_agentic_ts_from_filename, reverse=True)
    latest = all_json[0]
    try:
        with open(latest, "r", encoding="utf-8") as f:
            data = json.load(f)
        raw = data.get("final_score") if isinstance(data, dict) else None
        if raw is not None:
            return raw / 100.0
        scores_meta = data.get("scores", {}) if isinstance(data, dict) else {}
        results_list = scores_meta.get("scenario_results", [])
        if results_list:
            vals = [s.get("score", 0) for s in results_list if isinstance(s, dict)]
            return sum(vals) / len(vals) if vals else None
    except Exception:
        print(f"  [WARN] _try_read_agentic_score: could not parse {os.path.basename(latest)}", file=sys.stderr)
        return None
    return None


def _agentic_ts_from_filename(p: str) -> str:
    """Extract the 14-digit timestamp from an agentic JSON filename (fallback: basename)."""
    bn = os.path.basename(p).replace(".json", "")
    for part in bn.split("_"):
        if len(part) == 14 and part.isdigit():
            return part
    return bn


def _collect_pipeline_sample_sizes(model_keys: List[str]) -> Dict[str, set[int]]:
    """Distinct sample sizes per non-custom pipeline (EvalPlus/LM-Eval/Agentic).

    Reads the newest result files of the given model keys. Any unreadable
    or missing data is skipped silently.
    """
    sizes: Dict[str, set[int]] = {}
    for mk in model_keys:
        # EvalPlus: len(eval) of the newest humaneval/mbpp eval_results.json
        root = _find_newest_by_mtime("evalplus", mk)
        if root:
            for ds in ("humaneval", "mbpp"):
                dpath = os.path.join(root, ds)
                if not os.path.isdir(dpath):
                    continue
                eval_file = _pick_newest_eval_file(dpath)
                if not eval_file:
                    continue
                try:
                    with open(eval_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    n = len(data.get("eval", {}))
                except Exception:
                    continue
                if n:
                    sizes.setdefault("EvalPlus", set()).add(n)

        # LM-Eval: sample_len from the newest results_*.json (any task)
        root = _find_newest_by_mtime("lmeval", mk)
        if root:
            candidates: list[tuple[float, str]] = []
            for item in os.listdir(root):
                sub = os.path.join(root, item)
                if not os.path.isdir(sub):
                    continue
                for fname in os.listdir(sub):
                    if fname.startswith("results_") and fname.endswith(".json"):
                        fpath = os.path.join(sub, fname)
                        candidates.append((os.path.getmtime(fpath), fpath))
            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                try:
                    with open(candidates[0][1], "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for td in data.get("results", {}).values():
                        n = td.get("sample_len") if isinstance(td, dict) else None
                        if n:
                            sizes.setdefault("LM-Eval", set()).add(n)
                            break
                except Exception:
                    pass

        # Agentic: total_scenarios from the newest JSON
        root = _find_newest_by_mtime("agentic", mk)
        if root:
            all_json: list[str] = []
            for dirpath, _, filenames in os.walk(root):
                for fname in filenames:
                    if fname.endswith(".json"):
                        all_json.append(os.path.join(dirpath, fname))
            if all_json:
                all_json.sort(key=_agentic_ts_from_filename, reverse=True)
                try:
                    with open(all_json[0], "r", encoding="utf-8") as f:
                        data = json.load(f)
                    n = data.get("total_scenarios") if isinstance(data, dict) else None
                except Exception:
                    n = None
                if n:
                    sizes.setdefault("Agentic", set()).add(n)
    return sizes


def _describe_sample_sizes(sizes: Dict[str, set[int]]) -> str:
    """Human-readable sample-size summary: '20 (DS1000, CoderEval), 5 (EvalPlus)'."""
    if not sizes:
        return "mixed"
    grouped: Dict[int, List[str]] = {}
    mixed_parts: List[str] = []
    for bench in ("DS1000", "CoderEval", "EvalPlus", "LM-Eval", "Agentic"):
        ss = sizes.get(bench)
        if not ss:
            continue
        if len(ss) == 1:
            grouped.setdefault(next(iter(ss)), []).append(bench)
        else:
            mixed_parts.append(f"{','.join(str(v) for v in sorted(ss))} ({bench})")
    parts = [f"{size} ({', '.join(grouped[size])})" for size in sorted(grouped, reverse=True)]
    parts += mixed_parts
    return ", ".join(parts) if parts else "mixed"


def compute_category_scores(bench_scores: Dict[str, Optional[float]]) -> Dict[str, Optional[float]]:
    """Compute weighted category scores and Overall.
    
    Normalization: If a category has only partial data (e.g., only
    HumanEval+ but not MBPP+), available benchmarks are scaled up
    proportionally (total weight = 1.0). This prevents a category
    with only one benchmark from having the same impact as one with four.
    
    Overall = sum(cat_weight * cat_score) / sum(cat_weight)
    for all categories with data.
    """
    cats = {}
    for cat, bench_weights in CAT_WEIGHTS.items():
        score = 0.0
        total_w = 0.0
        for bench, w in bench_weights.items():
            if bench in bench_scores and bench_scores[bench] is not None:
                score += bench_scores[bench] * w
                total_w += w
        cats[cat] = score / total_w if total_w > 0 else None
    overall = 0.0
    total_w = 0.0
    for cat, w in OVERALL_WEIGHTS.items():
        if cats[cat] is not None:
            overall += cats[cat] * w
            total_w += w
    cats["overall"] = overall / total_w if total_w > 0 else None
    return cats


@dataclass
class ModelData:
    name: str
    ds1000: Optional[float] = None
    ds1000_ci_lo: Optional[float] = None
    ds1000_ci_hi: Optional[float] = None
    codereval: Optional[float] = None
    codereval_ci_lo: Optional[float] = None
    codereval_ci_hi: Optional[float] = None
    humaneval: Optional[float] = None
    mbpp: Optional[float] = None
    arc: Optional[float] = None
    hellaswag: Optional[float] = None
    truthfulqa: Optional[float] = None
    mmlu_pro: Optional[float] = None
    ifeval: Optional[float] = None
    math500: Optional[float] = None
    agentic: Optional[float] = None
    coding: Optional[float] = None
    knowledge: Optional[float] = None
    math: Optional[float] = None
    overall: Optional[float] = None
    runtime_min: Optional[str] = None
    eff_score_h: Optional[str] = None
    coding_eff_score_h: Optional[str] = None
    tok_s: Optional[str] = None
    vram_gb: Optional[float] = None
    quant: Optional[str] = None
    cpu_med: Optional[float] = None
    cpu_p90: Optional[float] = None
    gpu_med: Optional[float] = None
    gpu_p90: Optional[float] = None
    ram_med: Optional[float] = None
    ram_p90: Optional[float] = None
    gpu_temp_p90: Optional[float] = None

    def to_csv_dict(self) -> Dict[str, Any]:
        """Flatten the model row into the CSV column order."""
        return {
            "Model": self.name,
            "DS1000": self.ds1000,
            "DS1000_CI_lo": self.ds1000_ci_lo,
            "DS1000_CI_hi": self.ds1000_ci_hi,
            "CoderEval": self.codereval,
            "CoderEval_CI_lo": self.codereval_ci_lo,
            "CoderEval_CI_hi": self.codereval_ci_hi,
            "HumanEval+": self.humaneval,
            "MBPP+": self.mbpp,
            "ARC-Challenge": self.arc,
            "HellaSwag": self.hellaswag,
            "TruthfulQA": self.truthfulqa,
            "IFEval": self.ifeval,
            "MATH-500": self.math500,
            "Agentic": self.agentic,
            "Coding": self.coding,
            "Knowledge": self.knowledge,
            "Math": self.math,
            "Overall": self.overall,
            "Runtime (min)": self.runtime_min,
            "Eff (Score/h)": self.eff_score_h,
            "Coding Eff (Score/h)": self.coding_eff_score_h,
            "tok/s": self.tok_s,
            "VRAM (GB)": self.vram_gb,
            "CPU_med": self.cpu_med,
            "CPU_p90": self.cpu_p90,
            "GPU_med": self.gpu_med,
            "GPU_p90": self.gpu_p90,
            "RAM_med": self.ram_med,
            "RAM_p90": self.ram_p90,
            "GPU_Temp_p90": self.gpu_temp_p90,
        }


def read_data(model_keys: Optional[List[str]] = None, min_sample_size: int = 0,
              exclude_benchmarks: Optional[List[str]] = None,
              since: Optional[str] = None, until: Optional[str] = None,
              all_runs: bool = False, no_installed: bool = False,
              merge_runs: int = 0,
              out_sample_sizes: Optional[Dict[str, Dict[str, int]]] = None,
              out_model_keys: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Collect, score and aggregate results for all requested models.

    Discovers DS1000/CoderEval CSVs via find_latest_csvs(), optionally
    auto-discovers model keys from result directories, reads per-pipeline
    scores (Custom/EvalPlus/LM-Eval/Agentic), applies weighting and
    per-task bootstrap CIs, and returns ModelData dicts ready for
    CSV/Markdown output. Optional out_* parameters receive the sample
    sizes and model keys actually used.
    """
    ds1000_files, codereval_files, custom_sizes = find_latest_csvs(
        min_sample_size=min_sample_size, since=since, until=until, all_runs=all_runs, merge_runs=merge_runs)
    print(f"  DS1000 CSVs:  {len(ds1000_files)}")
    print(f"  CoderEval:    {len(codereval_files)}")
    if out_sample_sizes is not None:
        out_sample_sizes.update(custom_sizes)

    # Auto-discover model keys from result CSVs if none specified
    if model_keys is None:
        seen: set[str] = set()
        model_keys = []
        for mk in ds1000_files:
            if mk not in seen:
                model_keys.append(mk)
                seen.add(mk)
        for mk in codereval_files:
            if mk not in seen:
                model_keys.append(mk)
                seen.add(mk)

        # Discover models from evalplus/lmeval/agentic directories.
        # When min_sample_size > 0, only add models that also have at
        # least one qualifying CSV — otherwise unconstrained directory
        # discovery shows models that never ran with the requested
        # sample size (e.g. --sample-size 30 would include dozens of
        # models from older evalplus runs with no sample_size=30 data).
        csv_models: set[str] = set(ds1000_files) | set(codereval_files)
        scan_dirs = ["evalplus_", "lmeval_", "agentic_"]
        added = 0
        for prefix in scan_dirs:
            for dname in os.listdir(RESULTS_DIR):
                d = os.path.join(RESULTS_DIR, dname)
                if os.path.isdir(d) and dname.startswith(prefix):
                    mk = dname[len(prefix):]
                    if mk not in seen and (min_sample_size == 0 or mk in csv_models):
                        model_keys.append(mk)
                        seen.add(mk)
                        added += 1
        if added:
            print(f"  +{added} additional models from benchmark directories")

        # Filter to only currently-installed models (unless --no-installed)
        if not no_installed:
            installed = _get_installed_model_keys()
            if installed:
                before = len(model_keys)
                model_keys = [mk for mk in model_keys if mk in installed]
                print(f"  Installed filter: {before} -> {len(model_keys)} models")

    # Normalize and deduplicate model_keys: lowercase @variant, merge duplicates
    model_keys = _normalize_model_keys(model_keys)

    rows = []
    for model_key in model_keys:
        display = _get_display_name(model_key) if not model_key.startswith("_dummy_") else model_key
        bench_scores = {}
        tok_speeds = {}
        latencies = []

        # DS1000 – match by model_key (handle missing @variant in CSV)
        ds_scores: List[float] = []
        for mk, fn in ds1000_files.items():
            if mk == model_key or ("@" not in mk and mk.split("@")[0] == model_key.split("@")[0]):
                ds_score, ds_tps, ds_lat, ds_m = read_custom_csv(os.path.join(RESULTS_DIR, fn),
                                                                  out_scores=ds_scores)
                if ds_score is not None:
                    bench_scores["DS1000"] = ds_score
                    tok_speeds["DS1000"] = ds_tps
                    if ds_lat: latencies.append(ds_lat)
                break
        else:
            ds_score = ds_tps = None
            ds_m = {}

        # CoderEval – match by model_key (handle missing @variant in CSV)
        ce_scores: List[float] = []
        for mk, fn in codereval_files.items():
            if mk == model_key or ("@" not in mk and mk.split("@")[0] == model_key.split("@")[0]):
                ce_score, ce_tps, ce_lat, ce_m = read_custom_csv(os.path.join(RESULTS_DIR, fn),
                                                                  out_scores=ce_scores)
                if ce_score is not None:
                    bench_scores["CoderEval"] = ce_score
                    tok_speeds["CoderEval"] = ce_tps
                    if ce_lat: latencies.append(ce_lat)
                break
        else:
            ce_score = ce_tps = None
            ce_m = {}

        # Aggregate system metrics from all available benchmarks
        all_metrics = [m for m in [ds_m, ce_m] if m]
        sys_metrics = {}
        if all_metrics:
            for k in ["CPU_med", "CPU_p90",
                       "GPU_med", "GPU_p90",
                       "RAM_med", "RAM_p90",
                       "VRAM_GB", "GPU_Temp_p90"]:
                vals = [m.get(k) for m in all_metrics if m.get(k) is not None]
                if vals:
                    sys_metrics[k] = max(vals)

        # EvalPlus
        ep = try_read_evalplus(model_key)
        if ep:
            bench_scores["HumanEval+_plus"] = ep.get("humaneval_plus", 0)
            bench_scores["MBPP+_plus"] = ep.get("mbpp_plus", 0)
            he_base = ep.get("humaneval_base", 0)
            mb_base = ep.get("mbpp_base", 0)
        else:
            he_base = mb_base = None

        # LM-Eval per model
        lmev = read_lmeval_per_model(model_key)
        if lmev:
            for k, v in lmev.items():
                bench_scores[k] = v

        # Agentic (tool-eval-bench)
        agentic_score = read_agentic(model_key)
        if agentic_score is not None:
            bench_scores["Agentic"] = agentic_score

        # Exclude benchmarks if requested (removes them before category scoring)
        if exclude_benchmarks:
            for b in exclude_benchmarks:
                if b in bench_scores:
                    del bench_scores[b]

        # Runtime (hours) from DS1000+CoderEval latencies
        runtime_h = sum(latencies) / 3600 if latencies else None
        avg_tps = mean([v for v in tok_speeds.values() if v is not None]) if tok_speeds else None

        # Category scores
        cats = compute_category_scores(bench_scores)

        # Print per-model
        print(f"\n  {display}")
        for b in ["DS1000", "CoderEval", "HumanEval+_plus", "MBPP+_plus",
                   "ARC-Challenge", "HellaSwag", "TruthfulQA", "MATH-500", "IFEval"]:
            v = bench_scores.get(b)
            if v is not None:
                print(f"    {b:20s} {v:.1%}")
        agentic_v = bench_scores.get("Agentic")
        if agentic_v is not None:
            print(f"    {'Agentic':20s} {agentic_v:.1%}")
        print(f"    {'Coding':20s} {cats['coding']:.1%}" if cats.get('coding') is not None else "")
        print(f"    {'Knowledge':20s} {cats['knowledge']:.1%}" if cats.get('knowledge') is not None else "")
        print(f"    {'Math':20s} {cats['math']:.1%}" if cats.get('math') is not None else "")
        print(f"    {'Overall':20s} {cats['overall']:.1%}" if cats.get('overall') is not None else "")
        rt_min = runtime_h * 60 if runtime_h else None
        runtime_str = f"{rt_min:.1f} min" if rt_min else "—"
        print(f"    {'Runtime':20s} {runtime_str}")
        eff_str = f"{cats['overall']/runtime_h:.1f}" if cats.get('overall') is not None and runtime_h else "—"
        print(f"    {'Eff (Score/h)':20s} {eff_str} %p/h")

        def pct(val: Optional[float]) -> Optional[float]:
            """Fraction to percent (0-100) with 2 decimals; None passthrough."""
            return round(val * 100, 2) if val is not None else None

        # Bootstrap CIs (only with 2+ per-item scores)
        ds_ci_lo = ds_ci_hi = None
        ce_ci_lo = ce_ci_hi = None
        if len(ds_scores) > 1:
            ds_ci_lo, ds_ci_hi = bootstrap_ci(ds_scores)
        if len(ce_scores) > 1:
            ce_ci_lo, ce_ci_hi = bootstrap_ci(ce_scores)

        coding_eff = f"{cats['coding']/runtime_h:.1f}" if cats.get('coding') is not None and runtime_h else ""
        vram = _lookup_vram(model_key)
        rows.append(ModelData(
            name=display,
            ds1000=pct(ds_score),
            ds1000_ci_lo=pct(ds_ci_lo),
            ds1000_ci_hi=pct(ds_ci_hi),
            codereval=pct(ce_score),
            codereval_ci_lo=pct(ce_ci_lo),
            codereval_ci_hi=pct(ce_ci_hi),
            humaneval=pct(bench_scores.get('HumanEval+_plus')),
            mbpp=pct(bench_scores.get('MBPP+_plus')),
            arc=pct(bench_scores.get('ARC-Challenge')),
            hellaswag=pct(bench_scores.get('HellaSwag')),
            truthfulqa=pct(bench_scores.get('TruthfulQA')),
            ifeval=pct(bench_scores.get('IFEval')),
            math500=pct(bench_scores.get('MATH-500')),
            agentic=pct(agentic_score),
            coding=pct(cats.get('coding')),
            knowledge=pct(cats.get('knowledge')),
            math=pct(cats.get('math')),
            overall=pct(cats.get('overall')),
            runtime_min=f"{rt_min:.1f}" if rt_min else "",
            eff_score_h=f"{cats['overall']/runtime_h:.1f}" if cats.get('overall') is not None and runtime_h else "",
            coding_eff_score_h=coding_eff,
            tok_s=f"{avg_tps:.1f}" if avg_tps else "",
            vram_gb=vram["vram_gb"] if vram else "",
            quant=vram["quant"] if vram else "",
            cpu_med=sys_metrics.get("CPU_med"),
            cpu_p90=sys_metrics.get("CPU_p90"),
            gpu_med=sys_metrics.get("GPU_med"),
            gpu_p90=sys_metrics.get("GPU_p90"),
            ram_med=sys_metrics.get("RAM_med"),
            ram_p90=sys_metrics.get("RAM_p90"),
            gpu_temp_p90=sys_metrics.get("GPU_Temp_p90"),
        ))
    if out_model_keys is not None:
        out_model_keys.extend(model_keys)
    return [r.to_csv_dict() for r in rows]


# ── helpers ──
_NUMERIC_CELL_RE = re.compile(r"^-?\d+(?:\.\d+)?$")


def _align_decimal_cells(cells: List[str]) -> None:
    """Right-align numeric cells in place so decimal points align per column.

    Only cells matching a plain number (optional minus sign, integer part,
    optional fractional part) are touched; all other values (e.g. "80%",
    "0% [0%-0%]", "—") are left as-is and are right-aligned afterwards to
    the full column width.
    """
    int_w = 0
    frac_w = 0
    dotted = [False] * len(cells)
    for i, v in enumerate(cells):
        if _NUMERIC_CELL_RE.match(v) and "." in v:
            ip, fp = v.split(".", 1)
            int_w = max(int_w, len(ip))
            frac_w = max(frac_w, len(fp))
            dotted[i] = True
    if not int_w:
        return
    for i, v in enumerate(cells):
        if dotted[i]:
            ip, fp = v.split(".", 1)
            cells[i] = ip.rjust(int_w) + "." + fp.ljust(frac_w)
        elif _NUMERIC_CELL_RE.match(v):
            cells[i] = v.rjust(int_w + 1 + frac_w)


def _render_complete_table(rows: List[Dict[str, Any]], header_names: List[str],
                           header_units: List[str], cols_md: List[str]) -> List[str]:
    """Render the complete-results Markdown table.

    Column widths are content-driven: the longest header, unit or data cell
    determines the width of its column (the longest model name therefore
    sizes the first column). Numeric cells are aligned on their decimal
    point. Returns the table lines (two-line header + separator + data rows).
    """
    # Decimal-aligned cells per column
    col_cells: List[List[str]] = []
    widths: List[int] = []
    for i, c in enumerate(cols_md):
        cells = [str(r.get(c, "")) for r in rows]
        _align_decimal_cells(cells)
        col_cells.append(cells)
        w = max(len(header_names[i]), len(header_units[i]),
                *(len(cell) for cell in cells))
        if i == 0:
            w = max(w, len("Model"))
        widths.append(w)

    def _md_cell(txt: str, w: int, is_model: bool = False) -> str:
        """Pad a table cell to width (left-aligned for model names, right-aligned otherwise)."""
        s = str(txt)
        return s.ljust(w) if is_model else s.rjust(w)

    lines: List[str] = []
    parts = [_md_cell(header_names[0], widths[0], True)]
    parts += [_md_cell(h, w) for h, w in zip(header_names[1:], widths[1:])]
    lines.append("| " + " | ".join(parts) + " |")

    parts = [_md_cell(header_units[0], widths[0], True)]
    parts += [_md_cell(u, w) for u, w in zip(header_units[1:], widths[1:])]
    lines.append("| " + " | ".join(parts) + " |")

    lines.append("| " + " | ".join("-" * max(3, w) for w in widths) + " |")

    for r_i in range(len(rows)):
        parts = [_md_cell(col_cells[i][r_i], widths[i], i == 0)
                 for i in range(len(cols_md))]
        lines.append("| " + " | ".join(parts) + " |")
    return lines


def _val(key: str, r: Dict[str, Any], pct: bool = True) -> str:
    """Format a result value for the Markdown tables ("—" for missing).

    pct=True renders "NN%", otherwise one decimal (or integer above 100).
    """
    v = r.get(key, "")
    if v in (None, "", "—"):
        return "—"
    try:
        fv = float(v)
        if not pct:
            if fv < 100:
                return f"{fv:.1f}"
            return f"{fv:.0f}"
        s = f"{fv:.0f}"
        return f"{s}%"
    except (ValueError, TypeError):
        return str(v)

def _top(rows: List[Dict[str, Any]], sort_key: str) -> List[Dict[str, Any]]:
    """Top-5 rows by a numeric sort_key, ignoring missing values."""
    valid = [r for r in rows if r.get(sort_key) not in (None, "", "—")]
    if not valid:
        return []
    return sorted(valid, key=lambda x: float(x.get(sort_key, 0)), reverse=True)[:5]

def _write_tbl(f: Any, title: str, headers: List[str], sorted_rows: List[Dict[str, Any]], keys: List[str], pct_flags: Optional[List[bool]] = None) -> None:
    """Write a ranked Markdown table (### title + header + data rows).

    Rows are written with a rank column and decimal-aligned numeric
    cells; pct_flags controls percent vs plain-number formatting per
    column. Empty input is a no-op.
    """
    if not sorted_rows:
        return
    if pct_flags is None:
        pct_flags = [True] * len(keys)
    f.write(f"\n### {title}\n")
    all_h = ["Rang"] + headers

    # Content-driven widths: longest header or data cell per column,
    # numeric cells aligned on their decimal point.
    data_rows = []
    for i, r in enumerate(sorted_rows, 1):
        vals = [str(i), r['Model']]
        for key, pct_flag in zip(keys, pct_flags):
            vals.append(_val(key, r, pct=pct_flag))
        data_rows.append(vals)
    ws = []
    for col in range(len(all_h)):
        cells = [all_h[col]] + [row[col] for row in data_rows]
        if col >= 2:
            _align_decimal_cells(cells)
        for ri in range(len(data_rows)):
            data_rows[ri][col] = cells[ri + 1]
        ws.append(max(3, max(len(c) for c in cells)))

    def cell(txt: str, i: int) -> str:
        """Pad a table cell: centered rank, left-aligned model, right-aligned data."""
        w = ws[i]
        if i == 0:
            return txt.center(w)
        elif i == 1:
            return txt.ljust(w)
        else:
            return txt.rjust(w)
    cells_header = [cell(h, i) for i, h in enumerate(all_h)]
    f.write("| " + " | ".join(cells_header) + " |\n")
    cells_sep = []
    for i, w in enumerate(ws):
        if i == 0:
            cells_sep.append(":" + "-" * (w - 2) + ":")
        elif i == 1:
            cells_sep.append(":" + "-" * (w - 1))
        else:
            cells_sep.append("-" * (w - 1) + ":")
    f.write("| " + " | ".join(cells_sep) + " |\n")
    for row in data_rows:
        cells_data = [cell(v, j) for j, v in enumerate(row)]
        f.write("| " + " | ".join(cells_data) + " |\n")


def _run_comparison_mode(args: argparse.Namespace) -> None:
    """Paired bootstrap comparison for 2+ models."""
    parts = [p.strip() for p in args.compare.split(",")]
    if len(parts) < 2:
        error("--compare requires at least two comma-separated model keys")
        sys.exit(1)
    print("=" * 60)
    print("  Paired Quant Comparison (v13)")
    print(f"  Models: {', '.join(parts)}")
    print(f"  Seed: {args.seed}")
    print("=" * 60)
    merge_runs = args.runs if args.runs > 0 else (2 if args.merge else 0)
    ds1000_files, codereval_files, _ = find_latest_csvs(
        min_sample_size=args.sample_size, since=args.since, until=args.until,
        all_runs=args.all_runs, merge_runs=merge_runs)
    benchmarks_to_compare = []
    if args.compare_benchmark == "all":
        benchmarks_to_compare = [("DS1000", ds1000_files), ("CoderEval", codereval_files)]
    elif args.compare_benchmark in ("DS1000", "CoderEval"):
        benchmarks_to_compare = [
            (args.compare_benchmark, ds1000_files if args.compare_benchmark == "DS1000" else codereval_files)
        ]
    else:
        benchmarks_to_compare = [("DS1000", ds1000_files), ("CoderEval", codereval_files)]
    results = []
    for bench_name, files_dict in benchmarks_to_compare:
        print(f"\n  --- {bench_name} ---")
        for key_a, key_b in itertools.combinations(parts, 2):
            path_a = files_dict.get(key_a)
            path_b = files_dict.get(key_b)
            if not path_a or not path_b:
                missing = key_a if not path_a else key_b
                warn(f"No CSV for {missing}, skipping {key_a} vs {key_b}")
                continue
            scores_a, scores_b = read_paired_scores(path_a, path_b)
            if not scores_a:
                warn(f"No overlapping items for {key_a} vs {key_b}, skipping")
                continue
            result = compare_two_quants(key_a, key_b, scores_a, scores_b, args.seed)
            results.append(result)
            pval = result["p_value"]
            stars = " ***" if pval < 0.001 else (" **" if pval < 0.01 else (" *" if pval < 0.05 else ""))
            direction = f"scored {result['diff']:+.1f} points" if result["key_a_higher"] else f"scored {result['diff']:+.1f} points (inverted)"
            print(f"    {result['key_a']} vs {result['key_b']}: {result['mean_a']:.1f} vs {result['mean_b']:.1f} ({direction}), p={pval:.4f}{stars}")
    print(f"\n  {'='*50}")
    if results:
        avg_diff = sum(r["diff"] for r in results) / len(results)
        print(f"  Average diff: {avg_diff:+.1f} points")
    print("  Done.")
    sys.exit(0)


def _parse_args() -> Any:
    """Parse the CLI arguments and return the namespace."""
    import argparse
    parser = argparse.ArgumentParser(description="Consolidate benchmark results")
    parser.add_argument("--models", type=str, default=None,
                        help="Comma-separated list of model keys to consolidate (default: auto-discover from CSVs)")
    parser.add_argument("--compare", type=str, default=None,
                        help="Paired bootstrap comparison: 'modelA,modelB' (both must have been run with --seed)")
    parser.add_argument("--compare-benchmark", type=str, default=None,
                        help="Benchmark for comparison (DS1000, CoderEval, or 'all' for both)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for paired bootstrap (default: 42)")
    parser.add_argument("--sample-size", type=int, default=0,
                        help="Minimum sample_size filter for DS1000/CoderEval CSVs (default: no filter)")
    parser.add_argument("--exclude-benchmarks", type=str, default=None,
                        help="Comma-separated benchmarks to exclude (e.g. 'IFEval,Agentic')")
    parser.add_argument("--since", type=str, default=None,
                        help="Include only CSVs with timestamp >= this (format: YYYYMMDD_HHMMSS or YYYYMMDD)")
    parser.add_argument("--until", type=str, default=None,
                        help="Include only CSVs with timestamp <= this (format: YYYYMMDD_HHMMSS or YYYYMMDD)")
    parser.add_argument("--all-runs", action="store_true", default=False,
                        help="Include all historical benchmark runs (default: only latest run)")
    parser.add_argument("--no-installed", action="store_true", default=False,
                        help="Skip installed-model filter (default: only currently installed models)")
    parser.add_argument("--merge", action="store_true", default=False,
                        help="Merge mehrere Benchmark-Laeufe (neuestes CSV pro Modell, kein Installed-Filter)")
    parser.add_argument("--runs", type=int, default=0,
                        help="Anzahl der zu mergenden Laeufe (Timestamp-Cluster, default: 2 bei --merge)")
    return parser.parse_args()


def _read_all_data(args: Any, model_keys: Optional[List[str]],
                   exclude: Optional[List[str]]) -> Tuple[List[Dict[str, Any]], Dict[str, set[int]]]:
    """Apply merge/installed flags, print the banner and read all result data.

    Returns (rows, ss_ctx) where ss_ctx maps pipeline -> used sample sizes.
    """
    merge_runs = args.runs if args.runs > 0 else 0
    if args.merge:
        args.no_installed = True
        if merge_runs == 0:
            args.all_runs = True

    print("=" * 60)
    print("  Consolidating Dense-Run Results (v13)")
    print("  + Bootstrap 95% CI for DS1000 / CoderEval")
    ss_str = f" (min sample_size={args.sample_size})" if args.sample_size else ""
    filters = []
    if args.since:
        filters.append(f"since={args.since}")
    if args.until:
        filters.append(f"until={args.until}")
    if args.all_runs:
        filters.append("all-runs")
    elif not filters:
        filters.append("latest-run")
    if not args.no_installed:
        filters.append("installed-only")
    filter_str = f" [{', '.join(filters)}]" if filters else ""
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}{ss_str}{filter_str}")
    print("=" * 60)
    ss_sizes: Dict[str, Dict[str, int]] = {}
    model_keys_used: List[str] = []
    rows = read_data(model_keys=model_keys, min_sample_size=args.sample_size,
                     exclude_benchmarks=exclude, since=args.since, until=args.until,
                     all_runs=args.all_runs, no_installed=args.no_installed,
                     merge_runs=merge_runs,
                     out_sample_sizes=ss_sizes, out_model_keys=model_keys_used)

    # Sample sizes actually used across the included runs (for the MD header)
    ss_ctx: Dict[str, set[int]] = {btype: set(m2s.values()) for btype, m2s in ss_sizes.items()}
    if not args.sample_size:
        ss_ctx.update(_collect_pipeline_sample_sizes(model_keys_used))
    return rows, ss_ctx


def _write_csv(rows: List[Dict[str, Any]]) -> Tuple[str, str]:
    """Write konsolidiert_<timestamp>.csv with the unified column order.

    Returns (csv_path, timestamp) so the Markdown report can reuse the
    timestamp for a consistent filename.
    """
    fn_csv = ["Model"]
    fn_csv += ["DS1000", "DS1000_CI_lo", "DS1000_CI_hi"]
    fn_csv += ["CoderEval", "CoderEval_CI_lo", "CoderEval_CI_hi"]
    fn_csv += ["HumanEval+", "MBPP+",
               "ARC-Challenge", "HellaSwag", "TruthfulQA", "IFEval", "MATH-500",
               "Agentic",
               "Coding", "Knowledge", "Math", "Overall", "Runtime (min)",
               "Eff (Score/h)", "Coding Eff (Score/h)", "tok/s",
               "VRAM (GB)",
               "CPU_med", "CPU_p90",
               "GPU_med", "GPU_p90",
               "RAM_med", "RAM_p90",
               "GPU_Temp_p90"]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(RESULTS_DIR, f"konsolidiert_{ts}.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fn_csv, delimiter=";")
        w.writeheader()
        w.writerows(rows)
    print(f"\n  CSV: {csv_path}")
    return csv_path, ts


def _write_markdown(rows: List[Dict[str, Any]], args: Any,
                    ss_ctx: Dict[str, set[int]], ts: str) -> str:
    """Render the consolidated Markdown report and return its path.

    Formats all values into display strings (with CI brackets for
    DS1000/CoderEval), writes the header, the complete results table
    and the TOP/BOTTOM 5 and category rankings.
    """
    md_path = os.path.join(RESULTS_DIR, f"konsolidiert_{ts}.md")
    cols_md = ["Model", "DS1000", "CoderEval", "HumanEval+", "MBPP+",
               "ARC-Challenge", "HellaSwag", "TruthfulQA", "IFEval", "MATH-500",
               "Agentic",
               "Coding", "Knowledge", "Math", "Overall", "Runtime (min)",
               "Eff (Score/h)", "Coding Eff (Score/h)", "tok/s",
               "VRAM (GB)",
               "CPU_med", "CPU_p90",
               "GPU_med", "GPU_p90",
               "RAM_med", "RAM_p90",
               "GPU_Temp_p90"]

    def _fmt_pct(v: Any) -> str:
        """Format a value as "NN%" (fallback: original string)."""
        try:
            fv = float(v)
            return f"{fv:.0f}%"
        except (ValueError, TypeError):
            return str(v)

    def _fmt_num(v: Any) -> str:
        """Format a numeric value with one decimal (integer above 100)."""
        try:
            fv = float(v)
            if fv < 100:
                return f"{fv:.1f}"
            return f"{fv:.0f}"
        except (ValueError, TypeError):
            return str(v)

    str_rows = []
    for r in rows:
        vals = {"Model": r["Model"]}
        for c in cols_md[1:]:
            v = r.get(c, "")
            if c in ("DS1000", "CoderEval"):
                ci_lo = r.get(f"{c}_CI_lo", "")
                ci_hi = r.get(f"{c}_CI_hi", "")
                if v not in (None, "", "—") and ci_lo not in (None, "", "—") and ci_hi not in (None, "", "—"):
                    try:
                        sv = _fmt_pct(v)
                        clo = _fmt_pct(ci_lo)
                        chi = _fmt_pct(ci_hi)
                        vals[c] = f"{sv} [{clo}-{chi}]"
                    except Exception:
                        vals[c] = _fmt_pct(v)
                else:
                    vals[c] = _fmt_pct(v) if v not in (None, "", "—") else "—"
            elif v == "" or v is None:
                vals[c] = "—"
            elif c == "tok/s":
                vals[c] = f"{float(v):.0f}"
            elif c in ("Runtime (min)", "Eff (Score/h)", "Coding Eff (Score/h)", "VRAM (GB)"):
                vals[c] = _fmt_num(v)
            elif c in ("GPU_Temp_max", "GPU_Temp_p90"):
                vals[c] = f"{float(v):.0f}"
            else:
                vals[c] = _fmt_pct(v)
        str_rows.append(vals)

    str_rows.sort(key=lambda x: x["Model"])

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Consolidated Results – Dense Run (15+ Models)\n")
        if args.sample_size:
            ss_display = str(args.sample_size)
            ss_note = " (DS1000/CoderEval CSVs only)"
        else:
            ss_display = _describe_sample_sizes(ss_ctx)
            ss_note = ""
        f.write(f"\nAs of: {datetime.now().strftime('%Y-%m-%d %H:%M')}, SampleSize={ss_display}{ss_note}\n\n")
        f.write("** New Weighting Total Score: Coding 35%, Math 25%, Agentic & Instruction 25%, Knowledge 15% **\n")
        f.write("**Efficiency = Score / Runtime (in hours)** – Runtime based on measured DS1000+CoderEval latency.\n\n")

        # Complete results table (two-line header: Name + Unit)
        f.write("## Complete Results Table\n\n")

        header_names = ["Model", "DS1000", "CoderEv", "HEval+", "MBPP+",
                        "ARC", "HellaSw", "Truthf.", "IFEval", "M500",
                        "Agentic",
                        "Coding", "Knowl.", "Math", "Overall", "Runtime",
                        "Eff.", "Cod.Eff", "tok/s", "VRAM",
                        "CPUm", "CPUp",
                        "GPUm", "GPUp",
                        "RAMm", "RAMp", "Tp"]
        header_units = ["", "%", "%", "%", "%",
                        "%", "%", "%", "%", "%",
                        "%",
                        "%", "%", "%", "%", "min",
                        "%p/h", "%p/h", "tok/s", "GB",
                        "%", "%",
                        "%", "%",
                        "%", "%", "°C"]

        for line in _render_complete_table(str_rows, header_names, header_units, cols_md):
            f.write(line + "\n")

        f.write("\n---\n")
        f.write("\n**Weighting:**\n")
        f.write("- Coding (35%): HumanEval+ (25%), MBPP+ (25%), DS1000 (25%), CoderEval (25%)\n")
        f.write("- Math (25%): MATH-500 (100%)\n")
        f.write("- Agentic & Instruction (25%): Agentic (50%), IFEval (50%)\n")
        f.write("- Knowledge (15%): ARC-Challenge (1/3), HellaSwag (1/3), TruthfulQA (1/3)\n")
        f.write("- Efficiency = Score / Runtime (h). Values in %p/h.\n")
        f.write("- System metrics: a=arithmetic mean, m=median, d=maximum, p=90th percentile – for CPU/GPU/RAM. In the table: m (median) and p (90th percentile). Tp = GPU temperature P90.\n")

        # ── TOP 5 tables ──
        def _t5_named(title: str, sort_key: str, headers: List[str], keys: List[str], pct_flags: Optional[List[bool]] = None) -> None:
            """Write a TOP-5 Markdown table for the given sort key."""
            t5 = _top(rows, sort_key)
            _write_tbl(f, title, headers, t5, keys, pct_flags)

        def _threshold_filtered(rows: List[Dict[str, Any]], sort_key: str, threshold: float) -> List[Dict[str, Any]]:
            """Rows with sort_key >= threshold, sorted descending."""
            valid = [r for r in rows if r.get(sort_key) not in (None, "", "—")]
            sorted_rows = sorted(valid, key=lambda x: float(x.get(sort_key, 0)), reverse=True)
            return [r for r in sorted_rows if float(r.get(sort_key, 0)) >= threshold]

        def _b5_named(title: str, sort_key: str, headers: List[str], keys: List[str], pct_flags: Optional[List[bool]] = None) -> None:
            """Write a BOTTOM-5 Markdown table for the given sort key."""
            valid = [r for r in rows if r.get(sort_key) not in (None, "", "—")]
            if not valid:
                return
            b5 = sorted(valid, key=lambda x: float(x.get(sort_key, 0)), reverse=False)[:5]
            _write_tbl(f, title, headers, b5, keys, pct_flags)

        _t5_named("TOP 5 – Overall Score", "Overall",
            ["Model", "Overall", "Coding", "Knowledge", "Math", "Runtime", "Eff."],
            ["Overall", "Coding", "Knowledge", "Math", "Runtime (min)", "Eff (Score/h)"],
            [True, True, True, True, False, False])

        _b5_named("BOTTOM 5 – Overall Score", "Overall",
            ["Model", "Overall", "Coding", "Knowledge", "Math", "Runtime", "Eff."],
            ["Overall", "Coding", "Knowledge", "Math", "Runtime (min)", "Eff (Score/h)"],
            [True, True, True, True, False, False])

        _t5_named("TOP 5 – Efficiency (Overall / Runtime)", "Eff (Score/h)",
            ["Model", "Efficiency", "Overall", "Runtime"],
            ["Eff (Score/h)", "Overall", "Runtime (min)"],
            [False, True, False])

        top1 = max(rows, key=lambda x: float(x.get("Overall", 0) or 0))
        top1_name = top1["Model"] if top1 else ""
        f.write(f"\n=> Model **{top1_name}** wins the overall score and is 2nd best in efficiency (Overall/Runtime)!\n")

        f.write("\n---- \n")

        coding_top = _threshold_filtered(rows, "Coding", 60.0)
        coding_top_display = coding_top[:7]
        _write_tbl(f, f"TOP {len(coding_top_display)} – Coding (≥60%)",
            ["Model", "Coding", "DS1000", "CoderEval", "HEval+", "MBPP+", "Runtime", "Eff."],
            coding_top_display,
            ["Coding", "DS1000", "CoderEval", "HumanEval+", "MBPP+", "Runtime (min)", "Coding Eff (Score/h)"],
            [True, True, True, True, True, False, False])

        _t5_named("TOP 5 – Efficiency_Coding (Coding / Runtime)", "Coding Eff (Score/h)",
            ["Model", "Efficiency", "Coding", "Runtime"],
            ["Coding Eff (Score/h)", "Coding", "Runtime (min)"],
            [False, True, False])

        f.write("\nCoding winner *Qwen2.5 Coder 14B Instruct* is in the midfield in terms of runtime and efficiency, but not bad either.\n")
        f.write("Efficiency winner in coding is *Phi 4 (unsloth)*, more than three times faster than the coding winner and with a Coding score 10 percentage points lower.\n")

        f.write("\n----  \n")

        t5_math = _top(rows, "Math")
        _write_tbl(f, "TOP 5 – Math", ["Model", "Math", "MATH-500", "tok/s"],
                   t5_math, ["Math", "MATH-500", "tok/s"],
                   [True, True, False])

        t5_speed = _top(rows, "tok/s")
        _write_tbl(f, "TOP 5 – Speed (tok/s)", ["Model", "tok/s", "Overall"],
                   t5_speed, ["tok/s", "Overall"],
                   [False, True])

        t5_agentic = _top(rows, "Agentic")
        _write_tbl(f, "TOP 5 – Agentic & Instruction", ["Model", "Agentic", "IFEval", "HumanEval+", "MBPP+", "Coding"],
                   t5_agentic, ["Agentic", "IFEval", "HumanEval+", "MBPP+", "Coding"],
                   [True, True, True, True, True])
    return md_path


def main() -> None:
    """CLI entry point: consolidate benchmark results into CSV + Markdown.

    Supports --compare (paired bootstrap across models), model/sample-size
    filters, --since/--until windows, --all-runs/--merge and
    --no-installed. Writes konsolidiert_<timestamp>.csv/.md into
    RESULTS_DIR.
    """
    args = _parse_args()
    model_keys = [m.strip() for m in args.models.split(",")] if args.models else None
    exclude = [b.strip() for b in args.exclude_benchmarks.split(",")] if args.exclude_benchmarks else None
    if exclude:
        print(f"  Excluding benchmarks: {exclude}")

    # --compare mode: paired bootstrap analysis (2+ models, all pairwise)
    if args.compare:
        _run_comparison_mode(args)
        return

    rows, ss_ctx = _read_all_data(args, model_keys, exclude)
    csv_path, ts = _write_csv(rows)
    md_path = _write_markdown(rows, args, ss_ctx, ts)

    print(f"  MD:  {md_path}")
    print(f"\n{'=' * 60}")
    print(f"  Done – {len(rows)} Models")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
