#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Benchmark script for local LLMs via LM Studio API – DS1000 + CoderEval (v13).

── Role in the overall system ─────────────────────────────────────────
  This script is the "Custom" pipeline of the four-pipeline architecture:
    Pipeline             Script/Tool                Responsibility
    ────────             ───────────                ─────────────
    Custom (THIS ONE)    custom_benchmark_v13.py    DS1000, CoderEval
    EvalPlus             evalplus.codegen/evaluate  HumanEval+, MBPP+
    LM-Eval              lm_eval CLI                ARC, HellaSwag, ...
    Agentic              tool_eval_bench            Tool-Use Scenarios

── Boundaries ───────────────────────────────────────────────────────
  THIS SCRIPT MUST NOT:
  - Load/unload models (that is done ONLY by run_benchmarks_v13.py)
  - Call own model management functions
  - Start other pipelines

── Invocation ──────────────────────────────────────────────────────
  Normally as subprocess of run_benchmarks_v13.py via:
    python custom_benchmark_v13.py --non-interactive --model-key ... --api-model ... --sample-size N --benchmark DS1000
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

import ast
import csv
import csv_writer as csv_writer
import json
import math
import multiprocessing
import os
import random
import re
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from typing import Any, Optional, TypedDict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import requests

# Model management from shared module (is NOT initiated from here)
# NOTE: This script imports the constants and helper functions from
# model_manager.py, but NEVER calls load/unload. The load management
# is done exclusively by run_benchmarks_v13.py as the parent
# launcher. The exact model ID is passed via --api-model.
from model_manager import (
    API_BASE, TIMEOUT_CLI, TIMEOUT_HTTP, TIMEOUT_MODEL_READY,
    TIMEOUT_HEALTH_CHECK, TIMEOUT_UNLOAD_WAIT,
    check_api_available, get_current_loaded_model,
    unload_all_models, load_model_via_lms, wait_for_model_ready,
    get_available_models, parse_selection
)
from benchmark_config import EXCLUDE_KEYWORDS, get_model_config

# Native REST API URL (for reasoning=off support – reliable thinking disable)
NATIVE_CHAT_URL = API_BASE.replace("/v1", "/api/v1/chat")

import psutil
import pynvml

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "simple_evals")
RESULTS_DIR = os.path.join(BASE_DIR, "ergebnisse")
os.makedirs(RESULTS_DIR, exist_ok=True)

TIMEOUT_LOAD_MODEL = 180
TIMEOUT_SAMPLER_JOIN = 3
TIMEOUT_EXEC = 30

# Qwen3.5 compatibility: prompt embedding instead of system message
QWEN_PROMPT_MODE = False
THINKING_MODE = False
STRUCTURED_OUTPUT = True

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

def _use_structured_output(model_key: str | None) -> bool:
    if not STRUCTURED_OUTPUT:
        return False
    if THINKING_MODE:
        return False
    if model_key:
        kl = model_key.lower()
        if any(kw in kl for kw in ("r1-distill", "deepseek", "reasoning", "think")):
            return False
        if "mamba" in kl:
            return False
    return True


SAMPLE_SIZE = 10
random.seed()

MAX_TASKS_PER_BENCHMARK = 100

MAX_TOKENS_GENERAL = 2048
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
STOP_TOKENS_CODING = ["\n```", "\n# Task", "\n// ", "<|endoftext|>"]
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


class Monitor:
    def __init__(self) -> None:
        self.cpu_percent = []
        self.gpu_percent = []
        self.ram_usage_gb = []
        self.vram_usage_gb = []
        self._sampling = False
        self._peak = {"cpu": 0, "ram": 0, "gpu": 0, "vram": 0}
        self._nvml_ok = False
        try:
            pynvml.nvmlInit()
            count = pynvml.nvmlDeviceGetCount()
            if count > 0:
                self._nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                self._nvml_ok = True
        except Exception:
            pass
        if not self._nvml_ok:
            print("  [WARN] GPU/VRAM monitoring via NVML not available")

    def _read_gpu(self) -> tuple[Optional[float], Optional[float]]:
        if not self._nvml_ok:
            return None, None
        try:
            util = pynvml.nvmlDeviceGetUtilizationRates(self._nvml_handle)
            mem = pynvml.nvmlDeviceGetMemoryInfo(self._nvml_handle)
            return util.gpu, mem.used / (1024 ** 3)
        except Exception:
            return None, None

    def _read_cpu_ram(self, interval: float = 0.3) -> tuple[float, float]:
        cpu = psutil.cpu_percent(interval=interval)
        ram = psutil.virtual_memory().used / (1024 ** 3)
        return cpu, ram

    def update(self) -> None:
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
        self.update()
        return {
            "cpu": self.cpu_percent[-1] if self.cpu_percent else 0,
            "ram": self.ram_usage_gb[-1] if self.ram_usage_gb else 0,
            "gpu": self.gpu_percent[-1] if self.gpu_percent else 0,
            "vram": self.vram_usage_gb[-1] if self.vram_usage_gb else 0,
        }

    def start_sampling(self) -> None:
        self._peak = {"cpu": 0, "ram": 0, "gpu": 0, "vram": 0}
        self._sampling = True
        import threading as _thr

        def _sample_loop() -> None:
            while self._sampling:
                cpu = psutil.cpu_percent(interval=MONITOR_SAMPLE_INTERVAL_S)
                ram = psutil.virtual_memory().used / (1024 ** 3)
                if cpu > self._peak["cpu"]:
                    self._peak["cpu"] = cpu
                if ram > self._peak["ram"]:
                    self._peak["ram"] = ram
                if self._nvml_ok:
                    try:
                        util = pynvml.nvmlDeviceGetUtilizationRates(self._nvml_handle)
                        mem = pynvml.nvmlDeviceGetMemoryInfo(self._nvml_handle)
                        gpu_val = util.gpu
                        vram_val = mem.used / (1024 ** 3)
                        if gpu_val > self._peak["gpu"]:
                            self._peak["gpu"] = gpu_val
                        if vram_val > self._peak["vram"]:
                            self._peak["vram"] = vram_val
                    except Exception:
                        pass

        self._sampler = _thr.Thread(target=_sample_loop, daemon=True)
        self._sampler.start()

    def stop_sampling(self) -> dict[str, float]:
        self._sampling = False
        if hasattr(self, "_sampler"):
            self._sampler.join(timeout=TIMEOUT_SAMPLER_JOIN)
        peak = dict(self._peak)
        self._peak = {"cpu": 0, "ram": 0, "gpu": 0, "vram": 0}
        return peak


def collect_system_metrics() -> dict[str, Any]:
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
    except Exception:
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
    except Exception:
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
        self.samples = []
        self._start_time = None
        self._last_sample_time = 0
        self._sample_interval = sample_interval

    def start(self) -> None:
        self._start_time = time.time()
        self._last_sample_time = self._start_time
        self.samples = [(0.0, collect_system_metrics())]

    def sample(self) -> None:
        if self._start_time is None:
            return
        elapsed = time.time() - self._start_time
        self.samples.append((elapsed, collect_system_metrics()))

    def maybe_sample(self) -> None:
        if self._start_time is None:
            return
        now = time.time()
        if now - self._last_sample_time >= self._sample_interval:
            self._last_sample_time = now
            self.sample()

    def stop(self) -> None:
        self.sample()
        self._start_time = None

    def _values(self, key: str) -> list[float]:
        return [s[1].get(key) for s in self.samples if s[1].get(key) is not None]

    def avg(self, key: str) -> Optional[float]:
        vals = self._values(key)
        return sum(vals) / len(vals) if vals else None

    def max(self, key: str) -> Optional[float]:
        vals = self._values(key)
        return max(vals) if vals else None

    def min(self, key: str) -> Optional[float]:
        vals = self._values(key)
        return min(vals) if vals else None

    def get_summary(self) -> dict[str, Any]:
        result = {}
        for k in ("cpu_percent", "gpu_util", "ram_percent", "ram_used_gb", "gpu_mem_used_gb", "gpu_temp", "vram_gb"):
            result[f"{k}_avg"] = self.avg(k)
            result[f"{k}_max"] = self.max(k)
        return result


def load_jsonl(filepath: str) -> list[dict[str, Any]]:
    with open(filepath, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]



def _stream_chat_completion(url: str, headers: dict[str, str], body: dict[str, Any], start_timeout: int = START_TIMEOUT, finish_timeout: int = FINISH_TIMEOUT, max_retries: int = MAX_RETRIES) -> tuple[Optional[str], float, int, int, float, int, Optional[str], Optional[str]]:
    """Streaming chat completion with dual timeout and retry logic.
    
    Uses threading to monitor start_timeout (first token) and finish_timeout
    (between tokens) independently from the SSE stream.
    Returns 8-tuple: (content, elapsed, t_in, t_out, tps, thinking_tokens, error_type, error_detail)
    """
    for attempt in range(max_retries):
        current_start_timeout = start_timeout * (RETRY_MULTIPLIER ** attempt)
        result = {"content": "", "thinking": "", "done": False, "error": None, "usage": None}
        result_lock = threading.Lock()
        cancel_event = threading.Event()

        def _set_result(key: str, value: Any) -> None:
            with result_lock:
                result[key] = value

        def _result(key: str) -> Any:
            with result_lock:
                return result.get(key)

        def _worker() -> None:
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
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            with result_lock:
                                if delta.get("content"):
                                    result["content"] += delta["content"]
                                if delta.get("reasoning_content"):
                                    result["thinking"] += delta["reasoning_content"]
                        except json.JSONDecodeError:
                            pass
                _set_result("done", True)
            except Exception as e:
                # Extract response body for HTTPError so the launcher can detect
                # "Cannot combine structured output constraints with lazy grammar"
                # (LM Studio Channel-Error – see Server-Log 12.07.2026 L58671).
                err_text = str(e)
                try:
                    if hasattr(e, "response") and e.response is not None:
                        resp_body = e.response.text or ""
                        if resp_body:
                            err_text = f"{err_text} | body={resp_body[:300]}"
                except Exception:
                    pass
                _set_result("error", err_text)
                _set_result("done", True)
            finally:
                if sess is not None:
                    try:
                        sess.close()
                    except Exception:
                        pass
        start = time.time()
        thread = threading.Thread(target=_worker)
        thread.daemon = True
        thread.start()
        while time.time() - start < current_start_timeout:
            with result_lock:
                done = result["done"]
                content = result["content"]
                error = result["error"]
            if done or content or error:
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
            return None, elapsed, 0, 0, 0, 0, "api_error", error_val
        with result_lock:
            has_content = bool(result["content"])
            is_done = result["done"]
        if not has_content and not is_done:
            cancel_event.set()
            thread.join(timeout=1)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return None, elapsed, 0, 0, 0, 0, "api_error", f"No response within {current_start_timeout}s (attempt {attempt+1})"
        last_content_len = 0
        stall_start = time.time()
        while time.time() - stall_start < finish_timeout:
            with result_lock:
                is_done = result["done"]
            if is_done:
                break
            with result_lock:
                current_len = len(result["content"])
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
        thinking_tokens = len(thinking_content.split()) if thinking_content else 0
        content, think_tags = strip_thinking_tokens(content_raw)
        thinking_tokens = thinking_tokens + think_tags
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)
        if tokens_in == 0 and tokens_out == 0:
            tokens_out = len(content.split()) if content else 0
        tokens_per_sec = tokens_out / full_elapsed if full_elapsed > 0 else 0
        return content, full_elapsed, tokens_in, tokens_out, tokens_per_sec, thinking_tokens, None, None
    return None, 0, 0, 0, 0, 0, "api_error", "Max retries exceeded"


def strip_thinking_tokens(text: Optional[str]) -> tuple[Optional[str], int]:
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

    See: server-log 12.07.2026 – Qwen3.6-28b thinking tokens were estimated
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
    # NB: filter() to exclude empty strings – ``str.split()`` counts
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
        print(f"  [WARN] Thinking tokens consumed entire response ({estimated_tokens} tok estimated). "
              f"Model may need enable_thinking=False in MODEL_CONFIG.")
    return cleaned, estimated_tokens


def _non_streaming_fallback(url: str, body: dict[str, Any], timeout: int) -> tuple[Optional[str], int, int, int]:
    """Non-streaming fallback, if streaming fails."""
    try:
        payload = json.dumps(body).encode("utf-8")
        req = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        raw_content = result["choices"][0]["message"]["content"]
        content, thinking_tokens = strip_thinking_tokens(raw_content)
        usage = result.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)
        return content, tokens_in, tokens_out, thinking_tokens
    except (URLError, HTTPError, json.JSONDecodeError, KeyError, TimeoutError) as e:
        print(f"\n[ERROR] API error (Fallback, {type(e).__name__}): {e}")
        return None, 0, 0, 0


def generate_answer(prompt: Optional[str] = None, model_key: Optional[str] = None, timeout: int = TIMEOUT_HTTP,
                    max_tokens: int = MAX_TOKENS_GENERAL, system_msg: Optional[str] = None, messages: Optional[list[dict[str, Any]]] = None,
                    temperature: float = 0.0, top_p: float = 1.0, top_k: Optional[int] = None, min_p: Optional[float] = None,
                    enable_thinking: Optional[bool] = None, reasoning_effort: Optional[str] = None,
                    use_streaming: bool = True, stop: Optional[list[str]] = None,
                    response_format: Optional[dict] = None) -> tuple[Optional[str], float, int, int, float, int, Optional[str], Optional[str]]:
    if messages is None:
        messages = []
        if system_msg:
            messages.append({"role": "system", "content": system_msg})
        messages.append({"role": "user", "content": prompt})
    # Native REST API path: reliable thinking off via reasoning="off" parameter
    if enable_thinking is False:
        return _generate_answer_native(
            model_key=model_key or "local-model",
            messages=messages, prompt=prompt, system_msg=system_msg,
            temperature=temperature, top_p=top_p, max_tokens=max_tokens,
            top_k=top_k, min_p=min_p, timeout=timeout,
        )
    body = {
        "model": model_key or "local-model",
        "messages": messages,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
    }
    if top_k is not None:
        body["top_k"] = top_k
    if min_p is not None:
        body["min_p"] = min_p
    if enable_thinking is not None or reasoning_effort is not None:
        kwargs = {}
        if enable_thinking is not None:
            kwargs["enable_thinking"] = enable_thinking
        if reasoning_effort is not None:
            kwargs["reasoning_effort"] = reasoning_effort
        body["chat_template_kwargs"] = kwargs
    # Gemma 4: <|channel>thought tag is hardcoded in GGUF jinja template,
    # extra_body override is ignored. Force-disable via system prompt.
    if enable_thinking is False and model_key and "gemma" in model_key.lower():
        if not any(m.get("role") == "system" for m in messages):
            messages.append({"role": "system", "content": "Do NOT use thinking or reasoning. Answer directly without <|channel>thought tags."})
    if stop:
        body["stop"] = stop
    if response_format is not None:
        body["response_format"] = response_format
    url = f"{API_BASE}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if use_streaming:
        content, elapsed, t_in, t_out, tps, think_tok, err_type, err_detail = _stream_chat_completion(url, headers, body)
        if content is not None:
            return content, elapsed, t_in, t_out, tps, think_tok, err_type, err_detail
        print(f"\n[WARN] Streaming failed ({err_detail}), fallback without streaming...")
    start = time.time()
    content, t_in, t_out, think_tok = _non_streaming_fallback(url, {**body, "stream": False}, timeout)
    elapsed = time.time() - start
    if content is not None:
        tokens_per_sec = t_out / elapsed if elapsed > 0 else 0
        return content, elapsed, t_in, t_out, tokens_per_sec, think_tok, None, None
    return None, elapsed, t_in, t_out, 0, think_tok, "api_error", "Fallback also failed"


def _generate_answer_native(
    model_key: str,
    messages: list[dict[str, Any]],
    prompt: Optional[str],
    system_msg: Optional[str],
    temperature: float,
    top_p: float,
    max_tokens: int,
    top_k: Optional[int],
    min_p: Optional[float],
    timeout: int,
) -> tuple[Optional[str], float, int, int, float, int, Optional[str], Optional[str]]:
    """Use LM Studio native REST API with reasoning='off' to disable thinking.

    The native API has a dedicated reasoning parameter that reliably controls
    thinking behavior, unlike chat_template_kwargs which may be ignored by
    the OpenAI-compatible endpoint.
    """
    system_prompt = None
    input_text = prompt or ""
    for m in messages:
        if m.get("role") == "system" and not system_prompt:
            system_prompt = m.get("content", "")
        elif m.get("role") == "user":
            input_text = m.get("content", "")

    body: dict[str, Any] = {
        "model": model_key,
        "input": input_text,
        "temperature": temperature,
        "top_p": top_p,
        "max_output_tokens": max_tokens,
        "reasoning": "off",
    }
    if system_prompt:
        body["system_prompt"] = system_prompt
    if top_k is not None:
        body["top_k"] = top_k
    if min_p is not None:
        body["min_p"] = min_p

    headers = {"Content-Type": "application/json"}
    try:
        payload = json.dumps(body).encode("utf-8")
        req = Request(NATIVE_CHAT_URL, data=payload, headers=headers, method="POST")
        start = time.time()
        with urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        elapsed = time.time() - start

        output = result.get("output", [])
        content_parts = []
        thinking_content = ""
        for item in output:
            if item.get("type") == "message":
                content_parts.append(item.get("content", ""))
            elif item.get("type") == "reasoning":
                thinking_content += item.get("content", "")

        raw_content = "".join(content_parts)
        content, think_tags = strip_thinking_tokens(raw_content)
        thinking_tokens = len(thinking_content.split()) if thinking_content else 0
        thinking_tokens += think_tags

        stats = result.get("stats", {})
        tokens_in = stats.get("input_tokens", 0)
        tokens_out = stats.get("total_output_tokens", 0)
        tokens_per_sec = stats.get("tokens_per_second", 0)
        if tokens_per_sec == 0 and elapsed > 0:
            tokens_per_sec = tokens_out / elapsed

        return content, elapsed, tokens_in, tokens_out, tokens_per_sec, thinking_tokens, None, None
    except (URLError, HTTPError, json.JSONDecodeError, KeyError, TimeoutError) as e:
        err_text = str(e)
        try:
            if hasattr(e, "read"):
                resp_body = e.read().decode("utf-8", errors="replace")[:300]
                err_text = f"{err_text} | body={resp_body}"
        except Exception:
            pass
        return None, 0, 0, 0, 0, 0, "api_error", err_text


def extract_code(text: Optional[str], structured: bool = False) -> str:
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
    if structured:
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
    started = False
    for line in lines:
        stripped = line.strip()
        if line.startswith(("def ", "class ", "import ", "from ")):
            result.append(line)
            started = True
        elif started and (line.startswith(("    ", "\t")) or stripped == ""):
            result.append(line)
        elif started and _is_bare_statement(stripped):
            # continue capturing non-indented code lines (else/elif/except/for/if etc.)
            result.append(line)
        elif started:
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
        for i, line in enumerate(lines):
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
                if new_level < indent_level:
                    indent_level = new_level

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


def _looks_like_block_header(line: str) -> bool:
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
import tempfile as _tempfile
import textwrap as _textwrap
import subprocess as _subprocess
import os as _os

_SANDBOX_SAFE_BUILTINS = frozenset({
    'abs', 'all', 'any', 'bin', 'bool', 'bytearray', 'bytes', 'callable',
    'chr', 'complex', 'dict', 'dir', 'divmod', 'enumerate', 'filter',
    'float', 'format', 'frozenset', 'getattr', 'hasattr', 'hash', 'hex',
    'id', 'int', 'isinstance', 'issubclass', 'iter', 'len', 'list', 'map',
    'max', 'min', 'next', 'object', 'oct', 'ord', 'pow', 'print',
    'property', 'range', 'repr', 'reversed', 'round', 'set', 'slice',
    'sorted', 'str', 'sum', 'super', 'tuple', 'type', 'zip',
    'True', 'False', 'None', 'staticmethod', 'classmethod',
    'delattr', 'setattr', 'memoryview', 'bytes', 'bytearray',
    'reversed', 'sorted', 'iter', 'next', 'enumerate', 'zip', 'map',
    'filter', 'all', 'any', 'sum', 'min', 'max', 'abs', 'round',
    'pow', 'divmod', 'hash', 'id', 'len', 'repr', 'ascii', 'ord',
    'chr', 'bin', 'hex', 'oct', 'format', 'bool', 'int', 'float',
    'complex', 'str', 'bytes', 'bytearray', 'list', 'tuple', 'set',
    'frozenset', 'dict', 'type', 'object', 'range', 'slice',
    'property', 'staticmethod', 'classmethod', 'super',
})

_SANDBOX_BLOCKED_MODULES = frozenset({
    'subprocess', 'shutil', 'ctypes', 'socket',
    'http', 'urllib', 'ftplib', 'smtplib', 'telnetlib',
    'multiprocessing', 'threading', 'webbrowser',
    'signal', 'asyncio', 'code', 'codeop', 'pdb',
    'traceback', 'inspect', 'antigravity', 'tkinter',
    'platform', 'sysconfig', 'distutils',
})


def _build_sandbox_script(code_string: str, capture_state: bool = False, tests: Optional[list[str]] = None) -> str:
    """Build a sandbox script that executes code_string in a restricted namespace."""
    safe_list = _json.dumps(sorted(_SANDBOX_SAFE_BUILTINS))
    blocked_list = _json.dumps(sorted(_SANDBOX_BLOCKED_MODULES))
    code_json = _json.dumps(code_string)

    lines = [
        'import json as _js, sys as _sys',
        '',
        '_SAFE = ' + safe_list,
        '_BLOCKED = ' + blocked_list,
        '',
        '_bd = {}',
        'if isinstance(__builtins__, dict):',
        '    for _k in _SAFE:',
        '        if _k in __builtins__:',
        '            _bd[_k] = __builtins__[_k]',
        'else:',
        '    for _k in _SAFE:',
        '        _v = getattr(__builtins__, _k, None)',
        '        if _v is not None:',
        '            _bd[_k] = _v',
        '',
        '_ns = {"__builtins__": _bd}',
        '',
        'for _m in _BLOCKED:',
        '    _sys.modules.pop(_m, None)',
        '',
        '_orig_imp = _bd.get("__import__")',
        'def _safe_import(name, *args, **kwargs):',
        '    top = name.split(".")[0]',
        '    if top in _BLOCKED:',
        '        raise ImportError(f"Module {name!r} is blocked")',
        '    if _orig_imp is not None:',
        '        return _orig_imp(name, *args, **kwargs)',
        '    return __import__(name, *args, **kwargs)',
        "_bd['__import__'] = _safe_import",
        '',
        "for _bd_rm in ('exec', 'open', 'input', 'compile', 'globals', 'locals', 'vars'):",
        '    _bd.pop(_bd_rm, None)',
        '',
        '_result = {"ok": True, "error": None, "state": None, "passed": 0, "total": 0, "details": []}',
        'try:',
        '    exec(' + code_json + ', _ns)',
    ]

    if capture_state:
        lines.extend([
            '    _state = {}',
            '    for _k, _v in _ns.items():',
            "        if _k.startswith('_') or _k == '__builtins__':",
            '            continue',
            '        try:',
            '            _state[_k] = repr(_v)',
            '        except Exception:',
            '            _state[_k] = str(type(_v))',
            '    _result["state"] = _state',
        ])

    if tests is not None:
        test_items = _json.dumps(tests)
        lines.extend([
            '    _test_items = ' + test_items,
            '    _test_results = []',
            '    for _ti, _test in enumerate(_test_items):',
            '        try:',
            '            exec(_test, _ns)',
            '            _test_results.append({"index": _ti, "passed": True})',
            '        except Exception as _te:',
            '            _test_results.append({"index": _ti, "passed": False, "error": str(_te)})',
            '    _passed_cnt = sum(1 for _r in _test_results if _r["passed"])',
            '    _total_cnt = len(_test_results)',
            '    _result["ok"] = True',
            '    _result["error"] = None',
            '    _result["passed"] = _passed_cnt',
            '    _result["total"] = _total_cnt',
            '    _result["details"] = _test_results',
        ])

    lines.extend([
        'except Exception as _e:',
        '    _result = {"ok": False, "error": str(_e), "state": None, "passed": 0, "total": 0, "details": []}',
        '',
        '_print_data = _js.dumps(_result)',
        'print("__SANDBOX__" + _print_data)',
    ])

    return '\n'.join(lines)


def _run_sandbox(script: str, timeout: int = TIMEOUT_EXEC) -> dict[str, Any]:
    """Run a sandbox script as a subprocess in a temporary directory."""
    with _tempfile.TemporaryDirectory(prefix='sandbox_') as _tmpdir:
        tmppath = _os.path.join(_tmpdir, 'sandbox_script.py')
        try:
            with _os.fdopen(_os.open(tmppath, _os.O_CREAT | _os.O_WRONLY | _os.O_TRUNC, 0o644), 'w', encoding='utf-8') as f:
                f.write(script)
            result = _subprocess.run(
                [sys.executable, tmppath],
                capture_output=True, text=True, timeout=timeout,
                encoding='utf-8', errors='replace',
                env={**_os.environ, 'PYTHONIOENCODING': 'utf-8'}
            )
            out = result.stdout or ""
            for line in out.splitlines():
                if line.startswith('__SANDBOX__'):
                    try:
                        return _json.loads(line[len('__SANDBOX__'):])
                    except _json.JSONDecodeError:
                        continue
            if result.stderr:
                return {"ok": False, "error": result.stderr.strip()[:300], "state": None, "passed": 0, "total": 0}
            return {"ok": False, "error": f"Exit code {result.returncode}", "state": None, "passed": 0, "total": 0}
        except _subprocess.TimeoutExpired:
            return {"ok": False, "error": f"Timeout ({timeout}s)", "state": None, "passed": 0, "total": 0}


def exec_sandboxed(code: str, timeout: int = TIMEOUT_EXEC) -> tuple[bool, Optional[str]]:
    """Execute code in the sandbox subprocess. Returns (ok, error)."""
    script = _build_sandbox_script(code)
    res = _run_sandbox(script, timeout)
    return res["ok"], (res["error"] if not res["ok"] else None)


DS1000_DIR = _os.path.join(_os.path.dirname(__file__), 'ds1000_official')
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
        # Multiple [insert] – the meaningful one is the deepest
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
        raw_body = []
        for line in sol_lines[def_idx + 1:]:
            raw_body.append(line)
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


def _try_ds1000_harness(generated_code: str, setup_code: str) -> Optional[tuple[float, str]]:
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
        print("    [EVAL] DS1000-Harness: PASSED")
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
            print("    [EVAL] DS1000-Harness: PASSED (original)")
            return 1.0, "OK (DS1000-Harness)"
        print(f"    [EVAL] DS1000-Harness: FAILED -> {result['result']}")
        return 0.0, f"Harness error: {result['result']}"
    print(f"    [EVAL] DS1000-Harness: FAILED -> {result['result']}")
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
    if not generated_code:
        return 0.0, "No code generated"

    tests = parse_tests_field(tests_field)

    # --- DS1000-Harness (test_execution from code_context) ---
    if not tests and setup_code and "test_execution" in setup_code:
        print("    [EVAL] Trying DS1000-Harness ...")
        result = _try_ds1000_harness(generated_code, setup_code)
        if result is not None:
            return result
        print("    [EVAL] Harness not usable -> falling back to namespace comparison")

    # --- Namespace comparison (Reference vs Generated) ---
    if not tests and reference_code and setup_code:
        ref_combined = setup_code + "\n" + reference_code
        script = _build_sandbox_script(ref_combined, capture_state=True)
        res = _run_sandbox(script)
        if not res["ok"]:
            return 0.0, f"Reference error: {res['error']}"
        ref_state = res.get("state", {})
        setup_keys = set(ref_state.keys()) | {'__builtins__'}

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
            print("    [EVAL] Namespace comparison: no comparable outputs -> 1.0")
            return 1.0, "OK (Namespace: no outputs)"

        matched = 0
        for k, ref_val in ref_only.items():
            gen_val = gen_only.get(k)
            if gen_val == ref_val:
                matched += 1
        score = matched / len(ref_only)
        print(f"    [EVAL] Namespace comparison: {matched}/{len(ref_only)} correct")
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
    print(f"    [EVAL] Direct tests: {passed}/{total} passed")
    return passed / total if total > 0 else 1.0, f"Tests: {passed}/{total}"


def _get_model_config(model_key: Optional[str], benchmark_category: str = "coding", thinking: bool = False) -> dict[str, Any]:
    """Get merged config via benchmark_config.get_model_config()."""
    return get_model_config(model_key or "", category=benchmark_category, thinking=thinking)


# ── Benchmark-Name → Kategorie-Mapping (Custom-Pipeline) ──
# DS1000 und CoderEval sind beide Coding-Benchmarks.
BENCHMARK_CATEGORY_MAP = {
    "DS1000": "coding",
    "CoderEval": "coding",
}


def get_benchmark_category(benchmark_name: str) -> str:
    return BENCHMARK_CATEGORY_MAP.get(benchmark_name, "coding")


def run_task(task: dict[str, Any], task_type: str, model_key: Optional[str] = None, api_model: Optional[str] = None,
             model_config: Optional[dict[str, Any]] = None, benchmark_category: str = "coding") -> dict[str, Any]:
    prompt = task["prompt"]
    if model_config is None:
        model_config = _get_model_config(model_key, benchmark_category=benchmark_category, thinking=THINKING_MODE)

    gen_kwargs = {
        "model_key": api_model or model_key,
        "temperature": model_config.get("temperature", 0.0),
        "top_p": model_config.get("top_p", 1.0),
        "top_k": model_config.get("top_k"),
        "min_p": model_config.get("min_p"),
        "enable_thinking": model_config.get("enable_thinking"),
        "reasoning_effort": model_config.get("reasoning_effort"),
        "stop": model_config.get("stop", STOP_TOKENS_CODING),
    }

    no_system_msg = model_config.get("no_system_msg", False)
    max_tokens_task = model_config.get("max_tokens", MAX_TOKENS_GENERAL)

    # Qwen3.5 compatibility: embed system message in user prompt
    if no_system_msg and QWEN_PROMPT_MODE:
        qwen_prefix = "You are Qwen, a helpful AI assistant created by Alibaba Cloud. You are a coding expert. "
        prompt = qwen_prefix + prompt

    if task_type == "codereval":
        entry_point = task.get("entry_point", "")
        tests_field = task.get("tests", [])
        setup_code = task.get("setup_code", "")
        full_prompt = (
            "Complete the following Python function. "
            "Output only the function code, no additional text.\n\n"
            f"{prompt}"
        )
        if entry_point:
            full_prompt += f"\n\nCreate the function `{entry_point}`."
        response, latency, t_in, t_out, tps, think_tok, err_type, err_detail = generate_answer(
            full_prompt, **gen_kwargs,
            response_format=STRUCTURED_OUTPUT_SCHEMA if _use_structured_output(model_key) else None
        )
        if response is None:
            return {"response": None, "extracted_code": "", "score": 0.0,
                    "score_detail": f"Timeout/API error ({latency:.1f}s)", "latency": latency,
                    "tokens_in": t_in, "tokens_out": t_out, "tokens_per_sec": tps,
                    "thinking_tokens": think_tok, "error_type": err_type, "error_detail": err_detail}
        code = extract_code(response, structured=_use_structured_output(model_key)) if response else ""
        if not code and response:
            m = re.search(r"```(?:python)?\s*\n(.*?)```", response, re.DOTALL)
            if m:
                code = m.group(1).strip()
            else:
                code = "\n".join(
                    l for l in response.strip().split("\n")
                    if _is_bare_statement(l.strip())
                )
        score, detail = evaluate_code(code, entry_point, tests_field, "", setup_code=setup_code)
        return {
            "response": response,
            "extracted_code": code,
            "score": score,
            "score_detail": detail,
            "latency": latency,
            "tokens_in": t_in,
            "tokens_out": t_out,
            "tokens_per_sec": tps,
            "thinking_tokens": think_tok,
        }

    elif task_type == "data_science":
        entry_point = task.get("entry_point", "")
        tests_field = task.get("tests", [])
        reference_code = task.get("reference_code", "")
        full_prompt = (
            "Complete the following Python code. "
            "Only output the code, no additional text.\n\n"
            f"{prompt}"
        )
        if entry_point:
            full_prompt += f"\n\nCreate the function `{entry_point}`."

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

        response, latency, t_in, t_out, tps, think_tok, err_type, err_detail = generate_answer(
            full_prompt, **gen_kwargs,
            response_format=STRUCTURED_OUTPUT_SCHEMA if _use_structured_output(model_key) else None
        )
        if response is None:
            return {"response": None, "extracted_code": "", "score": 0.0,
                    "score_detail": f"Timeout/API error ({latency:.1f}s)", "latency": latency,
                    "tokens_in": t_in, "tokens_out": t_out, "tokens_per_sec": tps,
                    "thinking_tokens": think_tok, "error_type": err_type, "error_detail": err_detail}
        code = extract_code(response, structured=_use_structured_output(model_key)) if response else ""
        if not code and response:
            m = re.search(r"```(?:python)?\s*\n(.*?)```", response, re.DOTALL)
            if m:
                code = m.group(1).strip()
            else:
                code = "\n".join(
                    l for l in response.strip().split("\n")
                    if _is_bare_statement(l.strip())
                )
        score, detail = evaluate_code(code, entry_point, tests_field, reference_code, setup_code=setup_code)
        try:
            import matplotlib.pyplot as _plt
            _plt.close("all")
        except Exception:
            pass
        return {
            "response": response,
            "extracted_code": code,
            "score": score,
            "score_detail": detail,
            "latency": latency,
            "tokens_in": t_in,
            "tokens_out": t_out,
            "tokens_per_sec": tps,
            "thinking_tokens": think_tok,
        }

    return {"response": None, "extracted_code": "", "score": 0.0,
            "score_detail": f"Unknown task_type: {task_type}", "latency": 0.0,
            "tokens_in": 0, "tokens_out": 0, "tokens_per_sec": 0, "thinking_tokens": 0}


def get_task_type(benchmark_file: str) -> str:
    mapping = {
        "data_science.jsonl": "data_science",
        "codereval_selfcontained.jsonl": "codereval",
    }
    return mapping.get(benchmark_file, "unknown")


def benchmark_model(model_info: Any, tasks: list[dict[str, Any]], task_type: str, benchmark_name: str, monitor: Monitor, quiet: bool = False) -> tuple[list[dict[str, Any]], Optional[float], float, float, dict[str, Any]]:
    is_dict = isinstance(model_info, dict)
    display_name = model_info["display"] if is_dict else model_info
    model_key = model_info["key"] if is_dict else model_info
    # Prefer exact API ID, fall back to model_key
    api_model = model_info.get("_api_model") if is_dict else model_key
    benchmark_category = get_benchmark_category(benchmark_name)
    model_config = _get_model_config(model_key, benchmark_category=benchmark_category, thinking=THINKING_MODE)
    print(f"\n{'=' * 60}")
    print(f"  Benchmark: {benchmark_name} ({benchmark_category})")
    print(f"  Model:     {display_name}")
    print(f"  Tasks:     {len(tasks)}")
    print(f"{'=' * 60}")
    collector = MetricsCollector()
    collector.start()
    results = []
    def _safe(text: str) -> str:
        return str(text).encode('utf-8', errors='replace').decode('utf-8')
    for i, task in enumerate(tasks, 1):
        collector.maybe_sample()
        preview = task["prompt"][:70].replace("\n", " ")
        print(f"\n  [{i}/{len(tasks)}] {preview}...")
        before = monitor.get_snapshot()
        monitor.start_sampling()
        result = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                result = run_task(task, task_type, model_key=model_key, api_model=api_model, model_config=model_config)
                if result is not None and result.get("error_type") is None:
                    break
                if result is not None and result.get("error_type"):
                    err_detail = str(result.get('error_detail', '?'))
                    # Detect LM Studio Channel-Error (structured-output + lazy-grammar
                    # conflict, see Server-Log 12.07.2026 L58671/L94468). Print a
                    # marker the launcher can detect to trigger a retry with
                    # --no-structured-output.
                    if "Cannot combine structured output" in err_detail or "Channel Error" in err_detail:
                        print(f"  [CHANNEL-ERROR] {err_detail}")
                    if attempt < MAX_RETRIES:
                        print(f"  [RETRY] API error (Attempt {attempt}/{MAX_RETRIES}): {err_detail}")
                        time.sleep(2 ** attempt)
            except Exception as e:
                if attempt < MAX_RETRIES:
                    print(f"  [RETRY] Exception (Attempt {attempt}/{MAX_RETRIES}): {e}")
                    time.sleep(2 ** attempt)
                else:
                    print(f"  [ERROR] Task failed ({type(e).__name__}: {e})")
                    result = {
                        "score": 0.0,
                        "score_detail": f"Error: {e}",
                        "latency": 0.0,
                        "tokens_in": 0, "tokens_out": 0, "tokens_per_sec": 0,
                        "thinking_tokens": 0,
                        "thinking_anteil": 0,
                        "response": None,
                    }
        peak = monitor.stop_sampling()
        after = monitor.get_snapshot()
        result["task_index"] = i
        result["task_prompt"] = task["prompt"]
        for k in ("cpu", "ram", "gpu", "vram"):
            result[f"{k}_before"] = before[k]
            result[f"{k}_during"] = peak.get(k, after[k])
            result[f"{k}_after"] = after[k]
        tok_out = result.get("tokens_out", 0)
        think_tok = result.get("thinking_tokens", 0)
        result["thinking_anteil"] = (think_tok / tok_out * 100) if tok_out > 0 else 0
        if result["score"] is not None:
            detail_str = result.get("score_detail", "")
            if detail_str:
                detail_str = f" ({detail_str})"
            print(f"  Score: {result['score']:.0%}{detail_str} | "
                  f"Latenz: {result['latency']:.1f}s | "
                  f"{result['tokens_per_sec']:.1f} tok/s | "
                  f"\u2248{result.get('thinking_anteil', 0):.0f}% Thinking | "
                  f"CPU: {peak.get('cpu', after['cpu']):.0f}% | "
                  f"RAM: {peak.get('ram', after['ram']):.1f} GB | "
                  f"GPU: {peak.get('gpu', after['gpu']):.0f}% | "
                  f"VRAM: {peak.get('vram', after['vram']):.1f} GB")
        else:
            print(f"  Latenz: {result['latency']:.1f}s | "
                  f"{result['tokens_per_sec']:.1f} tok/s | "
                  f"\u2248{result.get('thinking_anteil', 0):.0f}% Thinking | "
                  f"CPU: {peak.get('cpu', after['cpu']):.0f}% | "
                  f"RAM: {peak.get('ram', after['ram']):.1f} GB | "
                  f"GPU: {peak.get('gpu', after['gpu']):.0f}% | "
                  f"VRAM: {peak.get('vram', after['vram']):.1f} GB")
        results.append(result)
    collector.stop()
    collector_summary = collector.get_summary()
    avg_lat = sum(r["latency"] for r in results) / len(results) if results else 0
    avg_tps = sum(r["tokens_per_sec"] for r in results) / len(results) if results else 0
    think_toks = [r.get("thinking_tokens", 0) for r in results]
    tok_outs = [r.get("tokens_out", 0) for r in results]
    sum_think = sum(think_toks)
    sum_out = sum(tok_outs)
    think_ratio = (sum_think / sum_out * 100) if sum_out > 0 else 0
    scores = [r["score"] for r in results if r["score"] is not None]
    avg_score = sum(scores) / len(scores) if scores else None
    # Always print average score for the launcher to parse, even in
    # non-interactive mode (quiet=True). The launcher's regex needs
    # "Average score: XX%" in stdout.
    if avg_score is not None:
        print(f"  Average score: {avg_score:.1%}")
    if not quiet:
        print(f"\n  --- Result {benchmark_name} / {model_key} ---")
        print(f"  Average latency: {avg_lat:.1f}s")
        print(f"  Average tokens/s: {avg_tps:.1f}")
        print(f"  \u2248{think_ratio:.0f}% Thinking ratio ({sum_think}/{sum_out} tokens)")
    # System metrics: from per-task peak values (monitor thread, ~5Hz during inference)
    # instead of MetricsCollector (only every 10s over entire run including idle)
    _ram_total_gb = psutil.virtual_memory().total / (1073741824)
    def _peak_avg_max(key: str, min_val: float = 0) -> tuple[Optional[float], Optional[float]]:
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


def _safe_float(value: Any) -> Optional[float]:
    """Convert value to float, returning None for missing/non-numeric inputs.

    Code-Review 2026-07-18 §5.2: replaces 4x repeated
    `try: x.append(float(...)) except (ValueError, TypeError, AttributeError): pass`
    blocks in parse_resource_avgs().
    """
    try:
        return float(value)
    except (ValueError, TypeError, AttributeError):
        return None


def parse_resource_avgs(task_results: list[dict[str, Any]]) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
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
    # Code-Review 2026-07-18 §4.1: EXCLUDE_KEYWORDS filtering is already
    # applied by get_available_models(); doing it again here is
    # redundant and drift-prone.
    filtered = available_models
    if not filtered:
        print("\n[WARN] No models found in LM Studio.")
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


def main() -> None:
    try:
        import sys as _sys
        _sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
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
    sample_size = _args.sample_size
    non_interactive = _args.non_interactive
    model_key_override = _args.model_key
    api_model_override = _args.api_model
    benchmark_override = _args.benchmark
    qwen_prompt_mode = _args.qwen_prompt
    thinking_mode = _args.thinking
    global QWEN_PROMPT_MODE, THINKING_MODE, STRUCTURED_OUTPUT
    QWEN_PROMPT_MODE = qwen_prompt_mode
    THINKING_MODE = thinking_mode
    STRUCTURED_OUTPUT = not _args.no_structured_output
    KEEP_RESPONSE = _args.keep_response
    if _args.seed is not None:
        _seed = _args.seed
    else:
        random.seed()
        _seed = random.randrange(2**32)
    random.seed(_seed)

    print(f"  Random-Seed: {_seed}")
    print("=" * 60)
    print("  LM Studio Benchmark Tool v13")
    print("  DS1000 + CoderEval")
    print(f"  Subsampling: {sample_size} tasks per benchmark")
    print("=" * 60)
    print(f"  Python: {sys.version.split()[0]} ({sys.executable})")
    print()
    monitor = Monitor()
    if not check_api_available():
        print(f"\n[ERROR] LM Studio API not reachable: {API_BASE}")
        sys.exit(1)
    print(f"\n[OK] LM Studio API: {API_BASE}")

    # Check DS1000 dependencies
    ds_deps = ["numpy", "pandas", "matplotlib", "seaborn"]
    missing = []
    for pkg in ds_deps:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"\n[WARN] DS1000 requires: {', '.join(missing)}")
        print("       Install missing packages with:")
        print(f"       pip install {' '.join(missing)}")
        print()


    if non_interactive:
        benchmarks = BENCHMARKS
        if benchmark_override:
            benchmarks = [b for b in benchmarks if b["name"].lower() == benchmark_override.lower()]
            if not benchmarks:
                print(f"\n[ERROR] Benchmark '{benchmark_override}' not found. Possible: {', '.join(b['name'] for b in BENCHMARKS)}")
                sys.exit(1)
        available = get_available_models(exclude_keywords=EXCLUDE_KEYWORDS)
        if model_key_override:
            models = [m for m in available if m["key"] == model_key_override]
            if not models:
                print(f"\n[ERROR] Model '{model_key_override}' not found.")
                sys.exit(1)
        else:
            models = available
    else:
        print("\n[WARN] Interactive mode is no longer supported – use run_benchmarks_v13.py")
        print("[INFO] custom_benchmark_v13.py only implements DS1000 + CoderEval. For HumanEval+/MBPP+/ARC/HellaSwag/TruthfulQA/IFEval/MATH-500 use run_benchmarks_v13.py.")
        print("[INFO] Start with: python run_benchmarks_v13.py --benchmarks DS1000,CoderEval")
        benchmarks = select_benchmark()
        models = select_models(get_available_models())
        # Check whether a model is already loaded (from previous run)
        loaded = get_current_loaded_model()
        if not loaded:
            print("\n[ERROR] No model loaded. Please load a model first via run_benchmarks_v13.py.")
            sys.exit(1)

    summary = []
    for midx, model_info in enumerate(models, 1):
        model_key = model_info["key"]
        model_display = model_info["display"]
        # Take exact API ID from parent (if set)
        if api_model_override:
            model_info["_api_model"] = api_model_override
        model_results = []
        print(f"\n{'=' * 60}")
        print(f"  Model {midx}/{len(models)}: {model_display}")
        print(f"{'=' * 60}")
        # Model management (load/unload) is initiated ONLY by run_benchmarks_v13.py.
        # We assume that the model is already loaded and ready.
        for bench in benchmarks:
            fp = os.path.join(DATA_DIR, bench["file"])
            if not os.path.exists(fp):
                print(f"[WARN] Missing: {fp}")
                continue
            tasks = load_jsonl(fp)
            if len(tasks) > MAX_TASKS_PER_BENCHMARK:
                print(f"\n  Loading {bench['file']} ({len(tasks)} tasks, using {MAX_TASKS_PER_BENCHMARK})")
                tasks = tasks[:MAX_TASKS_PER_BENCHMARK]
            else:
                print(f"\n  Loading {bench['file']} ({len(tasks)} tasks)")
            tt = get_task_type(bench["file"])
            tasks = subsample_tasks(tasks, tt, sample_size=sample_size)
            try:
                res, avg_s, avg_l, avg_t, cs = benchmark_model(
                    model_info, tasks, tt, bench["name"], monitor,
                    quiet=non_interactive
                )
            except Exception as e:
                print(f"\n[ERROR] Benchmark {bench['name']} completely failed: {e}")
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
            bench_names = "+".join(sorted(set(r["benchmark_name"] for r in model_results)))
            csv_writer.write_per_model_csv(
                model_results, model_display,
                model_key=model_info.get("key", ""),
                sample_size=sample_size,
            )

    # In non-interactive mode: skip redundant SUMMARY
    # (run_benchmarks_v13.py generates its own summaries)
    if not non_interactive:
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
            print(f"\n[INFO] Summary: {sp}")
    print("\n[INFO] Benchmark complete.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] Aborted.")
        print("[INFO] Unloading models...")
        unload_all_models()
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        traceback.print_exc()
        sys.exit(1)
