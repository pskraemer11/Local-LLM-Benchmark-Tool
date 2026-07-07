#!/usr/bin/env python3
"""Consolidate all benchmark results from a dense run into a single table.

── Role in the Overall System ─────────────────────────────────────
  This script is the last step of the benchmark pipeline.
  It reads CSV files from ergebnisse/ (written by
  csv_writer.py in run_benchmarks_v12.py) and consolidates them into:

    1. Overall ranking (CSV + MD) with score per benchmark
    2. Category scores: Coding (35%), Math (25%), Agentic (25%), Knowledge (15%)
    3. Overall score (normalized)
    4. TOP/BOTTOM 5 and category rankings

── Relationship to Other Scripts ──────────────────────────────────
  run_benchmarks_v12.py         -> writes model_*.csv (per model)
  custom_benchmark_v12.py       -> writes tasks_*.csv (per task)
  csv_writer.py                 -> unified CSV schema
  consolidate_results_v12.py    -> READS these CSVs

Computes weighted category scores + efficiency.
"""
from __future__ import annotations

import csv, json, os, sys, re, random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from statistics import mean, median
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE_DIR, "ergebnisse")

from benchmark_config import (MMLU_PRO_SUBSETS, LB_MEANS_BLACKLIST,
                             CAT_WEIGHTS, OVERALL_WEIGHTS, QUANT_MAP)

# --- Model info cache (from lms ls --json) ---
_MODEL_INFO_CACHE = None

def _get_model_info() -> Dict[str, Any]:
    global _MODEL_INFO_CACHE
    if _MODEL_INFO_CACHE is not None:
        return _MODEL_INFO_CACHE
    info = {}
    try:
        import subprocess
        r = subprocess.run(["lms", "ls", "--json"], capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            data = json.loads(r.stdout)
            for item in data if isinstance(data, list) else data.values():
                if isinstance(item, dict):
                    mk = item.get("modelKey", "")
                    if not mk:
                        continue
                    sz_bytes = item.get("sizeBytes", 0) or 0
                    quant = item.get("quantization", {}) or {}
                    quant_name = quant.get("name", "?") if isinstance(quant, dict) else str(quant)
                    sv = item.get("selectedVariant") or ""
                    # Build unique key per variant
                    unique_key = sv if sv and sv != mk else f"{mk}@{quant_name}"
                    display = item.get("displayName", "")
                    info[unique_key] = {
                        "displayName": display,
                        "vram_gb": round(sz_bytes / 1e9, 2),
                        "params": item.get("paramsString", "?"),
                        "quant": quant_name,
                        "modelKey": mk,
                    }
    except Exception:
        pass
    _MODEL_INFO_CACHE = info
    return info


def _get_display_name(model_key: str) -> str:
    """Resolve model_key -> human-readable display name."""
    info = _get_model_info()
    if model_key in info:
        dn = info[model_key].get("displayName")
        if dn:
            return dn
    # Search by stored modelKey field (variant-aware)
    for mk, meta in info.items():
        if meta.get("modelKey") == model_key:
            dn = meta.get("displayName")
            if dn:
                return dn
    # Fuzzy: strip publisher prefix
    import re as _re
    mk_norm = _re.sub(r"^[a-z0-9_-]+/", "", model_key.lower())
    for mk, meta in info.items():
        mk_stripped = _re.sub(r"^[a-z0-9_-]+/", "", mk.lower())
        if mk_norm == mk_stripped:
            dn = meta.get("displayName")
            if dn:
                return dn
    # Fallback: prettify key
    return model_key.replace("/", " ").replace("_", " ").replace("-", " ").title()


def _lookup_vram(model_key: str) -> Optional[Dict[str, Any]]:
    """Try to find VRAM + quant for a model_key.

    Priority for quant: QUANT_MAP (static) > lms ls --json (dynamic)
    Priority for vram_gb: lms ls --json only (dynamic – deleted models have no file)
    """
    # Step 1: Get quant from QUANT_MAP (primary – works for deleted models too)
    quant_from_map = QUANT_MAP.get(model_key)

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
        # Fuzzy: strip publisher prefix, match normalized
        import re as _re
        dk_norm = _re.sub(r"[^a-z0-9]", "", model_key.lower())
        for mk in info:
            mk_base = _re.sub(r"@.*", "", mk)
            mk_base_norm = _re.sub(r"[^a-z0-9]", "", mk_base.lower())
            if dk_norm in mk_base_norm or mk_base_norm in dk_norm:
                lms_match = info[mk]
                break
            dk_short = _re.sub(r"(ibm|google|microsoft|mistralai|essentialai)/", "", dk_norm)
            if len(dk_short) > 5 and dk_short in mk_base_norm:
                lms_match = info[mk]
                break

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
    try:
        return float(v)
    except (ValueError, TypeError):
        return None

def _read_col(row: Dict[str, str], col: str) -> Optional[float]:
    v = row.get(col, "").strip()
    if v:
        fv = _try_float(v)
        if fv is not None:
            return fv
    return None

def _percentile(values: List[float], p: float) -> float:
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
    """
    if len(scores) < 2:
        return (float('nan'), float('nan'))
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
    """
    if len(scores_a) != len(scores_b) or len(scores_a) < 2:
        return (float('nan'), float('nan'), float('nan'))
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
    delim = _auto_delimiter(path)
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


def find_latest_csvs(min_sample_size: int = 0) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Find latest CSV files for DS1000 and CoderEval.
    
    Args:
        min_sample_size: If > 0, only include CSVs with sample_size >= this value.
    
    Returns dicts keyed by model_key (from CSV content), not display name.
    This ensures unique entries for models with same name but different quants
    (e.g. qwen3-coder-reap-25b-a3b-i1@iq4_xs vs @q3_k_m).
    
    NOTE: The lookup key is the model_key field from the CSV content,
    NOT the filename. For models with the same base key but different
    quant variant, the CSV files must contain the correct model_key
    field (set by csv_writer.py).
    """
    ds1000 = {}
    codereval = {}
    # Pattern: (optional tasks_) + YYYYMMDD_HHMMSS + DS1000|CoderEval + _ModelName.csv
    pat = re.compile(
        r"^(?:tasks_)?(\d{8}_\d{6})_(DS1000|CoderEval)_(.+)\.csv$"
    )
    for fname in os.listdir(RESULTS_DIR):
        m = pat.match(fname)
        if not m:
            continue
        ts = m.group(1)
        btype = m.group(2)
        model_name_from_file = m.group(3)
        target = ds1000 if btype == "DS1000" else codereval
        
        # Try to extract model_key from CSV content
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
                    break  # only need first row
        except Exception:
            pass
        
        if min_sample_size > 0 and file_sample_size < min_sample_size:
            continue
        
        # Use model_key if available, else fall back to display name from filename
        lookup_key = model_key_from_csv or model_name_from_file
        if lookup_key not in target or ts > target[lookup_key][0]:
            target[lookup_key] = (ts, fpath)
    return {k: v[1] for k, v in ds1000.items()}, {k: v[1] for k, v in codereval.items()}


def try_read_evalplus(model_key: str) -> Optional[Dict[str, float]]:
    safe = model_key.replace("/", "_")
    root = os.path.join(RESULTS_DIR, f"evalplus_{safe}")
    if not os.path.isdir(root):
        # Backward compat: try base key (without @ variant)
        base = model_key.split("@")[0].replace("/", "_")
        if base != safe:
            root = os.path.join(RESULTS_DIR, f"evalplus_{base}")
            if not os.path.isdir(root):
                return None
        else:
            return None
    results = {}
    for dataset in ["humaneval", "mbpp"]:
        dpath = os.path.join(root, dataset)
        eval_file = os.path.join(dpath, "local-model_openai_temp_0.0.eval_results.json")
        if not os.path.exists(eval_file):
            eval_file = os.path.join(dpath, "local-model_openai_temp_1.0.eval_results.json")
        if not os.path.exists(eval_file):
            continue
        try:
            with open(eval_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
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
            continue
        td = data.get("results", {}).get(task_name, {})
        for metric in metric_priority:
            if metric in td:
                return td[metric]
    return None

def read_lmeval_per_model(model_key: str) -> Optional[Dict[str, float]]:
    safe = model_key.replace("/", "_")
    root = os.path.join(RESULTS_DIR, f"lmeval_{safe}")
    if not os.path.isdir(root):
        base = model_key.split("@")[0].replace("/", "_")
        if base != safe:
            root = os.path.join(RESULTS_DIR, f"lmeval_{base}")
            if not os.path.isdir(root):
                return None
        else:
            return None
    results = {}

    METRICS = ["exact_match,custom-extract", "exact_match,remove_whitespace",
               "exact_match,flexible-extract", "bleu_acc,none", "rouge1_acc,none"]

    # Old-style: find the model results subdirectory (NOT an MMLU-Pro subset)
    first_sub = None
    for item in os.listdir(root):
        sub = os.path.join(root, item)
        if os.path.isdir(sub) and item not in MMLU_PRO_SUBSETS:
            first_sub = sub
            break
    if first_sub:
        for fname in os.listdir(first_sub):
            if not (fname.startswith("results_") and fname.endswith(".json")):
                continue
            try:
                with open(os.path.join(first_sub, fname), "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            for task_name, task_data in data.get("results", {}).items():
                for metric in METRICS:
                    if metric in task_data:
                        alias = {"arc_challenge_chat": "ARC-Challenge",
                                  "hellaswag_gen": "HellaSwag",
                                  "truthfulqa_gen": "TruthfulQA",
                                  "mmlu_pro": "MMLU-Pro",
                                  "bbh_zeroshot": "BBH",
                                  "mathqa_gen": "MathQA"}.get(task_name, task_name)
                        results[alias] = task_data[metric]
                        break

    # MMLU-Pro modified: 14 individual subset directories
    mmlu_scores = []
    for subset in MMLU_PRO_SUBSETS:
        subset_dir = os.path.join(root, subset)
        if not os.path.isdir(subset_dir):
            continue
        # Within subset dir, find the model's results subdirectory
        for item in os.listdir(subset_dir):
            sub = os.path.join(subset_dir, item)
            if os.path.isdir(sub):
                score = _read_results_json(sub, subset, METRICS)
                if score is not None:
                    mmlu_scores.append(score)
                    break
    if mmlu_scores:
        results["MMLU-Pro"] = sum(mmlu_scores) / len(mmlu_scores)

    return results if results else None


def read_agentic(model_key: str) -> Optional[float]:
    safe = model_key.replace("/", "_")
    root = os.path.join(RESULTS_DIR, f"agentic_{safe}")
    if not os.path.isdir(root):
        base = model_key.split("@")[0].replace("/", "_")
        if base != safe:
            root = os.path.join(RESULTS_DIR, f"agentic_{base}")
            if not os.path.isdir(root):
                return None
        else:
            return None
    # Recursively find all .json files
    all_json = []
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            if fname.endswith(".json"):
                all_json.append(os.path.join(dirpath, fname))
    if not all_json:
        return None
    # Pick the one with the highest timestamp in its name
    def _extract_ts(p: str) -> str:
        bn = os.path.basename(p).replace(".json", "")
        for part in bn.split("_"):
            if len(part) == 14 and part.isdigit():
                return part
        return bn  # fallback
    all_json.sort(key=_extract_ts, reverse=True)
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
        return None
    return None


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
    mathqa: Optional[float] = None
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
            "MMLU-Pro": self.mmlu_pro,
            "MathQA": self.mathqa,
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


def read_data(model_keys: Optional[List[str]] = None, min_sample_size: int = 0) -> List[Dict[str, Any]]:
    ds1000_files, codereval_files = find_latest_csvs(min_sample_size=min_sample_size)
    print(f"  DS1000 CSVs:  {len(ds1000_files)}")
    print(f"  CoderEval:    {len(codereval_files)}")

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

    rows = []
    for model_key in model_keys:
        display = _get_display_name(model_key) if not model_key.startswith("_dummy_") else model_key
        bench_scores = {}
        tok_speeds = {}
        latencies = []

        # DS1000 – match by model_key
        ds_scores: List[float] = []
        for mk, fn in ds1000_files.items():
            if mk == model_key:
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

        # CoderEval – match by model_key
        ce_scores: List[float] = []
        for mk, fn in codereval_files.items():
            if mk == model_key:
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

        # Runtime (hours) from DS1000+CoderEval latencies
        runtime_h = sum(latencies) / 3600 if latencies else None
        avg_tps = mean([v for v in tok_speeds.values() if v is not None]) if tok_speeds else None

        # Category scores
        cats = compute_category_scores(bench_scores)

        # Print per-model
        print(f"\n  {display}")
        for b in ["DS1000", "CoderEval", "HumanEval+_plus", "MBPP+_plus",
                   "ARC-Challenge", "HellaSwag", "TruthfulQA", "MathQA", "MMLU-Pro"]:
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
            mmlu_pro=pct(bench_scores.get('MMLU-Pro')),
            mathqa=pct(bench_scores.get('MathQA')),
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
    # Embed quantization in model name (uniquely identifies models)
    for r in rows:
        if r.quant:
            q = r.quant if not r.quant.startswith("@") else r.quant[1:]
            if q.lower() not in r.name.lower():
                r.name = f"{r.name}@{q}"
    return [r.to_csv_dict() for r in rows]


def main() -> None:
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
    args = parser.parse_args()

    model_keys = [m.strip() for m in args.models.split(",")] if args.models else None

    # --compare mode: paired bootstrap analysis (2+ models, all pairwise)
    if args.compare:
        parts = [p.strip() for p in args.compare.split(",")]
        if len(parts) < 2:
            print("[ERROR] --compare requires at least two comma-separated model keys")
            sys.exit(1)
        print("=" * 60)
        print("  Paired Quant Comparison (v12)")
        print(f"  Models: {', '.join(parts)}")
        print(f"  Seed: {args.seed}")
        print("=" * 60)
        ds1000_files, codereval_files = find_latest_csvs(min_sample_size=args.sample_size)
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
            for key_a, key_b in __import__('itertools').combinations(parts, 2):
                path_a = files_dict.get(key_a)
                path_b = files_dict.get(key_b)
                if not path_a or not path_b:
                    missing = key_a if not path_a else key_b
                    print(f"    [WARN] No CSV for {missing}, skipping {key_a} vs {key_b}")
                    continue
                scores_a, scores_b = read_paired_scores(path_a, path_b)
                if not scores_a:
                    print(f"    [WARN] No overlapping items for {key_a} vs {key_b}, skipping")
                    continue
                cmp = compare_two_quants(key_a, key_b, scores_a, scores_b, seed=args.seed)
                cmp["benchmark"] = bench_name
                cmp["key_a"] = key_a
                cmp["key_b"] = key_b
                results.append(cmp)
                sig = "***" if cmp["p_value"] < 0.001 else "**" if cmp["p_value"] < 0.01 else "*" if cmp["p_value"] < 0.05 else "n.s."
                print(f"    {key_a} vs {key_b}:  {cmp['mean_a']:.1f}% vs {cmp['mean_b']:.1f}%  "
                      f"Diff={cmp['mean_diff']:+.2f}% [{cmp['ci_lo']:+.2f}, {cmp['ci_hi']:+.2f}]  p={cmp['p_value']:.4f} {sig}")
        if results:
            print(f"\n{'=' * 60}")
            print("  Summary")
            print(f"{'=' * 60}")
            for r in results:
                sig = "***" if r["p_value"] < 0.001 else "**" if r["p_value"] < 0.01 else "*" if r["p_value"] < 0.05 else "n.s."
                winner = r.get("key_a", "") if r["sign"] == "+" else r.get("key_b", "") if r["sign"] == "-" else "neither"
                print(f"  {r['benchmark']} | {r.get('key_a','')} vs {r.get('key_b','')}: "
                      f"{winner} wins ({r['mean_diff']:+.2f}%, p={r['p_value']:.4f} {sig})")
        sys.exit(0)

    print("=" * 60)
    print("  Consolidating Dense-Run Results (v12)")
    print("  + Bootstrap 95% CI for DS1000 / CoderEval")
    ss_str = f" (min sample_size={args.sample_size})" if args.sample_size else ""
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}{ss_str}")
    print("=" * 60)

    rows = read_data(model_keys=model_keys, min_sample_size=args.sample_size)

    # CSV – build columns dynamically
    fn_csv = ["Model"]
    fn_csv += ["DS1000", "DS1000_CI_lo", "DS1000_CI_hi"]
    fn_csv += ["CoderEval", "CoderEval_CI_lo", "CoderEval_CI_hi"]
    fn_csv += ["HumanEval+", "MBPP+",
               "ARC-Challenge", "HellaSwag", "TruthfulQA", "MMLU-Pro", "MathQA",
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

    # ── helpers ──
    def _val(key: str, r: Dict[str, Any], pct: bool = True) -> str:
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
        valid = [r for r in rows if r.get(sort_key) not in (None, "", "—")]
        if not valid:
            return []
        return sorted(valid, key=lambda x: float(x.get(sort_key, 0)), reverse=True)[:5]

    def _write_tbl(f: Any, title: str, headers: List[str], sorted_rows: List[Dict[str, Any]], keys: List[str], pct_flags: Optional[List[bool]] = None) -> None:
        if not sorted_rows:
            return
        if pct_flags is None:
            pct_flags = [True] * len(keys)
        f.write(f"\n### {title}\n")
        all_h = ["Rang"] + headers
        ws = []
        for h in all_h:
            if h == "Rang":
                ws.append(5)
            elif h == headers[0]:
                ws.append(max(29, len(h)))
            else:
                ws.append(max(8, len(h)))
        def cell(txt: str, i: int) -> str:
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
        for i, r in enumerate(sorted_rows, 1):
            vals = [str(i), r['Model']]
            for key, pct_flag in zip(keys, pct_flags):
                vals.append(_val(key, r, pct=pct_flag))
            cells_data = [cell(v, j) for j, v in enumerate(vals)]
            f.write("| " + " | ".join(cells_data) + " |\n")

    # Markdown
    md_path = os.path.join(RESULTS_DIR, f"konsolidiert_{ts}.md")
    cols_md = ["Model", "DS1000", "CoderEval", "HumanEval+", "MBPP+",
               "ARC-Challenge", "HellaSwag", "TruthfulQA", "MMLU-Pro", "MathQA",
               "Agentic",
               "Coding", "Knowledge", "Math", "Overall", "Runtime (min)",
               "Eff (Score/h)", "Coding Eff (Score/h)", "tok/s",
               "VRAM (GB)",
              "CPU_med", "CPU_p90",
              "GPU_med", "GPU_p90",
              "RAM_med", "RAM_p90",
              "GPU_Temp_p90"]

    def _fmt_pct(v: Any) -> str:
        try:
            fv = float(v)
            return f"{fv:.0f}%"
        except (ValueError, TypeError):
            return str(v)

    def _fmt_num(v: Any) -> str:
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
        f.write(f"\nAs of: {datetime.now().strftime('%Y-%m-%d %H:%M')}, SampleSize=20\n\n")
        f.write("** New Weighting Total Score: Coding 35%, Math 25%, Agentic 25%, Knowledge 15% **\n")
        f.write("**Efficiency = Score / Runtime (in hours)** – Runtime based on measured DS1000+CoderEval latency.\n\n")

        # Complete results table (two-line header: Name + Unit)
        f.write("## Complete Results Table\n\n")

        header_names = ["Model", "DS1000", "CoderEv", "HEval+", "MBPP+",
                        "ARC", "HellaSw", "Truthf.", "MMLU-Pro", "MathQA",
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

        def _fit(val: Any, width: int) -> str:
            s = str(val)
            if len(s) <= width:
                return s
            if width < 3:
                return s[:width]
            return s[:width-1] + "…"

        widths2 = {}
        for i, c in enumerate(cols_md):
            if c == "Model":
                max_w = max(len(header_names[i]), len(header_units[i]))
                for sr in str_rows:
                    max_w = max(max_w, len(str(sr.get(c, ""))))
                widths2[c] = max_w
            elif c in ("DS1000", "CoderEval"):
                max_w = max(len(header_names[i]), len(header_units[i]))
                for sr in str_rows:
                    max_w = max(max_w, len(str(sr.get(c, ""))))
                widths2[c] = max_w
            else:
                widths2[c] = 6

        header_cells = []
        for i, c in enumerate(cols_md):
            txt = header_names[i]
            if c == "Model":
                L = len(txt.ljust(widths2[c]))
                header_cells.append(" " + txt.ljust(widths2[c]) + " ")
            else:
                L = len(txt)
                if L <= 6:
                    header_cells.append(" " + txt.rjust(6) + " ")
                elif L == 7:
                    header_cells.append(" " + txt)
                elif L == 8:
                    header_cells.append(txt)
                else:
                    header_cells.append(" " + _fit(txt, 6).rjust(6) + " ")
        f.write("|" + "|".join(header_cells) + "|\n")

        parts = []
        for i, c in enumerate(cols_md):
            txt = header_units[i]
            parts.append(" " * widths2[c] if not txt else txt.rjust(widths2[c]))
        f.write("| " + " | ".join(parts) + " |\n")

        parts = []
        for i, c in enumerate(cols_md):
            parts.append("-" * widths2[c])
        f.write("| " + " | ".join(parts) + " |\n")

        for sr in str_rows:
            parts = []
            for c in cols_md:
                val = str(sr.get(c, ""))
                fitted = _fit(val, widths2[c])
                if c == "Model":
                    parts.append(fitted.ljust(widths2[c]))
                else:
                    parts.append(fitted.rjust(widths2[c]))
            f.write("| " + " | ".join(parts) + " |\n")

        f.write("\n---\n")
        f.write("\n**Weighting:**\n")
        f.write("- Coding (35%): HumanEval+ (25%), MBPP+ (25%), DS1000 (25%), CoderEval (25%)\n")
        f.write("- Math (25%): MathQA (100%)\n")
        f.write("- Agentic (25%): Agentic (100%)\n")
        f.write("- Knowledge (15%): ARC-Challenge (25%), HellaSwag (25%), TruthfulQA (25%), MMLU-Pro (25%)\n")
        f.write("- Efficiency = Score / Runtime (h). Values in %p/h.\n")
        f.write("- System metrics: a=arithmetic mean, m=median, d=maximum, p=90th percentile – for CPU/GPU/RAM. In the table: m (median) and p (90th percentile). Tp = GPU temperature P90.\n")

        # ── TOP 5 tables ──
        def _t5_named(title: str, sort_key: str, headers: List[str], keys: List[str], pct_flags: Optional[List[bool]] = None) -> None:
            t5 = _top(rows, sort_key)
            _write_tbl(f, title, headers, t5, keys, pct_flags)

        def _threshold_filtered(rows: List[Dict[str, Any]], sort_key: str, threshold: float) -> List[Dict[str, Any]]:
            valid = [r for r in rows if r.get(sort_key) not in (None, "", "—")]
            sorted_rows = sorted(valid, key=lambda x: float(x.get(sort_key, 0)), reverse=True)
            return [r for r in sorted_rows if float(r.get(sort_key, 0)) >= threshold]

        def _b5_named(title: str, sort_key: str, headers: List[str], keys: List[str], pct_flags: Optional[List[bool]] = None) -> None:
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
        _write_tbl(f, "TOP 5 – Math", ["Model", "Math", "MathQA", "tok/s"],
                   t5_math, ["Math", "MathQA", "tok/s"],
                   [True, True, False])

        t5_speed = _top(rows, "tok/s")
        _write_tbl(f, "TOP 5 – Speed (tok/s)", ["Model", "tok/s", "Overall"],
                   t5_speed, ["tok/s", "Overall"],
                   [False, True])

        t5_agentic = _top(rows, "Agentic")
        _write_tbl(f, "TOP 5 – Agentic", ["Model", "Agentic", "HumanEval+", "MBPP+", "Coding"],
                   t5_agentic, ["Agentic", "HumanEval+", "MBPP+", "Coding"],
                   [True, True, True, True])

    print(f"  MD:  {md_path}")
    print(f"\n{'=' * 60}")
    print(f"  Done – {len(rows)} Models")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
