#!/usr/bin/env python3
"""
assemble_blueprint.py – Prompt-Standardisierung per Blueprint-System

Phases:
  Phase 1: Klassifikation in model_registry.yaml (reasoning, capabilities, blueprint)
  Phase 2: Textbaustein-Bibliothek definieren (blueprint_definitions.yaml)
  Phase 3: Assembly – System-Prompts aus Blueprints generieren
  Phase 4: Validierung – Syntax-Check, Regression-Prüfung

Usage:
  python assemble_blueprint.py classify   -> Phase 1: Klassifikation
  python assemble_blueprint.py assemble   -> Phase 3: Assembly + Write
  python assemble_blueprint.py validate   -> Phase 4: Syntax-Check
  python assemble_blueprint.py all         -> Alle Phasen ausführen
"""

from ruamel.yaml import YAML
import json
import re
import os
import sys
from pathlib import Path
from datetime import datetime

# === Pfade ===
REPO_ROOT = Path(__file__).parent
REGISTRY_PATH = REPO_ROOT / "doc-git" / "model_registry.yaml"
BLUEPRINT_PATH = REPO_ROOT / "doc-git" / "blueprint_definitions.yaml"
CONFIG_ROOT = Path.home() / ".lmstudio" / ".internal" / "user-concrete-model-default-config"
INVENTORY_PATH = REPO_ROOT / "prompt_inventory.csv"

# === Reasoning Keywords ===
REASONING_KEYWORDS = [
    "r1", "thinker", "thinking", "qwq", "cascade",
    "cot", "reasoning", "reasoning-plus", "reasoningplus", "rnj",
    "math", "gpt-oss", "magistral", "phi-4", "ministral"
]
NON_REASONING_MODELS = [
    "whisper", "flux", "ocr", "translategemma"
]


def normalize_model_name(name: str) -> str:
    """Normalize a model name for matching between registry and directory names."""
    s = name.lower()
    s = re.sub(r'\.gguf$', '', s)
    s = re.sub(r'-(gguf|mxpr4)$', '', s)
    # Strip publisher prefix (e.g., "mradermacher/", "unsloth/")
    s = re.sub(r'^[^/]+/', '', s)
    # Normalize separators: dots and underscores become hyphens
    s = s.replace('.', '-').replace('_', '-')
    # Collapse multiple hyphens
    while '--' in s:
        s = s.replace('--', '-')
    return s


def classify_reasoning(model_name: str, notes: str = "") -> str:
    """Classify model reasoning type: thinking | instruct | none."""
    name_lower = model_name.lower()
    notes_lower = notes.lower() if notes else ""

    # Check for non-reasoning models first
    for kw in NON_REASONING_MODELS:
        if kw in name_lower:
            return "none"

    # Check for thinking/reasoning models
    for kw in REASONING_KEYWORDS:
        if kw in name_lower:
            return "thinking"

    # Notes-based detection removed: too many false positives
    # (descriptive words like "reasoning" in notes are not CoT indicators)

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
    if "gemma-4" in name_lower or "gemma-4" in arch_lower:
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

    # Reasoning models
    if reasoning == "thinking":
        if "coding" in capabilities.split(", "):
            return "reasoning_coding"
        return "reasoning_assistant"

    # Granite general-purpose models: keep on default_chat (not code-specialized)
    if "granite" in name_lower and "code" not in name_lower:
        return "default_chat"

    # Coding models
    if "coding" in capabilities.split(", "):
        return "coding_agent"

    # Default
    return "default_chat"


def has_custom_template(entry: dict) -> bool:
    """Check if model has a custom jinja template."""
    return "template" in entry and entry["template"]


def extract_params(model_name: str) -> str | None:
    """Extract parameter count from model name (e.g. '14B', '32B', '3.8b')."""
    m = re.search(r'(?:^|[-])(\d+\.?\d*)[BMK]', model_name, re.IGNORECASE)
    if m:
        val = m.group(0)  # e.g. "14B", "32B"
        # Clean up leading hyphen
        val = val.lstrip("-")
        return val.upper()
    return None


def format_publishers(pub_val) -> str:
    """Format publisher(s) into a readable string."""
    if isinstance(pub_val, list):
        names = [str(p) for p in pub_val if p]
        return "/".join(names) if names else "unknown"
    return str(pub_val) if pub_val else "unknown"


def format_capabilities(caps) -> str:
    """Format capabilities (comma-separated string or list) into readable string."""
    if not caps:
        return "test generation"
    if isinstance(caps, str):
        caps = [c.strip() for c in caps.split(",")]
    if isinstance(caps, list):
        labels = {
            "text": "test generation",
            "coding": "coding",
            "vision": "visual design",
            "audio": "audio processing",
            "agentic": "agentic tools",
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
        rendered = re.sub(r'  +', ' ', rendered).strip()
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
    if ctx_len >= 8192:
        return "medium"
    return "minimal"


def read_lms_configs(config_root: Path) -> list:
    """Read all LM Studio JSON config files, return a list of config dicts."""
    models = []
    if not config_root.exists():
        print(f"[WARN] Config root not found: {config_root}")
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
                        with open(json_path, "r", encoding=enc) as f:
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
                    for field in data.get("load", {}).get("fields", []):
                        if field.get("key") == "llm.load.contextLength":
                            ctx_length = field.get("value")
                            break

                    models.append({
                        "publisher": publisher,
                        "dir_name": model_dir_name,
                        "file_name": json_path.name,
                        "system_prompt": sys_prompt or "",
                        "context_length": ctx_length,
                        "json_path": json_path,
                    })
                except Exception as e:
                    print(f"[WARN] Error parsing {json_path}: {e}")

    return models


def classify_registry():
    """Phase 1: Read registry, classify models, write updated YAML."""
    if not REGISTRY_PATH.exists():
        print(f"[ERROR] Registry not found: {REGISTRY_PATH}")
        return

    yaml_ruamel = YAML()
    yaml_ruamel.preserve_quotes = True
    yaml_ruamel.indent(mapping=2, sequence=4, offset=2)

    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        registry = yaml_ruamel.load(f)

    if not registry:
        print("[ERROR] Empty registry")
        return

    # Read LM Studio configs for context_length info
    lms_configs = read_lms_configs(CONFIG_ROOT)

    updated_count = 0
    for model_name, entry in registry.items():
        if not isinstance(entry, dict):
            continue

        arch = str(entry.get("arch", ""))
        notes = str(entry.get("notes", ""))
        custom_tpl = has_custom_template(entry)

        # Classification
        reasoning = classify_reasoning(model_name, notes)
        capabilities = classify_capabilities(model_name, arch, notes)
        blueprint = select_blueprint(reasoning, capabilities, arch, model_name)

        # Get context length from LM Studio configs
        ctx_len = None
        for lms_info in lms_configs:
            lms_name = lms_info.get("dir_name", "")
            if normalize_model_name(model_name) in normalize_model_name(lms_name) or \
               normalize_model_name(lms_name) in normalize_model_name(model_name):
                ctx_len = lms_info.get("context_length")
                break

        truncation = truncation_from_context(ctx_len)

        # Add new fields (preserving insertion order)
        # Insert before 'notes' if it exists, otherwise at end
        entry["reasoning"] = reasoning
        entry["capabilities"] = capabilities
        entry["blueprint"] = blueprint
        entry["truncation"] = truncation
        if custom_tpl:
            entry["custom_template"] = True

        # Remove context from registry if it exists – truth is in JSON configs
        if "context" in entry:
            del entry["context"]

        updated_count += 1

    # Write updated registry
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        yaml_ruamel.dump(registry, f)

    # Normalize blank lines (no blanks within entries, one between entries)
    from fmt_registry import format_blank_lines
    format_blank_lines(REGISTRY_PATH)

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


def create_blueprint_definitions():
    """Phase 2: Create blueprint_definitions.yaml with blueprints and modules."""
    blueprints = {
        "default_chat": {
            "description": "Standard Chat-Assistent",
            "role": "You are a helpful AI assistant. Answer concisely and accurately.",
            "role_template": "You are {name}, a {arch} model{params_label} by {publisher}, optimized for {capabilities}{type_label}.",
            "modules": ["safety_block", "output_style_default"],
        },
        "coding_agent": {
            "description": "Coding-spezialisierter Assistent",
            "role": "You are an expert software engineer with strong coding skills.",
            "role_template": "You are {name}, a {arch} model{params_label} by {publisher}, specialized in {capabilities}{type_label}.",
            "modules": ["safety_block", "coding_principles", "output_style_technical"],
        },
        "reasoning_assistant": {
            "description": "Reasoning/Thinking-Modell (instruct-mode)",
            "role": "You are an AI assistant that analyzes problems carefully and provides well-reasoned answers.",
            "role_template": "You are {name}, a {arch} model{params_label} by {publisher}, optimized for {capabilities}{type_label}.",
            "modules": ["thinking_instruction", "safety_block", "output_style_default"],
        },
        "reasoning_coding": {
            "description": "Reasoning-Modell mit Coding-Fokus",
            "role": "You are an expert software engineer who analyzes problems step by step.",
            "role_template": "You are {name}, a {arch} model{params_label} by {publisher}, specialized in {capabilities}{type_label}.",
            "modules": ["thinking_instruction", "safety_block", "coding_principles", "output_style_technical"],
        },
         "gemma_assistant": {
            "description": "Gemma-4 spezifisch (Standard)",
            "role": "You are Gemma-4, a helpful AI assistant.",
            "role_template": "You are {name}, a {arch} model{params_label} by {publisher}, optimized for {capabilities}{type_label}.",
            "modules": ["gemma_capabilities", "safety_block", "output_style_default"],
            "custom_template": True,
        },
        "gemma_reasoning": {
            "description": "Gemma-4 spezifisch (Thinking via <|think|>)",
            "role": "You are Gemma-4, a helpful AI assistant.",
            "role_template": "You are {name}, a {arch} model{params_label} by {publisher}, optimized for {capabilities}{type_label}.",
            "modules": ["gemma_capabilities", "gemma_think_token", "safety_block", "output_style_default"],
            "custom_template": True,
        },
        "none": {
            "description": "No blueprint (audio/vision/etc.)",
            "role": "",
            "modules": [],
        },
    }

    modules = {
        "safety_block": {
            "description": "Safety-Constraints",
            "full": "<safety>\n- Do not execute code without explicit user confirmation.\n- Do not fabricate information or pretend to have capabilities you lack.\n- Respect user privacy and data security.\n</safety>",
            "medium": "<safety>Do not execute code without user confirmation. Do not fabricate information.</safety>",
            "minimal": "",
        },
        "coding_principles": {
            "description": "Code-Qualitätsregeln",
            "full": "<coding>\n- Understand the existing codebase before making changes.\n- Write clean, maintainable, efficient code.\n- Make minimal necessary changes.\n- Add comments only where they provide real explanatory value.\n- Prefer reproducible debugging and testing approaches.\n</coding>",
            "medium": "<coding>Write clean, minimal, correct code. Understand existing code first.</coding>",
            "minimal": "",
        },
        "output_style_default": {
            "description": "Allgemeiner Output-Stil",
            "full": "<output>\n- Structure responses clearly with concise sections where appropriate.\n- Prefer clarity over verbosity, precision over rhetoric.\n- Respond in the user's language.\n</output>",
            "medium": "<output>Prefer clarity over verbosity. Respond in the user's language.</output>",
            "minimal": "",
        },
        "output_style_technical": {
            "description": "Technischer Output-Stil",
            "full": "<output>\n- Provide concrete code examples where useful.\n- Explain design decisions briefly.\n- Include error handling and edge cases.\n- Prefer clarity over verbosity.\n</output>",
            "medium": "<output>Provide code with error handling. Prefer clarity over verbosity.</output>",
            "minimal": "",
        },
        "thinking_instruction": {
            "description": "Chain-of-Thought Anweisung für Reasoning-Modelle",
            "full": "<reasoning>\n- Analyze the problem step by step before answering.\n- Consider multiple approaches where relevant.\n- Distinguish between established facts, assumptions, and uncertainty.\n- Verify your reasoning for logical consistency.\n</reasoning>",
            "medium": "<reasoning>Analyze step by step. Consider multiple approaches. Distinguish facts from assumptions.</reasoning>",
            "minimal": "",
        },
         "gemma_think_token": {
            "description": "Gemma-4 <|think|> Token (statt <thinking>)",
            "full": "<|think|>Analyze the problem step by step before answering.</|think|>",
            "medium": "<|think|>Analyze step by step.</|think|>",
            "minimal": "",
        },
        "gemma_capabilities": {
            "description": "Gemma-4 Fähigkeitsprofil (Text, Code, Reasoning)",
            "full": "<capabilities>\n- Text generation and conversation\n- Code generation, completion, and debugging\n- Step-by-step reasoning and problem analysis\n- Function calling and structured tool use\n- Long context: up to 256K tokens\n- Multilingual: 140+ languages\n</capabilities>",
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


def assemble_prompts(preview_only: bool = False):
    """Phase 3: Generate system prompts from blueprints and write to JSON configs."""
    # Read registry
    yaml_ruamel = YAML()
    yaml_ruamel.preserve_quotes = True
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        registry = yaml_ruamel.load(f)

    # Read blueprint definitions
    with open(BLUEPRINT_PATH, "r", encoding="utf-8") as f:
        bp_defs = yaml_ruamel.load(f)

    blueprints = bp_defs.get("blueprints", {})
    modules = bp_defs.get("modules", {})

    # Read LM Studio configs
    lms_configs = read_lms_configs(CONFIG_ROOT)

    # Build reverse lookup: normalized config name -> list of (publisher, info)
    config_lookup = {}
    for info in lms_configs:
        name = info.get("dir_name", "")
        key = normalize_model_name(name)
        config_lookup.setdefault(key, []).append((info["publisher"], info))
        pub = info.get("publisher", "")
        if pub:
            key2 = normalize_model_name(f"{pub}-{name}")
            config_lookup.setdefault(key2, []).append((info["publisher"], info))

    stats = {"assembled": 0, "skipped": 0, "not_found": 0, "errors": 0, "total_configs_written": 0}

    for model_name in registry:
        entry = registry[model_name]
        if not isinstance(entry, dict):
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
        search_key = normalize_model_name(model_name)
        candidates = []
        seen_paths = set()

        # Exact match
        if search_key in config_lookup:
            for pub, info in config_lookup[search_key]:
                p = str(info.get("json_path", ""))
                if p not in seen_paths:
                    candidates.append((pub, info))
                    seen_paths.add(p)

        # Fuzzy match all keys (not just fallback)
        for ck, ci_list in config_lookup.items():
            if ck == search_key:
                continue
            if search_key in ck or ck in search_key:
                for pub, info in ci_list:
                    p = str(info.get("json_path", ""))
                    if p in seen_paths:
                        continue
                    # When config key is a substring of search_key (search_key is more specific),
                    # verify that the file name also contains the distinguishing suffix
                    if ck in search_key:
                        file_stem = info.get("file_name", "")
                        if file_stem.endswith(".json"):
                            file_stem = file_stem[:-5]
                        file_key = normalize_model_name(file_stem)
                        if search_key not in file_key:
                            continue
                    candidates.append((pub, info))
                    seen_paths.add(p)

        if not candidates:
            stats["not_found"] += 1
            if not preview_only:
                print(f"  [NOT FOUND] {model_name}")
            continue

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
                    with open(json_path, "r", encoding="utf-8-sig") as f:
                        data = json.load(f)

                    for field in data.get("operation", {}).get("fields", []):
                        if field.get("key") == "llm.prediction.systemPrompt":
                            field["value"] = assembled_prompt
                        if field.get("key") == "llm.prediction.promptTemplate":
                            field["value"] = ""

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


def validate_prompts():
    """Phase 4a: Validate all written prompts for XML well-formedness and content."""
    lms_configs = read_lms_configs(CONFIG_ROOT)
    issues = []
    passed = 0
    checked = 0

    # Read blueprint module content for expected patterns
    yaml_ruamel = YAML()
    with open(BLUEPRINT_PATH, "r", encoding="utf-8") as f:
        bp_defs = yaml_ruamel.load(f)

    for info in lms_configs:
        prompt = info.get("system_prompt", "")
        if not prompt:
            continue
        checked += 1

        # 1. Check XML-like tags are balanced
        open_tags = []
        for m in re.finditer(r'</?(\w+)>', prompt):
            tag = m.group(1)
            if prompt[m.start():m.start()+2] == '</':
                if open_tags and open_tags[-1] == tag:
                    open_tags.pop()
                else:
                    issues.append(f"{info['dir_name']}: Unbalanced closing </{tag}>")
            else:
                open_tags.append(tag)
        if open_tags:
            issues.append(f"{info['dir_name']}: Unclosed tag(s): {open_tags}")

        # 2. Check for Jinja template remnants ({{ or }} without valid syntax)
        if re.search(r'\{\{|\}\}', prompt) and not re.search(r'\{\{.*?\}\}', prompt):
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
        print(f"\nPrompt length stats:")
        print(f"  Min: {min(prompt_lengths)} chars | Max: {max(prompt_lengths)} chars")
        print(f"  Avg: {sum(prompt_lengths)//len(prompt_lengths)} chars")
        short = [l for l in prompt_lengths if l < 50]
        long = [l for l in prompt_lengths if l > 2000]
        if short:
            print(f"  WARN: {len(short)} prompts < 50 chars")
        if long:
            print(f"  WARN: {len(long)} prompts > 2000 chars (may still have old defaults)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command in ("classify", "all"):
        classify_registry()
        create_blueprint_definitions()

    if command in ("assemble", "all"):
        assemble_prompts(preview_only=False)

    if command == "preview":
        assemble_prompts(preview_only=True)

    if command in ("validate", "all"):
        validate_prompts()
