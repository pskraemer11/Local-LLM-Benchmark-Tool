#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gemeinsames Modul fuer LM-Studio-Modell-Management.
Wird von run_benchmarks_v11.py UND custom_benchmark_v11.py importiert.

── Rolle im Gesamtsystem ───────────────────────────────────────────
  Dieses Modul kapselt ALLE Interaktionen mit der LM-Studio-CLI
  (lms load / unload / ps). Es wird von zwei Seiten genutzt:

  1. run_benchmarks_v11.py (Launcher)
     - RUFT load_model_via_lms() und unload_all_models() auf
     - NUR HIER wird geladen/entladen
     - Nutzt get_current_loaded_model() zur Status-Pruefung

  2. custom_benchmark_v11.py (Custom-Pipeline-Subprozess)
     - IMPORTIERT die Konstanten (API_BASE, TIMEOUT_*)
     - RUFT NIEMALS load/unload auf (wird vom Launcher veranlasst)
     - Nutzt check_api_available() als Health-Check (Legacy)

── API- vs. CLI-Zugriff ────────────────────────────────────────────
  - lms CLI:     load, unload, ps, ls (Subprozesse)
  - REST API:    /v1/chat/completions, /v1/models (Inference)
  Die Konstanten API_BASE und TIMEOUT_* werden pipeline-uebergreifend
  von allen Skripten genutzt, sodass Aenderungen (z.B. Port) zentral
  erfolgen koennen.

── Wichtige Hinweise ───────────────────────────────────────────────
  - wait_for_model_ready() und check_api_available() werden aktuell
    NICHT mehr vom Launcher genutzt (ersetzt durch time.sleep(10)
    nach load_model_via_lms()). Sie bleiben fuer alte Skripte erhalten.
  - load_model_via_lms() gibt die EXAKTE Modell-ID aus lms ps --json
    zurueck (z.B. "microsoft/phi-4@q6_k"), die dann von ALLEN Pipelines
    als model-Parameter im API-Call verwendet wird.
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

# ── Pipeline-spezifische Timeouts ───────────────────────────────
# Die Werte werden von run_benchmarks_v11.py importiert und in den
# jeweiligen Pipeline-Funktionen als Subprozess-/Scenario-Timeout
# verwendet. Einige Werte (lmeval_base, evalplus_base) dienen als
# Basis und werden bei Reasoning-Modellen automatisch verdoppelt.
#
#   Key                     Standard  Verwendung
#   ─────────────────────── ───────── ─────────────────────────────
#   custom_subprocess        3600     Subprozess-Timeout (DS1000, CoderEval)
#   evalplus_base             600     Basis-Timeout codegen+evaluate (×2 bei Reasoning)
#   lmeval_base               600     Basis-Timeout lm_eval (×2 bei Reasoning, ×3 bei MathQA)
#   mmlupro_per_subset        300     Timeout pro MMLU-Pro Subset
#   agentic_subprocess        3600    Gesamtlaufzeit-Timeout tool_eval_bench
#   agentic_scenario          600     Timeout pro Szenario (--timeout an tool_eval_bench)
# (Werte in benchmark_config.py)


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
    print("  [INFO] Entlade alle Modelle...")
    try:
        r = subprocess.run(["lms", "unload", "--all"],
                           capture_output=True, text=True, timeout=TIMEOUT_CLI,
                           encoding="utf-8", errors="replace")
        if r.returncode == 0:
            print("  [OK] Entlade-Kommando gesendet")
        else:
            print(f"  [WARN] lms unload: {r.stderr.strip()[:100]}")
    except FileNotFoundError:
        print("[ERROR] lms.exe nicht gefunden")
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
                    print(f"  [WARN] Alter Modell noch aktiv (Versuch {attempt+1}/15)")
                    continue
        except (HTTPError, URLError, Exception):
            print("  [OK] Alter Modell vollstaendig entladen")
            return True
    print("  [WARN] Konnte Entladen nicht bestaetigen – fahre fort")
    return False


def _ensure_lmstudio_running() -> bool:
    """Starte llmster-Daemon + lms server falls nicht verfuegbar."""
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
        print(f"  [WARN] llmster.exe nicht gefunden unter {llmster}")
        return False
    try:
        subprocess.Popen([llmster], shell=True)
        time.sleep(5)
    except Exception as e:
        print(f"  [WARN] llmster start fehlgeschlagen: {e}")
        return False
    print("  [INFO] Starte lms server...")
    try:
        subprocess.run(["lms", "server", "start"], capture_output=True, text=True,
                       timeout=30, encoding="utf-8", errors="replace")
        time.sleep(5)
    except Exception as e:
        print(f"  [WARN] lms server start fehlgeschlagen: {e}")
        return False
    return True


def load_model_via_lms(model_key: str, context_length: Optional[int] = None) -> tuple[bool, Optional[str]]:
    print(f"\n  [INFO] Lade '{model_key}'...")
    cmd = ["lms", "load", model_key, "--yes"]
    if context_length is not None:
        cmd += ["-c", str(context_length)]
        print(f"  [INFO] Context-Length auf {context_length} gesetzt")
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
            print("[ERROR] lms.exe nicht gefunden")
            return False, None
        if result.returncode == 0:
            print("  [OK] Geladen")
            for _ in range(10):
                time.sleep(1)
                loaded = get_current_loaded_model()
                if loaded:
                    print(f"  [INFO] Exakte Modell-ID: {loaded['identifier']}")
                    return True, loaded["identifier"]
            return True, model_key
        stderr = result.stderr.strip()
        if "already loaded" in stderr.lower():
            print("  [OK] Bereits geladen")
            loaded = get_current_loaded_model()
            if loaded:
                return True, loaded["identifier"]
            return True, model_key
        if attempt == 0 and ("No LM Runtime" in stderr or "Runtime not found" in stderr):
            print(f"  [WARN] Daemon-Fehler – starte LM Studio neu...")
            if _ensure_lmstudio_running():
                time.sleep(3)
                continue
        print(f"  [WARN] Load fehlgeschlagen: {stderr[:200]}")
        return False, None
    return False, None


def wait_for_model_ready(timeout: int = TIMEOUT_MODEL_READY) -> bool:
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError
    start = time.time()
    consecutive_failures = 0
    print("  [INFO] Warte auf Bereitschaft", end="", flush=True)
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
                    print(" bereit")
                    return True
        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if "No models loaded" not in body:
                print(" bereit")
                return True
        except Exception as e:
            consecutive_failures += 1
            if consecutive_failures <= 3:
                print(f"\n  [WARN] readiness check: {e}")
    print(" TIMEOUT")
    return False
