#!/usr/bin/env python3
"""
Consolidated tool for model_registry.yaml and LM Studio JSON config maintenance.

Commands:
  compare       Compare registry vs LMS vs JSON configs (report only)
  add           Add LMS models to registry from piped JSON (lms ls --json | python registry_tool.py add)
  configs       Write load.fields (contextLength, offloadRatio, numParallelSessions,
                useUnifiedKvCache) into JSON configs (VRAM-aware formula)
  sync-ctx      Sync context_length from JSON configs into registry (only missing)
  sync-from-configs
                Sync offload, num_parallel, useUnifiedKvCache from JSON configs
                into registry (skips context_length to preserve native model limit)
  fill-arch     Read n_layers and hidden_dim from local GGUF headers for
                registry entries missing arch data
  fill-reasoning
                Read reasoning (thinking/instruct) from GGUF chat_template
                for registry entries without reasoning field
  fill-ctx      Add default context_length to entries missing it
                (size-based rule or 16384 fallback)
  fix-ctx       Recompute context_length for ALL entries (size-based formula)
  fix-np        Recompute num_parallel for ALL entries (architecture-based)
  fill-size     Look up file_size_bytes from LMS for registry entries missing it
  fmt           Normalize blank lines in registry YAML (no blanks within entries,
                one blank between entries)
  migrate-keys  Re-key entries without publisher prefix to publisher/model-name
  rm            Remove registry entry (optionally delete files + configs too):
                python registry_tool.py rm <model-key> [--delete-files] [--yes]
  validate      Check model_registry.yaml consistency: template files exist,
                Config JSON promptTemplate matches YAML, override overlap,
                required fields present, etc.
  sync          Full sync: add → fill-arch → fill-reasoning → configs → sync-ctx →
                sync-from-configs → fill-ctx → fmt
"""

from __future__ import annotations

import csv, json, os, re, shutil, struct, sys, subprocess, tempfile, concurrent.futures
from pathlib import Path
from collections import OrderedDict
from typing import Any, Callable

_SRC_DIR = Path(__file__).resolve().parent
# Make `src` importable regardless of how the tool is invoked
# (python -m src.registry_tool from the repo root puts only the CWD
# on sys.path, not `src/`). Fix for Code-Review_2026-08-03.md F4.
sys.path.insert(0, str(_SRC_DIR))

from utils.terminal import ok, warn, error
from type_defs import RegistryEntry

PROJECT_ROOT = _SRC_DIR.parent
REGISTRY_PATH = PROJECT_ROOT / "doc-git" / "model_registry.yaml"
CONFIG_ROOT = Path.home() / ".lmstudio" / ".internal" / "user-concrete-model-default-config"

# ── ruamel.yaml setup ──────────────────────────────────────────────
from ruamel.yaml import YAML
y = YAML()
y.preserve_quotes = True
y.indent(mapping=2, sequence=4, offset=2)

# ── assemble_blueprint helpers ─────────────────────────────────────
from assemble_blueprint import (
    normalize_model_name, normalize_for_config, find_config_for_registry_key,
    find_all_configs_for_registry_key, find_registry_key_for_config,
    read_lms_configs, _ARCH_REASONING_MAP,
    classify_registry, create_blueprint_definitions,
    assemble_prompts, validate_prompts,
)
from benchmark_config import (
    BLACKLIST,
    is_support_file,
    USABLE_VRAM_GB as _USABLE_VRAM_GB,
    USE_UNIFIED_KV_CACHE_THRESHOLD_GB as _USE_UNIFIED_KV_CACHE_THRESHOLD_GB,
    LEGACY_MODEL_GB_THRESHOLD_GB as _LEGACY_MODEL_GB_THRESHOLD_GB,
    MIN_CONTEXT_LENGTH as _MIN_CONTEXT_LENGTH,
)


# ── I/O helpers ────────────────────────────────────────────────────

def load_registry(path: Path | None = None) -> dict[str, RegistryEntry]:
    if path is None:
        path = REGISTRY_PATH
    with open(path, "r", encoding="utf-8") as f:
        return y.load(f) or {}


def _normalize_quants_flow_style(path: Path) -> None:
    """Convert block-style quants (multiline list) to flow-style [item] inline."""
    content = path.read_text("utf-8")
    new, n = re.subn(r'  quants:\n    - (\S+)', r'  quants: [\1]', content)
    if n:
        path.write_text(new, "utf-8")


def save_registry(reg: dict[str, Any], path: Path | None = None) -> None:
    if path is None:
        path = REGISTRY_PATH
    with open(path, "w", encoding="utf-8") as f:
        y.dump(reg, f)
    _format_blank_lines(path)
    _normalize_quants_flow_style(path)


def load_lms_json(path: str | Path) -> list[Any]:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def _run_lms_ls() -> list[dict[str, Any]]:
    try:
        r = subprocess.run(["lms", "ls", "--json"], capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            data = json.loads(r.stdout)
            return data if isinstance(data, list) else list(data.values())
        stderr = r.stderr.strip()
    except FileNotFoundError:
        stderr = "lms.exe not found"
    except subprocess.TimeoutExpired:
        stderr = "lms ls timed out"

    print(f"[INFO] lms ls fehlgeschlagen ({stderr}) – versuche Server-Start...")
    try:
        from model_manager import _is_lmstudio_running
        if _is_lmstudio_running():
            r = subprocess.run(["lms", "ls", "--json"], capture_output=True, text=True, timeout=15)
            if r.returncode == 0:
                data = json.loads(r.stdout)
                return data if isinstance(data, list) else list(data.values())
    except Exception as e:
        print(f"[WARN] Server-Start fehlgeschlagen: {e}")

    print(f"[WARN] lms ls auch nach Server-Start fehlgeschlagen")
    return []


# ── Blank-line formatting ──────────────────────────────────────────

def _format_blank_lines(path: Path) -> None:
    """Normalize blank lines in YAML: none within entries, one between entries."""
    with open(path, "r", encoding="utf-8", newline="") as f:
        content = f.read()
    lines = content.splitlines()

    def is_top_key(s: str) -> bool:
        s = s.rstrip()
        if not s or not s.endswith(":"):
            return False
        if s.startswith(" ") or s.startswith("\t"):
            return False
        return True

    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if is_top_key(line):
            if out and out[-1] != "" and out[-1].strip() != "":
                out.append("")
            out.append(line)
            i += 1
            while i < len(lines) and not is_top_key(lines[i]):
                if lines[i].strip() == "":
                    i += 1
                    continue
                out.append(lines[i])
                i += 1
        elif line.strip() == "" and out:
            if out[-1] != "":
                out.append("")
            i += 1
        else:
            out.append(line)
            i += 1
    while out and out[-1] == "":
        out.pop()
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(out) + "\n")


# ── fmt command ────────────────────────────────────────────────────

def cmd_fmt() -> None:
    _format_blank_lines(REGISTRY_PATH)
    print(f"[OK] Blank lines formatted in {REGISTRY_PATH.name}")


# ── fill-ctx command ───────────────────────────────────────────────

def cmd_fill_ctx(default: int = 16384) -> None:
    reg = load_registry()
    updated = 0
    for entry in reg.values():
        if not isinstance(entry, dict):
            continue
        if "context_length" in entry and entry["context_length"] is not None:
            continue
        size_bytes = entry.get("file_size_bytes")
        if size_bytes and size_bytes > 0:
            np_val = entry.get("num_parallel", 1)
            kc = entry.get("k_cache", "q8_0")
            vc = entry.get("v_cache", "iq4_nl")
            entry["context_length"] = _default_ctx_from_size(int(size_bytes), np_val, kc, vc)
        else:
            entry["context_length"] = default
        updated += 1
    if updated:
        save_registry(reg)
    print(f"[OK] {updated} entries got context_length")


# ── fix-ctx command ──────────────────────────────────────────────

def cmd_fix_ctx() -> None:
    """Recompute context_length for ALL entries based on current np and KV-cache settings."""
    reg = load_registry()
    updated = 0
    for entry in reg.values():
        if not isinstance(entry, dict):
            continue
        sb = entry.get("file_size_bytes")
        if sb and sb > 0:
            np_val = entry.get("num_parallel", 1)
            kc = entry.get("k_cache", "q8_0")
            vc = entry.get("v_cache", "iq4_nl")
            new_ctx = _default_ctx_from_size(int(sb), np_val, kc, vc)
            if entry.get("context_length") != new_ctx:
                entry["context_length"] = new_ctx
                updated += 1
    if updated:
        save_registry(reg)
    print(f"[OK] {updated} entries updated context_length")


# ── fill-size command ──────────────────────────────────────────────

def cmd_fill_size() -> None:
    """Look up file_size_bytes from LMS for registry entries missing it."""
    reg = load_registry()
    lms_models = _run_lms_ls()
    if not lms_models:
        print("[WARN] LMS nicht verfuegbar. Keine Aenderungen.")
        return
    # Build LMS lookup: normalized name -> sizeBytes
    lms_sizes: dict[str, int] = {}
    for m in lms_models:
        normalized_key = normalize_model_name(m.get("modelKey", ""))
        sb = m.get("sizeBytes", 0)
        if sb and sb > 0:
            if normalized_key not in lms_sizes:
                lms_sizes[normalized_key] = int(sb)
    updated = 0
    for key, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        if "file_size_bytes" in entry and entry["file_size_bytes"]:
            continue
        normalized_key = normalize_model_name(key)
        if normalized_key in lms_sizes:
            entry["file_size_bytes"] = lms_sizes[normalized_key]
            updated += 1
    if updated:
        save_registry(reg)
    print(f"[OK] {updated} entries got file_size_bytes from LMS")


_GGUF_FILE_CACHE: list[Path] | None = None


def _get_all_ggufs() -> list[Path]:
    """Return (and cache) all ``.gguf`` files under ``MODELS_CACHE``."""
    global _GGUF_FILE_CACHE
    if _GGUF_FILE_CACHE is None:
        _GGUF_FILE_CACHE = sorted(MODELS_CACHE.rglob("*.gguf"))
    return _GGUF_FILE_CACHE


def _norm(s: str) -> str:
    """Lower-case, strip ``.gguf``, replace ``-``/``_``/``\\``/``/``/``@`` with space."""
    s = s.lower().replace(".gguf", "").replace("-", " ").replace("_", " ").replace("\\", " ").replace("/", " ").replace("@", " ")
    return " ".join(s.split())


# Zentralisiert in benchmark_config.py (Code-Review 2026-08-03 §F1):
# wird identisch von model_manager.get_available_models() genutzt.
_is_support_file = is_support_file


def _significant_words(s: str) -> set[str]:
    """Split *s* into lower-case words, keep only ≥3-char tokens."""
    return {w for w in _norm(s).split() if len(w) >= 3}


def _resolve_model_path_multi(key: str) -> str:
    """Resolve GGUF path — exact substring match first, then word-match fallback.

    1. Exact ``MODELS_CACHE / key`` — library-level path from LM Studio.
    2. Substring match (normalised key suffix in normalised GGUF path).
    3. Word-match fallback (at least 2 significant words in common).
    Returns ``""`` if nothing suitable is found.
    """
    candidate = MODELS_CACHE / key
    if candidate.is_file():
        return str(candidate)

    suffix = key.split("/", 1)[1] if "/" in key else key
    sn = _norm(suffix)

    # 2) Substring match
    for g in _get_all_ggufs():
        if _is_support_file(g):
            continue
        if sn in _norm(str(g.relative_to(MODELS_CACHE))):
            return str(g)

    # 3) Word-match fallback — require ≥ 2 significant words in common
    sw = _significant_words(suffix)
    if len(sw) < 2:
        return ""
    best: tuple[int, str] = (0, "")
    for g in _get_all_ggufs():
        if _is_support_file(g):
            continue
        gw = _significant_words(str(g.relative_to(MODELS_CACHE)))
        match = len(sw & gw)
        if match >= 2 and match > best[0]:
            best = (match, str(g))
    return best[1]


# ── fix-np command ─────────────────────────────────────────────────

def _normalize_variants(key: str) -> set[str]:
    """All normalized spellings of a model key.

    Covers publisher prefixes (``unsloth/x`` vs ``x`` vs ``unsloth_x``),
    quant suffixes are stripped via the ``@`` split. Only used for
    **exact** comparisons, never for fuzzy word matching.
    """
    base = key.split("@", 1)[0]
    variants = {normalize_model_name(base)}
    if "/" in base:
        variants.add(normalize_model_name(base.split("/", 1)[1]))
    if "_" in base:
        variants.add(normalize_model_name(base.replace("_", "-")))
    return variants


def _quant_variant(key: str) -> str:
    """Normalized spelling of a quant-suffixed key (``...@q5_0`` → ``...@q5-0``).

    Keeps the quant, so keys with different quantizations stay distinct.
    """
    return normalize_model_name(key)


def _resolve_exact(reg_key: str, lms_path_map: dict[str, str]) -> str:
    """Exact-only path resolution (library-level, lms map, substring).

    Deliberately **no** word-match fallback: only identical files may
    end up in the same duplicate-collapse group.
    """
    candidate = MODELS_CACHE / reg_key
    if candidate.is_file():
        return str(candidate)
    for probe in (reg_key.lower(), normalize_model_name(reg_key)):
        mp = lms_path_map.get(probe, "")
        if mp and os.path.isfile(mp):
            return mp
    if "/" in reg_key:
        suffix = reg_key.split("/", 1)[1].lower()
        for probe in (suffix, normalize_model_name(suffix)):
            mp = lms_path_map.get(probe, "")
            if mp and os.path.isfile(mp):
                return mp
    sn = _norm(reg_key.split("/", 1)[1] if "/" in reg_key else reg_key)
    for g in _get_all_ggufs():
        if _is_support_file(g):
            continue
        if sn in _norm(str(g.relative_to(MODELS_CACHE))):
            return str(g)
    return ""


def cmd_fix_np() -> None:
    """Recompute arch classification + num_parallel, remove stale entries.

    - Reads ``expert_count`` from GGUF header as single source of truth
      for MoE detection.
    - Drops entries that have **neither** an exactly matching ``lms``
      entry **nor** a GGUF file on disk (stale / uninstalled models).
    - Collapses duplicate registry entries that resolve to the same
      installed model, keeping the best-matching key. This only runs
      when ``lms ls`` returned data — without it, resolution would
      degrade to fuzzy word matching and legit entries (e.g. quant
      variants) could be collapsed into each other.
    """
    reg = load_registry()
    lms_models = _run_lms_ls()
    if not lms_models:
        print("[WARN] lms ls lieferte keine Daten – Duplikat-Kollaps übersprungen, nur Phantome werden gelöscht.")

    # ── build lookup maps from lms ls ──
    lms_path_map: dict[str, str] = {}
    lms_variants: dict[str, str] = {}   # normalized variant → lms key
    lms_quant: dict[str, str] = {}      # normalized quant form → lms key
    lms_file_map: dict[str, str] = {}   # normcased file path → lms key
    for m in lms_models:
        mk = str(m.get("modelKey", "")).lower()
        rp = m.get("path", "")
        full_path = str(MODELS_CACHE / rp) if rp else ""
        lms_path_map[mk] = full_path
        lms_path_map[normalize_model_name(mk)] = full_path
        for i, ch in enumerate(mk):
            if ch == "/":
                lms_path_map[mk[i+1:]] = full_path
                lms_path_map[normalize_model_name(mk[i+1:])] = full_path
                break
        for variant in _normalize_variants(mk):
            lms_variants.setdefault(variant, mk)
        if "@" in mk:
            lms_quant.setdefault(_quant_variant(mk), mk)
        if full_path and os.path.isfile(full_path):
            lms_file_map.setdefault(os.path.normcase(full_path), mk)

    def _exact_lms_match(reg_key: str) -> str | None:
        """Return the lms key whose normalized form **exactly** matches a
        normalized spelling of the registry key (no word-substring fuzz).

        Quant-suffixed keys compare with their quant form first, so
        ``x@q5_0`` only matches ``x@q5_0``, not ``x@q6_k``.
        """
        if "@" in reg_key:
            lmk = lms_quant.get(_quant_variant(reg_key))
            if lmk is not None:
                return lmk
        for variant in _normalize_variants(reg_key):
            lmk = lms_variants.get(variant)
            if lmk is not None:
                return lmk
        return None

    def _resolve_path(reg_key: str) -> str:
        model_path = lms_path_map.get(reg_key.lower()) or lms_path_map.get(normalize_model_name(reg_key), "")
        if "/" in reg_key:
            suffix = reg_key.split("/", 1)[1].lower()
            mp = lms_path_map.get(suffix) or lms_path_map.get(normalize_model_name(suffix), "")
            if mp:
                model_path = mp
        if not model_path or not os.path.isfile(model_path):
            found = _resolve_model_path_multi(reg_key)
            if found:
                model_path = found
        return model_path

    updated = 0
    removed = 0
    keys = list(reg.keys())  # snapshot to allow deletion during iteration

    # ── pass 1: drop phantoms, group survivors by resolved target ──
    groups: dict[str, list[tuple[str, int, int]]] = {}  # target id → [(key, score, idx)]
    for idx, key in enumerate(keys):
        entry = reg[key]
        if not isinstance(entry, dict):
            continue
        lmk = _exact_lms_match(key)
        exact = _resolve_exact(key, lms_path_map) if lmk is None else ""
        has_file = bool(exact)

        # ── remove stale entries (no exact lms match + no GGUF) ──
        if lmk is None and not has_file:
            del reg[key]
            removed += 1
            print(f"  {key}: gelöscht (nicht installiert)")
            continue

        if lmk is not None:
            gid = "lms:" + lmk
            score = 2
            pub = key.split("/", 1)[0].lower() if "/" in key else ""
            if pub and pub in lmk:
                score += 1
        elif lms_models:
            if os.path.normcase(exact) in lms_file_map:
                gid = "lms:" + lms_file_map[os.path.normcase(exact)]
                score = 0
            else:
                gid = "file:" + os.path.normcase(exact)
                score = 0
        else:
            # no lms data → keep every survivor isolated (no collapse)
            gid = "key:" + key
            score = 0
        groups.setdefault(gid, []).append((key, score, idx))

    # ── pass 2: collapse duplicates per target, keep best match ──
    for gid, members in groups.items():
        if len(members) < 2:
            continue
        members.sort(key=lambda t: (-t[1], t[2]))
        keeper = members[0][0]
        for key, _, _ in members[1:]:
            del reg[key]
            removed += 1
            print(f"  {key}: gelöscht (Duplikat von {keeper})")

    # ── pass 3: reclassify survivors ──
    for key in list(reg.keys()):
        entry = reg[key]
        if not isinstance(entry, dict):
            continue
        model_path = _resolve_path(key)
        classification = _classify_arch(key, model_path)
        old_arch = entry.get("arch", "")
        old_np = entry.get("num_parallel")
        new_np = _infer_num_parallel(classification)
        changed = (classification != old_arch) or (new_np != old_np)
        entry["arch"] = classification
        entry["num_parallel"] = new_np
        if changed:
            updated += 1
            print(f"  {key}: arch {old_arch}→{classification}, np {old_np}→{new_np}")

    if updated or removed:
        save_registry(reg)
    print(f"[OK] {updated} aktualisiert, {removed} gelöscht")


# ── compare command ────────────────────────────────────────────────

def cmd_compare() -> dict[str, Any]:
    reg = load_registry()
    lms = _run_lms_ls()
    cfgs = read_lms_configs(CONFIG_ROOT)

    registry_key_map = {normalize_model_name(k): k for k, v in reg.items() if isinstance(v, dict)}
    lm = {normalize_model_name(m.get("modelKey", "")): m for m in lms}
    ck = {normalize_model_name(c["dir_name"]) for c in cfgs}

    new_models: list[dict] = []
    for lk, lm2 in sorted(lm.items()):
        if not any(lk == r for r in registry_key_map):
            new_models.append(lm2)

    missing: list[str] = []
    for rn, re_ in reg.items():
        if not isinstance(re_, dict) or re_.get("blueprint") == "none":
            continue
        rk2 = normalize_model_name(rn)
        if not any(rk2 in l or l in rk2 for l in lm):
            missing.append(rn)

    orphan: set[str] = set()
    for c in cfgs:
        n = normalize_model_name(c["dir_name"])
        if not any(n in r or r in n for r in registry_key_map):
            orphan.add(f"{c['publisher']}/{c['dir_name']}")

    report = {
        "lms": len(lms),
        "reg": len(registry_key_map),
        "cfg": len(cfgs),
        "new": len(new_models),
        "missing": len(missing),
        "orphan": len(orphan),
        "newd": [{
            "key": m.get("modelKey", "?"),
            "publisher": m.get("publisher", "?"),
            "arch": m.get("architecture", "?"),
            "params": m.get("paramsString", "?"),
            "ctx": m.get("maxContextLength", 0),
            "vision": m.get("vision", False),
            "tools": m.get("trainedForToolUse", False),
            "size_bytes": m.get("sizeBytes", 0),
        } for m in new_models[:20]],
        "missd": missing[:20],
        "orphd": sorted(orphan)[:20],
    }

    print(json.dumps(report, ensure_ascii=False, default=str))
    return report


# ── np inference helper ────────────────────────────────────────────

def _classify_arch(
    model_identifier: str = "",
    model_path: str = "",
) -> str:
    """Classify a model as ``"moe"``, ``"mtp"``, or ``"dense"``.

    Uses GGUF header (``expert_count``) as single source of truth for MoE.
    Falls back to ``"mtp"`` keyword in the model identifier.
    Everything else → ``"dense"``.
    """
    kl = model_identifier.lower()

    if model_path and os.path.isfile(model_path) and _gguf_has_experts(model_path):
        return "moe"
    if "mtp" in kl:
        return "mtp"
    return "dense"


def _infer_num_parallel(classification: str) -> int:
    """Determine num_parallel from a classification string.

    ``"moe"`` / ``"mtp"`` → 4, everything else → 1.
    """
    return 4 if classification in ("moe", "mtp") else 1


def _compute_np_ukv(model_gb: float, kv_per_slot_gb: float, native_ctx: int,
                     vram_available: float = _USABLE_VRAM_GB,
                     min_ctx: int = _MIN_CONTEXT_LENGTH) -> tuple[int, bool, int]:
    """Compute optimal num_parallel and useUnifiedKvCache based on VRAM budget.

    Priority (user-defined, 05.08.2026):
      1. np=4, UKV=False  →  max GPU parallelism
      2. np=4, UKV=True   →  save VRAM (np does not scale KV)
      3. np=2, UKV=True   →  reduce KV overhead further
      4. np=1, UKV=True   →  minimum parallelism
      5. np=1, UKV=False  →  last resort (reduce ctx)

    Args:
        model_gb: Model file size in GB.
        kv_per_slot_gb: KV-cache cost per slot (nl × hd × 2 × kv_bytes / 1e9).
        native_ctx: Native max context length from GGUF header.
        vram_available: Usable VRAM in GB (default: 15.3).
        min_ctx: Minimum acceptable context length (default: 32768).

    Returns:
        (num_parallel, use_unified_kv_cache, context_length)
    """
    if kv_per_slot_gb <= 0:
        # No arch data → fallback: np=4, UKV based on model size, native ctx
        is_ukv = model_gb >= _LEGACY_MODEL_GB_THRESHOLD_GB
        return 4, is_ukv, native_ctx

    # Estimate max ctx from VRAM (for models without max_context_length in registry)
    # Use np=1, UKV=True as baseline for max possible ctx
    max_possible_ctx = int(vram_available / (kv_per_slot_gb / 1e9)) if kv_per_slot_gb > 0 else native_ctx
    effective_native_ctx = min(native_ctx, max_possible_ctx)

    for np_val, ukv in [(4, False), (4, True), (2, True), (1, True), (1, False)]:
        np_factor = 1 if ukv else np_val
        # Max ctx for this np/UKV combination
        max_ctx_for_config = int(vram_available / (kv_per_slot_gb * np_factor / 1e9))
        ctx = min(effective_native_ctx, max_ctx_for_config)
        if ctx >= min_ctx:
            return np_val, ukv, ctx

    # Fallback: np=1, UKV=False, ctx=min_ctx
    return 1, False, min_ctx


# ── add command ────────────────────────────────────────────────────

def cmd_add(models: list[dict[str, Any]], interactive: bool = False) -> dict[str, Any]:
    reg = load_registry()
    added: list[str] = []
    skipped: list[tuple[str, str]] = []

    for m in models:
        mk = str(m.get("key") or m.get("modelKey") or "").strip()
        if not mk:
            skipped.append(("?", "leerer Key"))
            continue
        pub = str(m.get("publisher", "unknown")).strip()
        canonical = _canonical_key(mk, pub)
        sk = normalize_model_name(mk)
        if any(sk == normalize_model_name(k) for k in reg):
            skipped.append((mk, "bereits vorhanden"))
            continue
        if any(kw in mk.lower() for kw in BLACKLIST):
            skipped.append((mk, "blacklisted"))
            continue
        rp = m.get("path", "")
        if rp and _is_support_file(rp, str(m.get("architecture") or "")):
            skipped.append((mk, "Zusatzdatei (MTP-Drafter/mmproj) - kein eigenständiges Modell"))
            continue
        model_path = ""
        rp = m.get("path", "")
        if rp:
            mp_candidate = str(MODELS_CACHE / rp)
            if os.path.isfile(mp_candidate):
                model_path = mp_candidate
        classification = _classify_arch(mk, model_path)
        nt = f"Architektur: {classification}"
        if classification == "mtp":
            nt += " | Multi-Token Prediction"
        if m.get("params"):
            nt += f" | {m['params']} Parameter"
        if m.get("vision"):
            nt += " | Vision"
        if m.get("tools"):
            nt += " | Tool-Use"
        num_p = _infer_num_parallel(classification)
        size_bytes = m.get("size_bytes", 0) or m.get("sizeBytes", 0)
        entry = {
            "publisher": pub,
            "hf_url": f"https://huggingface.co/{canonical}",
            "arch": classification,
            "k_cache": "q8_0",
            "v_cache": "iq4_nl",
            "offload": 1,
            "num_parallel": num_p,
            "notes": nt,
        }
        if size_bytes and size_bytes > 0:
            entry["file_size_bytes"] = int(size_bytes)
            entry["context_length"] = _default_ctx_from_size(
                int(size_bytes), num_p,
                entry["k_cache"], entry["v_cache"]
            )

        # Auto-fill arch data from GGUF file if available
        model_path = m.get("path", "")
        if model_path:
            full_path = str(MODELS_CACHE / model_path)
            if os.path.isfile(full_path):
                nl, hd, is_reasoning, ctx = _read_gguf_arch(full_path)
                if nl and hd:
                    entry["n_layers"] = int(nl)
                    entry["hidden_dim"] = int(hd)
                if ctx is not None:
                    entry["max_context_length"] = int(ctx)
                if is_reasoning is not None:
                    entry["reasoning"] = "thinking" if is_reasoning else "instruct"

        # Interactive reasoning prompt (fallback: no GGUF data available)
        if "reasoning" not in entry and interactive:
            print(f"\n  Modell: {mk}")
            print(f"  Architektur: {classification}")
            print(f"  Keine GGUF-Datei gefunden – Reasoning-Typ kann nicht automatisch erkannt werden.")
            ans = input("  Reasoning-Typ? [i]nstruct / [t]hinking / [n]one / (d=instruct): ").strip().lower()
            if ans in ("t", "thinking"):
                entry["reasoning"] = "thinking"
            elif ans in ("n", "none"):
                entry["reasoning"] = "none"
            else:
                entry["reasoning"] = "instruct"

        reg[canonical] = entry
        added.append(canonical)

    if added:
        save_registry(reg)

    result = {"added": added, "skipped": skipped}
    print(json.dumps(result, ensure_ascii=False))
    return result


# ── configs command ────────────────────────────────────────────────

def cmd_configs() -> dict[str, Any]:
    reg = load_registry()
    cfgs = read_lms_configs(CONFIG_ROOT)
    registry_key_map = {normalize_model_name(k): k for k, v in reg.items() if isinstance(v, dict)}
    # Sort by descending normalized key length: more specific keys match first
    registry_key_sorted = sorted(registry_key_map.items(), key=lambda x: -len(x[0]))

    updated = skipped = blacklisted = errors = 0
    for cfg in cfgs:
        cn = normalize_model_name(cfg["dir_name"])
        match = None
        # Phase 1: exact match
        for rn2, rnk in registry_key_sorted:
            if cn == rn2:
                match = rnk
                break
        # Phase 2: config name has extra quantization suffix (e.g. -mxfp4, -Q3_K_M)
        if not match:
            for rn2, rnk in registry_key_sorted:
                if cn.startswith(rn2 + '-'):
                    match = rnk
                    break
        # Phase 3: config name stripped publisher that is embedded in registry key
        if not match:
            for rn2, rnk in registry_key_sorted:
                if rn2.endswith('-' + cn):
                    match = rnk
                    break
        if not match:
            skipped += 1
            continue
        if any(kw in match.lower() for kw in BLACKLIST):
            blacklisted += 1
            continue
        entry = reg[match]
        json_path = cfg["json_path"]
        try:
            with open(json_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            load_section = data.setdefault("load", {})
            fields = load_section.get("fields")
            if fields is None:
                fields = []
                load_section["fields"] = fields
            fidx = {f.get("key"): i for i, f in enumerate(fields) if isinstance(f, dict)}

            def set_field(key, value):
                if key in fidx:
                    fields[fidx[key]]["value"] = value
                else:
                    fields.append({"key": key, "value": value})
                    fidx[key] = len(fields) - 1

            if "offload" in entry:
                set_field("llm.load.llama.acceleration.offloadRatio", entry["offload"])

            # ── Priority-based np/UKV computation (05.08.2026) ──
            # Priority: np=4/UKV=F → np=4/UKV=T → np=2/UKV=T → np=1/UKV=T → np=1/UKV=F
            fs = entry.get("file_size_bytes", 0)
            nl = entry.get("n_layers")
            hd = entry.get("hidden_dim")
            kc = entry.get("k_cache", "q8_0")
            vc = entry.get("v_cache", "iq4_nl")
            kv_bytes = _KV_BYTES.get(kc, 1.0) + _KV_BYTES.get(vc, 0.5)
            model_gb = fs / 1_000_000_000 if fs else 0

            kv_per_slot_gb = 0.0
            if nl and hd and model_gb > 0:
                kv_per_slot_gb = nl * hd * 2 * kv_bytes / 1e9

            # native_ctx from GGUF header (registry max_context_length)
            native_ctx = entry.get("max_context_length") or 262144  # fallback: 256k

            # current_ctx from JSON config (llm.load.contextLength)
            current_ctx = None
            for field in fields:
                if isinstance(field, dict) and field.get("key") == "llm.load.contextLength":
                    current_ctx = field.get("value")
                    break

            np_new, ukv_new, ctx_new = _compute_np_ukv(
                model_gb, kv_per_slot_gb, native_ctx,
                vram_available=_USABLE_VRAM_GB,
                min_ctx=_MIN_CONTEXT_LENGTH,
            )

            # Only update if values changed
            old_np = entry.get("num_parallel")
            old_ukv = entry.get("useUnifiedKvCache")

            set_field("llm.load.numParallelSessions", np_new)
            set_field("llm.load.useUnifiedKvCache", ukv_new)

            # Also update registry entry in-memory for sync-from-configs
            entry["num_parallel"] = np_new
            entry["useUnifiedKvCache"] = ukv_new

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            updated += 1
        except (OSError, ValueError, KeyError, TypeError) as e:
            print(f"  [WARN] cmd_configs Fehler fuer {label}: {e}", file=sys.stderr)
            errors += 1

    result = {"updated": updated, "skipped": skipped, "blacklisted": blacklisted, "errors": errors}
    print(json.dumps(result, ensure_ascii=False))
    return result


# ── rm command (NEW 2026-07-31) ───────────────────────────────────

def cmd_rm(model_key: str, delete_files: bool = False, assume_yes: bool = False) -> int:
    """Remove a model entry from the registry.

    Optionally (--delete-files) also removes:
      - LM Studio JSON config(s) incl. .bak-* backups
      - the model files under ~/.lmstudio/hub/models/<publisher>/<name>

    Returns 0 on success, 1 on error/abort.
    """
    reg = load_registry()
    target = normalize_model_name(model_key)
    matches = [
        k for k, v in reg.items()
        if isinstance(v, dict)
        and (normalize_model_name(k) == target
             or normalize_model_name(k).endswith("-" + target))
    ]
    if not matches:
        print(f"[ERROR] Kein Registry-Eintrag gefunden für: {model_key} (normalisiert: {target})")
        return 1
    if len(matches) > 1:
        print(f"[ERROR] Mehrdeutig – mehrere Einträge matchen: {matches}")
        return 1
    key = matches[0]

    configs = read_lms_configs(CONFIG_ROOT)
    cfg_paths = [c["json_path"] for c in find_all_configs_for_registry_key(key, configs)]
    hub_dir = Path.home() / ".lmstudio" / "hub" / "models" / Path(*key.split("/"))
    models_dir = Path.home() / ".lmstudio" / "models" / Path(*key.split("/"))
    model_dirs = [d for d in (hub_dir, models_dir) if d.exists()]

    print(f"  Registry-Eintrag : {key}")
    if cfg_paths:
        for p in cfg_paths:
            print(f"  JSON-Config      : {p}")
    else:
        print("  JSON-Config      : (keine gefunden)")
    if delete_files:
        if model_dirs:
            for d in model_dirs:
                size_gb = sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / 1e9
                print(f"  Modell-Dateien   : {d} ({size_gb:.2f} GB)")
        else:
            print(f"  Modell-Dateien   : (nicht gefunden unter {hub_dir} / {models_dir})")

    if not assume_yes:
        answer = input("  Wirklich löschen? [y/N] ").strip().lower()
        if answer != "y":
            print("[OK] Abgebrochen – nichts gelöscht.")
            return 0

    del reg[key]
    save_registry(reg)
    print(f"[OK] Registry-Eintrag gelöscht: {key}")

    if delete_files:
        for p in cfg_paths:
            path = Path(p)
            for bak in sorted(path.parent.glob(path.name + ".bak-*")):
                bak.unlink()
                print(f"  [rm] Backup gelöscht: {bak}")
            path.unlink()
            print(f"  [rm] Config gelöscht: {path}")
        if model_dirs:
            for d in model_dirs:
                shutil.rmtree(d)
                print(f"  [rm] Modell-Dateien gelöscht: {d}")
    else:
        print("  [INFO] Dateien belassen. Mit --delete-files auch Dateien löschen.")
    return 0


# ── sync-from-configs command ────────────────────────────────────

def cmd_sync_from_configs() -> None:
    """Sync offload, num_parallel, useUnifiedKvCache from JSON configs into registry (skips context_length to preserve native model limit)."""
    if not REGISTRY_PATH.exists():
        print(f"[ERROR] Registry not found: {REGISTRY_PATH}")
        sys.exit(1)

    print("[1] Registry laden ...")
    reg = load_registry()
    if not reg:
        print("[ERROR] Leere Registry")
        sys.exit(1)

    print("[2] JSON-Configs scannen ...")
    configs = read_lms_configs(CONFIG_ROOT)
    print(f"  -> {len(configs)} Config-Dateien gefunden")

    registry_key_map = {normalize_model_name(k): k for k, v in reg.items() if isinstance(v, dict)}
    registry_key_sorted = sorted(registry_key_map.items(), key=lambda x: -len(x[0]))

    print("[3] Registry-Einträge aktualisieren ...")
    updated_offload = updated_np = updated_ukv = 0
    skipped_no_match = 0
    blacklisted = 0
    for cfg in configs:
        cn = normalize_model_name(cfg["dir_name"])
        match = find_registry_key_for_config(cn, registry_key_sorted)
        if not match:
            skipped_no_match += 1
            continue
        if any(kw in match.lower() for kw in BLACKLIST):
            blacklisted += 1
            continue
        entry = reg[match]
        if not isinstance(entry, dict):
            continue

        off = cfg.get("offload")
        if off is not None:
            entry["offload"] = float(off)
            updated_offload += 1

        np_val = cfg.get("num_parallel")
        if np_val is not None:
            entry["num_parallel"] = int(np_val)
            updated_np += 1

        ukv = cfg.get("use_unified_kv")
        if ukv is not None:
            entry["useUnifiedKvCache"] = bool(ukv)
            updated_ukv += 1

    print(f"  -> offload:          {updated_offload} aktualisiert")
    print(f"  -> num_parallel:     {updated_np} aktualisiert")
    print(f"  -> useUnifiedKvCache:{updated_ukv} aktualisiert (context_length uebersprungen)")
    print(f"  -> kein Match:       {skipped_no_match} uebersprungen")
    print(f"  -> blacklisted:      {blacklisted} uebersprungen")

    if updated_offload or updated_np or updated_ukv:
        save_registry(reg)
    print(f"[OK] sync-from-configs: offload {updated_offload}, np {updated_np}, ukv {updated_ukv} aktualisiert ({skipped_no_match} kein Match, {blacklisted} blacklisted)")


# ── sync-ctx command ───────────────────────────────────────────────

def _strip_quant(norm_key: str) -> str:
    idx = norm_key.find('@')
    return norm_key[:idx] if idx > 0 else norm_key


_CTX_FROM_SIZE: list[tuple[float, int]] = [
    (14, 16384),
    (13, 32768),
    (12, 49152),
    (11, 65536),
    (10, 98304),
    (9, 131072),
]

# Bytes per KV-cache element per quantization type.
# Read-only after init — treat as immutable (thread-safe by design).
_KV_BYTES: dict[str, float] = {
    "q8_0": 1.0, "q8_1": 2.0,
    "q5_1": 0.625, "q5_l": 0.625,
    "iq4_nl": 0.5,
    "q4_0": 0.5, "q4_1": 0.625,
    "f16": 2.0,
}


def _default_ctx_from_size(size_bytes: int, np: int = 1,
                           k_cache: str = "q8_0", v_cache: str = "iq4_nl") -> int:
    gb = size_bytes / 1_000_000_000
    for limit, ctx in _CTX_FROM_SIZE:
        if gb > limit:
            base_ctx = ctx
            break
    else:
        base_ctx = 262144

    if np == 1:
        return base_ctx

    # Scale: np factor × KV-quantization correction
    # Baseline: 1.5 B/element (q8_0 + iq4_nl, the most common case)
    kv_ref = 1.5
    kv_actual = _KV_BYTES.get(k_cache, 2.0) + _KV_BYTES.get(v_cache, 2.0)
    scale = (kv_ref / kv_actual) / np
    return max(8192, int(base_ctx * scale))


# _USABLE_VRAM_GB is now imported from benchmark_config at the top of
# this file (Code-Review 2026-07-18 §5.1: single source of truth for
# VRAM constants).


def _max_ctx_from_vram(model_gb: float, np_val: int, nl: int, hd: int,
                       kv_bytes: float) -> int:
    """Maximum context length that fits in usable VRAM.

    Formula:  ctx = (usable_vram - model_gb) / (np × nl × hd × 2 × kv_bytes / 1e9)
    """
    kv_gb_per_token = np_val * nl * hd * 2 * kv_bytes / 1_000_000_000
    if kv_gb_per_token <= 0:
        return 2048
    ctx = (_USABLE_VRAM_GB - model_gb) / kv_gb_per_token
    return max(2048, int(ctx))


def _canonical_key(mk: str, pub: str) -> str:
    """Build canonical registry key: publisher/model-name (cleaned)."""
    s = mk.strip().lower()
    s = re.sub(r'\.gguf$', '', s)
    s = re.sub(r'-(gguf|mxpr4)$', '', s)
    if "/" not in s:
        s = f"{pub.lower().strip()}/{s}"
    return s


def cmd_sync_ctx() -> None:
    if not REGISTRY_PATH.exists():
        print(f"[ERROR] Registry not found: {REGISTRY_PATH}")
        sys.exit(1)

    print("[1] Registry laden ...")
    reg = load_registry()
    if not reg:
        print("[ERROR] Leere Registry")
        sys.exit(1)

    print("[2] JSON-Configs scannen ...")
    configs = read_lms_configs(CONFIG_ROOT)
    print(f"  -> {len(configs)} Config-Dateien gefunden")

    dir_to_ctx: dict[str, list[int]] = {}
    dir_broad_to_ctx: dict[str, list[int]] = {}
    for c in configs:
        raw = f"{c['publisher']}/{c['dir_name']}"
        norm_dir = normalize_model_name(raw)
        broad_dir = normalize_for_config(raw)
        ctx = c.get("context_length")
        if ctx is not None:
            dir_to_ctx.setdefault(norm_dir, []).append(int(ctx))
            dir_broad_to_ctx.setdefault(broad_dir, []).append(int(ctx))
    dir_best_ctx = {d: min(ctxs) for d, ctxs in dir_to_ctx.items()}
    dir_broad_best_ctx = {d: min(ctxs) for d, ctxs in dir_broad_to_ctx.items()}
    print(f"  -> {len(dir_best_ctx)} eindeutige Modelle mit context_length")

    norm_reg: dict[str, str] = {}
    for key in reg:
        if isinstance(reg[key], dict):
            norm_reg[normalize_model_name(key)] = key

    print("[3] Registry-Einträge ergänzen ...")
    updated = skipped_no_config = skipped_has_value = 0
    for norm_key, orig_key in sorted(norm_reg.items()):
        entry = reg[orig_key]
        if not isinstance(entry, dict):
            continue
        if "context_length" in entry and entry["context_length"] is not None:
            skipped_has_value += 1
            continue
        base_key = _strip_quant(norm_key)
        broad_key = normalize_for_config(orig_key)
        ctx = (dir_best_ctx.get(base_key)
               or dir_best_ctx.get(norm_key)
               or dir_broad_best_ctx.get(broad_key))
        if ctx is not None:
            entry["context_length"] = ctx
            updated += 1
        else:
            skipped_no_config += 1

    print(f"  -> {updated} Einträge aktualisiert")
    print(f"  -> {skipped_has_value} bereits vorhanden")
    print(f"  -> {skipped_no_config} keine Config gefunden")

    if updated:
        save_registry(reg)
    print(f"[OK] sync-ctx: {updated} aktualisiert, {skipped_has_value} bereits vorhanden, {skipped_no_config} keine Config gefunden")


# ── migrate-keys command ───────────────────────────────────────────

def cmd_migrate_keys() -> None:
    """Migrate registry keys without publisher prefix to canonical format (publisher/model-name)."""
    reg = load_registry()
    migrated = 0
    skipped_no_pub = 0
    merged = 0

    for key in list(reg.keys()):
        entry = reg[key]
        if not isinstance(entry, dict):
            continue
        if "/" in key:
            continue
        pub = str(entry.get("publisher", "")).strip()
        if not pub or pub == "?" or pub == "unknown":
            print(f"  [SKIP] Kein Publisher fuer '{key}'")
            skipped_no_pub += 1
            continue
        new_key = f"{pub}/{key}".lower()
        if new_key in reg:
            # Merge: copy missing fields from old entry to canonical one
            target = reg[new_key]
            for k, v in entry.items():
                if k not in target or target[k] is None:
                    target[k] = v
            del reg[key]
            merged += 1
            continue
        reg[new_key] = reg.pop(key)
        # Fix hf_url if it had double publisher (publisher/publisher/model-name)
        expected_url = f"https://huggingface.co/{new_key}"
        hf = reg[new_key].get("hf_url", "").lower()
        if hf.startswith("https://huggingface.co/"):
            path = hf.replace("https://huggingface.co/", "")
            parts = path.split("/")
            if len(parts) >= 2 and parts[0] == parts[1]:
                reg[new_key]["hf_url"] = expected_url
        migrated += 1

    if migrated or merged:
        save_registry(reg)
    print(f"[OK] Migriert: {migrated}, gemerged: {merged}, kein Publisher: {skipped_no_pub}")


# ── fill-arch command ──────────────────────────────────────────────

def _read_gguf_arch(model_path: str) -> tuple[Optional[int], Optional[int], Optional[bool], Optional[int]]:
    """Read n_layers (block_count), hidden_dim (embedding_length), reasoning-support and context_length from a GGUF file header.

    Returns (block_count, embedding_length, is_reasoning, context_length) where is_reasoning
    is True/False if the chat_template was readable, or None if the GGUF
    header could not be parsed.
    """
    _GGUF_SIZES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}

    def _skip_value(f: Any, vt: int) -> None:
        """Properly skip a GGUF metadata value of the given type."""
        if vt in _GGUF_SIZES:
            f.read(_GGUF_SIZES[vt])
        elif vt == 8:  # STRING
            s_raw = f.read(8)
            if len(s_raw) < 8:
                return
            s_len = int.from_bytes(s_raw, "little")
            if s_len > 100_000 or s_len < 0:
                return
            f.read(s_len)
        elif vt == 9:  # ARRAY
            raw = f.read(4)
            if len(raw) < 4:
                return
            elem_type = int.from_bytes(raw, "little")
            raw = f.read(8)
            if len(raw) < 8:
                return
            arr_len = int.from_bytes(raw, "little")
            for _ in range(arr_len):
                _skip_value(f, elem_type)

    try:
        with open(model_path, "rb") as f:
            if f.read(4) != b"GGUF":
                return None, None, None, None
            f.read(4 + 8 + 8)  # version, tensor_count, metadata_count
            block_count = embedding_length = context_length = None
            chat_template = None
            for _ in range(10_000):
                raw = f.read(8)
                if len(raw) < 8:
                    break
                key_len = int.from_bytes(raw, "little")
                if key_len > 500 or key_len < 1:
                    break
                key = f.read(key_len).decode("utf-8", errors="replace")
                raw = f.read(4)
                if len(raw) < 4:
                    break
                val_type = int.from_bytes(raw, "little")

                if val_type == 8:
                    s_raw = f.read(8)
                    s_len = int.from_bytes(s_raw, "little")
                    val = f.read(s_len).decode("utf-8", errors="replace")
                elif val_type == 4:  # UINT32 - common for block_count/embedding_length
                    val = int.from_bytes(f.read(4), "little")
                elif val_type == 9:  # ARRAY (skip)
                    _skip_value(f, val_type)
                    val = None
                elif val_type in (0, 1, 7):  # U8, I8, BOOL
                    val = int.from_bytes(f.read(1), "little")
                elif val_type in (2, 3):  # U16, I16
                    val = int.from_bytes(f.read(2), "little")
                elif val_type in (5, 6):  # I32, F32
                    val = int.from_bytes(f.read(4), "little")
                elif val_type in (10, 11, 12):  # U64, I64, F64
                    val = int.from_bytes(f.read(8), "little")
                else:
                    val = None

                if key.endswith(".block_count"):
                    block_count = int(val)
                elif key.endswith(".embedding_length"):
                    embedding_length = int(val)
                elif key.endswith(".context_length"):
                    context_length = int(val)
                elif key == "tokenizer.chat_template":
                    chat_template = str(val)
                # Erst abbrechen, wenn ALLE vier Werte gelesen sind: tokenizer.chat_template
                # steht im GGUF-Header meist NACH block_count/embedding_length/context_length.
                if block_count is not None and embedding_length is not None and context_length is not None and chat_template is not None:
                    break
        is_reasoning = _detect_reasoning_from_template(chat_template) if chat_template else False
        return block_count, embedding_length, is_reasoning, context_length
    except (OSError, ValueError, struct.error):
        # GGUF header parse failures (corrupt file, unsupported version, etc.)
        return None, None, None, None


_REASONING_TOKEN_RE = re.compile(
    r'<\s*/?\s*(?:think|thinking|thought)\s*>|'
    r'<\|channel>\s*(?:thought|think)|'
    r'<\|channel\|>\s*analysis',
    re.IGNORECASE,
)

def _detect_reasoning_from_template(template: str) -> bool:
    """Check if a GGUF chat_template supports reasoning/thinking mode.

    Uses regex for token patterns (avoids false positives from
    accidental substring matches) and substring for the well-known
    Jinja llama.cpp variables.
    """
    if "enable_thinking" in template or "reasoning_effort" in template:
        return True
    return bool(_REASONING_TOKEN_RE.search(template))


MODELS_CACHE = Path.home() / ".lmstudio" / "models"

# ── GGUF expert_count check (for MoE detection) ───────────────────
# Cache: model_path -> bool (has experts / MoE)
_GGUF_EXPERT_CACHE: dict[str, bool] = {}
_GGUF_MOE_READER_LOCK: Any = None  # lazy import for threading

def _gguf_has_experts(model_path: str) -> bool:
    """Read GGUF header and return True if expert_count > 0 (MoE).

    Uses the 'gguf' library. The GGUF stores expert_count in an
    architecture-specific key like ``{arch}.expert_count`` (e.g.
    ``ernie4_5-moe.expert_count``). Dense models have no such key.
    Results are cached in _GGUF_EXPERT_CACHE.
    """
    if model_path in _GGUF_EXPERT_CACHE:
        return _GGUF_EXPERT_CACHE[model_path]
    try:
        import gguf
        reader = gguf.GGUFReader(model_path)
        arch_field = reader.fields.get("general.architecture")
        if arch_field is None:
            _GGUF_EXPERT_CACHE[model_path] = False
            return False
        arch_bytes = arch_field.parts[-1]
        if isinstance(arch_bytes, (bytes, bytearray)):
            arch = arch_bytes.decode("utf-8", errors="replace")
        else:
            arch = bytes(arch_bytes).decode("utf-8", errors="replace")
        ec_field = reader.fields.get(f"{arch}.expert_count")
        if ec_field is not None:
            val_arr = ec_field.parts[-1]
            result = bool(val_arr is not None and len(val_arr) > 0 and int(val_arr[0]) > 0)
        else:
            result = False
        _GGUF_EXPERT_CACHE[model_path] = result
        return result
    except Exception:
        _GGUF_EXPERT_CACHE[model_path] = False
        return False


def cmd_fill_arch() -> None:
    """Read n_layers and hidden_dim from local GGUF files (via lms ls).

    Modelle ohne GGUF-Datei (z.B. gelöschte) erhalten keine Architektur-Daten.
    """
    if not REGISTRY_PATH.exists():
        print(f"[ERROR] Registry not found: {REGISTRY_PATH}")
        sys.exit(1)

    print("[1] Registry laden ...")
    reg = load_registry()
    if not reg:
        print("[ERROR] Leere Registry")
        sys.exit(1)

    print("[2] LM Studio-Modelle scannen ...")
    lms_models = _run_lms_ls()
    unique: dict[str, str] = {}
    for m in lms_models:
        rp = m.get("path", "")
        if not rp:
            continue
        full_path = str(MODELS_CACHE / rp)
        if not os.path.isfile(full_path):
            continue
        key = normalize_model_name(m.get("modelKey", "")).lower()
        base = key.split("@")[0]
        if base not in unique:
            unique[base] = full_path
    print(f"  -> {len(unique)} einzigartige Modelle (von {len(lms_models)} GGUF-Dateien)")

    print("[3] GGUF-Header parallel parsen ...")
    gguf_arch: dict[str, tuple[int, int, bool | None, int | None]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        fut_to_base = {pool.submit(_read_gguf_arch, p): b for b, p in unique.items()}
        for i, fut in enumerate(concurrent.futures.as_completed(fut_to_base), 1):
            base = fut_to_base[fut]
            nl, hd, is_reasoning, ctx = fut.result()
            if nl and hd:
                gguf_arch[base] = (nl, hd, is_reasoning, ctx)
            if i % 10 == 0:
                print(f"     ({i}/{len(unique)})")
    print(f"  -> {len(gguf_arch)} mit n_layers/hidden_dim/context_length")

    total = len([k for k, v in reg.items() if isinstance(v, dict)])
    updated = skipped_has = skipped_no = 0
    reasoning_updated = 0
    print(f"[4] {total} Registry-Einträge durchgehen ...")

    for key, entry in reg.items():
        if not isinstance(entry, dict):
            continue

        # Always try to fill max_context_length (even if n_layers/hidden_dim already set)
        if entry.get("max_context_length") is None:
            normalized_key = normalize_model_name(key)
            found = gguf_arch.get(normalized_key)
            if not found:
                base = normalized_key.split("@")[0]
                found = gguf_arch.get(base)
            if not found:
                for gk, gv in gguf_arch.items():
                    if normalized_key in gk or gk in normalized_key:
                        found = gv
                        break
            if found and found[3] is not None:
                entry["max_context_length"] = int(found[3])
                reasoning_updated += 1  # reuse counter

        if entry.get("n_layers") and entry.get("hidden_dim"):
            skipped_has += 1
            continue

        normalized_key = normalize_model_name(key)
        found = gguf_arch.get(normalized_key)
        if not found:
            base = normalized_key.split("@")[0]
            found = gguf_arch.get(base)
        if not found:
            for gk, gv in gguf_arch.items():
                if normalized_key in gk or gk in normalized_key:
                    found = gv
                    break
        if found:
            entry["n_layers"] = int(found[0])
            entry["hidden_dim"] = int(found[1])
            if found[3] is not None and entry.get("max_context_length") is None:
                entry["max_context_length"] = int(found[3])
            updated += 1
        else:
            skipped_no += 1
            continue

        # Update reasoning field from GGUF header (skips if already explicitly set)
        if entry.get("reasoning") is None:
            normalized_key = normalize_model_name(key)
            found = gguf_arch.get(normalized_key)
            if not found:
                base = normalized_key.split("@")[0]
                found = gguf_arch.get(base)
            if not found:
                for gk, gv in gguf_arch.items():
                    if normalized_key in gk or gk in normalized_key:
                        found = gv
                        break
            if found and found[2] is not None:
                entry["reasoning"] = "thinking" if found[2] else "instruct"
                reasoning_updated += 1

    print(f"[OK] fill-arch: {updated} n_layers/hidden_dim gesetzt, {reasoning_updated} reasoning gesetzt, {skipped_has} bereits vorhanden, {skipped_no} kein GGUF-Match ({len(gguf_arch)} GGUF-Dateien ausgewertet)")

    if updated or reasoning_updated:
        save_registry(reg)


# ── fill-reasoning command ──────────────────────────────────────────

def cmd_fill_reasoning() -> None:
    """Fill reasoning field from GGUF headers for all registry entries without it.

    Scans LM Studio models, parses GGUF chat_template, and sets
    reasoning: thinking|instruct where previously missing.
    """
    if not REGISTRY_PATH.exists():
        print(f"[ERROR] Registry not found: {REGISTRY_PATH}")
        sys.exit(1)

    print("[1] Registry laden ...")
    reg = load_registry()
    if not reg:
        print("[ERROR] Leere Registry")
        sys.exit(1)

    print("[2] LM Studio-Modelle scannen ...")
    lms = _run_lms_ls()
    unique: dict[str, str] = {}
    for m in lms:
        rp = m.get("path", "")
        if not rp:
            continue
        full_path = str(MODELS_CACHE / rp)
        if not os.path.isfile(full_path):
            continue
        key = normalize_model_name(m.get("modelKey", "")).lower()
        base = key.split("@")[0]
        if base not in unique:
            unique[base] = full_path
    print(f"  -> {len(unique)} einzigartige Modelle")

    print("[3] GGUF-Header parallel parsen (reasoning-Scan) ...")
    gguf_reasoning: dict[str, bool] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        fut_to_base = {pool.submit(_read_gguf_arch, p): b for b, p in unique.items()}
        for i, fut in enumerate(concurrent.futures.as_completed(fut_to_base), 1):
            base = fut_to_base[fut]
            _, _, is_reasoning, _ = fut.result()
            if is_reasoning is not None:
                gguf_reasoning[base] = is_reasoning
            if i % 10 == 0:
                print(f"     ({i}/{len(unique)})")
    print(f"  -> {len(gguf_reasoning)} mit tokenizer.chat_template (reasoning-auswertbar)")

    total = len([k for k, v in reg.items() if isinstance(v, dict)])
    updated = skipped_has = skipped_no_match = 0
    print(f"[4] {total} Registry-Einträge durchgehen ...")

    for key, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("reasoning") is not None:
            skipped_has += 1
            continue
        normalized_key = normalize_model_name(key)
        found_base = unique.get(normalized_key)
        if not found_base:
            base = normalized_key.split("@")[0]
            found_base = unique.get(base)
        if not found_base:
            for ubase in unique:
                if normalized_key in ubase or ubase in normalized_key:
                    found_base = ubase
                    break
        if found_base and found_base in gguf_reasoning:
            entry["reasoning"] = "thinking" if gguf_reasoning[found_base] else "instruct"
            updated += 1
        else:
            skipped_no_match += 1

    print(f"[OK] fill-reasoning: {updated} reasoning gesetzt, {skipped_has} bereits vorhanden, {skipped_no_match} kein GGUF-Match ({len(gguf_reasoning)} GGUF-Dateien ausgewertet)")


# ── validate command ───────────────────────────────────────────────

TEMPLATE_DIR = PROJECT_ROOT / "doc-git" / "Jinja-Chat-Templates"


def cmd_validate() -> dict[str, Any]:
    """Validate model_registry.yaml consistency: templates, configs, overrides.

    Returns dict with error counts per check category.
    """
    reg = load_registry()
    cfgs = read_lms_configs(CONFIG_ROOT)
    errors: dict[str, list[str]] = {
        "template_missing_file": [],
        "template_missing_config": [],
        "override_overlap": [],
        "missing_reasoning": [],
        "missing_capabilities": [],
        "missing_blueprint": [],
        "registry_no_config": [],
        "orphan_override": [],
        "reasoning_arch_mismatch": [],
    }

    from benchmark_config import MODEL_TEMP_OVERRIDES

    # ── Check 1: template: references existent .jinja file ─────────
    for model_key, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        tpl = entry.get("template")
        if tpl:
            tpl_path = TEMPLATE_DIR / tpl
            if not tpl_path.exists():
                errors["template_missing_file"].append(
                    f"{model_key}: template='{tpl}' -> Datei nicht gefunden ({tpl_path})"
                )

    # ── Check 2: YAML template: -> Config JSON promptTemplate ──────
    for model_key, entry in reg.items():
        if not isinstance(entry, dict) or not entry.get("template"):
            continue
        match = find_config_for_registry_key(model_key, cfgs)
        if match is None:
            errors["template_missing_config"].append(
                f"{model_key}: template='{entry['template']}' in YAML, "
                f"aber Config-JSON nicht gefunden (auch nach fallback matching)"
            )
            continue
        json_path = Path(match["json_path"])
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            errors["template_missing_config"].append(
                f"{model_key}: Config-JSON nicht lesbar ({json_path})"
            )
            continue
        has_pt = False
        for field in data.get("operation", {}).get("fields", []):
            if field.get("key") == "llm.prediction.promptTemplate":
                val = field.get("value", "")
                if val and val.strip():
                    has_pt = True
                break
        if not has_pt:
            errors["template_missing_config"].append(
                f"{model_key}: template='{entry['template']}' in YAML, "
                f"aber promptTemplate in Config fehlt/leer ({json_path})"
            )

    # ── Check 3: Overlapping MODEL_TEMP_OVERRIDES substrings ──────
    override_keys = list(MODEL_TEMP_OVERRIDES.keys())
    for i, a in enumerate(override_keys):
        for b in override_keys[i + 1:]:
            if a in b or b in a:
                errors["override_overlap"].append(
                    f"'{a}' <-> '{b}': '{a}' ist substring von '{b}' "
                    f"(oder umgekehrt) – Reihenfolge im Dict entscheidet!"
                )

    # ── Check 4: reasoning/capabilities/blueprint fields ───────────
    for model_key, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        if not entry.get("reasoning"):
            errors["missing_reasoning"].append(model_key)
        if not entry.get("capabilities"):
            errors["missing_capabilities"].append(model_key)
        if not entry.get("blueprint"):
            errors["missing_blueprint"].append(model_key)

    # ── Check 5: Registry name findet Config JSON (mit fallback matching) ──
    for model_key, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        # Skip models without GGUF installed (no config expected)
        if not entry.get("file_size_bytes"):
            continue
        match = find_config_for_registry_key(model_key, cfgs)
        if match is None:
            rk = normalize_model_name(model_key)
            errors["registry_no_config"].append(
                f"{model_key}: keine passende Config-JSON gefunden (normalized: {rk})"
            )

    # ── Check 6: MODEL_TEMP_OVERRIDES keys matchen Registry-Modell ─
    # Use RAW registry keys (not normalized) to avoid '.' -> '-' conversion
    from benchmark_config import _word_boundary_match
    reg_raw_names = {k.lower() for k in reg if isinstance(reg.get(k), dict)}
    for pattern in MODEL_TEMP_OVERRIDES:
        matches_any = any(_word_boundary_match(pattern, rn) for rn in reg_raw_names)
        if not matches_any:
            errors["orphan_override"].append(
                f"'{pattern}': kein Registry-Modell mit diesem Substring"
            )

    # ── Check 7: reasoning stimmt mit Architektur-Map überein ──────
    for model_key, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        reasoning = entry.get("reasoning")
        arch_raw = entry.get("arch", "")
        if not reasoning or not arch_raw:
            continue
        detected = None
        arch_lower = arch_raw.lower().replace(".", "")  # normalize: "Qwen3.5" → "qwen35"
        for arch_key, rtype in _ARCH_REASONING_MAP.items():
            if arch_key in arch_lower:
                detected = rtype
                break
        if detected is not None and reasoning != detected:
            errors["reasoning_arch_mismatch"].append(
                f"{model_key}: reasoning={reasoning}, aber Architektur "
                f"'{arch_raw}' erwartet '{detected}'"
            )

    # ── Report ─────────────────────────────────────────────────────
    total = sum(len(v) for v in errors.values())
    print(f"\n{'=' * 60}")
    print(f"  Validierung: {total} Probleme gefunden")
    print(f"{'=' * 60}")
    for check, items in errors.items():
        if items:
            print(f"\n  ❌ {check} ({len(items)}):")
            for item in items[:10]:
                print(f"     - {item}")
            if len(items) > 10:
                print(f"     ... und {len(items) - 10} weitere")
        else:
            print(f"\n  ✅ {check}: 0")

    return errors


# ── sync command (full) ────────────────────────────────────────────

def cmd_sync() -> None:
    """Full sync: add → fill-arch → configs → sync-ctx → sync-from-configs → fill-ctx → fmt"""
    lms = _run_lms_ls()
    reg = load_registry()
    registry_key_map = {normalize_model_name(k): k for k, v in reg.items() if isinstance(v, dict)}

    # Find new models
    new_models = []
    for m in lms:
        mk = str(m.get("modelKey", "")).strip()
        if not mk:
            continue
        sk = normalize_model_name(mk)
        if not any(sk == r for r in registry_key_map):
            new_models.append(m)

    if new_models:
        print(f"[add] {len(new_models)} neue Modelle zur Registry ...")
        cmd_add(new_models)
    else:
        print("[add] Keine neuen Modelle")

    print("[fill-arch] n_layers/hidden_dim + reasoning aus GGUF-Headern in Registry ...")
    cmd_fill_arch()

    print("[fill-reasoning] Fehlende reasoning-Felder aus GGUF-Headern ergänzen ...")
    cmd_fill_reasoning()

    print("[configs] load.fields in JSON-Configs schreiben (inkl. useUnifiedKvCache über VRAM-Formel) ...")
    cmd_configs()

    print("[sync-ctx] context_length aus JSON-Configs in Registry (nur fehlende) ...")
    cmd_sync_ctx()

    print("[sync-from-configs] offload, num_parallel, useUnifiedKvCache from JSON configs into Registry (skipping context_length) ...")
    cmd_sync_from_configs()

    print("[fill-ctx] Default context_length für fehlende Einträge ...")
    cmd_fill_ctx()

    print("[fmt] Blank lines normalisieren ...")
    cmd_fmt()

    print("[classify] reasoning/capabilities/blueprint/truncation aus Registry ...")
    classify_registry()
    create_blueprint_definitions()

    print("[assemble] Prompt in JSON-Configs schreiben ...")
    assemble_prompts(preview_only=False)

    print("[validate] Prompt-Syntax-Prüfung ...")
    validate_prompts()

    print("[OK] Sync abgeschlossen")


# ── CLI dispatch ──────────────────────────────────────────────────

def _print_menu(cmds: list[tuple[str, str]]) -> None:
    print("=" * 60)
    print("  registry_tool.py – Interactive Menu")
    print("=" * 60)
    for i, (cmd, desc) in enumerate(cmds, 1):
        print(f"  {i:2d}. {cmd:20s} {desc}")
    print(f"   q. {'quit':20s} Exit")
    print("=" * 60)


def _run_menu_cmd(cmd: str) -> None:
    """Execute a single menu command and wait for user to acknowledge."""
    print(f"\n[RUN] registry_tool.py {cmd}\n")
    dispatch: dict[str, Callable[[], Any]] = {
        "sync": cmd_sync,
        "validate": cmd_validate,
        "configs": cmd_configs,
        "compare": cmd_compare,
        "fmt": cmd_fmt,
        "fix-np": cmd_fix_np,
        "fix-ctx": cmd_fix_ctx,
        "fill-arch": cmd_fill_arch,
        "fill-reasoning": cmd_fill_reasoning,
        "fill-ctx": cmd_fill_ctx,
        "fill-size": cmd_fill_size,
        "sync-ctx": cmd_sync_ctx,
        "sync-from-configs": cmd_sync_from_configs,
        "migrate-keys": cmd_migrate_keys,
    }
    if cmd == "add":
        if not sys.stdin.isatty():
            models = json.load(sys.stdin)
            if not isinstance(models, list):
                models = [models]
            cmd_add(models, interactive=True)
        else:
            print("  [add] Ermittle installierte Modelle via LMS ...")
            models = _run_lms_ls()
            if models:
                cmd_add(models, interactive=True)
            else:
                print("  [WARN] Keine Modelle von LMS erhalten.")
    elif cmd == "rm":
        key = input("  Model-Key (z.B. Intel/gpt-oss-20b-gguf-q4ks-AutoRound): ").strip()
        if not key:
            print("[OK] Abgebrochen")
        else:
            delete_files = input("  Auch Dateien löschen (Config + Hub)? [y/N] ").strip().lower() == "y"
            cmd_rm(key, delete_files=delete_files)
    else:
        dispatch[cmd]()
    if input("\nDrücke Enter für das Menü ... oder q für Quit: ").strip().lower() == "q":
        print("[OK] Bye")
        sys.exit(0)


def _interactive_menu() -> None:
    """Show interactive command selection menu when no args given."""
    cmds = [
        ("sync",      "Full sync: add → fill-arch → fill-reasoning → configs → sync → fmt → classify → assemble → validate"),
        ("validate",  "Check model_registry.yaml consistency"),
        ("configs",   "Write offloadRatio, numParallelSessions, useUnifiedKvCache into JSON configs (VRAM-aware)"),
        ("compare",   "Compare registry vs LMS vs JSON configs"),
        ("add",       "Add LMS models to registry (pipe JSON or provide file)"),
        ("fmt",       "Normalize blank lines in registry YAML"),
        ("fix-np",    "Recompute num_parallel for ALL entries"),
        ("fix-ctx",   "Recompute context_length for ALL entries"),
        ("fill-arch", "Read n_layers/hidden_dim from GGUF headers"),
        ("fill-reasoning", "Read reasoning from GGUF chat_template"),
        ("fill-ctx",  "Add default context_length to missing entries"),
        ("fill-size", "Look up file_size_bytes from LMS"),
        ("sync-ctx",  "Sync context_length from JSON configs into registry"),
        ("sync-from-configs", "Sync offload/np/UKV from configs into registry"),
        ("migrate-keys", "Re-key entries without publisher prefix"),
        ("rm",        "Remove registry entry (optionally files + configs too)"),
    ]

    _print_menu(cmds)
    while True:
        try:
            choice = input("Select command [1-15] or q: ").strip().lower()
            if not choice or choice == "q":
                print("[OK] Bye")
                sys.exit(0)
            idx = int(choice) - 1
            if 0 <= idx < len(cmds):
                _run_menu_cmd(cmds[idx][0])
                _print_menu(cmds)
            else:
                print(f"[ERROR] Invalid choice: {choice}")
        except (EOFError, KeyboardInterrupt):
            print("\n[OK] Bye")
            sys.exit(0)
        except ValueError:
            print(f"[ERROR] Invalid choice: {choice}")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        if len(sys.argv) < 2:
            _interactive_menu()
        else:
            print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "compare":
        cmd_compare()
    elif cmd == "add":
        # Read new models JSON from file arg, stdin, or auto-detect via LMS
        if len(sys.argv) > 2:
            with open(sys.argv[2], "r", encoding="utf-8-sig") as f:
                models = json.load(f)
        elif not sys.stdin.isatty():
            models = json.load(sys.stdin)
        else:
            print("  [add] Ermittle installierte Modelle via LMS ...")
            models = _run_lms_ls()
            if not models:
                print("[ERROR] Kein JSON via Pipe/Datei und LMS nicht erreichbar.")
                print("  Nutzung:   Get-LMSModels | python registry_tool.py add")
                print("  Alternativ: python registry_tool.py add models.json")
                sys.exit(1)
        if not isinstance(models, list):
            models = [models]
        cmd_add(models, interactive=True)
    elif cmd == "configs":
        cmd_configs()
    elif cmd == "sync-ctx":
        cmd_sync_ctx()
    elif cmd == "sync-from-configs":
        cmd_sync_from_configs()
    elif cmd == "fill-ctx":
        cmd_fill_ctx()
    elif cmd == "fix-np":
        cmd_fix_np()
    elif cmd == "fix-ctx":
        cmd_fix_ctx()
    elif cmd == "fill-size":
        cmd_fill_size()
    elif cmd == "fill-arch":
        cmd_fill_arch()
    elif cmd == "fill-reasoning":
        cmd_fill_reasoning()
    elif cmd == "fmt":
        cmd_fmt()
    elif cmd == "migrate-keys":
        cmd_migrate_keys()
    elif cmd == "rm":
        if len(sys.argv) < 3:
            print("[ERROR] Nutzung: python registry_tool.py rm <model-key> [--delete-files] [--yes]")
            sys.exit(1)
        delete_files = "--delete-files" in sys.argv
        assume_yes = "--yes" in sys.argv
        sys.exit(cmd_rm(sys.argv[2], delete_files=delete_files, assume_yes=assume_yes))
    elif cmd == "validate":
        cmd_validate()
    elif cmd == "sync":
        cmd_sync()
    else:
        print(f"[ERROR] Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
