#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Benchmark-Skript fuer lokale LLMs ueber LM Studio API – DS1000 + CoderEval (v10).

── Rolle im Gesamtsystem ───────────────────────────────────────────
  Dieses Skript ist die "Custom"-Pipeline der Vier-Pipelines-Architektur:
    Pipeline             Skript/Tool                Verantwortung
    ────────             ───────────                ─────────────
    Custom (DAS HIER)    custom_benchmark_v11.py    DS1000, CoderEval
    EvalPlus             evalplus.codegen/evaluate  HumanEval+, MBPP+
    LM-Eval              lm_eval CLI                ARC, HellaSwag, ...
    Agentic              tool_eval_bench            Tool-Use-Szenarien

── Grenzen ─────────────────────────────────────────────────────────
  DIESES SKRIPT DARF NICHT:
  - Modelle laden/entladen (das macht NUR run_benchmarks_v11.py)
  - Eigene Modell-Management-Funktionen aufrufen
  - Andere Pipelines starten

── Aufruf ──────────────────────────────────────────────────────────
  Normalerweise als Subprozess von run_benchmarks_v11.py via:
    python custom_benchmark_v11.py --non-interactive --model-key ... --api-model ... --sample-size N --benchmark DS1000
  Kann standalone laufen (ohne --non-interactive), warnt dann aber.

── Datenquellen ────────────────────────────────────────────────────
  JSONL-Dateien unter simple_evals/:
    - data_science.jsonl                (DS1000: 5 Libraries)
    - codereval_selfcontained.jsonl     (CoderEval: ~138 Tasks)

── Auswertung ──────────────────────────────────────────────────────
  Pro Aufgabe: Modell generiert Code via LM-Studio-API, dann
  Ausfuehrung in exec_sandboxed() mit 4 Evaluierungs-Modi:
    1. DS1000-Harness (test_execution)
    2. Namespace-Vergleich (reference_code + setup_code)
    3. Reference als Tests
    4. Direkte Tests
  Systemmetriken (CPU/GPU/RAM) via Monitor-Thread waehrend API-Call.

── CSV-Output ─────────────────────────────────────────────────────
  Nutzt csv_writer.py fuer einheitliches Schema.
  Der Launcher aggregiert die Ergebnisse pipeline-uebergreifend.

── Aenderungen zu v10 ──────────────────────────────────────────────
  - CSV-Output ueber csv_writer.py (einheitliches Schema, ;-Delimiter, utf-8)

Quellen: DS1000, CoderEval
"""

from __future__ import annotations

import ast
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

# Modell-Management aus gemeinsamem Modul (wird NICHT von hier veranlasst)
# HINWEIS: Dieses Skript importiert die Konstanten und Hilfsfunktionen aus
# model_manager.py, ruft aber NIEMALS load/unload auf. Das Lademanagement
# erfolgt ausschliesslich durch run_benchmarks_v11.py als uebergeordneter
# Launcher. Die exakte Modell-ID wird ueber --api-model uebergeben.
from model_manager import (
    API_BASE, TIMEOUT_CLI, TIMEOUT_HTTP, TIMEOUT_MODEL_READY,
    TIMEOUT_HEALTH_CHECK, TIMEOUT_UNLOAD_WAIT,
    check_api_available, get_current_loaded_model,
    unload_all_models, load_model_via_lms, wait_for_model_ready
)

import psutil
import pynvml

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "simple_evals")
RESULTS_DIR = os.path.join(BASE_DIR, "ergebnisse")
os.makedirs(RESULTS_DIR, exist_ok=True)

TIMEOUT_LOAD_MODEL = 180
TIMEOUT_SAMPLER_JOIN = 3
TIMEOUT_EXEC = 30

# Qwen3.5-Kompatibilitaet: Prompt-Einbettung statt System-Message
QWEN_PROMPT_MODE = False

SAMPLE_SIZE = 10
random.seed()

MAX_TASKS_PER_BENCHMARK = 100

MAX_TOKENS_GENERAL = 2048
MAX_TOKENS_MC = 64

MONITOR_HISTORY_MAX = 500

EXCLUDE_KEYWORDS = ["whisper", "vision", "ocr", "transcription", "transcribe", "translat", "audit", "audio", "embed"]

# --- Streaming / Timeout / Retry Konfiguration ---
START_TIMEOUT = 30           # max Sekunden bis zum ersten Token
FINISH_TIMEOUT = 25          # max Sekunden zwischen Tokens (stall detection)
MAX_RETRIES = 3              # max Wiederholungen bei API-Fehlern
RETRY_MULTIPLIER = 1.5       # Timeout-Multiplikator pro Retry
STOP_TOKENS_CODING = ["\n```", "\n# Aufgabe", "\n// ", "<|endoftext|>"]
STOP_TOKENS_DEFAULT = ["<|endoftext|>"]

BENCHMARKS = [
    {"key": "1", "name": "DS1000", "file": "data_science.jsonl"},
    {"key": "3", "name": "CoderEval", "file": "codereval_selfcontained.jsonl"},
]

MODEL_CONFIG = {
    "default": {
        "temperature": 0.0,
        "top_p": 1.0,
        "max_tokens": MAX_TOKENS_GENERAL,
        "enable_thinking": None,
    },
    "qwen3.5": {
        "temperature": 0.2,
        "top_p": 0.9,
        "top_k": 20,
        "max_tokens": MAX_TOKENS_GENERAL,
        "enable_thinking": False,
        "no_system_msg": True,
    },
    "qwen3.6": {
        "temperature": 0.0,
        "top_p": 1.0,
        "max_tokens": 8192,
        "enable_thinking": False,
        # ACHTUNG: Qwen3.6 nutzt Reasoning-Thinking standardmaessig.
        # Wenn enable_thinking nicht auf False gesetzt wird, verbrauchen
        # die Thinking-Tokens das gesamte max_tokens-Budget (2048) und
        # es bleibt kein Platz fuer die eigentliche Antwort -> Score 0%.
        # LM Studio GUI-Option "Parsing von Begründungsabschnitten" ist
        # inkompatibel – muss ueber API (extra_body) deaktiviert werden.
    },
    "deepseek": {
        "temperature": 0.1,
        "top_p": 0.9,
        "min_p": 0.02,
        "max_tokens": MAX_TOKENS_GENERAL,
        "enable_thinking": True,
    },
    "gpt-oss": {
        "temperature": 1.0,
        "top_p": 1.0,
        "top_k": 0,
        "max_tokens": 4096,
        "enable_thinking": None,
    },
}


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
            print("  [WARN] GPU/VRAM-Monitoring via NVML nicht verfuegbar")

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
                cpu = psutil.cpu_percent(interval=0.2)
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


def get_available_models() -> list[dict[str, Any]]:
    try:
        result = subprocess.run(
            ["lms", "ls", "--json"],
            capture_output=True, text=True, timeout=TIMEOUT_CLI,
            encoding="utf-8", errors="replace"
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            models = []
            for item in data if isinstance(data, list) else data.values():
                if isinstance(item, dict):
                    key = item.get("modelKey", "")
                    if key:
                        models.append({
                            "key": key,
                            "display": item.get("displayName", key),
                            "identifier": item.get("indexedModelIdentifier", key),
                            "params": item.get("paramsString", ""),
                            "publisher": item.get("publisher", ""),
                            "quant": item.get("quantization", {}).get("name", ""),
                        })
            # Bei doppelten Display-Namen Organisations-Prefix anhaengen (erster Fund bleibt)
            seen_displays = {}
            for m in models:
                d = m["display"]
                if d in seen_displays:
                    prefix = m["key"].split("/")[0] if "/" in m["key"] else m["key"]
                    m["display"] = f"{d} ({prefix})"
                else:
                    seen_displays[d] = m
            if models:
                return models
        print(f"[WARN] lms ls fehlgeschlagen: {result.stderr.strip()}")
    except FileNotFoundError:
        print("[ERROR] lms.exe nicht gefunden. Ist LM Studio installiert?")
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        print(f"[WARN] Fehler bei lms ls: {e}")
    return []


def _stream_chat_completion(url: str, headers: dict[str, str], body: dict[str, Any], start_timeout: int = START_TIMEOUT, finish_timeout: int = FINISH_TIMEOUT, max_retries: int = MAX_RETRIES) -> tuple[Optional[str], float, int, int, float, int, Optional[str], Optional[str]]:
    """Streaming Chat-Completion mit Dual-Timeout und Retry-Logik.
    
    Nutzt Threading, um start_timeout (erster Token) und finish_timeout
    (zwischen Tokens) unabhaengig vom SSE-Stream zu ueberwachen.
    Gibt 8-Tupel zurueck: (content, elapsed, t_in, t_out, tps, thinking_tokens, error_type, error_detail)
    """
    for attempt in range(max_retries):
        current_start_timeout = start_timeout * (RETRY_MULTIPLIER ** attempt)
        result = {"content": "", "thinking": "", "done": False, "error": None, "usage": None}
        cancel_event = threading.Event()
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
                                result["usage"] = chunk["usage"]
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            if delta.get("content"):
                                result["content"] += delta["content"]
                            if delta.get("reasoning_content"):
                                result["thinking"] += delta["reasoning_content"]
                        except json.JSONDecodeError:
                            pass
                result["done"] = True
            except Exception as e:
                result["error"] = str(e)
                result["done"] = True
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
            if result["done"] or result["content"] or result["error"]:
                break
            time.sleep(0.05)
        elapsed = time.time() - start
        if result["error"]:
            if attempt < max_retries - 1:
                cancel_event.set()
                thread.join(timeout=1)
                time.sleep(2 ** attempt)
                continue
            return None, elapsed, 0, 0, 0, 0, "api_error", result["error"]
        if not result["content"] and not result["done"]:
            cancel_event.set()
            thread.join(timeout=1)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return None, elapsed, 0, 0, 0, 0, "api_error", f"No response within {current_start_timeout}s (attempt {attempt+1})"
        last_content_len = 0
        stall_start = time.time()
        while time.time() - stall_start < finish_timeout:
            if result["done"]:
                break
            current_len = len(result["content"])
            if current_len > last_content_len:
                last_content_len = current_len
                stall_start = time.time()
            time.sleep(0.05)
        if not result["done"]:
            cancel_event.set()
            thread.join(timeout=1)
        full_elapsed = time.time() - start
        thinking_content = result["thinking"]
        thinking_tokens = len(thinking_content.split()) if thinking_content else 0
        content_raw = result["content"]
        content, think_tags = strip_thinking_tokens(content_raw)
        thinking_tokens = thinking_tokens + think_tags
        usage = result.get("usage") or {}
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)
        if tokens_in == 0 and tokens_out == 0:
            tokens_out = len(content.split()) if content else 0
        tokens_per_sec = tokens_out / full_elapsed if full_elapsed > 0 else 0
        return content, full_elapsed, tokens_in, tokens_out, tokens_per_sec, thinking_tokens, None, None
    return None, 0, 0, 0, 0, 0, "api_error", "Max retries exceeded"


def strip_thinking_tokens(text: Optional[str]) -> tuple[Optional[str], int]:
    if not text:
        return text, 0
    matches = re.findall(r"<think>(.*?)</think>", text, re.DOTALL)
    total_chars = sum(len(m) for m in matches)
    estimated_tokens = total_chars // 4
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    return cleaned, estimated_tokens


def _non_streaming_fallback(url: str, body: dict[str, Any], timeout: int) -> tuple[Optional[str], int, int, int]:
    """Fallback ohne Streaming, falls Streaming fehlschlaegt."""
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
        print(f"\n[ERROR] API-Fehler (Fallback, {type(e).__name__}): {e}")
        return None, 0, 0, 0


def generate_answer(prompt: Optional[str] = None, model_key: Optional[str] = None, timeout: int = TIMEOUT_HTTP,
                    max_tokens: int = MAX_TOKENS_GENERAL, system_msg: Optional[str] = None, messages: Optional[list[dict[str, Any]]] = None,
                    temperature: float = 0.0, top_p: float = 1.0, top_k: Optional[int] = None, min_p: Optional[float] = None,
                    enable_thinking: Optional[bool] = None, use_streaming: bool = True, stop: Optional[list[str]] = None) -> tuple[Optional[str], float, int, int, float, int, Optional[str], Optional[str]]:
    if messages is None:
        messages = []
        if system_msg:
            messages.append({"role": "system", "content": system_msg})
        messages.append({"role": "user", "content": prompt})
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
    if enable_thinking is not None:
        body.setdefault("extra_body", {})
        body["extra_body"]["chat_template_kwargs"] = {"enable_thinking": enable_thinking}
    if stop:
        body["stop"] = stop
    url = f"{API_BASE}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if use_streaming:
        content, elapsed, t_in, t_out, tps, think_tok, err_type, err_detail = _stream_chat_completion(url, headers, body)
        if content is not None:
            return content, elapsed, t_in, t_out, tps, think_tok, err_type, err_detail
        print(f"\n[WARN] Streaming fehlgeschlagen ({err_detail}), Fallback ohne Streaming...")
    start = time.time()
    content, t_in, t_out, think_tok = _non_streaming_fallback(url, {**body, "stream": False}, timeout)
    elapsed = time.time() - start
    if content is not None:
        tokens_per_sec = t_out / elapsed if elapsed > 0 else 0
        return content, elapsed, t_in, t_out, tokens_per_sec, think_tok, None, None
    return None, elapsed, t_in, t_out, 0, think_tok, "api_error", "Fallback ebenfalls fehlgeschlagen"


def extract_code(text: Optional[str]) -> str:
    if not text:
        return ""
    pattern = r"```(?:python)?\s*\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        return matches[-1].strip()
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
    # Fallback: bare statements (plt.plot, df.sort_values, etc.) erkennen
    code_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _is_bare_statement(stripped):
            code_lines.append(stripped.rstrip(","))
    if code_lines:
        return "\n".join(code_lines)
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
        # Block-Header ohne Body erkennen und pass einfuegen
        new_lines = []
        for i, line in enumerate(result):
            new_lines.append(line)
            stripped = line.strip()
            if _BLOCK_HEADER.match(stripped):
                # Naechste Zeile(n) nach Header pruefen
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
    """Prueft ob eine Zeile ein Block-Header ohne Body ist (def, class, if, for, etc.)"""
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


# --- Sandbox fuer sicheres Code-Ausfuehren ---
# Fuehrt LLM-generierten Code in einem Subprozess mit eingeschraenkten Builtins aus.
# Blockiert gefaehrliche Module (os, subprocess, shutil, socket, etc.)
# und unerwuenschte Builtins (open, eval, exec, __import__ fuer blockierte Module).

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
    """Baut ein Sandbox-Skript, das code_string in einem restricted Namespace ausfuehrt."""
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
    """Fuehrt ein Sandbox-Skript als Subprozess in einem temporaeren Verzeichnis aus."""
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
    """Fuehrt Code im Sandbox-Subprozess aus. Returns (ok, error)."""
    script = _build_sandbox_script(code)
    res = _run_sandbox(script, timeout)
    return res["ok"], (res["error"] if not res["ok"] else None)


DS1000_DIR = _os.path.join(_os.path.dirname(__file__), 'ds1000_official')
_TIMEOUT_DS1000 = 120  # offizielles DS1000-Timeout

def _unwrap_solution_for_insert(solution: str, setup_code: str) -> str:
    """Wenn exec_context [insert] in einem Funktions-Block hat,
    und die Loesung eine Funktion definiert, dann nimm nur den Body."""
    import re as _re
    m = _re.search(r'exec_context\s*=\s*r?"""(.*?)"""', setup_code, _re.DOTALL)
    if not m:
        return solution
    ctx = m.group(1)
    if "[insert]" not in ctx:
        return solution
    before = ctx.split("[insert]")[0].strip()
    if not before:
        return solution
    last = before.split("\n")[-1].strip()
    _BH = r"^(?:def |class |if |elif |else:|for |while |with |try:|except(?: |:)|finally:)"
    if not _re.match(_BH, last):
        return solution  # [insert] auf oberster Ebene -> ok
    # Funktion aus exec_context-Header extrahieren
    ef = _re.match(r"def\s+(\w+)", last)
    exec_func = ef.group(1) if ef else None
    # In der Loesung nach der ERSTEN def/class Zeile suchen
    sol = solution.strip()
    sol_lines = sol.split("\n")
    def_idx = None
    def_line = None
    for i, line in enumerate(sol_lines):
        if _re.match(_BH, line.strip()):
            def_idx = i
            def_line = line.strip()
            break
    if def_idx is not None:
        # def/class gefunden -> Funktionsnamen vergleichen
        sf = _re.match(r"def\s+(\w+)", def_line)
        sol_func = sf.group(1) if sf else None
        if exec_func and sol_func and exec_func != sol_func:
            # Anderer Funktionsname -> gesamte Loesung einruecken
            indent = "    "
            return indent + ("\n" + indent).join(sol_lines)
        # Unwrap: alles ab der def-Zeile raus, nur den Body (eingerueckte Zeilen danach) behalten
        body = []
        for line in sol_lines[def_idx + 1:]:
            body.append(line)
        while body and not body[0].strip():
            body.pop(0)
        if not body:
            return "    pass"
        # Pruefe ob der Body nur Kommentare/Leerzeilen enthaelt
        has_real_stmt = any(
            line.strip() and not line.strip().startswith("#")
            for line in body
        )
        if not has_real_stmt:
            return "    pass"
        return "\n".join(body)
    # Keine def/class in der Loesung -> gesamte Loesung einruecken
    indent = "    "
    return indent + ("\n" + indent).join(sol_lines)


def _try_ds1000_harness(generated_code: str, setup_code: str) -> Optional[tuple[float, str]]:
    if not setup_code or "test_execution" not in setup_code:
        return None
    if DS1000_DIR not in sys.path:
        sys.path.insert(0, DS1000_DIR)
    from execution import check_correctness
    unwrapped = _unwrap_solution_for_insert(generated_code, setup_code)
    test_program = (
        setup_code + "\n"
        + f"code = {_json.dumps(unwrapped)}\n"
        + "test_execution(code)\n"
    )
    if "test_string(" in setup_code:
        test_program += "test_string(code)\n"
    result = check_correctness(test_program, timeout=_TIMEOUT_DS1000)
    if result["passed"]:
        print("    [EVAL] DS1000-Harness: BESTANDEN")
        return 1.0, "OK (DS1000-Harness)"
    # Fallback: falls unwrapping nicht geholfen hat, mit Original versuchen
    if unwrapped != generated_code:
        test_program2 = (
            setup_code + "\n"
            + f"code = {_json.dumps(generated_code)}\n"
            + "test_execution(code)\n"
        )
        result2 = check_correctness(test_program2, timeout=_TIMEOUT_DS1000)
        if result2["passed"]:
            print("    [EVAL] DS1000-Harness: BESTANDEN (original)")
            return 1.0, "OK (DS1000-Harness)"
        print(f"    [EVAL] DS1000-Harness: FEHLGESCHLAGEN -> {result['result']}")
        return 0.0, f"Harness-Fehler: {result['result']}"
    print(f"    [EVAL] DS1000-Harness: FEHLGESCHLAGEN -> {result['result']}")
    return 0.0, f"Harness-Fehler: {result['result']}"


def evaluate_code(generated_code: str, entry_point: str, tests_field: Any, reference_code: str = "", setup_code: str = "") -> tuple[float, str]:
    if not generated_code:
        return 0.0, "Kein Code generiert"

    tests = parse_tests_field(tests_field)

    # --- DS1000-Harness (test_execution aus code_context) ---
    if not tests and setup_code and "test_execution" in setup_code:
        print("    [EVAL] Versuche DS1000-Harness ...")
        result = _try_ds1000_harness(generated_code, setup_code)
        if result is not None:
            return result
        print("    [EVAL] Harness nicht nutzbar -> Fallback auf Namespace-Vergleich")

    # --- Namespace-Vergleich (Reference vs Generated) ---
    if not tests and reference_code and setup_code:
        ref_combined = setup_code + "\n" + reference_code
        script = _build_sandbox_script(ref_combined, capture_state=True)
        res = _run_sandbox(script)
        if not res["ok"]:
            return 0.0, f"Reference-Fehler: {res['error']}"
        ref_state = res.get("state", {})
        setup_keys = set(ref_state.keys()) | {'__builtins__'}

        gen_combined = setup_code + "\n" + generated_code
        script = _build_sandbox_script(gen_combined, capture_state=True)
        res = _run_sandbox(script)
        if not res["ok"]:
            return 0.0, f"Code-Fehler: {res['error']}"
        gen_state = res.get("state", {})

        # Nur State-Keys vergleichen, die NICHT im setup_keys sind
        ref_only = {k: v for k, v in ref_state.items() if k not in setup_keys}
        gen_only = {k: v for k, v in gen_state.items() if k not in setup_keys}

        if not ref_only:
            print("    [EVAL] Namespace-Vergleich: keine vergleichbaren Outputs -> 1.0")
            return 1.0, "OK (Namespace: keine Outputs)"

        matched = 0
        for k, ref_val in ref_only.items():
            gen_val = gen_only.get(k)
            if gen_val == ref_val:
                matched += 1
        score = matched / len(ref_only)
        print(f"    [EVAL] Namespace-Vergleich: {matched}/{len(ref_only)} korrekt")
        return score, f"Namespace: {matched}/{len(ref_only)}"

    if not tests and reference_code:
        tests = [reference_code]

    # --- Direkte Tests ---
    if not tests:
        # Nur Code ausfuehren, keine Tests
        combined = ""
        if setup_code:
            combined += setup_code + "\n"
        combined += generated_code
        ok, err = exec_sandboxed(combined)
        if not ok:
            return 0.0, f"Code-Fehler: {err}"
        return 1.0, "OK (keine Tests)"

    # Mit Tests: Bundle alles in einen Sandbox-Durchlauf
    combined_code = ""
    if setup_code:
        combined_code += setup_code + "\n"
    combined_code += generated_code

    script = _build_sandbox_script(combined_code, tests=tests)
    res = _run_sandbox(script)
    if not res["ok"]:
        return 0.0, f"Code-Fehler: {res['error']}"

    passed = res.get("passed", 0)
    total = res.get("total", 0)
    print(f"    [EVAL] Direkte Tests: {passed}/{total} bestanden")
    return passed / total if total > 0 else 1.0, f"Tests: {passed}/{total}"


def _get_model_config(model_key: Optional[str]) -> dict[str, Any]:
    key_lower = model_key.lower() if model_key else ""
    for pattern, cfg in MODEL_CONFIG.items():
        if pattern in key_lower:
            return cfg
    return MODEL_CONFIG["default"]


def run_task(task: dict[str, Any], task_type: str, model_key: Optional[str] = None, api_model: Optional[str] = None, model_config: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    prompt = task["prompt"]
    if model_config is None:
        model_config = _get_model_config(model_key)

    gen_kwargs = {
        "model_key": api_model or model_key,
        "temperature": model_config.get("temperature", 0.0),
        "top_p": model_config.get("top_p", 1.0),
        "top_k": model_config.get("top_k"),
        "min_p": model_config.get("min_p"),
        "enable_thinking": model_config.get("enable_thinking"),
        "stop": STOP_TOKENS_CODING,
    }

    no_system_msg = model_config.get("no_system_msg", False)
    max_tokens_task = model_config.get("max_tokens", MAX_TOKENS_GENERAL)

    # Qwen3.5-Kompatibilitaet: System-Message in User-Prompt einbetten
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
            full_prompt, **gen_kwargs
        )
        if response is None:
            return {"response": None, "extracted_code": "", "score": 0.0,
                    "score_detail": f"Timeout/API-Fehler ({latency:.1f}s)", "latency": latency,
                    "tokens_in": t_in, "tokens_out": t_out, "tokens_per_sec": tps,
                    "thinking_tokens": think_tok, "error_type": err_type, "error_detail": err_detail}
        code = extract_code(response) if response else ""
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
            full_prompt, **gen_kwargs
        )
        if response is None:
            return {"response": None, "extracted_code": "", "score": 0.0,
                    "score_detail": f"Timeout/API-Fehler ({latency:.1f}s)", "latency": latency,
                    "tokens_in": t_in, "tokens_out": t_out, "tokens_per_sec": tps,
                    "thinking_tokens": think_tok, "error_type": err_type, "error_detail": err_detail}
        code = extract_code(response) if response else ""
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
            "score_detail": f"Unbekannter task_type: {task_type}", "latency": 0.0,
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
    # Exakte API-ID bevorzugen, fallback auf model_key
    api_model = model_info.get("_api_model") if is_dict else model_key
    model_config = _get_model_config(model_key)
    print(f"\n{'=' * 60}")
    print(f"  Benchmark: {benchmark_name}")
    print(f"  Modell:    {display_name}")
    print(f"  Aufgaben:  {len(tasks)}")
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
                    if attempt < MAX_RETRIES:
                        print(f"  [RETRY] API-Fehler (Versuch {attempt}/{MAX_RETRIES}): {result.get('error_detail', '?')}")
                        time.sleep(2 ** attempt)
            except Exception as e:
                if attempt < MAX_RETRIES:
                    print(f"  [RETRY] Exception (Versuch {attempt}/{MAX_RETRIES}): {e}")
                    time.sleep(2 ** attempt)
                else:
                    print(f"  [ERROR] Task fehlgeschlagen ({type(e).__name__}: {e})")
                    result = {
                        "score": 0.0,
                        "score_detail": f"Fehler: {e}",
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
    think_anteil = (sum_think / sum_out * 100) if sum_out > 0 else 0
    scores = [r["score"] for r in results if r["score"] is not None]
    avg_score = sum(scores) / len(scores) if scores else None
    if not quiet:
        print(f"\n  --- Ergebnis {benchmark_name} / {model_key} ---")
        if avg_score is not None:
            print(f"  Durchschnitts-Score: {avg_score:.1%}")
        print(f"  Durchschnitts-Latenz: {avg_lat:.1f}s")
        print(f"  Durchschnitts-Tokens/s: {avg_tps:.1f}")
        print(f"  \u2248{think_anteil:.0f}% Thinking-Anteil ({sum_think}/{sum_out} Tokens)")
    # Systemmetriken: aus Per-Task-Peak-Werten (Monitor-Thread, ~5Hz waehrend Inference)
    # statt aus MetricsCollector (nur alle 10s ueber gesamten Lauf inkl. Leerlauf)
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


def save_csv(results: list[dict[str, Any]], benchmark_name: str, model_id: str) -> Any:
    """Legacy – leitet an csv_writer weiter (v10)."""
    return csv_writer.write_per_task_csv(results, benchmark_name, model_id)


def save_model_summary(model_display: str, model_results: list[dict[str, Any]], bench_name: str = "", quiet: bool = False) -> Any:
    """Legacy – leitet an csv_writer weiter (v10)."""
    return csv_writer.write_per_model_csv(model_results, model_display)


def parse_resource_avgs(task_results: list[dict[str, Any]]) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    cpu, ram, gpu, vram = [], [], [], []
    for t in task_results:
        try: cpu.append(float(t.get("cpu_during", 0)))
        except: pass
        try: ram.append(float(t.get("ram_during", 0)))
        except: pass
        try: gpu.append(float(t.get("gpu_during", 0)))
        except: pass
        try: vram.append(float(t.get("vram_during", 0)))
        except: pass
    return (
        sum(cpu)/len(cpu) if cpu else None,
        sum(ram)/len(ram) if ram else None,
        sum(gpu)/len(gpu) if gpu else None,
        sum(vram)/len(vram) if vram else None,
    )


def _parse_selection(choice: str, max_val: int) -> Optional[list[int]]:
    choice = choice.strip()
    if not choice:
        return None
    parts = choice.replace(" ", "").split(",")
    selected = set()
    for part in parts:
        if "-" in part:
            try:
                lo, hi = part.split("-", 1)
                lo_i, hi_i = int(lo), int(hi)
                if lo_i < 1 or hi_i > max_val or lo_i > hi_i:
                    return None
                for n in range(lo_i, hi_i + 1):
                    selected.add(n - 1)
            except ValueError:
                return None
        else:
            try:
                n = int(part)
                if n < 1 or n > max_val:
                    return None
                selected.add(n - 1)
            except ValueError:
                return None
    return sorted(selected) if selected else None


def select_benchmark() -> list[dict[str, Any]]:
    print("\n" + "=" * 60)
    print("  Benchmark-Auswahl")
    print("=" * 60)
    for b in BENCHMARKS:
        print(f"  [{b['key']}] {b['name']}")
    print("  [a] Alle Benchmarks nacheinander")
    print("  [q] Beenden")
    while True:
        choice = input("\n  Deine Wahl: ").strip().lower()
        if choice == "q":
            sys.exit(0)
        if choice == "a":
            return BENCHMARKS
        indices = _parse_selection(choice, len(BENCHMARKS))
        if indices is not None:
            result = [BENCHMARKS[i] for i in indices]
            names = ", ".join(b["name"] for b in result)
            print(f"  -> {names}")
            return result
        print("  Ungueltige Eingabe.")


def select_models(available_models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered = [m for m in available_models
                if not any(kw in m["key"].lower() for kw in EXCLUDE_KEYWORDS)]
    if not filtered:
        print("\n[WARN] Keine Modelle in LM Studio gefunden.")
        sys.exit(1)
    print("\n" + "-" * 50)
    print("  Verfuegbare Modelle:")
    for i, m in enumerate(filtered, 1):
        label = m["display"]
        if m.get("params"):
            label += f" ({m['params']})"
        if m.get("publisher"):
            label += f" - {m['publisher']}"
        print(f"  [{i}] {label}")
    print("  [a] Alle Modelle testen")
    while True:
        choice = input("  Deine Wahl: ").strip().lower()
        if choice == "a":
            return filtered
        indices = _parse_selection(choice, len(filtered))
        if indices is not None:
            return [filtered[i] for i in indices]
        print("  Ungueltige Eingabe.")


def main() -> None:
    try:
        import sys as _sys
        _sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    import argparse as _ap
    _parser = _ap.ArgumentParser(description="Benchmark-Tool v10 (DS1000 + CoderEval)")
    _parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE,
                         help=f"Stichprobengroesse pro Benchmark (Default: {SAMPLE_SIZE})")
    _parser.add_argument("--non-interactive", action="store_true",
                         help="Ueberspringe interaktive Auswahl, fuehre alle Benchmarks + Modelle aus")
    _parser.add_argument("--model-key", type=str, default=None,
                         help="Modell-Key fuer nicht-interaktiven Modus")
    _parser.add_argument("--benchmark", type=str, default=None,
                         help="Nur diesen Benchmark ausfuehren (z.B. DS1000, CoderEval)")
    _parser.add_argument("--api-model", type=str, default=None,
                         help="Exakte Modell-ID fuer API-Aufrufe (aus lms ps)")
    _parser.add_argument("--qwen-prompt", action="store_true",
                         help="Qwen3.5-Kompatibilitaet: systemlose Prompt-Einbettung")
    _args, _ = _parser.parse_known_args()
    sample_size = _args.sample_size
    non_interactive = _args.non_interactive
    model_key_override = _args.model_key
    api_model_override = _args.api_model
    benchmark_override = _args.benchmark
    qwen_prompt_mode = _args.qwen_prompt
    global QWEN_PROMPT_MODE
    QWEN_PROMPT_MODE = qwen_prompt_mode
    random.seed()
    _seed = random.randrange(2**32)
    random.seed(_seed)

    print(f"  Random-Seed: {_seed}")
    print("=" * 60)
    print("  LM Studio Benchmark-Tool v10")
    print("  DS1000 + CoderEval")
    print(f"  Subsampling: {sample_size} Aufgaben pro Benchmark")
    print("=" * 60)
    print(f"  Python: {sys.version.split()[0]} ({sys.executable})")
    print()
    monitor = Monitor()
    if not check_api_available():
        print(f"\n[ERROR] LM Studio API nicht erreichbar: {API_BASE}")
        sys.exit(1)
    print(f"\n[OK] LM Studio API: {API_BASE}")

    # Pruefe DS1000-Abhaengigkeiten
    ds_deps = ["numpy", "pandas", "matplotlib", "seaborn"]
    missing = []
    for pkg in ds_deps:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"\n[WARN] DS1000 benoetigt: {', '.join(missing)}")
        print("       Installiere fehlende Pakete mit:")
        print(f"       pip install {' '.join(missing)}")
        print()


    if non_interactive:
        benchmarks = BENCHMARKS
        if benchmark_override:
            benchmarks = [b for b in benchmarks if b["name"].lower() == benchmark_override.lower()]
            if not benchmarks:
                print(f"\n[ERROR] Benchmark '{benchmark_override}' nicht gefunden. Moegliche: {', '.join(b['name'] for b in BENCHMARKS)}")
                sys.exit(1)
        available = get_available_models()
        if model_key_override:
            models = [m for m in available if m["key"] == model_key_override]
            if not models:
                print(f"\n[ERROR] Modell '{model_key_override}' nicht gefunden.")
                sys.exit(1)
        else:
            models = available
    else:
        print("\n[WARN] Interaktiver Modus wird nicht mehr unterstuetzt – nutze run_benchmarks_v11.py")
        print("[INFO] Starte mit: python run_benchmarks_v11.py --benchmarks DS1000,CoderEval")
        benchmarks = select_benchmark()
        models = select_models(get_available_models())
        # Pruefe ob Modell bereits geladen ist (von Vorlauf)
        loaded = get_current_loaded_model()
        if not loaded:
            print("\n[ERROR] Kein Modell geladen. Bitte zuerst Modell via run_benchmarks_v11.py laden.")
            sys.exit(1)

    summary = []
    for midx, model_info in enumerate(models, 1):
        model_key = model_info["key"]
        model_display = model_info["display"]
        # Exakte API-ID vom Parent uebernehmen (falls gesetzt)
        if api_model_override:
            model_info["_api_model"] = api_model_override
        model_results = []
        print(f"\n{'=' * 60}")
        print(f"  Modell {midx}/{len(models)}: {model_display}")
        print(f"{'=' * 60}")
        # Modell-Management (laden/entladen) wird NUR von run_benchmarks_v11.py veranlasst.
        # Wir gehen davon aus, dass das Modell bereits geladen und bereit ist.
        for bench in benchmarks:
            fp = os.path.join(DATA_DIR, bench["file"])
            if not os.path.exists(fp):
                print(f"[WARN] Fehlt: {fp}")
                continue
            tasks = load_jsonl(fp)
            tt = get_task_type(bench["file"])
            tasks = subsample_tasks(tasks, tt, sample_size=sample_size)
            if len(tasks) > MAX_TASKS_PER_BENCHMARK:
                print(f"\n  Lade {bench['file']} ({len(tasks)} Aufgaben, nutze {MAX_TASKS_PER_BENCHMARK})")
                tasks = tasks[:MAX_TASKS_PER_BENCHMARK]
            else:
                print(f"\n  Lade {bench['file']} ({len(tasks)} Aufgaben)")
            try:
                res, avg_s, avg_l, avg_t, cs = benchmark_model(
                    model_info, tasks, tt, bench["name"], monitor,
                    quiet=non_interactive
                )
            except Exception as e:
                print(f"\n[ERROR] Benchmark {bench['name']} komplett fehlgeschlagen: {e}")
                traceback.print_exc()
                res = []
                avg_s = avg_l = avg_t = None
                cs = {}
            csv_p = csv_writer.write_per_task_csv(
                res, bench["name"], model_display,
                model_key=model_info.get("key", ""),
                sample_size=sample_size,
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
                "Modell": model_display, "Benchmark": bench["name"],
                "Aufgaben": len(tasks),
                "Score": f"{avg_s:.1%}" if avg_s is not None else "-",
                "Latenz": f"{avg_l:.1f}s" if avg_l is not None else "-",
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

    # In non-interactive-Modus: redundante ZUSAMMENFASSUNG ueberspringen
    # (run_benchmarks_v11.py erzeugt eigene Zusammenfassungen)
    if not non_interactive:
        print("\n" + "=" * 60)
        print("  ZUSAMMENFASSUNG")
        print("=" * 60)
        if summary:
            hdr = "{:<25} {:<20} {:<6} {:<8} {:<8} {:<8}".format(
                "Modell", "Benchmark", "Aufg.", "Score", "Latenz", "tok/s")
            print("  " + hdr)
            print("  " + "-" * len(hdr))
            for r in summary:
                print("  {:<25} {:<20} {:<6} {:<8} {:<8} {:<8}".format(
                    r["Modell"][:24], r["Benchmark"][:19], r["Aufgaben"],
                    r["Score"], r["Latenz"], r["tok/s"]))
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        sp = os.path.join(RESULTS_DIR, f"zusammenfassung_{ts}.csv")
        if summary:
            with open(sp, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=summary[0].keys())
                w.writeheader()
                w.writerows(summary)
            print(f"\n[INFO] Zusammenfassung: {sp}")
    print("\n[INFO] Benchmark abgeschlossen.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] Abgebrochen.")
        print("[INFO] Entlade Modelle...")
        unload_all_models()
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        traceback.print_exc()
        sys.exit(1)
