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
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from benchmark_config import PIPELINE_TIMEOUTS

API_BASE = "http://127.0.0.1:1234/v1"
TIMEOUT_CLI = 30
TIMEOUT_HTTP = 120
TIMEOUT_MODEL_READY = 120
TIMEOUT_LOAD_MODEL = 180
TIMEOUT_HEALTH_CHECK = 5
TIMEOUT_UNLOAD_WAIT = 2

# Magic strings (Code-Review 2026-07-18 §5.3): sentinel model name for
# the readiness health-check. Not a valid LM Studio model, so the server
# responds with HTTP 400 (no model loaded) – exactly the signal we
# need to know that the server is reachable but no model is loaded yet.
HEALTH_CHECK_SENTINEL_MODEL = "check"

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


# Code-Review 2026-07-18 §6.2: central safe JSON loader. The LMS server
# is trusted, but using object_pairs_hook=OrderedDict ensures that
# all parsed objects preserve insertion order regardless of LMS
# version changes (CPython 3.7+ guarantees this for regular dicts,
# but a future JSON change with a `__getattr__`-style hook could
# cause surprises). The cost is one wrapper class per object.
def safe_json_loads(text: str) -> Any:
    """Parse JSON text into Python objects with deterministic ordering.

    Returns lists, OrderedDicts, and primitives. Top-level dicts are
    also OrderedDicts. Safe against LMS schema changes.
    """
    from collections import OrderedDict
    return json.loads(text, object_pairs_hook=OrderedDict)


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
        entries = safe_json_loads(r.stdout)
        if not entries:
            return None
        entry = entries[0]
        return {
            "identifier": entry.get("identifier", ""),
            "model_key": entry.get("modelKey", entry.get("path", "")),
            "display_name": entry.get("displayName", ""),
            "status": entry.get("status", ""),
            "context_length": entry.get("contextLength"),
        }
    except (json.JSONDecodeError, subprocess.TimeoutExpired, Exception):
        return None


def unload_all_models() -> bool:
    """Unload all models and wait until the LMS process reports no loaded models.

    Polls `lms ps --json` (the canonical LMS state source) instead of pinging
    /v1/chat/completions with `model:"check"`. The HTTP-ping approach is
    racy because LM Studio can answer the bogus "check" model with HTTP 400,
    which the old code misinterpreted as "model gone" while the old model
    was still resident. See Code-Review 2026-07-18, Bug 1.
    """
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

    # Poll lms ps --json until no models are reported loaded. This is the
    # single source of truth for LMS state (no HTTP 400 vs. 200 ambiguity).
    for attempt in range(15):
        time.sleep(2)
        try:
            r = subprocess.run(["lms", "ps", "--json"],
                               capture_output=True, text=True, timeout=10,
                               encoding="utf-8", errors="replace")
            if r.returncode != 0:
                print(f"  [WARN] lms ps failed (attempt {attempt+1}/15): "
                      f"{r.stderr.strip()[:80]}")
                continue
            try:
                loaded_entries = safe_json_loads(r.stdout)
            except json.JSONDecodeError:
                print(f"  [WARN] lms ps: invalid JSON (attempt {attempt+1}/15)")
                continue
            if not loaded_entries:
                print("  [OK] Old model fully unloaded")
                return True
            print(f"  [WARN] {len(loaded_entries)} model(s) still loaded "
                  f"(attempt {attempt+1}/15)")
        except subprocess.TimeoutExpired:
            print(f"  [WARN] lms ps timeout (attempt {attempt+1}/15)")
    print("  [WARN] Could not confirm unload – continuing")
    return False


def _registry_display_overrides() -> dict[str, str]:
    """Load model_registry.yaml and return {normalized_key: display_name}."""
    from assemble_blueprint import normalize_model_name
    rpath = Path(__file__).resolve().parent / "doc-git" / "model_registry.yaml"
    if not rpath.exists():
        return {}
    try:
        from ruamel.yaml import YAML
        y = YAML()
        y.preserve_quotes = True
        with open(rpath, "r", encoding="utf-8") as f:
            data = y.load(f) or {}
    except Exception:
        return {}
    overrides = {}
    for key, entry in data.items():
        if isinstance(entry, dict) and "display_name" in entry:
            overrides[normalize_model_name(key)] = entry["display_name"]
    return overrides


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
            data = safe_json_loads(result.stdout)
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
                # Apply registry display_name overrides
                overrides = _registry_display_overrides()
                if overrides:
                    from assemble_blueprint import normalize_model_name
                    for m in models:
                        nk = normalize_model_name(m["model_key"])
                        if nk in overrides:
                            m["display"] = overrides[nk]
                            if m["quant"]:
                                m["display"] = f"{m['display']}@{m['quant']}"
                if exclude_keywords:
                    # Code-Review 2026-07-18 §4.1: filter on BOTH key and
                    # display, not just key. Some models have publisher
                    # prefixes in `key` (e.g. "unsloth/phi-4") but the
                    # filter keywords ("vision", "embed") may only appear
                    # in `display`. Filter on the concatenation to catch
                    # both.
                    models = [m for m in models
                              if not any(
                                  kw in (m["key"] + " " + m["display"]).lower()
                                  for kw in exclude_keywords)]
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
    """Ensure LM Studio server is reachable, starting it if necessary.

    Order of operations (each step is a no-op if the previous succeeded):
      1. Check whether /v1/models responds – if yes, return True.
      2. Try `lms server start` directly. Modern LMS versions manage the
         underlying daemon themselves.
      3. Fall back to finding the latest installed `llmster.exe` under
         `.lmstudio/llmster/` via glob, sorted by version directory name.

    Previously this function relied on a hardcoded path
    `.lmstudio/llmster/0.0.12-1/llmster.exe` which broke whenever LMS
    shipped a new version. See Code-Review 2026-07-18, Bug 2.
    """
    from urllib.request import Request, urlopen
    from urllib.error import URLError
    # 1. Already running?
    try:
        req = Request(f"{API_BASE}/models", method="GET")
        with urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                return True
    except (URLError, Exception):
        pass

    # 2. Try `lms server start` (preferred – LMS handles daemon internally)
    print("  [INFO] LM Studio-Server nicht erreichbar – versuche 'lms server start'...")
    try:
        r = subprocess.run(["lms", "server", "start"],
                           capture_output=True, text=True, timeout=30,
                           encoding="utf-8", errors="replace")
        time.sleep(5)
        # Verify
        try:
            req = Request(f"{API_BASE}/models", method="GET")
            with urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    print("  [OK] LM Studio-Server gestartet via 'lms server start'")
                    return True
        except (URLError, Exception):
            pass
        print(f"  [WARN] 'lms server start' brachte Server nicht hoch: "
              f"{r.stderr.strip()[:120]}")
    except FileNotFoundError:
        print("  [WARN] lms.exe nicht im PATH – versuche llmster.exe direkt")
    except subprocess.TimeoutExpired:
        print("  [WARN] 'lms server start' Timeout")
    except Exception as e:
        print(f"  [WARN] 'lms server start' Fehler: {e}")

    # 3. Fallback: find the newest llmster.exe under .lmstudio/llmster/*/
    llmster_root = Path(os.path.dirname(os.path.dirname(__file__))) / ".lmstudio" / "llmster"
    if llmster_root.exists():
        # Find all version directories matching pattern "<version>/llmster.exe"
        candidates = sorted(
            (p for p in llmster_root.iterdir() if p.is_dir()),
            key=lambda p: p.name,
            reverse=True,  # newest version first (lexicographic – works for semver)
        )
        for ver_dir in candidates:
            exe = ver_dir / "llmster.exe"
            if exe.is_file():
                print(f"  [INFO] Starte llmster {ver_dir.name}...")
                try:
                    subprocess.Popen([str(exe)])
                    time.sleep(5)
                    # Verify
                    try:
                        req = Request(f"{API_BASE}/models", method="GET")
                        with urlopen(req, timeout=3) as resp:
                            if resp.status == 200:
                                # Now also start the LMS server
                                subprocess.run(["lms", "server", "start"],
                                               capture_output=True, text=True, timeout=30,
                                               encoding="utf-8", errors="replace")
                                time.sleep(5)
                                print("  [OK] LM Studio-Server gestartet via llmster")
                                return True
                    except (URLError, Exception):
                        # Server didn't respond yet after llmster start;
                        # try the next version. This is intentionally
                        # silent (Code-Review 2026-07-18 §5.2).
                        pass
                except Exception as e:
                    print(f"  [WARN] llmster {ver_dir.name} start fehlgeschlagen: {e}")
    print("  [ERROR] Konnte LM Studio-Server nicht starten")
    return False


# Code-Review 2026-07-18 §6.1: defensive model_key validation.
# All subprocess calls in this module already use list-form (not
# shell=True), so a malicious model_key cannot inject shell syntax.
# But we still validate the character set to fail early on bad data
# (typos, copy-paste errors, etc.) and to provide a clearer error
# message than the underlying subprocess errors.
_VALID_MODEL_KEY_RE = re.compile(r"^[A-Za-z0-9._/\-@:+=#]{1,256}$")


def _validate_model_key(model_key: str) -> str:
    """Return model_key if it contains only safe characters; raise ValueError otherwise.

    Valid characters: ASCII letters/digits, `.`, `_`, `/`, `-`, `@`, `:`, `+`, `=`, `#`.
    Max length 256 (longer-than-realistic for any model name on HF).
    """
    if not isinstance(model_key, str) or not _VALID_MODEL_KEY_RE.match(model_key):
        raise ValueError(
            f"Invalid model_key: {model_key!r}. "
            f"Allowed: alphanumeric, '.', '_', '/', '-', '@', ':', '+', '=', '#'; max 256 chars."
        )
    return model_key


def load_model_via_lms(model_key: str, gpu_offload: Optional[float] = None) -> tuple[bool, Optional[str]]:
    # Code-Review 2026-07-18 §6.1: validate input early. subprocess.run
    # already uses list-form (no shell injection possible), but bad
    # input should fail with a clear message, not a cryptic CLI error.
    try:
        _validate_model_key(model_key)
    except ValueError as e:
        print(f"  [ERROR] {e}")
        return False, None
    print(f"\n  [INFO] Loading '{model_key}'...")
    cmd = ["lms", "load", model_key, "--yes"]
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
                              "model": HEALTH_CHECK_SENTINEL_MODEL,
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
