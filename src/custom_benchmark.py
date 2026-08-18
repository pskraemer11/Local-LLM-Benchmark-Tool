#!/usr/bin/env python3
"""
Benchmark script for local LLMs via LM Studio API - DS1000 + CoderEval (v13).

── Role in the overall system ─────────────────────────────────────────
  This script is the "Custom" pipeline of the four-pipeline architecture:
    Pipeline             Script/Tool                Responsibility
    ────────             ───────────                ─────────────
    Custom (THIS ONE)    custom_benchmark.py    DS1000, CoderEval
    EvalPlus             evalplus.codegen/evaluate  HumanEval+, MBPP+
    LM-Eval              lm_eval CLI                ARC, HellaSwag, ...
    Agentic              tool_eval_bench            Tool-Use Scenarios

── Boundaries ───────────────────────────────────────────────────────
  THIS SCRIPT MUST NOT:
  - Load/unload models (that is done ONLY by run_benchmarks.py)
  - Call own model management functions
  - Start other pipelines

── Invocation ──────────────────────────────────────────────────────
  Normally as subprocess of run_benchmarks.py via:
    python custom_benchmark.py --non-interactive --model-key ... --api-model ... --sample-size N --benchmark DS1000
  Can run standalone (without --non-interactive), but then warns.

── Data sources ───────────────────────────────────────────────────
  JSONL files under simple_evals/:
    - data_science.jsonl                (DS1000: 5 Libraries)
    - codereval_selfcontained.jsonl     (CoderEval: ~138 Tasks)

── Evaluation ───────────────────────────────────────────────────────
  Per task: model generates code via LM Studio API, then
  execution in exec_sandboxed() with 4 evaluation modes:
    1. DS1000-Harness (test_execution)
    2. Namespace comparison (reference_code + setup_code)
    3. Reference as tests
    4. Direct tests
  System metrics (CPU/GPU/RAM) via monitor thread during API call.

── CSV Output ──────────────────────────────────────────────────────
  Uses csv_writer.py for unified schema.
  The launcher aggregates the results across pipelines.

── Changes vs v11 ──────────────────────────────────────────────────
  - CSV output via csv_writer.py (unified schema, ;-delimiter, utf-8)

Sources: DS1000, CoderEval
"""

from __future__ import annotations

import os as _os
import sys as _sys

# Make `src` importable regardless of the working directory
# (python -m src.custom_benchmark from the repo root puts only the CWD
# on sys.path, not `src/`). Fix for Code-Review_2026-08-03.md F4.
_SRC_DIR = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _SRC_DIR)

import ast
import csv
import json
import math
import os
import random
import re
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import psutil
import pynvml
import requests

import csv_writer as csv_writer
from benchmark_config import EXCLUDE_KEYWORDS, get_model_config

# Model management from shared module (is NOT initiated from here)
# NOTE: This script imports the constants and helper functions from
# model_manager.py, but NEVER calls load/unload. The load management
# is done exclusively by run_benchmarks.py as the parent
# launcher. The exact model ID is passed via --api-model.
from model_manager import (
    API_BASE,
    get_available_models,
    get_current_loaded_model,
    has_unloaded_all_models,
    is_api_available,
    parse_selection,
)
from type_defs import (
    GenerationConfig,
    MetricsSummary,
    ModelConfig,
    SandboxResult,
    SystemMetrics,
    TaskResult,
)
from utils.terminal import (
    error,
    info,
    ok,
    warn,
)

# ── Registry Reasoning Check ────────────────────────────────────────────
# Used to check if a model supports reasoning (thinking/instruct/unknown).
_REGISTRY_REASONING_CACHE: dict[str, str | None] | None = None

def _model_supports_reasoning(model_identifier: str) -> bool | None:
    """Check registry for reasoning field.

    Returns True (thinking), False (instruct), None (missing / unknown).
    """
    global _REGISTRY_REASONING_CACHE
    if _REGISTRY_REASONING_CACHE is None:
        _REGISTRY_REASONING_CACHE = {}
        try:
            from assemble_blueprint import normalize_model_name
            from registry_tool import load_registry
            data = load_registry()
            for key, entry in data.items():
                if isinstance(entry, dict) and "reasoning" in entry:
                    nk = normalize_model_name(key)
                    _REGISTRY_REASONING_CACHE[nk] = entry["reasoning"]
                    # Basis-Key (ohne @quant) mit abbilden, damit auch
                    # Quant-less Anfragen wie der LMS modelKey auf Mischquants
                    # (Registry '@mixed') und reguläre Quants matchen. Analog
                    # zum Launcher-Fix _load_registry_for_context (13.08.).
                    _REGISTRY_REASONING_CACHE.setdefault(nk.split("@")[0], entry["reasoning"])
        except (OSError, KeyError, ValueError):
            pass
    try:
        from assemble_blueprint import normalize_model_name
        normalized_key = normalize_model_name(model_identifier)
    except (ImportError, AttributeError):
        normalized_key = model_identifier.lower().replace("-", "_").replace(" ", "_")
    cached = _REGISTRY_REASONING_CACHE.get(normalized_key) if normalized_key else None
    # Fallback: ohne @quant-Suffix (Registry-Keys haben kein Quant)
    if cached is None and normalized_key and "@" in normalized_key:
        base_key = normalized_key.split("@")[0]
        cached = _REGISTRY_REASONING_CACHE.get(base_key)
    if cached == "thinking":
        return True
    if cached == "instruct":
        return False
    return None


SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SRC_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "simple_evals")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "ergebnisse")
os.makedirs(RESULTS_DIR, exist_ok=True)

TIMEOUT_LOAD_MODEL = 180
TIMEOUT_SAMPLER_JOIN = 3
TIMEOUT_EXEC = 30

# Qwen3.5 compatibility: prompt embedding instead of system message
IS_QWEN_PROMPT_MODE = False
IS_THINKING_MODE = False
HAS_STRUCTURED_OUTPUT = True
KEEP_RESPONSE = False

STRUCTURED_OUTPUT_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "code_response",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"}
            },
            "required": ["code"]
        }
    }
}

def _can_use_structured_output(model_identifier: str | None) -> bool:
    """Whether the JSON-schema response format can be requested for a model.

    Disabled when structured output is globally off (--no-structured-output),
    when thinking mode is enabled, when the registry marks the model as
    reasoning (thinking), or for Mamba architectures which reject
    constrained decoding. Also disabled for Codestral-22B whose grammar
    generation fails server-side ("Failed to initialize samplers:
    Unexpected empty grammar stack after accepting piece", Server-Log
    03.08.2026, Code-Review_2026-08-03.md F5). Falls back to regex-based
    extraction otherwise.
    """
    if not HAS_STRUCTURED_OUTPUT:
        return False
    if IS_THINKING_MODE:
        return False
    if model_identifier and _model_supports_reasoning(model_identifier) is True:
        return False
    if model_identifier and "mamba" in model_identifier.lower():
        return False
    if model_identifier and "codestral" in model_identifier.lower():
        return False
    return True


SAMPLE_SIZE = 10
random.seed()

MAX_TASKS_PER_BENCHMARK = 100

MAX_TOKENS_GENERAL = 4096
MAX_TOKENS_MC = 64

MONITOR_HISTORY_MAX = 500
# Code-Review 2026-07-18 §4.1: sampling interval increased from 0.2s to
# 0.5s to reduce NVML/syscall overhead by ~60%. Median/P90 over 5-10
# samples per task is statistically equivalent for our 1-5s task windows.
MONITOR_SAMPLE_INTERVAL_S = 0.5

# --- Streaming / Timeout / Retry Configuration ---
START_TIMEOUT = 30           # max seconds until first token
FINISH_TIMEOUT = 25          # max seconds between tokens (stall detection)
MAX_RETRIES = 3              # max retries on API errors
RETRY_MULTIPLIER = 1.5       # Timeout-Multiplikator pro Retry
# \n```\n (statt \n```) : "\n```" matcht die OEFFNUNG eines Markdown-Codeblocks
# (Modelle wie deepseek-r1-distill-qwen-14b beginnen die Antwort mit "\n```python"),
# schneidet die gesamte Antwort auf ~0 Tokens ab ("No code generated").
# Mit folgendem Newline matcht der Stop nur das SCHLIESSEN des Blocks.
# Siehe: Server-Experiment 01.08.2026 - DeepSeek-Verifikationslauf 0% trotz Prompt-Hardening.
STOP_TOKENS_CODING = ["\n```\n", "\n# Task", "\n// ", "<|endoftext|>"]
STOP_TOKENS_DEFAULT = ["<|endoftext|>"]

BENCHMARKS = [
    {"key": "1", "name": "DS1000", "file": "data_science.jsonl"},
    # NOTE: The interactive menu uses parse_selection() which expects 1..len(BENCHMARKS).
    # Keep keys sequential so the printed options match what the parser accepts.
    {"key": "2", "name": "CoderEval", "file": "codereval_selfcontained.jsonl"},
]

# Prio 3.13 (Code-Review_2026-07-12.md §3.1 D2): zentralisierte
# Thinking-Konfiguration. Vorher gab es eine doppelte Pflege in
# `MODEL_CONFIG` (hier) und `_get_lmeval_params()` (im Launcher).
# Jetzt in benchmark_config.get_model_config() vereinheitlicht (Variante C+).
# Siehe BENCHMARK_CATEGORY_DEFAULTS + MODEL_TEMP_OVERRIDES.

def parse_tests_field(tests_field: Any) -> list[str]:
    """Normalize the heterogeneous ``tests`` field of a benchmark task.

    Accepts an actual list, a JSON-ish string (e.g. "['assert ...']" or
    "[]"), or a plain string. Returns a list of test code strings; a
    plain string is wrapped in a single-element list as last resort.
    """
    if isinstance(tests_field, list):
        return tests_field
    if isinstance(tests_field, str):
        tests_field = tests_field.strip()
        if not tests_field or tests_field == "[]":
            return []
        try:
            parsed = ast.literal_eval(tests_field)
            if isinstance(parsed, list):
                return parsed
        except (ValueError, SyntaxError):
            pass
        return [tests_field]
    return []


def subsample_tasks(tasks: list[dict[str, Any]], task_type: str, sample_size: int = SAMPLE_SIZE) -> list[dict[str, Any]]:
    """Stratified random subsampling that keeps ``_group`` balance.

    When tasks carry a ``_group`` field, the sample size is distributed
    across the groups (ceil per group) so no library/domain is dropped;
    the result is trimmed to ``sample_size`` if over-selected. Without
    groups, a plain random sample is drawn. Returns the input unchanged
    when there is nothing to subsample.
    """
    if not tasks:
        return tasks
    if sample_size is None or sample_size >= len(tasks):
        return tasks
    groups = {}
    for t in tasks:
        g = t.get("_group")
        if g is not None:
            groups.setdefault(str(g), []).append(t)
    if not groups:
        return random.sample(tasks, min(sample_size, len(tasks)))
    num_groups = len(groups)
    per_group = math.ceil(sample_size / num_groups)
    selected = []
    for g in sorted(groups.keys()):
        pool = groups[g]
        take = min(len(pool), per_group)
        selected.extend(random.sample(pool, take))
    if len(selected) > sample_size:
        selected = random.sample(selected, sample_size)
    return selected


_DS1000_BROKEN_API_PATTERNS: list[str] = [
    "interp2d",  # removed in scipy 1.13+, breaks DS1000 task #339
]


def _filter_broken_code_tasks(tasks: list[dict]) -> list[dict]:
    """Filter out DS1000 tasks whose code_context uses removed/broken APIs.

    The official DS1000 environment pins scipy==1.12.0, but the current
    benchmark environment has scipy>=1.17 where interp2d was removed.
    These tasks would always score 0 due to harness error, not model quality.
    """
    filtered: list[dict] = []
    removed = 0
    for task in tasks:
        code_ctx = task.get("code_context", "")
        if any(p in code_ctx for p in _DS1000_BROKEN_API_PATTERNS):
            removed += 1
            continue
        filtered.append(task)
    if removed:
        print(f"  [FILTER] {removed} Task(s) mit broken APIs entfernt (interp2d in code_context)")
    return filtered


class Monitor:
    def __init__(self) -> None:
        """Initialize rolling resource-history buffers and NVML if available.

        Tries pynvml for GPU/VRAM readings; when unavailable, GPU metrics
        stay empty and a warning is issued. CPU/RAM come from psutil.
        """
        self.cpu_percent = []
        self.gpu_percent = []
        self.ram_usage_gb = []
        self.vram_usage_gb = []
        self._is_sampling = False
        self._peak = {"cpu": 0, "ram": 0, "gpu": 0, "vram": 0}
        self._is_nvml_ok = False
        try:
            pynvml.nvmlInit()
            count = pynvml.nvmlDeviceGetCount()
            if count > 0:
                self._nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                self._is_nvml_ok = True
        except (pynvml.NVMLError, OSError):
            pass
        if not self._is_nvml_ok:
            warn("GPU/VRAM monitoring via NVML not available")

    def _read_gpu(self) -> tuple[float | None, float | None]:
        """Return (gpu_util_percent, vram_used_gb) via NVML, or (None, None)."""
        if not self._is_nvml_ok:
            return None, None
        try:
            util = pynvml.nvmlDeviceGetUtilizationRates(self._nvml_handle)
            mem = pynvml.nvmlDeviceGetMemoryInfo(self._nvml_handle)
            return util.gpu, mem.used / (1024 ** 3)
        except (pynvml.NVMLError, OSError):
            return None, None

    def _read_cpu_ram(self, interval: float = 0.3) -> tuple[float, float]:
        """Return (cpu_percent, ram_used_gb) sampled over ``interval`` seconds."""
        cpu = psutil.cpu_percent(interval=interval)
        ram = psutil.virtual_memory().used / (1024 ** 3)
        return cpu, ram

    def update(self) -> None:
        """Append one CPU/RAM/GPU/VRAM sample, trimming the rolling history."""
        cpu, ram = self._read_cpu_ram()
        self.cpu_percent.append(cpu)
        self.ram_usage_gb.append(ram)
        gpu, vram = self._read_gpu()
        if gpu is not None:
            self.gpu_percent.append(gpu)
            self.vram_usage_gb.append(vram)
        for lst in (self.cpu_percent, self.ram_usage_gb, self.gpu_percent, self.vram_usage_gb):
            if len(lst) > MONITOR_HISTORY_MAX:
                del lst[:-MONITOR_HISTORY_MAX]

    def get_snapshot(self) -> dict[str, float]:
        """Take a fresh sample and return the latest per-resource values."""
        self.update()
        return {
            "cpu": self.cpu_percent[-1] if self.cpu_percent else 0,
            "ram": self.ram_usage_gb[-1] if self.ram_usage_gb else 0,
            "gpu": self.gpu_percent[-1] if self.gpu_percent else 0,
            "vram": self.vram_usage_gb[-1] if self.vram_usage_gb else 0,
        }

    def start_sampling(self) -> None:
        """Start a daemon thread that tracks peak CPU/RAM/GPU/VRAM values."""
        self._peak = {"cpu": 0, "ram": 0, "gpu": 0, "vram": 0}
        self._is_sampling = True
        import threading as _thr

        def _sample_loop() -> None:
            """Background loop: sample CPU/RAM (and GPU/VRAM) peaks until stopped."""
            while self._is_sampling:
                cpu = psutil.cpu_percent(interval=MONITOR_SAMPLE_INTERVAL_S)
                ram = psutil.virtual_memory().used / (1024 ** 3)
                self._peak["cpu"] = max(self._peak["cpu"], cpu)
                self._peak["ram"] = max(self._peak["ram"], ram)
                if self._is_nvml_ok:
                    try:
                        util = pynvml.nvmlDeviceGetUtilizationRates(self._nvml_handle)
                        mem = pynvml.nvmlDeviceGetMemoryInfo(self._nvml_handle)
                        gpu_val = util.gpu
                        vram_val = mem.used / (1024 ** 3)
                        self._peak["gpu"] = max(self._peak["gpu"], gpu_val)
                        self._peak["vram"] = max(self._peak["vram"], vram_val)
                    except (pynvml.NVMLError, OSError):
                        pass

        self._sampler = _thr.Thread(target=_sample_loop, daemon=True)
        self._sampler.start()

    def stop_sampling(self) -> dict[str, float]:
        """Stop the sampler thread and return the recorded peak values."""
        self._is_sampling = False
        if hasattr(self, "_sampler"):
            self._sampler.join(timeout=TIMEOUT_SAMPLER_JOIN)
        peak = dict(self._peak)
        self._peak = {"cpu": 0, "ram": 0, "gpu": 0, "vram": 0}
        return peak


def collect_system_metrics() -> SystemMetrics:
    """Collect a one-shot snapshot of CPU/RAM (psutil) and GPU (nvidia-smi).

    GPU values come from ``nvidia-smi --query-gpu=...``; the VRAM in-use
    figure is additionally parsed from ``lms ps`` when nvidia-smi fails
    or reports nothing. Missing values are None.
    """
    cpu_percent = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    ram_percent = mem.percent
    ram_used_gb = mem.used / (1024 ** 3)
    ram_total_gb = mem.total / (1024 ** 3)
    gpu_util = None
    gpu_mem_util = None
    gpu_mem_used_gb = None
    gpu_mem_total_gb = None
    gpu_temp = None
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace"
        )
        if r.returncode == 0 and r.stdout.strip():
            parts = [x.strip() for x in r.stdout.strip().split(",")]
            if len(parts) >= 5:
                gpu_util = float(parts[0])
                gpu_mem_util = float(parts[1])
                gpu_mem_used_gb = float(parts[2]) / 1024
                gpu_mem_total_gb = float(parts[3]) / 1024
                gpu_temp = float(parts[4])
    except (ValueError, IndexError, OSError):
        pass
    vram_gb = None
    try:
        r = subprocess.run(
            ["lms", "ps"],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace"
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                line = line.strip()
                if not line or line.startswith("NAME") or line.startswith("---"):
                    continue
                parts = re.split(r"\s{2,}", line)
                for p in parts:
                    p = p.strip()
                    m = re.match(r"([\d.]+)\s*(GB|GiB)", p, re.IGNORECASE)
                    if m:
                        vram_gb = float(m.group(1))
                        break
                    m = re.match(r"([\d.]+)\s*(MB|MiB)", p, re.IGNORECASE)
                    if m:
                        vram_gb = float(m.group(1)) / 1024
                        break
                if vram_gb is not None:
                    break
    except (re.error, ValueError, IndexError, OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    return {
        "cpu_percent": cpu_percent,
        "ram_percent": ram_percent,
        "ram_used_gb": ram_used_gb,
        "ram_total_gb": ram_total_gb,
        "gpu_util": gpu_util,
        "gpu_mem_util": gpu_mem_util,
        "gpu_mem_used_gb": gpu_mem_used_gb,
        "gpu_mem_total_gb": gpu_mem_total_gb,
        "gpu_temp": gpu_temp,
        "vram_gb": vram_gb,
    }


class MetricsCollector:
    def __init__(self, sample_interval: int = 10) -> None:
        """Create a collector that samples system metrics every ``sample_interval`` seconds."""
        self.samples = []
        self._start_time = None
        self._last_sample_time = 0
        self._sample_interval = sample_interval

    def start(self) -> None:
        """Begin a collection window and record the initial baseline sample."""
        self._start_time = time.time()
        self._last_sample_time = self._start_time
        self.samples = [(0.0, collect_system_metrics())]

    def sample(self) -> None:
        """Record one (elapsed, metrics) sample if the collector is running."""
        if self._start_time is None:
            return
        elapsed = time.time() - self._start_time
        self.samples.append((elapsed, collect_system_metrics()))

    def maybe_sample(self) -> None:
        """Sample now if at least ``sample_interval`` seconds have elapsed."""
        if self._start_time is None:
            return
        now = time.time()
        if now - self._last_sample_time >= self._sample_interval:
            self._last_sample_time = now
            self.sample()

    def stop(self) -> None:
        """Take the final sample and close the collection window."""
        self.sample()
        self._start_time = None

    def _values(self, key: str) -> list[float]:
        """All non-None values of a metric key across the samples."""
        return [s[1].get(key) for s in self.samples if s[1].get(key) is not None]

    def avg(self, key: str) -> float | None:
        """Average of a metric key over the samples (None if empty)."""
        vals = self._values(key)
        return sum(vals) / len(vals) if vals else None

    def max(self, key: str) -> float | None:
        """Maximum of a metric key over the samples (None if empty)."""
        vals = self._values(key)
        return max(vals) if vals else None

    def min(self, key: str) -> float | None:
        """Minimum of a metric key over the samples (None if empty)."""
        vals = self._values(key)
        return min(vals) if vals else None

    def get_summary(self) -> MetricsSummary:
        """Aggregate avg/max per metric key into a MetricsSummary dict."""
        result = {}
        for k in ("cpu_percent", "gpu_util", "ram_percent", "ram_used_gb", "gpu_mem_used_gb", "gpu_temp", "vram_gb"):
            result[f"{k}_avg"] = self.avg(k)
            result[f"{k}_max"] = self.max(k)
        return result


def load_jsonl(filepath: str) -> list[dict[str, Any]]:
    """Load a JSONL file into a list of dicts, skipping blank lines."""
    with open(filepath, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]



def _stream_chat_completion(url: str, headers: dict[str, str], body: dict[str, Any], start_timeout: int = START_TIMEOUT, finish_timeout: int = FINISH_TIMEOUT, max_retries: int = MAX_RETRIES) -> tuple[str | None, float, int, int, float, int, bool, str | None, str | None]:
    """Streaming chat completion with dual timeout and retry logic.
    
    Uses threading to monitor start_timeout (first token) and finish_timeout
    (between tokens) independently from the SSE stream.
    Returns 9-tuple: (content, elapsed, t_in, t_out, tps, thinking_tokens, truncated, error_type, error_detail)
    truncated = True when the server stopped generation because the
    token budget was reached (finish_reason "length" or tokens_out >= max_tokens).
    """
    max_tokens_requested = body.get("max_tokens")
    for attempt in range(max_retries):
        current_start_timeout = start_timeout * (RETRY_MULTIPLIER ** attempt)
        result = {"content": "", "thinking": "", "done": False, "error": None, "usage": None, "finish_reason": None}
        result_lock = threading.Lock()
        cancel_event = threading.Event()

        def _set_result(key: str, value: Any, result_lock: threading.Lock = result_lock,
                        result: dict[str, Any] = result) -> None:
            """Thread-safe write to the shared result dict."""
            with result_lock:
                result[key] = value

        def _result(key: str, result_lock: threading.Lock = result_lock,
                    result: dict[str, Any] = result) -> Any:
            """Thread-safe read from the shared result dict."""
            with result_lock:
                return result.get(key)

        def _worker(result_lock: threading.Lock = result_lock,
                    result: dict[str, Any] = result,
                    cancel_event: threading.Event = cancel_event,
                    current_start_timeout: int = current_start_timeout) -> None:
            """Stream SSE deltas into the shared result dict in a background thread."""
            sess = None
            try:
                sess = requests.Session()
                resp = sess.post(url, headers=headers, json={**body, "stream": True}, stream=True, timeout=(10, current_start_timeout))
                resp.raise_for_status()
                for line in resp.iter_lines(decode_unicode=True):
                    if cancel_event.is_set():
                        break
                    if not line:
                        continue
                    text = line.strip()
                    if text == "data: [DONE]":
                        break
                    if text.startswith("data: "):
                        try:
                            chunk = json.loads(text[6:])
                            if "usage" in chunk:
                                with result_lock:
                                    result["usage"] = chunk["usage"]
                            finish_reason = chunk.get("choices", [{}])[0].get("finish_reason")
                            if finish_reason:
                                with result_lock:
                                    result["finish_reason"] = finish_reason
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            reasoning_delta = _extract_reasoning_delta(delta)
                            with result_lock:
                                if delta.get("content"):
                                    result["content"] += delta["content"]
                                if reasoning_delta:
                                    result["thinking"] += reasoning_delta
                        except json.JSONDecodeError:
                            pass
                _set_result("done", True)
            except (requests.exceptions.RequestException, ConnectionError, TimeoutError, ValueError, KeyError) as e:
                # Extract response body for HTTPError so the launcher can detect
                # "Cannot combine structured output constraints with lazy grammar"
                # (LM Studio Channel-Error - see Server-Log 12.07.2026 L58671).
                err_text = str(e)
                try:
                    if hasattr(e, "response") and e.response is not None:
                        resp_body = e.response.text or ""
                        if resp_body:
                            err_text = f"{err_text} | body={resp_body[:300]}"
                except (AttributeError, ValueError, TypeError):
                    pass
                _set_result("error", err_text)
                _set_result("done", True)
            finally:
                if sess is not None:
                    try:
                        sess.close()
                    except OSError:
                        pass
        start = time.time()
        thread = threading.Thread(target=_worker)
        thread.daemon = True
        thread.start()
        while time.time() - start < current_start_timeout:
            with result_lock:
                done = result["done"]
                content = result["content"]
                thinking = result["thinking"]
                error = result["error"]
            # Reasoning-Modelle (z.B. DeepSeek R1 Distill) streamen zunaechst
            # NUR reasoning_content; content folgt erst nach dem Denken. Wird
            # nur auf content gewartet, laeuft der Start-Timeout ab und der
            # Stream wird abgebrochen, obwohl das Modell aktiv arbeitet.
            if done or content or thinking or error:
                break
            time.sleep(0.05)
        elapsed = time.time() - start
        with result_lock:
            error_val = result["error"]
        if error_val:
            if attempt < max_retries - 1:
                cancel_event.set()
                thread.join(timeout=1)
                time.sleep(2 ** attempt)
                continue
            return None, elapsed, 0, 0, 0, 0, False, "api_error", error_val
        with result_lock:
            has_content = bool(result["content"]) or bool(result["thinking"])
            is_done = result["done"]
        if not has_content and not is_done:
            cancel_event.set()
            thread.join(timeout=1)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return None, elapsed, 0, 0, 0, 0, False, "api_error", f"No response within {current_start_timeout}s (attempt {attempt+1})"
        last_content_len = 0
        stall_start = time.time()
        while time.time() - stall_start < finish_timeout:
            with result_lock:
                is_done = result["done"]
            if is_done:
                break
            with result_lock:
                current_len = len(result["content"]) + len(result["thinking"])
            if current_len > last_content_len:
                last_content_len = current_len
                stall_start = time.time()
            time.sleep(0.05)
        with result_lock:
            is_done = result["done"]
        if not is_done:
            cancel_event.set()
            thread.join(timeout=1)
        full_elapsed = time.time() - start
        with result_lock:
            thinking_content = result["thinking"]
            content_raw = result["content"]
            usage = result.get("usage") or {}
            finish_reason = result["finish_reason"]
        thinking_tokens = len(thinking_content.split()) if thinking_content else 0
        content, think_tags = strip_thinking_tokens(content_raw)
        thinking_tokens = thinking_tokens + think_tags
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)
        usage_present = bool(usage)
        if not usage_present:
            # LM Studio liefert usage nicht immer im Stream - dann abschaetzen
            # ueber Wortzahl (inkl. Thinking-Anteil fuer Reasoning-Modelle).
            tokens_out = len((content_raw + " " + thinking_content).split())
        truncated = finish_reason == "length"
        if max_tokens_requested and usage_present and tokens_out >= max_tokens_requested:
            truncated = True
        tokens_per_sec = tokens_out / full_elapsed if full_elapsed > 0 else 0
        return content, full_elapsed, tokens_in, tokens_out, tokens_per_sec, thinking_tokens, truncated, None, None
    return None, 0, 0, 0, 0, 0, False, "api_error", "Max retries exceeded"


def strip_thinking_tokens(text: str | None) -> tuple[str | None, int]:
    """Remove thinking sections from the response and estimate their token count.

    Supports both:
    - Gemma 4: <|channel>thought\n...<channel|>
    - Legacy: <think>...</think>

    The previous `total_chars // 4` heuristic systematically over-counted
    tokens for Gemma-4 thinking sections because they typically contain
    repeated reasoning phrases, whitespace and special tokens that don't
    tokenize 1:1 with characters. We now use a content-aware estimate:
      - Whitespace-split words (best for natural language + code)
      - Whitespace split + special-token penalty for Gemma-4

    See: server-log 12.07.2026 - Qwen3.6-28b thinking tokens were estimated
    at >50% of total tokens for some prompts; the new heuristic brings that
    to a more realistic 20-35%.
    """
    if not text:
        return text, 0

    # Gemma 4: <|channel>thought\n...<channel|>
    channel_matches = re.findall(r"<\|channel>thought\n(.*?)<channel\|>", text, re.DOTALL)

    # Legacy: <think>...</think>
    think_matches = re.findall(r"<think>(.*?)</think>", text, re.DOTALL)

    all_content = channel_matches + think_matches
    if not all_content:
        return text, 0

    # Content-aware token estimation:
    # - word_count is the most accurate cheap approximation for English/Code
    #   (~0.75-0.85 tokens per word for typical content)
    # - char_count is the fallback (was the old behavior)
    # - We pick the larger of the two as a conservative upper bound and cap
    #   with char//4 to detect pathological whitespace-heavy sections.
    # NB: filter() to exclude empty strings - ``str.split()`` counts
    # consecutive whitespace as empty tokens, inflating word_count.
    word_count = sum(len([w for w in m.split() if w]) for m in all_content)
    char_count = sum(len(m) for m in all_content)
    # If the content is mostly whitespace (word_count == 0), BPE tokenizers
    # would emit a single whitespace token or a few special tokens. We
    # cap at 1 token per ~64 whitespace chars (a conservative estimate).
    if word_count == 0 and char_count > 0:
        estimated_tokens = max(1, char_count // 64)
    else:
        char_based = char_count // 4
        # Whitespace-heavy Gemma-4 chains inflate char_count but not word_count.
        # Average: take word_count * 1.3 (1.3 tokens per word, BPE typical) and
        # char//4, then use the higher of the two. The 1.3 factor accounts for
        # BPE splitting of long words/code identifiers.
        estimated_tokens = max(int(word_count * 1.3), char_based)
    # Cap by char_count (cannot have more tokens than characters) and
    # ensure non-negative.
    estimated_tokens = max(0, min(estimated_tokens, char_count))

    cleaned = text
    cleaned = re.sub(r"<\|channel>thought\n.*?<channel\|>", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
    # If thinking tags consumed the entire response, warn
    if estimated_tokens > 0 and (not cleaned or len(cleaned) < 10):
        warn(f"Thinking tokens consumed entire response ({estimated_tokens} tok estimated). "
              f"Model may need enable_thinking=False in MODEL_CONFIG.")
    return cleaned, estimated_tokens


def _non_streaming_fallback(url: str, body: dict[str, Any], timeout: int) -> tuple[str | None, int, int, int, bool]:
    """Non-streaming fallback, if streaming fails."""
    try:
        payload = json.dumps(body).encode("utf-8")
        req = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        message = result["choices"][0]["message"]
        raw_content = message.get("content", "")
        thinking_tokens = 0
        # gpt-oss: Reasoning ist in message.reasoning (nicht in content)
        reasoning_content = message.get("reasoning", "")
        # DeepSeek R1 Distill etc.: LM Studio liefert reasoning_content
        if not reasoning_content:
            reasoning_content = message.get("reasoning_content", "")
        if reasoning_content:
            thinking_tokens = len(reasoning_content.split())
        content, think_tags = strip_thinking_tokens(raw_content)
        thinking_tokens += think_tags
        usage = result.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)
        finish_reason = result.get("choices", [{}])[0].get("finish_reason")
        truncated = finish_reason == "length"
        max_tokens_requested = body.get("max_tokens")
        if max_tokens_requested and usage and tokens_out >= max_tokens_requested:
            truncated = True
        return content, tokens_in, tokens_out, thinking_tokens, truncated
    except (URLError, HTTPError, json.JSONDecodeError, KeyError, TimeoutError) as e:
        error(f"API error (Fallback, {type(e).__name__}): {e}")
        return None, 0, 0, 0, False


def _extract_reasoning_delta(delta: dict) -> str:
    """Extract reasoning content from a streamed chat delta chunk.

    The field name depends on model and LM Studio version:
      - DeepSeek R1 (LM Studio 0.3.9+, App Settings > Developer
        "Separate reasoning_content"): `delta.reasoning_content`
      - gpt-oss (LM Studio 0.3.23+, o3-mini-conform, see
        /docs/developer/api-changelog): `delta.reasoning`
    Returns "" when no reasoning content is present.
    """
    reasoning = delta.get("reasoning_content")
    if reasoning is None and isinstance(delta.get("reasoning"), str):
        reasoning = delta["reasoning"]
    return reasoning or ""


def _supports_chat_template_kwargs(model_identifier: str | None) -> bool:
    """True if the model's chat template supports ``chat_template_kwargs``.

    ``chat_template_kwargs`` (enable_thinking / reasoning_effort) is the only
    API-level thinking control and is supported by chat templates that render
    ``enable_thinking``:
      - Qwen3/Qwen3.5 and Qwen-based distills (Qwen2 arch, Qwen template)
      - Gemma-4 (minijinja templates render ``<|think|>`` when
        ``enable_thinking`` is truthy; fixed 15.08. — previously only Qwen
        was covered, so Gemma never received the flag and the JSON-config
        budget (2048) kept thinking active for ALL Gemma benchmarks).
    """
    name = (model_identifier or "").lower()
    return "qwen" in name or "gemma" in name


def generate_answer(cfg: GenerationConfig) -> tuple[str | None, float, int, int, float, int, bool, str | None, str | None]:
    """Send one chat-completions request (streaming first, then fallback).

    Builds the request body from ``cfg``, including thinking control via
    ``chat_template_kwargs`` for Qwen-based templates. Tries the streaming
    path first; on failure it warns and falls back to a non-streaming
    request. Returns a 9-tuple
    (content, elapsed, t_in, t_out, tps, thinking_tokens, truncated,
    error_type, error_detail) — content is None on error.
    """
    messages = cfg.messages
    if messages is None:
        messages = []
        if cfg.system_msg:
            messages.append({"role": "system", "content": cfg.system_msg})
        messages.append({"role": "user", "content": cfg.prompt})
    body = {
        "model": cfg.model_identifier or "local-model",
        "messages": messages,
        "temperature": cfg.temperature,
        "top_p": cfg.top_p,
        "max_tokens": cfg.max_tokens,
    }
    if cfg.top_k is not None:
        body["top_k"] = cfg.top_k
    if cfg.min_p is not None:
        body["min_p"] = cfg.min_p
    # ── Thinking-Modus ueber OpenAI-kompatibles API steuern ──
    #
    # Quelle:
    #   - Qwen3/Qwen3.5 und Qwen-basierte Distills: chat_template_kwargs
    #     (nur fuer Qwen-Templates) Quelle:
    #     https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1573
    #
    # WICHTIG: chat_template_kwargs ist KEIN OpenAI-Standard-Parameter und wird
    #   nur von Qwen-Modellen unterstuetzt. Fuer andere Modelle keine
    #   Thinking-Steuerung ueber diese API moeglich.
    #
    # 2026-08-02: Der gpt-oss-Override (reasoning_effort="low" +
    #   max_thinking_tokens=200) wurde entfernt. Reasoning-Budget wird in
    #   LM Studio GUI per Modell gesetzt (Slider); siehe Recovery.
    #
    if cfg.is_thinking_enabled is False:
        if _supports_chat_template_kwargs(cfg.model_identifier):
            body["chat_template_kwargs"] = {"enable_thinking": False}
    elif cfg.is_thinking_enabled is not None or cfg.reasoning_effort is not None:
        kwargs = {}
        if cfg.is_thinking_enabled is not None:
            kwargs["enable_thinking"] = cfg.is_thinking_enabled
        if cfg.reasoning_effort is not None:
            kwargs["reasoning_effort"] = cfg.reasoning_effort
        if _supports_chat_template_kwargs(cfg.model_identifier):
            body["chat_template_kwargs"] = kwargs
    if cfg.stop:
        body["stop"] = cfg.stop
    if cfg.response_format is not None:
        body["response_format"] = cfg.response_format
    url = f"{API_BASE}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if cfg.is_streaming:
        content, elapsed, t_in, t_out, tps, think_tok, truncated, err_type, err_detail = _stream_chat_completion(url, headers, body)
        if content is not None:
            return content, elapsed, t_in, t_out, tps, think_tok, truncated, err_type, err_detail
        warn(f"Streaming failed ({err_detail}), fallback without streaming...")
    start = time.time()
    content, t_in, t_out, think_tok, truncated = _non_streaming_fallback(url, {**body, "stream": False}, cfg.timeout)
    elapsed = time.time() - start
    if content is not None:
        tokens_per_sec = t_out / elapsed if elapsed > 0 else 0
        return content, elapsed, t_in, t_out, tokens_per_sec, think_tok, truncated, None, None
    return None, elapsed, t_in, t_out, 0, think_tok, truncated, "api_error", "Fallback also failed"


def classify_output(code: str, response: str, is_structured: bool, entry_point: str = "") -> dict[str, Any]:
    """Diagnose how the response was converted to runnable code.

    This is the "Struktur-Gate" diagnostic: it records HOW the raw LLM
    output was translated into `code`, so we can measure structured-output
    fidelity independently of the harness pass/fail.
    """
    status = "empty"
    if response:
        if is_structured:
            try:
                parsed = json.loads(response)
            except (json.JSONDecodeError, TypeError, AttributeError):
                status = "json_invalid"
            else:
                if isinstance(parsed, dict) and parsed.get("code"):
                    status = "json_ok"
                else:
                    status = "json_missing_code"
        else:
            status = "fenced" if re.search(r"```", response) else "bare"
    ep_found: bool | None = None
    if entry_point:
        ep_found = bool(code and re.search(r"(?m)^\s*def\s+" + re.escape(entry_point) + r"\s*\(", code))
    return {
        "output_status": status,
        "entry_point_found": ep_found,
        "entry_point": entry_point or "",
    }


def extract_code(text: str | None, is_structured: bool = False) -> str:
    """Extract Python code from the model's response.

    Handles four output styles (see Code-Review_2026-07-12.md §7.7.7
    for the Granite failure mode):

    1. **Markdown code blocks** — standard ```python ... ``` form
    2. **Structured JSON** — {"code": "..."} form (when structured=True)
    3. **Bare Python** — def/class/import + body (most models)
    4. **Bare statements** — no function wrapper, just calls (Granite
       for some CoderEval tasks). Granite emits bare `return ...` or
       `if ...:` blocks that look like code but lack the `def` header.

    The Granite 0% problem: Granite sometimes emits a code block with
    no `def`/`class`/`import` opener (e.g. just `return x` or
    `print("hello")`). The previous version needed a header line to
    start capturing. We now detect bare-statement outputs and capture
    them via the "no def/class" branch.
    """
    if not text:
        return ""
    if is_structured:
        try:
            parsed = json.loads(text)
            code = parsed.get("code", "")
            if code:
                return code.strip()
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass  # Fallback to regex
    # Try standard markdown code-block extraction
    pattern = r"```(?:python)?\s*\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        return matches[-1].strip()
    # Try alternative code-block delimiters (Granite sometimes uses
    # single backticks or no language tag)
    alt_patterns = [
        r"```\s*\n(.*?)```",                  # no language tag
        r"`{3,}\w*\s*(.*?)`{3,}",            # 3+ backticks
    ]
    for alt in alt_patterns:
        m = re.findall(alt, text, re.DOTALL)
        if m:
            return m[-1].strip()
    # No code blocks at all — try to extract Python from plain text
    lines = text.strip().split("\n")
    result = []
    is_started = False
    for line in lines:
        stripped = line.strip()
        if line.startswith(("def ", "class ", "import ", "from ")):
            result.append(line)
            is_started = True
        elif is_started and (line.startswith(("    ", "\t")) or stripped == ""):
            result.append(line)
        elif is_started and _is_bare_statement(stripped):
            # continue capturing non-indented code lines (else/elif/except/for/if etc.)
            result.append(line)
        elif is_started:
            break
    if result:
        joined = "\n".join(result).strip()
        return _repair_indentation(joined)
    # No def/class in response — Granite may emit only bare statements
    # or single expressions. Capture everything that looks like Python.
    # Heuristic: a line is Python if it parses as a Python statement
    # (or contains a Python operator).
    code_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _is_bare_statement(stripped):
            code_lines.append(stripped.rstrip(","))
    if code_lines:
        return "\n".join(code_lines)
    # Last-resort fallback: if the whole response looks like code
    # (high ratio of `=` and `()`), return it as-is
    if text and sum(c in text for c in "=():") > len(text) * 0.05:
        return text.strip()
    return ""


def _repair_indentation(code: str, max_iter: int = 10) -> str:
    """Re-indent malformed LLM output so it parses as a Python block.

    Detects block headers (def/class/if/...) and normalizes the following
    lines to 4-space indent levels, handling dedents for else/elif/
    except/finally and comment-only bodies (pass insertion). Used for
    bare-statement and Granite-style outputs extracted by extract_code().
    """
    _BLOCK_HEADER = re.compile(
        r"^(?:def |class |if |elif |else:|for |while |with |try:|except(?: |:)|finally:)"
    )
    _TOP_LEVEL = re.compile(r"^(?:def |class |async\s+def )")
    for _ in range(max_iter):
        try:
            compile(code, "<repair>", "exec")
            return code
        except (IndentationError, TabError):
            pass
        except SyntaxError:
            pass
        lines = code.split("\n")
        result = []
        indent_level = 0
        for _, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                result.append(line)
                continue
            is_header = bool(_BLOCK_HEADER.match(stripped))
            if re.match(r"^(?:else:|elif |except(?: |:)|finally:)", stripped) and indent_level > 0:
                indent_level -= 1
            current_indent = len(line) - len(line.lstrip())

            if current_indent == 0 and _TOP_LEVEL.match(stripped) and indent_level > 0:
                indent_level = 0

            if current_indent > 0 and current_indent < indent_level * 4:
                new_level = current_indent // 4
                indent_level = min(indent_level, new_level)

            expected_indent = indent_level * 4
            if indent_level > 0 and (not line.startswith(("    ", "\t")) or current_indent < expected_indent):
                result.append("    " * indent_level + stripped)
            else:
                result.append(line)
            if is_header:
                indent_level += 1
        # Detect block header without body and insert pass
        new_lines = []
        for i, line in enumerate(result):
            new_lines.append(line)
            stripped = line.strip()
            if _BLOCK_HEADER.match(stripped):
                # Check next line(s) after header
                j = i + 1
                while j < len(result) and not result[j].strip():
                    j += 1
                has_body = j < len(result) and (result[j].startswith(("    ", "\t"))
                                                 or _is_bare_statement(result[j].strip()))
                if not has_body:
                    indent = len(line) - len(line.lstrip()) + 4
                    new_lines.append(" " * indent + "pass")
        code = "\n".join(new_lines)
    return code


def _is_block_header(line: str) -> bool:
    """Check whether a line is a block header without body (def, class, if, for, etc.)"""
    stripped = line.strip()
    return bool(re.match(
        r"^(?:def |class |if |elif |else:|for |while |with |try:|except(?: |:)|finally:)", stripped
    ))


def _is_bare_statement(line: str) -> bool:
    """Check if a line looks like a Python statement (bare, no natural language prefix)."""
    if len(line) < 3:
        return False
    # Python assignment or compound assignment
    if re.match(r"^[a-zA-Z_][\w.]*\s*(?::\s*[\w[\]{}, \"]+)?\s*=(?!=)", line):
        return True
    # Increment/decrement
    if re.match(r"^[a-zA-Z_][\w.]*\s*[+\-*/%]=?", line):
        return True
    # Function/method call
    if re.match(r"^[a-zA-Z_][\w.]*(?:\[.*?\])*\s*\(", line):
        return True
    # Import variants
    if re.match(r"^(?:import|from)\s+", line):
        return True
    # return / yield / raise / pass / break / continue
    if re.match(r"^(?:return|yield|raise|pass|break|continue)\b", line):
        return True
    # if / for / while / with / try (without trailing content that is natural language)
    if re.match(r"^(?:if|elif|else|for|while|with|try|except|finally)\s", line):
        return True
    # @decorator
    if line.startswith("@"):
        return True
    # Comment-only lines (not "here is" explanations)
    if re.match(r"^#\s*(?!.*?\b(?:here|this|the|we|is|are|will|should|can)\b)", line, re.IGNORECASE):
        return True
    # Lambda or walrus
    if re.match(r"^lambda\s", line) or ":=" in line:
        return True
    return False


# --- Sandbox for safe code execution ---
# Executes LLM-generated code in a subprocess with restricted builtins.
# Blocks dangerous modules (os, subprocess, shutil, socket, etc.)
# and unwanted builtins (open, eval, exec, __import__ for blocked modules).

import json as _json
import os as _os
import subprocess as _subprocess
import tempfile as _tempfile

from sandbox_worker import (
    SANDBOX_MAX_OUTPUT_BYTES as _SANDBOX_MAX_OUTPUT_BYTES,
)
from windows_job_object import WindowsJobObject, WindowsJobObjectError

SANDBOX_MEMORY_LIMIT_BYTES = 1024 * 1024 * 1024
SANDBOX_ENV_ALLOWLIST = frozenset({
    "COMSPEC", "LOCALAPPDATA", "NUMBER_OF_PROCESSORS", "OS", "PATH", "PATHEXT",
    "PROCESSOR_ARCHITECTURE", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)",
    "PROGRAMW6432", "SYSTEMDRIVE", "SYSTEMROOT", "USERPROFILE", "WINDIR",
})
SANDBOX_SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")


def _sandbox_environment(tmpdir: str) -> dict[str, str]:
    """Build the small environment needed by local scientific libraries."""
    env = {
        key: value
        for key, value in _os.environ.items()
        if key.upper() in SANDBOX_ENV_ALLOWLIST
        and not any(marker in key.upper() for marker in SANDBOX_SECRET_MARKERS)
    }
    env.update({
        "PYTHONIOENCODING": "utf-8",
        "PYTHONNOUSERSITE": "1",
        "TEMP": tmpdir,
        "TMP": tmpdir,
        "MPLCONFIGDIR": _os.path.join(tmpdir, ".matplotlib"),
        "HF_HOME": _os.path.join(tmpdir, ".hf"),
        "MPLBACKEND": "Agg",
    })
    return env


def _build_sandbox_script(code_string: str, should_capture_state: bool = False, tests: list[str] | None = None) -> str:
    """Build the JSON request consumed by ``sandbox_worker.py``."""
    return _json.dumps({
        "code": code_string,
        "capture_state": should_capture_state,
        "tests": tests,
    }, ensure_ascii=False, separators=(",", ":"))


def _run_sandbox(script: str, timeout: int = TIMEOUT_EXEC) -> SandboxResult:
    """Run one JSON worker request under a Windows Job Object."""
    with _tempfile.TemporaryDirectory(prefix="sandbox_") as _tmpdir:
        worker_path = _os.path.join(_os.path.dirname(__file__), "sandbox_worker.py")
        command = [sys.executable, "-I", "-B", "-X", "utf8", worker_path]
        creationflags = 0
        job: WindowsJobObject | None = None
        if _os.name == "nt":
            creationflags = getattr(_subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            creationflags |= getattr(_subprocess, "CREATE_SUSPENDED", 0x00000004)
        process = None
        try:
            if _os.name == "nt":
                job = WindowsJobObject(SANDBOX_MEMORY_LIMIT_BYTES)
            process = _subprocess.Popen(
                command,
                stdin=_subprocess.PIPE,
                stdout=_subprocess.PIPE,
                stderr=_subprocess.PIPE,
                cwd=_tmpdir,
                env=_sandbox_environment(_tmpdir),
                creationflags=creationflags,
            )
            if job is not None:
                job.assign(process)
                job.resume(process)
            stdout_data, stderr_data = process.communicate(script.encode("utf-8"), timeout=timeout)
            out = _decode_worker_output(stdout_data or b"")
            for line in out.splitlines():
                if line.startswith("__SANDBOX__"):
                    try:
                        return _json.loads(line[len("__SANDBOX__"):])
                    except _json.JSONDecodeError:
                        continue
            stderr = _decode_worker_output(stderr_data or b"").strip()
            if stderr:
                return {"ok": False, "error": stderr[:300], "state": None, "passed": 0, "total": 0}
            return {"ok": False, "error": "Sandbox worker exited without a result", "state": None, "passed": 0, "total": 0}
        except WindowsJobObjectError as exc:
            if process is not None:
                process.kill()
            return {"ok": False, "error": f"Job Object setup failed: {exc}", "state": None, "passed": 0, "total": 0}
        except _subprocess.TimeoutExpired:
            if job is not None:
                job.terminate()
            elif process is not None:
                process.kill()
            if process is not None:
                try:
                    process.communicate(timeout=2)
                except _subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
            return {"ok": False, "error": f"Timeout ({timeout}s)", "state": None, "passed": 0, "total": 0}
        finally:
            if job is not None:
                job.close()


def _decode_worker_output(data: bytes) -> str:
    """Decode bounded worker output without retaining untrusted excess data."""
    if len(data) > _SANDBOX_MAX_OUTPUT_BYTES:
        data = data[-_SANDBOX_MAX_OUTPUT_BYTES:]
    return data.decode("utf-8", errors="replace")


def exec_sandboxed(code: str, timeout: int = TIMEOUT_EXEC) -> tuple[bool, str | None]:
    """Execute code in the sandbox subprocess. Returns (ok, error)."""
    script = _build_sandbox_script(code)
    res = _run_sandbox(script, timeout)
    return res["ok"], (res["error"] if not res["ok"] else None)


DS1000_DIR = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "ds1000_official")
_TIMEOUT_DS1000 = 120  # offizielles DS1000-Timeout

def _unwrap_solution_for_insert(solution: str, setup_code: str) -> str:
    """If exec_context has [insert] in a function block,
    and the solution defines a function, take only the body.

    Improvements over the previous implementation (see Code-Review
    2026-07-12.md §7.7.3 for the original failure modes on
    Granite models):

    1. Handle multiple `[insert]` markers (DS1000 problems with
       helper functions sometimes have nested insertion points).
    2. Skip comment-only lines when looking for the FIRST def/class
       line in the solution (Granite sometimes emits a docstring
       that confuses the previous code).
    3. When the solution has NO def/class line but the setup
       expects one, wrap the entire solution in a function with
       a `pass` fallback (instead of just indenting).
    4. When the function names differ, generate a synthetic
       wrapper function with the expected name and a call to the
       model's function.
    """
    import re as _re
    # Multiple [insert] markers can appear in complex DS1000 problems
    m = _re.search(r'exec_context\s*=\s*r?"""(.*?)"""', setup_code, _re.DOTALL)
    if not m:
        return solution
    ctx = m.group(1)
    if "[insert]" not in ctx:
        return solution
    # Take the LAST [insert] block (innermost in nested cases)
    parts = ctx.split("[insert]")
    if len(parts) > 2:
        # Multiple [insert] - the meaningful one is the deepest
        before = parts[-2].strip()
    else:
        before = parts[0].strip()
    if not before:
        return solution
    last = before.split("\n")[-1].strip()
    _BH = r"^(?:def |class |if |elif |else:|for |while |with |try:|except(?: |:)|finally:)"
    if not _re.match(_BH, last):
        return solution  # [insert] at top level -> ok
    # Extract function from exec_context header
    ef = _re.match(r"def\s+(\w+)", last)
    exec_func = ef.group(1) if ef else None
    # In the solution, look for the FIRST def/class line (skipping
    # comment-only and docstring-only lines that Granite emits first)
    sol = solution.strip()
    sol_lines = sol.split("\n")
    def_idx = None
    def_line = None
    for i, line in enumerate(sol_lines):
        stripped = line.strip()
        # Skip empty lines and pure-comment lines
        if not stripped or stripped.startswith("#") or stripped.startswith('"""') \
                or stripped.startswith("'''"):
            continue
        if _re.match(_BH, stripped):
            def_idx = i
            def_line = stripped
            break
    if def_idx is not None:
        # def/class found -> compare function names
        sf = _re.match(r"def\s+(\w+)", def_line)
        sol_func = sf.group(1) if sf else None
        if exec_func and sol_func and exec_func != sol_func:
            # Different function name → include the model's function
            # definition AND a synthetic wrapper that calls it.
            indent = "    "
            wrapped = (
                solution + "\n\n"
                f"def {exec_func}(*args, **kwargs):\n"
                f"{indent}return {sol_func}(*args, **kwargs)\n"
            )
            return wrapped
        # Unwrap: remove the def/class line, keep only the body.
        # Normalize indentation: find minimum indent of non-empty body lines,
        # dedent by that amount, then re-indent to 4 spaces.
        raw_body = list(sol_lines[def_idx + 1:])
        while raw_body and not raw_body[0].strip():
            raw_body.pop(0)
        if not raw_body:
            return "    pass"
        # Find minimum leading whitespace in non-empty lines
        min_indent = None
        for line in raw_body:
            if line.strip():
                ws = len(line) - len(line.lstrip())
                if min_indent is None or ws < min_indent:
                    min_indent = ws
        if min_indent is None:
            min_indent = 0
        # Dedent and re-indent to 4 spaces
        norm = []
        for line in raw_body:
            if line.strip():
                norm.append("    " + line[min_indent:])
            else:
                norm.append(line)
        # Check whether the body contains only comments/blank lines
        has_real_stmt = any(
            ln.strip() and not ln.strip().startswith("#")
            for ln in norm
        )
        if not has_real_stmt:
            return "    pass"
        return "\n".join(norm)
    # No def/class in the solution (Code-Review 2026-07-18 §6.4: Prio 2.2
    # fix). Granite sometimes emits only bare statements (e.g. "return x * 2")
    # without a wrapping def. When the setup expects a function with a
    # known name, we wrap the body in a synthetic `def expected_func(...):`
    # that contains the model's body, so the exec_context can be exec'd.
    # When the setup has no recognizable def name (exec_func is None),
    # we just indent the body so it plugs into the [insert] position.
    if exec_func:
        indent = "    "
        body_lines = sol_lines
        wrapped = (
            f"def {exec_func}(*args, **kwargs):\n"
            + "\n".join(indent + line if line.strip() else line
                        for line in body_lines)
        )
        return wrapped
    # Setup has no recognizable def → just indent the body.
    indent = "    "
    return indent + ("\n" + indent).join(sol_lines)


def _eval_log(msg: str) -> None:
    """Per-Task-Evaluierungs-Details nach stderr (Punkt 2a).

    stdout bleibt fuer Fortschrittsbalken + Zusammenfassung frei; die
    Details stehen im Subprozess-stderr bzw. in der Per-Task-CSV.
    """
    print(f"    [EVAL] {msg}", file=sys.stderr)


def _try_ds1000_harness(generated_code: str, setup_code: str) -> tuple[float, str] | None:
    """Run the official DS1000 harness (test_execution) against the code.

    Only usable when setup_code contains ``test_execution``; returns None
    to signal "not applicable". The solution is unwrapped for [insert]
    positions and matplotlib incompatibilities patched before execution.
    Returns (score, detail); on failure the unpatched original code is
    retried once before giving up.
    """
    if not setup_code or "test_execution" not in setup_code:
        return None
    if DS1000_DIR not in sys.path:
        sys.path.insert(0, DS1000_DIR)
    from execution import check_correctness
    unwrapped = _unwrap_solution_for_insert(generated_code, setup_code)
    # Patch common matplotlib API incompatibilities BEFORE running the
    # harness. Some models (Granite, Qwen3.6) emit `plt.set_xticklabels(...)`
    # which doesn't exist in modern matplotlib. We forward-port those
    # calls to `ax.set_xticklabels(...)` so the harness code doesn't
    # AttributeError. See Code-Review_2026-07-12.md §7.7.3.
    patched_code = _patch_matplotlib_compat(unwrapped)
    test_program = (
        setup_code + "\n"
        + f"code = {_json.dumps(patched_code)}\n"
        + "test_execution(code)\n"
    )
    if "test_string(" in setup_code:
        test_program += "test_string(code)\n"
    result = check_correctness(test_program, timeout=_TIMEOUT_DS1000)
    if result["passed"]:
        _eval_log("DS1000-Harness: PASSED")
        return 1.0, "OK (DS1000-Harness)"
    # Fallback: if unwrapping did not help, try with original
    if patched_code != generated_code:
        test_program2 = (
            setup_code + "\n"
            + f"code = {_json.dumps(generated_code)}\n"
            + "test_execution(code)\n"
        )
        result2 = check_correctness(test_program2, timeout=_TIMEOUT_DS1000)
        if result2["passed"]:
            _eval_log("DS1000-Harness: PASSED (original)")
            return 1.0, "OK (DS1000-Harness)"
        _eval_log(f"DS1000-Harness: FAILED -> {result['result']}")
        return 0.0, f"Harness error: {result['result']}"
    _eval_log(f"DS1000-Harness: FAILED -> {result['result']}")
    return 0.0, f"Harness error: {result['result']}"


def _patch_matplotlib_compat(code: str) -> str:
    """Forward-port deprecated matplotlib pyplot calls to their
    Axes equivalents. Models (Granite, Qwen3.6) emit these old
    forms which AttributeError in matplotlib >= 3.5.

    Currently handled:
      - ``plt.set_xticklabels(...)`` -> ``plt.gca().set_xticklabels(...)``
      - ``plt.set_yticklabels(...)`` -> ``plt.gca().set_yticklabels(...)``
      - ``plt.set_xlabel(...)``    -> ``plt.gca().set_xlabel(...)``
      - ``plt.set_ylabel(...)``    -> ``plt.gca().set_ylabel(...)``
      - ``plt.set_title(...)``     -> ``plt.gca().set_title(...)``

    The functions are rewritten in-place; the original code is
    otherwise unchanged. We use simple regex substitution to avoid
    tokenizing the generated code.
    """
    if "plt." not in code:
        return code
    import re as _re
    # Map old -> new for the most common offenders
    patches = [
        (r"plt\.set_xticklabels\(", "plt.gca().set_xticklabels("),
        (r"plt\.set_yticklabels\(", "plt.gca().set_yticklabels("),
        (r"plt\.set_xlabel\(",     "plt.gca().set_xlabel("),
        (r"plt\.set_ylabel\(",     "plt.gca().set_ylabel("),
        (r"plt\.set_title\(",      "plt.gca().set_title("),
    ]
    out = code
    for pat, repl in patches:
        out = _re.sub(pat, repl, out)
    return out


def evaluate_code(generated_code: str, entry_point: str, tests_field: Any, reference_code: str = "", setup_code: str = "") -> tuple[float, str]:
    """Score generated code through one of four evaluation modes.

    1. Entry-point triage (CoderEval): fail early when the requested
       function is missing.
    2. DS1000 harness when setup_code defines test_execution.
    3. Namespace comparison: run reference and generated code in the
       sandbox and compare state keys not provided by setup_code.
    4. Reference-as-tests or direct test execution in the sandbox.

    Returns (score 0.0-1.0, human-readable detail).
    """
    if not generated_code:
        return 0.0, "No code generated"

    tests = parse_tests_field(tests_field)
    # Entry-Point-Triage: nur beim direkten Tests-Pfad (CoderEval), wo die
    # aufgerufene Funktion auch wirklich benoetigt wird. DS1000-Harness und
    # Namespace-/Bare-Execution verzichten darauf (entry_point dort leer oder
    # die Signatur steckt im setup_code).
    if tests and entry_point and not re.search(r"(?m)^\s*def\s+" + re.escape(entry_point) + r"\s*\(", generated_code):
        return 0.0, f"Entry point '{entry_point}' not found in code"

    # --- DS1000-Harness (test_execution from code_context) ---
    if not tests and setup_code and "test_execution" in setup_code:
        _eval_log("Trying DS1000-Harness ...")
        result = _try_ds1000_harness(generated_code, setup_code)
        if result is not None:
            return result
        _eval_log("Harness not usable -> falling back to namespace comparison")

    # --- Namespace comparison (Reference vs Generated) ---
    if not tests and reference_code and setup_code:
        ref_combined = setup_code + "\n" + reference_code
        script = _build_sandbox_script(ref_combined, capture_state=True)
        res = _run_sandbox(script)
        if not res["ok"]:
            return 0.0, f"Reference error: {res['error']}"
        ref_state = res.get("state", {})
        setup_keys = set(ref_state.keys()) | {"__builtins__"}

        gen_combined = setup_code + "\n" + generated_code
        script = _build_sandbox_script(gen_combined, capture_state=True)
        res = _run_sandbox(script)
        if not res["ok"]:
            return 0.0, f"Code error: {res['error']}"
        gen_state = res.get("state", {})

        # Only compare state keys that are NOT in setup_keys
        ref_only = {k: v for k, v in ref_state.items() if k not in setup_keys}
        gen_only = {k: v for k, v in gen_state.items() if k not in setup_keys}

        if not ref_only:
            _eval_log("Namespace comparison: no comparable outputs -> 1.0")
            return 1.0, "OK (Namespace: no outputs)"

        matched = 0
        for k, ref_val in ref_only.items():
            gen_val = gen_only.get(k)
            if gen_val == ref_val:
                matched += 1
        score = matched / len(ref_only)
        _eval_log(f"Namespace comparison: {matched}/{len(ref_only)} correct")
        return score, f"Namespace: {matched}/{len(ref_only)}"

    if not tests and reference_code:
        tests = [reference_code]

    # --- Direct tests ---
    if not tests:
        # Only execute code, no tests
        combined = ""
        if setup_code:
            combined += setup_code + "\n"
        combined += generated_code
        ok, err = exec_sandboxed(combined)
        if not ok:
            return 0.0, f"Code error: {err}"
        return 1.0, "OK (no tests)"

    # With tests: bundle everything into one sandbox run
    combined_code = ""
    if setup_code:
        combined_code += setup_code + "\n"
    combined_code += generated_code

    script = _build_sandbox_script(combined_code, tests=tests)
    res = _run_sandbox(script)
    if not res["ok"]:
        return 0.0, f"Code error: {res['error']}"

    passed = res.get("passed", 0)
    total = res.get("total", 0)
    _eval_log(f"Direct tests: {passed}/{total} passed")
    return passed / total if total > 0 else 1.0, f"Tests: {passed}/{total}"


def _get_model_config(model_identifier: str | None, benchmark_category: str = "coding", is_thinking_enabled: bool = False) -> ModelConfig:
    """Get merged config via benchmark_config.get_model_config()."""
    return get_model_config(model_identifier or "", category=benchmark_category, is_thinking_enabled=is_thinking_enabled)


# ── Benchmark-Name → Kategorie-Mapping (Custom-Pipeline) ──
# DS1000 und CoderEval sind beide Coding-Benchmarks.
BENCHMARK_CATEGORY_MAP = {
    "DS1000": "coding",
    "CoderEval": "coding",
}


def get_benchmark_category(benchmark_name: str) -> str:
    """Map a benchmark name to its pipeline category (default: "coding")."""
    return BENCHMARK_CATEGORY_MAP.get(benchmark_name, "coding")


def run_task(task: dict[str, Any], task_type: str, model_identifier: str | None = None, api_model: str | None = None,
             model_config: ModelConfig | None = None, benchmark_category: str = "coding",
             native_model_identifier: str | None = None) -> TaskResult:
    """Run a single benchmark task end-to-end and return the TaskResult.

    Builds the generation parameters from the merged model config,
    applies Qwen system-message embedding when required, dispatches to
    the codereval or data_science prompt+eval pipeline, and returns a
    zero-filled error result for unknown task types.
    """
    prompt = task["prompt"]
    if model_config is None:
        model_config = _get_model_config(model_identifier, benchmark_category=benchmark_category, is_thinking_enabled=IS_THINKING_MODE)

    generation_parameters = {
        "model_identifier": api_model or model_identifier,
        "native_model_identifier": native_model_identifier or model_identifier,
        "temperature": model_config.get("temperature", 0.0),
        "top_p": model_config.get("top_p", 1.0),
        "top_k": model_config.get("top_k"),
        "min_p": model_config.get("min_p"),
        "is_thinking_enabled": model_config.get("enable_thinking"),
        "reasoning_effort": model_config.get("reasoning_effort"),
        "stop": model_config.get("stop", STOP_TOKENS_CODING),
    }

    no_system_msg = model_config.get("no_system_msg", False)
    code_only = bool(model_config.get("enable_thinking"))

    # Qwen3.5 compatibility: embed system message in user prompt
    if no_system_msg and IS_QWEN_PROMPT_MODE:
        qwen_prefix = "You are Qwen, a helpful AI assistant created by Alibaba Cloud. You are a coding expert. "
        prompt = qwen_prefix + prompt

    if task_type == "codereval":
        entry_point = task.get("entry_point", "")
        tests_field = task.get("tests", [])
        setup_code = task.get("setup_code", "")
        full_prompt = _make_codereval_prompt(prompt, entry_point, code_only=code_only)
        result = _call_and_evaluate(full_prompt, generation_parameters, model_identifier, entry_point, tests_field, "", setup_code)
        return result

    elif task_type == "data_science":
        entry_point = task.get("entry_point", "")
        tests_field = task.get("tests", [])
        reference_code = task.get("reference_code", "")
        full_prompt = _make_datascience_prompt(prompt, entry_point, code_only=code_only)
        setup_code = _extract_setup_code(task, prompt, reference_code)
        result = _call_and_evaluate(full_prompt, generation_parameters, model_identifier, entry_point, tests_field, reference_code, setup_code)
        try:
            import matplotlib.pyplot as _plt
            _plt.close("all")
        except (ImportError, AttributeError, RuntimeError):
            pass
        return result

    return {"response": None, "extracted_code": "", "score": 0.0,
            "score_detail": f"Unknown task_type: {task_type}", "latency": 0.0,
            "tokens_in": 0, "tokens_out": 0, "tokens_per_sec": 0, "thinking_tokens": 0,
            "truncated": False, "output_status": "empty", "entry_point_found": None}


# Thinking-Modelle (enable_thinking=True) neigen dazu, statt Code eine
# Erklaerung auszugeben ("No code generated" - beobachtet 2026-07-31 bei
# DeepSeek R1 Distill Qwen 14B). Haertung: finale Antwort = NUR Code in
# einem ```python-Block, Erklaerungen gehoeren in die Thinking-Phase.
_THINKING_CODE_ONLY_SUFFIX = (
    "\n\nIMPORTANT: You may reason during your thinking phase, but your FINAL "
    "answer must contain ONLY the complete Python code inside a single "
    "```python code block. No explanations, no prose, no commentary."
)


def _make_codereval_prompt(prompt: str, entry_point: str, code_only: bool = False) -> str:
    """Build the CoderEval instruction: function completion with code-only suffix."""
    full = "Complete the following Python function. Output only the function code, no additional text.\n\n" + prompt
    if entry_point:
        full += f"\n\nCreate the function `{entry_point}`."
    if code_only:
        full += _THINKING_CODE_ONLY_SUFFIX
    return full


def _make_datascience_prompt(prompt: str, entry_point: str, code_only: bool = False) -> str:
    """Build the DS1000-style instruction: complete the code with code-only suffix."""
    full = "Complete the following Python code. Only output the code, no additional text.\n\n" + prompt
    if entry_point:
        full += f"\n\nCreate the function `{entry_point}`."
    if code_only:
        full += _THINKING_CODE_ONLY_SUFFIX
    return full


def _extract_setup_code(task: dict[str, Any], prompt: str, reference_code: str) -> str:
    """Assemble the setup/execution context for a data-science task.

    Starts from the task's code_context, appends <code> blocks found
    before the SOLUTION marker in the prompt, and prepends the
    matplotlib Agg preamble when the task uses plotting libraries.
    """
    setup_code = task.get("code_context", "")
    for marker in ("# SOLUTION START", "BEGIN SOLUTION\n<code>"):
        idx = prompt.find(marker)
        if idx >= 0:
            prefix = prompt[:idx]
            code_blocks = re.findall(r"<code>(.*?)</code>", prefix, re.DOTALL)
            if code_blocks:
                setup_code += "\n" + "\n".join(code_blocks)
            else:
                setup_code += "\n" + prefix.strip()
            break
    setup_code = setup_code.strip()
    agg_needed = any(kw in (setup_code + reference_code)
                     for kw in ("matplotlib", "plt.", "seaborn"))
    if agg_needed:
        agg_setup = (
            "import matplotlib\n"
            "matplotlib.use('Agg')\n"
            "import matplotlib.pyplot as plt\n"
            "plt.ioff()\n"
        )
        setup_code = agg_setup + setup_code
    return setup_code


def _call_and_evaluate(full_prompt: str, generation_parameters: dict[str, Any], model_identifier: str | None,
                       entry_point: str, tests_field: list, reference_code: str, setup_code: str) -> TaskResult:
    """Generate an answer, extract code, classify output and evaluate it.

    Wires generate_answer -> extract_code/classify_output -> evaluate_code
    into a complete TaskResult dict, or an error result when generation
    returned nothing.
    """
    gcfg = GenerationConfig(
        prompt=full_prompt, **generation_parameters,
        response_format=STRUCTURED_OUTPUT_SCHEMA if _can_use_structured_output(model_identifier) else None
    )
    response, latency, t_in, t_out, tps, think_tok, truncated, err_type, err_detail = generate_answer(gcfg)
    if response is None:
        return {"response": None, "extracted_code": "", "score": 0.0,
                "score_detail": f"Timeout/API error ({latency:.1f}s)", "latency": latency,
                "tokens_in": t_in, "tokens_out": t_out, "tokens_per_sec": tps,
                "thinking_tokens": think_tok, "truncated": truncated,
                "output_status": "empty", "entry_point_found": None,
                "error_type": err_type, "error_detail": err_detail}
    is_structured = _can_use_structured_output(model_identifier)
    code = extract_code(response, is_structured=is_structured) if response else ""
    if not code and response:
        m = re.search(r"```(?:python)?\s*\n(.*?)```", response, re.DOTALL)
        if m:
            code = m.group(1).strip()
        else:
            code = "\n".join(
                line for line in response.strip().split("\n")
                if _is_bare_statement(line.strip())
            )
    struct = classify_output(code, response or "", is_structured, entry_point)
    score, detail = evaluate_code(code, entry_point, tests_field, reference_code, setup_code=setup_code)
    return {
        "response": response,
        "extracted_code": code,
        "output_status": struct["output_status"],
        "entry_point_found": struct["entry_point_found"],
        "score": score,
        "score_detail": detail,
        "latency": latency,
        "tokens_in": t_in,
        "tokens_out": t_out,
        "tokens_per_sec": tps,
        "thinking_tokens": think_tok,
        "truncated": truncated,
    }


def get_task_type(benchmark_file: str) -> str:
    """Map a benchmark JSONL filename to its task type ("data_science" | "codereval")."""
    mapping = {
        "data_science.jsonl": "data_science",
        "codereval_selfcontained.jsonl": "codereval",
    }
    return mapping.get(benchmark_file, "unknown")


class _TaskProgress:
    """Thread-safe single-line progress bar (Punkt 2a).

    Ersetzt die frueheren Per-Task-Ausgaben ([i/n] preview, Score-Zeilen):
    Auf dem Bildschirm laeuft nur dieser Balken, Details gehen in die CSV.
    """

    def __init__(self, total: int, enabled: bool = True) -> None:
        self.total = total
        self.enabled = enabled
        self.done = 0
        self._lock = threading.Lock()
        self._last_len = 0

    def step(self) -> None:
        with self._lock:
            self.done += 1
            if not self.enabled:
                return
            done, total = self.done, self.total
            bar_w = min(total, 50)
            filled = int(bar_w * done / total) if total > 0 else 0
            bar = "#" * filled + "." * (bar_w - filled)
            line = f"  Progress: [{bar}] {done}/{total}"
            pad = " " * max(0, self._last_len - len(line))
            print(f"\r{line}{pad}", end="", flush=True)
            self._last_len = len(line)
            if done >= total:
                print()


def benchmark_model(model_info: Any, tasks: list[dict[str, Any]], task_type: str, benchmark_name: str, monitor: Monitor, is_quiet_mode: bool = False, num_parallel: int = 1) -> tuple[list[dict[str, Any]], float | None, float, float, dict[str, Any]]:
    """Run all tasks of one benchmark against one model.

    Iterates the tasks with retries on API errors (Channel-Error markers
    are printed for the launcher), records resource peaks via the monitor
    thread and MetricsCollector, prints per-task progress, and returns
    (task_results, avg_score, avg_latency, avg_tps, collector_summary).
    "Average score: XX%" is always printed so the launcher can parse it.

    num_parallel > 1: tasks run in a ThreadPoolExecutor so LM Studio can
    serve them on multiple slots simultaneously (verified: MoE/MTP models
    load with n_slots=4, see Server-Log 04.08.2026). Result order is
    preserved; the monitor samples one peak window over the whole batch
    (per-task peaks are meaningless with overlapping requests).
    """
    is_dict = isinstance(model_info, dict)
    display_name = model_info["display"] if is_dict else model_info
    model_identifier = (
        model_info.get("registry_key", model_info["key"]) if is_dict else model_info
    )
    # Prefer exact API ID, fall back to model_identifier
    api_model = model_info.get("_api_model") if is_dict else model_identifier
    benchmark_category = get_benchmark_category(benchmark_name)
    model_config = _get_model_config(model_identifier, benchmark_category=benchmark_category, is_thinking_enabled=IS_THINKING_MODE)
    print(f"\n  Benchmark: {benchmark_name} ({benchmark_category})")
    print(f"  Model:     {display_name}")
    print(f"  Tasks:     {len(tasks)}")
    if num_parallel > 1:
        print(f"  Parallel:  {num_parallel} Worker (LM Studio Multi-Slot)")
    # Effektive Generations-Parameter anzeigen (Punkt 1): Quelle ist die
    # Sampling-Tabelle ("benchmark-table"), der Kategorie- bzw. Thinking-Fallback.
    _cfg_src = model_config.get("_source", "?")
    print(f"  Config:    temp={model_config.get('temperature')}, "
          f"top_p={model_config.get('top_p')}, "
          f"top_k={model_config.get('top_k')}, "
          f"min_p={model_config.get('min_p')}, "
          f"max_tokens={model_config.get('max_tokens')}, "
          f"thinking={model_config.get('enable_thinking')} (Quelle: {_cfg_src})")
    collector = MetricsCollector()
    collector.start()
    results = []
    def _safe(text: str) -> str:
        """Sanitize a string for safe output (lossy UTF-8 round-trip)."""
        return str(text).encode("utf-8", errors="replace").decode("utf-8")
    n_tasks = len(tasks)
    native_identifier = api_model or model_info.get("model_identifier", model_identifier)
    # Fortschrittsbalken statt Per-Task-Ausgabe (Punkt 2a): Details gehoeren
    # in die CSV (write_per_task_csv); auf dem Bildschirm reicht der Balken.
    _progress = _TaskProgress(total=n_tasks, enabled=not is_quiet_mode)

    def _run_single(task: dict[str, Any], i: int) -> dict[str, Any]:
        """Run one task with retries; returns the raw result dict.

        May execute in a worker thread (num_parallel > 1), so it must not
        touch monitor/collector state.
        """
        try:
            result = None
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    result = run_task(task, task_type, model_identifier=model_identifier, api_model=api_model, model_config=model_config,
                                      native_model_identifier=native_identifier)
                    if result is not None and result.get("error_type") is None:
                        break
                    if result is not None and result.get("error_type"):
                        err_detail = str(result.get("error_detail", "?"))
                        # Detect LM Studio Channel-Error (structured-output + lazy-grammar
                        # conflict, see Server-Log 12.07.2026 L58671/L94468). Print a
                        # marker the launcher can detect to trigger a retry with
                        # --no-structured-output.
                        if "Cannot combine structured output" in err_detail or "Channel Error" in err_detail:
                            print(f"  [CHANNEL-ERROR] {err_detail}")
                        if attempt < MAX_RETRIES:
                            warn(f"API error (Attempt {attempt}/{MAX_RETRIES}): {err_detail}")
                            time.sleep(2 ** attempt)
                except (requests.exceptions.RequestException, ConnectionError, TimeoutError) as e:
                    if attempt < MAX_RETRIES:
                        warn(f"Exception (Attempt {attempt}/{MAX_RETRIES}): {e}")
                        time.sleep(2 ** attempt)
                    else:
                        error(f"Task failed ({type(e).__name__}: {e})")
                        result = {
                            "score": 0.0,
                            "score_detail": f"Error: {e}",
                            "latency": 0.0,
                            "tokens_in": 0, "tokens_out": 0, "tokens_per_sec": 0,
                            "thinking_tokens": 0,
                            "truncated": False,
                            "thinking_anteil": 0,
                            "output_status": "empty", "entry_point_found": None,
                            "response": None,
                        }
            return result
        finally:
            _progress.step()

    def _finalize(result: dict[str, Any], i: int, peak: dict[str, float], before: dict[str, float], after: dict[str, float]) -> None:
        """Attach index/prompt/resource metrics to one result (CSV-Details, Punkt 2a).

        Per-Task-Ausgabe auf dem Bildschirm ist entfernt; die Details (Score,
        Latenz, Ressourcen) landen in der Per-Task-CSV (write_per_task_csv).
        """
        result["task_index"] = i
        result["task_prompt"] = tasks[i - 1]["prompt"]
        for k in ("cpu", "ram", "gpu", "vram"):
            result[f"{k}_before"] = before[k]
            result[f"{k}_during"] = peak.get(k, after[k])
            result[f"{k}_after"] = after[k]
        tok_out = result.get("tokens_out", 0)
        think_tok = result.get("thinking_tokens", 0)
        result["thinking_anteil"] = (think_tok / tok_out * 100) if tok_out > 0 else 0
        results.append(result)

    if num_parallel > 1:
        from concurrent.futures import ThreadPoolExecutor
        before = monitor.get_snapshot()
        monitor.start_sampling()
        with ThreadPoolExecutor(max_workers=num_parallel, thread_name_prefix="bm-task") as pool:
            raw_results = list(pool.map(_run_single, tasks, range(1, n_tasks + 1)))
        peak = monitor.stop_sampling()
        after = monitor.get_snapshot()
        for i, result in enumerate(raw_results, 1):
            collector.maybe_sample()
            _finalize(result, i, peak, before, after)
    else:
        for i, task in enumerate(tasks, 1):
            collector.maybe_sample()
            before = monitor.get_snapshot()
            monitor.start_sampling()
            result = _run_single(task, i)
            peak = monitor.stop_sampling()
            after = monitor.get_snapshot()
            _finalize(result, i, peak, before, after)
    collector.stop()
    collector_summary = collector.get_summary()
    avg_lat = sum(r["latency"] for r in results) / len(results) if results else 0
    avg_tps = sum(r["tokens_per_sec"] for r in results) / len(results) if results else 0
    think_toks = [r.get("thinking_tokens", 0) for r in results]
    tok_outs = [r.get("tokens_out", 0) for r in results]
    sum_think = sum(think_toks)
    sum_out = sum(tok_outs)
    think_ratio = (sum_think / sum_out * 100) if sum_out > 0 else 0
    trunc_n = sum(1 for r in results if r.get("truncated"))
    trunc_ratio = (trunc_n / len(results) * 100) if results else 0
    scores = [r["score"] for r in results if r["score"] is not None]
    avg_score = sum(scores) / len(scores) if scores else None
    # Always print average score for the launcher to parse, even in
    # non-interactive mode (quiet=True). The launcher's regex needs
    # "Average score: XX%" in stdout.
    if avg_score is not None:
        print(f"  Average score: {avg_score:.1%}")
    if not is_quiet_mode:
        print(f"\n  --- Result {benchmark_name} / {model_identifier} ---")
        print(f"  Average latency: {avg_lat:.1f}s")
        print(f"  Average tokens/s: {avg_tps:.1f}")
        print(f"  \u2248{think_ratio:.0f}% Thinking ratio ({sum_think}/{sum_out} tokens)")
        print(f"  Truncated: {trunc_n}/{len(results)} ({trunc_ratio:.0f}%)")
    # System metrics: from per-task peak values (monitor thread, ~5Hz during inference)
    # instead of MetricsCollector (only every 10s over entire run including idle)
    _ram_total_gb = psutil.virtual_memory().total / (1073741824)
    def _peak_avg_max(key: str, min_val: float = 0) -> tuple[float | None, float | None]:
        """Average and max of a per-task resource metric above ``min_val``."""
        vals = [r.get(key) for r in results if r.get(key) is not None and r[key] > min_val]
        if not vals:
            return None, None
        return sum(vals) / len(vals), max(vals)
    _cpu_avg, _cpu_max = _peak_avg_max("cpu_during")
    _gpu_avg, _gpu_max = _peak_avg_max("gpu_during")
    _ram_vals = [r.get("ram_during") for r in results if r.get("ram_during") is not None and r["ram_during"] > 0]
    _ram_avg_pct = (sum(_ram_vals) / len(_ram_vals) / _ram_total_gb * 100) if _ram_vals and _ram_total_gb > 0 else None
    _ram_max_pct = (max(_ram_vals) / _ram_total_gb * 100) if _ram_vals and _ram_total_gb > 0 else None
    _vram_avg, _vram_max = _peak_avg_max("vram_during")
    _gpu_temp_max = collector_summary.get("gpu_temp_max")
    for r in results:
        r["CPU_avg"] = _cpu_avg
        r["CPU_max"] = _cpu_max
        r["GPU_avg"] = _gpu_avg
        r["GPU_max"] = _gpu_max
        r["RAM_avg"] = _ram_avg_pct
        r["RAM_max"] = _ram_max_pct
        r["VRAM_GB"] = _vram_avg or _vram_max
        r["GPU_Temp_max"] = _gpu_temp_max
    return results, avg_score, avg_lat, avg_tps, collector_summary


# NOTE: Legacy-Aliase (save_csv, save_model_summary) wurden am
# 12.07.2026 entfernt (Code-Review_2026-07-12.md §3.1 D5).
# Direkt csv_writer.write_per_task_csv / write_per_model_csv nutzen.


def _safe_float(value: Any) -> float | None:
    """Convert value to float, returning None for missing/non-numeric inputs.

    Code-Review 2026-07-18 §5.2: replaces 4x repeated
    `try: x.append(float(...)) except (ValueError, TypeError, AttributeError): pass`
    blocks in parse_resource_avgs().
    """
    try:
        return float(value)
    except (ValueError, TypeError, AttributeError):
        return None


def parse_resource_avgs(task_results: list[dict[str, Any]]) -> tuple[float | None, float | None, float | None, float | None]:
    """Average CPU/RAM/GPU/VRAM "during" values across task results.

    Non-numeric or missing values are ignored (via _safe_float); returns
    (cpu, ram, gpu, vram) with None for metrics without samples.
    """
    cpu, ram, gpu, vram = [], [], [], []
    for t in task_results:
        for buf, key in ((cpu, "cpu_during"), (ram, "ram_during"),
                         (gpu, "gpu_during"), (vram, "vram_during")):
            v = _safe_float(t.get(key, 0))
            if v is not None:
                buf.append(v)
    return (
        sum(cpu)/len(cpu) if cpu else None,
        sum(ram)/len(ram) if ram else None,
        sum(gpu)/len(gpu) if gpu else None,
        sum(vram)/len(vram) if vram else None,
    )



def select_benchmark() -> list[dict[str, Any]]:
    """Interactive benchmark picker (interactive mode only).

    Prompts until a valid choice is entered; "a" returns all benchmarks,
    "q" exits. Selection syntax is parsed by parse_selection().
    """
    print("\n" + "=" * 60)
    print("  Benchmark selection")
    print("=" * 60)
    for b in BENCHMARKS:
        print(f"  [{b['key']}] {b['name']}")
    print("  [a] All benchmarks sequentially")
    print("  [q] Quit")
    while True:
        choice = input("\n  Your choice: ").strip().lower()
        if choice == "q":
            sys.exit(0)
        if choice == "a":
            return BENCHMARKS
        indices = parse_selection(choice, len(BENCHMARKS))
        if indices is not None:
            result = [BENCHMARKS[i] for i in indices]
            names = ", ".join(b["name"] for b in result)
            print(f"  -> {names}")
            return result
        print("  Invalid input.")


def select_models(available_models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Interactive model picker (interactive mode only).

    Lists the pre-filtered available models and returns the chosen ones
    ("a" = all). Exits when no models are available.
    """
    # Code-Review 2026-07-18 §4.1: EXCLUDE_KEYWORDS filtering is already
    # applied by get_available_models(); doing it again here is
    # redundant and drift-prone.
    filtered = available_models
    if not filtered:
        warn("No models found in LM Studio.")
        sys.exit(1)
    print("\n" + "-" * 50)
    print("  Available models:")
    for i, m in enumerate(filtered, 1):
        label = m["display"]
        if m.get("params"):
            label += f" ({m['params']})"
        if m.get("publisher"):
            label += f" - {m['publisher']}"
        print(f"  [{i}] {label}")
    print("  [a] Test all models")
    while True:
        choice = input("  Your choice: ").strip().lower()
        if choice == "a":
            return filtered
        indices = parse_selection(choice, len(filtered))
        if indices is not None:
            return [filtered[i] for i in indices]
        print("  Invalid input.")


def _parse_args() -> tuple[Any, int]:
    """Parse CLI arguments, apply module-global flags, seed RNG, print banner.

    Returns (args, seed). The globals IS_QWEN_PROMPT_MODE, IS_THINKING_MODE,
    HAS_STRUCTURED_OUTPUT and KEEP_RESPONSE are set from the parsed flags.
    """
    try:
        import sys as _sys
        _sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        # Python <3.7 or non-reconfigurable stdout (subprocess without TTY)
        pass
    import argparse as _ap
    _parser = _ap.ArgumentParser(description="Benchmark tool v13 (DS1000 + CoderEval)")
    _parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE,
                         help=f"Sample size per benchmark (default: {SAMPLE_SIZE})")
    _parser.add_argument("--non-interactive", action="store_true",
                         help="Skip interactive selection, run all benchmarks + models")
    _parser.add_argument("--model-key", type=str, default=None,
                         help="Model key for non-interactive mode")
    _parser.add_argument("--benchmark", type=str, default=None,
                         help="Run only this benchmark (e.g. DS1000, CoderEval)")
    _parser.add_argument("--api-model", type=str, default=None,
                         help="Exact model ID for API calls (from lms ps)")
    _parser.add_argument("--qwen-prompt", action="store_true",
                         help="Qwen3.5 compatibility: system-less prompt embedding")
    _parser.add_argument("--thinking", action="store_true",
                         help="Enable thinking mode for reasoning models")
    _parser.add_argument("--seed", type=int, default=None,
                         help="Random seed for reproducible task selection")
    _parser.add_argument("--no-structured-output", action="store_true",
                         help="Disable structured JSON output (fallback to regex code extraction)")
    _parser.add_argument("--keep-response", action="store_true",
                         help="Write full LLM response to per-task CSVs (default: truncated to 200 chars)")
    _args, _ = _parser.parse_known_args()
    global IS_QWEN_PROMPT_MODE, IS_THINKING_MODE, HAS_STRUCTURED_OUTPUT, KEEP_RESPONSE
    IS_QWEN_PROMPT_MODE = _args.qwen_prompt
    IS_THINKING_MODE = _args.thinking
    HAS_STRUCTURED_OUTPUT = not _args.no_structured_output
    KEEP_RESPONSE = _args.keep_response
    if _args.seed is not None:
        _seed = _args.seed
    else:
        random.seed()
        _seed = random.randrange(2**32)
    random.seed(_seed)

    print(f"  Random-Seed: {_seed}")
    print("  LM Studio Benchmark Tool v13 (DS1000 + CoderEval)")
    print(f"  Subsampling: {_args.sample_size} tasks per benchmark")
    print(f"  Python: {sys.version.split()[0]} ({sys.executable})")
    print()
    return _args, _seed


def _verify_environment() -> Monitor:
    """Create the resource Monitor and verify API reachability + DS1000 deps."""
    monitor = Monitor()
    if not is_api_available():
        error(f"LM Studio API not reachable: {API_BASE}")
        sys.exit(1)
    ok(f"LM Studio API: {API_BASE}")

    # Check DS1000 dependencies
    ds_deps = ["numpy", "pandas", "matplotlib", "seaborn"]
    missing = []
    for pkg in ds_deps:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        warn(f"DS1000 requires: {', '.join(missing)}")
        print("       Install missing packages with:")
        print(f"       pip install {' '.join(missing)}")
        print()
    return monitor


def _resolve_benchmarks(args: Any) -> list[dict[str, Any]]:
    """Resolve the benchmark list for non-interactive mode (with --benchmark override)."""
    benchmarks = BENCHMARKS
    if args.benchmark:
        benchmarks = [b for b in benchmarks if b["name"].lower() == args.benchmark.lower()]
        if not benchmarks:
            error(f"Benchmark '{args.benchmark}' not found. Possible: {', '.join(b['name'] for b in BENCHMARKS)}")
            sys.exit(1)
    return benchmarks


def _resolve_models(args: Any) -> list[dict[str, Any]]:
    """Resolve the model list for non-interactive mode (with --model-key override)."""
    available = get_available_models(exclude_keywords=EXCLUDE_KEYWORDS)
    if args.model_key:
        target = args.model_key.strip()
        # Tolerant match: exakte Key-Übereinstimmung ODER Basis-Key-Vergleich
        # (ohne @quant). Registry-Keys mit '@mixed' (z.B. REAP-Modelle)
        # unterscheiden sich vom LMS modelKey (ohne Quant); der Launcher
        # übergibt model_info["key"] aus get_available_models().
        try:
            from assemble_blueprint import normalize_model_name
            target_norm = normalize_model_name(target)
            target_base = target_norm.split("@")[0]
        except (ImportError, AttributeError):
            target_norm = target.lower()
            target_base = target_norm.split("@")[0]
        models = []
        for m in available:
            key = m.get("key", "")
            registry_key = m.get("registry_key", "")
            if key == target or registry_key == target:
                models.append(m)
                continue
            try:
                from assemble_blueprint import normalize_model_name
                m_norm = normalize_model_name(key)
            except (ImportError, AttributeError):
                m_norm = key.lower()
            registry_norm = normalize_model_name(registry_key) if registry_key else ""
            if (m_norm == target_norm or m_norm.split("@")[0] == target_base
                    or registry_norm == target_norm
                    or registry_norm.split("@")[0] == target_base):
                models.append(m)
        if not models:
            error(f"Model '{args.model_key}' not found.")
            sys.exit(1)
    else:
        models = available
    return models


def _run_model_loop(models: list[dict[str, Any]], benchmarks: list[dict[str, Any]],
                    monitor: Monitor, args: Any) -> list[dict[str, Any]]:
    """Run every model against every benchmark; return the summary rows.

    Skips models without a registry reasoning entry, filters broken DS1000
    tasks, subsamples per group, writes per-task and per-model CSVs via
    csv_writer, and collects per-model metric summaries.
    """
    sample_size = args.sample_size
    non_interactive = args.non_interactive
    api_model_override = args.api_model
    summary = []
    for _, model_info in enumerate(models, 1):
        model_identifier = model_info.get("registry_key", model_info["key"])
        model_display = model_info["display"]
        # Reasoning-Registry-Prüfung - ohne Eintrag überspringen
        r = _model_supports_reasoning(model_identifier)
        if r is None:
            error(f"{model_display}: reasoning nicht in Registry - "
                  "`python registry_tool.py sync` ausführen. Überspringe.")
            continue
        # Take exact API ID from parent (if set)
        if api_model_override:
            model_info["_api_model"] = api_model_override
        model_results = []
        # Model management (load/unload) is initiated ONLY by run_benchmarks.py.
        # We assume that the model is already loaded and ready.
        for bench in benchmarks:
            fp = os.path.join(DATA_DIR, bench["file"])
            if not os.path.exists(fp):
                warn(f"Missing: {fp}")
                continue
            tasks = load_jsonl(fp)
            if len(tasks) > MAX_TASKS_PER_BENCHMARK:
                print(f"\n  Loading {bench['file']} ({len(tasks)} tasks, using {MAX_TASKS_PER_BENCHMARK})")
                tasks = tasks[:MAX_TASKS_PER_BENCHMARK]
            else:
                print(f"\n  Loading {bench['file']} ({len(tasks)} tasks)")
            # DS1000: Filter tasks whose code_context uses APIs removed from
            # the current environment (e.g. scipy.interpolate.interp2d).
            tasks = _filter_broken_code_tasks(tasks)
            tt = get_task_type(bench["file"])
            tasks = subsample_tasks(tasks, tt, sample_size=sample_size)
            try:
                res, avg_s, avg_l, avg_t, cs = benchmark_model(
                    model_info, tasks, tt, bench["name"], monitor,
                    is_quiet_mode=non_interactive,
                    num_parallel=4 if sample_size >= 10 else 1,
                )
            except Exception as e:
                error(f"Benchmark {bench['name']} completely failed: {e}")
                traceback.print_exc()
                res = []
                avg_s = avg_l = avg_t = None
                cs = {}
            csv_p = csv_writer.write_per_task_csv(
                res, bench["name"], model_display,
                model_key=model_info.get("key", ""),
                sample_size=sample_size,
                keep_response=KEEP_RESPONSE,
            ) if res else ""

            avg_cpu, avg_ram, avg_gpu, avg_vram = parse_resource_avgs(res)

            cpu_max = cs.get("cpu_percent_max") if cs else None
            gpu_max = cs.get("gpu_util_max") if cs else None
            ram_max = cs.get("ram_percent_max") if cs else None
            gpu_temp_max = cs.get("gpu_temp_max") if cs else None
            vram_gb = cs.get("vram_gb_max") or cs.get("vram_gb_avg") if cs else None

            model_results.append({
                "benchmark_name": bench["name"],
                "avg_score": avg_s,
                "avg_latency": avg_l,
                "avg_tps": avg_t,
                "avg_cpu": avg_cpu,
                "avg_ram": avg_ram,
                "avg_gpu": avg_gpu,
                "avg_vram": avg_vram,
                "cpu_max": cpu_max,
                "gpu_max": gpu_max,
                "ram_max": ram_max,
                "gpu_temp_max": gpu_temp_max,
                "vram_gb": vram_gb,
            })
            summary.append({
                "Model": model_display, "Benchmark": bench["name"],
                "Tasks": len(tasks),
                "Score": f"{avg_s:.1%}" if avg_s is not None else "-",
                "Latency": f"{avg_l:.1f}s" if avg_l is not None else "-",
                "tok/s": f"{avg_t:.1f}" if avg_t is not None else "-",
                "CPU [%]": f"{avg_cpu:.0f}" if avg_cpu is not None else "-",
                "GPU [%]": f"{avg_gpu:.0f}" if avg_gpu is not None else "-",
                "RAM [GB]": f"{avg_ram:.1f}" if avg_ram is not None else "-",
                "VRAM [GB]": f"{avg_vram:.1f}" if avg_vram is not None else "-",
                "CPU_avg": f"{avg_cpu:.0f}" if avg_cpu is not None else "-",
                "CPU_max": f"{cpu_max:.0f}" if cpu_max is not None else "-",
                "GPU_avg": f"{avg_gpu:.0f}" if avg_gpu is not None else "-",
                "GPU_max": f"{gpu_max:.0f}" if gpu_max is not None else "-",
                "RAM_avg": f"{avg_ram:.1f}" if avg_ram is not None else "-",
                "RAM_max": f"{ram_max:.1f}" if ram_max is not None else "-",
                "VRAM_GB": f"{vram_gb:.1f}" if vram_gb is not None else "-",
                "GPU_Temp_max": f"{gpu_temp_max:.0f}" if gpu_temp_max is not None else "-",
                "CSV": csv_p,
            })

        if model_results:
            csv_writer.write_per_model_csv(
                model_results, model_display,
                model_key=model_info.get("key", ""),
                sample_size=sample_size,
            )
    return summary


def _print_summary(summary: list[dict[str, Any]]) -> None:
    """Print the interactive-mode SUMMARY table and write summary_*.csv."""
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    if summary:
        hdr = "{:<25} {:<20} {:<6} {:<8} {:<8} {:<8}".format(
            "Model", "Benchmark", "Tasks", "Score", "Latency", "tok/s")
        print("  " + hdr)
        print("  " + "-" * len(hdr))
        for r in summary:
            print("  {:<25} {:<20} {:<6} {:<8} {:<8} {:<8}".format(
                r["Model"][:24], r["Benchmark"][:19], r["Tasks"],
                r["Score"], r["Latency"], r["tok/s"]))
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    sp = os.path.join(RESULTS_DIR, f"summary_{ts}.csv")
    if summary:
        with open(sp, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=summary[0].keys())
            w.writeheader()
            w.writerows(summary)
        info(f"Summary: {sp}")


def main() -> None:
    """CLI entry point for the Custom pipeline (DS1000 + CoderEval).

    Orchestrates: argument parsing -> environment check -> model/benchmark
    selection -> benchmark run loop -> optional interactive SUMMARY.
    """
    args, _seed = _parse_args()
    monitor = _verify_environment()
    if args.non_interactive:
        benchmarks = _resolve_benchmarks(args)
        models = _resolve_models(args)
    else:
        warn("Interactive mode is no longer supported - use run_benchmarks.py")
        info("custom_benchmark.py only implements DS1000 + CoderEval. For HumanEval+/MBPP+/ARC/HellaSwag/TruthfulQA/IFEval/MATH-500 use run_benchmarks.py.")
        info("Start with: python run_benchmarks.py --benchmarks DS1000,CoderEval")
        benchmarks = select_benchmark()
        models = select_models(get_available_models())
        # Check whether a model is already loaded (from previous run)
        loaded = get_current_loaded_model()
        if not loaded:
            error("No model loaded. Please load a model first via run_benchmarks.py.")
            sys.exit(1)
    summary = _run_model_loop(models, benchmarks, monitor, args)
    # In non-interactive mode: skip redundant SUMMARY
    # (run_benchmarks.py generates its own summaries)
    if not args.non_interactive:
        _print_summary(summary)
    info("Benchmark complete.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        info("Aborted.")
        info("Unloading models...")
        has_unloaded_all_models()
        sys.exit(0)
    except Exception as e:
        error(str(e))
        traceback.print_exc()
        sys.exit(1)
