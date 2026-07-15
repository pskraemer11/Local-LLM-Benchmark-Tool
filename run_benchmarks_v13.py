#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified benchmark launcher v13 – integrates:
  [1] Custom: DS1000, CoderEval (custom_benchmark_v13.py)
  [2] EvalPlus: HumanEval+, MBPP+ (evalplus.codegen + evalplus.evaluate)
  [3] LM-Eval: ARC, HellaSwag, TruthfulQA, IFEval, MATH-500 (lm_eval)
  [4] Agentic: tool-eval-bench (SampleSize scenarios, random selection)

── Four-Pipeline Architecture ──────────────────────────────────────
  This script is the CENTRAL ENTRY POINT. It orchestrates all
  four evaluation pipelines as subprocesses. ONLY HERE is model
  management (load/unload) initiated – the subprocesses must
  NOT load/unload themselves.

  Pipeline         Script/Tool                Data Source
  ────────         ───────────                ───────────
  Custom           custom_benchmark_v13.py    JSONL under simple_evals/
  EvalPlus         evalplus.codegen/evaluate  evalplus-native datasets
  LM-Eval          lm_eval CLI                lm-eval built-in + custom YAML
  Agentic          tool_eval_bench (<-m)      HuggingFace tool_eval_bench

  All results are output via csv_writer.py with a uniform schema
  (; delimiter, UTF-8) and consolidated by consolidate_results_v13.py
  into rankings.

── Script Hierarchy ────────────────────────────────────────────────
  run_benchmarks_v13.py  (Launcher, ONLY HERE load/unload)
    ├── model_manager.py         (load/unload/check via lms CLI)
    ├── custom_benchmark_v13.py (subprocess: DS1000, CoderEval)
    ├── csv_writer.py            (uniform CSV output)
    ├── evalplus (external library, via -m)
    ├── lm_eval   (external library, via -m)
    └── tool_eval_bench (external library, via -m)

Changes from v12 (@2026-07-11):
  - DISPLAY_NAMES + WHITELIST removed (auto-discovery via result CSVs)
  - EXCLUDE_KEYWORDS + MMLU_PRO_SUBSETS centralized in benchmark_config.py

Features:
  - Interactive selection or CLI-controlled (--model, --benchmarks)
  - --sample-size N for all pipelines
  - PYTHONIOENCODING=utf-8 for ALL subprocesses (Unicode arrows)
  - Intermediate summary per model
  - Qwen3.5 system message in user prompt
  - Reasoning timeout ×2 for reasoning models
  - MoE detection
"""

from __future__ import annotations

import argparse
import csv_writer as csv_writer
import glob
import json
import math
import os
import random
import re
import subprocess
import sys
import time
import warnings
from datetime import datetime
from typing import Any, Optional

# ── Model Management from Shared Module ──────────────────────
# Load/Unload is ONLY initiated in main() of this script.
# The subprocesses (custom_benchmark_v13.py, evalplus, lm_eval, tool_eval_bench)
# must NOT load/unload themselves – they receive the model ID
# via model_info["_api_model"] and only call the API.
#
# API reference (LM Studio REST / OpenAI-Compat):
#   https://lmstudio.ai/docs/developer/rest
#
# Important endpoints:
#   /api/v1/models              GET  – native: model list
#   /api/v1/models/load         POST – native: load model (streamed events)
#   /api/v1/models/unload       POST – native: unload model
#   /api/v1/chat                POST – native: chat inference
#   /v1/chat/completions        POST – OpenAI-Compat: chat inference
#   /v1/models                  GET  – OpenAI-Compat: model list
#
from benchmark_config import (PIPELINE_DISCOVERY, TOOL_EVAL_SCENARIO_IDS,
                             EXCLUDE_KEYWORDS, MMLU_PRO_SUBSETS, MMLU_PRO_ENABLED)
from model_manager import (
    API_BASE, TIMEOUT_CLI, TIMEOUT_MODEL_READY, PIPELINE_TIMEOUTS,
    get_current_loaded_model, unload_all_models,
    load_model_via_lms, get_available_models, parse_selection,
    wait_for_model_ready
)

# Model classification helper functions
REASONING_KEYWORDS = ["reasoning", "think", "r1", "rnj"]

def _is_qwen3_6_model(model_key: str) -> bool:
    return "qwen3.6" in model_key.lower()
MOE_PATTERN = re.compile(r"\d+b-a\d+b", re.IGNORECASE)  # e.g., "8b-a1b", "24b-a2b"

def _is_reasoning_model(model_key: str) -> bool:
    kl = model_key.lower()
    return any(kw in kl for kw in REASONING_KEYWORDS)

def _is_moe_model(model_key: str) -> bool:
    return bool(MOE_PATTERN.search(model_key))

def _is_qwen3_5_model(model_key: str) -> bool:
    return "qwen3.5" in model_key.lower() or "qwopus3" in model_key.lower()

def _is_gptoss_model(model_key: str) -> bool:
    return "gpt-oss" in model_key.lower()

def _is_gemma_model(model_key: str) -> bool:
    return "gemma" in model_key.lower()

def _model_short_name(model_key: str) -> str:
    """Generates a short filename-compatible model name."""
    s = model_key.replace("/", "_").replace("\\", "_").replace(" ", "_")
    for sep in ("/", "\\"):
        if sep in s:
            s = s.rsplit(sep, 1)[-1]
    return s[:30]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE_DIR, "ergebnisse")
DATA_DIR = os.path.join(BASE_DIR, "simple_evals")
os.makedirs(RESULTS_DIR, exist_ok=True)

# Global: ensure all subprocesses inherit UTF-8 encoding (Windows cp1252 workaround)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
# Also reconfigure this process's stdout so print() doesn't choke on Unicode arrows/symbols
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

LMEVAL_TASKS_DIR = os.path.join(BASE_DIR, "lm_eval_tasks")

# ── Versioned Script References (dynamic) ──────────────────
# Automatically finds the highest version of custom_benchmark_v*.py.
# No manual update after Copy-Item needed anymore.
# Prio 3.12 (Code-Review_2026-07-12.md §3.1 D1): log the resolved path
# so it's clear which script version is actually being used.
_custom_scripts = glob.glob(os.path.join(BASE_DIR, "custom_benchmark_v*.py"))
_versions = []
for _s in _custom_scripts:
    _m = re.search(r'_v(\d+)\.py$', _s)
    if _m:
        _versions.append((int(_m.group(1)), _s))
if not _versions:
    sys.exit("[FATAL] No custom_benchmark_v*.py found.")
CUSTOM_BENCHMARK_SCRIPT = max(_versions, key=lambda x: x[0])[1]
print(f"[INFO] Using custom_benchmark script: {os.path.basename(CUSTOM_BENCHMARK_SCRIPT)} "
      f"(version v{max(_versions, key=lambda x: x[0])[0]})")
print(f"[INFO] Subprocess interpreter: {sys.executable}")
print(f"[INFO] Repository root:        {BASE_DIR}")
del _custom_scripts, _versions, _m, _s

# ── Benchmark Definitions ──────────────────────────────────────
# Each benchmark is assigned to exactly ONE pipeline:
#   Pipeline "custom"   ->  subprocess CUSTOM_BENCHMARK_SCRIPT
#   Pipeline "evalplus"  ->  evalplus.codegen + evalplus.evaluate
#   Pipeline "lmeval"    ->  lm_eval --model local-chat-completions
#   Pipeline "agentic"   ->  tool_eval_bench (tool evaluation)
#
# The distinction is made in main() via name comparisons:
#   - MMLU-Pro (modified=True) -> run_mmlupro_modified()
#   - bname in agentic_names  -> run_agentic()
#   - bname in ep_names       -> run_evalplus()
#   - bname in lmeval_names   -> run_lmeval()
#   - otherwise (is_custom)   -> run_custom_benchmark()
# Classification: coding / math / knowledge / agentic
# Mirrors CAT_WEIGHTS in benchmark_config.py (updated 2026-07-11)
CUSTOM_BENCHMARKS = [
    {"key": "1", "name": "DS1000",         "category": "coding",    "file": "data_science.jsonl"},
    {"key": "2", "name": "CoderEval",       "category": "coding",    "file": "codereval_selfcontained.jsonl"},
]
EVALPLUS_BENCHMARKS = [
    {"key": "3", "name": "HumanEval+",      "category": "coding",    "dataset": "humaneval"},
    {"key": "4", "name": "MBPP+",           "category": "coding",    "dataset": "mbpp"},
]
LMEVAL_BENCHMARKS = [
    {"key": "5", "name": "ARC-Challenge",   "category": "knowledge", "task": "arc_challenge_chat"},
    {"key": "6", "name": "HellaSwag",       "category": "knowledge", "task": "hellaswag_gen", "min_limit": 100},
    {"key": "7", "name": "TruthfulQA",      "category": "knowledge", "task": "truthfulqa_gen"},
    {"key": "8", "name": "IFEval",          "category": "agentic",   "task": "ifeval"},
    {"key": "9", "name": "MATH-500",        "category": "math",      "task": "minerva_math500", "timeout_mult": 3},
]

# MMLU-Pro 14 Subsets (lm_eval individual tasks) – removed in v13: too expensive
# Agentic: tool-eval-bench mit 69 Szenarien
# (TOOL_EVAL_SCENARIO_IDS in benchmark_config.py)
AGENTIC_BENCHMARKS = [
    {"key": "10", "name": "Agentic", "category": "agentic", "pipeline": "agentic"},
]

ALL_BENCHMARKS = CUSTOM_BENCHMARKS + EVALPLUS_BENCHMARKS + LMEVAL_BENCHMARKS + AGENTIC_BENCHMARKS
BENCH_LOOKUP = {b["name"].lower(): b for b in ALL_BENCHMARKS}
ALL_BENCH_NAMES = sorted(BENCH_LOOKUP.keys())


# Fallback hardcoded context lengths (used only when registry has no entry).
SAFE_CONTEXT_FALLBACK: dict[str, int] = {
    "kimi-linear-48b-a3b-instruct": 131072,  # 1M native → extreme VRAM
    "kimi-linear-reap-35b-a3b-instruct-i1": 131072,
    "north-mini-code-1.0": 131072,     # 256K native → KV-quant inkompatibel
    "ministral-3-14b-instruct-2512": 65536,
}

# Cached registry data
_REGISTRY_DATA: Optional[dict] = None
_REGISTRY_NORM: Optional[dict[str, str]] = None

def _load_registry_for_context() -> tuple[dict, dict[str, str]]:
    global _REGISTRY_DATA, _REGISTRY_NORM
    if _REGISTRY_DATA is not None:
        return _REGISTRY_DATA, _REGISTRY_NORM

    from assemble_blueprint import normalize_model_name
    from pathlib import Path

    rpath = Path(__file__).resolve().parent / "doc-git" / "model_registry.yaml"
    if not rpath.exists():
        _REGISTRY_DATA = {}
        _REGISTRY_NORM = {}
        return _REGISTRY_DATA, _REGISTRY_NORM

    try:
        from ruamel.yaml import YAML
        y = YAML()
        y.preserve_quotes = True
        with open(rpath, "r", encoding="utf-8") as f:
            data = y.load(f) or {}
    except Exception:
        _REGISTRY_DATA = {}
        _REGISTRY_NORM = {}
        return _REGISTRY_DATA, _REGISTRY_NORM

    norm = {}
    for key, entry in data.items():
        if isinstance(entry, dict) and "context_length" in entry:
            nk = normalize_model_name(key)
            norm[nk] = key
    _REGISTRY_DATA = data
    _REGISTRY_NORM = norm
    return _REGISTRY_DATA, _REGISTRY_NORM


def _get_safe_context(model_key: str) -> Optional[int]:
    """Return capped context length for VRAM-safe model loading.

    Priority:
      1. model_registry.yaml entry matching via normalized name
      2. SAFE_CONTEXT_FALLBACK hardcoded dict
    """
    from assemble_blueprint import normalize_model_name

    # 1. Try registry
    registry, rnorm = _load_registry_for_context()
    nk = normalize_model_name(model_key)
    if nk in rnorm:
        entry = registry[rnorm[nk]]
        ctx = entry.get("context_length")
        if ctx is not None:
            return int(ctx)

    # 2. Try fallback (exact normalized match)
    for pattern, ctx in SAFE_CONTEXT_FALLBACK.items():
        if normalize_model_name(pattern) == nk:
            return ctx

    # 3. Try substring fallback matching (for patterns that are prefixes)
    for pattern, ctx in SAFE_CONTEXT_FALLBACK.items():
        if pattern in model_key.lower():
            return ctx

    return None

def _model_family(model_key: str) -> str:
    """Extract model family (without publisher prefix) for deduplication."""
    return model_key.replace("\\", "/").split("/")[-1].lower()

def resolve_models(available_models: list[dict[str, Any]], model_arg: Optional[str]) -> Optional[list[dict[str, Any]]]:
    filtered = [m for m in available_models
                if not any(kw in m["key"].lower() for kw in EXCLUDE_KEYWORDS)]
    if not filtered:
        print("\n[WARN] No models found.")
        return None

    if not model_arg or model_arg == "all":
        return filtered

    # Try number or range (handles comma-separated numbers like "1,3,5-8")
    indices = parse_selection(model_arg, len(filtered))
    if indices is not None:
        return [filtered[i] for i in indices]

    # Comma-separated model names/keys
    parts = [p.strip() for p in model_arg.split(",") if p.strip()]
    if len(parts) > 1:
        result = []
        seen = set()
        for part in parts:
            sub = resolve_models(available_models, part)
            if sub:
                for m in sub:
                    if m["key"] not in seen:
                        result.append(m)
                        seen.add(m["key"])
            else:
                print(f"  [WARN] Could not resolve model '{part}', skipping")
        if result:
            return result
        print("[ERROR] No models could be resolved from comma-separated list")
        print("  Available: " + ", ".join(f"{m['display']}" for m in filtered))
        return None

    # Single model: try exact match first (prevent substring collision)
    model_arg_lower = model_arg.lower()
    exact = [m for m in filtered if m["key"].lower() == model_arg_lower
             or m["display"].lower() == model_arg_lower]
    if exact:
        return exact

    # Fallback to keyword match
    matches = [m for m in filtered if model_arg_lower in m["key"].lower()
               or model_arg_lower in m["display"].lower()]
    if matches:
        return matches

    print(f"[ERROR] No model found for '{model_arg}'")
    print("  Available: " + ", ".join(f"{m['display']}" for m in filtered))
    return None


def resolve_benchmarks(bench_arg: Optional[str]) -> Optional[list[dict[str, Any]]]:
    if not bench_arg or bench_arg == "all":
        return ALL_BENCHMARKS

    # Try numbers
    indices = parse_selection(bench_arg, len(ALL_BENCHMARKS))
    if indices is not None:
        return [ALL_BENCHMARKS[i] for i in indices]

    # Try comma-separated names
    names = [n.strip().lower() for n in bench_arg.split(",")]
    result = []
    for n in names:
        if n in BENCH_LOOKUP:
            result.append(BENCH_LOOKUP[n])
        else:
            print(f"[ERROR] Unknown benchmark '{n}'. Possible: {', '.join(ALL_BENCH_NAMES)}")
            return None
    return result


def select_models_interactive(available_models: list[dict[str, Any]]) -> Optional[list[dict[str, Any]]]:
    filtered = [m for m in available_models
                if not any(kw in m["key"].lower() for kw in EXCLUDE_KEYWORDS)]
    if not filtered:
        print("\n[WARN] No models found.")
        return None

    # Stable, deterministic ordering for the menu: alphabetic by display label.
    filtered.sort(key=lambda m: str(m.get("display") or m.get("key") or "").lower())
    print("\n" + "-" * 50)
    print("  Available models:")
    for i, m in enumerate(filtered, 1):
        print(f"  [{i}] {m['display']}")
    print("  [a] All models")
    while True:
        choice = input("  Your choice: ").strip().lower()
        if choice == "a":
            return filtered
        indices = parse_selection(choice, len(filtered))
        if indices is not None:
            return [filtered[i] for i in indices]
        print("  Invalid input.")


def select_benchmarks_interactive() -> Optional[list[dict[str, Any]]]:
    print("\n" + "=" * 60)
    print("  Benchmark Selection")
    print("=" * 60)
    cat_order = ["coding", "math", "knowledge", "agentic"]
    cat_heading = {"coding": "CODING", "math": "MATH", "knowledge": "KNOWLEDGE", "agentic": "AGENTIC & INSTRUCTION"}
    # Display contiguous benchmark numbers (1..N) without gaps.
    displayed: list[dict[str, Any]] = []
    for cat in cat_order:
        print(f"  --- {cat_heading.get(cat, cat.upper())} ---")
        for b in ALL_BENCHMARKS:
            if b.get("category") != cat:
                continue
            displayed.append(b)
            idx = len(displayed)

            label = b["name"]
            if b.get("modified"):
                label += " (mod.)"
            if b.get("pipeline") == "agentic":
                label += " (tool-eval-bench)"
            if b.get("task") == "ifeval":
                label += " (lm-eval)"
            print(f"  [{idx}] {label}")
    print("  [a] All benchmarks")
    print("  [q] Quit")

    while True:
        choice = input("\n  Your choice: ").strip().lower()
        if choice == "q":
            print("\nBye.")
            return None
        if choice == "a":
            return displayed

        indices = parse_selection(choice, len(displayed))
        if indices is not None:
            result = [displayed[i] for i in indices]
            names = ", ".join(b["name"] for b in result)
            print(f"  -> {names}")
            return result
        print("  Invalid input.")


# Global: Thinking mode for MATH-500 (reasoning models)
THINKING_ENABLED = False

def _get_lmeval_params(model_key: str, bench_name: str = "") -> dict[str, Any]:
    """Returns LM-Eval parameters for the given model class.
    
    NOTE: The parameters must match the behavior in custom_benchmark_v13.py
    (MODEL_CONFIG). Especially important:
      - Qwen3.6: enable_thinking=False AND max_tokens=8192 (both needed!)
      - GPT-OSS: temperature=1.0, until=["<|return|>","<|call|>"], top_k=0
      - Reasoning: min_p=0.02, timeout x2
      - Thinking mode for MATH-500 via --thinking (all reasoning models)
    
    Returned keys are split by the caller into --model_args (constructor) and
    --gen_kwargs (generation kwargs). See run_lmeval() for the split logic.
    """
    gptoss = _is_gptoss_model(model_key)
    if gptoss:
        return {"max_tokens": 4096, "temperature": 1.0, "top_p": 1.0, "top_k": 0,
                "until": ["<|return|>", "<|call|>"],
                "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
    if _is_qwen3_6_model(model_key):
        return {"max_tokens": 8192, "temperature": 0.0, "top_p": 1.0, "until": [],
                "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
    if _is_qwen3_5_model(model_key):
        return {"temperature": 0.2, "top_p": 0.9, "top_k": 20,
                "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
    if _is_gemma_model(model_key):
        base = {"max_tokens": 4096, "temperature": 0.0, "top_p": 1.0, "until": [],
                "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
        if THINKING_ENABLED and bench_name == "MATH-500":
            return {**base, "max_tokens": 8192,
                    "extra_body": {"chat_template_kwargs": {"enable_thinking": True}}}
        return base
    if _is_reasoning_model(model_key):
        base = {"temperature": 0.1, "top_p": 0.9, "min_p": 0.02,
                "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
        if THINKING_ENABLED and bench_name == "MATH-500":
            return {**base, "max_tokens": 8192, "until": [],
                    "extra_body": {"chat_template_kwargs": {"enable_thinking": True}}}
        return base
    return {"max_tokens": 1024, "temperature": 0.0, "top_p": 1.0,
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}


def _build_lmeval_cmd(model_key: str, api_model: str, subset_task: str, per_limit: int, output_dir: str, bench_name: str = "") -> list[str]:
    """Like run_lmeval(), but returns the cmd list instead of executing it.
    
    Used by run_agentic() for per-scenario lm_eval invocations.
    Mirrors the same --model_args / --gen_kwargs split as run_lmeval().
    """
    gptoss = _is_gptoss_model(model_key)
    lmeval_params = _get_lmeval_params(model_key, bench_name=bench_name)
    model_args_dict = {
        "base_url": f"{API_BASE}/chat/completions",
        "model": api_model,
        "num_concurrent": 1,
        "max_gen_toks": 512,   # fallback if YAML gen_kwargs has no max_gen_toks
    }
    # eos_string only for GPT-OSS; other models use YAML until sequences or gen_kwargs
    if gptoss and "until" not in lmeval_params:
        model_args_dict["eos_string"] = "<|endoftext|>"
    # Generation params go to --gen_kwargs (overrides YAML gen_kwargs via merge)
    gen_kwargs_keys = {"max_tokens", "temperature", "top_p", "top_k", "min_p",
                       "until", "extra_body"}
    gen_kwargs = {k: v for k, v in lmeval_params.items()
                  if k in gen_kwargs_keys and v is not None}
    model_args = json.dumps(model_args_dict, ensure_ascii=False)
    cmd = [
        sys.executable, "-m", "lm_eval",
        "--model", "local-chat-completions",
        "--model_args", model_args,
        "--tasks", subset_task,
        "--limit", str(per_limit),
        "--output_path", output_dir,
        "--apply_chat_template",
        "--log_samples",
    ]
    if gen_kwargs:
        cmd.extend(["--gen_kwargs", json.dumps(gen_kwargs, ensure_ascii=False)])
    return cmd


def _parse_subset_score(sub_output_dir: str, subset_task: str) -> Optional[float]:
    sub_score = None
    for item in os.listdir(sub_output_dir):
        sub = os.path.join(sub_output_dir, item)
        if os.path.isdir(sub):
            for fname in sorted(os.listdir(sub)):
                if fname.startswith("results_") and fname.endswith(".json"):
                    with open(os.path.join(sub, fname), encoding="utf-8") as f:
                        data = json.load(f)
                    td = data.get("results", {}).get(subset_task, {})
                    for metric in ["exact_match,remove_whitespace",
                                   "exact_match,custom-extract",
                                   "bleu_acc,none", "rouge1_acc,none"]:
                        if metric in td:
                            sub_score = td[metric]
                            break
                if sub_score is not None:
                    break
        if sub_score is not None:
            break
    return sub_score


# ── Pipeline 1/4: Custom (DS1000, CoderEval) ──────────────────
# Starts custom_benchmark_v13.py as subprocess.
# This script reads JSONL files from simple_evals/, queries the
# model via LM-Studio-REST-API and evaluates code execution
# in a sandbox (exec_sandboxed).
#
# IMPORTANT: This call passes --api-model as the exact load ID
# from lms ps --json. custom_benchmark_v13.py uses this ID for all
# API calls. On mismatch, LM Studio responds with HTTP 400.
#
# Qwen3.5 compatibility: --qwen-prompt enables prompt-based
# embedding instead of system message (no_system_msg in MODEL_CONFIG).
#


def _ensure_model_still_loaded(model_key: str, load_key: str, bench_name: str = "") -> None:
    """After EVERY benchmark (Custom/EvalPlus/LM-Eval/Agentic) verify the
    model is still loaded. If not, transparently reload it. This avoids
    silent crashes when a sub-process accidentally unloads the model.
    """
    cand_key = model_key.lower()
    loaded = get_current_loaded_model()
    ok = False
    if loaded:
        lk = loaded["model_key"].lower()
        li = loaded["identifier"].lower()
        if cand_key in lk or cand_key in li or lk in cand_key or li in cand_key:
            ok = True
    if not ok:
        label = f" after {bench_name}" if bench_name else ""
        print(f"  [WARN] Model{label} no longer loaded – reloading...")
        load_model_via_lms(load_key, context_length=_get_safe_context(load_key))
        if not wait_for_model_ready(timeout=60):
            print("  [WARN] Model readiness check timed out")


# Returns: dict with pipeline="custom", score (0-1).
def run_custom_benchmark(model_info: dict[str, Any], bench: dict[str, Any], sample_size: int = 5, seed: Optional[int] = None, no_structured_output: bool = False, keep_response: bool = False) -> Optional[dict[str, Any]]:
    model_key = model_info["key"]
    model_display = model_info["display"]
    fp = os.path.join(DATA_DIR, bench["file"])
    if not os.path.exists(fp):
        print(f"  [WARN] Missing: {fp}")
        return None
    print(f"\n  >>> Custom: {bench['name']} / {model_display}")
    api_model = model_info.get("_api_model") or model_key
    cmd = [
        sys.executable, os.path.join(BASE_DIR, CUSTOM_BENCHMARK_SCRIPT),
        "--non-interactive",
        "--model-key", model_key,
        "--api-model", api_model,
        "--sample-size", str(sample_size),
        "--benchmark", bench["name"],
    ]
    if seed is not None:
        cmd.extend(["--seed", str(seed)])
    # Qwen3.5 compatibility: enable systemless prompt embedding
    if _is_qwen3_5_model(model_key):
        cmd.append("--qwen-prompt")
    # Thinking mode only for reasoning models with enable_thinking=True as default
    # Gemma models have enable_thinking=False (thinking disturbs coding benchmarks)
    if THINKING_ENABLED and _is_reasoning_model(model_key) and not _is_gemma_model(model_key):
        cmd.append("--thinking")
    # Only add --no-structured-output on retry (see fallback below)
    _do_retry = no_structured_output
    if _do_retry:
        cmd.append("--no-structured-output")
    if keep_response:
        cmd.append("--keep-response")
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=PIPELINE_TIMEOUTS["custom_subprocess"],
                            encoding="utf-8", errors="replace")
    elapsed = time.time() - t0
    output = result.stdout[-2000:] if result.stdout else ""
    stderr_text = result.stderr or ""
    if output.strip():
        print(output)
    # Channel-Error Auto-Fallback: if the subprozess reports a LM Studio
    # Channel-Error (structured-output + lazy-grammar conflict, see Server-Log
    # 12.07.2026 L58671/L94468), transparently retry once with
    # --no-structured-output instead of returning a 0% score.
    # Detection via the [CHANNEL-ERROR] marker printed by the subprozess
    # when error_detail contains "Cannot combine structured output" /
    # "Channel Error" (see custom_benchmark_v13.py run benchmark loop).
    if not _do_retry and "[CHANNEL-ERROR]" in (result.stdout or ""):
        print(f"  [INFO] Channel-Error detected – retrying with --no-structured-output")
        return run_custom_benchmark(model_info, bench, sample_size=sample_size,
                                   seed=seed, no_structured_output=True)
    if result.returncode != 0:
        print(f"  [ERROR] Returncode {result.returncode}")
        print(stderr_text[-500:])
        return None
    score = None
    if output:
        # Match "Average score: XX%" (aggregated) instead of per-task "Score: XX%"
        m = re.search(r"Average score:\s*(\d+(?:\.\d+)?)%", output)
        if m:
            score = float(m.group(1)) / 100.0
    print(f"  [OK] {bench['name']} done ({elapsed:.0f}s)")
    return {"pipeline": "custom", "bench": bench["name"], "category": bench.get("category", ""),
            "model": model_display,
            "score": score, "thinking": THINKING_ENABLED}


# ── Pipeline 2/4: EvalPlus (HumanEval+, MBPP+) ────────────────
# Two-stage process:
#   1. Random sampling: sample_size tasks with seed (via evalplus API)
#   2. evalplus.codegen via direct API call (filtered to selected tasks)
#   3. evalplus.evaluate -> differential testing with plus_input
# Uses evalplus-native datasets (humanEval, mbpp).
# Returns: dict with pipeline="evalplus", score pass@1 (0-1).
def run_evalplus(model_info: dict[str, Any], bench: dict[str, Any], sample_size: int = 5, seed: Optional[int] = None, reasoning: bool = False) -> Optional[dict[str, Any]]:
    # Some models (e.g. DeepSeek Coder) generate regex patterns like "\d+"
    # instead of r"\d+", causing SyntaxWarning spam from Python 3.12+.
    warnings.filterwarnings("ignore", category=SyntaxWarning)

    model_key = model_info["key"]
    model_display = model_info["display"]
    dataset = bench["dataset"]
    gptoss = _is_gptoss_model(model_key)
    print(f"\n  >>> EvalPlus: {bench['name']} / {model_display}")
    root_dir = os.path.join(RESULTS_DIR, f"evalplus_{model_key.replace('/', '_')}")
    os.makedirs(root_dir, exist_ok=True)

    # ── Load dataset & randomly sample tasks ─────────────────
    from evalplus.data import get_human_eval_plus, get_mbpp_plus
    dataset_fn = get_human_eval_plus if dataset == "humaneval" else get_mbpp_plus
    all_tasks = dataset_fn()
    task_ids = sorted(all_tasks.keys(), key=lambda k: int(k.split("/")[1]))
    rng = random.Random(seed) if seed is not None else random
    n_select = min(sample_size, len(task_ids))
    selected_ids = set(rng.sample(task_ids, n_select))
    filtered_tasks = {k: v for k, v in all_tasks.items() if k in selected_ids}

    print(f"  [codegen] {dataset}: {len(filtered_tasks)}/{len(all_tasks)} tasks (seed={seed})")
    t0 = time.time()

    # ── Codegen via evalplus Python API ──────────────────────
    from evalplus.provider import make_model
    from evalplus.codegen import codegen as evalplus_codegen

    model_obj = make_model(
        model="local-model",
        backend="openai",
        dataset=dataset,
        base_url=API_BASE,
        temperature=0.0,
        instruction_prefix="Please provide a self-contained Python script that solves the following problem in a markdown code block:",
        response_prefix="Below is a Python script with a self-contained function that solves the problem and passes corresponding tests:",
    )

    temp_str = "1.0" if gptoss else "0.0"
    out_dir = os.path.join(root_dir, dataset)
    os.makedirs(out_dir, exist_ok=True)

    # Delete old .jsonl/.raw.jsonl to prevent accumulation across runs
    import glob as _glob
    for old_f in _glob.glob(os.path.join(out_dir, "*.jsonl")):
        try:
            os.remove(old_f)
        except Exception:
            pass

    samples_path = os.path.join(out_dir, f"local-model_openai_temp_{temp_str}.jsonl")

    limit_scale = max(1.0, n_select / 5.0)
    eval_base = PIPELINE_TIMEOUTS["evalplus_base"]
    eval_timeout = (eval_base * 2 if reasoning else eval_base) * limit_scale

    from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FUTimeout
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(
        evalplus_codegen,
        target_path=samples_path,
        model=model_obj,
        dataset=filtered_tasks,
        greedy=not gptoss,
        n_samples=1,
        resume=False,
    )
    try:
        future.result(timeout=eval_timeout)
        print(f"  [OK] codegen finished ({len(filtered_tasks)} tasks)")
    except _FUTimeout:
        print(f"  [ERROR] codegen timed out after {eval_timeout:.0f}s")
        executor.shutdown(wait=False)
        return None
    except Exception as e:
        print(f"  [ERROR] codegen failed: {e}")
        executor.shutdown(wait=False)
        return None
    finally:
        executor.shutdown(wait=False)
    del model_obj

    if not os.path.exists(samples_path):
        print(f"  [WARN] samples not found: {samples_path}")
        return None

    # Delete old eval_results, otherwise evalplus interactively asks to overwrite
    eval_results_pattern = os.path.join(os.path.dirname(samples_path), "*.eval_results.json")
    import glob
    for old_result in glob.glob(eval_results_pattern):
        try:
            os.remove(old_result)
        except Exception:
            pass

    print(f"  [evaluate] {dataset} ...")
    r2 = subprocess.run(
        [sys.executable, "-m", "evalplus.evaluate",
         "--dataset", dataset,
         "--samples", samples_path,
         "--i_just_wanna_run"],
        capture_output=True, text=True, timeout=eval_timeout,
        encoding="utf-8", errors="replace"
    )
    eval_out = r2.stdout[-500:] if r2.stdout else ""
    eval_out = "\n".join(l for l in eval_out.split("\n") if "Skipping" not in l and "WARNING" not in l)
    print(eval_out)
    score = None
    if eval_out:
        m = re.search(r"humaneval\+ \(base \+ extra tests\).*?pass@1:\s*([\d.]+)", eval_out, re.DOTALL)
        if m:
            score = float(m.group(1))
        else:
            m = re.search(r"mbpp\+ \(base \+ extra tests\).*?pass@1:\s*([\d.]+)", eval_out, re.DOTALL)
            if m:
                score = float(m.group(1))
    if r2.returncode != 0:
        print(f"  [WARN] evaluate stderr: {r2.stderr[-300:]}")
    elapsed = time.time() - t0
    print(f"  [OK] {bench['name']} done ({elapsed:.0f}s)")
    return {"pipeline": "evalplus", "bench": bench["name"], "category": bench.get("category", ""),
            "model": model_display,
            "samples": samples_path, "score": score, "thinking": THINKING_ENABLED}


# ── Pipeline 3/4: LM-Eval (ARC, HellaSwag, TruthfulQA, MATH-500, BBH) ─
# Uses lm_eval --model local-chat-completions as subprocess.
# For MMLU-Pro there is a separate modified function (see below),
# which stratifies the benchmark across 14 subset tasks.
# Returns: dict with pipeline="lmeval", score (0-1).
def run_lmeval(model_info: dict[str, Any], bench: dict[str, Any], limit: int = 5, reasoning: bool = False) -> Optional[dict[str, Any]]:
    model_key = model_info["key"]
    model_display = model_info["display"]
    gptoss = _is_gptoss_model(model_key)
    # Use exact load ID from lms ps, fallback variant, fallback key
    api_model = model_info.get("_api_model") or model_info.get("variant") or model_key
    task_name = bench["task"]
    safe = model_key.replace("/", "_").replace("\\", "_")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(RESULTS_DIR, f"lmeval_{safe}")
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n  >>> LM-Eval: {bench['name']} / {model_display}")
    t0 = time.time()
    lmeval_params = _get_lmeval_params(model_key, bench_name=bench['name'])
    #
    # Split params: constructor-level (--model_args) vs. generation-level (--gen_kwargs).
    #
    # model_args is consumed by LocalChatCompletion.__init__(**kwargs).
    #   Keys like base_url, model, num_concurrent, max_gen_toks, eos_string
    #   are constructor params. All other params in lmeval_params are silently
    #   dropped by the constructor (openai_completions.py:158 **kwargs).
    #
    # gen_kwargs is merged by the evaluator into the YAML task's generation_kwargs
    #   (evaluator.py:311: task_obj.set_config(update=True)), and then passed
    #   as gen_kwargs to _create_payload(). The remaining **gen_kwargs are
    #   spread into the API payload dict (openai_completions.py:206).
    #
    # IMPORTANT: The model parameter MUST correspond to the exact load ID from lms ps,
    #           otherwise LM Studio responds with HTTP 400 "model not found".
    #           A test with "model=check" (invalid name) causes the request to HANG
    #           (no timeout, no error response) – therefore ALWAYS use api_model.
    model_args_dict = {
        "base_url": f"{API_BASE}/chat/completions",
        "model": api_model,
        "num_concurrent": 1,
        "max_gen_toks": 512,
    }
    # Only set eos_string for models that explicitly need a fixed EOS token.
    # GPT-OSS uses <|endoftext|> as its primary stop; other chat models rely on
    # the YAML's until sequences ("\n\n", "Question:") or explicit gen_kwargs.
    if gptoss and "until" not in lmeval_params:
        model_args_dict["eos_string"] = "<|endoftext|>"
    # Gen_kwargs keys that should override YAML generation_kwargs per request.
    gen_kwargs_keys = {"max_tokens", "temperature", "top_p", "top_k", "min_p",
                       "until", "extra_body"}
    gen_kwargs = {k: v for k, v in lmeval_params.items()
                  if k in gen_kwargs_keys and v is not None}
    model_args = json.dumps(model_args_dict, ensure_ascii=False)
    cmd = [
        sys.executable, "-m", "lm_eval",
        "--model", "local-chat-completions",
        "--model_args", model_args,
        "--tasks", task_name,
        "--limit", str(limit),
        "--output_path", output_dir,
        "--apply_chat_template",
        "--log_samples",
    ]
    if gen_kwargs:
        cmd.extend(["--gen_kwargs", json.dumps(gen_kwargs, ensure_ascii=False)])
    yaml_path = None
    for p in [os.path.join(LMEVAL_TASKS_DIR, f"{task_name}.yaml"),
              os.path.join(LMEVAL_TASKS_DIR, task_name, f"{task_name}.yaml")]:
        if os.path.exists(p):
            yaml_path = p
            break
    if yaml_path:
        cmd.extend(["--include_path", os.path.dirname(yaml_path)])

    lm_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    limit_scale = max(1.0, limit / 5.0)
    lmeval_base = PIPELINE_TIMEOUTS["lmeval_base"]
    base_timeout = (lmeval_base * 2 if reasoning else lmeval_base) * limit_scale
    timeout_mult = bench.get("timeout_mult", 1)
    elapsed = 0
    stdout = ""
    stderr = ""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=base_timeout * timeout_mult,
                           encoding="utf-8", errors="replace", env=lm_env)
        stdout = r.stdout or ""
        stderr = r.stderr or ""
        elapsed = time.time() - t0
        out = stdout[-2000:]
        print(out)
        if r.returncode != 0:
            print(f"  [WARN] lm_eval returncode={r.returncode}")
            print(f"  [WARN] lm_eval stderr ({len(stderr)} chars):")
            for line in stderr.split("\n"):
                print(f"    | {line}")
        else:
            print(f"  [OK] {bench['name']} done ({elapsed:.0f}s)")
    except subprocess.TimeoutExpired:
        elapsed = time.time() - t0
        print(f"  [WARN] {bench['name']} TIMEOUT after {elapsed:.0f}s")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  [WARN] {bench['name']} ERROR: {e}")

    # Parse results JSON from output directory (may be nested: output_dir/model_name/results_*.json)
    score = None
    try:
        # Collect ALL directories to search (output_dir + all subdirectories)
        search_dirs = [output_dir]
        for item in os.listdir(output_dir):
            sub = os.path.join(output_dir, item)
            if os.path.isdir(sub):
                search_dirs.append(sub)
        # Search ALL JSON result files across all directories for the matching task
        for sdir in search_dirs:
            if not os.path.isdir(sdir):
                continue
            candidates = [f for f in os.listdir(sdir) if f.startswith("results_") and f.endswith(".json")]
            candidates.sort(key=lambda f: os.path.getmtime(os.path.join(sdir, f)), reverse=True)
            for fname in candidates:
                with open(os.path.join(sdir, fname), "r", encoding="utf-8") as f:
                    data = json.load(f)
                task_data = data.get("results", {}).get(task_name, {})
                if task_data:
                    for metric in ["exact_match,custom-extract",
                                "bleu_acc,none", "rouge1_acc,none",
                               "exact_match,remove_whitespace",
                               "exact_match,none", "math_verify,none"]:
                        if metric in task_data:
                            score = task_data[metric]
                            break
                if score is not None:
                    break
            if score is not None:
                break
    except Exception as e:
        print(f"  [WARN] lm_eval score parsing: {e}")

    return {"pipeline": "lmeval", "bench": bench["name"], "category": bench.get("category", ""),
            "model": model_display,
            "score": score, "thinking": THINKING_ENABLED}


# ── MMLU-Pro (ARCHIVIERT 12.07.2026) ──
# Die spezielle MMLU-Pro-Auswertung wurde aus Performance-Gründen
# (12,032 Tasks × ~25s/call = >50h pro Modell auf 16-GB-VRAM) aus
# dem aktiven Launcher entfernt. Die Logik ist in
# `Archiv/run_mmlupro_benchmark.py` self-contained ausgelagert
# und kann bei Bedarf aufgerufen werden mit:
#     python Archiv/run_mmlupro_benchmark.py --model <key> --sample-size 14
# Siehe Code-Review_2026-07-12.md §3.1 D4 für Details.

# ── Pipeline 4/4: Agentic (tool-eval-bench) ───────────────────
# Starts tool_eval_bench as module (-m) with a random
# selection from 69 scenarios (TC-01..TC-69). Each scenario tests
# tool-use capabilities (function calls, API usage).
# Result is extracted from JSON envelope (final_score 0-100 -> 0-1).
# Returns: dict with pipeline="agentic", score (0-1).
def run_agentic(model_info: dict[str, Any], limit: int = 5) -> Optional[dict[str, Any]]:
    """Agentic: tool-eval-bench with sample_size random scenarios."""
    model_key = model_info["key"]
    model_display = model_info["display"]
    safe = model_key.replace("/", "_").replace("\\", "_")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(RESULTS_DIR, f"agentic_{safe}")
    os.makedirs(output_dir, exist_ok=True)
    json_path = os.path.join(output_dir, f"agentic_{model_key}_{ts}.json")

    selected = random.sample(TOOL_EVAL_SCENARIO_IDS, min(limit, len(TOOL_EVAL_SCENARIO_IDS)))

    print(f"\n  >>> Agentic (tool-eval-bench): {model_display}")
    print(f"      Scenarios: {len(selected)}/{len(TOOL_EVAL_SCENARIO_IDS)} randomly selected")

    t0 = time.time()
    cmd = [
        sys.executable, "-m", "tool_eval_bench",
        "--base-url", "http://127.0.0.1:1234/v1",
        "--scenarios", *selected,
        "--json-file", json_path,
        "--timeout", str(PIPELINE_TIMEOUTS["agentic_scenario"]),
        "--no-live",
    ]
    lm_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    score = None
    stdout = ""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=PIPELINE_TIMEOUTS["agentic_subprocess"],
                           encoding="utf-8", errors="replace", env=lm_env)
        stdout = r.stdout or ""
        stderr = r.stderr or ""
        elapsed = time.time() - t0
        if r.returncode == 0:
            print(f"  [OK] Agentic done ({elapsed:.0f}s)")
        else:
            print(f"  [WARN] tool-eval-bench returncode={r.returncode}")
            for line in stderr.split("\n")[-5:]:
                print(f"    | {line}")

        # Parse JSON result – tool-eval-bench envelope format
        if os.path.exists(json_path):
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
            # final_score: int 0-100 im Envelope, auf 0-1 normalisieren
            raw = data.get("final_score") if isinstance(data, dict) else None
            if raw is not None:
                score = raw / 100.0
            else:
                # Fallback: average scenario_results
                scores_meta = data.get("scores", {}) if isinstance(data, dict) else {}
                results = scores_meta.get("scenario_results", [])
                if results:
                    vals = [s.get("score", 0) for s in results if isinstance(s, dict)]
                    score = sum(vals) / len(vals) if vals else None
    except subprocess.TimeoutExpired:
        elapsed = time.time() - t0
        print(f"  [WARN] Agentic TIMEOUT after {elapsed:.0f}s")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  [WARN] Agentic ERROR: {e}")

    return {"pipeline": "agentic", "bench": "Agentic", "category": "agentic",
            "model": model_display,
            "score": score, "thinking": THINKING_ENABLED}


def save_summary_csv(results: list[dict[str, Any]], model_info: Optional[dict[str, Any]] = None,
                     sample_size: int = 5, seed: str = "", exclude_benchmarks: str = "",
                     no_structured_output: str = "", no_unload_between: str = "") -> Any:
    """Legacy – forwards to csv_writer."""
    return csv_writer.write_accumulative_summary(
        results, model_info or {},
        sample_size=sample_size, seed=seed, exclude_benchmarks=exclude_benchmarks,
        no_structured_output=no_structured_output, no_unload_between=no_unload_between,
        base_dir=BASE_DIR,
    )


# NOTE: Legacy save_model_summary_csv wurde am 12.07.2026 entfernt
# (Code-Review_2026-07-12.md §3.1 D5). Direkt
# csv_writer.write_accumulative_summary(...) nutzen.


def main() -> None:
    # ── Entry Point ─────────────────────────────────────────
    # Flow:
    #   1. Resolve models (CLI argument or interactive)
    #   2. Resolve benchmarks (CLI argument or interactive)
    #   3. For each model:
    #      a. Load model (via model_manager.load_model_via_lms)
    #      b. For each benchmark: call pipeline function
    #      c. Intermediate summary via csv_writer
    #   4. Unload model
    #   5. Consolidated overview via csv_writer
    #
    # Important: All pipelines use model_info["_api_model"]
    # as unified model ID – no more mismatch between
    # loaded ID and API call.
    parser = argparse.ArgumentParser(description="Unified Benchmark Launcher v13")
    parser.add_argument("--sample-size", "-s", type=int, default=5,
                        help="Tasks per benchmark (default: 5)")
    parser.add_argument("--model", "-m", type=str, default=None,
                        help="Model selection: number(s) like '20', '1,3,5', '1-5', name or 'all'")
    parser.add_argument("--benchmarks", "-b", type=str, default=None,
                        help="Benchmark selection: number(s), name(s) or 'all'")
    parser.add_argument("--thinking", action="store_true",
                        help="Enable thinking mode for MATH-500 (reasoning models)")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed for reproducible task selection (passed to custom benchmarks)")
    parser.add_argument("--exclude-benchmarks", "-x", type=str, default=None,
                        help="Comma-separated benchmark names to exclude (e.g. 'MATH-500')")
    parser.add_argument("--no-structured-output", action="store_true",
                        help="Disable structured JSON output in custom benchmarks (fallback to regex)")
    parser.add_argument("--unload-between", action="store_true",
                        help="Reload model between benchmarks (default: keep loaded). "
                             "Use if KV-cache/GPU memory degradation occurs.")
    parser.add_argument("--keep-response", action="store_true",
                        help="Write the full LLM response to per-task CSVs (default: truncated to 200 chars, see W1 in Code-Review_2026-07-12.md)")
    args = parser.parse_args()

    global THINKING_ENABLED
    THINKING_ENABLED = args.thinking

    # Read version from VERSION file (Prio 4.17 – single source of truth)
    _version = "13.0.0-p3"
    _version_file = os.path.join(BASE_DIR, "VERSION")
    if os.path.isfile(_version_file):
        with open(_version_file, "r", encoding="utf-8") as _vf:
            for _line in _vf:
                if _line.startswith("__version__"):
                    _version = _line.split("=", 1)[1].strip().strip("'\"")
                    break

    print("=" * 60)
    print(f"  Unified Benchmark Launcher v{_version}")
    print(f"  SampleSize: {args.sample_size}")
    if args.thinking:
        print("  Thinking mode: ON (MATH-500, reasoning models)")
        print("  Pipelines: Custom (DS1000/CoderEval), EvalPlus, LM-Eval (ARC/HS/TQA/IFEval/M500), Agentic (tool-eval-bench)")
    print("  CSV-Format: csv_writer (; Delimiter, utf-8)")
    print("=" * 60)

    available = get_available_models(exclude_keywords=EXCLUDE_KEYWORDS)
    if not available:
        print("[ERROR] No models available. Aborting.")
        sys.exit(1)

    if args.model:
        models = resolve_models(available, args.model)
    else:
        models = select_models_interactive(available)
    if not models:
        print("[ERROR] No models selected. Aborting.")
        sys.exit(1)
    print(f"  Models: {', '.join(m['display'] for m in models)}")

    if args.benchmarks:
        benchmarks = resolve_benchmarks(args.benchmarks)
    else:
        benchmarks = select_benchmarks_interactive()
    if not benchmarks:
        print("[ERROR] No benchmarks selected. Aborting.")
        sys.exit(1)

    # Apply --exclude-benchmarks filter
    if args.exclude_benchmarks:
        exclude_names = {n.strip().lower() for n in args.exclude_benchmarks.split(",")}
        excluded = [b for b in benchmarks if b["name"].lower() in exclude_names]
        benchmarks = [b for b in benchmarks if b["name"].lower() not in exclude_names]
        if excluded:
            print(f"  Excluded: {', '.join(b['name'] for b in excluded)}")
        if not benchmarks:
            print("[ERROR] All benchmarks excluded. Aborting.")
            sys.exit(1)

    print(f"  Benchmarks: {', '.join(b['name'] for b in benchmarks)}")

    all_summary = []
    for midx, model_info in enumerate(models, 1):
        model_key = model_info["key"]
        load_key = model_info.get("model_key", model_key)   # base key for lms load
        model_display = model_info["display"]
        reasoning = _is_reasoning_model(model_key) or _is_qwen3_6_model(model_key)
        print(f"\n{'=' * 60}")
        print(f"  Model {midx}/{len(models)}: {model_display}")
        if reasoning:
            print(f"  * Reasoning model (detected) – timeout ×2")
        if _is_moe_model(model_key):
            print(f"  * MoE model (detected)")
        print(f"{'=' * 60}")

        # CENTRAL Model management: load + determine exact identifiers
        loaded = get_current_loaded_model()
        api_model = None

        if loaded:
            li = loaded["identifier"].lower()
            lk = loaded["model_key"].lower()
            mk = model_key.lower()
            desired_ctx = _get_safe_context(load_key)
            current_ctx = loaded.get("context_length")
            # Check if this model is already loaded (key or identifier match)
            if mk in li or mk in lk or li in mk or lk in mk:
                if current_ctx is not None and desired_ctx is not None and current_ctx != desired_ctx:
                    print(f"  [INFO] '{model_display}' loaded with context={current_ctx}, need {desired_ctx} – reloading...")
                    unload_all_models()
                    ok, api_model = load_model_via_lms(load_key, context_length=desired_ctx)
                    if not ok:
                        print(f"  [ERROR] Loading failed. Skipping.")
                        continue
                else:
                    api_model = loaded["identifier"]
                    print(f"  [OK] '{model_display}' already loaded – ID: {api_model}")
            else:
                print(f"  [INFO] Different model loaded ({loaded['display_name']}) – unloading...")
                unload_all_models()
                ok, api_model = load_model_via_lms(load_key, context_length=desired_ctx)
                if not ok:
                    print(f"  [ERROR] Loading failed. Skipping.")
                    continue
        else:
            ok, api_model = load_model_via_lms(load_key, context_length=_get_safe_context(load_key))
            if not ok:
                print(f"  [ERROR] Loading failed. Skipping.")
                continue
        # Verify loaded model context length matches desired value
        desired_ctx = _get_safe_context(load_key)
        if desired_ctx is not None:
            loaded_after = get_current_loaded_model()
            actual_ctx = loaded_after.get("context_length") if loaded_after else None
            if actual_ctx is not None and actual_ctx != desired_ctx:
                print(f"  [WARN] Model loaded with context={actual_ctx}, expected {desired_ctx} – reloading...")
                unload_all_models()
                ok, api_model = load_model_via_lms(load_key, context_length=desired_ctx)
                if ok:
                    loaded_after = get_current_loaded_model()
                    actual_ctx = loaded_after.get("context_length") if loaded_after else None
                    if actual_ctx is not None and actual_ctx != desired_ctx:
                        print(f"  [ERROR] Still context={actual_ctx} after reload – continuing anyway")
                    else:
                        print(f"  [OK] Context now {desired_ctx}")
                else:
                    print(f"  [ERROR] Reload failed – continuing with context={actual_ctx}")

        # Short pause – the model is confirmed loaded via lms ps,
        # but the REST server needs a moment to initialize.
        # 30B models can take 30-60s to finish loading on RTX 5070 Ti
        # (see Server-Log 12.07.2026: 13x "No models loaded" with 30s timeout).
        print("  [INFO] Waiting for API readiness...")
        if not wait_for_model_ready(timeout=60):
            print("  [WARN] Model readiness check timed out – continuing anyway")
        model_info["_api_model"] = api_model  # Unified ID for ALL pipelines

        # Warn if loaded variant differs from requested quant
        all_variants = model_info.get("variants") or []
        if len(all_variants) > 1 and api_model:
            desired_quant = model_info.get("quant", "").lower()
            if desired_quant and desired_quant not in api_model.lower():
                print(f"  [WARN] Requested '@{desired_quant}' but '{api_model}' loaded")
                print(f"  [WARN] Available variants: {', '.join(v.split('@')[-1] for v in all_variants)}")
                print(f"  [WARN] Load specific quant via LM Studio GUI or install only the desired variant")

        model_results = []

        for bidx, bench in enumerate(benchmarks):
            # Unload/reload between benchmarks — off by default, opt-in via --unload-between
            if args.unload_between and bidx > 0:
                print(f"  [INFO] Unloading/reloading model between benchmarks...")
                unload_all_models()
                time.sleep(2)
                ok, api_model = load_model_via_lms(load_key, context_length=_get_safe_context(load_key))
                if not ok:
                    print(f"  [ERROR] Reload before {bench['name']} failed. Skipping.")
                    continue
                print("  [INFO] Waiting for API re-initialization...")
                if not wait_for_model_ready(timeout=60):
                    print("  [WARN] Model readiness check timed out – continuing anyway")
                model_info["_api_model"] = api_model

            try:
                bname = bench["name"]
                ep_names = {b["name"] for b in EVALPLUS_BENCHMARKS}
                lmeval_names = {b["name"] for b in LMEVAL_BENCHMARKS}
                agentic_names = {b["name"] for b in AGENTIC_BENCHMARKS}

                if bname in agentic_names:
                    result = run_agentic(model_info, limit=args.sample_size)
                elif bname in ep_names:
                    result = run_evalplus(model_info, bench, sample_size=args.sample_size, seed=args.seed, reasoning=reasoning)
                elif bname in lmeval_names:
                    per_limit = max(bench.get("min_limit", 0), args.sample_size)
                    result = run_lmeval(model_info, bench, limit=per_limit, reasoning=reasoning)
                else:
                    result = run_custom_benchmark(model_info, bench, sample_size=args.sample_size, seed=args.seed, no_structured_output=args.no_structured_output, keep_response=args.keep_response)

                if result:
                    model_results.append(result)

                # After custom benchmarks: check model status
                if result:
                    all_summary.append(result)

                # After EVERY benchmark: check whether the model is still loaded.
                # Previously this was only for Custom – EvalPlus/LM-Eval/Agentic
                # could silently lose the model between runs.
                _ensure_model_still_loaded(model_key, load_key, bench_name=bname)
            except subprocess.TimeoutExpired:
                print(f"  [ERROR] {bench['name']} timeout (expired)")
            except Exception as e:
                print(f"  [ERROR] {bench['name']}: {e}")

        # Intermediate summary per model (csv_writer, uniform schema)
        if model_results:
            csv_writer.write_accumulative_summary(model_results, model_info,
                                                  sample_size=args.sample_size,
                                                  seed=str(args.seed or ""),
                                                  exclude_benchmarks=args.exclude_benchmarks or "",
                                                  no_structured_output=str(args.no_structured_output or ""),
                                                  no_unload_between='True' if not args.unload_between else '',
                                                  base_dir=BASE_DIR)

    print("\n" + "=" * 60)
    print("  FINISHED")
    print("=" * 60)
    for s in all_summary:
        cat = s.get("category", "").ljust(9)
        print(f"  [{s['pipeline']}] {s['model']} / {cat}{s['bench']}")

    # Free memory: unload model
    print("\n  [INFO] Cleaning up – unloading model(s)...")
    unload_all_models()

    # Consolidated overall overview (csv_writer)
    if all_summary and len(models) > 1:
        csv_writer.write_konsolidiert_aktuell(all_summary,
                                              sample_size=args.sample_size,
                                              seed=str(args.seed or ""),
                                              exclude_benchmarks=args.exclude_benchmarks or "",
                                              no_structured_output=str(args.no_structured_output or ""),
                                               no_unload_between='True' if not args.unload_between else '',
                                              base_dir=BASE_DIR)


if __name__ == "__main__":
    main()
