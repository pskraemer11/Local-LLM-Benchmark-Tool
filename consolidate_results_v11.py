#!/usr/bin/env python3
"""Consolidate all benchmark results from a dense run into a single table.

── Rolle im Gesamtsystem ───────────────────────────────────────────
  Dieses Skript ist der letzte Schritt der Benchmark-Pipeline.
  Es liest die CSV-Dateien aus ergebnisse/ (geschrieben von
  csv_writer.py in run_benchmarks_v11.py) und verdichtet sie zu:

    1. Gesamt-Rangliste (CSV + MD) mit Score pro Benchmark
    2. Kategorie-Scores: Coding (35%), Math (25%), Agentic (25%), Knowledge (15%)
    3. Overall-Score (normalisiert)
    4. TOP/BOTTOM 5 und Kategorie-Rankings

── Bezug zu anderen Skripten ──────────────────────────────────────
  run_benchmarks_v11.py         -> schreibt modell_*.csv (pro Modell)
  custom_benchmark_v11.py       -> schreibt tasks_*.csv (pro Task)
  csv_writer.py                 -> einheitliches CSV-Schema
  consolidate_results_v11.py    -> LIEST diese CSVs

Computes weighted category scores + efficiency.
"""
from __future__ import annotations

import csv, json, os, sys, re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from statistics import mean, median
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE_DIR, "ergebnisse")

from benchmark_config import (DISPLAY_NAMES, WHITELIST, MMLU_PRO_SUBSETS,
                             LB_MEANS_BLACKLIST, CAT_WEIGHTS, OVERALL_WEIGHTS,
                             QUANT_MAP)

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
                    if mk:
                        sz_bytes = item.get("sizeBytes", 0) or 0
                        quant = item.get("quantization", {}) or {}
                        info[mk] = {
                            "vram_gb": round(sz_bytes / 1e9, 2),
                            "params": item.get("paramsString", "?"),
                            "quant": quant.get("name", "?") if isinstance(quant, dict) else str(quant),
                        }
    except Exception:
        pass
    _MODEL_INFO_CACHE = info
    return info


def _lookup_vram(display_name: str) -> Optional[Dict[str, Any]]:
    """Try to find VRAM + quant for a display name.

    Priority for quant: QUANT_MAP (static) > lms ls --json (dynamic)
    Priority for vram_gb: lms ls --json only (dynamic – deleted models have no file)
    """
    # Step 1: Find the model_key for this display_name
    model_key = None
    for dk, dn in DISPLAY_NAMES.items():
        if dn == display_name:
            model_key = dk
            break

    # Step 2: Get quant from QUANT_MAP (primary – works for deleted models too)
    quant_from_map = None
    if model_key and model_key in QUANT_MAP:
        quant_from_map = QUANT_MAP[model_key]

    # Step 3: Get VRAM + quant from lms ls --json (dynamic – only installed models)
    info = _get_model_info()
    lms_match = None
    for mk, meta in info.items():
        if display_name in mk or mk in display_name:
            lms_match = meta
            break
    if not lms_match and model_key:
        # Try direct key match
        if model_key in info:
            lms_match = info[model_key]
        else:
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

    # Step 4: Merge – QUANT_MAP wins for quant, lms wins for vram_gb
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

def _auto_delimiter(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        first = f.readline()
    if ";" in first:
        return ";"
    return ","

def read_custom_csv(path: str) -> Tuple[Optional[float], Optional[float], Optional[float], Dict[str, Any]]:
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


def find_latest_csvs() -> Tuple[Dict[str, str], Dict[str, str]]:
    """Find latest CSV files for DS1000 and CoderEval.
    
    Returns dicts keyed by model_key (from CSV content), not display name.
    This ensures unique entries for models with same name but different quants
    (e.g. qwen3-coder-reap-25b-a3b-i1@iq4_xs vs @q3_k_m).
    
    ACHTUNG: Der Lookup-Key ist das model_key-Feld aus dem CSV-Inhalt,
    NICHT der Dateiname. Bei Modellen mit gleichem Basis-Key aber
    unterschiedlicher Quant-Variante muessen die CSV-Dateien das
    korrekte model_key-Feld enthalten (wird von csv_writer.py gesetzt).
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
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    mk = row.get("model_key", "")
                    if mk:
                        model_key_from_csv = mk
                        break
        except Exception:
            pass
        
        # Use model_key if available, else fall back to display name from filename
        lookup_key = model_key_from_csv or model_name_from_file
        if lookup_key not in target or ts > target[lookup_key][0]:
            target[lookup_key] = (ts, fname)
    return {k: v[1] for k, v in ds1000.items()}, {k: v[1] for k, v in codereval.items()}


def try_read_evalplus(model_key: str) -> Optional[Dict[str, float]]:
    safe = model_key.replace("/", "_")
    root = os.path.join(RESULTS_DIR, f"evalplus_{safe}")
    if not os.path.isdir(root):
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
    """Berechnete gewichtete Kategorie-Scores und Overall.
    
    Normalisierung: Wenn eine Kategorie nur teilweise Daten hat (z.B. nur
    HumanEval+ aber kein MBPP+), werden die vorhandenen Benchmarks proportional
    hochskaliert (Gesamtgewicht = 1.0). Das verhindert, dass eine Kategorie
    mit nur einem Benchmark den gleichen Einfluss hat wie eine mit vier.
    
    Overall = summe(cat_weight * cat_score) / summe(cat_weight)
    fuer alle Kategorien mit Daten.
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
    codereval: Optional[float] = None
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
    laufzeit_min: Optional[str] = None
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
            "Modell": self.name,
            "DS1000": self.ds1000,
            "CoderEval": self.codereval,
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
            "Laufzeit (min)": self.laufzeit_min,
            "Eff (Score/h)": self.eff_score_h,
            "Coding Eff (Score/h)": self.coding_eff_score_h,
            "tok/s": self.tok_s,
            "VRAM (GB)": self.vram_gb,
            "Quant": self.quant,
            "CPU_med": self.cpu_med,
            "CPU_p90": self.cpu_p90,
            "GPU_med": self.gpu_med,
            "GPU_p90": self.gpu_p90,
            "RAM_med": self.ram_med,
            "RAM_p90": self.ram_p90,
            "GPU_Temp_p90": self.gpu_temp_p90,
        }


def read_data() -> List[Dict[str, Any]]:
    ds1000_files, codereval_files = find_latest_csvs()
    print(f"  DS1000 CSVs:  {len(ds1000_files)}")
    print(f"  CoderEval:    {len(codereval_files)}")

    rows = []
    for model_key in WHITELIST:
        display = DISPLAY_NAMES[model_key]
        bench_scores = {}
        tok_speeds = {}
        latencies = []

        # DS1000 – match by model_key
        for mk, fn in ds1000_files.items():
            if mk == model_key:
                ds_score, ds_tps, ds_lat, ds_m = read_custom_csv(os.path.join(RESULTS_DIR, fn))
                if ds_score is not None:
                    bench_scores["DS1000"] = ds_score
                    tok_speeds["DS1000"] = ds_tps
                    if ds_lat: latencies.append(ds_lat)
                break
        else:
            ds_score = ds_tps = None
            ds_m = {}

        # CoderEval – match by model_key
        for mk, fn in codereval_files.items():
            if mk == model_key:
                ce_score, ce_tps, ce_lat, ce_m = read_custom_csv(os.path.join(RESULTS_DIR, fn))
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
        lt_str = f"{rt_min:.1f} min" if rt_min else "—"
        print(f"    {'Laufzeit':20s} {lt_str}")
        eff_str = f"{cats['overall']/runtime_h:.1f}" if cats.get('overall') is not None and runtime_h else "—"
        print(f"    {'Eff (Score/h)':20s} {eff_str} %p/h")

        def pct(val: Optional[float]) -> Optional[float]:
            return round(val * 100, 2) if val is not None else None

        coding_eff = f"{cats['coding']/runtime_h:.1f}" if cats.get('coding') is not None and runtime_h else ""
        vram = _lookup_vram(display)
        rows.append(ModelData(
            name=display,
            ds1000=pct(ds_score),
            codereval=pct(ce_score),
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
            laufzeit_min=f"{rt_min:.1f}" if rt_min else "",
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
    return [r.to_csv_dict() for r in rows]


def main() -> None:
    print("=" * 60)
    print("  Konsolidierung Dense-Run Ergebnisse (v10)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    rows = read_data()

    # CSV
    fn_csv = ["Modell", "Quant", "DS1000", "CoderEval", "HumanEval+", "MBPP+",
              "ARC-Challenge", "HellaSwag", "TruthfulQA", "MMLU-Pro", "MathQA",
              "Agentic",
              "Coding", "Knowledge", "Math", "Overall", "Laufzeit (min)",
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
            vals = [str(i), r['Modell']]
            for key, pct_flag in zip(keys, pct_flags):
                vals.append(_val(key, r, pct=pct_flag))
            cells_data = [cell(v, j) for j, v in enumerate(vals)]
            f.write("| " + " | ".join(cells_data) + " |\n")

    # Markdown
    md_path = os.path.join(RESULTS_DIR, f"konsolidiert_{ts}.md")
    cols_md = ["Modell", "Quant", "DS1000", "CoderEval", "HumanEval+", "MBPP+",
               "ARC-Challenge", "HellaSwag", "TruthfulQA", "MMLU-Pro", "MathQA",
               "Agentic",
               "Coding", "Knowledge", "Math", "Overall", "Laufzeit (min)",
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
        vals = {"Modell": r["Modell"]}
        for c in cols_md[1:]:
            v = r.get(c, "")
            if v == "" or v is None:
                vals[c] = "—"
            elif c == "tok/s":
                vals[c] = f"{float(v):.0f}"
            elif c in ("Laufzeit (min)", "Eff (Score/h)", "Coding Eff (Score/h)", "VRAM (GB)", "Quant"):
                vals[c] = _fmt_num(v)
            elif c in ("GPU_Temp_max", "GPU_Temp_p90"):
                vals[c] = f"{float(v):.0f}"
            else:
                vals[c] = _fmt_pct(v)
        str_rows.append(vals)

    str_rows.sort(key=lambda x: x["Modell"])

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Konsolidierte Ergebnisse – Dense Run (15+ Modelle)\n")
        f.write(f"\nStand: {datetime.now().strftime('%Y-%m-%d %H:%M')}, SampleSize=8\n\n")
        f.write("** Neue Gewichtung Gesamt-Score: Coding 35%, Math 25%, Agentic 25%, Knowledge 15% **\n")
        f.write("**Effizienz = Score / Laufzeit (in Stunden)** – Laufzeit basiert auf gemessener DS1000+CoderEval-Latenz.\n\n")

        # Vollständige Ergebnistabelle (zweizeiliger Kopf: Name + Einheit)
        f.write("## Vollständige Ergebnistabelle\n\n")

        header_names = ["Modell", "Quant", "DS1000", "CoderEv", "HEval+", "MBPP+",
                        "ARC", "HellaSw", "Truthf.", "MMLU-Pro", "MathQA",
                        "Agentic",
                        "Coding", "Knowl.", "Math", "Overall", "Laufzeit",
                        "Eff.", "Cod.Eff", "tok/s", "VRAM",
                        "CPUm", "CPUp",
                        "GPUm", "GPUp",
                        "RAMm", "RAMp", "Tp"]
        header_units = ["", "", "%", "%", "%", "%",
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
            if c == "Modell":
                max_w = max(len(header_names[i]), len(header_units[i]))
                for sr in str_rows:
                    max_w = max(max_w, len(str(sr.get(c, ""))))
                widths2[c] = max_w
            else:
                widths2[c] = 6

        header_cells = []
        for i, c in enumerate(cols_md):
            txt = header_names[i]
            if c == "Modell":
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
                if c == "Modell":
                    parts.append(fitted.ljust(widths2[c]))
                else:
                    parts.append(fitted.rjust(widths2[c]))
            f.write("| " + " | ".join(parts) + " |\n")

        f.write("\n---\n")
        f.write("\n**Gewichtung:**\n")
        f.write("- Coding (35%): HumanEval+ (25%), MBPP+ (25%), DS1000 (25%), CoderEval (25%)\n")
        f.write("- Math (25%): MathQA (100%)\n")
        f.write("- Agentic (25%): Agentic (100%)\n")
        f.write("- Knowledge (15%): ARC-Challenge (25%), HellaSwag (25%), TruthfulQA (25%), MMLU-Pro (25%)\n")
        f.write("- Effizienz = Score / Laufzeit (h). Werte in %p/h.\n")
        f.write("- Systemmetriken: a=arithmetischer Mittelwert, m=Median, d=Maximum, p=90%-Perzentil – für CPU/GPU/RAM. In der Tabelle dargestellt: m (Median) und p (90%-Perzentil). Tp = GPU-Temperatur P90.\n")

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

        _t5_named("TOP 5 – Gesamtscore", "Overall",
            ["Modell", "Overall", "Coding", "Knowledge", "Math", "Laufzeit", "Effiz."],
            ["Overall", "Coding", "Knowledge", "Math", "Laufzeit (min)", "Eff (Score/h)"],
            [True, True, True, True, False, False])

        _b5_named("BOTTOM 5 – Gesamtscore", "Overall",
            ["Modell", "Overall", "Coding", "Knowledge", "Math", "Laufzeit", "Effiz."],
            ["Overall", "Coding", "Knowledge", "Math", "Laufzeit (min)", "Eff (Score/h)"],
            [True, True, True, True, False, False])

        _t5_named("TOP 5 – Effizienz (Gesamtscore / Laufzeit)", "Eff (Score/h)",
            ["Modell", "Effizienz", "Overall", "Laufzeit"],
            ["Eff (Score/h)", "Overall", "Laufzeit (min)"],
            [False, True, False])

        top1 = max(rows, key=lambda x: float(x.get("Overall", 0) or 0))
        top1_name = top1["Modell"] if top1 else ""
        f.write(f"\n=> Modell **{top1_name}** ist Sieger im Gesamtscore und 2.bester in der Effizienz (Gesamtscore/Laufzeit)!\n")

        f.write("\n---- \n")

        coding_top = _threshold_filtered(rows, "Coding", 60.0)
        coding_top_display = coding_top[:7]
        _write_tbl(f, f"TOP {len(coding_top_display)} – Coding (≥60%)",
            ["Modell", "Coding", "DS1000", "CoderEval", "HEval+", "MBPP+", "Laufzeit", "Effiz."],
            coding_top_display,
            ["Coding", "DS1000", "CoderEval", "HumanEval+", "MBPP+", "Laufzeit (min)", "Coding Eff (Score/h)"],
            [True, True, True, True, True, False, False])

        _t5_named("TOP 5 – Effizienz_Coding (Coding / Laufzeit)", "Coding Eff (Score/h)",
            ["Modell", "Effizienz", "Coding", "Laufzeit"],
            ["Coding Eff (Score/h)", "Coding", "Laufzeit (min)"],
            [False, True, False])

        f.write("\nCoding-Sieger *Qwen2.5 Coder 14B Instruct* ist bei der Laufzeit und Effizienz eher im Mittelfeld, aber auch nicht schlecht.\n")
        f.write("Effizienzsieger beim Coding ist *Phi 4 (unsloth)*, mehr als dreimal so schnell wie der Coding-Sieger und einem Coding-Score von 10%-Punkten weniger.\n")

        f.write("\n----  \n")

        t5_math = _top(rows, "Math")
        _write_tbl(f, "TOP 5 – Math", ["Modell", "Math", "MathQA", "tok/s"],
                   t5_math, ["Math", "MathQA", "tok/s"],
                   [True, True, False])

        t5_speed = _top(rows, "tok/s")
        _write_tbl(f, "TOP 5 – Geschwindigkeit (tok/s)", ["Modell", "tok/s", "Overall"],
                   t5_speed, ["tok/s", "Overall"],
                   [False, True])

        t5_agentic = _top(rows, "Agentic")
        _write_tbl(f, "TOP 5 – Agentic", ["Modell", "Agentic", "HumanEval+", "MBPP+", "Coding"],
                   t5_agentic, ["Agentic", "HumanEval+", "MBPP+", "Coding"],
                   [True, True, True, True])

    print(f"  MD:  {md_path}")
    print(f"\n{'=' * 60}")
    print(f"  Fertig – {len(rows)} Modelle")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
