#!/usr/bin/env python3
"""
Unified benchmark launcher v13 - integrates:
  [1] Custom: DS1000, CoderEval (custom_benchmark.py)
  [2] EvalPlus: HumanEval+, MBPP+ (evalplus.codegen + evalplus.evaluate)
  [3] LM-Eval: ARC, HellaSwag, TruthfulQA, IFEval, MATH-500 (lm_eval)
  [4] Agentic: tool-eval-bench (SampleSize scenarios, random selection)

── Four-Pipeline Architecture ──────────────────────────────────────
  This script is the CENTRAL ENTRY POINT. It orchestrates all
  four evaluation pipelines as subprocesses. ONLY HERE is model
  management (load/unload) initiated - the subprocesses must
  NOT load/unload themselves.

  Pipeline         Script/Tool                Data Source
  ────────         ───────────                ───────────
  Custom           custom_benchmark.py    JSONL under simple_evals/
  EvalPlus         evalplus.codegen/evaluate  evalplus-native datasets
  LM-Eval          lm_eval CLI                lm-eval built-in + custom YAML
  Agentic          tool_eval_bench (<-m)      HuggingFace tool_eval_bench

  All results are output via csv_writer.py with a uniform schema
  (; delimiter, UTF-8) and consolidated by consolidate_results.py
  into rankings.

── Script Hierarchy ────────────────────────────────────────────────
  run_benchmarks.py  (Launcher, ONLY HERE load/unload)
    ├── model_manager.py         (load/unload/check via lms CLI)
    ├── custom_benchmark.py (subprocess: DS1000, CoderEval)
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
  - Reasoning timeout x2 for reasoning models
  - MoE detection
"""

from __future__ import annotations

import os as _os
import sys as _sys

# Make `src` importable regardless of the working directory
# (python -m src.run_benchmarks from the repo root puts only the CWD
# on sys.path, not `src/`). Fix for Code-Review_2026-08-03.md F4.
_SRC_DIR = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _SRC_DIR)

import argparse
import atexit
import glob
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
import warnings
from datetime import datetime
from typing import TYPE_CHECKING, Any

import psutil

import csv_writer as csv_writer

if TYPE_CHECKING:
    from type_defs import AvailableModelInfo, BenchmarkDef, PipelineResult

# ── Model Management from Shared Module ──────────────────────
# Load/Unload is ONLY initiated in main() of this script.
# The subprocesses (custom_benchmark.py, evalplus, lm_eval, tool_eval_bench)
# must NOT load/unload themselves - they receive the model ID
# via model_info["_api_model"] and only call the API.
#
# API reference (LM Studio REST / OpenAI-Compat):
#   https://lmstudio.ai/docs/developer/rest
#
# Important endpoints:
#   /api/v1/models              GET  - native: model list
#   /api/v1/models/load         POST - native: load model (streamed events)
#   /api/v1/models/unload       POST - native: unload model
#   /api/v1/chat                POST - native: chat inference
#   /v1/chat/completions        POST - OpenAI-Compat: chat inference
#   /v1/models                  GET  - OpenAI-Compat: model list
#
from benchmark_config import (
    AGENTIC_SAFETY_SCENARIO_IDS,
    EXCLUDE_KEYWORDS,
    PIPELINE_TIMEOUTS,
    TOOL_EVAL_SCENARIO_IDS,
    get_model_config,
)
from model_manager import (
    API_BASE,
    get_available_models,
    get_current_loaded_model,
    has_unloaded_all_models,
    is_model_ready,
    load_model_via_lms,
    parse_selection,
)
from utils.terminal import (
    cyan,
    green,
    ok,
    progress_bar,
    warn,
)

# Model classification helper functions
REASONING_KEYWORDS = ["reasoning", "think", "r1", "rnj", "magistral"]

def _is_qwen3_6_model(model_identifier: str) -> bool:
    return "qwen3.6" in model_identifier.lower()
MOE_PATTERN = re.compile(r"\d+b-a\d+b", re.IGNORECASE)  # e.g., "8b-a1b", "24b-a2b"

def _is_reasoning_model(model_identifier: str) -> bool:
    """Check registry for reasoning field (thinking=True, instruct=False).

    Falls back to False with a warning if no registry data.
    """
    try:
        from assemble_blueprint import normalize_model_name
        registry, rnorm = _load_registry_for_context()
        normalized_key = normalize_model_name(model_identifier)
        base_key = normalized_key.split("@")[0]
        matched_key = rnorm.get(normalized_key) or rnorm.get(base_key)
        if matched_key:
            entry = registry[matched_key]
            reasoning_val = entry.get("reasoning")
            if reasoning_val == "thinking":
                return True
            if reasoning_val == "instruct":
                return False
        print(f"  [WARN] {model_identifier}: reasoning nicht in Registry - "
              "`python registry_tool.py sync` ausführen.", file=sys.stderr)
    except (ImportError, KeyError, OSError):
        pass
    return False


def _check_reasoning_registry(model_identifier: str) -> bool | None:
    """Tri-state: True (thinking), False (instruct), None (missing/unknown)."""
    try:
        from assemble_blueprint import normalize_model_name
        registry, rnorm = _load_registry_for_context()
        normalized_key = normalize_model_name(model_identifier)
        base_key = normalized_key.split("@")[0]
        matched_key = rnorm.get(normalized_key) or rnorm.get(base_key)
        if matched_key:
            entry = registry[matched_key]
            reasoning_val = entry.get("reasoning")
            if reasoning_val == "thinking":
                return True
            if reasoning_val == "instruct":
                return False
        return None
    except (ImportError, KeyError, OSError):
        return None

def _is_mamba_model(model_identifier: str) -> bool:
    return "mamba" in model_identifier.lower()

def _is_moe_model(model_identifier: str) -> bool:
    return bool(MOE_PATTERN.search(model_identifier))

def _is_qwen3_5_model(model_identifier: str) -> bool:
    return "qwen3.5" in model_identifier.lower() or "qwopus3" in model_identifier.lower()

def _is_gptoss_model(model_identifier: str) -> bool:
    return "gpt-oss" in model_identifier.lower()

def _is_gemma_model(model_identifier: str) -> bool:
    return "gemma" in model_identifier.lower()

# ── GGUF EOS lookup (for tasks without YAML until sequences, e.g. IFEval) ──
# Root cause of IFEval HTTP 500 "does not match the expected peg-native format"
# (llama.cpp post-generation PEG parser, see ggml-org/llama.cpp #20260):
# ifeval.yaml ships `until: []`, so no stop string is sent to the engine and
# the model generates freely until its own EOS - at extreme quants (e.g. Jamba2
# IQ2_XXS) this frequently produces output that violates the model's chat
# template format. Other lm_eval tasks define `until` in their YAML and are
# unaffected. Fix: resolve the model's EOS token from the GGUF header and send
# it as `eos_string` (-> `stop` in the OpenAI payload) for such tasks.
_GGUF_EOS_CACHE: dict[str, str | None] = {}
_GGUF_EOS_LOCK = threading.Lock()

def _resolve_model_gguf_path(model_identifier: str) -> str | None:
    """Find the model's GGUF file under the LM Studio models cache.

    Substring match on the normalised identifier suffix (like
    registry_tool._resolve_model_path_multi, but self-contained).
    """
    models_root = os.path.expanduser(os.path.join("~", ".lmstudio", "models"))
    if not os.path.isdir(models_root):
        return None
    suffix = model_identifier.split("/", 1)[1] if "/" in model_identifier else model_identifier
    suffix_norm = suffix.replace("_", "").replace("-", "").replace("@", "").lower()
    for g in sorted(glob.glob(os.path.join(models_root, "**", "*.gguf"), recursive=True)):
        g_base = os.path.basename(g).lower()
        if "mmproj" in g_base or g_base.startswith("mtp-"):
            continue
        g_norm = os.path.basename(g).replace("_", "").replace("-", "").lower()
        if suffix_norm and suffix_norm in g_norm:
            return g
    return None


def _get_model_eos_string(model_identifier: str) -> str | None:
    """Return the EOS token string of a model from its GGUF header (cached).

    Reads tokenizer.ggml.eos_token_id + the interleaved string-array vocab
    (GGUF v3: header parts, then per string [uint64 length, uint8 data]).
    Returns None on any parse failure - callers must keep the previous behaviour.
    """
    with _GGUF_EOS_LOCK:
        if model_identifier in _GGUF_EOS_CACHE:
            return _GGUF_EOS_CACHE[model_identifier]
    path = _resolve_model_gguf_path(model_identifier)
    if not path:
        _GGUF_EOS_CACHE[model_identifier] = None
        return None
    try:
        from gguf import GGUFReader  # installed; used by registry_tool.py
        reader = GGUFReader(path)
        eos_field = reader.fields.get("tokenizer.ggml.eos_token_id")
        tokens_field = reader.fields.get("tokenizer.ggml.tokens")
        if eos_field is None or tokens_field is None:
            _GGUF_EOS_CACHE[model_identifier] = None
            return None
        eos_id = int(eos_field.parts[-1][0])
        parts = tokens_field.parts
        # Header: 5 parts (key len, key bytes, vtype, elem type, count),
        # then per token [uint64 length, uint8 data].
        if len(parts) < 7 + 2 * eos_id + 1:
            _GGUF_EOS_CACHE[model_identifier] = None
            return None
        length = int(parts[5 + 2 * eos_id][0])
        raw = bytes(parts[6 + 2 * eos_id][:length])
        eos_str = raw.decode("utf-8", errors="replace")
        result = eos_str if eos_str else None
    except Exception:
        result = None
    _GGUF_EOS_CACHE[model_identifier] = result
    return result


def _task_yaml_has_until_sequence(task_name: str) -> bool:
    """Check whether the task's YAML defines `generation_kwargs.until`.

    Looks in the custom lm_eval_tasks dir first, then in the installed
    lm_eval package. Returns True on any read failure (conservative: keep
    the existing behaviour of NOT sending an eos_string).
    """
    candidates = [
        os.path.join(LMEVAL_TASKS_DIR, f"{task_name}.yaml"),
        os.path.join(LMEVAL_TASKS_DIR, task_name, f"{task_name}.yaml"),
    ]
    try:
        import lm_eval
        lm_eval_tasks = os.path.join(os.path.dirname(lm_eval.__file__), "tasks")
        candidates += [
            os.path.join(lm_eval_tasks, f"{task_name}.yaml"),
            os.path.join(lm_eval_tasks, task_name, f"{task_name}.yaml"),
        ]
    except (ImportError, AttributeError):
        pass
    import yaml
    class _NoopLoader(yaml.SafeLoader):
        pass
    def _noop_tag(loader: Any, tag_suffix: Any, node: Any) -> Any:
        # lm_eval YAML files use tags like !function utils.process_results;
        # for the until check the scalar value is all we need.
        if isinstance(node, yaml.ScalarNode):
            return loader.construct_scalar(node)
        if isinstance(node, yaml.SequenceNode):
            return loader.construct_sequence(node, deep=True)
        return loader.construct_mapping(node, deep=True)
    _NoopLoader.add_multi_constructor("!", _noop_tag)
    for p in candidates:
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    # _NoopLoader ersetzt alle `!tag`-Konstruktionen durch sichere
                    # No-Op-Konstruktoren (Scalar/Sequence/Mapping); yaml.safe_load
                    # scheitert an lm_eval-`!function`-Tags und wuerde das Verhalten aendern.
                    data = yaml.load(fh, Loader=_NoopLoader)  # noqa: S506 - _NoopLoader ist bewusst sicher (s. o.)
                gen = data.get("generation_kwargs") or {}
                until = gen.get("until")
                return bool(until)
            except Exception:
                return True  # cannot verify -> keep current behaviour
    return True  # task not found -> keep current behaviour


def _lmeval_needs_eos_string(task_name: str, evaluation_parameters: dict[str, Any]) -> bool:
    """True if this lm_eval invocation needs an explicit eos_string stop.

    Covers tasks without an until sequence in their YAML (e.g. IFEval) and
    without a model-config until override.
    """
    if "until" in evaluation_parameters and evaluation_parameters.get("until"):
        return False
    return not _task_yaml_has_until_sequence(task_name)


def _model_short_name(model_identifier: str) -> str:
    """Generates a short filename-compatible model name."""
    s = model_identifier.replace("/", "_").replace("\\", "_").replace(" ", "_")
    for sep in ("/", "\\"):
        if sep in s:
            s = s.rsplit(sep, 1)[-1]
    return s[:30]

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SRC_DIR)
RESULTS_DIR = os.path.join(PROJECT_ROOT, "ergebnisse")
DATA_DIR = os.path.join(PROJECT_ROOT, "simple_evals")
os.makedirs(RESULTS_DIR, exist_ok=True)

# ── LM-Eval Proxy ──────────────────────────────────────────────
LMEVAL_PROXY_PORT = 1235
LMEVAL_PROXY_SCRIPT = os.path.join(SRC_DIR, "tools", "lmeval_proxy.py")
_lmeval_proxy_proc: subprocess.Popen | None = None


def _proxy_is_running() -> bool:
    return _lmeval_proxy_proc is not None and _lmeval_proxy_proc.poll() is None


def _start_lmeval_proxy() -> None:
    global _lmeval_proxy_proc
    if _proxy_is_running():
        return
    if not os.path.isfile(LMEVAL_PROXY_SCRIPT):
        print(f"  [WARN] lmeval_proxy.py not found at {LMEVAL_PROXY_SCRIPT} - proxy disabled")
        return
    try:
        _lmeval_proxy_proc = subprocess.Popen(
            [sys.executable, LMEVAL_PROXY_SCRIPT, "--port", str(LMEVAL_PROXY_PORT)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        # Wait briefly for startup
        import socket
        for _ in range(10):
            if _proxy_is_running():
                try:
                    s = socket.socket()
                    s.settimeout(0.5)
                    s.connect(("127.0.0.1", LMEVAL_PROXY_PORT))
                    s.close()
                    print(f"  [OK] LM-Eval Proxy on port {LMEVAL_PROXY_PORT}")
                    return
                except (ConnectionRefusedError, OSError):
                    pass
            time.sleep(0.3)
        print(f"  [WARN] lmeval_proxy started but not responding on port {LMEVAL_PROXY_PORT}")
    except (OSError, subprocess.SubprocessError) as e:
        print(f"  [WARN] lmeval_proxy failed to start: {e}")


def _stop_lmeval_proxy() -> None:
    global _lmeval_proxy_proc
    if _lmeval_proxy_proc is None:
        return
    try:
        _lmeval_proxy_proc.terminate()
        _lmeval_proxy_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _lmeval_proxy_proc.kill()
    except (OSError, subprocess.SubprocessError):
        pass
    _lmeval_proxy_proc = None

# ── Single-Instance Lock ─────────────────────────────────────────
# Prevents parallel launcher instances: concurrent runs load/unload
# models against each other (VRAM first, then system RAM - observed
# 2026-07-31 with 3 parallel runs: 32 GB system RAM exhausted, hang).
LOCK_PATH = os.path.join(RESULTS_DIR, ".benchmark.lock")


def _acquire_single_instance_lock(lock_path: str | None = None) -> str | None:
    """Acquire the single-instance lock file.

    Returns an error message if another LIVE launcher holds the lock,
    else None on success (lock file written for this PID).
    Stale lock files (dead PID or corrupt content) are overwritten.
    """
    lock_path = lock_path or LOCK_PATH
    if os.path.exists(lock_path):
        try:
            with open(lock_path, encoding="utf-8") as f:
                data = json.load(f)
            pid = int(data.get("pid", -1))
            started = data.get("started", "?")
            if pid > 0 and psutil.pid_exists(pid):
                proc = psutil.Process(pid)
                if proc.is_running():
                    return (f"[FATAL] Another benchmark launcher is already running "
                            f"(PID {pid}, started {started}). Parallel runs load/unload "
                            f"models against each other and exhaust VRAM/system RAM. "
                            f"Wait until it finishes or kill it first.")
        except (OSError, ValueError, KeyError):
            pass  # corrupt or unreadable lock file -> treat as stale
        except psutil.Error:
            pass  # process vanished while checking -> stale
    try:
        with open(lock_path, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(),
                       "started": datetime.now().isoformat(timespec="seconds")}, f)
    except OSError as e:
        print(f"  [WARN] Cannot write lock file {lock_path}: {e}")
    return None


def _release_single_instance_lock(lock_path: str | None = None) -> None:
    """Remove the lock file if this process still owns it."""
    lock_path = lock_path or LOCK_PATH
    try:
        if os.path.exists(lock_path):
            with open(lock_path, encoding="utf-8") as f:
                data = json.load(f)
            if int(data.get("pid", -1)) == os.getpid():
                os.remove(lock_path)
    except (OSError, ValueError, KeyError):
        pass


# Magic-string constants (Code-Review 2026-07-18 §5.3): sentinel model
# name required by evalplus.provider.make_model(). The actual model
# routing happens via the OpenAI-compatible request to LMS.
EVALPLUS_SENTINEL_MODEL = "local-model"

# Global: ensure all subprocesses inherit UTF-8 encoding (Windows cp1252 workaround)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
# Also reconfigure this process's stdout so print() doesn't choke on Unicode arrows/symbols
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

LMEVAL_TASKS_DIR = os.path.join(PROJECT_ROOT, "lm_eval_tasks")

# ── Script References ──────────────────────────────────────
# Custom benchmark script (renamed from custom_benchmark_v13.py).
CUSTOM_BENCHMARK_SCRIPT = os.path.join(SRC_DIR, "custom_benchmark.py")
if not os.path.exists(CUSTOM_BENCHMARK_SCRIPT):
    sys.exit(f"[FATAL] custom_benchmark.py not found at {CUSTOM_BENCHMARK_SCRIPT}")
print(f"[INFO] Using custom_benchmark script: {os.path.basename(CUSTOM_BENCHMARK_SCRIPT)}")
print(f"[INFO] Subprocess interpreter: {sys.executable}")
print(f"[INFO] Repository root:        {PROJECT_ROOT}")

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

# MMLU-Pro 14 Subsets (lm_eval individual tasks) - removed in v13: too expensive
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
_REGISTRY_DATA: dict | None = None
_REGISTRY_NORM: dict[str, str] | None = None

def _load_registry_for_context() -> tuple[dict[str, Any], dict[str, str]]:
    global _REGISTRY_DATA, _REGISTRY_NORM
    if _REGISTRY_DATA is not None:
        return _REGISTRY_DATA, _REGISTRY_NORM

    from pathlib import Path

    from assemble_blueprint import normalize_model_name

    rpath = Path(__file__).resolve().parent.parent / "doc-git" / "model_registry.yaml"
    if not rpath.exists():
        _REGISTRY_DATA = {}
        _REGISTRY_NORM = {}
        return _REGISTRY_DATA, _REGISTRY_NORM

    try:
        from ruamel.yaml import YAML
        from ruamel.yaml.error import YAMLError
        y = YAML()
        y.preserve_quotes = True
        with open(rpath, encoding="utf-8") as f:
            data = y.load(f) or {}
    except (YAMLError, OSError, UnicodeDecodeError) as e:
        print(f"  [WARN] model_registry.yaml fehlerhaft: {e}", file=sys.stderr)
        _REGISTRY_DATA = {}
        _REGISTRY_NORM = {}
        return _REGISTRY_DATA, _REGISTRY_NORM

    norm = {}
    for key, entry in data.items():
        if isinstance(entry, dict):
            normalized_key = normalize_model_name(key)
            norm[normalized_key] = key
    _REGISTRY_DATA = data
    _REGISTRY_NORM = norm
    return _REGISTRY_DATA, _REGISTRY_NORM


def _get_safe_context(model_identifier: str) -> int | None:
    """Return capped context length for VRAM-safe model loading.

    Priority:
      1. model_registry.yaml entry matching via normalized name
      2. SAFE_CONTEXT_FALLBACK hardcoded dict
    """
    from assemble_blueprint import normalize_model_name

    # 1. Try registry
    registry, rnorm = _load_registry_for_context()
    normalized_key = normalize_model_name(model_identifier)
    if normalized_key in rnorm:
        entry = registry[rnorm[normalized_key]]
        ctx = entry.get("context_length")
        if ctx is not None:
            return int(ctx)

    # 2. Try fallback (exact normalized match)
    for pattern, ctx in SAFE_CONTEXT_FALLBACK.items():
        if normalize_model_name(pattern) == normalized_key:
            return ctx

    # 3. Try substring fallback matching (for patterns that are prefixes)
    for pattern, ctx in SAFE_CONTEXT_FALLBACK.items():
        if pattern in model_identifier.lower():
            return ctx

    return None


def _resolve_num_parallel(model_identifier: str, sample_size: int,
                          cli_override: int | None) -> int:
    """Determine num_parallel for a model benchmark run.

    Resolution order:
      1. Explicit CLI ``--num-parallel N`` (N > 0) → use N
      2. SampleSize >= 20 → force 4 for all models (batching benefit)
      3. Registry value (MoE/MTP → 4, Dense → 1)
      4. Fallback → 1
    """
    # 1. Explicit CLI override
    if cli_override is not None and cli_override > 0:
        return cli_override

    # 2. SampleSize >= 20 → force parallel for all models
    if sample_size >= 20:
        return 4

    # 3. Registry default (MoE/MTP → 4, Dense → 1)
    registry, rnorm = _load_registry_for_context()
    from assemble_blueprint import normalize_model_name
    normalized_key = normalize_model_name(model_identifier)
    if normalized_key in rnorm:
        entry = registry[rnorm[normalized_key]]
        np_val = entry.get("num_parallel")
        if np_val is not None:
            return int(np_val)

    # 4. Fallback
    return 1


def _model_family(model_identifier: str) -> str:
    """Extract model family (without publisher prefix) for deduplication."""
    return model_identifier.replace("\\", "/").split("/")[-1].lower()

def resolve_models(available_models: list[dict[str, Any]], model_arg: str | None) -> list[dict[str, Any]] | None:
    # Code-Review 2026-07-18 §4.1: EXCLUDE_KEYWORDS filtering is already
    # done in get_available_models(); doing it again here would be
    # redundant and drift-prone.
    filtered = available_models
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


def resolve_benchmarks(bench_arg: str | None) -> list[dict[str, Any]] | None:
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


def select_models_interactive(available_models: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    # Code-Review 2026-07-18 §4.1: filtering already applied upstream.
    filtered = available_models
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


def select_benchmarks_interactive() -> list[dict[str, Any]] | None:
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


# Global: Thinking mode for reasoning models (all pipelines)
# Code-Review 2026-07-18 §6.3: This is a module-level global, set once
# in main() via args.thinking. It is NOT thread-safe (no Lock), but
# the current launcher runs strictly single-threaded (one model at a
# time, sequential benchmark calls), so it is safe in practice. If
# parallel benchmarking is added, wrap mutations with a threading.Lock.
IS_THINKING_ENABLED = False

def _derive_category(bench_name: str) -> str:
    """Map a benchmark name to its config category ("coding", "math", ...)."""
    bench_name_lower = (bench_name or "").lower()
    categories = {"coding": {"ds1000", "codereval", "humaneval", "mbpp"},
                  "math": {"math-500", "math"},
                  "knowledge": {"arc", "hellaswag", "truthfulqa"},
                  "agentic": {"ifeval", "agentic"}}
    for cat, keywords in categories.items():
        if any(kw in bench_name_lower for kw in keywords):
            return cat
    return "coding"


def _evaluation_summary(model_identifier: str, category: str) -> str:
    """Human-readable summary of the effective generation config (Punkt 1).

    Shows temp/top_p/top_k/min_p/max_tokens/thinking and the source
    ("benchmark-table" = MODEL_CATEGORY_SAMPLING-Ausnahme, "category-default" =
    Instruct-Fallback, "thinking-default" = Thinking-Fallback im --thinking-Lauf).
    """
    cfg = get_model_config(model_identifier, category=category, is_thinking_enabled=IS_THINKING_ENABLED)
    parts = [f"temp={cfg.get('temperature')}", f"top_p={cfg.get('top_p')}",
             f"max_tokens={cfg.get('max_tokens')}", f"thinking={cfg.get('enable_thinking')}"]
    if cfg.get("top_k") is not None:
        parts.append(f"top_k={cfg['top_k']}")
    if cfg.get("min_p") is not None:
        parts.append(f"min_p={cfg['min_p']}")
    if cfg.get("reasoning_effort") is not None:
        parts.append(f"reasoning_effort={cfg['reasoning_effort']}")
    src = cfg.get("_source", "?")
    return f"[CFG] {', '.join(parts)} (Quelle: {src})"


def _get_evaluation_parameters(model_identifier: str, bench_name: str = "") -> dict[str, Any]:
    """Returns LM-Eval parameters from benchmark_config.get_model_config().

    Derives benchmark category from bench_name, then calls get_model_config()
    (Sampling-Design 2026-08-06: MODEL_CATEGORY_SAMPLING > Kategorie-Defaults;
    aus der LMS-JSON-Config nur Nicht-Temperatur-Felder).
    MODEL_TEMP_OVERRIDES / Registry-Thinking / Knowledge-Floor sind entfernt.

    Returned keys are split by the caller into --model_args (constructor) and
    --generation_parameters (generation kwargs). See run_lmeval() for the split logic.
    """
    # Derive category from benchmark name
    category = _derive_category(bench_name)

    # Get merged config
    config = get_model_config(model_identifier, category=category, is_thinking_enabled=IS_THINKING_ENABLED)

    # Convert to lm_eval format (extra_body wrapping)
    generation_parameters = {
        "temperature": config.get("temperature", 0.0),
        "top_p": config.get("top_p", 1.0),
        "max_tokens": config.get("max_tokens", 4096),
    }
    if config.get("top_k") is not None:
        generation_parameters["top_k"] = config["top_k"]
    if config.get("min_p") is not None:
        generation_parameters["min_p"] = config["min_p"]
    if config.get("stop"):
        generation_parameters["until"] = config["stop"]

    # ── chat_template_kwargs for enable_thinking / reasoning_effort ──
    #
    # WICHTIG: chat_template_kwargs ist KEIN OpenAI-Standard-Parameter.
    #   Er wird NUR von Qwen-Templates unterstuetzt (Qwen3, Qwen3.5 und
    #   Qwen-basierte Distills wie deepseek-r1-distill-qwen-14b).
    #   Quelle: https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1573
    #   enable_thinking=True fuer Registry-Thinking-Modelle kommt via
    #   get_model_config() aus der Registry (reasoning: thinking).
    #
    # 2026-08-02: gpt-oss-Override (reasoning_effort/max_thinking_tokens)
    #   entfernt; Reasoning-Budget wird in LM Studio GUI per Modell gesetzt.
    #
    if not _is_gptoss_model(model_identifier):
        ctw = {}
        if config.get("enable_thinking") is not None:
            ctw["enable_thinking"] = config["enable_thinking"]
        if config.get("reasoning_effort") is not None:
            ctw["reasoning_effort"] = config["reasoning_effort"]
        if ctw:
            generation_parameters["chat_template_kwargs"] = ctw

    return generation_parameters


def _build_lmeval_cmd(model_identifier: str, api_model: str, subset_task: str, per_limit: int, output_dir: str, bench_name: str = "", num_parallel: int = 1) -> list[str]:
    """Like run_lmeval(), but returns the cmd list instead of executing it.
    
    Used by run_agentic() for per-scenario lm_eval invocations.
    Mirrors the same --model_args / --generation_parameters split as run_lmeval().
    """
    gptoss = _is_gptoss_model(model_identifier)
    evaluation_parameters = _get_evaluation_parameters(model_identifier, bench_name=bench_name)
    model_settings = {
        "base_url": f"{API_BASE}/chat/completions",
        "model": api_model,
        "num_concurrent": num_parallel,
    }
    # eos_string only for GPT-OSS; other models use YAML until sequences or generation_parameters
    # (except tasks without until, e.g. IFEval: GGUF-EOS fallback, see run_lmeval)
    if gptoss and "until" not in evaluation_parameters:
        model_settings["eos_string"] = "<|endoftext|>"
    elif _lmeval_needs_eos_string(subset_task, evaluation_parameters):
        eos_str = _get_model_eos_string(model_identifier)
        if eos_str:
            model_settings["eos_string"] = eos_str
    # Generation params go to --generation_parameters (overrides YAML generation_parameters via merge)
    generation_parameters_keys = {"max_tokens", "temperature", "top_p", "top_k", "min_p",
                       "until", "chat_template_kwargs", "reasoning", "reasoning_effort", "max_thinking_tokens"}
    generation_parameters = {k: v for k, v in evaluation_parameters.items()
                  if k in generation_parameters_keys and v is not None}
    model_args = json.dumps(model_settings, ensure_ascii=False)
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
    if generation_parameters:
        cmd.extend(["--gen_kwargs", json.dumps(generation_parameters, ensure_ascii=False)])
    return cmd


def _parse_subset_score(sub_output_dir: str, subset_task: str) -> float | None:
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
# Starts custom_benchmark.py as subprocess.
# This script reads JSONL files from simple_evals/, queries the
# model via LM-Studio-REST-API and evaluates code execution
# in a sandbox (exec_sandboxed).
#
# IMPORTANT: This call passes --api-model as the exact load ID
# from lms ps --json. custom_benchmark.py uses this ID for all
# API calls. On mismatch, LM Studio responds with HTTP 400.
#
# Qwen3.5 compatibility: --qwen-prompt enables prompt-based
# embedding instead of system message (no_system_msg in MODEL_CONFIG).
#


def _ensure_model_still_loaded(model_identifier: str, model_load_key: str, bench_name: str = "") -> None:
    """After EVERY benchmark (Custom/EvalPlus/LM-Eval/Agentic) verify the
    model is still loaded. If not, transparently reload it. This avoids
    silent crashes when a sub-process accidentally unloads the model.
    """
    candidate_key = model_identifier.lower()
    loaded = get_current_loaded_model()
    is_ok = False
    if loaded:
        lk = loaded["model_identifier"].lower()
        li = loaded["identifier"].lower()
        if candidate_key in lk or candidate_key in li or lk in candidate_key or li in candidate_key:
            is_ok = True
    if not is_ok:
        label = f" after {bench_name}" if bench_name else ""
        print(f"  [WARN] Model{label} no longer loaded - reloading...")
        load_model_via_lms(model_load_key)
        if not is_model_ready(timeout=60):
            print("  [WARN] Model readiness check timed out")


# Returns: dict with pipeline="custom", score (0-1).
def run_custom_benchmark(model_info: AvailableModelInfo, bench: BenchmarkDef, sample_size: int = 5, seed: int | None = None, is_structured_output_disabled: bool = False, should_keep_response: bool = False, num_parallel: int = 1) -> PipelineResult | None:
    model_identifier = model_info["key"]
    model_display = model_info["display"]
    fp = os.path.join(DATA_DIR, bench["file"])
    if not os.path.exists(fp):
        print(f"  [WARN] Missing: {fp}")
        return None
    print(f"\n{'=' * 60}\n  >>> Custom: {bench['name']} / {model_display}")
    api_model = model_info.get("_api_model") or model_identifier
    cmd = [
        sys.executable, CUSTOM_BENCHMARK_SCRIPT,
        "--non-interactive",
        "--model-key", model_identifier,
        "--api-model", api_model,
        "--sample-size", str(sample_size),
        "--benchmark", bench["name"],
    ]
    if num_parallel > 1:
        cmd.extend(["--num-parallel", str(num_parallel)])
    if seed is not None:
        cmd.extend(["--seed", str(seed)])
    # Qwen3.5 compatibility: enable systemless prompt embedding
    if _is_qwen3_5_model(model_identifier):
        cmd.append("--qwen-prompt")
    # Thinking mode only when --thinking flag is set (math default now False).
    # Gemma models are excluded from the --thinking flag: they get
    # enable_thinking=True via the registry (reasoning: thinking) already.
    if IS_THINKING_ENABLED and _is_reasoning_model(model_identifier) and not _is_gemma_model(model_identifier):
        cmd.append("--thinking")
    # Pre-emptive --no-structured-output for reasoning and Mamba models
    # (structured output grammar constraints break thinking tokens / SSM architectures)
    if _is_reasoning_model(model_identifier) or _is_mamba_model(model_identifier):
        cmd.append("--no-structured-output")
        is_structured_output_disabled = True
    # Fallback: retry with --no-structured-output on channel error (see below)
    if is_structured_output_disabled and "--no-structured-output" not in cmd:
        cmd.append("--no-structured-output")
    if should_keep_response:
        cmd.append("--keep-response")
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=PIPELINE_TIMEOUTS["custom_subprocess"],
                            encoding="utf-8", errors="replace")
    elapsed = time.time() - t0
    # Print full subprocess output. Truncation would slice mid-line and
    # corrupt the header (e.g. "Subsampling:" -> "pling:"), so only trim
    # very long outputs and always keep head (banner) + tail (score).
    full_output = result.stdout or ""
    if len(full_output) > 12000:
        output = full_output[:800] + "\n  ...[output truncated]...\n" + full_output[-12000:]
    else:
        output = full_output
    stderr_text = result.stderr or ""
    if output.strip():
        print(output)
    # Channel-Error Auto-Fallback: if the subprozess reports a LM Studio
    # Channel-Error (structured-output + lazy-grammar conflict, see Server-Log
    # 12.07.2026 L58671/L94468), transparently retry once with
    # --no-structured-output instead of returning a 0% score.
    # Detection via the [CHANNEL-ERROR] marker printed by the subprozess
    # when error_detail contains "Cannot combine structured output" /
    # "Channel Error" (see custom_benchmark.py run benchmark loop).
    if not is_structured_output_disabled and "[CHANNEL-ERROR]" in (result.stdout or ""):
        print("  [INFO] Channel-Error detected - retrying with --no-structured-output")
        return run_custom_benchmark(model_info, bench, sample_size=sample_size,
                                   seed=seed, is_structured_output_disabled=True,
                                   should_keep_response=should_keep_response, num_parallel=num_parallel)
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
            "score": score, "thinking": IS_THINKING_ENABLED}


# ── Pipeline 2/4: EvalPlus (HumanEval+, MBPP+) ────────────────
# Two-stage process:
#   1. Random sampling: sample_size tasks with seed (via evalplus API)
#   2. evalplus.codegen via direct API call (filtered to selected tasks)
#   3. evalplus.evaluate -> differential testing with plus_input
# Uses evalplus-native datasets (humanEval, mbpp).
# Returns: dict with pipeline="evalplus", score pass@1 (0-1).
def run_evalplus(model_info: AvailableModelInfo, bench: BenchmarkDef, sample_size: int = 5, seed: int | None = None, is_reasoning_model: bool = False, num_parallel: int = 1) -> PipelineResult | None:
    # Some models (e.g. DeepSeek Coder) generate regex patterns like "\d+"
    # instead of r"\d+", causing SyntaxWarning spam from Python 3.12+.
    warnings.filterwarnings("ignore", category=SyntaxWarning)

    model_identifier = model_info["key"]
    model_display = model_info["display"]
    dataset = bench["dataset"]
    print(f"\n  >>> EvalPlus: {bench['name']} / {model_display}")
    root_dir = os.path.join(RESULTS_DIR, f"evalplus_{model_identifier.replace('/', '_')}")
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
    from evalplus.codegen import codegen as evalplus_codegen
    from evalplus.provider import make_model

    # Sentinel name required by evalplus; the actual model ID is sent
    # via the OpenAI-compatible request (Code-Review 2026-07-18 §5.3).
    # Temperatur kommt seit 2026-08-05 aus der LMS-JSON-Config (einzige
    # Quelle, Punkte 3+4) statt hardcoded 0.0/0.7.
    evaluation_parameters = _get_evaluation_parameters(model_identifier, bench_name=dataset)
    max_tokens = evaluation_parameters.get("max_tokens", 4096)
    gen_temp = float(evaluation_parameters.get("temperature", 0.0))
    print(f"  {_evaluation_summary(model_identifier, _derive_category(dataset))}")
    model_obj = make_model(
        model=EVALPLUS_SENTINEL_MODEL,
        backend="openai",
        dataset=dataset,
        base_url=API_BASE,
        temperature=gen_temp,
        instruction_prefix="Please provide a self-contained Python script that solves the following problem in a markdown code block:",
        response_prefix="Below is a Python script with a self-contained function that solves the problem and passes corresponding tests:",
        max_new_tokens=max_tokens,
    )

    temp_str = f"{gen_temp:g}"
    out_dir = os.path.join(root_dir, dataset)
    os.makedirs(out_dir, exist_ok=True)

    # Delete old .jsonl/.raw.jsonl to prevent accumulation across runs
    import glob as _glob
    for old_f in _glob.glob(os.path.join(out_dir, "*.jsonl")):
        try:
            os.remove(old_f)
        except OSError as e:
            print(f"  [WARN] alte sample-Datei nicht loeschbar: {old_f}: {e}", file=sys.stderr)

    samples_path = os.path.join(out_dir, f"local-model_openai_temp_{temp_str}.jsonl")

    limit_scale = max(1.0, n_select / 5.0)
    eval_base = PIPELINE_TIMEOUTS["evalplus_base"]
    eval_timeout = (eval_base * 2 if is_reasoning_model else eval_base) * limit_scale

    import io
    from concurrent.futures import ThreadPoolExecutor
    from concurrent.futures import TimeoutError as _FUTimeout
    from contextlib import redirect_stdout

    from evalplus.codegen import sanitize as _evalplus_sanitize
    _total_tasks = len(filtered_tasks)
    # Progress live via StringIO-Polling (Punkt 2b): evalplus schreibt die
    # Samples-Datei inkrementell, aber der Datei-Polling-Ansatz zeigte den
    # Balken erst nach Abschluss. Stattdessen zaehlen wir die per-Task-Zeilen
    # ("Codegen: <task_id> @ ...") direkt im redirect-Puffer.
    codegen_buf = io.StringIO()

    # Parallel codegen (Fix 05.08.): evalplus' codegen() iteriert SEQUENZIELL
    # ueber die Tasks (ein HTTP-Request pro Task) - dadurch wird bei
    # num_parallel > 1 trotz n_slots=4 nur 1 Slot belegt (Server-Log-Beweis:
    # alle Requests auf Slot 3). Wir replizieren die per-Task-Logik
    # (n_samples=1, resume=False, identisches JSONL-Format) in einem
    # ThreadPoolExecutor mit max_workers=num_parallel, damit LM Studio
    # mehrere Slots parallel nutzt.
    raw_target_path = samples_path.replace(".jsonl", ".raw.jsonl")
    _write_lock = threading.Lock()

    def _gen_one_task(task_id: str, task: dict) -> None:
        prompt = task["prompt"].strip() + "\n"
        outputs = model_obj.codegen(  # noqa: F821 - closure variable from enclosing scope
            prompt,
            do_sample=gen_temp != 0.0,
            num_samples=1,
        )
        assert outputs, f"No outputs from model for {task_id}"
        impl = outputs[0]
        solution = prompt + impl if model_obj.is_direct_completion() else impl  # noqa: F821 - closure variable from enclosing scope
        sanitized_solution = _evalplus_sanitize(solution, entrypoint=task["entry_point"])
        print(f"Codegen: {task_id} @ {model_obj}")  # noqa: F821 - closure variable from enclosing scope
        with _write_lock:
            with open(samples_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"task_id": task_id, "solution": sanitized_solution}) + "\n")
            with open(raw_target_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"task_id": task_id, "solution": solution}) + "\n")

    def _codegen_wrapper() -> None:
        with redirect_stdout(codegen_buf):
            if num_parallel > 1:
                with ThreadPoolExecutor(max_workers=num_parallel,
                                        thread_name_prefix="evalplus") as pool:
                    futures = [
                        pool.submit(_gen_one_task, tid, task)
                        for tid, task in filtered_tasks.items()
                    ]
                    for fut in futures:
                        fut.result()
            else:
                evalplus_codegen(
                    target_path=samples_path,
                    model=model_obj,  # noqa: F821 - closure variable from enclosing scope
                    dataset=filtered_tasks,
                    greedy=gen_temp == 0.0,
                    n_samples=1,
                    resume=False,
                )
    def _codegen_progress() -> None:
        import sys as _sys
        dots_printed = [0]
        while dots_printed[0] < _total_tasks:
            time.sleep(2)
            done = codegen_buf.getvalue().count("Codegen: ")
            if done > dots_printed[0]:
                print(f"  [{'.' * done}{' ' * (_total_tasks - done)}] {done}/{_total_tasks}", end="\r")
                _sys.stdout.flush()
                dots_printed[0] = done
    progress_thread = threading.Thread(target=_codegen_progress, daemon=True)
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_codegen_wrapper)
    progress_thread.start()
    try:
        future.result(timeout=eval_timeout)
        # Finaler Zustand auch dann rendern, wenn der Thread noch schlief
        done = codegen_buf.getvalue().count("Codegen: ")
        if done >= _total_tasks:
            print(f"  [{'.' * _total_tasks}] {_total_tasks}/{_total_tasks}")
        print(f"  [OK] codegen finished ({len(filtered_tasks)} tasks)")
    except _FUTimeout:
        print(f"  [ERROR] codegen timed out after {eval_timeout:.0f}s")
        executor.shutdown(wait=False)
        return None
    except (subprocess.SubprocessError, OSError, ValueError, TypeError, json.JSONDecodeError) as e:
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
        except OSError as e:
            print(f"  [WARN] alte eval_results-Datei nicht loeschbar: {old_result}: {e}", file=sys.stderr)

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
    eval_out = "\n".join(line for line in eval_out.split("\n") if "Skipping" not in line and "WARNING" not in line)
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
            "samples": samples_path, "score": score, "thinking": IS_THINKING_ENABLED}


# ── Pipeline 3/4: LM-Eval (ARC, HellaSwag, TruthfulQA, MATH-500, BBH) ─
# Uses lm_eval --model local-chat-completions as subprocess.
# For MMLU-Pro there is a separate modified function (see below),
# which stratifies the benchmark across 14 subset tasks.
# Returns: dict with pipeline="lmeval", score (0-1).
def run_lmeval(model_info: AvailableModelInfo, bench: BenchmarkDef, limit: int = 5, is_reasoning_model: bool = False, num_parallel: int = 1) -> PipelineResult | None:
    model_identifier = model_info["key"]
    model_display = model_info["display"]
    gptoss = _is_gptoss_model(model_identifier)
    # Use exact load ID from lms ps, fallback variant, fallback key
    api_model = model_info.get("_api_model") or model_info.get("variant") or model_identifier
    task_name = bench["task"]
    safe = model_identifier.replace("/", "_").replace("\\", "_")
    output_dir = os.path.join(RESULTS_DIR, f"lmeval_{safe}")
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n  >>> LM-Eval: {bench['name']} / {model_display}")
    t0 = time.time()
    evaluation_parameters = _get_evaluation_parameters(model_identifier, bench_name=bench["name"])
    #
    # Split params: constructor-level (--model_args) vs. generation-level (--generation_parameters).
    #
    # model_args is consumed by LocalChatCompletion.__init__(**kwargs).
    #   Keys like base_url, model, num_concurrent, eos_string
    #   are constructor params. All other params in evaluation_parameters are silently
    #   dropped by the constructor (openai_completions.py:158 **kwargs).
    #
    # generation_parameters is merged by the evaluator into the YAML task's generation_kwargs
    #   (evaluator.py:311: task_obj.set_config(update=True)), and then passed
    #   as generation_parameters to _create_payload(). The remaining **generation_parameters are
    #   spread into the API payload dict (openai_completions.py:206).
    #
    # IMPORTANT: The model parameter MUST correspond to the exact load ID from lms ps,
    #           otherwise LM Studio responds with HTTP 400 "model not found".
    #           A test with "model=check" (invalid name) causes the request to HANG
    #           (no timeout, no error response) - therefore ALWAYS use api_model.
    # Use proxy only when explicitly started (e.g. for custom base_url routing)
    use_proxy = _proxy_is_running()
    lm_base_url = f"http://127.0.0.1:{LMEVAL_PROXY_PORT}/v1/chat/completions" if use_proxy else f"{API_BASE}/chat/completions"
    model_settings = {
        "base_url": lm_base_url,
        "model": api_model,
        "num_concurrent": num_parallel,
    }
    # Only set eos_string for models that explicitly need a fixed EOS token.
    # GPT-OSS uses <|endoftext|> as its primary stop; other chat models rely on
    # the YAML's until sequences ("\n\n", "Question:") or explicit generation_parameters.
    # Tasks WITHOUT an until sequence (e.g. IFEval: `until: []`) get the model's
    # GGUF EOS token as stop. Otherwise low-quant models generate freely and
    # violate the chat template format -> HTTP 500 "peg-native format"
    # (llama.cpp #20260, observed with Jamba2 Mini@IQ2_XXS).
    if gptoss and "until" not in evaluation_parameters:
        model_settings["eos_string"] = "<|endoftext|>"
    elif _lmeval_needs_eos_string(task_name, evaluation_parameters):
        eos_str = _get_model_eos_string(model_identifier)
        if eos_str:
            model_settings["eos_string"] = eos_str
            print(f"  [CFG] eos_string={eos_str!r} (Task {task_name} hat keine until-Stops)")
    # Gen_kwargs keys that should override YAML generation_kwargs per request.
    generation_parameters_keys = {"max_tokens", "temperature", "top_p", "top_k", "min_p",
                       "until", "chat_template_kwargs", "reasoning", "reasoning_effort", "max_thinking_tokens"}
    generation_parameters = {k: v for k, v in evaluation_parameters.items()
                  if k in generation_parameters_keys and v is not None}
    print(f"  {_evaluation_summary(model_identifier, _derive_category(bench['name']))}")
    model_args = json.dumps(model_settings, ensure_ascii=False)
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
    if generation_parameters:
        cmd.extend(["--gen_kwargs", json.dumps(generation_parameters, ensure_ascii=False)])
    # Prio: custom YAML überschreibt built-in (inkl. MATH-500 V2.0 statt V3.0)
    yaml_path = None
    for p in [os.path.join(LMEVAL_TASKS_DIR, f"{task_name}.yaml"),
              os.path.join(LMEVAL_TASKS_DIR, task_name, f"{task_name}.yaml")]:
        if os.path.exists(p):
            yaml_path = p
            break
    if yaml_path:
        print(f"  [CFG] Custom task YAML: {yaml_path}")
        cmd.extend(["--include_path", os.path.dirname(yaml_path)])

    lm_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    limit_scale = max(1.0, limit / 5.0)
    lmeval_base = PIPELINE_TIMEOUTS["lmeval_base"]
    base_timeout = (lmeval_base * 2 if is_reasoning_model else lmeval_base) * limit_scale
    timeout_mult = bench.get("timeout_mult", 1)
    total_timeout = base_timeout * timeout_mult
    elapsed = 0
    stderr = ""
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace", env=lm_env)
        stdout_lines = []
        stderr_lines = []
        def _stream_stdout() -> None:
            import re as _re
            progress_re = _re.compile(r"(\d+)/(\d+)")
            last_bar_len = [0]
            for line in iter(proc.stdout.readline, ""):
                stdout_lines.append(line)
                m = progress_re.search(line)
                if m:
                    done, total = int(m.group(1)), int(m.group(2))
                    bar_w = min(total, 50)
                    filled = int(bar_w * done / total) if total > 0 else 0
                    bar = "#" * filled + "." * (bar_w - filled)
                    progress_str = f"  [{bar}] {done}/{total}"
                    pad = " " * max(0, last_bar_len[0] - len(progress_str))
                    print(f"\r{progress_str}{pad}", end="", flush=True)
                    last_bar_len[0] = len(progress_str)
                    if done >= total:
                        print()
                else:
                    stripped = line.rstrip()
                    if stripped:
                        print(f"  {stripped}")
        def _collect_stderr() -> None:
            for line in iter(proc.stderr.readline, ""):
                stderr_lines.append(line)  # noqa: PERF402 - false positive: kein list-Copy-Muster
        tout = threading.Thread(target=_stream_stdout, daemon=True)
        terr = threading.Thread(target=_collect_stderr, daemon=True)
        tout.start()
        terr.start()
        proc.wait(timeout=total_timeout)
        tout.join(timeout=2)
        terr.join(timeout=2)
        stderr = "".join(stderr_lines)
        elapsed = time.time() - t0
        if proc.returncode != 0:
            print(f"  [WARN] lm_eval returncode={proc.returncode}")
            if stderr:
                if "peg-native" in stderr or "does not match the expected peg" in stderr:
                    print("  [WARN] Bekannter Engine-Fehler (llama.cpp #20260): "
                          "post-generation PEG-Parser lehnt Modellausgabe ab "
                          "(HTTP 500 'peg-native format').")
                    print("  [WARN] Dieser Lauf hat keine eos_string-Stops an die Engine gesendet "
                          "(Task-YAML ohne 'until'); der GGUF-EOS-Fallback greift ab "
                          "dem nächsten Start automatisch.")
                    print(f"  [WARN] stderr-Kurzfassung ({len(stderr)} chars total):")
                    for line in stderr.split("\n")[:12]:
                        print(f"    | {line}")
                else:
                    print(f"  [WARN] lm_eval stderr ({len(stderr)} chars):")
                    for line in stderr.split("\n"):
                        print(f"    | {line}")
        else:
            print(f"  [OK] {bench['name']} done ({elapsed:.0f}s)")
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        elapsed = time.time() - t0
        print(f"  [WARN] {bench['name']} TIMEOUT after {elapsed:.0f}s")
    except (subprocess.SubprocessError, OSError, ValueError, KeyError) as e:
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
                with open(os.path.join(sdir, fname), encoding="utf-8") as f:
                    data = json.load(f)
                task_data = data.get("results", {}).get(task_name, {})
                if task_data:
                    for metric in ["exact_match,custom-extract",
                                "bleu_acc,none", "rouge1_acc,none",
                               "exact_match,remove_whitespace",
                               "exact_match,none", "math_verify,none",
                               "inst_level_loose_acc,none",
                               "inst_level_strict_acc,none",
                               "prompt_level_loose_acc,none",
                               "prompt_level_strict_acc,none"]:
                        if metric in task_data:
                            score = task_data[metric]
                            break
                if score is not None:
                    break
            if score is not None:
                break
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"  [WARN] lm_eval score parsing: {e}")

    return {"pipeline": "lmeval", "bench": bench["name"], "category": bench.get("category", ""),
            "model": model_display,
            "score": score, "thinking": IS_THINKING_ENABLED}


# ── MMLU-Pro (ARCHIVIERT 12.07.2026) ──
# Die spezielle MMLU-Pro-Auswertung wurde aus Performance-Gründen
# (12,032 Tasks x ~25s/call = >50h pro Modell auf 16-GB-VRAM) aus
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
def run_agentic(model_info: AvailableModelInfo, limit: int = 5, mode: str = "random",
                seed: int | None = None) -> PipelineResult | None:
    """Agentic: tool-eval-bench with sample_size scenarios.

    mode:
      - "random"   -> Zufallsauswahl aus allen 69 Szenarien (bisheriges Verhalten)
      - "safety"   -> NUR die 13 Category-K-Szenarien (Safety & Boundaries)
    seed: reproduzierbare Auswahl (überall deterministisch, auch bei safety).
    """
    if mode not in ("random", "safety"):
        mode = "random"
        print(f"      [WARN] Unknown agentic mode '{mode}' -> 'random'")
    all_ids = AGENTIC_SAFETY_SCENARIO_IDS if mode == "safety" else TOOL_EVAL_SCENARIO_IDS
    rng = random.Random(seed)
    selected = rng.sample(all_ids, min(limit, len(all_ids)))

    model_identifier = model_info["key"]
    model_display = model_info["display"]
    safe = model_identifier.replace("/", "_").replace("\\", "_")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(RESULTS_DIR, f"agentic_{safe}")
    os.makedirs(output_dir, exist_ok=True)
    json_path = os.path.join(output_dir, f"agentic_{safe}_{ts}.json")

    print(f"\n  {green('>>>')} Agentic ({cyan('tool-eval-bench')}): {model_display}")
    label = "safety (Category K)" if mode == "safety" else "randomly"
    print(f"      Scenarios: {len(selected)}/{len(all_ids)} {label} selected")

    t0 = time.time()
    agentic_runner = os.path.join(SRC_DIR, "tools", "tool_eval_bench_runner.py")
    cmd = [
        sys.executable, agentic_runner,
        "--base-url", API_BASE,
        "--scenarios", *selected,
        "--json-file", json_path,
        "--timeout", str(PIPELINE_TIMEOUTS["agentic_scenario"]),
        "--no-live",
    ]

    scenario_timeout = PIPELINE_TIMEOUTS["agentic_scenario"]
    total_timeout = limit * scenario_timeout + 600  # 10 min buffer
    lm_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    score = None
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding="utf-8", errors="replace", env=lm_env
        )

        def _stream_stdout(out_list: list[str]) -> None:
            if proc.stdout is None:
                return
            for line in iter(proc.stdout.readline, ""):
                out_list.append(line)
                stripped = line.rstrip("\n\r")
                if stripped:
                    m = re.search(r"Scenario\s+(\S+)\s+-\s+score:\s*([\d.]+)", stripped)
                    if m:
                        scenario = m.group(1)
                        done = sum(1 for line in out_list if "score:" in line)
                        progress_bar(done, limit, prefix=f"  {cyan(scenario)}")
                    else:
                        print(f"    {stripped}")

        def _collect_stderr(err_list: list[str]) -> None:
            if proc.stderr is None:
                return
            for line in iter(proc.stderr.readline, ""):
                err_list.append(line)  # noqa: PERF402 - false positive: kein list-Copy-Muster

        tout = threading.Thread(target=_stream_stdout, args=(stdout_lines,), daemon=True)
        terr = threading.Thread(target=_collect_stderr, args=(stderr_lines,), daemon=True)
        tout.start()
        terr.start()
        tout.join(timeout=total_timeout)
        proc.wait(timeout=max(total_timeout - 10, 10))
        terr.join(timeout=5)

        elapsed = time.time() - t0
        if proc.returncode == 0:
            ok(f"Agentic done ({elapsed:.0f}s)")
        else:
            warn(f"tool-eval-bench returncode={proc.returncode}")
            if stderr_lines:
                for line in stderr_lines[-5:]:
                    print(f"    | {line.rstrip()}")

        # Parse JSON result - tool-eval-bench envelope format
        if os.path.exists(json_path):
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
            raw = data.get("final_score") if isinstance(data, dict) else None
            if raw is not None:
                score = raw / 100.0
            else:
                scores_meta = data.get("scores", {}) if isinstance(data, dict) else {}
                results = scores_meta.get("scenario_results", [])
                if results:
                    vals = [s.get("score", 0) for s in results if isinstance(s, dict)]
                    score = sum(vals) / len(vals) if vals else None
    except subprocess.TimeoutExpired:
        proc.kill()
        elapsed = time.time() - t0
        warn(f"Agentic TIMEOUT after {elapsed:.0f}s (limit {total_timeout}s)")
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError, KeyError, ValueError) as e:
        elapsed = time.time() - t0
        warn(f"Agentic ERROR: {e}")

    return {"pipeline": "agentic", "bench": "Agentic", "category": "agentic",
            "model": model_display,
            "score": score, "thinking": IS_THINKING_ENABLED}


def save_summary_csv(results: list[dict[str, Any]], model_info: dict[str, Any] | None = None,
                     sample_size: int = 5, seed: str = "", exclude_benchmarks: str = "",
                     no_structured_output: str = "", no_unload_between: str = "") -> Any:
    """Legacy - forwards to csv_writer."""
    return csv_writer.write_accumulative_summary(
        results, model_info or {},
        sample_size=sample_size, seed=seed, exclude_benchmarks=exclude_benchmarks,
        no_structured_output=no_structured_output, no_unload_between=no_unload_between,
        base_dir=PROJECT_ROOT,
    )


# NOTE: Legacy save_model_summary_csv wurde am 12.07.2026 entfernt
# (Code-Review_2026-07-12.md §3.1 D5). Direkt
# csv_writer.write_accumulative_summary(...) nutzen.


# ── Run-Spec (YAML) Support ─────────────────────────────────
# P3: Reproduzierbare Runs über --run-spec/config <datei.yaml>.
# Precedence: CLI-Flags > YAML-Werte > Skript-Defaults.

# YAML-Schlüssel -> CLI-Dest. Mehrere Aliase erlaubt (kebab/snake).
RUN_SPEC_DEST_MAP = {
    "sample_size": "sample_size", "sample-size": "sample_size",
    "model": "model", "models": "model",
    "benchmark": "benchmarks", "benchmarks": "benchmarks",
    "seed": "seed",
    "thinking": "thinking",
    "agentic_mode": "agentic_mode", "agentic-mode": "agentic_mode",
    "exclude_benchmarks": "exclude_benchmarks", "exclude-benchmarks": "exclude_benchmarks",
    "no_structured_output": "no_structured_output", "no-structured-output": "no_structured_output",
    "unload_between": "unload_between", "unload-between": "unload_between",
    "keep_response": "keep_response", "keep-response": "keep_response",
}

# YAML-Schlüssel, die Listen erlauben (Liste -> Komma-String).
_RUN_SPEC_CSV_KEYS = {"model", "models", "benchmark", "benchmarks",
                      "exclude_benchmarks", "exclude-benchmarks"}
# YAML-Schlüssel, die als Boolean erwartet werden.
_RUN_SPEC_BOOL_KEYS = {"thinking", "unload_between", "unload-between",
                       "no_structured_output", "no-structured-output",
                       "keep_response", "keep-response"}

# CLI-Defaults je Dest - für Precedence-Check (CLI explizit > YAML).
RUN_SPEC_PARSER_DEFAULTS: dict[str, Any] = {
    "sample_size": 5, "model": None, "benchmarks": None, "seed": None,
    "thinking": False, "agentic_mode": "random", "exclude_benchmarks": None,
    "no_structured_output": False, "unload_between": False, "keep_response": False,
    "num_parallel": None,
}


def _normalize_available_keys(available: list[dict[str, Any]]) -> set[str]:
    return {m.get("key", "").lower() for m in available} | {m.get("display", "").lower() for m in available}


def _load_run_spec(path: str) -> dict[str, Any]:
    """Run-Spec-YAML lesen + validieren. Unbekanntes -> Warn + igonrieren, fatale Fehler -> exit(1)."""
    if not os.path.isfile(path):
        print(f"[ERROR] Run-Spec-Datei nicht gefunden: {path}")
        sys.exit(1)
    yaml_lib = _run_spec_yaml()
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml_lib.safe_load(fh)
    except yaml_lib.YAMLError as e:
        print(f"[ERROR] Run-Spec-YAML-Fehler: {e}")
        sys.exit(1)

    if data is None:
        data = {}
    if not isinstance(data, dict):
        print(f"[ERROR] Run-Spec muss ein Mapping (top-level dict) sein, bekam: {type(data).__name__}")
        sys.exit(1)

    known = set(RUN_SPEC_DEST_MAP)
    for key in sorted(set(data) - known):
        print(f"  [WARN] Run-Spec: unbekannter Schlüssel '{key}' - wird ignoriert")

    spec: dict[str, Any] = {}
    for key, value in data.items():
        if key not in known:
            continue
        dest = RUN_SPEC_DEST_MAP[key]
        if key in _RUN_SPEC_CSV_KEYS and isinstance(value, list):
            value = ",".join(str(v).strip() for v in value if str(v).strip())
        if key in _RUN_SPEC_BOOL_KEYS:
            if not isinstance(value, bool):
                print(f"  [WARN] Run-Spec '{key}': erwartet bool, bekam {type(value).__name__} - ignoriert")
                continue
        spec[dest] = value

    # Semantische Validierung einzelner Felder
    if "sample_size" in spec:
        try:
            ss = int(spec["sample_size"])
            if ss <= 0:
                raise ValueError
            spec["sample_size"] = ss
        except (ValueError, TypeError):
            print("  [WARN] Run-Spec sample_size muss positive int sein - ignoriert")
            spec.pop("sample_size")
    if "seed" in spec:
        try:
            sd = int(spec["seed"])
            if sd <= 0:
                raise ValueError
            spec["seed"] = sd
        except (ValueError, TypeError):
            print("  [WARN] Run-Spec seed muss positive int sein - ignoriert")
            spec.pop("seed")
    if "agentic_mode" in spec and spec["agentic_mode"] not in ("random", "safety"):
        print("  [WARN] Run-Spec agentic_mode muss 'random'/'safety' sein - ignoriert")
        spec.pop("agentic_mode")

    return spec


def _validate_run_spec_selections(spec: dict[str, Any],
                                  available_models: list[dict[str, Any]]) -> dict[str, Any]:
    """Benchmark-/Modell-Namen aus der Run-Spec gegen bekannte Namen validieren (Warn bei Treffer-ern.Unbekannt)."""
    # Benchmarks
    if spec.get("benchmarks"):
        for n in [x.strip().lower() for x in spec["benchmarks"].split(",") if x.strip()]:
            if n in ALL_BENCH_NAMES or re.match(r"^[\d,\-]+$", n):
                continue
            print(f"  [WARN] Run-Spec: unbekannter Benchmark '{n}' (verwendbar: {', '.join(ALL_BENCH_NAMES)})")
    # Models (nur textbasiert; "all"/Nummern/Ranges -> skip)
    if spec.get("model") and available_models:
        known = _normalize_available_keys(available_models)
        for part in [p.strip() for p in str(spec["model"]).split(",") if p.strip()]:
            if part == "all" or re.match(r"^[\d,\-]+$", part) or part.lower() in known:
                continue
            print(f"  [WARN] Run-Spec: unbekanntes Modell '{part}'")
    return spec


def _apply_run_spec(args: Any, spec: dict[str, Any],
                    explicit_dests: set[str] | None = None) -> Any:
    """Rechne Run-Spec in das Namespace-Objekt ein.

    Precedence: CLI (explizit gesetzt) > YAML > Defaults.
    - explicit_dests: Menge der vom CLI explizit gesetzten Dest-Namen
      (via SUPPRESS-Probe-Parse). Wenn None (z.B. Unit-Tests), fällt
      eine Heuristik auf Basis RUN_SPEC_PARSER_DEFAULTS greift.
    """
    if not spec:
        return args
    for dest, value in spec.items():
        if dest not in RUN_SPEC_PARSER_DEFAULTS:
            continue
        if explicit_dests is not None:
            if dest in explicit_dests:
                continue
        elif getattr(args, dest, None) != RUN_SPEC_PARSER_DEFAULTS[dest]:
            continue
        setattr(args, dest, value)
    return args


def _run_spec_yaml() -> Any:
    """Lazy-Lazy-Import von PyYAML (nur nötig wenn --run-spec benutzt wird)."""
    try:
        import yaml
        return yaml
    except ImportError:
        print("[ERROR] PyYAML benötigt für --run-spec (pip install pyyaml).")
        sys.exit(1)


# ── main() Orchestrierungs-Helfer ──────────────────────────────

# Argument-Definitionen, geteilt zwischen Haupt- und Probe-Parser.
_LAUNCHER_ARG_SPECS: list[tuple[tuple[str, ...], dict[str, Any]]] = [
    (("--sample-size", "-s"), {"type": int, "default": 5,
                               "help": "Tasks per benchmark (default: 5)"}),
    (("--model", "-m"), {"type": str, "default": None,
                         "help": "Model selection: number(s) like '20', '1,3,5', '1-5', name or 'all'"}),
    (("--benchmarks", "-b"), {"type": str, "default": None,
                              "help": "Benchmark selection: number(s), name(s) or 'all'"}),
    (("--thinking",), {"action": "store_true",
                       "help": "Force-enable thinking mode for reasoning models on all pipelines (default: off)"}),
    (("--seed",), {"type": int, "default": None,
                   "help": "Random seed for reproducible task selection (passed to custom benchmarks)"}),
    (("--num-parallel",), {"type": int, "default": None,
                           "help": "Parallel worker threads for custom benchmarks (DS1000/CoderEval), "
                                   "uses LM Studio multi-slot serving. "
                                   "Auto: registry value (MoE/MTP=4, Dense=1); "
                                   "forced to 4 for all models when SampleSize >= 20. "
                                   "Explicit value overrides auto."}),
    (("--agentic-mode",), {"type": str, "default": "random", "choices": ["random", "safety"],
                           "help": "Agentic scenario selection: 'random' (all 69) or 'safety' (13 Category-K)"}),
    (("--exclude-benchmarks", "-x"), {"type": str, "default": None,
                                      "help": "Comma-separated benchmark names to exclude (e.g. 'MATH-500')"}),
    (("--no-structured-output",), {"action": "store_true",
                                   "help": "Disable structured JSON output in custom benchmarks (fallback to regex)"}),
    (("--unload-between",), {"action": "store_true",
                             "help": "Reload model between benchmarks (default: keep loaded). "
                                     "Use if KV-cache/GPU memory degradation occurs."}),
    (("--keep-response",), {"action": "store_true",
                            "help": "Write the full LLM response to per-task CSVs (default: truncated to 200 chars, see W1 in Code-Review_2026-07-12.md)"}),
]


def _build_launcher_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified Benchmark Launcher v13")
    parser.add_argument("--run-spec", "--config", type=str, default=None,
                        metavar="YAML",
                        help="Run-Spec (run.yaml): models/benchmarks/seed/... - CLI flags override YAML")
    for names, kwargs in _LAUNCHER_ARG_SPECS:
        parser.add_argument(*names, **kwargs)
    return parser


def _parse_args(argv: list[str] | None = None) -> tuple[Any, str]:
    """Phase 1: CLI-Parse + Run-Spec (--run-spec/config) + Versionsinfo.

    CLI-Flags haben Vorrang vor Run-Spec-Werten. Erkennung, welche
    CLI-Flags explizit gesetzt wurden, erfolgt über einen SUPPRESS-
    Probe-Parse (nur explizit gesetzte Dest-Namen landen im Namespace).
    """
    parser = _build_launcher_parser()
    args = parser.parse_args(argv)

    if args.run_spec:
        spec = _load_run_spec(args.run_spec)
        if spec.get("model"):
            available = get_available_models(exclude_keywords=EXCLUDE_KEYWORDS, registry_only=True)
        else:
            available = []
        spec = _validate_run_spec_selections(spec, available)

        # Probe-Parse: nur explizit gesetzte CLI-Flags (SUPPRESS-Defaults).
        probe = argparse.ArgumentParser(add_help=False)
        probe.add_argument("--run-spec", "--config", type=str, default=argparse.SUPPRESS)
        for names, kwargs in _LAUNCHER_ARG_SPECS:
            probe_kwargs = dict(kwargs)
            probe_kwargs["default"] = argparse.SUPPRESS
            if "choices" in probe_kwargs:
                probe_kwargs["choices"] = list(probe_kwargs["choices"])
            probe.add_argument(*names, **probe_kwargs)
        try:
            probe_ns, _ = probe.parse_known_args(argv if argv is not None else None)
            explicit_dests = set(vars(probe_ns)) - {"run_spec"}
        except argparse.ArgumentError:
            explicit_dests = None

        args = _apply_run_spec(args, spec, explicit_dests=explicit_dests)
        print(f"[INFO] Run-Spec angewendet: {os.path.basename(args.run_spec)} (CLI-Flags haben Vorrang)")

    _version = "13.0.0-p7"
    _version_file = os.path.join(PROJECT_ROOT, "VERSION")
    if os.path.isfile(_version_file):
        with open(_version_file, encoding="utf-8") as _vf:
            for _line in _vf:
                if _line.startswith("__version__"):
                    _version = _line.split("=", 1)[1].strip().strip("'\"")
                    break

    print("=" * 60)
    print(f"  Unified Benchmark Launcher v{_version}")
    print(f"  SampleSize: {args.sample_size}")
    if args.thinking:
        print("  Thinking mode: ON (reasoning models, force-enabled via --thinking)")
    print("  Pipelines: Custom (DS1000/CoderEval), EvalPlus, LM-Eval (ARC/HS/TQA/IFEval/M500), Agentic (tool-eval-bench)")
    print("  CSV-Format: csv_writer (; Delimiter, utf-8)")
    print("=" * 60)
    return args, _version


def _resolve_models(args: Any, available: list[AvailableModelInfo]) -> list[AvailableModelInfo]:
    """Phase 2a: Modelle aus CLI oder interaktiv auflösen."""
    if not available:
        print("[ERROR] No models available. Aborting.")
        sys.exit(1)
    models = resolve_models(available, args.model) if args.model else select_models_interactive(available)
    if not models:
        print("[ERROR] No models selected. Aborting.")
        sys.exit(1)
    print(f"  Models: {', '.join(m['display'] for m in models)}")
    return models


def _resolve_benchmarks(args: Any) -> list[BenchmarkDef]:
    """Phase 2b: Benchmarks aus CLI oder interaktiv auflösen + exclude-Filter."""
    benchmarks = resolve_benchmarks(args.benchmarks) if args.benchmarks else select_benchmarks_interactive()
    if not benchmarks:
        print("[ERROR] No benchmarks selected. Aborting.")
        sys.exit(1)
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
    return benchmarks


def _start_proxy_if_needed(models: list[AvailableModelInfo], benchmarks: list[BenchmarkDef]) -> None:
    """Phase 2c: LM-Eval-Proxy starten falls Reasoning-Modell + lm_eval-Benchmarks."""
    lmeval_names = {b["name"] for b in LMEVAL_BENCHMARKS}
    has_lmeval = any(b["name"] in lmeval_names for b in benchmarks)
    has_reasoning = any(_is_reasoning_model(m["key"]) for m in models)
    if has_lmeval and has_reasoning:
        _start_lmeval_proxy()


def _check_registry_for_model(model_identifier: str, model_display: str) -> bool | None:
    """Registry-Prüfungen (7 Checks). Gibt is_reasoning zurück oder None (skip)."""
    try:
        from assemble_blueprint import normalize_model_name
        registry, rnorm = _load_registry_for_context()
        normalized_key = normalize_model_name(model_identifier)
        base_key = normalized_key.split("@")[0]

        if normalized_key not in rnorm and base_key not in rnorm:
            print(f"\n  [ERROR] {model_display}: nicht in Registry - "
                  "`python registry_tool.py sync` ausführen. Überspringe.")
            return None

        matched_key = rnorm.get(normalized_key) or rnorm.get(base_key)
        reasoning_val = registry[matched_key].get("reasoning")
        if reasoning_val is None:
            print(f"\n  [ERROR] {model_display}: reasoning-Feld fehlt - "
                  "`python registry_tool.py sync` ausführen. Überspringe.")
            return None

        tpl = registry[matched_key].get("template")
        if tpl:
            from registry_tool import TEMPLATE_DIR
            if not (TEMPLATE_DIR / tpl).exists():
                print(f"\n  [WARN] {model_display}: template='{tpl}' -> Datei nicht gefunden")

        caps = registry[matched_key].get("capabilities")
        if not caps:
            print(f"\n  [ERROR] {model_display}: capabilities-Feld fehlt - Überspringe.")
            return None

        bp = registry[matched_key].get("blueprint")
        if not bp or bp == "none":
            print(f"\n  [ERROR] {model_display}: blueprint-Feld fehlt oder 'none' - Überspringe.")
            return None

        trunc = registry[matched_key].get("truncation")
        if trunc not in ("full", "medium", "minimal"):
            print(f"\n  [WARN] {model_display}: truncation-Feld fehlt - setze default='full'.")
            registry[matched_key]["truncation"] = "full"

        # Check assembled systemPrompt in Config JSON
        try:
            from pathlib import Path as _Path

            from assemble_blueprint import read_lms_configs
            cfgs = read_lms_configs(_Path.home() / ".lmstudio" / ".internal" / "user-concrete-model-default-config")
            cfg_key = normalize_model_name(model_identifier)
            for c in cfgs:
                if normalize_model_name(c.get("dir_name", "")) == cfg_key:
                    _data = json.loads(_Path(c["json_path"]).read_text(encoding="utf-8-sig"))
                    sys_prompt = next((_f.get("value", "") for _f in _data.get("operation", {}).get("fields", [])
                                      if _f.get("key") == "llm.prediction.systemPrompt"), "")
                    if not sys_prompt:
                        print(f"\n  [WARN] {model_display}: systemPrompt in Config JSON ist leer - "
                              "`assemble_blueprint.py assemble` ausführen.")
                    break
        except (ImportError, KeyError, OSError, ValueError):
            pass

        return (reasoning_val == "thinking") or _is_qwen3_6_model(model_identifier)
    except (ImportError, KeyError, OSError, ValueError):
        print("\n  [WARN] Registry nicht lesbar - ohne Reasoning-Info fortfahren.")
        return False


def _load_model(model_info: AvailableModelInfo, model_load_key: str, args: Any) -> str | None:
    """Modell laden + API-Ready prüfen. Gibt api_model zurück oder None (skip)."""
    loaded = get_current_loaded_model()
    api_model = None

    if loaded:
        li = loaded["identifier"].lower()
        lk = loaded["model_identifier"].lower()
        mk = model_info["key"].lower()
        if mk in li or mk in lk or li in mk or lk in mk:
            api_model = loaded["identifier"]
            print(f"  [OK] '{model_info['display']}' already loaded - ID: {api_model}")
        else:
            print(f"  [INFO] Different model loaded ({loaded['display_name']}) - unloading...")
            has_unloaded_all_models()
            ok, api_model = load_model_via_lms(model_load_key)
            if not ok:
                return None
    else:
        ok, api_model = load_model_via_lms(model_load_key)
        if not ok:
            return None

    print("  [INFO] Waiting for API readiness...")
    if not is_model_ready(timeout=60):
        print("  [WARN] Model readiness check timed out - continuing anyway")

    model_info["_api_model"] = api_model

    # Warn on variant mismatch
    all_variants = model_info.get("variants") or []
    if len(all_variants) > 1 and api_model:
        desired_quant = model_info.get("quant", "").lower()
        if desired_quant and desired_quant not in api_model.lower():
            print(f"  [WARN] Requested '@{desired_quant}' but '{api_model}' loaded")
            print(f"  [WARN] Available variants: {', '.join(v.split('@')[-1] for v in all_variants)}")

    return api_model


def _run_benchmarks_for_model(model_info: AvailableModelInfo, benchmarks: list[BenchmarkDef],
                               args: Any, is_reasoning_model: bool,
                               all_summary: list[dict]) -> list[dict]:
    """Benchmark-Dispatch: Custom/EvalPlus/LM-Eval/Agentic für ein Modell."""
    model_results: list[dict] = []
    model_load_key = model_info.get("model_identifier", model_info["key"])

    for bidx, bench in enumerate(benchmarks):
        if args.unload_between and bidx > 0:
            print("  [INFO] Unloading/reloading model between benchmarks...")
            has_unloaded_all_models()
            time.sleep(2)
            ok, api_model = load_model_via_lms(model_load_key)
            if not ok:
                print(f"  [ERROR] Reload before {bench['name']} failed. Skipping.")
                continue
            print("  [INFO] Waiting for API re-initialization...")
            if not is_model_ready(timeout=60):
                print("  [WARN] Model readiness check timed out - continuing anyway")
            model_info["_api_model"] = api_model

        bname = bench["name"]
        ep_names = {b["name"] for b in EVALPLUS_BENCHMARKS}
        lmeval_names = {b["name"] for b in LMEVAL_BENCHMARKS}
        agentic_names = {b["name"] for b in AGENTIC_BENCHMARKS}

        try:
            np = _resolve_num_parallel(model_load_key, args.sample_size,
                                      getattr(args, "num_parallel", None))
            if np > 1:
                print(f"  [PARALLEL] num_parallel={np} (SS={args.sample_size})")

            if bname in agentic_names:
                result = run_agentic(model_info, limit=args.sample_size,
                                     mode=getattr(args, "agentic_mode", "random"),
                                     seed=args.seed)
            elif bname in ep_names:
                result = run_evalplus(model_info, bench, sample_size=args.sample_size,
                                      seed=args.seed, is_reasoning_model=is_reasoning_model,
                                      num_parallel=np)
            elif bname in lmeval_names:
                per_limit = max(bench.get("min_limit", 0), args.sample_size)
                result = run_lmeval(model_info, bench, limit=per_limit,
                                    is_reasoning_model=is_reasoning_model, num_parallel=np)
            else:
                result = run_custom_benchmark(model_info, bench, sample_size=args.sample_size,
                                              seed=args.seed, is_structured_output_disabled=args.no_structured_output,
                                              should_keep_response=args.keep_response,
                                              num_parallel=np)

            if result:
                model_results.append(result)
                all_summary.append(result)

            _ensure_model_still_loaded(model_info["key"], model_load_key, bench_name=bname)
        except subprocess.TimeoutExpired:
            print(f"  [ERROR] {bench['name']} timeout (expired)")
        except (subprocess.SubprocessError, OSError, ValueError, TypeError, KeyError) as e:
            print(f"  [ERROR] {bench['name']}: {e}")

    return model_results


def _write_intermediate_summary(model_results: list[dict], model_info: AvailableModelInfo, args: Any) -> None:
    """Zwischen-Summary pro Modell via csv_writer."""
    if model_results:
        csv_writer.write_accumulative_summary(
            model_results, model_info,
            sample_size=args.sample_size,
            seed=str(args.seed or ""),
            exclude_benchmarks=args.exclude_benchmarks or "",
            no_structured_output=str(args.no_structured_output or ""),
            no_unload_between="True" if not args.unload_between else "",
            base_dir=PROJECT_ROOT,
        )


def _print_final_summary(all_summary: list[dict]) -> None:
    """Konsolen-Ausgabe aller Ergebnisse."""
    print("\n" + "=" * 60)
    print("  FINISHED")
    print("=" * 60)
    for s in all_summary:
        cat = s.get("category", "").ljust(9)
        print(f"  [{s['pipeline']}] {s['model']} / {cat}{s['bench']}")


def _write_consolidated_overview(all_summary: list[dict], models: list, args: Any) -> None:
    """Konsolidierte Übersicht (konsolidiert_aktuell.csv) bei Mehrfach-Modell-Läufen."""
    if all_summary and len(models) > 1:
        csv_writer.write_konsolidiert_aktuell(
            all_summary,
            sample_size=args.sample_size,
            seed=str(args.seed or ""),
            exclude_benchmarks=args.exclude_benchmarks or "",
            no_structured_output=str(args.no_structured_output or ""),
            no_unload_between="True" if not args.unload_between else "",
            base_dir=PROJECT_ROOT,
        )


def main() -> None:
    args, _version = _parse_args()

    lock_error = _acquire_single_instance_lock()
    if lock_error:
        print(lock_error)
        sys.exit(1)
    atexit.register(_release_single_instance_lock)

    global IS_THINKING_ENABLED
    IS_THINKING_ENABLED = args.thinking

    available = get_available_models(exclude_keywords=EXCLUDE_KEYWORDS, registry_only=True)
    models = _resolve_models(args, available)
    benchmarks = _resolve_benchmarks(args)
    _start_proxy_if_needed(models, benchmarks)

    all_summary: list[dict] = []

    for midx, model_info in enumerate(models, 1):
        model_identifier = model_info["key"]
        model_load_key = model_info.get("model_identifier", model_identifier)
        model_display = model_info["display"]

        is_reasoning_model = _check_registry_for_model(model_identifier, model_display)
        if is_reasoning_model is None:
            continue

        print(f"\n{'=' * 60}")
        print(f"  Model {midx}/{len(models)}: {model_display}")
        if is_reasoning_model:
            print("  * Reasoning model (detected) - timeout x2")
        if _is_moe_model(model_identifier):
            print("  * MoE model (detected)")
        print(f"{'=' * 60}")

        api_model = _load_model(model_info, model_load_key, args)
        if api_model is None:
            print("  [ERROR] Loading failed. Skipping.")
            continue

        model_results = _run_benchmarks_for_model(model_info, benchmarks, args,
                                                   is_reasoning_model, all_summary)
        _write_intermediate_summary(model_results, model_info, args)

    _stop_lmeval_proxy()
    _print_final_summary(all_summary)

    print("\n  [INFO] Cleaning up - unloading model(s)...")
    has_unloaded_all_models()

    _write_consolidated_overview(all_summary, models, args)


if __name__ == "__main__":
    main()
