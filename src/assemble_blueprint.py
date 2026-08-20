#!/usr/bin/env python3
"""
assemble_blueprint.py - Prompt-Standardisierung per Blueprint-System

Generiert System-Prompts und Jinja-Templates aus Blueprint-Definitionen
und schreibt sie in die LM-Studio JSON-Configs.

Phases:
  Phase 1: Klassifikation in model_registry.yaml (reasoning, capabilities, blueprint)
  Phase 2: Textbaustein-Bibliothek definieren (blueprint_definitions.yaml)
  Phase 3: Assembly - System-Prompts aus Blueprints generieren und in
           JSON-Configs schreiben (systemPrompt, promptTemplate)
  Phase 4: Validierung - Syntax-Check, Regression-Prüfung

Usage:
  python assemble_blueprint.py classify   -> Phase 1: Klassifikation
  python assemble_blueprint.py assemble   -> Phase 3: Assembly + Write JSON
  python assemble_blueprint.py validate   -> Phase 4: Syntax-Check
  python assemble_blueprint.py all         -> Alle Phasen ausführen
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from benchmark_config import BLACKLIST, GPTOSS_REASONING_EFFORT
from model_identity import (
    _arch_reasoning_map,
    normalize_for_config,
    normalize_model_name,
)

# === Pfade ===
_SRC_DIR = Path(__file__).parent
PROJECT_ROOT = _SRC_DIR.parent
sys.path.insert(0, str(_SRC_DIR))

REGISTRY_PATH = PROJECT_ROOT / "doc-git" / "model_registry.yaml"
BLUEPRINT_PATH = PROJECT_ROOT / "doc-git" / "blueprint_definitions.yaml"
CONFIG_ROOT = Path.home() / ".lmstudio" / ".internal" / "user-concrete-model-default-config"
TEMPLATE_DIR = PROJECT_ROOT / "doc-git" / "Jinja-Chat-Templates"
INVENTORY_PATH = PROJECT_ROOT / "prompt_inventory.csv"

# === Reasoning Keywords ===
REASONING_KEYWORDS = [
    "r1", "thinker", "thinking", "qwq", "cascade",
    "cot", "reasoning", "reasoning-plus", "reasoningplus", "rnj",
    "math", "magistral", "phi-4-reasoning",
]
NON_REASONING_MODELS = [
    "whisper", "flux", "ocr", "translategemma"
]

# Architecture → default reasoning type (priority after GGUF/existing)
# WICHTIG: Reihenfolge! qwen35moe/qwen35 MUSS vor qwen3moe/qwen3 geprüft werden
# (Substring-Overlap: "qwen3" ⊂ "qwen35").
# Qwen3.6 (qwen35, qwen35moe): Dual-Mode, Default = Thinking.
# Qwen3 (qwen3, qwen3moe): Default = Instruct. Nur explizites "thinking" im Namen → thinking.
# Exception: "qwen3-30b-a3b-thinking-2507" → thinking
# Zentrale Quelle ist seit 2026-08-09 model_identity.MODEL_FAMILIES.
_ARCH_REASONING_MAP = _arch_reasoning_map()


# Normalisierung konsolidiert in model_identity.py (Fix 2026-08-09):
# normalize_model_name / normalize_for_config werden von dort importiert.
# _VARIANT_SUFFIXES bleibt als Alias fuer bestehende Nutzungsstellen.
_VARIANT_SUFFIXES = (
    "-ud",          # Unsloth distilled
    "-qat",         # Quantization-aware training variant: wird "qat" geschrieben, nicht "quat"!
    "-imatrix",     # Importance-matrix quant
)


def find_config_for_registry_key(
    registry_key: str,
    configs: list[dict],
) -> dict | None:
    """Find the best matching LM Studio config for a registry key.

    Multi-level matching:
    1. Exact normalized match (via normalize_model_name)
    2. Broader match (via normalize_for_config, strips @quant + -ud/-quat)
    3. Registry key is prefix of config name (e.g. 'gemma-4-12b-it-qat' → 'gemma-4-12b-it-qat-q4-0')
    4. Config name is prefix of registry key (e.g. 'gemma-4-26b-a4b-it' → 'gemma-4-26b-a4b-it-quat')
    """
    all_cfgs = _find_all_configs_for_registry_key(registry_key, configs)
    return all_cfgs[0] if all_cfgs else None


def find_all_configs_for_registry_key(
    registry_key: str,
    configs: list[dict],
) -> list[dict]:
    """Like find_config_for_registry_key but returns ALL matching configs."""
    return _find_all_configs_for_registry_key(registry_key, configs)


def _find_all_configs_for_registry_key(
    registry_key: str,
    configs: list[dict],
) -> list[dict]:
    """Internal: find all matching configs for a registry key (used by both single and multi)."""
    rn = normalize_model_name(registry_key)
    rn_broad = normalize_for_config(registry_key)

    cfg_exact: dict[str, list[dict]] = {}
    cfg_broad: dict[str, list[dict]] = {}
    cfg_raw: list[dict] = []
    for cfg in configs:
        raw = f"{cfg['publisher']}/{cfg['dir_name']}"
        cn = normalize_model_name(raw)
        cb = normalize_for_config(raw)
        cfg_exact.setdefault(cn, []).append(cfg)
        cfg_broad.setdefault(cb, []).append(cfg)
        cfg_raw.append((cn, raw, cfg))

    # Level 1: exact match
    if rn in cfg_exact:
        return cfg_exact[rn]

    # Level 2: broad match (stripped quant/variant)
    if rn_broad in cfg_broad:
        return cfg_broad[rn_broad]

    # Level 3: registry key is prefix of config name
    matched: list[dict] = []
    for cn, _, cfg in cfg_raw:
        if cn.startswith(rn + "-"):
            matched.append(cfg)
    if matched:
        return matched

    # Level 4: config name is prefix of registry key
    for cn, _, cfg in sorted(cfg_raw, key=lambda x: -len(x[0])):
        if rn.startswith(cn + "-") or rn_broad.startswith(cn + "-"):
            matched.append(cfg)
    return matched


def find_registry_key_for_config(
    config_norm: str,
    registry_sorted: list[tuple[str, str]],
) -> str | None:
    """Find the best matching registry key for a config name.

    Multi-level matching (mirrors the existing logic in cmd_configs + _strip_quant):
    1. Exact match
    2. Config starts with registry key + hyphen
    3. Registry key ends with hyphen + config
    4. Broad match (config vs broad registry key)
    """
    for rn2, rnk in registry_sorted:
        if config_norm == rn2:
            return rnk
    for rn2, rnk in registry_sorted:
        if config_norm.startswith(rn2 + "-"):
            return rnk
    for rn2, rnk in registry_sorted:
        if rn2.endswith("-" + config_norm):
            return rnk
    # Broad match: strip quant from registry keys and retry
    for rn2, rnk in registry_sorted:
        rn2_clean = normalize_for_config(rn2)
        if config_norm == rn2_clean:
            return rnk
    return None


def classify_reasoning(
    model_name: str,
    notes: str = "",
    arch: str = "",
    existing_reasoning: str | None = None,
) -> str:
    """Classify model reasoning type: thinking | instruct | none.

    Priority chain:
      1. existing_reasoning (GGUF header / user override)
      2. arch → _ARCH_REASONING_MAP
      3. NON_REASONING_MODELS keyword blacklist
      4. REASONING_KEYWORDS keyword whitelist
      5. Default: "instruct"
    """
    name_lower = model_name.lower()

    if existing_reasoning is not None:
        return existing_reasoning

    if arch:
        arch_lower = arch.lower().replace(".", "")  # normalize: "Qwen3.5" → "qwen35"
        for arch_key, reasoning_type in _ARCH_REASONING_MAP.items():
            if arch_key in arch_lower:
                # Qwen3 / Qwen3.6 Klassifikation über Modellnamen:
                # - Qwen3 (qwen3, qwen3moe): Default Instruct. Nur explizites "thinking" im Namen → thinking.
                # - Qwen3.6 (qwen35, qwen35moe): Dual-Mode (Thinking per Toggle schaltbar).
                #   Default Thinking (Hub model.yaml: enableThinking defaultValue: true,
                #   Qwen-Model-Card). "thinking" im Namen → thinking.
                # - Special case: "qwen3-30b-a3b-thinking-2507..." → thinking
                if arch_key.startswith("qwen"):
                    if "thinking" in name_lower:
                        return "thinking"
                    # "instruct"/"coder" im Namen → Instruct (gilt für Qwen3 UND Qwen3.6)
                    if "instruct" in name_lower or "coder" in name_lower:
                        return "instruct"
                    # Default aus der Map: Qwen3.6 (qwen35/qwen35moe) → thinking,
                    # Qwen3 (qwen3/qwen3moe) → instruct.
                    # Exception: "qwen3-30b-a3b-thinking-2507" → thinking (Name enthält "thinking")
                    return reasoning_type
                return reasoning_type

    for kw in NON_REASONING_MODELS:
        if kw in name_lower:
            return "none"

    for kw in REASONING_KEYWORDS:
        if kw in name_lower:
            return "thinking"

    return "instruct"


def classify_capabilities(model_name: str, arch: str = "", notes: str = "") -> str:
    """Determine model capabilities (comma-separated string)."""
    name_lower = model_name.lower()
    arch_lower = arch.lower() if arch else ""
    notes_lower = notes.lower() if notes else ""
    caps = []

    # Vision
    vision_indicators = ["vl", "vision", "ocr"]
    if any(kw in name_lower for kw in vision_indicators) or \
       any(kw in arch_lower for kw in vision_indicators) or \
       any(kw in notes_lower for kw in vision_indicators):
        caps.append("vision")

    # Audio
    if "whisper" in name_lower:
        caps.append("audio")

    # Coding
    coding_indicators = ["coder", "code", "python", "wizardcoder"]
    if any(kw in name_lower for kw in coding_indicators) or \
       "(coder)" in arch_lower:
        caps.append("coding")

    # Gemma-4 models: all support coding + vision (text + image per HF card)
    # Audio only on 12B, E4B, E2B
    if "gemma-4" in name_lower:
        if "coding" not in caps:
            caps.append("coding")
        if "vision" not in caps:
            caps.append("vision")
        if ("12b" in name_lower or "e4b" in name_lower or "e2b" in name_lower) and "audio" not in caps:
            caps.append("audio")

    # Granite models: all support code generation per HF cards
    if "granite" in name_lower and "coding" not in caps:
        caps.append("coding")

    # Model families with vision + coding support (verified via HF cards)
    vision_coding_families = ["ministral", "apriel", "kimi", "devstral", "qwen3", "magistral"]
    for fam in vision_coding_families:
        if fam in name_lower:
            if "coding" not in caps:
                caps.append("coding")
            if "vision" not in caps:
                caps.append("vision")
            break

    # Additional model families with coding support only (verified via HF cards)
    coding_families = ["llama-3", "phi-4", "falcon3", "glm-4.7", "nemotron",
                       "mistral-nemo", "mistral-small", "solar-pro",
                       "qwen2.5", "ernie", "mellum",
                       "acemath", "mathstral", "numina", "gpt-oss"]
    for fam in coding_families:
        if fam in name_lower and "coding" not in caps:
            caps.append("coding")
            break

    # Agentic
    if "agentic" in notes_lower:
        caps.append("agentic")

    # Text is default for all non-special models
    if not any(kw in name_lower for kw in ["whisper", "flux"]):
        caps.append("text")

    if not caps:
        return "text"
    return ", ".join(caps)


def select_blueprint(reasoning: str, capabilities: str, arch: str = "", model_name: str = "") -> str:
    """Select the appropriate blueprint for a model."""
    name_lower = model_name.lower()
    arch_lower = arch.lower() if arch else ""

    if reasoning == "none":
        return "none"

    # Gemma-4 models
    if "gemma-4" in name_lower or "gemma-4" in arch_lower or "gemma4" in name_lower:
        if reasoning == "thinking":
            return "gemma_reasoning"
        return "gemma_assistant"

    # GPT-OSS (Harmony-Format, Configurable Reasoning Effort)
    if "gpt-oss" in name_lower:
        return "gptoss_reasoning"

    # Magistral (model-spezifischer System-Prompt mit [THINK]/[/THINK])
    if "magistral" in name_lower:
        return "magistral_reasoning"

    # Phi-4-Reasoning-Plus (ChatML, <think>/</think>-Tags, temp=0.8, top_k=50)
    if "phi-4-reasoning" in name_lower or "phi4-reasoning" in name_lower:
        return "phi4_reasoning"

    # Ministral Reasoning ([THINK]-Tags wie Magistral)
    if "ministral" in name_lower and "reasoning" in name_lower:
        return "ministral_reasoning"

    # Nemotron Cascade ([THINK]-Token-basiertes Reasoning)
    if "nemotron" in name_lower and "thinking" in name_lower:
        return "nemotron_reasoning"

    # Apriel Thinker ([BEGIN FINAL RESPONSE]-Format)
    if "apriel" in name_lower and "thinker" in name_lower:
        return "apriel_reasoning"

    # Granite models use their own blueprint so the Granite-specific Jinja
    # map cannot affect unrelated coding models.
    if "granite" in name_lower:
        if "coding" in capabilities.split(", "):
            return "granite_coding_agent"
        return "default_chat"

    # Reasoning models
    if reasoning == "thinking":
        if "coding" in capabilities.split(", "):
            return "reasoning_coding"
        return "reasoning_assistant"

    # Coding models
    if "coding" in capabilities.split(", "):
        return "coding_agent"

    # Default
    return "default_chat"


def has_custom_template(entry: dict) -> bool:
    """Check if model has a custom jinja template (legacy registry-field path)."""
    return "template" in entry and entry["template"]


def resolve_template_name(bp_def: dict | None, model_name: str = "") -> str | None:
    """Resolve jinja template filename from a blueprint definition (SSOT).

    Priority:
      1. ``template_map``: model-name substring match (e.g. gemma sizes 12b/19b/26b)
      2. ``template``: blueprint-wide template file
      3. legacy registry ``template:`` field (handled by the caller)

    ``model_name`` is matched case-insensitively on substrings; pattern dots
    and hyphens are treated as interchangeable (registry keys normalize dots
    to hyphens, e.g. ``granite-4.1-30b`` -> ``granite-4-1-30b``).
    """
    if not isinstance(bp_def, dict):
        return None
    tpl_map = bp_def.get("template_map")
    if isinstance(tpl_map, dict):
        name_lower = model_name.lower() if model_name else ""
        norm_lower = re.sub(r"[.\s]", "-", name_lower)
        for pattern, fname in tpl_map.items():
            pat = str(pattern).lower()
            pat_norm = re.sub(r"[.\s]", "-", pat)
            if (pat and pat in name_lower) or (pat_norm and pat_norm in norm_lower):
                return str(fname)
    tpl = bp_def.get("template")
    return str(tpl) if tpl else None


_BLUEPRINT_DEFS_CACHE: dict[str, Any] | None = None


def load_blueprint_defs() -> dict[str, Any]:
    """Load blueprint_definitions.yaml (blueprints + modules), cached.

    Single Source of Truth fuer Modellspezifika (template, stop_strings,
    reasoning_parsing). Bestandteil des Refactors 14.08.: Die Registry
    traegt nur noch den Blueprint-Namen, die Detailwerte kommen von hier.
    """
    global _BLUEPRINT_DEFS_CACHE
    if _BLUEPRINT_DEFS_CACHE is not None:
        return _BLUEPRINT_DEFS_CACHE
    with open(BLUEPRINT_PATH, encoding="utf-8") as f:
        data = YAML().load(f) or {}
    _BLUEPRINT_DEFS_CACHE = data
    return _BLUEPRINT_DEFS_CACHE


def blueprint_features(bp_name: str, model_name: str = "") -> dict[str, Any]:
    """Modellspezifika eines Blueprints als dict (SSOT).

    Liefert ``template``/``stop_strings``/``reasoning_parsing`` (falls der
    Blueprint sie definiert) fuer die Benchmark-Config. ``model_name`` wird
    nur fuer die ``template_map``-Aufloesung benoetigt.
    """
    bp = load_blueprint_defs().get("blueprints", {}).get(bp_name) or {}
    features: dict[str, Any] = {}
    tpl = resolve_template_name(bp, model_name)
    if tpl:
        features["template"] = tpl
    stops = bp.get("stop_strings")
    if isinstance(stops, list) and stops:
        features["stop_strings"] = [str(s) for s in stops]
    parsing = bp.get("reasoning_parsing")
    if isinstance(parsing, dict) and "enabled" in parsing:
        features["reasoning_parsing"] = parsing
    thinking_cats = bp.get("enable_thinking_by_category")
    if isinstance(thinking_cats, dict) and thinking_cats:
        features["enable_thinking_by_category"] = {
            str(k): bool(v) for k, v in thinking_cats.items()
        }
    return features


def extract_params(model_name: str) -> str | None:
    """Extract parameter count from model name (e.g. '14B', '32B', '3.8b')."""
    m = re.search(r"(?:^|[-])(\d+\.?\d*)[BMK]", model_name, re.IGNORECASE)
    if m:
        val = m.group(0)  # e.g. "14B", "32B"
        # Clean up leading hyphen
        val = val.lstrip("-")
        return val.upper()
    return None


def format_publishers(pub_val: Any) -> str:
    """Format publisher(s) into a readable string."""
    if isinstance(pub_val, list):
        names = [str(p) for p in pub_val if p]
        return "/".join(names) if names else "unknown"
    return str(pub_val) if pub_val else "unknown"


def format_capabilities(caps: Any) -> str:
    """Format capabilities (comma-separated string or list) into readable string."""
    if not caps:
        return "text generation"
    if isinstance(caps, str):
        caps = [c.strip() for c in caps.split(",")]
    if isinstance(caps, list):
        labels = {
            "text": "text generation",
            "coding": "coding",
            "vision": "visual design",
            "audio": "audio processing",
            "agentic": "agentic tool use",
        }
        human = [labels.get(c, c) for c in caps]
        return ", ".join(human)
    return str(caps)


def render_role(entry: dict, model_name: str, role_template: str | None, static_role: str) -> str:
    """Render a role template with model-specific variables, falling back to static role."""
    if not role_template:
        return static_role

    # Extract reasoning
    reasoning = entry.get("reasoning", "instruct")

    # Build variables
    params = extract_params(model_name)
    params_label = f" with {params} parameters" if params else ""
    publisher = format_publishers(entry.get("publisher", "unknown"))
    capabilities = format_capabilities(entry.get("capabilities", "text"))
    arch = str(entry.get("arch", "Unknown"))
    type_labels = {
        "thinking": " and reasoning features",
        "instruct": ", following instructions",
        "none": "",
    }
    type_label = type_labels.get(reasoning, "")

    vars_dict = {
        "name": model_name,
        "arch": arch,
        "publisher": publisher,
        "params": params or "",
        "params_label": params_label,
        "capabilities": capabilities,
        "type_label": type_label,
    }

    try:
        rendered = role_template.format(**vars_dict)
        # Collapse multiple spaces
        rendered = re.sub(r"  +", " ", rendered).strip()
        return rendered
    except KeyError as e:
        print(f"[WARN] Template key not found: {e} for {model_name}, using static role")
        return static_role


def truncation_from_context(ctx_len: int) -> str:
    """Determine truncation level from context length."""
    if ctx_len is None or ctx_len == 0:
        return "full"
    if ctx_len >= 32000:
        return "full"
    if ctx_len >= 16384:
        return "medium"
    return "minimal"


_LMS_CONFIGS_CACHE: dict[str, tuple[float, list]] = {}
_LMS_CONFIGS_TTL_S = 5.0  # Re-scan file system at most every 5 seconds


def read_lms_configs(config_root: Path) -> list:
    """Read all LM Studio JSON config files, return a list of config dicts.

    Code-Review 2026-07-18 §4.2: results are cached for 5 seconds per
    config_root path. cmd_sync() invokes this 4+ times in quick succession;
    without the cache, every call would re-walk 158+ JSON files.
    """
    import time as _time
    key = str(config_root)
    now = _time.time()
    cached = _LMS_CONFIGS_CACHE.get(key)
    if cached is not None:
        ts, models = cached
        if now - ts < _LMS_CONFIGS_TTL_S:
            return models
    models = []
    if not config_root.exists():
        print(f"[WARN] Config root not found: {config_root}")
        _LMS_CONFIGS_CACHE[key] = (now, models)
        return models

    for publisher_dir in sorted(config_root.iterdir()):
        if not publisher_dir.is_dir():
            continue
        publisher = publisher_dir.name
        for item in sorted(publisher_dir.iterdir()):
            # Handle both: flat JSON files and subdirectories with JSON files
            if item.is_file() and item.suffix.lower() == ".json":
                json_files = [item]
                model_dir_name = item.stem
            elif item.is_dir():
                json_files = list(item.glob("*.json"))
                if not json_files:
                    continue
                model_dir_name = item.name
            else:
                continue

            for json_path in json_files:
                data = None
                for enc in ("utf-8", "utf-8-sig"):
                    try:
                        with open(json_path, encoding=enc) as f:
                            data = json.load(f)
                        break
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue

                if data is None:
                    print(f"[WARN] Cannot decode {json_path}")
                    continue

                try:
                    sys_prompt = None
                    for field in data.get("operation", {}).get("fields", []):
                        if field.get("key") == "llm.prediction.systemPrompt":
                            sys_prompt = field.get("value", "")
                            break

                    ctx_length = None
                    offload = None
                    num_parallel = None
                    use_unified_kv = None
                    for field in data.get("load", {}).get("fields", []):
                        k = field.get("key")
                        if k == "llm.load.contextLength":
                            ctx_length = field.get("value")
                        elif k == "llm.load.llama.acceleration.offloadRatio":
                            offload = field.get("value")
                        elif k == "llm.load.numParallelSessions":
                            num_parallel = field.get("value")
                        elif k == "llm.load.useUnifiedKvCache":
                            v = field.get("value")
                            if isinstance(v, bool):
                                use_unified_kv = v
                            elif isinstance(v, str):
                                use_unified_kv = v.lower() == "true"

                    models.append({
                        "publisher": publisher,
                        "dir_name": model_dir_name,
                        "file_name": json_path.name,
                        "system_prompt": sys_prompt or "",
                        "context_length": ctx_length,
                        "offload": offload,
                        "num_parallel": num_parallel,
                        "use_unified_kv": use_unified_kv,
                        "json_path": json_path,
                    })
                except Exception as e:
                    print(f"[WARN] Error parsing {json_path}: {e}")

    _LMS_CONFIGS_CACHE[key] = (now, models)
    return models


def classify_registry() -> None:
    """Phase 1: Read registry, classify models, write updated YAML."""
    if not REGISTRY_PATH.exists():
        print(f"[ERROR] Registry not found: {REGISTRY_PATH}")
        return

    yaml_ruamel = YAML()
    yaml_ruamel.preserve_quotes = True
    yaml_ruamel.indent(mapping=2, sequence=4, offset=2)

    with open(REGISTRY_PATH, encoding="utf-8") as f:
        registry = yaml_ruamel.load(f)

    if not registry:
        print("[ERROR] Empty registry")
        return

    # Read LM Studio configs for context_length info
    lms_configs = read_lms_configs(CONFIG_ROOT)

    # Read blueprint definitions (SSOT fuer custom template detection)
    with open(BLUEPRINT_PATH, encoding="utf-8") as f:
        bp_defs = yaml_ruamel.load(f)
    blueprints = bp_defs.get("blueprints", {})

    updated_count = 0
    for model_name, entry in registry.items():
        if not isinstance(entry, dict):
            continue

        arch = str(entry.get("arch", ""))
        notes = str(entry.get("notes", ""))

        # Classification (priority: GGUF/override > arch map > keywords > instruct)
        existing_reasoning = entry.get("reasoning")
        reasoning = classify_reasoning(model_name, notes, arch, existing_reasoning)
        capabilities = classify_capabilities(model_name, arch, notes)
        blueprint = select_blueprint(reasoning, capabilities, arch, model_name)

        # Custom-Template-Detection: Blueprint-Definition ist SSOT; das
        # Registry-`template:`-Feld gilt als veraltet und wird ignoriert.
        custom_tpl = resolve_template_name(blueprints.get(blueprint), model_name) is not None

        # Get context length from LM Studio configs
        ctx_len = None
        for lms_info in lms_configs:
            lms_name = lms_info.get("dir_name", "")
            if normalize_model_name(model_name) in normalize_model_name(lms_name) or \
               normalize_model_name(lms_name) in normalize_model_name(model_name):
                ctx_len = lms_info.get("context_length")
                break

        # Truncation basiert auf der echten Modellfähigkeit (GGUF max_context_length),
        # nicht auf der in LM Studio eingestellten Config-ctx (VRAM-bedingt).
        truncation = truncation_from_context(entry.get("max_context_length") or ctx_len)

        # Add new fields (preserving insertion order)
        # Insert before 'notes' if it exists, otherwise at end
        entry["reasoning"] = reasoning
        entry["capabilities"] = capabilities
        entry["blueprint"] = blueprint
        entry["truncation"] = truncation
        if custom_tpl:
            entry["custom_template"] = True

        # Remove context from registry if it exists - truth is in JSON configs
        if "context" in entry:
            del entry["context"]

        updated_count += 1

    # Write updated registry
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        yaml_ruamel.dump(registry, f)

    # Normalize blank lines (no blanks within entries, one between entries)
    from registry_tool import _format_blank_lines
    _format_blank_lines(REGISTRY_PATH)

    print(f"[OK] Updated {updated_count} models in {REGISTRY_PATH}")

    # Write summary
    reasoning_counts = {}
    blueprint_counts = {}
    for entry in registry.values():
        if isinstance(entry, dict):
            r = entry.get("reasoning", "?")
            b = entry.get("blueprint", "?")
            reasoning_counts[r] = reasoning_counts.get(r, 0) + 1
            blueprint_counts[b] = blueprint_counts.get(b, 0) + 1

    print(f"Reasoning: {dict(reasoning_counts)}")
    print(f"Blueprint: {dict(blueprint_counts)}")


def create_blueprint_definitions() -> None:
    """Phase 2: Create blueprint_definitions.yaml with blueprints and modules."""
    blueprints = {
        "default_chat": {
            "description": "Standard Chat-Assistent",
            "role": "You are a helpful AI assistant. Answer concisely and accurately.",
            "role_template": "You are {name}, a {arch} model{params_label} by {publisher}, optimized for {capabilities}{type_label}.",
            "modules": ["instruct_scaffolding", "safety_block", "output_style_default"],
        },
        "coding_agent": {
            "description": "Coding-spezialisierter Assistent",
            "role": "You are an expert software engineer with strong coding skills.",
            "role_template": "You are {name}, a {arch} model{params_label} by {publisher}, specialized in {capabilities}{type_label}.",
            "modules": ["instruct_scaffolding", "coding_principles", "safety_block", "output_style_technical"],
        },
        "granite_coding_agent": {
            "description": "IBM Granite Coding-Assistent mit modellfamilien-spezifischem Template",
            "role": "You are an IBM Granite software engineer with strong coding skills.",
            "role_template": "You are {name}, a {arch} model{params_label} by {publisher}, specialized in {capabilities}{type_label}.",
            "modules": ["instruct_scaffolding", "coding_principles", "safety_block", "output_style_technical"],
            "template_map": {
                "granite-4.0": "granite-4.0-h-tiny_template.jinja",
                "granite-4.1-30b": "granite-4.1-30b_template.jinja",
            },
        },
        "reasoning_assistant": {
            "description": "Reasoning/Thinking-Modell ohne CoT-Scaffolding",
            "role": "You are an AI assistant. Provide accurate, well-considered answers.",
            "role_template": "You are {name}, a {arch} model{params_label} by {publisher}, optimized for {capabilities}{type_label}.",
            "modules": ["safety_block", "output_style_default"],
        },
        "reasoning_coding": {
            "description": "Reasoning-Modell mit Coding-Fokus ohne CoT-Scaffolding",
            "role": "You are an expert software engineer with strong coding skills.",
            "role_template": "You are {name}, a {arch} model{params_label} by {publisher}, specialized in {capabilities}{type_label}.",
            "modules": ["coding_principles", "safety_block", "output_style_technical"],
        },
         "gemma_assistant": {
            "description": "Gemma-4 spezifisch (Standard)",
            "role": "You are Gemma-4, a helpful AI assistant.",
            "role_template": "You are {name}, a {arch} model{params_label} by {publisher}, optimized for {capabilities}{type_label}.",
            "modules": ["instruct_scaffolding", "gemma_capabilities", "coding_principles", "safety_block", "output_style_default"],
            "custom_template": True,
        },
        "gemma_reasoning": {
            "description": "Gemma-4 spezifisch (Thinking via <|think|>)",
            "role": "You are Gemma-4, a helpful AI assistant.",
            "role_template": "You are {name}, a {arch} model{params_label} by {publisher}, optimized for {capabilities}{type_label}.",
            "modules": ["gemma_capabilities", "coding_principles", "safety_block", "output_style_default"],
            "custom_template": True,
            "template_map": {
                "12b": "gemma4_12b_template_minijinja.jinja",
                "19b": "gemma4-19b-template_minijinja.jinja",
                "26b": "gemma4-26b-template_minijinja.jinja",
            },
            "enable_thinking_by_category": {
                "coding": False,
                "agentic": False,
                "knowledge": True,
                "math": True,
            },
            "reasoning_parsing": {
                "enabled": False,
                "startString": " thinking",
                "endString": " response",
            },
        },
        "gptoss_reasoning": {
            "description": "GPT-OSS Harmony-Format (Reasoning + Coding)",
            "role": "You are GPT-OSS, a helpful AI assistant with coding and reasoning skills.",
            "role_template": "You are {name}, a {arch} model{params_label} by {publisher}, optimized for {capabilities}{type_label}.",
            "modules": ["gptoss_reasoning_level", "coding_principles", "safety_block", "output_style_technical"],
        },
        "magistral_reasoning": {
            "description": "Magistral [THINK]-Format (Reasoning + Coding)",
            "role": "You are Magistral, an AI assistant.",
            "role_template": "You are {name}, a {arch} model{params_label} by {publisher}, optimized for {capabilities}{type_label}.",
            "modules": ["coding_principles", "safety_block", "output_style_technical"],
        },
        "phi4_reasoning": {
            "description": "Phi-4-Reasoning-Plus <think>-Format",
            "role": "You are Phi-4, an AI assistant.",
            "role_template": "You are {name}, a {arch} model{params_label} by {publisher}, optimized for {capabilities}{type_label}.",
            "modules": ["coding_principles", "safety_block", "output_style_technical"],
        },
        "ministral_reasoning": {
            "description": "Ministral Reasoning [THINK]-Format",
            "role": "You are Ministral, an AI assistant.",
            "role_template": "You are {name}, a {arch} model{params_label} by {publisher}, optimized for {capabilities}{type_label}.",
            "modules": ["coding_principles", "safety_block", "output_style_technical"],
        },
        "nemotron_reasoning": {
            "description": "Nemotron Cascade Thinking-Format",
            "role": "You are Nemotron, an AI assistant.",
            "role_template": "You are {name}, a {arch} model{params_label} by {publisher}, optimized for {capabilities}{type_label}.",
            "modules": ["coding_principles", "safety_block", "output_style_technical"],
        },
        "apriel_reasoning": {
            "description": "Apriel Thinker [BEGIN FINAL RESPONSE]-Format",
            "role": "You are Apriel, an AI assistant.",
            "role_template": "You are {name}, a {arch} model{params_label} by {publisher}, optimized for {capabilities}{type_label}.",
            "modules": ["coding_principles", "safety_block", "output_style_technical"],
        },
        "none": {
            "description": "No blueprint (audio/vision/etc.)",
            "role": "",
            "modules": [],
        },
    }

    modules = {
        "safety_block": {
            "description": "Safety constraints",
            "full": "<safety>\n-Never introduce secrets or credentials into code, logs, or commits.\n- Do not execute code without explicit user confirmation.\n- Do not fabricate information or pretend to have capabilities you lack.\n- Respect user privacy and data security.\n</safety>",
            "medium": "<safety>Never introduce secrets or credentials into code, logs, or commits. Do not execute code without user confirmation. Do not fabricate information.</safety>",
            "minimal": "<safety>Never introduce secrets or credentials into code, logs, or commits. Do not execute code without user confirmation. Do not fabricate information.</safety>",
        },
        "coding_principles": {
            "description": "Code quality rules",
            "full": "\n<coding>\n1. GitHub: Never commit unless explicitly asked. Never push unless explicitly asked.\n2. Never introduce secrets or credentials into code, logs, or commits.\n3. Don't refactor surrounding code unless asked.\n\n<Code_changes>\n- Understand existing conventions before editing\n- Read surrounding code, imports, and neighboring files\n- Mimic existing style. Use the same libraries and patterns\n- Never assume a library is available — verify it's used\n- Make minimal changes\n- When running a non-trivial bash command that changes the system, briefly state what it does and why\n- After completing a task, run lint and typecheck. If tools are unknown, ask the user and suggest adding to `AGENTS.md`\n</Code_changes>\n\n<code_quality>\n- Write clean, efficient code with minimal comments\n- Comment only where logic is not self-explanatory; avoid redundancy\n- Understand the codebase thoroughly before implementing\n- Break extensive new code into smaller units\n</code_quality>\n\n<file_system>\n- Verify file paths; do not assume relative to cwd\n- Edit files in place; never create renamed copies\n- Use sed for global search/replace\n</file_system>\n\n<testing>\n- For bug fixes: write a test that reproduces the issue first\n- For new features: test-driven development where appropriate\n- Consult user if testing infra is missing or costly to set up\n</testing>\n\n<troubleshooting>\n- On failure, consider root causes systematically\n- On repeated failures: list 5-7 possible causes, assess likelihood, address systematically\n- On major obstacles: propose a new plan and seek confirmation\n</troubleshooting>\n\n</coding>\n</coding>",
            "medium": "<coding>Understand existing conventions before editing. Read surrounding code, imports, and neighboring files. Mimic existing style. Use the same libraries and patterns. Never assume a library is available — verify it's used. Make minimal changes. Don't refactor surrounding code unless asked. After completing a task, run lint and typecheck. If unknown, ask the user and suggest adding to AGENTS.md. When running a non-trivial bash command that changes the system, briefly state what it does and why. Edit in place; verify paths. Reproduce bugs with tests before fixing. On failure, consider root causes systematically.</coding>",
            "minimal": "<coding>Write clean, minimal code. Understand codebase first. Edit in place; verify paths. Reproduce bugs with tests before fixing. On failure, consider root causes systematically.</coding>",
        },
        "output_style_default": {
            "description": "General output style",
            "full": "<output>\n- Structure responses clearly with concise sections where appropriate.\n- Prefer clarity over verbosity, precision over rhetoric.\n- Respond in the user's language.\n</output>",
            "medium": "<output>Prefer clarity over verbosity. Respond in the user's language.</output>",
            "minimal": "<output>Prefer clarity over verbosity. Respond in the user's language.</output>",
        },
        "output_style_technical": {
            "description": "Technical output style",
            "full": "<output>\n- Provide concrete code examples where useful.\n- Explain design decisions briefly.\n- Include error handling and edge cases.\n- Prefer clarity over verbosity.\n</output>",
            "medium": "<output>Provide code with error handling. Prefer clarity over verbosity.</output>",
            "minimal": "<output>Provide code with error handling. Prefer clarity over verbosity.</output>",
        },
        "gptoss_reasoning_level": {
            "description": "GPT-OSS Reasoning-Level (OpenAI: 'The reasoning level can be set in the system prompts, e.g. Reasoning: high')",
            "full": f"Reasoning: {GPTOSS_REASONING_EFFORT}",
            "medium": f"Reasoning: {GPTOSS_REASONING_EFFORT}",
            "minimal": f"Reasoning: {GPTOSS_REASONING_EFFORT}",
        },
        "instruct_scaffolding": {
            "description": "Structured problem-solving guidance for instruct models",
            "full": "<reasoning>\n- Analyze the problem step by step before answering.\n- Consider multiple approaches where relevant.\n- Distinguish between established facts, assumptions, and uncertainty.\n- Verify your reasoning for logical consistency.\n</reasoning>",
            "medium": "<reasoning>Analyze step by step. Consider multiple approaches. Distinguish facts from assumptions.</reasoning>",
            "minimal": "",
        },
         "gemma_capabilities": {
            "description": "Gemma-4 capabilities profile (text, code, reasoning)",
            "full": "<capabilities>\n- Text generation and conversation\n- Code generation, completion, and debugging\n- Reasoning and problem-analysis capabilities\n- Function calling and structured tool use\n- Long context: up to 256K tokens\n- Multilingual: 140+ languages\n</capabilities>",
            "medium": "<capabilities>Text generation, coding, reasoning, function calling, long context, multilingual.</capabilities>",
            "minimal": "",
        },
    }

    definitions = {
        "version": "1.0",
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "blueprints": blueprints,
        "modules": modules,
    }

    yaml_ruamel = YAML()
    yaml_ruamel.indent(mapping=2, sequence=4, offset=2)
    yaml_ruamel.default_flow_style = False
    with open(BLUEPRINT_PATH, "w", encoding="utf-8") as f:
        yaml_ruamel.dump(definitions, f)

    print(f"[OK] Created {BLUEPRINT_PATH} with {len(blueprints)} blueprints and {len(modules)} modules")


def assemble_prompts(preview_only: bool = False) -> None:
    """Phase 3: Generate system prompts from blueprints and write to JSON configs."""
    # Read registry
    yaml_ruamel = YAML()
    yaml_ruamel.preserve_quotes = True
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        registry = yaml_ruamel.load(f)

    # Read blueprint definitions
    with open(BLUEPRINT_PATH, encoding="utf-8") as f:
        bp_defs = yaml_ruamel.load(f)

    blueprints = bp_defs.get("blueprints", {})
    modules = bp_defs.get("modules", {})

    # Read LM Studio configs
    lms_configs = read_lms_configs(CONFIG_ROOT)

    # Build reverse lookup: normalized config name -> list of (publisher, info)
    # Zusaetzlich Broad-Keys (ohne @quant/Variant-Suffix) einfuegen, damit
    # Registry-Keys mit Quant-Suffix (z.B. "...@iq4_nl") matchen koennen.
    config_lookup = {}
    for info in lms_configs:
        name = info.get("dir_name", "")
        key = normalize_model_name(name)
        config_lookup.setdefault(key, []).append((info["publisher"], info))
        key_broad = normalize_for_config(name)
        config_lookup.setdefault(key_broad, []).append((info["publisher"], info))
        pub = info.get("publisher", "")
        if pub:
            key2 = normalize_model_name(f"{pub}-{name}")
            config_lookup.setdefault(key2, []).append((info["publisher"], info))
            key2_broad = normalize_for_config(f"{pub}-{name}")
            config_lookup.setdefault(key2_broad, []).append((info["publisher"], info))

    stats = {"assembled": 0, "skipped": 0, "not_found": 0, "errors": 0, "total_configs_written": 0}

    for model_name in registry:
        entry = registry[model_name]
        if not isinstance(entry, dict):
            continue
        if any(kw in model_name.lower() for kw in BLACKLIST):
            stats["skipped"] += 1
            continue

        bp_name = entry.get("blueprint", "default_chat")

        if bp_name == "none":
            stats["skipped"] += 1
            continue

        bp = blueprints.get(bp_name)
        if not bp:
            print(f"[WARN] Blueprint '{bp_name}' not found for {model_name}")
            stats["skipped"] += 1
            continue

        truncation = entry.get("truncation", "full")
        if truncation not in ("full", "medium", "minimal"):
            truncation = "full"

        static_role = bp.get("role", "")
        role_template = bp.get("role_template", None)
        role = render_role(entry, model_name, role_template, static_role)
        module_list = bp.get("modules", [])
        prompt_parts = []
        if role:
            prompt_parts.append(f"<role>\n{role}\n</role>")
        for mod_name in module_list:
            mod = modules.get(mod_name)
            if not mod:
                continue
            content = mod.get(truncation, mod.get("full", ""))
            if content:
                prompt_parts.append(content)
        assembled_prompt = "\n\n".join(prompt_parts)

        # Find all matching JSON configs (all publisher variants, exact + fuzzy)
        # @quant-Suffixe (z.B. @iq4_nl) bleiben in normalize_model_name erhalten und
        # verhindern den Match. Deshalb zusaetzlich den Broad-Key (ohne Quant/
        # Variant-Suffix) pruefen. Fix 2026-08-07: NOT FOUND fuer @quant-Keys.
        search_keys = [normalize_model_name(model_name)]
        broad_key = normalize_for_config(model_name)
        if broad_key != search_keys[0]:
            search_keys.append(broad_key)
        candidates = []
        seen_paths = set()

        # Exact match
        for search_key in search_keys:
            if search_key in config_lookup:
                for pub, info in config_lookup[search_key]:
                    p = str(info.get("json_path", ""))
                    if p not in seen_paths:
                        candidates.append((pub, info))
                        seen_paths.add(p)

        # Fuzzy match all keys (not just fallback)
        for search_key in search_keys:
            for ck, ci_list in config_lookup.items():
                if ck == search_key:
                    continue
                if search_key in ck or ck in search_key:
                    for pub, info in ci_list:
                        p = str(info.get("json_path", ""))
                        if p in seen_paths:
                            continue
                        if ck in search_key:
                            # Config key is shorter: verify file name has distinguishing suffix
                            file_stem = info.get("file_name", "")
                            file_stem = file_stem.removesuffix(".json")
                            file_key = normalize_model_name(file_stem)
                            if search_key not in file_key:
                                continue
                        else:
                            # search_key in ck: exclude variant-suffixed configs not matching
                            suffix = ck[len(search_key):].lstrip("-")
                            for vs in _VARIANT_SUFFIXES:
                                vs_clean = vs.lstrip("-")
                                if suffix.startswith(vs_clean) and not search_key.endswith(vs_clean):
                                    break
                            else:
                                candidates.append((pub, info))
                                seen_paths.add(p)
                            continue
                        candidates.append((pub, info))
                        seen_paths.add(p)

        if not candidates:
            stats["not_found"] += 1
            if not preview_only:
                print(f"  [NOT FOUND] {model_name}")
            continue

        # Publisher-Filter: Configs anderer Publisher nicht mit diesem
        # Registry-Entry ueberschreiben (z.B. verhindert unsloth-Entry,
        # per Fuzzy-Match die bartowski/google/mradermacher-Configs zu
        # treffen und mit der unsloth-Rolle zu ueberschreiben).
        entry_pub = str(entry.get("publisher", "")).lower() if entry.get("publisher") else ""
        if entry_pub and candidates:
            pub_match = [c for c in candidates if str(c[0]).lower() == entry_pub]
            if pub_match:
                candidates = pub_match

        if preview_only:
            old_prompt = candidates[0][1].get("system_prompt", "")
            old_len = len(old_prompt)
            new_len = len(assembled_prompt)
            print(f"\n{'='*60}")
            print(f"[PREVIEW] {model_name}")
            print(f"  Blueprint: {bp_name} | Truncation: {truncation}")
            print(f"  Candidates: {len(candidates)} | Old: {old_len} chars | New: {new_len} chars")
            sys.stdout.flush()
        else:
            written = 0
            for pub, info in candidates:
                json_path = info["json_path"]
                try:
                    with open(json_path, encoding="utf-8-sig") as f:
                        data = json.load(f)

                    tpl_name = resolve_template_name(bp, model_name) or entry.get("template")
                    tpl_content = None
                    if tpl_name:
                        tpl_path = TEMPLATE_DIR / tpl_name
                        if tpl_path.exists():
                            tpl_content = tpl_path.read_text(encoding="utf-8")

                    fields = data.setdefault("operation", {}).setdefault("fields", [])
                    found_pt = False
                    for field in fields:
                        if field.get("key") == "llm.prediction.systemPrompt":
                            field["value"] = assembled_prompt
                        if field.get("key") == "llm.prediction.promptTemplate":
                            if tpl_content is not None:
                                field["value"] = tpl_content
                            found_pt = True
                    if tpl_content is not None and not found_pt:
                        fields.append({"key": "llm.prediction.promptTemplate", "value": tpl_content})

                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)

                    written += 1
                except Exception as e:
                    print(f"[ERROR] {model_name} ({pub}): {e}")
                    stats["errors"] += 1

            stats["assembled"] += 1
            stats["total_configs_written"] += written
            print(f"[OK] {model_name}: {bp_name}/{truncation} -> {written} config(s) ({len(assembled_prompt)} chars)")

    print(f"\n{'='*60}")
    print(f"Summary: {stats['assembled']} assembled, {stats['skipped']} skipped, "
          f"{stats['not_found']} not found, {stats['errors']} errors")


def validate_prompts() -> None:
    """Phase 4a: Validate all written prompts for XML well-formedness and content."""
    lms_configs = read_lms_configs(CONFIG_ROOT)
    issues = []
    passed = 0
    checked = 0

    # Read blueprint module content for expected patterns
    yaml_ruamel = YAML()
    with open(BLUEPRINT_PATH, encoding="utf-8") as f:
        yaml_ruamel.load(f)

    for info in lms_configs:
        prompt = info.get("system_prompt", "")
        if not prompt:
            continue
        checked += 1

        # 1. Check XML-like tags are balanced
        open_tags = []
        for m in re.finditer(r"</?(\w+)>", prompt):
            tag = m.group(1)
            if prompt[m.start():m.start()+2] == "</":
                if open_tags and open_tags[-1] == tag:
                    open_tags.pop()
                else:
                    issues.append(f"{info['dir_name']}: Unbalanced closing </{tag}>")
            else:
                open_tags.append(tag)
        if open_tags:
            issues.append(f"{info['dir_name']}: Unclosed tag(s): {open_tags}")

        # 2. Check for Jinja template remnants ({{ or }} without valid syntax)
        if re.search(r"\{\{|\}\}", prompt) and not re.search(r"\{\{.*?\}\}", prompt):
            issues.append(f"{info['dir_name']}: Suspicious Jinja syntax")

        # 3. Check prompt length is reasonable
        if len(prompt) < 50:
            issues.append(f"{info['dir_name']}: Very short prompt ({len(prompt)} chars)")
        if len(prompt) > 5000:
            issues.append(f"{info['dir_name']}: Very long prompt ({len(prompt)} chars)")

        passed += 1

    print(f"\n{'='*60}")
    print(f"Validation: {checked} checked, {passed} passed, {len(issues)} issues")
    if issues:
        print(f"\nIssues ({len(issues)}):")
        for issue in issues:
            print(f"  ! {issue}")

    # Summary statistics
    prompt_lengths = [len(info["system_prompt"]) for info in lms_configs if info["system_prompt"]]
    if prompt_lengths:
        print("\nPrompt length stats:")
        print(f"  Min: {min(prompt_lengths)} chars | Max: {max(prompt_lengths)} chars")
        print(f"  Avg: {sum(prompt_lengths)//len(prompt_lengths)} chars")
        short = [pl for pl in prompt_lengths if pl < 50]
        long = [pl for pl in prompt_lengths if pl > 2000]
        if short:
            print(f"  WARN: {len(short)} prompts < 50 chars")
        if long:
            print(f"  WARN: {len(long)} prompts > 2000 chars (may still have old defaults)")


def _interactive_menu() -> None:
    """Show interactive command selection menu when no args given."""
    cmds = [
        ("all",      "classify → assemble → validate (full pipeline)"),
        ("classify", "Read model registry & GGUF headers, classify blueprint + reasoning"),
        ("assemble", "Build and write system prompts from blueprints"),
        ("preview",  "Dry-run: compute prompts and print summary without writing"),
        ("validate", "Check all system prompts for XML balance, length, Jinja remnants"),
    ]
    print("\n" + "=" * 60)
    print("  assemble_blueprint.py - Interactive Menu")
    print("=" * 60)
    for i, (cmd, desc) in enumerate(cmds, 1):
        print(f"  {i:2d}. {cmd:12s} {desc}")
    print(f"  {len(cmds)+1:2d}. {'quit':12s} Exit")
    print("=" * 60)

    while True:
        try:
            choice = input("\nSelect command [1-6]: ").strip()
            if not choice or choice == str(len(cmds) + 1):
                print("[OK] Bye")
                sys.exit(0)
            idx = int(choice) - 1
            if 0 <= idx < len(cmds):
                cmd = cmds[idx][0]
                print(f"\n[RUN] assemble_blueprint.py {cmd}\n")
                sys.argv = [sys.argv[0], cmd]
                break
            print(f"[ERROR] Invalid choice: {choice}")
        except (EOFError, KeyboardInterrupt):
            print("\n[OK] Bye")
            sys.exit(0)
        except ValueError:
            print(f"[ERROR] Invalid choice: {choice}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        _interactive_menu()

    command = sys.argv[1]

    # Bootstrap: Blueprint-YAML ist die Quelle der Wahrheit. Sie wird nur
    # generiert, wenn sie (noch) nicht existiert - nie aus dem Python-Code
    # überschrieben. Manuelle Anpassungen an der YAML bleiben erhalten.
    if not BLUEPRINT_PATH.exists():
        print("[BOOTSTRAP] blueprint_definitions.yaml fehlt - initial aus Code-Defaults erzeugen ...")
        create_blueprint_definitions()

    if command in ("classify", "all"):
        classify_registry()

    if command in ("assemble", "all"):
        assemble_prompts(preview_only=False)

    if command == "preview":
        assemble_prompts(preview_only=True)

    if command in ("validate", "all"):
        validate_prompts()
