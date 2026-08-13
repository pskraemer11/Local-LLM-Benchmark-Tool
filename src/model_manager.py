#!/usr/bin/env python3
"""
Shared module for LM Studio model management.
Imported by run_benchmarks.py AND custom_benchmark.py.

── Role in the system ─────────────────────────────────────────────
  This module encapsulates ALL interactions with the LM Studio CLI
  (lms load / unload / ps). It is used from two sides:

  1. run_benchmarks.py (Launcher)
     - CALLS load_model_via_lms() and has_unloaded_all_models()
     - Model load/unload happens HERE ONLY
     - Uses get_current_loaded_model() for status checking

  2. custom_benchmark.py (Custom pipeline subprocess)
     - IMPORTS the constants (API_BASE, TIMEOUT_*)
     - NEVER calls load/unload (initiated by the launcher)
     - Uses is_api_available() as health-check (legacy)

── API- vs. CLI-Zugriff ────────────────────────────────────────────
  - lms CLI:     load, unload, ps, ls (Subprozesse)
  - REST API:    /v1/chat/completions, /v1/models (Inference)
  Die Konstanten API_BASE und TIMEOUT_* werden pipeline-uebergreifend
  von allen Skripten genutzt, sodass Aenderungen (z.B. Port) zentral
  erfolgen koennen.

── Wichtige Hinweise ───────────────────────────────────────────────
  - is_model_ready() wird vom Launcher nach load_model_via_lms()
    aufgerufen, um die API-Bereitschaft aktiv zu prüfen (anstatt time.sleep(10)).
  - load_model_via_lms() returns the EXACT model ID from lms ps --json
    (e.g. "microsoft/phi-4@q6_k"), used by ALL pipelines as the
    model parameter in API calls.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from benchmark_config import is_support_file
from utils.terminal import error, info, ok, warn

if TYPE_CHECKING:
    from type_defs import AvailableModelInfo, LoadedModelInfo

API_BASE = os.environ.get("LLM_API_BASE", "http://127.0.0.1:1234/v1")
# REST API base (without /v1 suffix) for model management endpoints
_REST_API_BASE = API_BASE.rsplit("/v1", 1)[0] if API_BASE.endswith("/v1") else API_BASE
TIMEOUT_CLI = 30
TIMEOUT_HTTP = 120
TIMEOUT_MODEL_READY = 120
TIMEOUT_LOAD_MODEL = 180
TIMEOUT_HEALTH_CHECK = 5
TIMEOUT_UNLOAD_WAIT = 2

# Magic strings (Code-Review 2026-07-18 §5.3): sentinel model name for
# the readiness health-check. Not a valid LM Studio model, so the server
# responds with HTTP 400 (no model loaded) - exactly the signal we
# need to know that the server is reachable but no model is loaded yet.
HEALTH_CHECK_SENTINEL_MODEL = "check"


# ── TabbyAPI-Fallback (exllamav3-Backend) ─────────────────────────
# Die Modell-Verwaltung (Laden/Entladen/Status) spricht standardmaessig
# LM Studio an (lms CLI bzw. /api/v1/*-Endpunkte). TabbyAPI stellt das
# Modell-Management unter /v1/model/* bereit. Diese Helfer greifen nur,
# wenn der LM-Studio-Pfad fehlschlaegt (Server nicht erreichbar/404).

def _tabbyapi_request(endpoint: str, method: str = "GET", data: dict | None = None,
                      timeout: int = 30, read_body: bool = True) -> dict | None:
    """Low-level request gegen TabbyAPI-Endpunkte (/v1/model/*).

    read_body=False: Antwort nicht lesen (SSE-Streams wie /model/load laufen
    bis Load-Ende weiter). Der Load laeuft in TabbyAPI als Detached-Task,
    der Client-Disconnect ueberlebt. Jeder 2xx-Status gilt als Erfolg.
    """
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen
    body = None if data is None else json.dumps(data).encode("utf-8")
    headers = {"Content-Type": "application/json"} if body is not None else {}
    try:
        req = Request(f"{API_BASE}{endpoint}", data=body, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as resp:
            if not read_body:
                resp.read(1)
                return {}
            raw = resp.read().decode("utf-8")
            if not raw:
                return {}
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                # Erfolgreicher 2xx, aber kein JSON (z.B. SSE vom
                # /model/load-Stream) - als Erfolg werten.
                return {}
    except (HTTPError, URLError, OSError):
        return None


def _tabbyapi_loaded_name() -> str | None:
    """Name des in TabbyAPI aktuell geladenen Modells (oder None).

    Waehrend eines Loads antwortet /v1/model mit 503 ("No models are
    currently loaded") -> wird als None gewertet, Polling laeuft weiter.
    """
    data = _tabbyapi_request("/model")
    if data is None:
        return None
    name = data.get("id")
    return name if name else None


def _tabbyapi_config_load_args() -> dict:
    """cache_size/max_seq_len aus der tabbyAPI config.yml lesen (Fallback-Defaults).

    Ohne cache_size wuerde TabbyAPI 262144 Tokens als KV-Cache ansetzen und
    an 16 GB VRAM (RTX 5060 Ti) mit OOM scheitern. Beim Laden via API werden
    die config.yml-Werte naemlich NICHT uebernommen (nur beim Serverstart).
    """
    cfg_paths = [
        Path(os.environ.get("TABBYAPI_CONFIG", "")) if os.environ.get("TABBYAPI_CONFIG") else None,
        Path(__file__).resolve().parents[1] / "tabbyAPI" / "config.yml",
    ]
    for p in cfg_paths:
        if p is None or not p.is_file():
            continue
        try:
            import re as _re
            text = p.read_text(encoding="utf-8")

            def _find(key: str, default: int, _text: str = text) -> int:
                m = _re.search(rf"^\s*{key}\s*:\s*(\d+)", _text, _re.MULTILINE)
                return int(m.group(1)) if m else default
            return {
                "cache_size": _find(r"cache_size", 8192),
                "max_seq_len": _find(r"max_seq_len", 16384),
            }
        except OSError:
            continue
    return {"cache_size": 8192, "max_seq_len": 16384}


def _tabbyapi_load_model(model_identifier: str, timeout: int = TIMEOUT_LOAD_MODEL) -> str | None:
    """Modell in TabbyAPI laden (Name = Ordner-/Modellname) und auf Load warten."""
    if _tabbyapi_loaded_name() == model_identifier:
        return model_identifier
    payload = {"model_name": model_identifier, **_tabbyapi_config_load_args()}
    if _tabbyapi_request("/model/load", method="POST", data=payload,
                         timeout=10, read_body=False) is None:
        return None
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(2)
        name = _tabbyapi_loaded_name()
        if name == model_identifier:
            return name
    return None


def _tabbyapi_unload(timeout: int = TIMEOUT_MODEL_READY) -> bool:
    """Alle Modelle in TabbyAPI entladen."""
    _tabbyapi_request("/model/unload", method="POST", data={})
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(2)
        if _tabbyapi_loaded_name() is None:
            return True
    return False


# ── Pipeline-specific timeouts ──────────────────────────────────
# These values are imported by run_benchmarks.py and used as
# subprocess/scenario timeouts in each pipeline function.
# Some values (lmeval_base, evalplus_base) serve as base timeouts
# and are automatically doubled for reasoning models.
#
#   Key                     Default  Usage
#   ─────────────────────── ──────── ──────────────────────────────
#   custom_subprocess        3600    Subprocess timeout (DS1000, CoderEval)
#   evalplus_base             600    Base timeout codegen+evaluate (x2 for reasoning)
#   lmeval_base               600    Base timeout lm_eval (x2 for reasoning, x3 for MathQA)
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


def _rest_request(endpoint: str, method: str = "GET", data: dict | None = None,
                  timeout: int = TIMEOUT_HTTP) -> dict | None:
    """Make a request to LM Studio REST API.
    
    Args:
        endpoint: REST API endpoint (e.g., "/api/v1/models/load")
        method: HTTP method (GET, POST)
        data: Request body (will be JSON-encoded)
        timeout: Request timeout in seconds
        
    Returns:
        Parsed JSON response or None on error
    """
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen
    
    url = f"{_REST_API_BASE}{endpoint}"
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8") if data else None
    
    try:
        req = Request(url, method=method, data=body, headers=headers)
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        # Return error details for HTTP errors (4xx, 5xx)
        try:
            error_body = json.loads(e.read().decode("utf-8"))
            warn(f"REST API error {e.code}: {error_body}")
        except Exception:
            warn(f"REST API error {e.code}: {e.reason}")
        return None
    except (URLError, OSError, TimeoutError) as e:
        warn(f"REST API request failed: {type(e).__name__}: {e}")
        return None


def is_api_available() -> bool:
    from urllib.request import Request, urlopen
    try:
        req = Request(f"{API_BASE}/models", method="GET")
        with urlopen(req, timeout=TIMEOUT_HEALTH_CHECK) as resp:
            return resp.status == 200
    except Exception as e:
        # Vertrag: -> bool, True wenn erreichbar, sonst False.
        # Breiter Catch ist beabsichtigt: Jeder Fehler bedeutet "nicht erreichbar".
        warn(f"is_api_available: {type(e).__name__}: {e}")
        return False


def _loaded_from_tabbyapi() -> dict | None:
    """Geladenes Modell aus TabbyAPI (oder None)."""
    name = _tabbyapi_loaded_name()
    if name:
        return {
            "identifier": name,
            "model_identifier": name,
            "display_name": name,
            "status": "loaded",
            "context_length": 0,
        }
    return None


def get_current_loaded_model() -> LoadedModelInfo | None:
    try:
        r = subprocess.run(["lms", "ps", "--json"], capture_output=True, text=True,
                           timeout=15, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            # Fallback: TabbyAPI (z.B. LM Studio läuft, aber CLI antwortet nicht).
            return _loaded_from_tabbyapi()
        entries = safe_json_loads(r.stdout)
        if not entries:
            return _loaded_from_tabbyapi()
        entry = entries[0]
        return {
            "identifier": entry.get("identifier", ""),
            "model_identifier": entry.get("modelKey", entry.get("path", "")),
            "display_name": entry.get("displayName", ""),
            "status": entry.get("status", ""),
            "context_length": entry.get("contextLength"),
        }
    except (json.JSONDecodeError, subprocess.TimeoutExpired, OSError, KeyError) as e:
        # KeyError deckt den Fall ab, dass `lms ps --json` ein dict (statt Liste)
        # liefert - siehe test_handles_dict_format. Vertrag: Optional[LoadedModelInfo].
        warn(f"lms ps --json fehlgeschlagen: {type(e).__name__}: {e}")
        # Fallback: TabbyAPI (geladenes Modell direkt vom /v1/model).
        loaded = _loaded_from_tabbyapi()
        if loaded:
            return loaded
        return None


def has_unloaded_all_models() -> bool:
    """Unload all models via LM Studio REST API.
    
    Uses POST /api/v1/models/unload for each loaded model, then polls
    GET /api/v1/models until no models are reported loaded.
    """
    info("Unloading all models...")
    
    # Get list of loaded models
    models_data = _rest_request("/api/v1/models", method="GET")
    if models_data is None:
        # Fallback: TabbyAPI - entladen ohne Modellliste.
        if _tabbyapi_unload():
            ok("All models unloaded (TabbyAPI)")
            return True
        warn("Could not fetch model list")
        return False
    
    models = models_data.get("models", [])
    loaded_instances = []
    for model in models:
        for inst in model.get("loaded_instances", []):
            loaded_instances.append(inst.get("id"))
    
    if not loaded_instances:
        ok("No models loaded")
        return True
    
    # Unload each loaded model
    for instance_id in loaded_instances:
        result = _rest_request("/api/v1/models/unload", method="POST",
                              data={"instance_id": instance_id})
        if result is not None:
            ok(f"Unloaded {instance_id}")
        else:
            warn(f"Failed to unload {instance_id}")
    
    # Poll until no models are loaded
    for attempt in range(15):
        time.sleep(2)
        models_data = _rest_request("/api/v1/models", method="GET")
        if models_data is None:
            warn(f"Could not fetch model list (attempt {attempt+1}/15)")
            continue
        
        models = models_data.get("models", [])
        still_loaded = sum(len(m.get("loaded_instances", [])) for m in models)
        
        if still_loaded == 0:
            ok("Old model fully unloaded")
            return True
        
        warn(f"{still_loaded} model(s) still loaded (attempt {attempt+1}/15)")
    
    warn("Could not confirm unload - continuing")
    return False


# ── Registry Helpers ─────────────────────────────────────────────────
_REGISTRY_CACHE: dict | None = None

def _load_registry_data() -> dict:
    """Load and cache model_registry.yaml."""
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is not None:
        return _REGISTRY_CACHE
    from ruamel.yaml import YAML
    from ruamel.yaml.error import YAMLError
    rpath = Path(__file__).resolve().parent.parent / "doc-git" / "model_registry.yaml"
    if not rpath.exists():
        _REGISTRY_CACHE = {}
        return _REGISTRY_CACHE
    try:
        y = YAML()
        y.preserve_quotes = True
        with open(rpath, encoding="utf-8") as f:
            data = y.load(f) or {}
    except (YAMLError, OSError, UnicodeDecodeError) as e:
        warn(f"model_registry.yaml fehlerhaft: {e}")
        data = {}
    _REGISTRY_CACHE = data
    return data


def _registry_display_overrides() -> dict[str, str]:
    """Load model_registry.yaml and return {normalized_key: display_name}."""
    from assemble_blueprint import normalize_model_name
    data = _load_registry_data()
    overrides = {}
    for key, entry in data.items():
        if isinstance(entry, dict) and "display_name" in entry:
            overrides[normalize_model_name(key)] = entry["display_name"]
    return overrides


def get_available_models(exclude_keywords: list[str] | None = None, registry_only: bool = False) -> list[AvailableModelInfo]:
    """Query LM Studio for installed models via `lms ls --json`.

    Returns a list of dicts with keys:
        key, model_identifier, display, variant, quant, variants,
        identifier, params, publisher, vram_gb, modelKey
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
                    # Code-Review 2026-08-03 §F1: MTP-Drafter/mmproj-Zusatzdateien
                    # aus der Modellliste filtern (gleiche Logik wie registry_tool
                    # `_is_support_file`). Legitime MTP-Modelle (qwen3.6-27b-mtp,
                    # Ternary-Bonsai-27B-MTP) bleiben unberührt.
                    if is_support_file(
                        item.get("path", "") or item.get("indexedModelIdentifier", ""),
                        item.get("architecture", ""),
                    ):
                        continue
                    quant = item.get("quantization", {}) or {}
                    quant_name = quant.get("name", "") if isinstance(quant, dict) else ""
                    sv = item.get("selectedVariant") or ""
                    unique_key = sv if sv and sv != base_key else (
                        f"{base_key}@{quant_name}" if quant_name
                        and not base_key.lower().endswith(f"@{quant_name.lower()}")
                        else base_key
                    )
                    if not quant_name and base_key.endswith("@?"):
                        # LM Studio kann die Quantisierung dieser GGUF-Datei
                        # nicht parsen (z.B. TQ2_0, ternär) und setzt im
                        # modelKey '?' als Platzhalter. Quant für die Anzeige
                        # aus dem GGUF-Dateinamen zurückgewinnen (letztes
                        # '-' Segment); der Load-Key bleibt LM Studios
                        # exakter '@?'-Key (in der GUI ladbar).
                        fn = (item.get("path") or "").replace("\\", "/").rsplit("/", 1)[-1]
                        if fn.lower().endswith(".gguf"):
                            stem = fn[:-5]
                            if "-" in stem:
                                quant_name = stem.rsplit("-", 1)[-1]
                    display = item.get("displayName", base_key)
                    if quant_name:
                        if "@" in display:
                            display = display.split("@")[0]
                        else:
                            # displayName enthält den Quant ggf. als
                            # Leerzeichen-Variante ("TQ2 0") - entfernen.
                            space_form = quant_name.replace("_", " ")
                            display = display.removesuffix(" " + space_form)
                        display = f"{display}@{quant_name}"
                    sz_bytes = item.get("sizeBytes", 0) or 0
                    models.append({
                        "key": unique_key,
                        "model_identifier": base_key,
                        "display": display,
                        "variant": sv or base_key,
                        "quant": quant_name,
                        "variants": item.get("variants") or [],
                        "identifier": item.get("indexedModelIdentifier", base_key),
                        "params": item.get("paramsString", ""),
                        "publisher": item.get("publisher", ""),
                        "vram_gb": round(sz_bytes / 1e9, 2) if sz_bytes else "",
                        "modelKey": base_key,
                    })
            if models:
                # Apply registry display_name overrides
                overrides = _registry_display_overrides()
                if overrides:
                    from assemble_blueprint import normalize_model_name
                    for m in models:
                        normalized_key = normalize_model_name(m["model_identifier"])
                        if normalized_key in overrides:
                            m["display"] = overrides[normalized_key]
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
                if registry_only:
                    from assemble_blueprint import normalize_model_name
                    registry_data = _load_registry_data()
                    registry_base_keys = set()
                    for key in registry_data:
                        if isinstance(registry_data[key], dict):
                            registry_base_keys.add(
                                normalize_model_name(key).split("@")[0])
                    filtered = []
                    for m in models:
                        # model_identifier = LMS modelKey (ohne Quant), key =
                        # unique_key (inkl. @quant, z.B. über selectedVariant).
                        # Registry-Keys tragen i.d.R. den @quant-Suffix; der
                        # Filter prüft die Modell-IDENTITÄT (Basis ohne @quant,
                        # da Sampling-Parameter pro Modell gelten, nicht pro
                        # Quant). Deckt auch Mischquants ab (Registry
                        # '@mixed' vs. LMS 'Q3_K').
                        base = normalize_model_name(m["model_identifier"]).split("@")[0]
                        if base in registry_base_keys:
                            filtered.append(m)
                    missing = len(models) - len(filtered)
                    if missing:
                        warn(f"{missing} Modelle nicht in Registry - mit `python registry_tool.py sync` hinzufügen. Ignoriert.")
                    models = filtered
                return models
        warn(f"lms ls failed: {result.stderr.strip()}")
    except FileNotFoundError:
        error("lms.exe not found. Is LM Studio installed?")
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        warn(f"Error with lms ls: {e}")
    return []


def parse_selection(choice: str, max_val: int) -> list[int] | None:
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


def _is_lmstudio_running() -> bool:
    """Ensure LM Studio server is reachable, starting it if necessary.

    Order of operations (each step is a no-op if the previous succeeded):
      1. Check whether /v1/models responds - if yes, return True.
      2. Try `lms server start` directly. Modern LMS versions manage the
         underlying daemon themselves.
      3. Fall back to finding the latest installed `llmster.exe` under
         `.lmstudio/llmster/` via glob, sorted by version directory name.

    Previously this function relied on a hardcoded path
    `.lmstudio/llmster/0.0.12-1/llmster.exe` which broke whenever LMS
    shipped a new version. See Code-Review 2026-07-18, Bug 2.
    """
    from urllib.error import URLError
    from urllib.request import Request, urlopen
    # 1. Already running?
    try:
        req = Request(f"{API_BASE}/models", method="GET")
        with urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                return True
    except (URLError, OSError, TimeoutError):
        pass

    # 2. Try `lms server start` (preferred - LMS handles daemon internally)
    print("  [INFO] LM Studio-Server nicht erreichbar - versuche 'lms server start'...")
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
                    ok("LM Studio-Server gestartet via 'lms server start'")
                    return True
        except (URLError, OSError, TimeoutError):
            pass
        warn(f"'lms server start' brachte Server nicht hoch: "
             f"{r.stderr.strip()[:120]}")
    except FileNotFoundError:
        warn("lms.exe nicht im PATH - versuche llmster.exe direkt")
    except subprocess.TimeoutExpired:
        warn("'lms server start' Timeout")
    except (OSError, subprocess.SubprocessError) as e:
        warn(f"'lms server start' Fehler: {e}")

    # 3. Fallback: find the newest llmster.exe under .lmstudio/llmster/*/
    llmster_root = Path(os.path.dirname(os.path.dirname(__file__))) / ".lmstudio" / "llmster"
    if llmster_root.exists():
        # Find all version directories matching pattern "<version>/llmster.exe"
        candidates = sorted(
            (p for p in llmster_root.iterdir() if p.is_dir()),
            key=lambda p: p.name,
            reverse=True,  # newest version first (lexicographic - works for semver)
        )
        for ver_dir in candidates:
            exe = ver_dir / "llmster.exe"
            if exe.is_file():
                info(f"Starte llmster {ver_dir.name}...")
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
                                ok("LM Studio-Server gestartet via llmster")
                                return True
                    except (URLError, OSError):
                        # Server didn't respond yet after llmster start;
                        # try the next version. This is intentionally
                        # silent (Code-Review 2026-07-18 §5.2).
                        pass
                except (OSError, subprocess.SubprocessError) as e:
                    warn(f"llmster {ver_dir.name} start fehlgeschlagen: {e}")
    error("Konnte LM Studio-Server nicht starten")
    return False


# Code-Review 2026-07-18 §6.1: defensive model_identifier validation.
# All subprocess calls in this module already use list-form (not
# shell=True), so a malicious model_identifier cannot inject shell syntax.
# But we still validate the character set to fail early on bad data
# (typos, copy-paste errors, etc.) and to provide a clearer error
# message than the underlying subprocess errors.
# '?' ist LM Studios Platzhalter für nicht parsebare Quant-Namen
# (z.B. TQ2_0, ternär) - der modelKey ist dann z.B. "...@?".
_VALID_MODEL_KEY_RE = re.compile(r"^[A-Za-z0-9._/\-@:+=#?]{1,256}$")


def _validate_model_identifier(model_identifier: str) -> str:
    """Return model_identifier if it contains only safe characters; raise ValueError otherwise.

    Valid characters: ASCII letters/digits, `.`, `_`, `/`, `-`, `@`, `:`, `+`, `=`, `#`, `?`.
    Max length 256 (longer-than-realistic for any model name on HF).
    '?' tritt als LM-Studio-Platzhalter in modelKeys auf, deren Quant-Name
    nicht geparst werden kann.
    """
    if not isinstance(model_identifier, str) or not _VALID_MODEL_KEY_RE.match(model_identifier):
        raise ValueError(
            f"Invalid model_identifier: {model_identifier!r}. "
            f"Allowed: alphanumeric, '.', '_', '/', '-', '@', ':', '+', '=', '#', '?'; max 256 chars."
        )
    return model_identifier


def load_model_via_lms(model_identifier: str, gpu_offload: float | None = None) -> tuple[bool, str | None]:
    """Load model via LM Studio REST API.
    
    Uses POST /api/v1/models/load to load a model into memory.
    Returns (success, instance_id) tuple.
    """
    # Code-Review 2026-07-18 §6.1: validate input early.
    try:
        _validate_model_identifier(model_identifier)
    except ValueError as e:
        error(str(e))
        return False, None
    
    info(f"Loading '{model_identifier}'...")
    
    # Build load request payload
    payload = {"model": model_identifier, "echo_load_config": True}
    if gpu_offload is not None:
        payload["gpu_offload"] = gpu_offload

    for attempt in range(2):
        result = _rest_request("/api/v1/models/load", method="POST", data=payload,
                              timeout=TIMEOUT_LOAD_MODEL)

        if result is not None and result.get("status") == "loaded":
            instance_id = result.get("instance_id", model_identifier)
            load_time = result.get("load_time_seconds", 0)
            load_cfg = result.get("load_config", {})
            parallel = load_cfg.get("parallel", "?")
            ok(f"Loaded in {load_time:.1f}s (np={parallel})")
            info(f"Instance ID: {instance_id}")
            return True, instance_id
        
        if result is not None:
            ok("Model already loaded")
            models_data = _rest_request("/api/v1/models", method="GET")
            if models_data:
                for model in models_data.get("models", []):
                    if model.get("key") == model_identifier or model_identifier in model.get("key", ""):
                        for inst in model.get("loaded_instances", []):
                            return True, inst.get("id", model_identifier)
            return True, model_identifier
        
        # Handle specific errors
        if result is None:
            # Fallback: TabbyAPI (Modellname = Modell-/Ordnername).
            # Wird zuerst versucht, unabhaengig vom LM-Studio-Status.
            loaded = _tabbyapi_load_model(model_identifier)
            if loaded:
                ok(f"Loaded via TabbyAPI: {loaded}")
                return True, loaded
            if attempt == 0:
                # Check if LM Studio is running, retry if needed
                if _is_lmstudio_running():
                    warn("Load failed - retrying...")
                    time.sleep(3)
                    continue
                else:
                    warn("LM Studio not running")

        warn(f"Load failed (attempt {attempt+1}/2)")
        return False, None
    
    return False, None


def is_model_ready(timeout: int = TIMEOUT_MODEL_READY) -> bool:
    """Wait for the LM Studio API to return a successful response (model loaded and serving).
    
    Unlike the previous implementation, this only considers HTTP 200 as "ready".
    Other errors (e.g. "No models loaded", 500, timeout) are retried until timeout.
    """
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen
    start = time.time()
    print("  [INFO] Waiting for model readiness", end="", flush=True)
    while time.time() - start < timeout:
        time.sleep(2)
        print(".", end="", flush=True)
        # TabbyAPI: bereit, sobald /v1/model/status ein Modell meldet.
        if _tabbyapi_loaded_name() is not None:
            print(" OK (TabbyAPI)")
            return True
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
        except (HTTPError, URLError, OSError):
            # "No models loaded" (HTTP 400), 503, connection refused → keep waiting
            pass
        except (RuntimeError, ValueError, TimeoutError) as e:
            # Server-side protocol errors (JSON parse, malformed response, etc.) → keep waiting
            warn(f"Health-check protocol error: {e}")
    print(" TIMEOUT")
    warn("Model readiness timeout")
    return False
