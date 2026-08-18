"""
Central configuration for all benchmark pipelines.

Imported by:
  - run_benchmarks.py       (PIPELINE_DISCOVERY, TOOL_EVAL_SCENARIO_IDS)
  - consolidate_results.py  (extract_quant_from_key, CAT_WEIGHTS, ...)
  - tests/test_scores.py        (CAT_WEIGHTS, OVERALL_WEIGHTS)

Model identity: publisher/model@quant (3 entities, always unique).
Quant is extracted from the key — no static QUANT_MAP needed.
Fallback: GGUF filename (Source of Truth).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from type_defs import ModelConfig
from model_identity import match_registry_key, normalize_lms_model_name, normalized_lms_key
from utils.terminal import warn

BLACKLIST = [
    # Embedding-Modelle (separates Projekt embedding-eval/)
    "embed",
    "bge-m3",
    # < 16K native context -> zu klein fuer Coding-Benchmarks
    "datagemma-rig",
    "granitelib-rag",
    # OCR / Vision / Audio
    "ocr",
    "vision",
    "flux",
    "whisper",
    "translat",
    "transcription",
    "transcribe",
    "audit",
    "audio",
    "vl",           # vl = vision language (i.A.)
    # Rest
    "rag",
    "f2llm",                # F2LLM-v2-Familie = reine Embedding-Modelle (Feature Extraction, kein Chat; 80M-14B)
    "imatrix",              # Importance Matrix GGUF files (< 200 MB) — companion files, not standalone models
]

# MTP drafter models: name contains "mtp" AND size < 1 GB.
# These are companion files (e.g. for speculative decoding), not standalone models.
# Regular LLMs with "mtp" in the name but > 1 GB are NOT drafters.
def is_mtp_drafter(model_name: str, file_size_bytes: int = 0) -> bool:
    """True if the model is an MTP drafter (companion file, not standalone).

    Rule: name contains "mtp" (case-insensitive) AND size < 1 GB.
    """
    if "mtp" not in model_name.lower():
        return False
    return file_size_bytes < 1_000_000_000  # < 1 GB

EXCLUDE_KEYWORDS = BLACKLIST


# ── Benchmark-Kategorie-Defaults (Fallback, seit 2026-08-05) ──
# Seit 2026-08-06 gilt das Sampling-Design (MODEL_CATEGORY_SAMPLING >
# Kategorie-Defaults; JSON-temp/top_p GUI-only, siehe get_model_config).
# Die Kategorie-Defaults greifen, wenn weder Tabellen-Zelle noch Thinking-Lauf
# zutrifft. MODEL_TEMP_OVERRIDES und der Knowledge-Floor wurden entfernt
# (Punkte 3+4, Transparenz-Refactor 05.08.2026).
# Temperaturen: Recherche 06.08.2026 (doc-git/Temperature Recommondations_en.md).
# Instruct-Modelle nutzen Kategorie-Defaults (coding 0.2, knowledge 0.6,
# agentic 0.6, math 0.7); Reasoning/Thinking-Modelle (im --thinking-Lauf)
# nutzen BENCHMARK_THINKING_DEFAULTS (pauschal 0.6/0.95).
BENCHMARK_CATEGORY_DEFAULTS = {
    "coding": {
        "temperature": 0.2,
        "top_p": 1.0,
        "max_tokens": 4096,
        "enable_thinking": False,
    },
    "math": {
        "temperature": 0.7,
        "top_p": 0.95,
        "max_tokens": 4096,
        "enable_thinking": False,
    },
    "knowledge": {
        "temperature": 0.6,
        "top_p": 1.0,
        "max_tokens": 4096,
        "enable_thinking": False,
    },
    "agentic": {
        "temperature": 0.6,
        "top_p": 0.95,
        "max_tokens": 4096,
        "enable_thinking": False,
    },
}

# ── Thinking-Defaults (Fallback im --thinking-Lauf) ──
# Reasoning/Thinking-Modelle pauschal t=0.6 / top_p 0.95 fuer alle
# Kategorien (offizielle Thinking-Werte: DeepSeek-R1, Qwen3, Qwen3.6,
# Nemotron-Cascade, Kimi-K2; "DO NOT use greedy"). top_p 1.0-Feld:
# flat top_p 0.95 wie in der Recherche vorgeschlagen.
BENCHMARK_THINKING_DEFAULTS = {
    "temperature": 0.6,
    "top_p": 0.95,
    "max_tokens": 4096,
    "enable_thinking": True,
}


# Reasoning-Muster fuer enable_thinking-Override via --thinking-Flag
# Ergänzt 2026-08-06: deckt die Registry-Modelle mit reasoning=thinking ab
# (auch die, bei denen "think" nur eingebettet ist: mirothinker, ...-thinking-…).
REASONING_PATTERNS = {
    "acemath",
    "deepseek",
    "gemma",
    "phi-4-reasoning",
    "ministral",
    "nemotron",
    "apriel",
    "magistral",
    "gpt-oss",
    "reasoning",
    "think",
    "r1",
    "rnj",
    "qwq",
    "cascade",
    "cot",
    "phi-4",
    "kimi",
    "mirothinker",
    "thinking",
    "glm-4.7",
    "glm-4.6v",
    "qwen3.5",
    "qwen3.6",
    "qwen3-14b",
    "qwen3-coder-reap",
}

# ── gpt-oss: Reasoning-Level / Budget (zentrale Quelle) ──
# Steuert BOTH Ebenen, damit sie synchron bleiben:
#   1. LM-Studio-Engine-Config (registry_tool.py patch-reasoning-effort schreibt reasoningEffort/budgetTokens)
#   2. System-Prompt des gptoss_reasoning-Blueprints (assemble_blueprint.py)
# OpenAI: "The reasoning level can be set in the system prompts, e.g. 'Reasoning: high'."
GPTOSS_REASONING_EFFORT = "medium"
GPTOSS_REASONING_BUDGET = 4096

# ── Quantization extraction from model key (canonical identity) ──
# The quant is ALWAYS part of the key: publisher/model@quant.
# No static map needed — extract directly from the key.
# Fallback: read from GGUF filename (Source of Truth).

_KNOWN_QUANTS = (
    "q1_0", "q2_k", "q2_k_s", "q3_k_xs", "q3_k_s", "q3_k_m", "q3_k_l",
    "q4_0", "q4_1", "q4_k_s", "q4_k_m", "q4_k_xl",
    "q5_0", "q5_1", "q5_k_s", "q5_k_m",
    "q6_k", "q8_0", "q8_1",
    "iq1_s", "iq1_m",
    "iq2_xxs", "iq2_xs", "iq2_s", "iq2_m",
    "iq3_xxs", "iq3_xs", "iq3_s", "iq3_m", "iq3_nl",
    "iq4_xs", "iq4_nl",
    "mxfp4", "mxpr4", "fp16", "f16",
    "bf16",
)


def extract_quant_from_key(model_key: str) -> str:
    """Extract the quant suffix from a model key.

    Key format: publisher/model@quant
    Returns the quant in UPPERCASE (e.g. "Q3_K_S") or "" if no @quant present.
    """
    if "@" not in model_key:
        return ""
    _, quant = model_key.split("@", 1)
    return quant.upper()


def guess_quant_from_filename(filename: str) -> str:
    """Guess quant from GGUF filename when key has no @quant.

    Uses known quant patterns. Returns quant in UPPERCASE or "".
    """
    name = filename.lower().removesuffix(".gguf")
    for quant in _KNOWN_QUANTS:
        if quant.replace("_", "-") in name or quant in name:
            return quant.upper()
    # Fallback: last hyphen-separated part if it looks like a quant
    parts = name.rsplit("-", 1)
    if len(parts) == 2 and parts[1] and parts[1][0] in ("q", "i", "f", "m", "b"):
        return parts[1].upper()
    return ""


def get_quant(model_identifier: str) -> str:
    """Get the quant of a model from its key (canonical identity).

    The key format is ALWAYS publisher/model@quant — the @quant is part of the
    unique identity. No static map, no fallback. Base entries without @quant
    are invalid and return "?".
    """
    if not model_identifier:
        return "?"
    quant = extract_quant_from_key(model_identifier)
    return quant if quant else "?"


# Registry cache for get_quant() step 5 (avoids re-parsing YAML on every call)
_QUANT_REGISTRY_CACHE: dict[str, Any] = {}
_QUANT_REGISTRY_LOADED = False


def _load_quant_registry() -> dict[str, Any]:
    """Load and cache model_registry.yaml for get_quant() fallback."""
    global _QUANT_REGISTRY_CACHE, _QUANT_REGISTRY_LOADED
    if _QUANT_REGISTRY_LOADED:
        return _QUANT_REGISTRY_CACHE
    from pathlib import Path as _Path

    registry_path = _Path(__file__).resolve().parent.parent / "doc-git" / "model_registry.yaml"
    try:
        from ruamel.yaml import YAML
        from ruamel.yaml.error import YAMLError

        y = YAML()
        with open(registry_path, encoding="utf-8") as f:
            _QUANT_REGISTRY_CACHE = y.load(f) or {}
    except (YAMLError, OSError, UnicodeDecodeError) as _e:
        warn(f"model_registry.yaml fehlerhaft: {_e}")
        _QUANT_REGISTRY_CACHE = {}
    _QUANT_REGISTRY_LOADED = True
    return _QUANT_REGISTRY_CACHE


# ── MMLU-Pro-Subsets (ARCHIVIERT 12.07.2026) ──
# MMLU-Pro wurde aus dem aktiven Benchmark-Settings entfernt, weil die
# Auswertung auf 16-GB-VRAM-Hardware zu zeitaufwändig war (siehe
# Code-Review_2026-07-12.md §3.1 D4).
#
# Für Re-Aktivierung: siehe `Archiv/run_mmlupro_benchmark.py` - dort ist
# die vollständige Logik als self-contained Skript ausgelagert.
# Aufzurufen mit:
#     python Archiv/run_mmlupro_benchmark.py --model gemma-4-26b-a4b-it
#
# Code-Review 2026-07-18 §4.3: The legacy `MMLU_PRO_ENABLED = False`
# constant was imported but never read anywhere; it has been removed.
# MMLU_PRO_SUBSETS itself is still used by consolidate_results.py
# as a defensive directory-exclusion list (`if item not in
# MMLU_PRO_SUBSETS`) so it stays.
MMLU_PRO_SUBSETS = [
    "mmlu_pro_biology",
    "mmlu_pro_business",
    "mmlu_pro_chemistry",
    "mmlu_pro_computer_science",
    "mmlu_pro_economics",
    "mmlu_pro_engineering",
    "mmlu_pro_health",
    "mmlu_pro_history",
    "mmlu_pro_law",
    "mmlu_pro_math",
    "mmlu_pro_other",
    "mmlu_pro_philosophy",
    "mmlu_pro_physics",
    "mmlu_pro_psychology",
]


# ── Benchmark-Sampling-Tabelle Temperatur (Modell x Kategorie) ──
# Hoechste Precedence fuer temperature/top_p im Benchmark (2026-08-06):
#   MODEL_CATEGORY_SAMPLING > Kategorie-Defaults > Thinking-Defaults
# Die LMS-JSON-Temperatur wird fuer Benchmarks IGNORIERT (ein Einzelwert pro
# Modell kann die Kategorie-Differenzierung nicht ausdruecken); sie gilt nur
# noch fuer die GUI-Nutzung. Quellen: doc-git/Temperature Recommondations_en.md
# (Uebersichtstabelle). Fehlende Zellen = Kategorie-Defaults. Keys sind die
# normalisierten Modellnamen (Prefix-Match, "name"-Key bzw. "key"-Praefix).
MODEL_CATEGORY_SAMPLING: dict[str, dict[str, tuple[float, float]]] = {
    "qwen3-coder-30b-a3b": {
        "coding": (0.7, 0.8),
        "knowledge": (0.7, 0.8),
        "agentic": (0.7, 0.8),
        "math": (0.7, 0.8),
    },
    "qwen3-coder-reap": {
        "coding": (0.7, 0.8),
        "knowledge": (0.7, 0.8),
        "agentic": (0.7, 0.8),
        "math": (0.7, 0.8),
    },
    "qwen2-5-coder-14b": {
        "knowledge": (0.7, 0.8),
        "agentic": (0.6, 0.8),
        "math": (0.7, 0.8),
    },
    "qwen3-30b-a3b-instruct-2507": {
        "coding": (0.7, 0.8),
        "knowledge": (0.7, 0.8),
        "agentic": (0.7, 0.8),
        "math": (0.7, 0.8),
    },
    "qwen3-14b": {
        "coding": (0.6, 0.95),
        "knowledge": (0.6, 0.95),
        "agentic": (0.6, 0.95),
        "math": (0.6, 0.95),
    },
    "qwen3-5-9b": {
        "coding": (0.6, 0.95),
        "knowledge": (1.0, 0.95),
        "agentic": (1.0, 0.95),
        "math": (1.0, 1.0),
    },
    "qwen3-6-27b": {
        "coding": (0.6, 0.95),
        "knowledge": (1.0, 0.95),
        "agentic": (1.0, 0.95),
        "math": (1.0, 0.95),
    },
    "qwen3-6-28b-reap-i1": {
        "coding": (0.6, 0.95),
        "knowledge": (1.0, 0.95),
        "agentic": (1.0, 0.95),
        "math": (1.0, 0.95),
    },
    "deepseek-coder-33b": {
        "coding": (0.2, 0.95),
        "knowledge": (0.7, 0.95),
        "agentic": (0.2, 0.95),
        "math": (0.5, 0.95),
    },
    "deepseek-coder-v2": {
        "coding": (0.3, 0.95),
        "knowledge": (0.7, 0.95),
        "agentic": (0.3, 0.95),
        "math": (0.4, 0.95),
    },
    "gpt-oss": {
        "coding": (1.0, 1.0),
        "knowledge": (1.0, 1.0),
        "agentic": (1.0, 1.0),
        "math": (1.0, 1.0),
    },
    "phi-4": {
        "coding": (0.0, 1.0),
        "knowledge": (0.0, 1.0),
        "agentic": (0.0, 1.0),
        "math": (0.0, 1.0),
    },
    "gemma-4": {
        "coding": (1.0, 0.95),
        "knowledge": (1.0, 0.95),
        "agentic": (1.0, 0.95),
        "math": (1.0, 0.95),
    },
    "gemma4-26b-a4b-reap-25": {
        "coding": (1.0, 0.95),
        "knowledge": (1.0, 0.95),
        "agentic": (1.0, 0.95),
        "math": (1.0, 0.95),
    },
    "rnj-1": {
        "coding": (0.2, 0.95),
        "knowledge": (0.2, 0.95),
        "agentic": (0.2, 0.95),
        "math": (0.2, 0.95),
    },
    "granite-4": {
        "coding": (0.0, 1.0),
        "knowledge": (0.0, 1.0),
        "agentic": (0.0, 1.0),
        "math": (0.0, 1.0),
    },
    "codestral-22b": {
        "coding": (0.2, 0.95),
        "knowledge": (0.7, 0.95),
        "agentic": (0.2, 0.95),
        "math": (0.3, 0.95),
    },
    "mamba-codestral": {
        "coding": (0.2, 0.95),
        "knowledge": (0.7, 0.95),
        "agentic": (0.2, 0.95),
        "math": (0.3, 0.95),
    },
    "devstral": {
        "coding": (0.15, 0.95),
        "knowledge": (0.4, 0.95),
        "agentic": (0.15, 0.95),
        "math": (0.3, 0.95),
    },
    "mistralai-magistral": {
        "coding": (0.7, 0.95),
        "knowledge": (0.7, 0.95),
        "agentic": (0.7, 0.95),
        "math": (0.7, 0.95),
    },
    "ministral": {
        "coding": (0.1, 0.95),
        "knowledge": (0.1, 0.95),
        "agentic": (0.1, 0.95),
        "math": (0.1, 0.95),
    },
    "januscoder": {
        "knowledge": (0.7, 0.8),
        "agentic": (0.2, 0.95),
        "math": (0.5, 0.95),
    },
    "north-mini-code": {
        "coding": (1.0, 0.95),
        "knowledge": (1.0, 0.95),
        "agentic": (1.0, 0.95),
        "math": (1.0, 0.95),
    },
    "nerdsking": {
        "coding": (0.1, 0.95),
        "knowledge": (0.7, 0.95),
        "agentic": (0.2, 0.95),
        "math": (0.25, 0.95),
    },
    "glm-4-7": {
        "coding": (0.7, 1.0),
        "knowledge": (1.0, 0.95),
        "agentic": (0.7, 0.95),
        "math": (1.0, 0.95),
    },
    "glm-4-6v": {
        "coding": (0.8, 0.6),
        "knowledge": (0.8, 0.6),
        "agentic": (0.8, 0.6),
        "math": (0.8, 0.6),
    },
    "ernie": {
        "knowledge": (0.8, 1.0),
        "agentic": (0.3, 0.95),
        "math": (0.25, 0.95),
    },
    "falcon3": {
        "coding": (0.2, 0.95),
        "knowledge": (0.65, 0.9),
        "agentic": (0.25, 0.95),
        "math": (0.2, 0.95),
    },
    "mellum2": {
        "coding": (0.6, 0.95),
        "knowledge": (0.6, 0.95),
        "math": (0.6, 0.95),
    },
    "kimi-linear": {
        "coding": (0.6, 0.95),
        "knowledge": (0.6, 0.95),
        "math": (0.6, 0.95),
    },
    "nemotron-3-nano": {
        "coding": (1.0, 1.0),
        "knowledge": (1.0, 1.0),
        "agentic": (0.6, 0.95),
        "math": (1.0, 1.0),
    },
    "lfm2-24b": {
        "knowledge": (0.1, 0.95),
        "agentic": (0.1, 0.95),
        "math": (0.1, 0.95),
    },
    "internlm2-5": {
        "coding": (0.6, 0.8),
        "knowledge": (0.6, 0.8),
        "agentic": (0.6, 0.8),
        "math": (0.6, 0.8),
    },
    "internlm2-math": {
        "knowledge": (0.7, 0.95),
        "math": (0.2, 0.95),
    },
}


# ── LM Studio JSON-Configs: GUI-Quelle fuer Generations-Parameter ──
# Die LMS-GUI speichert ihre Einstellungen pro Modell als JSON-Config unter
# ~/.lmstudio/.internal/user-concrete-model-default-config/. Seit 2026-08-06
# gilt fuer Benchmarks das Sampling-Design (MODEL_CATEGORY_SAMPLING +
# Kategorie-Defaults); aus den JSON-Configs werden nur NICHT-Temperatur-Felder
# uebernommen (top_k, min_p, enable_thinking, reasoning_effort). Die JSON-
# temperature/top_p gelten nur noch fuer die GUI-Nutzung (ein Einzelwert pro
# Modell kann die Kategorie-Differenzierung nicht ausdruecken).
# Ausgelesen werden operation.fields:
#   llm.prediction.temperature / topPSampling / topKSampling / minPSampling
#   llm.prediction.reasoning.enableThinking / budgetTokens / parsing
#   ext.virtualModel.customField.openai.gptOss20b.reasoningEffort
LMS_CONFIG_ROOT = Path.home() / ".lmstudio" / ".internal" / "user-concrete-model-default-config"

_LMS_INDEX_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_LMS_JSON_CACHE: dict[str, tuple[float, dict[str, Any] | None]] = {}
_LMS_TTL_S = 5.0  # Re-scan File-System hoechstens alle 5 Sekunden

# operation.field key -> ModelConfig-Key
_LMS_OP_KEY_MAP = {
    "llm.prediction.temperature": "temperature",
    "llm.prediction.topPSampling": "top_p",
    "llm.prediction.topKSampling": "top_k",
    "llm.prediction.minPSampling": "min_p",
    "ext.virtualModel.customField.openai.gptOss20b.reasoningEffort": "reasoning_effort",
}


def _normalize_lms_model_name(name: str) -> str:
    """Normalize a model/config name for matching (mirror of assemble_blueprint).

    Konsolidiert in model_identity.py (Fix 2026-08-09).
    """
    return cast("str", normalize_lms_model_name(name))


def _lms_index() -> list[dict[str, Any]]:
    """Scan the LMS config root (TTL-cached) for config files."""
    key = str(LMS_CONFIG_ROOT)
    now = time.time()
    cached = _LMS_INDEX_CACHE.get(key)
    if cached is not None and now - cached[0] < _LMS_TTL_S:
        return cached[1]
    entries: list[dict[str, Any]] = []
    if LMS_CONFIG_ROOT.exists():
        for publisher_dir in sorted(LMS_CONFIG_ROOT.iterdir()):
            if not publisher_dir.is_dir():
                continue
            publisher = publisher_dir.name
            for item in sorted(publisher_dir.iterdir()):
                if item.is_file() and item.suffix.lower() == ".json":
                    json_path = item
                    model_dir_name = item.stem
                elif item.is_dir():
                    json_files = sorted(item.glob("*.json"))
                    if not json_files:
                        continue
                    json_path = json_files[0]
                    model_dir_name = item.name
                else:
                    continue
                entries.append(
                    {
                        "publisher": publisher,
                        "dir_name": model_dir_name,
                        "file_stem": json_path.stem,
                        "json_path": json_path,
                    }
                )
    _LMS_INDEX_CACHE[key] = (now, entries)
    return entries


def _load_lms_json(json_path: Path) -> dict[str, Any] | None:
    """Read one LMS config JSON (TTL-cached, tolerant encoding)."""
    key = str(json_path)
    now = time.time()
    cached = _LMS_JSON_CACHE.get(key)
    if cached is not None and now - cached[0] < _LMS_TTL_S:
        return cached[1]
    data: dict[str, Any] | None = None
    for enc in ("utf-8", "utf-8-sig"):
        try:
            with open(json_path, encoding=enc) as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data = loaded
            break
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
    _LMS_JSON_CACHE[key] = (now, data)
    return data


def _lms_field_value(fields: list[dict[str, Any]], key: str) -> Any:
    for f in fields or []:
        if f.get("key") == key:
            return f.get("value")
    return None


def _unwrap_lms_value(value: Any) -> Any:
    """Unwrap LMS {checked, value}-Objekte; 0 bzw. unchecked => None (disabled).

    Plaine Skalare (z.B. temperature=0.0) bleiben unveraendert.
    """
    if isinstance(value, dict) and "checked" in value:
        if value.get("checked") is not True:
            return None
        inner = value.get("value")
        return None if inner == 0 else inner
    return value


def _normalized_lms_key(model_identifier: str) -> str:
    """Normalisierter Matching-Key eines Modellnamens (Registry-Key-Form).

    Konsolidiert in model_identity.py (Fix 2026-08-09).
    """
    return cast("str", normalized_lms_key(model_identifier))


def _model_sampling_row(model_identifier: str) -> dict[str, tuple[float, float]] | None:
    """Passende Zeile der Benchmark-Sampling-Tabelle (MODEL_CATEGORY_SAMPLING).

    Prefix-/Suffix-Match gegen den normalisierten Modellnamen (wie
    _lms_generation_config), erste Treffer-Zeile gewinnt.
    """
    if not model_identifier:
        return None
    key = _normalized_lms_key(model_identifier)
    if not key:
        return None
    for table_key, row in MODEL_CATEGORY_SAMPLING.items():
        if table_key == key or key.startswith(table_key + "-") or key.endswith("-" + table_key):
            return row
    return None


def _registry_sampling_block(model_identifier: str) -> dict[str, Any] | None:
    """Registry-`sampling:`-Block (Variante A) fuer das Modell, falls vorhanden.

    Deterministisches Registry-Matching (match_registry_key), Rueckgabe des
    verschachtelten sampling-Dicts oder None. SSOT seit 2026-08-11/13
    (Migration, siehe doc-git/Planung/registry_sampling.md).
    """
    if not model_identifier:
        return None
    reg = _load_quant_registry()
    if not reg:
        return None
    key = match_registry_key(model_identifier, list(reg.keys()))
    if key is None:
        return None
    entry = reg.get(key) or {}
    block = entry.get("sampling")
    if not isinstance(block, dict):
        return None
    return block


def _lms_generation_config(model_identifier: str) -> dict[str, Any] | None:
    """Generations-Parameter aus der LMS-JSON-Config des Modells.

    Matching wie registry_tool (3 Phasen, publisher-bewusst). Rueckgabe
    eines flachen dicts (temperature/top_p/top_k/min_p/enable_thinking/
    reasoning_effort) oder None, wenn keine Config zum Modell passt.
    """
    if not model_identifier:
        return None
    key = _normalized_lms_key(model_identifier)
    if not key:
        return None
    inp_pub = model_identifier.split("/")[0].lower() if "/" in model_identifier else None

    def _matches(candidate: str) -> bool:
        if candidate == key:
            return True
        if candidate.startswith(key + "-"):
            return True
        if candidate.endswith("-" + key):
            return True
        if key.endswith("-" + candidate):
            return True
        return False

    pub_matches: list[dict[str, Any]] = []
    fallback_matches: list[dict[str, Any]] = []
    for entry in _lms_index():
        norm_dir = _normalize_lms_model_name(entry["dir_name"])
        norm_file = _normalize_lms_model_name(entry["file_stem"])
        if _matches(norm_dir) or _matches(norm_file):
            if inp_pub is not None and entry["publisher"].lower() == inp_pub:
                pub_matches.append(entry)
            else:
                # Kein Publisher-Key oder Publisher weicht ab (z. B. Repack
                # unter anderem Publisher): als Fallback trotzdem pruefen.
                fallback_matches.append(entry)
    # Mehrere Kandidaten (Quant-Varianten): erste Config mit Parametern gewinnt
    for entry in pub_matches + fallback_matches:
        out = _lms_params_from_entry(entry)
        if out:
            return out
    return None


def _lms_params_from_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    """Extract generation params from one matched LMS config file."""
    data = _load_lms_json(entry["json_path"])
    if not isinstance(data, dict):
        return None
    fields = (data.get("operation") or {}).get("fields") or []
    out: dict[str, Any] = {}
    for f in fields:
        if not isinstance(f, dict):
            continue
        target = _LMS_OP_KEY_MAP.get(f.get("key"))
        if target is not None:
            v = _unwrap_lms_value(f.get("value"))
            if v is not None:
                out[target] = v

    # Thinking-Toggle: enableThinking > budgetTokens (value>0) > parsing.enabled
    thinking = _lms_field_value(fields, "llm.prediction.reasoning.enableThinking")
    budget = _lms_field_value(fields, "llm.prediction.reasoning.budgetTokens")
    parsing = _lms_field_value(fields, "llm.prediction.reasoning.parsing")
    if isinstance(thinking, bool):
        out["enable_thinking"] = thinking
    elif isinstance(budget, dict):
        if budget.get("checked") is False:
            out["enable_thinking"] = False
        elif budget.get("checked") is True and isinstance(budget.get("value"), (int, float)) and budget["value"] > 0:
            out["enable_thinking"] = True
        elif isinstance(parsing, dict) and isinstance(parsing.get("enabled"), bool):
            out["enable_thinking"] = parsing["enabled"]
    elif isinstance(parsing, dict) and isinstance(parsing.get("enabled"), bool):
        out["enable_thinking"] = parsing["enabled"]

    return out if out else None



def _word_boundary_match(pattern: str, text: str) -> bool:
    """Substring match with word-boundary check to avoid false overlaps.

    Returns True if `pattern` is bounded by non-alphanumeric chars
    or string boundaries (start/end, '-', '_', '/', '.', '@').
    A digit counts as a boundary when adjacent to the pattern.
    """
    if pattern not in text:
        return False
    idx = text.find(pattern)
    while idx != -1:
        before = text[idx - 1] if idx > 0 else ""
        after = text[idx + len(pattern)] if idx + len(pattern) < len(text) else ""
        before_ok = not before or not before.isalnum() or before.isdigit()
        after_ok = not after or not after.isalnum() or after.isdigit()
        if before_ok and after_ok:
            return True
        idx = text.find(pattern, idx + 1)
    return False


def should_use_unified_kv_cache(model_name: str, model_size_gb: float) -> bool:
    """Determine UKV for a model based on size threshold and special cases.

    Rules:
      1. Models in UKV_FORCE_TRUE_MODELS -> always True (keine KV-Quant vertragbar)
      2. Models >= USE_UNIFIED_KV_CACHE_THRESHOLD_GB (12 GB) -> True
      3. Smaller models -> False
    """
    name_lower = model_name.lower()
    for pattern in UKV_FORCE_TRUE_MODELS:
        if pattern in name_lower:
            return True
    return model_size_gb >= USE_UNIFIED_KV_CACHE_THRESHOLD_GB


def get_model_config(model_identifier: str, category: str = "coding", is_thinking_enabled: bool = False) -> ModelConfig:
    """Generations-Parameter fuer Benchmarks (Sampling-Design 2026-08-06).

    Priority:
      1. Registry `sampling:`-Block (Variante A, SSOT) - temperature/top_p pro
         Kategorie; fehlende Kategorien fallen auf Punkt 2 zurueck.
      2. MODEL_CATEGORY_SAMPLING[row][category] - temperature/top_p als
         Ausnahme-Tabelle (Modell x Kategorie, Research 06.08.2026); gilt fuer
         Instruct- UND Thinking-Laeufe (dokumentierte Thinking-Ausnahmen wie
         GPT-OSS 1.0/1.0, Gemma-4 1.0/0.95, Nemotron-3-Reasoning 1.0/1.0)
      3. BENCHMARK_THINKING_DEFAULTS (0.6/0.95) fuer Reasoning-Modelle im
         --thinking-Lauf, sonst BENCHMARK_CATEGORY_DEFAULTS[category]
      4. LM Studio JSON-Config: NUR Nicht-Temperatur-Felder (top_k, min_p,
         enable_thinking, reasoning_effort) - temperature/top_p der GUI werden
         IGNORIERT (ein Einzelwert pro Modell kann die Kategorie-Differenzierung
         nicht ausdruecken; JSON-Werte gelten seit 2026-08-06 nur noch fuer die
         GUI-Nutzung, nicht fuer Benchmarks)
      5. --thinking CLI-Flag: force enable_thinking fuer Reasoning-Modelle
    Das Ergebnis enthaelt `_source` ("registry-sampling" | "benchmark-table" |
    "thinking-default" | "category-default") zur Anzeige.
    """
    cat = category if category in BENCHMARK_CATEGORY_DEFAULTS else "coding"
    key_lower = model_identifier.lower() if model_identifier else ""
    # Thinking-Lauf + Reasoning-Modell: pauschale Thinking-Defaults (0.6/0.95)
    # statt der Kategorie-Defaults (Research 06.08.2026). Die Ausnahme-Tabelle
    # und der Registry-Block schlagen auch hier (dokumentierte Ausnahmen:
    # GPT-OSS 1.0/1.0, Gemma-4 1.0/0.95, Nemotron-3-Reasoning 1.0/1.0, ...).
    is_thinking_model = is_thinking_enabled and any(_word_boundary_match(p, key_lower) for p in REASONING_PATTERNS)
    if is_thinking_model:
        config: dict[str, Any] = dict(BENCHMARK_THINKING_DEFAULTS)
        source = "thinking-default"
        cell = _sampling_cell(model_identifier, cat)
        if cell:
            config["temperature"], config["top_p"], source = cell
    else:
        config = dict(BENCHMARK_CATEGORY_DEFAULTS[cat])
        cell = _sampling_cell(model_identifier, cat)
        if cell:
            config["temperature"], config["top_p"], source = cell
        else:
            source = "category-default"
    lms = _lms_generation_config(model_identifier)
    if lms:
        # Nur Nicht-Temperatur-Felder uebernehmen (Sampling-Design 2026-08-06).
        # enable_thinking wird NICHT blind uebernommen: Kategorie-basierte
        # Steuerung via Blueprint-Feld schlaegt die JSON-Config (Fix 15.08. -
        # Gemma-Configs mit budgetTokens=2048 haetten sonst Thinking in allen
        # Kategorien erzwungen, auch Coding).
        for k in ("top_k", "min_p", "enable_thinking", "reasoning_effort"):
            if k in lms:
                config[k] = lms[k]
    # Blueprint-SSOT: stop_strings + reasoning_parsing aus blueprint_definitions.yaml
    # (Refactor 14.08. - Registry-`template:`-Feld ist veraltet).
    bp_features = _blueprint_features(model_identifier)
    if bp_features.get("stop_strings"):
        config["stop"] = bp_features["stop_strings"]
    if bp_features.get("reasoning_parsing"):
        config["reasoning_parsing"] = bp_features["reasoning_parsing"]
    # Kategorie-basierte Thinking-Steuerung aus dem Blueprint (SSOT, 15.08.):
    # ueberschreibt den LMS-Config-Wert (budgetTokens). Reihenfolge: zuerst die
    # Kategorie-Steuerung anwenden, damit das --thinking-Flag danach als Force
    # gewinnen kann (siehe unten).
    bp_thinking = bp_features.get("enable_thinking_by_category")
    if isinstance(bp_thinking, dict) and cat in bp_thinking:
        config["enable_thinking"] = bp_thinking[cat]
    # Thinking-Flag: force enable_thinking=True fuer Reasoning-Modelle (gewinnt)
    if is_thinking_model:
        config["enable_thinking"] = True
    config["_source"] = source
    return config


def _blueprint_features(model_identifier: str) -> dict[str, Any]:
    """Modellspezifika (stop_strings/reasoning_parsing) aus blueprint_definitions.yaml.

    Single Source of Truth seit 14.08. (Registry-`template:`-Feld veraltet):
    Registry liefert nur den Blueprint-Namen, die Detailwerte kommen aus der
    Blueprint-Definition. Liefert {} wenn Modell nicht aufloesbar.
    """
    if not model_identifier:
        return {}
    try:
        from assemble_blueprint import blueprint_features
    except ImportError:
        return {}
    reg = _load_quant_registry()
    if not reg:
        return {}
    key = match_registry_key(model_identifier, list(reg.keys()))
    if key is None:
        return {}
    bp_name = (reg.get(key) or {}).get("blueprint") or "default_chat"
    return cast("dict[str, Any]", blueprint_features(bp_name, model_identifier))


def _sampling_cell(model_identifier: str, cat: str) -> tuple[float, float, str] | None:
    """temperature/top_p + Quelle fuer Modell x Kategorie.

    Precedence: Registry-`sampling:`-Block (SSOT) -> MODEL_CATEGORY_SAMPLING
    -> None (dann greifen Kategorie-/Thinking-Defaults im Aufrufer).
    """
    reg = _registry_sampling_block(model_identifier)
    if reg:
        entry = reg.get(cat)
        if isinstance(entry, dict) and "temperature" in entry and "top_p" in entry:
            return float(entry["temperature"]), float(entry["top_p"]), "registry-sampling"
    cell = (_model_sampling_row(model_identifier) or {}).get(cat)
    if cell:
        return cell[0], cell[1], "benchmark-table"
    return None


# ── Backward-Compat: THINKING_CONFIG bleibt als Alias ──
# Wird noch von custom_benchmark.py importiert (MODEL_CONFIG = THINKING_CONFIG).
# Neu: Nutze get_model_config() statt direktem Dict-Zugriff.
THINKING_CONFIG = BENCHMARK_CATEGORY_DEFAULTS


def is_support_file(
    path: str | os.PathLike[str],
    architecture: str = "",
) -> bool:
    """True for auxiliary GGUF files that are NOT standalone benchmark models.

    - ``mmproj*``: vision projector files
    - ``mtp-*`` or ``*/MTP/*``: MTP draft models (speculative-decoding add-ons,
      e.g. unsloth's ``mtp-gemma-4-12B-it-Q8_0.gguf``). Legitimate standalone
      MTP models (``qwen3.6-27b-mtp``, ``...-MTP-...`` in the name) are NOT
      affected - only the ``mtp-`` filename prefix or an ``MTP`` path segment.
    - ``*imatrix*``: Importance Matrix quantization files (< 200 MB), companion
      files to the main model, not standalone.
    - architecture ending in ``-assistant`` (e.g. ``gemma4-assistant``): MTP
      drafter architecture reported by LM Studio / GGUF header.

    Zentralisiert hier, damit registry_tool.py (add/resolve), model_manager.py
    (get_available_models) und run_benchmarks.py dieselbe Filter-Logik nutzen
    (Code-Review 2026-08-03 §F1).
    """
    name = os.path.basename(str(path)).lower()
    if "mmproj" in name:
        return True
    if name.startswith("mtp-"):
        return True
    if "imatrix" in name:
        return True
    parts = str(path).replace("\\", "/").split("/")
    if any(seg.lower() == "mtp" for seg in parts):
        return True
    arch = architecture.lower().strip()
    return arch.endswith("-assistant")


# Code-Review 2026-07-18 §5.1: Centralised VRAM constants. Previously
# scattered across registry_tool.py (`_USABLE_VRAM_GB = 15.3`) and
# run_benchmarks.py (in-line magic numbers). All VRAM-related
# thresholds now live here as the single source of truth.
USABLE_VRAM_GB = 15.3  # RTX 5060 Ti 16 GB minus driver overhead
USE_UNIFIED_KV_CACHE_THRESHOLD_GB = 12.0  # When model_size_gb >= this, UKV=True (empirically determined)

# Modelle, die KEINE KV-Quantisierung vertragen -> IMMER UKV=True
# (unabhaengig von der Modellgroesse, da KV-Quant zu Qualitaetsverlusten fuehrt)
# Gemma-4: KV-Quant fuehrt zu massiven Qualitaetsverlusten
# Kimi Linear: vertragen keine KV-Quant
# Gpt-Oss: vertragen keine KV-Quant (nur fp16 KV-Cache)
UKV_FORCE_TRUE_MODELS = {
    "gemma-4",      # Gemma-4 Familie (26B, 19B, 12B)
    "kimi-linear",  # Kimi Linear REAP
    "gpt-oss",      # GPT-OSS-20B
}
LEGACY_MODEL_GB_THRESHOLD_GB = 9.0  # Fallback for entries without n_layers/hd
KV_QUANT_REFERENCE_BYTES = 1.5  # Reference (q8_0 + iq4_nl) for ctx scaling
MIN_CONTEXT_LENGTH = 32768  # Minimum ctx for np/UKV priority algorithm (32k tokens)

LB_MEANS_BLACKLIST = {"Granite 4.0 H Tiny"}
# Code-Review 2026-07-18 §4.2: Imported by consolidate_results.py for
# potential Granite-specific Lower-Bound-via-Means handling, but currently
# unused (no `if model in LB_MEANS_BLACKLIST` checks downstream). Kept as
# documentation of the special-case intent.

CAT_WEIGHTS = {
    "coding": {
        "HumanEval+_plus": 0.25,
        "MBPP+_plus": 0.25,
        "DS1000": 0.25,
        "CoderEval": 0.25,
    },
    "knowledge": {
        "ARC-Challenge": 1 / 3,
        "HellaSwag": 1 / 3,
        "TruthfulQA": 1 / 3,
    },
    "math": {
        "MATH-500": 1.0,
    },
    "agentic": {
        "Agentic": 0.5,
        "IFEval": 0.5,
    },
}

OVERALL_WEIGHTS = {"coding": 0.35, "math": 0.25, "agentic": 0.25, "knowledge": 0.15}

PIPELINE_TIMEOUTS = {
    "custom_subprocess": 14400,
    "evalplus_base": 600,
    "lmeval_base": 600,
    "mmlupro_per_subset": 600,
    "agentic_subprocess": 3600,
    "agentic_scenario": 600,
}

TOOL_EVAL_SCENARIO_IDS = [f"TC-{i:02d}" for i in range(1, 70)]

# Safety & Boundaries (Category K) Szenarien aus tool_eval_bench v2.0.7.
# Diese 13 TCs testen Injection-/Sicherheits- und Grenzfall-Verhalten
# (Prompt-Injection, Authority Escalation, Sleeper Injection, Hallucination,
# Scope Limitation ...). Bei --agentic-mode=safety wird NUR aus dieser Liste
# gestartet. Quelle: evals/scenarios.py + evals/scenarios_adversarial.py.
AGENTIC_SAFETY_SCENARIO_IDS = [
    "TC-31",
    "TC-32",
    "TC-33",
    "TC-34",
    "TC-35",
    "TC-36",
    "TC-41",
    "TC-42",
    "TC-43",
    "TC-57",
    "TC-58",
    "TC-59",
    "TC-60",
]

PIPELINE_DISCOVERY = {
    "custom": {"module": None, "glob": "custom_benchmark_v*.py", "desc": "Subprozess (DS1000, CoderEval)"},
    "evalplus": {"module": "evalplus", "glob": None, "desc": "Python-Modul (HumanEval+, MBPP+)"},
    "lmeval": {"module": "lm_eval", "glob": None, "desc": "Python-Modul (ARC, HellaSwag, ...)"},
    "agentic": {"module": "tool_eval_bench", "glob": None, "desc": "Python-Modul (Tool-Evaluation)"},
}
