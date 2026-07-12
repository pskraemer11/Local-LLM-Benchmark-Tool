#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared module for LM Studio model management.
Imported by run_benchmarks_v13.py AND custom_benchmark_v13.py.

── Role in the system ─────────────────────────────────────────────
  This module encapsulates ALL interactions with the LM Studio CLI
  (lms load / unload / ps). It is used from two sides:

  1. run_benchmarks_v13.py (Launcher)
     - CALLS load_model_via_lms() and unload_all_models()
     - Model load/unload happens HERE ONLY
     - Uses get_current_loaded_model() for status checking

  2. custom_benchmark_v13.py (Custom pipeline subprocess)
     - IMPORTS the constants (API_BASE, TIMEOUT_*)
     - NEVER calls load/unload (initiated by the launcher)
     - Uses check_api_available() as health-check (legacy)

── API- vs. CLI-Zugriff ────────────────────────────────────────────
  - lms CLI:     load, unload, ps, ls (Subprozesse)
  - REST API:    /v1/chat/completions, /v1/models (Inference)
  Die Konstanten API_BASE und TIMEOUT_* werden pipeline-uebergreifend
  von allen Skripten genutzt, sodass Aenderungen (z.B. Port) zentral
  erfolgen koennen.

── Wichtige Hinweise ───────────────────────────────────────────────
  - wait_for_model_ready() wird vom Launcher nach load_model_via_lms()
    aufgerufen, um die API-Bereitschaft aktiv zu prüfen (anstatt time.sleep(10)).
  - load_model_via_lms() returns the EXACT model ID from lms ps --json
    (e.g. "microsoft/phi-4@q6_k"), used by ALL pipelines as the
    model parameter in API calls.
"""

import json
import os
import subprocess
import sys
import time
from typing import Optional

from benchmark_config import PIPELINE_TIMEOUTS

API_BASE = "http://127.0.0.1:1234/v1"
TIMEOUT_CLI = 30
TIMEOUT_HTTP = 120
TIMEOUT_MODEL_READY = 90
TIMEOUT_LOAD_MODEL = 180
TIMEOUT_HEALTH_CHECK = 5
TIMEOUT_UNLOAD_WAIT = 2

# ── Pipeline-specific timeouts ──────────────────────────────────
# These values are imported by run_benchmarks_v13.py and used as
# subprocess/scenario timeouts in each pipeline function.
# Some values (lmeval_base, evalplus_base) serve as base timeouts
# and are automatically doubled for reasoning models.
#
#   Key                     Default  Usage
#   ─────────────────────── ──────── ──────────────────────────────
#   custom_subprocess        3600    Subprocess timeout (DS1000, CoderEval)
#   evalplus_base             600    Base timeout codegen+evaluate (×2 for reasoning)
#   lmeval_base               600    Base timeout lm_eval (×2 for reasoning, ×3 for MathQA)
#   mmlupro_per_subset        300    Timeout per MMLU-Pro subset
#   agentic_subprocess        3600    Total runtime timeout tool_eval_bench
#   agentic_scenario          600    Timeout per scenario (--timeout passed to tool_eval_bench)
# (Values in benchmark_config.py)


def check_api_available() -> bool:
    try:
        from urllib.request import Request, urlopen
        req = Request(f"{API_BASE}/models", method="GET")
        with urlopen(req, timeout=TIMEOUT_HEALTH_CHECK) as resp:
            return resp.status == 200
    except Exception:
        return False


def get_current_loaded_model() -> Optional[dict[str, str]]:
    try:
        r = subprocess.run(["lms", "ps", "--json"], capture_output=True, text=True,
                           timeout=15, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            return None
        entries = json.loads(r.stdout)
        if not entries:
            return None
        entry = entries[0]
        return {
            "identifier": entry.get("identifier", ""),
            "model_key": entry.get("modelKey", entry.get("path", "")),
            "display_name": entry.get("displayName", ""),
            "status": entry.get("status", ""),
        }
    except (json.JSONDecodeError, subprocess.TimeoutExpired, Exception):
        return None


def unload_all_models() -> bool:
    print("  [INFO] Unloading all models...")
    try:
        r = subprocess.run(["lms", "unload", "--all"],
                           capture_output=True, text=True, timeout=TIMEOUT_CLI,
                           encoding="utf-8", errors="replace")
        if r.returncode == 0:
            print("  [OK] Unload command sent")
        else:
            print(f"  [WARN] lms unload: {r.stderr.strip()[:100]}")
    except FileNotFoundError:
        print("[ERROR] lms.exe not found")
        return False
    except subprocess.TimeoutExpired:
        print("[WARN] lms unload --all timeout")
        return False
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError
    for attempt in range(15):
        time.sleep(2)
        try:
            req = Request(f"{API_BASE}/chat/completions", method="POST",
                          data=b'{"model":"check","messages":[{"role":"user","content":"ping"}],"max_tokens":1}',
                          headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    print(f"  [WARN] Old model still active (attempt {attempt+1}/15)")
                    continue
        except (HTTPError, URLError, Exception):
            print("  [OK] Old model fully unloaded")
            return True
    print("  [WARN] Could not confirm unload – continuing")
    return False


def get_available_models(exclude_keywords: Optional[list[str]] = None) -> list[dict]:
    """Query LM Studio for installed models via `lms ls --json`.

    Returns a list of dicts with keys:
        key, model_key, display, variant, quant, variants,
        identifier, params, publisher
    """
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
                    base_key = item.get("modelKey", "")
                    if not base_key:
                        continue
                    quant = item.get("quantization", {}) or {}
                    quant_name = quant.get("name", "") if isinstance(quant, dict) else ""
                    sv = item.get("selectedVariant") or ""
                    unique_key = sv if sv and sv != base_key else (f"{base_key}@{quant_name}" if quant_name else base_key)
                    display = item.get("displayName", base_key)
                    if quant_name:
                        if "@" in display:
                            display = display.split("@")[0]
                        display = f"{display}@{quant_name}"
                    models.append({
                        "key": unique_key,
                        "model_key": base_key,
                        "display": display,
                        "variant": sv or base_key,
                        "quant": quant_name,
                        "variants": item.get("variants") or [],
                        "identifier": item.get("indexedModelIdentifier", base_key),
                        "params": item.get("paramsString", ""),
                        "publisher": item.get("publisher", ""),
                    })
            if models:
                if exclude_keywords:
                    models = [m for m in models
                              if not any(kw in m["key"].lower() for kw in exclude_keywords)]
                return models
        print(f"[WARN] lms ls failed: {result.stderr.strip()}")
    except FileNotFoundError:
        print("[ERROR] lms.exe not found. Is LM Studio installed?")
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        print(f"[WARN] Error with lms ls: {e}")
    return []


def parse_selection(choice: str, max_val: int) -> Optional[list[int]]:
    """Parse user input like '1', '1,3,5', '1-5' into zero-based indices."""
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


def _ensure_lmstudio_running() -> bool:
    """Start llmster daemon + lms server if not available."""
    from urllib.request import Request, urlopen
    from urllib.error import URLError
    try:
        req = Request(f"{API_BASE}/models", method="GET")
        with urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                return True
    except (URLError, Exception):
        pass
    print("  [INFO] LM Studio-Server nicht erreichbar – starte Daemon...")
    llmster = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                           ".lmstudio", "llmster", "0.0.12-1", "llmster.exe")
    if not os.path.exists(llmster):
        print(f"  [WARN] llmster.exe not found at {llmster}")
        return False
    try:
        subprocess.Popen([llmster])
        time.sleep(5)
    except Exception as e:
        print(f"  [WARN] llmster start failed: {e}")
        return False
    print("  [INFO] Starting lms server...")
    try:
        subprocess.run(["lms", "server", "start"], capture_output=True, text=True,
                       timeout=30, encoding="utf-8", errors="replace")
        time.sleep(5)
    except Exception as e:
        print(f"  [WARN] lms server start failed: {e}")
        return False
    return True


def load_model_via_lms(model_key: str, context_length: Optional[int] = None, gpu_offload: Optional[float] = None) -> tuple[bool, Optional[str]]:
    print(f"\n  [INFO] Loading '{model_key}'...")
    cmd = ["lms", "load", model_key, "--yes"]
    if context_length is not None:
        cmd.extend(["--context-length", str(context_length)])
    if gpu_offload is not None:
        cmd.extend(["--gpu", str(gpu_offload)])
    for attempt in range(2):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=TIMEOUT_LOAD_MODEL,
                encoding="utf-8", errors="replace"
            )
        except subprocess.TimeoutExpired:
            print(f"  [WARN] Load timeout ({TIMEOUT_LOAD_MODEL}s)")
            return False, None
        except FileNotFoundError:
            print("[ERROR] lms.exe not found")
            return False, None
        if result.returncode == 0:
            print("  [OK] Loaded")
            for _ in range(10):
                time.sleep(1)
                loaded = get_current_loaded_model()
                if loaded:
                    print(f"  [INFO] Exact model ID: {loaded['identifier']}")
                    return True, loaded["identifier"]
            return True, model_key
        stderr = result.stderr.strip()
        if "already loaded" in stderr.lower():
            print("  [OK] Already loaded")
            loaded = get_current_loaded_model()
            if loaded:
                return True, loaded["identifier"]
            return True, model_key
        if attempt == 0 and ("No LM Runtime" in stderr or "Runtime not found" in stderr):
            print(f"  [WARN] Daemon error – restarting LM Studio...")
            if _ensure_lmstudio_running():
                time.sleep(3)
                continue
        print(f"  [WARN] Load failed: {stderr[:200]}")
        return False, None
    return False, None


def wait_for_model_ready(timeout: int = TIMEOUT_MODEL_READY) -> bool:
    """Wait for the LM Studio API to return a successful response (model loaded and serving).
    
    Unlike the previous implementation, this only considers HTTP 200 as "ready".
    Other errors (e.g. "No models loaded", 500, timeout) are retried until timeout.
    """
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError
    start = time.time()
    print("  [INFO] Waiting for model readiness", end="", flush=True)
    while time.time() - start < timeout:
        time.sleep(2)
        print(".", end="", flush=True)
        try:
            req = Request(f"{API_BASE}/chat/completions", method="POST",
                          data=json.dumps({
                              "model": "check",
                              "messages": [{"role": "user", "content": "ping"}],
                              "max_tokens": 1,
                          }).encode("utf-8"),
                          headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    print(" ready")
                    return True
        except (HTTPError, URLError, OSError) as e:
            # "No models loaded" (HTTP 400), 503, connection refused → keep waiting
            pass
        except Exception:
            pass
    print(" TIMEOUT")
    return False
