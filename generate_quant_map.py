#!/usr/bin/env python3
"""Generate QUANT_MAP for benchmark_config.py from multiple sources.

Sources (in priority order):
1. lms ls --json (currently installed models)
2. LM Studio config files (user-concrete-model-default-config)
3. GGUF metadata cache (gguf-metadata-cache.json)

Usage:
    python generate_quant_map.py              # Print QUANT_MAP to stdout
    python generate_quant_map.py --write      # Write to benchmark_config.py
"""
from __future__ import annotations

import json, os, re, sys, subprocess
from typing import Any, Dict, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LMSTUDIO_INTERNAL = os.path.expanduser(r"~\.lmstudio\.internal")
CONFIG_DIR = os.path.join(LMSTUDIO_INTERNAL, "user-concrete-model-default-config")
GGUF_CACHE = os.path.join(LMSTUDIO_INTERNAL, "gguf-metadata-cache.json")

# Quantization pattern: Q3_K_S, Q4_K_M, Q5_K_M, Q6_K, Q8_0, IQ3_XXS, IQ3_M, IQ4_XS, IQ4_NL, MXFP4, etc.
QUANT_RE = re.compile(r'(?<![a-zA-Z])(Q[0-9]_[A-Z0-9_]+|IQ[0-9]_[A-Z0-9_]+|MXFP[0-9]+|Q8_0_i)(?![a-zA-Z])')


def _source_lms_ls() -> Dict[str, str]:
    """Source 1: lms ls --json for currently installed models."""
    result = {}
    try:
        r = subprocess.run(
            ["lms", "ls", "--json"],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace"
        )
        if r.returncode == 0:
            data = json.loads(r.stdout)
            items = data if isinstance(data, list) else list(data.values())
            for item in items:
                if not isinstance(item, dict):
                    continue
                mk = item.get("modelKey", "")
                if not mk:
                    continue
                # Direct quantization field
                quant = item.get("quantization", {})
                if isinstance(quant, dict) and quant.get("name"):
                    result[mk] = quant["name"]
                    continue
                # Fallback: extract from path/filename
                path = item.get("path", "")
                m = QUANT_RE.search(path)
                if m:
                    result[mk] = m.group(1)
    except Exception as e:
        print(f"  [WARN] lms ls: {e}", file=sys.stderr)
    return result


def _source_config_dir() -> Dict[str, str]:
    """Source 2: LM Studio config files – extract quant from GGUF filenames.

    Config-Dir structure: publisher/repo/filename.gguf.json
    Filename pattern: modelname-Q8_0.gguf.json or modelname.Q6_K.gguf.json
    We extract (model_name, quant) and try to match model_name against WHITELIST keys.
    """
    result = {}
    if not os.path.isdir(CONFIG_DIR):
        return result
    for publisher in os.listdir(CONFIG_DIR):
        pub_dir = os.path.join(CONFIG_DIR, publisher)
        if not os.path.isdir(pub_dir):
            continue
        for repo in os.listdir(pub_dir):
            repo_dir = os.path.join(pub_dir, repo)
            if not os.path.isdir(repo_dir):
                continue
            for fname in os.listdir(repo_dir):
                if not fname.endswith(".json"):
                    continue
                # Extract quant from GGUF filename
                # e.g. "deepseek-coder-33b-instruct.Q3_K_S.gguf.json" → Q3_K_S
                # e.g. "mathstral-7B-v0.1-Q8_0.gguf.json" → Q8_0
                base = fname.replace(".gguf.json", "").replace(".json", "")
                m = QUANT_RE.search(base)
                if m:
                    quant = m.group(1)
                    # Extract model name: everything before the quant pattern
                    # Find where the quant starts in the filename
                    quant_start = base.rfind(m.group(0))
                    name_part = base[:quant_start].rstrip(".-_")
                    # Normalize: lowercase, replace underscores/hyphens
                    name_norm = re.sub(r'[^a-z0-9]+', '-', name_part.lower()).strip('-')
                    if name_norm:
                        result[name_norm] = quant
    return result


def _source_gguf_cache() -> Dict[str, str]:
    """Source 3: GGUF metadata cache – extract quant from file paths."""
    result = {}
    if not os.path.exists(GGUF_CACHE):
        return result
    try:
        with open(GGUF_CACHE, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        # Cache structure: {"json": {"map": [[path, {metadata: {...}}], ...]}}
        map_data = data.get("json", {}).get("map", [])
        for entry in map_data:
            if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                continue
            path = entry[0]
            meta = entry[1] if isinstance(entry[1], dict) else {}
            # Extract quant from path
            m = QUANT_RE.search(path)
            if m:
                quant = m.group(1)
                # Extract model name from path
                # e.g. "C:/.../Qwen3-30B-A3B-python-coder.Q3_K_S.gguf" → qwen3-30b-a3b-python-coder
                basename = os.path.basename(path)
                name_part = QUANT_RE.split(basename)[0].rstrip(".-")
                # Normalize: lowercase, replace underscores with hyphens
                name_norm = re.sub(r'[^a-z0-9]+', '-', name_part.lower()).strip('-')
                if name_norm:
                    result[name_norm] = quant
    except Exception as e:
        print(f"  [WARN] gguf-cache: {e}", file=sys.stderr)
    return result


def _normalize_key(key: str) -> str:
    """Normalize a model key for fuzzy matching."""
    k = key.lower()
    # Remove publisher prefix
    k = re.sub(r'^[a-z0-9_-]+/', '', k)
    # Remove @variant suffix
    k = re.sub(r'@.*', '', k)
    # Normalize separators
    k = re.sub(r'[^a-z0-9]', '', k)
    return k


def build_quant_map(whitelist: Dict[str, str]) -> Dict[str, str]:
    """Build QUANT_MAP for all WHITELIST models from multiple sources.

    Args:
        whitelist: {model_key: display_name} from benchmark_config.py

    Returns:
        {model_key: quantization_name}
    """
    # Collect all sources
    lms_data = _source_lms_ls()
    config_data = _source_config_dir()
    cache_data = _source_gguf_cache()

    print(f"  lms ls:       {len(lms_data)} models")
    print(f"  Config-Dir:   {len(config_data)} entries")
    print(f"  GGUF-Cache:   {len(cache_data)} entries")

    result = {}

    for model_key, display_name in whitelist.items():
        quant = None

        # Priority 1: Exact match in lms ls --json
        if model_key in lms_data:
            quant = lms_data[model_key]

        # Priority 2: Exact match in config dir (publisher/repo or repo)
        if not quant:
            for candidate in [model_key, model_key.split("/")[-1]]:
                if candidate in config_data:
                    quant = config_data[candidate]
                    break

        # Priority 3: Fuzzy match in config dir
        if not quant:
            norm_key = _normalize_key(model_key)
            for ck, cv in config_data.items():
                if _normalize_key(ck) == norm_key:
                    quant = cv
                    break

        # Priority 4: Fuzzy match in GGUF cache
        if not quant:
            norm_key = _normalize_key(model_key)
            for ck, cv in cache_data.items():
                if _normalize_key(ck) == norm_key:
                    quant = cv
                    break

        # Priority 5: Extract from display name or model key
        if not quant:
            for text in [model_key, display_name]:
                m = QUANT_RE.search(text)
                if m:
                    quant = m.group(1)
                    break

        if quant:
            result[model_key] = quant
        else:
            print(f"  [WARN] No quant found for: {model_key} ({display_name})")

    return result


def _format_quant_map(quant_map: Dict[str, str], whitelist: Dict[str, str]) -> str:
    """Format QUANT_MAP as Python source code."""
    lines = [
        "# Auto-generated by generate_quant_map.py – do not edit manually.",
        "# Run 'python generate_quant_map.py --write' to update.",
        "# Source: lms ls --json + LM Studio configs + GGUF cache",
        "# Conflicts resolved: Steckbrief > Config > GGUF-Cache > Filename",
        "QUANT_MAP = {",
    ]
    # Sort by display name for readability
    sorted_items = sorted(quant_map.items(), key=lambda x: whitelist.get(x[0], x[0]))
    for mk, q in sorted_items:
        dn = whitelist.get(mk, mk)
        lines.append(f'    "{mk}": "{q}",  # {dn}')
    lines.append("}")
    return "\n".join(lines)


def main():
    write_mode = "--write" in sys.argv

    # Import whitelist from benchmark_config
    sys.path.insert(0, BASE_DIR)
    from benchmark_config import DISPLAY_NAMES, WHITELIST

    print("=" * 60)
    print("  QUANT_MAP Generator")
    print("=" * 60)
    print(f"  WHITELIST: {len(WHITELIST)} models")
    print()

    quant_map = build_quant_map(DISPLAY_NAMES)

    print(f"\n  Found quantization for {len(quant_map)}/{len(WHITELIST)} models")
    missing = [mk for mk in WHITELIST if mk not in quant_map]
    if missing:
        print(f"  Missing: {missing}")

    print()
    output = _format_quant_map(quant_map, DISPLAY_NAMES)

    if write_mode:
        config_path = os.path.join(BASE_DIR, "benchmark_config.py")
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Find and replace QUANT_MAP block
        # The QUANT_MAP block in benchmark_config.py starts with the auto-generated
        # comment and ends with the closing "}". We search for the comment markers
        # that are actually written by _format_quant_map().
        marker_start = "# Auto-generated by generate_quant_map.py"
        marker_end = "# Conflicts resolved: Steckbrief > Config > GGUF-Cache > Filename"
        # Find the QUANT_MAP = { ... } block
        quant_map_start = content.find("QUANT_MAP = {")
        quant_map_end = content.find("\n}", quant_map_start) + 2 if quant_map_start != -1 else -1

        if quant_map_start != -1 and quant_map_end != -1:
            # Also grab the comment block above QUANT_MAP
            comment_start = content.rfind("\n", 0, quant_map_start)
            if comment_start == -1:
                comment_start = 0
            else:
                comment_start += 1
            # Check if there's an auto-generated comment above
            if "# Auto-generated by generate_quant_map.py" in content[comment_start:quant_map_start]:
                start = comment_start
            else:
                start = quant_map_start
            content = content[:start] + output + "\n" + content[quant_map_end:]
        else:
            # Insert after DISPLAY_NAMES section
            insert_after = "WHITELIST = list(DISPLAY_NAMES.keys())"
            if insert_after in content:
                pos = content.index(insert_after) + len(insert_after)
                content = content[:pos] + "\n\n" + output + "\n" + content[pos:]
            else:
                content += "\n\n" + output + "\n"

        with open(config_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  Written to: {config_path}")
    else:
        print(output)


if __name__ == "__main__":
    main()
