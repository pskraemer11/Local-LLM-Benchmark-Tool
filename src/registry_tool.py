#!/usr/bin/env python3
r"""
Registry and prompt-policy tool for local LLM benchmarks.

This program prepares models for `run_benchmarks.py`. It discovers benchmarkable
LM Studio models, uses the canonical identity `publisher/model@quant`, reads
technical facts from GGUF files, maintains `doc-git\model_registry.yaml`, and
checks prompt and runtime drift.

1. RECOMMENDED WORKFLOW FOR NEW USERS

After downloading a model or changing the local model inventory:

  1) Show the current state:		py -3.12 .\src\registry_tool.py pipeline status

  2) Synchronize the registry:	py -3.12 .\src\registry_tool.py pipeline sync

  3) Check prompts and drift:	py -3.12 .\src\registry_tool.py pipeline full

  4) Write prompt assembly:	py -3.12 .\src\assemble_blueprint.py assemble

  5) Start benchmarks:		py -3.12 .\src\run_benchmarks.py --help

`pipeline full` runs prompt assembly as a preview only and does not write LM
Studio JSON configurations. To write the configurations, run
`assemble_blueprint.py assemble` directly or use the corresponding explicit
write path.

2. DATA OWNERSHIP AND WRITE BOUNDARIES

  Registry policy		doc-git\model_registry.yaml — benchmark and provider-neutral model metadata.
  Technical facts		GGUF files and headers — architecture, quantization, and native limits.
  Prompt policy			doc-git\blueprint_definitions.yaml — blueprints, roles, and prompt modules.
  Runtime artifacts	LM Studio JSON configurations
			Local backend settings; normal sync and `pipeline full` do not silently overwrite them.
  Results			ergebnisse\ — CSVs, telemetry, and summaries.

The Registry is the source of truth for benchmark policy, especially
`useUnifiedKvCache` and `context_length`. The fixed `num_parallel` policy uses
Sample Size (SS): SS >= 10 selects four slots; smaller runs select one slot.
Unified KV-cache (UKV) and local runtime configurations remain separate
responsibility areas.

3. PIPELINE MODES

  pipeline status
      Default: pipeline status. Read-only. Compares benchmarkable LM Studio
      models, the Registry, and config JSONs. Writes nothing.

  pipeline sync
      Status comparison and full Registry synchronization: new models,
      sampling onboarding, quantization, GGUF architecture, reasoning,
      config drift in report mode, and YAML formatting. May write
      model_registry.yaml; does not write config JSONs.

  pipeline full
      `pipeline sync` plus quarantine dry run, blueprint/reasoning
      classification, prompt preview, prompt validation, and Registry drift
      validation. Open blocking ownership drift returns exit code 1.
      `--ignore-drift` changes only the exit code; it does not repair drift.
      `--ignore-drift` keeps it report-only.

  --refresh-sampling
      Re-run sampling research for all benchmarkable candidates. Without this
      option, terminal research statuses are skipped.

4. REGISTRY AND DIAGNOSTIC COMMANDS

  compare       Compare the Registry, LM Studio inventory, and config JSONs.
  sync          Run the full direct Registry synchronization.
  add [JSON]    Add models from JSON, stdin, or LM Studio and research
                sampling values once.
  validate      Check Registry, template, config, and ownership rules.
                Options: --ci/--headless, --verbose, --repro.
  suggest       Show a VRAM-based context/UKV recommendation; writes nothing.
  fill-ctx      Fill missing context_length values; otherwise use 16384.
  fix-ctx       Fill only missing or zero context_length values using the
                size-based formula; existing values remain unchanged.
  fill-size     Fill missing file_size_bytes from GGUF or LM Studio.
  fill-quant    Derive missing @quant identity from GGUF filenames.
  fill-arch     Read missing n_layers and hidden_dim values from GGUF headers.
  sync-from-gguf
                Automatically correct GGUF-owned fields n_layers, hidden_dim,
                max_context_length, and arch.
  fill-reasoning
                Fill reasoning mode from GGUF chat templates.
  fmt           Format the Registry YAML.
  migrate-keys  Convert Registry keys without a publisher.
  sync-from-configs [--write|--write-context]
                Compare config values. Read-only by default.
                --write-context imports only contextLength into context_length;
                --write deliberately imports all supported config fields.
  sync-templates
                Write missing promptTemplate values from Registry templates
                into LM Studio config JSONs.
  sync-template-from-gguf <model-key>
                Copy tokenizer.chat_template from the matching GGUF into a
                config.
  patch-reasoning-effort [--dry-run] [--wait-for-lock] [--effort] [--budget]
                Add gpt-oss reasoning fields to LM Studio configs.
  patch-glm-configs [--dry-run]
                Run the explicit GLM config patch.
  rm <model-key> [--delete-files] [--yes]
                Remove a Registry entry. File/config deletion requires both
                --delete-files and --yes; verify target and scope first.

These runtime commands deliberately modify local JSONs and should be used only
after a preview or targeted review.

5. SAMPLING ONBOARDING AND MODEL FILTERS

New models can be researched once through Hugging Face model cards,
base-model metadata, and bounded official documentation paths. The Registry
stores status, sources, and evidence in the `sampling` block. Possible status
values are `confirmed`, `unresolved`, `conflict`, and `not_found`. Benchmark
runs do not perform web searches; they read only local Registry values and
use category defaults when evidence is missing.

Only models with local benchmark pipelines belong in the Registry. Embedding,
OCR, vision, audio, and RAG-only models, as well as MTP, DFlash, mmproj, and
iMatrix helper files, are excluded.

The identity of every Registry entry is:

  publisher/model@quant

Publisher, base model, and quantization are authoritative for matching and
comparisons.

6. PROMPT ASSEMBLY AND RELATED ENTRY POINTS

  py -3.12 .\src\assemble_blueprint.py --help
      Explain prompt assembly, preview, and validation.

  py -3.12 .\src\assemble_blueprint.py assemble
      Write system prompts and Jinja templates to LM Studio configs.

  py -3.12 .\src\run_benchmarks.py --help
      Explain benchmark selection and run options.

`registry_tool.py` classifies and validates prompt policy. The actual write
assembly remains an explicit step in `assemble_blueprint.py`.

7. TECHNICAL NOTES

  - Windows PowerShell and Python 3.12 are the reference environment.
  - `validate --ci`/`--headless` is for CI without local LM Studio state.
  - `--ignore-drift` suppresses only the exit code; it does not repair drift.
  - Registry synchronization and benchmark execution do not perform sampling
    web searches.
  - Before commit and push, the project's Registry, Ruff, test, and review
    gates apply.

"""

from __future__ import annotations

import concurrent.futures
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

import psutil

_SRC_DIR = Path(__file__).resolve().parent
# Make `src` importable regardless of how the tool is invoked
# (python -m src.registry_tool from the repo root puts only the CWD
# on sys.path, not `src/`). Fix for Code-Review_2026-08-03.md F4.
sys.path.insert(0, str(_SRC_DIR))

if TYPE_CHECKING:
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
    _ARCH_REASONING_MAP,
    assemble_prompts,
    classify_registry,
    find_all_configs_for_registry_key,
    find_config_for_registry_key,
    find_registry_key_for_config,
    normalize_model_name,
    read_lms_configs,
    resolve_template_name,
    validate_prompts,
)
from benchmark_config import (
    GPTOSS_REASONING_BUDGET,
    GPTOSS_REASONING_EFFORT,
    is_blacklisted_model_name,
    is_mtp_drafter,
    is_registry_candidate,
    is_support_file,
)
from benchmark_config import (
    MIN_CONTEXT_LENGTH as _MIN_CONTEXT_LENGTH,
)
from benchmark_config import (
    USABLE_VRAM_GB as _USABLE_VRAM_GB,
)
from benchmark_config import (
    USE_UNIFIED_KV_CACHE_THRESHOLD_GB as _USE_UNIFIED_KV_CACHE_THRESHOLD_GB,  # noqa: F401 - re-export for tests
)
from model_identity import build_model_identity, decompose_model_identity, normalize_variants
from model_paths import configured_gguf_roots
from sampling_research import (
    RESEARCH_STATUSES,
    compact_sampling_block,
    research_sampling,
    research_sampling_report,
    validate_sampling_block,
)

_DEFAULT_RESEARCH_SAMPLING = research_sampling

# ── I/O helpers ────────────────────────────────────────────────────


def load_registry(path: Path | None = None) -> dict[str, RegistryEntry]:
    if path is None:
        path = REGISTRY_PATH
    with open(path, encoding="utf-8") as f:
        return y.load(f) or {}


def _normalize_quants_flow_style(path: Path) -> None:
    """Convert block-style quants (multiline list) to flow-style [item] inline."""
    content = path.read_text("utf-8")
    new, n = re.subn(r"  quants:\n    - (\S+)", r"  quants: [\1]", content)
    if n:
        path.write_text(new, "utf-8")


def _normalize_sampling_schema(reg: dict[str, Any]) -> None:
    """Merge legacy sampling provenance fields into each sampling block."""
    legacy_fields = (
        "sampling_source",
        "sampling_research_status",
        "sampling_researched_at",
        "sampling_sources",
        "sampling_evidence",
        "sampling_category_status",
    )
    for entry in reg.values():
        if not isinstance(entry, dict):
            continue
        sampling = entry.get("sampling")
        has_legacy = any(field in entry for field in legacy_fields)
        if not isinstance(sampling, dict) and not has_legacy:
            continue
        entry["sampling"] = compact_sampling_block(
            sampling if isinstance(sampling, dict) else {},
            status=entry.get("sampling_research_status"),
            researched_at=entry.get("sampling_researched_at"),
            sources=entry.get("sampling_sources"),
            evidence=entry.get("sampling_evidence"),
            category_status=entry.get("sampling_category_status"),
        )
        for field in legacy_fields:
            entry.pop(field, None)


def save_registry(reg: dict[str, Any], path: Path | None = None) -> None:
    if path is None:
        path = REGISTRY_PATH
    _normalize_sampling_schema(reg)
    with open(path, "w", encoding="utf-8") as f:
        y.dump(reg, f)
    _format_blank_lines(path)
    _normalize_quants_flow_style(path)


def _sampling_researched_at() -> str:
    """Return a stable UTC timestamp for one onboarding research attempt."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _run_sampling_research(model: dict[str, Any]) -> dict[str, Any]:
    """Run the detailed researcher, preserving the old patchable test seam."""
    if research_sampling is not _DEFAULT_RESEARCH_SAMPLING:
        result = research_sampling(model)
        if result is None:
            return {"sampling_research_status": "unresolved", "sampling_sources": []}
        report = dict(result)
        report.setdefault("sampling_research_status", "confirmed")
        report.setdefault("sampling_evidence", [])
        return report
    return research_sampling_report(model)


def _apply_sampling_report(entry: dict[str, Any], report: dict[str, Any]) -> bool:
    """Persist a confirmed or terminal sampling research result in an entry."""
    status = str(report.get("sampling_research_status") or "unresolved")
    if status not in {"confirmed", "unresolved", "conflict", "not_found"}:
        status = "unresolved"
    researched_at = _sampling_researched_at()
    category_status = report.get("sampling_category_status")
    sampling = compact_sampling_block(
        report.get("sampling") if isinstance(report.get("sampling"), dict) else {},
        status=status,
        researched_at=researched_at,
        sources=report.get("sampling_sources"),
        evidence=report.get("sampling_evidence"),
        category_status=category_status if isinstance(category_status, dict) else None,
    )
    entry["sampling"] = sampling
    for field in (
        "sampling_source",
        "sampling_research_status",
        "sampling_researched_at",
        "sampling_sources",
        "sampling_evidence",
        "sampling_category_status",
    ):
        entry.pop(field, None)
    return status == "confirmed" and any(
        isinstance(value, dict) and "temperature" in value and "top_p" in value
        for key, value in sampling.items()
        if key in ("coding", "knowledge", "agentic", "math", "thinking")
    )


def apply_sampling_review(
    model_key: str,
    sampling: dict[str, Any],
    sources: list[str],
    evidence: list[dict[str, Any]],
) -> None:
    """Apply an explicitly reviewed sampling result through the Registry API.

    This is the write seam for the manual Codex review workflow. It validates
    the submitted block and never touches LM Studio configuration files.
    """
    issues = validate_sampling_block(sampling)
    if issues:
        raise ValueError("Ungültiger Sampling-Block: " + "; ".join(issues))
    reg = load_registry()
    entry = reg.get(model_key)
    if not isinstance(entry, dict):
        raise KeyError(f"Registry-Key nicht gefunden: {model_key}")
    entry["sampling"] = compact_sampling_block(
        sampling,
        status="confirmed",
        researched_at=_sampling_researched_at(),
        sources=sources,
        evidence=evidence,
    )
    for field in (
        "sampling_source",
        "sampling_research_status",
        "sampling_researched_at",
        "sampling_sources",
        "sampling_evidence",
        "sampling_category_status",
    ):
        entry.pop(field, None)
    save_registry(reg)


def load_lms_json(path: str | Path) -> list[Any]:
    with open(path, encoding="utf-8-sig") as f:
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

    print(f"[INFO] lms ls fehlgeschlagen ({stderr}) - versuche Server-Start...")
    try:
        from model_manager import _is_lmstudio_running

        if _is_lmstudio_running():
            r = subprocess.run(["lms", "ls", "--json"], capture_output=True, text=True, timeout=15)
            if r.returncode == 0:
                data = json.loads(r.stdout)
                return data if isinstance(data, list) else list(data.values())
    except Exception as e:
        print(f"[WARN] Server-Start fehlgeschlagen: {e}")

    print("[WARN] lms ls auch nach Server-Start fehlgeschlagen")
    return []


def _configure_utf8_output() -> None:
    """Make direct CLI output safe for Windows consoles and CI runners."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            # Test doubles and already-closed streams may not support reconfigure.
            pass


# ── Blank-line formatting ──────────────────────────────────────────


def _format_blank_lines(path: Path) -> None:
    """Normalize blank lines in YAML: none within entries, one between entries."""
    with open(path, encoding="utf-8", newline="") as f:
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


# Feste Benchmark-Policy seit 13.08.: np=4 bei SampleSize >= 10, sonst 1.
# Die Kontextberechnung rechnet mit der Standard-Benchmark-Konfiguration (np=4).
_NP_POLICY = 4


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
            kc = entry.get("k_cache", "q8_0")
            vc = entry.get("v_cache", "iq4_nl")
            entry["context_length"] = _default_ctx_from_size(int(size_bytes), _NP_POLICY, kc, vc)
        else:
            entry["context_length"] = default
        updated += 1
    if updated:
        save_registry(reg)
    print(f"[OK] {updated} entries got context_length")


# ── fix-ctx command ──────────────────────────────────────────────


def cmd_fix_ctx() -> None:
    """Fill missing or zero context_length values using the size-based formula."""
    reg = load_registry()
    updated = 0
    for entry in reg.values():
        if not isinstance(entry, dict):
            continue
        sb = entry.get("file_size_bytes")
        if sb and sb > 0:
            kc = entry.get("k_cache", "q8_0")
            vc = entry.get("v_cache", "iq4_nl")
            new_ctx = _default_ctx_from_size(int(sb), _NP_POLICY, kc, vc)
            if entry.get("context_length") in (None, 0):
                entry["context_length"] = new_ctx
                updated += 1
    if updated:
        save_registry(reg)
    print(f"[OK] {updated} entries updated context_length")


# ── fill-size command ──────────────────────────────────────────────


def cmd_fill_size() -> None:
    """Fill file_size_bytes from filesystem (GGUF files), LMS as fallback.

    Source of Truth: the actual GGUF file on disk. LMS is only used if the
    file is not directly accessible (e.g., not in MODELS_CACHE).
    """
    reg = load_registry()
    updated = 0

    # Primary: read from filesystem directly
    for key, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("file_size_bytes"):
            continue
        # Find the GGUF file for this key
        ggu = _find_gguf_for_key(key)
        if ggu is not None:
            try:
                size = ggu.stat().st_size
                if size > 0:
                    entry["file_size_bytes"] = size
                    updated += 1
                    continue
            except OSError:
                pass

    # Fallback: LMS for entries still missing size
    lms_models = _benchmark_lms_models(_run_lms_ls())
    if lms_models:
        lms_sizes: dict[str, int] = {}
        for m in lms_models:
            mk = normalize_model_name(m.get("modelKey", ""))
            sb = m.get("sizeBytes", 0)
            if sb and sb > 0 and mk not in lms_sizes:
                lms_sizes[mk] = int(sb)
        for key, entry in reg.items():
            if not isinstance(entry, dict) or entry.get("file_size_bytes"):
                continue
            if normalize_model_name(key) in lms_sizes:
                entry["file_size_bytes"] = lms_sizes[normalize_model_name(key)]
                updated += 1

    if updated:
        save_registry(reg)
    print(f"[OK] {updated} entries got file_size_bytes (filesystem primary, LMS fallback)")


def _find_gguf_for_key(key: str) -> Path | None:
    """Find the GGUF file for a registry key by scanning configured roots.

    Returns the Path or None if not found.
    """
    from model_identity import normalize_model_name
    base = normalize_model_name(key).split("@")[0]
    for g in _get_all_ggufs():
        if g.is_file() and base.replace("-", "_") in g.name.replace("-", "_"):
            return g
    return None


_GGUF_FILE_CACHE: list[Path] | None = None
_GGUF_FILE_CACHE_ROOTS: tuple[str, ...] | None = None


def _get_all_ggufs() -> list[Path]:
    """Return (and cache) all ``.gguf`` files under the configured roots."""
    global _GGUF_FILE_CACHE, _GGUF_FILE_CACHE_ROOTS
    roots = _gguf_roots()
    root_key = tuple(str(root).casefold() for root in roots)
    if _GGUF_FILE_CACHE is None or _GGUF_FILE_CACHE_ROOTS != root_key:
        files: list[Path] = []
        for root in roots:
            if root.is_dir():
                files.extend(root.rglob("*.gguf"))
        _GGUF_FILE_CACHE = sorted(files, key=lambda item: str(item).casefold())
        _GGUF_FILE_CACHE_ROOTS = root_key
    return _GGUF_FILE_CACHE


def _norm(s: str) -> str:
    """Lower-case, strip ``.gguf``, replace ``-``/``_``/``\\``/``/``/``@`` with space."""
    s = (
        s.lower()
        .replace(".gguf", "")
        .replace("-", " ")
        .replace("_", " ")
        .replace("\\", " ")
        .replace("/", " ")
        .replace("@", " ")
    )
    return " ".join(s.split())


# Zentralisiert in benchmark_config.py (Code-Review 2026-08-03 §F1):
# wird identisch von model_manager.get_available_models() genutzt.
_is_support_file = is_support_file


def _significant_words(s: str) -> set[str]:
    """Split *s* into lower-case words, keep only ≥3-char tokens."""
    return {w for w in _norm(s).split() if len(w) >= 3}


def _resolve_model_path_multi(key: str) -> str:
    """Resolve GGUF path — exact substring match first, then word-match fallback.

    1. Exact ``GGUF root / key`` — library-level path from LM Studio.
    2. Substring match (normalised key suffix in normalised GGUF path).
    3. Word-match fallback (at least 2 significant words in common).
    Returns ``""`` if nothing suitable is found.
    """
    candidate = _find_gguf_relative_path(key)
    if candidate is not None:
        return str(candidate)

    suffix = key.split("/", 1)[1] if "/" in key else key
    sn = _norm(suffix)

    # 2) Substring match
    for g in _get_all_ggufs():
        if _is_support_file(g):
            continue
        if sn in _norm(str(g)):
            return str(g)

    # 3) Word-match fallback — require ≥ 2 significant words in common
    sw = _significant_words(suffix)
    if len(sw) < 2:
        return ""
    best: tuple[int, str] = (0, "")
    for g in _get_all_ggufs():
        if _is_support_file(g):
            continue
        gw = _significant_words(str(g))
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
    # Konsolidiert in model_identity.py (Fix 2026-08-09).
    return normalize_variants(key)


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
    candidate = _find_gguf_relative_path(reg_key)
    if candidate is not None:
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
        if sn in _norm(str(g)):
            return str(g)
    return ""


def cmd_fix_np() -> None:
    """Seit 13.08. überflüssig: np ist feste Policy (SS>=10 → 4, sonst 1),
    kein Registry-Feld mehr. Arch-Reclassification erledigt sync-from-gguf."""
    print("[INFO] fix-np entfällt: num_parallel ist seit 13.08. eine feste")
    print("       Benchmark-Policy (SS>=10 → 4, sonst 1) und kein Registry-Feld.")
    print("       Arch-Reclassification: registry_tool.py sync-from-gguf.")


# ── compare command ────────────────────────────────────────────────


def cmd_compare() -> dict[str, Any]:
    reg = load_registry()
    lms = _benchmark_lms_models(_run_lms_ls())
    cfgs = read_lms_configs(CONFIG_ROOT)

    registry_keys = [k for k, v in reg.items() if isinstance(v, dict)]
    new_models: list[dict] = []
    for model in lms:
        if not any(_lms_matches_registry_key(model, key) for key in registry_keys):
            new_models.append(model)

    missing: list[str] = []
    for rn, re_ in reg.items():
        if (
            not isinstance(re_, dict)
            or re_.get("blueprint") == "none"
            or not is_registry_candidate({"modelKey": rn})
        ):
            continue
        if not any(_lms_matches_registry_key(model, rn) for model in lms):
            missing.append(rn)

    orphan: set[str] = set()
    registry_key_sorted = sorted(
        [(normalize_model_name(k), k) for k in registry_keys],
        key=lambda x: -len(x[0]),
    )
    for c in cfgs:
        n = normalize_model_name(c["dir_name"])
        if find_registry_key_for_config(n, registry_key_sorted, config=c) is None:
            orphan.add(f"{c['publisher']}/{c['dir_name']}")

    report = {
        "lms": len(lms),
        "reg": len(registry_keys),
        "cfg": len(cfgs),
        "new": len(new_models),
        "missing": len(missing),
        "orphan": len(orphan),
        "newd": [
            {
                "key": m.get("modelKey", "?"),
                "publisher": m.get("publisher", "?"),
                "arch": m.get("architecture", "?"),
                "params": m.get("paramsString", "?"),
                "ctx": m.get("maxContextLength", 0),
                "vision": m.get("vision", False),
                "tools": m.get("trainedForToolUse", False),
                "size_bytes": m.get("sizeBytes", 0),
            }
            for m in new_models[:20]
        ],
        "missd": missing[:20],
        "orphd": sorted(orphan)[:20],
    }

    print(json.dumps(report, ensure_ascii=False, default=str))
    return report


# ── quarantine-missing command ─────────────────────────────────────


def _registry_key_installed(
    key: str,
    lms_quant: dict[str, str],
    lms_variants: dict[str, str],
) -> str | None:
    """Exakter Match auf installierte LMS-Modelle (kein Substring/Fuzz).

    Strenge Erkennung (2026-08-10): @-Quant-Keys (z.B. ``x@iq4_nl``) gelten
    NUR als installiert, wenn LMS exakt diese Variante führt (``lms_quant``).
    Die Basis-Variante ohne @ zählt nicht - ``normalize_variants`` strippt
    @-Suffixe und würde sonst uninstallierte Quants maskieren.
    """
    if "@" in key:
        return lms_quant.get(_quant_variant(key))
    for variant in _normalize_variants(key):
        lmk = lms_variants.get(variant)
        if lmk is not None:
            return lmk
    return None


def _missing_registry_keys(lms: list[dict]) -> list[str]:
    """Registry-Keys ohne passendes installiertes LMS-Modell.

    Strenge Erkennung: @-Quant-Varianten nur installiert, wenn LMS exakt
    diese Variante führt. (compare nutzt bewusst Substring - dort ist der
    Report konservativ; Quarantäne entfernt nur nachweislich fehlende.)
    """
    reg = load_registry()
    lms = _benchmark_lms_models(lms)

    missing: list[str] = []
    for rn, re_ in reg.items():
        if (
            not isinstance(re_, dict)
            or re_.get("blueprint") == "none"
            or not is_registry_candidate({"modelKey": rn})
        ):
            continue
        if _lms_record_for_registry_key(rn, lms) is None:
            missing.append(rn)
    return missing


def _gguf_for_key_exists(key: str) -> bool:
    """True wenn für den Registry-Key eine GGUF-Datei physisch existiert.

    Prüft die konfigurierten GGUF-Roots und ``~/.lmstudio/hub/models``.
    Der Vergleich ist wort-basiert auf dem normalisierten Modellnamen (ohne
    Publisher, ``-gguf-``-Suffix und @-Quant, wie ``normalize_model_name``):
    alle signifikanten Wörter des Keys müssen im Dateinamen vorkommen.
    Wenn eine Datei existiert, wird der Key nur gemeldet (möglicher
    Index-Fehler wie GLM-4.6V am 09.08.), nicht quarantänt.
    """
    suffix = key.split("/", 1)[1] if "/" in key else key
    base = normalize_model_name(suffix.split("@", 1)[0])
    sn = _significant_words(base)
    if not sn:
        return False
    for base_dir in (*_gguf_roots(), Path.home() / ".lmstudio" / "hub" / "models"):
        if not base_dir.is_dir():
            continue
        for g in base_dir.rglob("*.gguf"):
            if g.is_file() and sn.issubset(_significant_words(str(g))):
                return True
    return False


def _config_claimed_by_other(
    cfg: dict[str, Any],
    key: str,
    reg: dict[str, Any],
    cfgs: list[dict],
) -> str | None:
    """Registry-Key, der dieselbe Config (publisher/dir_name) referenziert.

    Configs werden breit gematcht (``find_all_configs_for_registry_key``:
    Level 2-4 = broad/prefix). Eine Config kann daher zu mehreren Registry-
    Keys passen (z.B. ``google/gemma-4-26b-a4b-it-qat`` matcht die Config von
    ``unsloth/gemma-4-26b-a4b-it@iq3_s``). Beim Quarantänen darf eine Config
    nur mitverschoben werden, wenn kein anderer verbleibender Registry-Key
    sie beansprucht. Rückgabe: Name des anderen Keys, sonst ``None``.
    """
    for other, other_entry in reg.items():
        if other == key or not isinstance(other_entry, dict):
            continue
        for oc in find_all_configs_for_registry_key(other, cfgs):
            if oc["publisher"] == cfg["publisher"] and oc["dir_name"] == cfg["dir_name"]:
                return other
    return None


def cmd_quarantine_missing(dry_run: bool = False) -> int:
    """Registry-Einträge nicht-installierter Modelle in Quarantäne verschieben.

    Für jeden Registry-Key ohne passendes LMS-Modell (missing-Liste wie
    ``compare``):
      1. GGUF physisch noch vorhanden? -> nur melden (Index-Problem vermutet).
      2. Sonst: zugehörige JSON-Configs nach ``_quarantine_missing_<ts>``
         verschieben (nicht löschen), Registry-Eintrag entfernen.
      3. Entfernte Einträge als YAML-Backup sichern (reversibel).
    Mit ``dry_run=True`` wird nichts geschrieben/verschoben.
    """
    lms = _benchmark_lms_models(_run_lms_ls())
    if not lms:
        print("[WARN] lms ls lieferte keine Modelle - Quarantäne übersprungen (kein Auto-Löschen).")
        return 1

    reg = load_registry()
    cfgs = read_lms_configs(CONFIG_ROOT)
    missing = _missing_registry_keys(lms)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    quarantine_dir = CONFIG_ROOT / f"_quarantine_missing_{ts}"
    backup_path = (
        PROJECT_ROOT / "doc-git" / "Review-Artifacts" / f"quarantine_registry_{ts}.yaml"
    )

    remaining = {k: v for k, v in reg.items() if k not in missing}

    quarantined: list[str] = []
    reported: list[str] = []
    moved_configs = 0
    backup_entries: dict[str, Any] = {}

    for key in sorted(missing):
        if _gguf_for_key_exists(key):
            reported.append(key)
            print(f"  [HINWEIS] {key}: GGUF existiert physisch - nur gemeldet (Index-Problem vermutet)")
            continue
        if dry_run:
            print(f"  [DRY-RUN] {key}: Configs + Registry-Eintrag würden quarantänt")
            quarantined.append(key)
            continue

        cfg_paths: list[Path] = []
        for cfg in find_all_configs_for_registry_key(key, cfgs):
            claimed = _config_claimed_by_other(cfg, key, remaining, cfgs)
            if claimed:
                print(f"  {key}: Config {cfg['publisher']}/{cfg['dir_name']}/{cfg['file_name']} "
                      f"gehört {claimed} (bleibt)")
                continue
            flat = CONFIG_ROOT / cfg["publisher"] / cfg["file_name"]
            nested = CONFIG_ROOT / cfg["publisher"] / cfg["dir_name"] / cfg["file_name"]
            src = nested if nested.is_file() else flat
            if src.is_file():
                cfg_paths.append(src)
        for src in cfg_paths:
            dest = quarantine_dir / src.relative_to(CONFIG_ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            moved_configs += 1
            print(f"  {key}: Config verschoben -> {dest.relative_to(CONFIG_ROOT)}")

        entry = reg.get(key)
        is_partial = isinstance(entry, dict) and set(entry.keys()) <= {"reasoning", "blueprint"}
        if not is_partial:
            backup_entries[key] = entry
        del reg[key]
        quarantined.append(key)
        if is_partial:
            print(f"  {key}: Registry-Eintrag entfernt (kein Backup: partieller Eintrag)")
        else:
            print(f"  {key}: Registry-Eintrag entfernt (Backup: {backup_path.name})")

    if not dry_run and quarantined:
        save_registry(reg)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        with open(backup_path, "w", encoding="utf-8") as f:
            YAML().dump(backup_entries, f)

    verb = "quarantänt" if not dry_run else "würde quarantänt"
    print(f"[OK] {len(quarantined)} Modelle {verb}, {moved_configs} Config(s) verschoben, "
          f"{len(reported)} nur gemeldet (GGUF vorhanden).")
    return 0 if not reported else 2


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


def _compute_ukv(
    model_gb: float,
    kv_per_slot_gb: float,
    native_ctx: int,
    vram_available: float = _USABLE_VRAM_GB,
    min_ctx: int = _MIN_CONTEXT_LENGTH,
    model_name: str = "",
) -> tuple[bool, int]:
    """Compute optimal useUnifiedKvCache and context_length based on VRAM budget.

    Seit 13.08.: num_parallel ist eine feste Benchmark-Policy (SS>=10 → 4, sonst 1),
    kein Registry-Feld. Vom verfügbaren Speicher, der Kontextlänge und der
    KV-Quantisierung abhängig ist nur UKV — nicht np. Die Kontextberechnung
    geht daher von der Standard-Benchmark-Konfiguration (np=_NP_POLICY) aus.

    Args:
        model_gb: Model file size in GB.
        kv_per_slot_gb: KV-cache cost per slot (nl x hd x 2 x kv_bytes / 1e9).
        native_ctx: Native max context length from GGUF header.
        vram_available: Usable VRAM in GB (default: 15.3).
        min_ctx: Minimum acceptable context length (default: 32768).
        model_name: Model identifier for UKV special case lookup (optional).

    Returns:
        (use_unified_kv_cache, context_length)
    """
    if kv_per_slot_gb <= 0:
        # No arch data → UKV based on benchmark formula
        from benchmark_config import should_use_unified_kv_cache
        is_ukv = should_use_unified_kv_cache(model_name or "unknown", model_gb)
        return is_ukv, native_ctx

    # Estimate max ctx from VRAM (for models without max_context_length in registry)
    max_possible_ctx = int(vram_available / (kv_per_slot_gb / 1e9)) if kv_per_slot_gb > 0 else native_ctx
    effective_native_ctx = min(native_ctx, max_possible_ctx)

    # np factor for KV usage: 1 if UKV else _NP_POLICY
    for ukv in (False, True):
        np_factor = 1 if ukv else _NP_POLICY
        # Max ctx for this UKV combination
        max_ctx_for_config = int(vram_available / (kv_per_slot_gb * np_factor / 1e9))
        ctx = min(effective_native_ctx, max_ctx_for_config)
        if ctx >= min_ctx:
            return ukv, ctx

    # Fallback: UKV=False, ctx=min_ctx
    return False, min_ctx


# ── add command ────────────────────────────────────────────────────


def cmd_add(
    models: list[dict[str, Any]],
    interactive: bool = False,
    research_web: bool = False,
) -> dict[str, Any]:
    """Add eligible LMS models and research a verified sampling profile.

    Web research is best-effort and never changes LM Studio JSON files.  A
    sampling block is added only when temperature and top_p are found with
    unambiguous, plausible values in a model card or official source.
    """
    reg = load_registry()
    added: list[str] = []
    skipped: list[tuple[str, str]] = []
    sampling_unresolved: list[str] = []

    for m in models:
        if not is_registry_candidate(m):
            skipped.append((str(m.get("modelKey") or m.get("key") or "?"), "nicht benchmarkfähig"))
            continue
        mk = str(m.get("key") or m.get("modelKey") or "").strip()
        if not mk:
            skipped.append(("?", "leerer Key"))
            continue
        pub = str(m.get("publisher", "unknown")).strip()
        # LM Studio often reports the base model in ``modelKey`` and stores
        # the selected quant only in ``quantization``/``selectedVariant``.
        # Use the complete identity here, otherwise a new quant is mistaken
        # for an already-installed base as soon as another @quant exists.
        canonical = _canonical_lms_key(m)
        canonical_base = canonical.split("@", 1)[0]
        sk = normalize_model_name(canonical)
        # Exact match (including @quant) — always a duplicate
        if sk in (normalize_model_name(k) for k in reg):
            skipped.append((mk, "bereits vorhanden"))
            continue
        # Base entry (without @quant) when a @quant variant already exists,
        # e.g. skip "model" if "model@q3_k_s" exists. Multiple @quant variants
        # (@q3_k_s, @q6_k) should coexist. @? variants filtered by is_support_file.
        if "@" not in sk:
            if any("@" in k and normalize_model_name(k).split("@")[0] == sk for k in reg):
                skipped.append((mk, "bereits vorhanden (Quant-Variante existiert)"))
                continue
        else:
            # @quant variant: remove existing base entry (without @) if present.
            # The base entry is ambiguous; the @quant entry is specific and has a
            # unique file_size_bytes.
            base_key = sk.split("@")[0]
            base_entry = next((k for k in reg if normalize_model_name(k) == base_key), None)
            if base_entry is not None:
                print(f"  [CLEANUP] Entferne Base-Eintrag '{base_key}' (ersetzt durch {mk})")
                del reg[base_entry]
        if is_blacklisted_model_name(mk):
            skipped.append((mk, "blacklisted"))
            continue
        rp = m.get("path", "")
        size_bytes = m.get("size_bytes", 0) or m.get("sizeBytes", 0)
        if is_mtp_drafter(mk, size_bytes):
            skipped.append((mk, "blacklisted (MTP drafter)"))
            continue
        if rp and _is_support_file(rp, str(m.get("architecture") or "")):
            skipped.append((mk, "Zusatzdatei (MTP-Drafter/mmproj/imatrix) - kein eigenständiges Modell"))
            continue
        model_path = ""
        rp = m.get("path", "")
        if rp:
            mp_candidate = _find_gguf_relative_path(rp)
            if mp_candidate is not None:
                model_path = str(mp_candidate)
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
        size_bytes = m.get("size_bytes", 0) or m.get("sizeBytes", 0)
        entry = {
            "publisher": pub,
            "hf_url": f"https://huggingface.co/{canonical_base}",
            "arch": classification,
            "k_cache": "q8_0",
            "v_cache": "iq4_nl",
            "offload": 1,
            "notes": nt,
        }
        base_architecture = str(m.get("architecture") or "").strip().lower()
        if base_architecture:
            entry["architecture_family"] = base_architecture
        if size_bytes and size_bytes > 0:
            entry["file_size_bytes"] = int(size_bytes)
            entry["context_length"] = _default_ctx_from_size(int(size_bytes), _NP_POLICY, entry["k_cache"], entry["v_cache"])

        # Auto-fill arch data from GGUF file if available
        model_path = m.get("path", "")
        if model_path:
            full_path = _find_gguf_relative_path(model_path)
            if full_path is not None:
                nl, hd, is_reasoning, ctx, _ = _read_gguf_arch(str(full_path))
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
            print("  Keine GGUF-Datei gefunden - Reasoning-Typ kann nicht automatisch erkannt werden.")
            ans = input("  Reasoning-Typ? [i]nstruct / [t]hinking / [n]one / (d=instruct): ").strip().lower()
            if ans in ("t", "thinking"):
                entry["reasoning"] = "thinking"
            elif ans in ("n", "none"):
                entry["reasoning"] = "none"
            else:
                entry["reasoning"] = "instruct"

        if research_web:
            research_model = dict(m)
            research_model.update({"modelKey": canonical, "hf_url": entry["hf_url"]})
            report = _run_sampling_research(research_model)
            if _apply_sampling_report(entry, report):
                print(
                    f"  [SAMPLING] {canonical}: Web-Profil übernommen "
                    f"({len(report.get('sampling_sources', []))} Quelle(n))"
                )
            else:
                sampling_unresolved.append(canonical)
                current_status = (entry.get("sampling") or {}).get("sampling_research_status")
                print(
                    f"  [SAMPLING-WARN] {canonical}: Status "
                    f"{current_status} - keine eindeutige, "
                    "plausible Temperatur/top_p-Kombination gefunden; "
                    "Kategorie-Defaults bleiben aktiv"
                )

        reg[canonical] = entry
        added.append(canonical)

    if added:
        save_registry(reg)

    result = {
        "added": added,
        "skipped": skipped,
        "sampling_unresolved": sampling_unresolved,
    }
    print(json.dumps(result, ensure_ascii=False))
    return result


def _research_missing_sampling(reg: dict[str, Any], force: bool = False) -> list[str]:
    """Research sampling incrementally, or every candidate when forced."""
    unresolved: list[str] = []
    changed = False
    for model_key, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        if not force and "sampling" in entry:
            continue
        sampling_block = entry.get("sampling") if isinstance(entry.get("sampling"), dict) else {}
        if not force and (
            entry.get("sampling_research_status")
            or sampling_block.get("sampling_research_status")
        ):
            continue
        if not is_registry_candidate({"modelKey": model_key}):
            continue
        model = dict(entry)
        model.update(
            {
                "modelKey": model_key,
                "publisher": entry.get("publisher") or model_key.split("/", 1)[0],
                "hf_url": entry.get("hf_url") or f"https://huggingface.co/{model_key.split('@', 1)[0]}",
            }
        )
        report = _run_sampling_research(model)
        confirmed = _apply_sampling_report(entry, report)
        changed = True
        if not confirmed:
            unresolved.append(model_key)
            current_sampling = entry.get("sampling")
            current_status = entry.get("sampling_research_status")
            if not current_status and isinstance(current_sampling, dict):
                current_status = current_sampling.get("sampling_research_status")
            print(
                f"  [SAMPLING-WARN] {model_key}: Status "
                f"{current_status} "
                "- keine Web-Empfehlung gefunden"
            )
            continue
        if force:
            print(f"  [SAMPLING] {model_key}: kategorisierte Sampling-Evidenz aktualisiert")
        else:
            print(f"  [SAMPLING] {model_key}: fehlender Block aus Web-Quelle ergänzt")

    if changed:
        save_registry(reg)
    return unresolved


# ── configs command ────────────────────────────────────────────────


def cmd_suggest() -> dict[str, Any]:
    """Dry-run: compute VRAM-based np/UKV/offload recommendation, write NOTHING.

    The JSON configs are the source of truth (set via LM Studio GUI); this
    command only shows what the VRAM formula would recommend, so the user can
    decide manually. max_context_length stays in the registry (from GGUF).
    """
    reg = load_registry()
    cfgs = read_lms_configs(CONFIG_ROOT)
    # Keep duplicate normalized names: publisher and quant are resolved by
    # find_registry_key_for_config instead of collapsing them in a dict.
    registry_key_sorted = sorted(
        [(normalize_model_name(k), k) for k, v in reg.items() if isinstance(v, dict)],
        key=lambda x: -len(x[0]),
    )

    shown = skipped = blacklisted = errors = 0
    for cfg in cfgs:
        cn = normalize_model_name(cfg["dir_name"])
        match = find_registry_key_for_config(cn, registry_key_sorted, config=cfg)
        if not match:
            skipped += 1
            continue
        if is_blacklisted_model_name(match):
            blacklisted += 1
            continue
        entry = reg[match]
        try:
            # ── UKV/ctx computation (13.08.: np ist feste Policy, s. _NP_POLICY) ──
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

            ukv_new, ctx_new = _compute_ukv(
                model_gb,
                kv_per_slot_gb,
                native_ctx,
                vram_available=_USABLE_VRAM_GB,
                min_ctx=_MIN_CONTEXT_LENGTH,
                model_name=match,
            )

            offload = entry.get("offload")
            print(f"  [SUGGEST] {match}")
            if offload is not None:
                print(f"    offload      : {offload} (aus Registry)")
            print(f"    useUnifiedKvCache: {ukv_new} (Empfehlung)")
            print(f"    context      : {ctx_new} (Empfehlung, min={_MIN_CONTEXT_LENGTH})")
            print(f"    native ctx   : {native_ctx} (aus GGUF, nicht in Config)")
            shown += 1
        except (OSError, ValueError, KeyError, TypeError) as e:
            print(f"  [WARN] cmd_suggest Fehler fuer {match}: {e}", file=sys.stderr)
            errors += 1

    result = {"shown": shown, "skipped": skipped, "blacklisted": blacklisted, "errors": errors}
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
        k
        for k, v in reg.items()
        if isinstance(v, dict) and (normalize_model_name(k) == target or normalize_model_name(k).endswith("-" + target))
    ]
    if not matches:
        print(f"[ERROR] Kein Registry-Eintrag gefunden für: {model_key} (normalisiert: {target})")
        return 1
    if len(matches) > 1:
        print(f"[ERROR] Mehrdeutig - mehrere Einträge matchen: {matches}")
        return 1
    key = matches[0]

    configs = read_lms_configs(CONFIG_ROOT)
    cfg_paths = [c["json_path"] for c in find_all_configs_for_registry_key(key, configs)]
    hub_dir = Path.home() / ".lmstudio" / "hub" / "models" / Path(*key.split("/"))
    model_dirs = [root / Path(*key.split("/")) for root in _gguf_roots()]
    model_dirs = [d for d in (hub_dir, *model_dirs) if d.exists()]

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
            print(f"  Modell-Dateien   : (nicht gefunden unter {hub_dir} / {_gguf_roots()})")

    if not assume_yes:
        answer = input("  Wirklich löschen? [y/N] ").strip().lower()
        if answer != "y":
            print("[OK] Abgebrochen - nichts gelöscht.")
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


def cmd_sync_from_configs(
    write: bool = False,
    write_context: bool = False,
    installed_models: list[dict[str, Any]] | None = None,
) -> None:
    """Compare GUI load settings and optionally persist them in the registry.

    ``write=False`` is the safe report mode. With ``write=True``, values from
    LM Studio configs are copied. ``write_context=True`` is the narrow variant
    that persists only ``context_length`` and leaves offload/UKV/KV settings
    untouched. Conflicting values across configs for one registry entry are
    reported and skipped. When ``installed_models`` is provided by ``sync``,
    configs with no matching current LMS inventory entry are ignored as stale
    runtime artifacts.
    """
    if write_context:
        write = True
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
    if installed_models is not None:
        active_configs: list[dict[str, Any]] = []
        for cfg in configs:
            if any(_config_matches_lms_model(cfg, model) for model in installed_models):
                active_configs.append(cfg)
            else:
                print(f"[SKIP] Veraltete Config nicht im LMS-Inventar: {cfg['json_path']}")
        configs = active_configs
        print(f"  -> {len(configs)} aktive Config-Dateien nach LMS-Abgleich")

    # Do not collapse equal normalized model names: publisher and quantization
    # are part of the identity and are resolved per config below.
    registry_key_sorted = sorted(
        [(normalize_model_name(k), k) for k, v in reg.items() if isinstance(v, dict)],
        key=lambda x: -len(x[0]),
    )

    print(f"[3] Registry-Einträge mit Configs abgleichen ({'Schreibmodus' if write else 'Melde-Modus'}) ...")
    skipped_no_match = 0
    blacklisted = 0
    observations: dict[str, dict[str, list[tuple[Any, Path]]]] = {}
    for cfg in configs:
        cn = normalize_model_name(cfg["dir_name"])
        match = find_registry_key_for_config(cn, registry_key_sorted, config=cfg)
        if not match:
            skipped_no_match += 1
            continue
        if is_blacklisted_model_name(match):
            blacklisted += 1
            continue
        fields_to_sync = (("context_length", "context_length"),) if write_context else (
            ("offload", "offload"),
            ("useUnifiedKvCache", "use_unified_kv"),
            ("context_length", "context_length"),
            ("k_cache", "k_cache"),
            ("v_cache", "v_cache"),
        )
        for field, cfg_field in fields_to_sync:
            value = cfg.get(cfg_field)
            if value is not None:
                if field == "context_length":
                    try:
                        value = int(value)
                    except (TypeError, ValueError):
                        print(f"[WARN] {match}: ungueltige context_length in {cfg['json_path']}: {value!r}")
                        continue
                observations.setdefault(match, {}).setdefault(field, []).append(
                    (value, Path(cfg["json_path"]))
                )

    drifts = writes = conflicts = 0
    for match, fields in observations.items():
        entry = reg.get(match)
        if not isinstance(entry, dict):
            continue
        for field, values in fields.items():
            distinct = {repr(value) for value, _path in values}
            if len(distinct) > 1:
                conflicts += 1
                locations = ", ".join(str(path) for _value, path in values)
                print(f"[KONFLIKT] {match}: {field} hat mehrere GUI-Werte ({locations}); nicht geschrieben")
                continue
            gui_value, source_path = values[0]
            registry_value = entry.get(field)
            if registry_value == gui_value:
                continue
            drifts += 1
            print(f"[DRIFT] {match}: {field} Registry={registry_value!r} GUI={gui_value!r} ({source_path})")
            if write:
                entry[field] = gui_value
                writes += 1

    if write and writes:
        save_registry(reg)
    print(f"[OK] sync-from-configs: {drifts} Drifts, {writes} geschrieben, {conflicts} Konflikte")


# Context fallback helpers used by fill-ctx/fix-ctx and GGUF-derived setup.
_CTX_FROM_SIZE: list[tuple[float, int]] = [
    (14, 16384),
    (13, 32768),
    (12, 49152),
    (11, 65536),
    (10, 98304),
    (9, 131072),
]

_KV_BYTES: dict[str, float] = {
    "q8_0": 1.0,
    "q8_1": 2.0,
    "q5_1": 0.625,
    "q5_l": 0.625,
    "iq4_nl": 0.5,
    "q4_0": 0.5,
    "q4_1": 0.625,
    "f16": 2.0,
}


def _default_ctx_from_size(size_bytes: int, np: int = 1, k_cache: str = "q8_0", v_cache: str = "iq4_nl") -> int:
    gb = size_bytes / 1_000_000_000
    for limit, ctx in _CTX_FROM_SIZE:
        if gb > limit:
            base_ctx = ctx
            break
    else:
        base_ctx = 262144

    if np == 1:
        return base_ctx

    kv_ref = 1.5
    kv_actual = _KV_BYTES.get(k_cache, 2.0) + _KV_BYTES.get(v_cache, 2.0)
    scale = (kv_ref / kv_actual) / np
    return max(16384, int(base_ctx * scale))


def _max_ctx_from_vram(model_gb: float, np_val: int, nl: int, hd: int, kv_bytes: float) -> int:
    """Maximum context length that fits in usable VRAM.

    Formula:  ctx = (usable_vram - model_gb) / (np x nl x hd x 2 x kv_bytes / 1e9)
    """
    kv_gb_per_token = np_val * nl * hd * 2 * kv_bytes / 1_000_000_000
    if kv_gb_per_token <= 0:
        return 2048
    ctx = (_USABLE_VRAM_GB - model_gb) / kv_gb_per_token
    return max(2048, int(ctx))


def _canonical_key(mk: str, pub: str) -> str:
    """Build canonical registry key: publisher/model-name (cleaned)."""
    s = mk.strip().lower()
    s = re.sub(r"\.gguf$", "", s)
    s = re.sub(r"-(gguf|mxpr4)$", "", s)
    parsed_publisher, model_name, quant = decompose_model_identity(s)
    return build_model_identity(parsed_publisher or pub, model_name, quant)


def _benchmark_lms_models(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only installed records eligible for this benchmark registry."""
    eligible: list[dict[str, Any]] = []
    for model in models:
        if not is_registry_candidate(model):
            continue
        path = str(model.get("path") or model.get("indexedModelIdentifier") or "")
        size_bytes = model.get("sizeBytes", model.get("size_bytes", 0)) or 0
        if is_mtp_drafter(str(model.get("modelKey", "")), int(size_bytes or 0)):
            continue
        if path and is_support_file(path, str(model.get("architecture") or "")):
            continue
        eligible.append(model)
    return eligible


def _identity_aliases(key: str) -> set[str]:
    """Return stable aliases for publisher/model[@quant] identity matching."""
    raw = key.strip().lower()
    _base, separator, quant = raw.partition("@")
    publisher, model, parsed_quant = decompose_model_identity(raw)
    quant = parsed_quant.strip()
    if not model:
        return set()

    def compact(value: str) -> str:
        return re.sub(r"[-_.]", "", value)

    aliases: set[str] = set()
    normalized_model = normalize_model_name(model)
    for model_alias in (model, normalized_model, compact(model), compact(normalized_model)):
        base_alias = f"{publisher}/{model_alias}" if publisher else model_alias
        aliases.add(base_alias)
        if separator and quant:
            aliases.add(f"{base_alias}@{compact(quant)}")
    return aliases


def _lms_identity_keys(model: dict[str, Any]) -> set[str]:
    """Return base and variant-qualified registry identities for one LMS row."""
    model_key = str(model.get("modelKey", "")).strip()
    if not model_key:
        return set()
    publisher = str(model.get("publisher", "")).strip()
    base = _canonical_key(model_key, publisher)
    identities = {base}

    variant_values: list[str] = []
    selected = str(model.get("selectedVariant") or "").strip()
    if selected:
        variant_values.append(selected)
    raw_variants = model.get("variants") or []
    if isinstance(raw_variants, list):
        variant_values.extend(str(value).strip() for value in raw_variants if value)
    quant = _quant_from_lms_record(model) or ""
    if quant and "@" not in base:
        publisher_name, model_name, _existing_quant = decompose_model_identity(base)
        variant_values.append(build_model_identity(publisher_name, model_name, quant))

    for variant in variant_values:
        if "@" not in variant and quant:
            publisher_name, model_name, _existing_quant = decompose_model_identity(variant)
            variant = build_model_identity(publisher_name, model_name, quant)
        identities.add(_canonical_key(variant, publisher))
    return identities


def _lms_record_for_registry_key(
    registry_key: str,
    models: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Find an eligible LMS record by base identity and, for variants, quant."""
    registry_aliases = _identity_aliases(registry_key)
    has_quant = "@" in registry_key
    for model in models:
        if not is_registry_candidate(model):
            continue
        for identity in _lms_identity_keys(model):
            if has_quant and "@" not in identity:
                continue
            if not has_quant and "@" in identity:
                continue
            identity_aliases = _identity_aliases(identity)
            if has_quant:
                registry_aliases_to_compare = {alias for alias in registry_aliases if "@" in alias}
                identity_aliases = {alias for alias in identity_aliases if "@" in alias}
            else:
                registry_aliases_to_compare = {alias for alias in registry_aliases if "@" not in alias}
                identity_aliases = {alias for alias in identity_aliases if "@" not in alias}
            if registry_aliases_to_compare.intersection(identity_aliases):
                return model
    return None


def _lms_matches_registry_key(model: dict[str, Any], registry_key: str) -> bool:
    """Return whether one LMS row represents a registry base/quant identity."""
    registry_aliases = _identity_aliases(registry_key)
    has_quant = "@" in registry_key
    for identity in _lms_identity_keys(model):
        if has_quant and "@" not in identity:
            continue
        if not has_quant and "@" in identity:
            continue
        identity_aliases = _identity_aliases(identity)
        if has_quant:
            registry_aliases_to_compare = {alias for alias in registry_aliases if "@" in alias}
            identity_aliases = {alias for alias in identity_aliases if "@" in alias}
        else:
            registry_aliases_to_compare = {alias for alias in registry_aliases if "@" not in alias}
            identity_aliases = {alias for alias in identity_aliases if "@" not in alias}
        if registry_aliases_to_compare.intersection(identity_aliases):
            return True
    return False


def _quant_from_lms_record(model: dict[str, Any]) -> str | None:
    """Return the selected quantization name from an LMS record, if present."""
    selected = str(model.get("selectedVariant") or "").strip()
    if "@" in selected:
        return selected.rsplit("@", 1)[1].lower()
    quantization = model.get("quantization") or {}
    if isinstance(quantization, dict):
        quant = str(quantization.get("name", "")).strip()
        if quant:
            return quant.lower()
    searchable = " ".join(
        str(model.get(field, ""))
        for field in ("modelKey", "path", "indexedModelIdentifier")
    ).lower()
    match = re.search(r"(?<![a-z0-9])(iq\d_[a-z0-9]+|q\d(?:_[a-z0-9]+)+|mxfp4|nvfp4|fp16|f16)(?![a-z0-9])", searchable)
    if match:
        return match.group(1)
    return None


def _canonical_lms_key(model: dict[str, Any]) -> str:
    """Build the exact publisher/model@quant key represented by an LMS row."""
    model_key = str(model.get("modelKey") or model.get("key") or "").strip()
    publisher = str(model.get("publisher", "")).strip()
    base = _canonical_key(model_key, publisher)
    selected = str(model.get("selectedVariant") or "").strip()
    if "@" in selected:
        return _canonical_key(selected, publisher)
    quant = _quant_from_lms_record(model)
    if quant and "@" not in base:
        publisher_name, model_name, _existing_quant = decompose_model_identity(base)
        return build_model_identity(publisher_name, model_name, quant)
    return base


def _config_matches_lms_model(config: dict[str, Any], model: dict[str, Any]) -> bool:
    """Return whether a local config belongs to an installed LMS model.

    Configs can outlive deleted LM Studio models.  Reuse the same publisher,
    base-name and quant-aware matcher as registry/config synchronization so a
    stale JSON cannot create a false drift or conflict during ``sync``.
    """
    model_key = _canonical_lms_key(model)
    if not model_key:
        return False
    return find_config_for_registry_key(model_key, [config]) is not None


def _rekey_registry_to_lms(
    registry: dict[str, Any],
    models: list[dict[str, Any]],
) -> int:
    """Align existing registry keys with current LMS names without changing values."""
    changed = 0
    for old_key in list(registry):
        entry = registry.get(old_key)
        if not isinstance(entry, dict) or not is_registry_candidate({"modelKey": old_key}):
            continue
        model = _lms_record_for_registry_key(old_key, models)
        if model is None:
            continue
        new_key = _canonical_lms_key(model)
        if not new_key or new_key == old_key:
            continue
        if new_key in registry:
            print(f"  [SKIP] Registry-Key {old_key} -> {new_key}: Ziel-Key existiert bereits")
            continue
        registry[new_key] = registry.pop(old_key)
        changed += 1
        print(f"  [FIX] Registry-Key {old_key} -> {new_key} (LMS-Identität)")
    if changed:
        save_registry(registry)
    return changed


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


def _read_gguf_arch(
    model_path: str,
) -> tuple[int | None, int | None, bool | None, int | None, int | None]:
    """Read n_layers, hidden_dim, reasoning, context_length and expert_count from GGUF header.

    Returns (block_count, embedding_length, is_reasoning, context_length, expert_count)
    where is_reasoning is True/False if the chat_template was readable (else None),
    and expert_count is the MoE expert count or None if the key is absent.
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
                return None, None, None, None, None
            f.read(4 + 8 + 8)  # version, tensor_count, metadata_count
            block_count = embedding_length = context_length = expert_count = None
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
                elif key.endswith(".expert_count"):
                    expert_count = int(val)
                elif key == "tokenizer.chat_template":
                    chat_template = str(val)
                # Erst abbrechen, wenn ALLE vier Werte gelesen sind: tokenizer.chat_template
                # steht im GGUF-Header meist NACH block_count/embedding_length/context_length.
                # expert_count (MoE) folgt dem gleichen arch.*-Präfix und ist in der Regel
                # ebenfalls schon gelesen; fehlt der Key, bleibt es None (dense Model).
                if (
                    block_count is not None
                    and embedding_length is not None
                    and context_length is not None
                    and chat_template is not None
                ):
                    break
        is_reasoning = _detect_reasoning_from_template(chat_template) if chat_template else False
        return block_count, embedding_length, is_reasoning, context_length, expert_count
    except (OSError, ValueError, struct.error):
        # GGUF header parse failures (corrupt file, unsupported version, etc.)
        return None, None, None, None, None


def _read_gguf_base_arch(model_path: str) -> str | None:
    """Read the provider-neutral ``general.architecture`` GGUF identifier."""
    try:
        from gguf import GGUFReader

        field = GGUFReader(model_path).fields.get("general.architecture")
        if field is None:
            return None
        value = field.contents()
        return value.strip().lower() if isinstance(value, str) and value.strip() else None
    except (ImportError, KeyError, OSError, ValueError, RuntimeError):
        return None


_REASONING_TOKEN_RE = re.compile(
    r"<\s*/?\s*(?:think|thinking|thought)\s*>|"
    r"<\|channel>\s*(?:thought|think)|"
    r"<\|channel\|>\s*analysis",
    re.IGNORECASE,
)


_KNOWN_QUANTS = (
    "q1_0", "q2_k", "q3_k_s", "q3_k_m", "q3_k_l", "q4_0", "q4_k_s", "q4_k_m",
    "q5_0", "q5_k_s", "q5_k_m", "q6_k", "q8_0_i", "q8_0", "iq2_xxs", "iq2_xs", "iq2_s",
    "iq2_m", "iq3_xxs", "iq3_xs", "iq3_s", "iq3_m", "iq4_xs", "iq4_nl",
    "q2_k_s", "q3_k_xs", "q4_k_xl", "mxfp4", "fp16", "f16",
)


def _gguf_quant_from_header(gguf_path: str) -> str | None:
    """Extract quantization type from GGUF filename.

    The GGUF header does not store the quant type directly, but the filename
    follows conventions like ``model-name-Q3_K_S.gguf``. This function parses
    the filename to extract the quant suffix.

    Returns the quant string (e.g. "Q3_K_S") or None if not determinable.
    """
    fname = os.path.basename(gguf_path).lower()
    fname = fname.removesuffix(".gguf")

    # Try to find a known quant suffix in the filename
    for quant in _KNOWN_QUANTS:
        if quant in fname:
            # Return in uppercase convention
            return quant.upper()

    # Fallback: try to extract after the last hyphen if it looks like a quant
    parts = fname.rsplit("-", 1)
    if len(parts) == 2 and parts[1] and parts[1][0] in ("q", "i", "f", "m"):
        return parts[1].upper()

    return None


def _detect_reasoning_from_template(template: str) -> bool:
    """Check if a GGUF chat_template supports reasoning/thinking mode.

    Uses regex for token patterns (avoids false positives from
    accidental substring matches) and substring for the well-known
    Jinja llama.cpp variables.
    """
    if "enable_thinking" in template or "reasoning_effort" in template:
        return True
    return bool(_REASONING_TOKEN_RE.search(template))


def _read_gguf_chat_template(model_path: str | Path) -> str | None:
    """Read the embedded ``tokenizer.chat_template`` from a GGUF file."""
    try:
        from gguf import GGUFReader

        field = GGUFReader(str(model_path)).fields.get("tokenizer.chat_template")
        if field is None:
            return None
        value = field.contents()
        return value if isinstance(value, str) and value.strip() else None
    except (ImportError, KeyError, OSError, ValueError, RuntimeError):
        return None


_DEFAULT_GGUF_ROOTS = configured_gguf_roots()
MODELS_CACHE = _DEFAULT_GGUF_ROOTS[0]
_DEFAULT_MODELS_CACHE = MODELS_CACHE


def _gguf_roots() -> tuple[Path, ...]:
    """Return the configured roots, honoring the legacy test seam."""
    if MODELS_CACHE != _DEFAULT_MODELS_CACHE:
        # Existing callers and tests patch MODELS_CACHE to isolate a scan.
        return (MODELS_CACHE,)
    return _DEFAULT_GGUF_ROOTS


def _find_gguf_relative_path(relative_path: str | Path) -> Path | None:
    """Find an LMS-relative path in primary-first root order."""
    candidate = Path(relative_path)
    for root in _gguf_roots():
        path = root / candidate
        if path.is_file():
            return path
    return None

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
    lms_models = _benchmark_lms_models(_run_lms_ls())
    unique: dict[str, str] = {}
    for m in lms_models:
        rp = m.get("path", "")
        if not rp:
            continue
        full_path = _find_gguf_relative_path(rp)
        if full_path is None:
            continue
        full_path = str(full_path)
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
            nl, hd, is_reasoning, ctx, _ = fut.result()
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

    print(
        f"[OK] fill-arch: {updated} n_layers/hidden_dim gesetzt, {reasoning_updated} reasoning gesetzt, {skipped_has} bereits vorhanden, {skipped_no} kein GGUF-Match ({len(gguf_arch)} GGUF-Dateien ausgewertet)"
    )

    if updated or reasoning_updated:
        save_registry(reg)


def cmd_fill_quant() -> None:
    """Fill missing @quant in registry keys from GGUF headers (Source of Truth).

    For registry entries without @quant (base entries), reads the installed
    GGUF header to determine the actual quantization. Renames the key to
    publisher/model@quant and sets the quants field.

    Source of Truth: GGUF header (via lms ls path -> file -> header parse).
    Base entries without @quant are ambiguous — the triple
    (publisher, model, quant) is the unique identity.
    """
    reg = load_registry()
    if not reg:
        print("[ERROR] Leere Registry")
        sys.exit(1)

    lms_models = _benchmark_lms_models(_run_lms_ls())
    if not lms_models:
        print("[WARN] lms ls lieferte keine Modelle - fill-quant übersprungen")
        return

    # Build lookup: normalized base key -> GGUF path
    lms_by_base: dict[str, str] = {}
    lms_pub_base: dict[str, str] = {}
    for m in lms_models:
        mk = str(m.get("modelKey", "")).lower()
        rp = m.get("path", "")
        if not rp:
            continue
        full_path = _find_gguf_relative_path(rp)
        if full_path is None:
            continue
        full_path = str(full_path)
        base = normalize_model_name(mk).split("@")[0]
        if base not in lms_by_base:
            lms_by_base[base] = full_path
            pub = str(m.get("publisher", "")).strip().lower()
            lms_pub_base[base] = pub

    updated = 0
    for key in list(reg.keys()):
        if not isinstance(reg[key], dict):
            continue
        if "@" in key:
            continue  # already has quant

        lms_record = _lms_record_for_registry_key(key, lms_models)
        base = normalize_model_name(key)
        gguf_path = lms_by_base.get(base)
        quant = _quant_from_lms_record(lms_record) if lms_record is not None else None
        if quant is None and gguf_path is not None:
            # Fallback for older LMS records without quantization metadata.
            quant = _gguf_quant_from_header(gguf_path)
        if not quant:
            print(f"  [SKIP] {key}: Quant konnte aus LMS/GGUF nicht gelesen werden")
            continue

        new_key = _canonical_lms_key(lms_record) if lms_record is not None else ""
        if not new_key:
            pub = lms_pub_base.get(base, key.split("/")[0] if "/" in key else "")
            model_part = base.split("/", 1)[1] if "/" in base else base
            new_key = build_model_identity(pub, model_part, quant)

        # Don't overwrite if new key already exists
        if new_key in reg and new_key != key:
            print(f"  [SKIP] {key}: Ziel-Key {new_key} existiert bereits")
            continue

        entry = reg.pop(key)
        entry["quants"] = quant.upper()
        reg[new_key] = entry
        updated += 1
        print(f"  [FIX] {key} -> {new_key} (quants={quant.upper()})")

    if updated:
        save_registry(reg)
    print(f"[OK] fill-quant: {updated} Keys mit @quant ergänzt (Quelle: GGUF-Header)")


# ── sync-from-gguf command (Auto-Fix, Feld-Ownership) ───────────────


def _find_gguf_arch_for_key(reg_key: str, gguf_arch: dict[str, tuple[int, int, bool | None, int | None]]) -> (
    tuple[int, int, bool | None, int | None] | None
):
    """GGUF-Architektur zu einem Registry-Key finden (Exact → @strip → Fuzzy)."""
    normalized_key = normalize_model_name(reg_key)
    found = gguf_arch.get(normalized_key)
    if not found:
        found = gguf_arch.get(normalized_key.split("@")[0])
    if not found:
        for gk, gv in gguf_arch.items():
            if normalized_key in gk or gk in normalized_key:
                found = gv
                break
    return found


def cmd_sync_from_gguf() -> None:
    """Registry-Auto-Fix aus GGUF-Headern (Feld-Ownership: gguf→registry, auto_fix).

    Korrigiert n_layers, hidden_dim, max_context_length und arch aus den
    unveraenderlichen GGUF-Headern, wenn die Registry abweicht. Berichtet
    jede Aenderung. reasoning bleibt unangetastet, wenn es bereits gesetzt
    ist (Interpretationsspielraum - nur melden, nicht ueberschreiben).
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
    lms_models = _benchmark_lms_models(_run_lms_ls())
    unique: dict[str, str] = {}
    for m in lms_models:
        rp = m.get("path", "")
        if not rp:
            continue
        full_path = _find_gguf_relative_path(rp)
        if full_path is None:
            continue
        full_path = str(full_path)
        if _is_support_file(rp):
            continue
        key = normalize_model_name(m.get("modelKey", "")).lower()
        base = key.split("@")[0]
        if base not in unique:
            unique[base] = full_path
    print(f"  -> {len(unique)} einzigartige Modelle (von {len(lms_models)} GGUF-Dateien)")

    print("[3] GGUF-Header parallel parsen ...")
    gguf_arch: dict[str, tuple[int, int, bool | None, int | None]] = {}
    gguf_family: dict[str, str] = {}
    gguf_moe: dict[str, bool] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        fut_to_base = {pool.submit(_read_gguf_arch, p): b for b, p in unique.items()}
        for i, fut in enumerate(concurrent.futures.as_completed(fut_to_base), 1):
            base = fut_to_base[fut]
            nl, hd, is_reasoning, ctx, exp = fut.result()
            architecture_family = _read_gguf_base_arch(unique[base])
            if architecture_family:
                gguf_family[base] = architecture_family
            if nl and hd:
                gguf_arch[base] = (nl, hd, is_reasoning, ctx)
            if exp is not None:
                gguf_moe[base] = bool(exp)
            if i % 10 == 0:
                print(f"     ({i}/{len(unique)})")
    print(f"  -> {len(gguf_arch)} mit n_layers/hidden_dim/context_length")

    print("[4] Registry-Einträge mit GGUF-Quelle abgleichen (Auto-Fix) ...")
    fixes: list[str] = []
    for key, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        found = _find_gguf_arch_for_key(key, gguf_arch)
        if not found:
            continue

        nl, hd, is_reasoning, ctx = found
        # arch: moe/mtp/dense aus GGUF expert_count
        base = normalize_model_name(key).split("@")[0]
        architecture_family = gguf_family.get(base)
        if architecture_family and entry.get("architecture_family") != architecture_family:
            old = entry.get("architecture_family")
            entry["architecture_family"] = architecture_family
            fixes.append(
                f"{key}: architecture_family {old!r} -> {architecture_family!r} (GGUF general.architecture)"
            )
        exp = gguf_moe.get(base)
        expected_arch = "moe" if exp else None
        if expected_arch is not None and entry.get("arch") != expected_arch:
            old = entry.get("arch")
            entry["arch"] = expected_arch
            fixes.append(f"{key}: arch {old!r} -> {expected_arch!r} (GGUF expert_count={exp})")

        if ctx is not None and entry.get("max_context_length") != ctx:
            old = entry.get("max_context_length")
            entry["max_context_length"] = int(ctx)
            fixes.append(f"{key}: max_context_length {old!r} -> {ctx} (GGUF-Header)")

        if entry.get("n_layers") != nl:
            old = entry.get("n_layers")
            entry["n_layers"] = int(nl)
            fixes.append(f"{key}: n_layers {old!r} -> {nl} (GGUF-Header)")

        if entry.get("hidden_dim") != hd:
            old = entry.get("hidden_dim")
            entry["hidden_dim"] = int(hd)
            fixes.append(f"{key}: hidden_dim {old!r} -> {hd} (GGUF-Header)")

    for f in fixes:
        print(f"  [FIX] {f}")
    print(f"\n[OK] sync-from-gguf: {len(fixes)} Korrekturen ({len(gguf_arch)} GGUF-Dateien ausgewertet)")

    if fixes:
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
    lms_models = _benchmark_lms_models(_run_lms_ls())
    unique: dict[str, str] = {}
    for m in lms_models:
        rp = m.get("path", "")
        if not rp:
            continue
        full_path = _find_gguf_relative_path(rp)
        if full_path is None:
            continue
        full_path = str(full_path)
        if _is_support_file(rp):
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
            _, _, is_reasoning, _, _ = fut.result()
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

    print(
        f"[OK] fill-reasoning: {updated} reasoning gesetzt, {skipped_has} bereits vorhanden, {skipped_no_match} kein GGUF-Match ({len(gguf_reasoning)} GGUF-Dateien ausgewertet)"
    )


# ── sync-templates command ─────────────────────────────────────────

TEMPLATE_DIR = PROJECT_ROOT / "doc-git" / "Jinja-Chat-Templates"

_BLUEPRINT_CACHE: dict[str, Any] | None = None


def _load_blueprints() -> dict[str, Any]:
    """Load blueprint_definitions.yaml (SSOT fuer custom templates/stop-strings)."""
    global _BLUEPRINT_CACHE
    if _BLUEPRINT_CACHE is None:
        from ruamel.yaml import YAML
        y = YAML()
        bp_path = PROJECT_ROOT / "doc-git" / "blueprint_definitions.yaml"
        with open(bp_path, encoding="utf-8") as f:
            data = y.load(f)
        _BLUEPRINT_CACHE = (data or {}).get("blueprints", {})
    return _BLUEPRINT_CACHE


def _registry_template_name(model_key: str) -> str | None:
    """Resolve the template filename for a registry key.

    An ``explicit_file`` policy is an intentional model/provider-specific
    override. Otherwise the Blueprint remains the shared source of truth and
    the registry ``template`` field is kept as a legacy fallback.
    """
    reg = load_registry()
    entry = reg.get(model_key) or {}
    if entry.get("template_policy") == "explicit_file":
        tpl = entry.get("template")
        return str(tpl) if tpl else None
    bp_name = entry.get("blueprint") or "default_chat"
    bp = _load_blueprints().get(bp_name) or {}
    name = resolve_template_name(bp, model_key)
    if name:
        return name
    tpl = entry.get("template")
    return str(tpl) if tpl else None


def cmd_sync_templates() -> None:
    """Write promptTemplate from blueprint-defined templates into configs missing it.

    Blueprint-driven (SSOT): jedes Registry-Entry, dessen Blueprint eine
    ``template``/``template_map``-Definition besitzt, wird gegen seine Config
    geprueft; fehlt/leer ist das Feld ``llm.prediction.promptTemplate``, wird
    der Inhalt der .jinja-Datei geschrieben. Behebt die validate-Kategorie
    ``template_missing_config``. Das Registry-``template:``-Feld gilt als
    veraltet (Fallback).
    """
    reg = load_registry()
    cfgs = read_lms_configs(CONFIG_ROOT)
    added = skipped = errors = 0
    for model_key, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        tpl_name = _registry_template_name(model_key)
        if not tpl_name:
            continue
        tpl_path = TEMPLATE_DIR / tpl_name
        if not tpl_path.exists():
            print(f"  [ERROR] {model_key}: Template-Datei fehlt ({tpl_path})")
            errors += 1
            continue
        match = find_config_for_registry_key(model_key, cfgs)
        if match is None:
            print(f"  [SKIP] {model_key}: keine Config-JSON gefunden")
            skipped += 1
            continue
        json_path = Path(match["json_path"])
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            template_content = tpl_path.read_text(encoding="utf-8")
            fields = data.setdefault("operation", {}).setdefault("fields", [])
            found = False
            for field in fields:
                if field.get("key") == "llm.prediction.promptTemplate":
                    found = True
                    if not field.get("value"):
                        field["value"] = template_content
                        json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                        print(f"  [FIX] {model_key}: promptTemplate ergänzt")
                        added += 1
                    else:
                        skipped += 1
                    break
            if not found:
                fields.append({"key": "llm.prediction.promptTemplate", "value": template_content})
                json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"  [FIX] {model_key}: promptTemplate ergänzt")
                added += 1
        except Exception as e:
            print(f"  [ERROR] {model_key}: {e}")
            errors += 1
    print(f"\n[OK] sync-templates: {added} Configs aktualisiert, {skipped} übersprungen, {errors} Fehler")


def _find_lms_gguf_for_registry_key(model_key: str) -> Path | None:
    """Resolve the installed LM Studio GGUF for a Registry key."""
    target = normalize_model_name(model_key).split("@")[0]
    target_suffix = target.rsplit("/", 1)[-1]
    for model in _benchmark_lms_models(_run_lms_ls()):
        candidate = normalize_model_name(str(model.get("modelKey", ""))).split("@")[0]
        if candidate not in {target, target_suffix} and candidate.rsplit("/", 1)[-1] != target_suffix:
            continue
        relative_path = str(model.get("path", ""))
        candidate_path = _find_gguf_relative_path(relative_path)
        if candidate_path is not None and not _is_support_file(relative_path):
            return candidate_path
    return None


def cmd_sync_template_from_gguf(model_key: str) -> int:
    """Copy one GGUF-embedded chat template into its LM Studio config.

    This is an explicit runtime-artifact repair. It never writes the Registry
    and refuses to replace an already populated config template.
    """
    configs = read_lms_configs(CONFIG_ROOT)
    config = find_config_for_registry_key(model_key, configs)
    if config is None:
        print(f"[ERROR] {model_key}: keine passende LM-Studio-Config gefunden")
        return 1

    gguf_path = _find_lms_gguf_for_registry_key(model_key)
    if gguf_path is None:
        print(f"[ERROR] {model_key}: keine passende lokale GGUF-Datei gefunden")
        return 1
    template = _read_gguf_chat_template(gguf_path)
    if template is None:
        print(f"[ERROR] {model_key}: GGUF enthält kein lesbares tokenizer.chat_template")
        return 1

    json_path = Path(config["json_path"])
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        fields = data.setdefault("operation", {}).setdefault("fields", [])
        for field in fields:
            if field.get("key") != "llm.prediction.promptTemplate":
                continue
            if field.get("value"):
                print(f"[SKIP] {model_key}: promptTemplate ist bereits befüllt ({json_path})")
                return 0
            field["value"] = template
            break
        else:
            fields.append({"key": "llm.prediction.promptTemplate", "value": template})
        json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except (OSError, TypeError, ValueError) as exc:
        print(f"[ERROR] {model_key}: Config konnte nicht aktualisiert werden: {exc}")
        return 1

    print(
        f"[FIX] {model_key}: tokenizer.chat_template aus {gguf_path.name} "
        f"in {json_path.name} übernommen ({len(template)} Zeichen)"
    )
    return 0


# ── validate command ───────────────────────────────────────────────


def _hub_model_yaml(entry: dict[str, Any], model_key: str) -> tuple[Path, dict[str, Any]] | None:
    """Locate LM Studio Hub model.yaml for a registry entry (publisher/name)."""
    publisher = str(entry.get("publisher", "")).strip()
    hub_models = Path.home() / ".lmstudio" / "hub" / "models"
    if not publisher or not hub_models.is_dir():
        return None
    pub_dir = hub_models / publisher
    if not pub_dir.is_dir():
        return None
    name = model_key.split("/", 1)[-1] if "/" in model_key else model_key
    norm = name.lower().replace("_", "-")
    reader = YAML(typ="safe")
    candidates: list[Path] = [pub_dir / name / "model.yaml"]
    candidates += sorted(d / "model.yaml" for d in pub_dir.iterdir() if d.is_dir() and d.name.lower().replace("_", "-") == norm)
    seen: set[Path] = set()
    for cand in candidates:
        if cand in seen or not cand.is_file():
            continue
        seen.add(cand)
        try:
            with cand.open(encoding="utf-8") as f:
                return cand, dict(reader.load(f) or {})
        except Exception:  # noqa: S112 - kaputte Hub-model.yaml ueberspringen
            continue
    for d in sorted(pub_dir.iterdir()):
        cand = d / "model.yaml"
        if not cand.is_file():
            continue
        try:
            with cand.open(encoding="utf-8") as f:
                data = dict(reader.load(f) or {})
            if str(data.get("model", "")).split("/", 1)[-1] == name:
                return cand, data
        except Exception:  # noqa: S112 - kaputte Hub-model.yaml ueberspringen
            continue
    return None


def _write_repro_issues(reg: dict[str, RegistryEntry], errors: dict[str, list[str]], verbose: bool) -> None:
    """Write doc-git/Review-Artifacts/repro_issues.md: validate errors + hub diffs.

    Repro artifact for the review: every registry decision (context_length,
    max_context_length, arch, reasoning, capabilities) is checked against the
    LM Studio Hub model.yaml (metadataOverrides); deviations are documented as
    'REPRO-Check'. An existing file is overwritten.
    """
    artifacts_dir = PROJECT_ROOT / "doc-git" / "Review-Artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    out = artifacts_dir / "repro_issues.md"

    lines: list[str] = [
        "# Repro-Issues: model_registry.yaml vs. LM Studio Hub",
        "",
        "Generated automatically: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "",
        "Source of truth for model facts are the GGUF files (immutable).",
        "The `model_registry.yaml` is editable (python programs/manual) and is",
        "checked here against the Hub `model.yaml` (`metadataOverrides`), which is",
        "shipped by LM Studio and never touched anywhere in the process.",
        "",
        "## Validate summary",
        "",
    ]
    total = sum(len(v) for v in errors.values())
    lines.append(f"- **Total issues (validate):** {total}")
    for check, items in errors.items():
        lines.append(f"- `{check}`: {len(items)}")
    lines.append("")

    # ── Repro checks: registry vs. hub ─────────────────────────────
    lines.append("## Hub deviations (Registry vs. model.yaml)")
    lines.append("")
    hub_diffs: list[str] = []
    hub_missing: list[str] = []
    for model_key, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        found = _hub_model_yaml(entry, model_key)
        if found is None:
            if entry.get("file_size_bytes"):
                if "@" in model_key:
                    hub_missing.append(
                        f"- **{model_key}**: quant variant without its own model.yaml "
                        f"(base model in hub carries the architecture info)"
                    )
                else:
                    hub_missing.append(f"- **{model_key}**: no hub model.yaml found (registry has GGUF size)")
            continue
        hub_path, hub = found
        mo = hub.get("metadataOverrides") or {}
        archs = mo.get("architectures") or []
        ctxs = mo.get("contextLengths") or []
        reason = mo.get("reasoning")
        diffs: list[str] = []
        if archs:
            reg_arch = str(entry.get("arch", ""))
            archs_l = [str(a).lower() for a in archs]
            if reg_arch and reg_arch.lower() not in archs_l and reg_arch not in ("dense", "moe"):
                diffs.append(f"arch: Registry='{reg_arch}' vs Hub={archs}")
        if ctxs:
            max_ctx = max(int(c) for c in ctxs if isinstance(c, (int, float)))
            reg_max = entry.get("max_context_length")
            reg_ctx = entry.get("context_length")
            if reg_max is not None and int(reg_max) != max_ctx:
                diffs.append(f"max_context_length: Registry={reg_max} vs Hub={max_ctx}")
            if reg_ctx is not None and int(reg_ctx) > max_ctx:
                diffs.append(f"context_length: Registry={reg_ctx} > Hub-Max={max_ctx}")
        if reason is not None:
            reg_reason = str(entry.get("reasoning", "")).lower()
            hub_reason = str(reason).lower()
            if reg_reason and hub_reason in ("true", "false"):
                reg_bool = reg_reason not in ("false", "instruct", "none")
                hub_bool = hub_reason == "true"
                if reg_bool != hub_bool:
                    diffs.append(f"reasoning: Registry='{reg_reason}' vs Hub={reason}")
        if diffs:
            hub_diffs.append(f"- **{model_key}** ({hub_path.parent.name}):\n" + "\n".join(f"    - {d}" for d in diffs))

    if hub_diffs:
        lines.append(f"{len(hub_diffs)} registry entries deviate from the hub:")
        lines.append("")
        lines.extend(hub_diffs)
    else:
        lines.append("No deviations between registry and hub model.yaml.")
    lines.append("")

    if hub_missing:
        lines.append("## Hub notes (no model.yaml in local hub)")
        lines.append("")
        lines.append(
            f"{len(hub_missing)} entries have no local hub model.yaml "
            "(no comparison possible, manual GGUF check required):"
        )
        lines.append("")
        lines.extend(hub_missing)
        lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[REPRO] Artifact written: {out}")
    print(f"[REPRO] {len(hub_diffs)} hub deviations, {len(hub_missing)} without hub model.yaml documented.")


def _gguf_drift_errors(reg: dict[str, Any]) -> list[str]:
    """GGUF-Header vs. Registry: auto_fix-Felder (Feld-Ownership) abgleichen.

    Liest die GGUF-Header (via lms ls, parallel) und meldet Abweichungen bei
    n_layers/hidden_dim/max_context_length/arch. Fixbar durch
    'sync-from-gguf' (kein Schreiben hier - validate bleibt read-only).
    reasoning wird bewusst nicht geprueft (Interpretationsspielraum).
    """
    try:
        lms_models = _benchmark_lms_models(_run_lms_ls())
    except Exception as e:  # lms nicht erreichbar: Check ueberspringen
        print(f"[WARN] gguf_header_drift uebersprungen (lms ls fehlgeschlagen: {e})")
        return []

    unique: dict[str, str] = {}
    for m in lms_models:
        rp = m.get("path", "")
        if not rp:
            continue
        full_path = _find_gguf_relative_path(rp)
        if full_path is None:
            continue
        full_path = str(full_path)
        key = normalize_model_name(m.get("modelKey", "")).lower()
        base = key.split("@")[0]
        if base not in unique:
            unique[base] = full_path

    gguf_arch: dict[str, tuple[int, int, bool | None, int | None]] = {}
    gguf_moe: dict[str, bool] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        fut_to_base = {pool.submit(_read_gguf_arch, p): b for b, p in unique.items()}
        for fut in concurrent.futures.as_completed(fut_to_base):
            base = fut_to_base[fut]
            nl, hd, is_reasoning, ctx, exp = fut.result()
            if nl and hd:
                gguf_arch[base] = (nl, hd, is_reasoning, ctx)
            if exp is not None:
                gguf_moe[base] = bool(exp)

    out: list[str] = []
    for key, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        found = _find_gguf_arch_for_key(key, gguf_arch)
        if not found:
            continue
        nl, hd, is_reasoning, ctx = found
        base = normalize_model_name(key).split("@")[0]
        exp = gguf_moe.get(base)

        if exp is True and entry.get("arch") != "moe":
            out.append(
                f"{key}: arch={entry['arch']} vs GGUF expert_count=True (Quelle: gguf, Auto-Fix via sync-from-gguf)"
            )
        if ctx is not None and entry.get("max_context_length") != ctx:
            out.append(
                f"{key}: max_context_length={entry.get('max_context_length')} vs GGUF={ctx} (Quelle: gguf, Auto-Fix via sync-from-gguf)"
            )
        if entry.get("n_layers") != nl:
            out.append(
                f"{key}: n_layers={entry.get('n_layers')} vs GGUF={nl} (Quelle: gguf, Auto-Fix via sync-from-gguf)"
            )
        if entry.get("hidden_dim") != hd:
            out.append(
                f"{key}: hidden_dim={entry.get('hidden_dim')} vs GGUF={hd} (Quelle: gguf, Auto-Fix via sync-from-gguf)"
            )
    return out


def cmd_validate(verbose: bool = False, repro: bool = False, ci: bool = False) -> dict[str, Any]:
    """Validate model_registry.yaml consistency: templates, configs, overrides.

    verbose: zeigt alle Einzelprobleme (statt nur die ersten 10 je Kategorie).
    repro:   schreibt zusätzlich doc-git/Review-Artifacts/repro_issues.md mit
             GGUF-Hub-Abweichungen (Registry vs. LM-Studio-Hub model.yaml).
    ci:      headless static checks only; skips LM-Studio configs and local GGUFs.

    Returns dict with error counts per check category.
    """
    reg = load_registry()
    cfgs = [] if ci else read_lms_configs(CONFIG_ROOT)
    errors: dict[str, list[str]] = {
        "template_missing_file": [],
        "template_missing_config": [],
        "missing_reasoning": [],
        "missing_capabilities": [],
        "missing_blueprint": [],
        "sampling_invalid": [],
        "sampling_research_status_invalid": [],
        "registry_no_config": [],
        "reasoning_arch_mismatch": [],
        "config_context_drift": [],
        "config_np_ukv_drift": [],
        "config_context_too_small": [],
        "gguf_header_drift": [],
    }

    # ── Check 1: template references existent .jinja file ─────────
    # Explicit registry files are intentional provider/model-specific
    # overrides; all other templates come from the Blueprint SSOT.
    for model_key, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        tpl = _registry_template_name(model_key)
        if tpl:
            tpl_path = TEMPLATE_DIR / tpl
            if not tpl_path.exists():
                errors["template_missing_file"].append(
                    f"{model_key}: template='{tpl}' -> Datei nicht gefunden ({tpl_path})"
                )

    # ── Check 2: blueprint template -> Config JSON promptTemplate ──
    for model_key, entry in reg.items():
        if ci:
            continue
        if not isinstance(entry, dict):
            continue
        tpl = _registry_template_name(model_key)
        if not tpl:
            continue
        match = find_config_for_registry_key(model_key, cfgs)
        if match is None:
            errors["template_missing_config"].append(
                f"{model_key}: template='{tpl}' definiert, "
                f"aber Config-JSON nicht gefunden (auch nach fallback matching)"
            )
            continue
        json_path = Path(match["json_path"])
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            errors["template_missing_config"].append(f"{model_key}: Config-JSON nicht lesbar ({json_path})")
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
                f"{model_key}: template='{tpl}' definiert, "
                f"aber promptTemplate in Config fehlt/leer ({json_path})"
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

    # ── Check 4a: Sampling schema/ranges ────────────────────────────
    for model_key, entry in reg.items():
        if not isinstance(entry, dict) or "sampling" not in entry:
            continue
        for issue in validate_sampling_block(entry["sampling"]):
            errors["sampling_invalid"].append(f"{model_key}: {issue}")

    for model_key, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        sampling_block = entry.get("sampling") if isinstance(entry.get("sampling"), dict) else {}
        status = entry.get("sampling_research_status") or sampling_block.get("sampling_research_status")
        if status is not None and status not in RESEARCH_STATUSES:
            errors["sampling_research_status_invalid"].append(f"{model_key}: {status!r}")

    # ── Check 4b: Modell-Identität = Publisher + Modellname + Quantisierung ──
    # Jeder Registry-Key MUSS die Form publisher/modelname@quant haben.
    # Base-Entries ohne @quant sind nicht eindeutig und gehören entfernt.
    from model_identity import decompose_model_identity
    for model_key in reg:
        pub, _model, quant = decompose_model_identity(model_key)
        if not pub:
            errors.setdefault("missing_publisher", []).append(
                f"{model_key}: kein Publisher-Prefix (MUSS publisher/model@quant sein)"
            )
        if not quant:
            errors.setdefault("missing_quant", []).append(
                f"{model_key}: keine @quant (MUSS publisher/model@quant sein)"
            )

    # ── Check 5: Registry name findet Config JSON (mit fallback matching) ──
    for model_key, entry in reg.items():
        if ci:
            continue
        if not isinstance(entry, dict):
            continue
        # Skip models without GGUF installed (no config expected)
        if not entry.get("file_size_bytes"):
            continue
        match = find_config_for_registry_key(model_key, cfgs)
        if match is None:
            rk = normalize_model_name(model_key)
            errors["registry_no_config"].append(f"{model_key}: keine passende Config-JSON gefunden (normalized: {rk})")

    # ── Check 7: reasoning stimmt mit Architektur-Map überein ──────
    for model_key, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        reasoning = entry.get("reasoning")
        arch_raw = entry.get("architecture_family") or entry.get("arch", "")
        if not reasoning or not arch_raw:
            continue
        # Several GGUF bases are implementation families, not reasoning
        # contracts: e.g. ``deepseek2`` contains both GLM and Moonlight,
        # ``llama`` contains instruct and reasoning derivatives, and Gemma-4
        # has category-dependent thinking.  Only Qwen's name exceptions and
        # GPT-OSS have a stable architecture-level reasoning contract here.
        arch_normalized = str(arch_raw).lower().replace(".", "")
        if not (arch_normalized.startswith("qwen") or arch_normalized == "gpt-oss"):
            continue
        detected = None
        arch_lower = arch_normalized  # normalize: "Qwen3.5" → "qwen35"
        for arch_key, rtype in _ARCH_REASONING_MAP.items():
            if arch_key in arch_lower:
                detected = rtype
                break
        if detected is not None and reasoning != detected:
            errors["reasoning_arch_mismatch"].append(
                f"{model_key}: reasoning={reasoning}, aber Architektur '{arch_raw}' erwartet '{detected}'"
            )

    # ── Check 8: JSON-Config vs. Registry (Drift) ──────────────────
    # Die JSON-Configs sind die Quelle (LMS GUI). Registry weicht ab?
    # context_length: nur WARNEN wenn Config < Registry-Erwartung oder
    # Context > native max_context_length (dann ist Config inkonsistent).
    registry_key_sorted = sorted(
        [(normalize_model_name(k), k) for k, v in reg.items() if isinstance(v, dict)],
        key=lambda x: -len(x[0]),
    )

    for cfg in cfgs:
        cn = normalize_model_name(cfg["dir_name"])
        match = find_registry_key_for_config(cn, registry_key_sorted, config=cfg)
        if not match:
            continue
        entry = reg[match]
        json_path = Path(cfg["json_path"])
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: S112 - fehlende/kaputte JSON-Configs ueberspringen
            continue
        load_fields = {
            f.get("key"): f.get("value") for f in data.get("load", {}).get("fields", []) if isinstance(f, dict)
        }

        cfg_ctx = load_fields.get("llm.load.contextLength")

        # context_length: Config-Wert kleiner als Registry-Erwartung → Altlast?
        reg_ctx = entry.get("context_length")
        if isinstance(cfg_ctx, int) and isinstance(reg_ctx, int) and cfg_ctx != reg_ctx:
            errors["config_context_drift"].append(
                f"{match}: Config contextLength={cfg_ctx} != Registry context_length={reg_ctx} ({cfg['json_path']})"
            )
        # Only check: config must not exceed model's native max_context_length
        max_ctx = entry.get("max_context_length")
        if isinstance(cfg_ctx, int) and isinstance(max_ctx, int) and cfg_ctx > max_ctx:
            errors["config_context_too_small"].append(
                f"{match}: Config contextLength={cfg_ctx} > max_context_length={max_ctx} "
                f"(exceeds model native limit, {cfg['json_path']})"
            )
        # Also check for invalid zero/negative values
        if isinstance(cfg_ctx, int) and cfg_ctx <= 0:
            errors["config_context_too_small"].append(
                f"{match}: Config contextLength={cfg_ctx} <= 0 (invalid, {cfg['json_path']})"
            )

        # np/UKV/offload: Registry ist SSOT (Stand 11.08.2026).
        # JSON-Configs werden ignoriert — Benchmark überschreibt alle Parameter
        # explizit via API. Drift-Check entfernt, da Configs irrelevant.

    # ── Check 9: GGUF-Header vs. Registry (Feld-Ownership) ──────────
    # auto_fix-Felder (n_layers/hidden_dim/max_context_length/arch) aus den
    # unveraenderlichen GGUF-Headern; Abweichungen werden gemeldet (fixbar
    # durch 'sync-from-gguf'). reasoning bleibt bewusst außen vor
    # (Interpretationsspielraum, wird nur als fill-if-missing behandelt).
    gguf_drift_errors = [] if ci else _gguf_drift_errors(reg)
    errors["gguf_header_drift"] = gguf_drift_errors

    # ── Report ─────────────────────────────────────────────────────
    advisory_checks = {"missing_capabilities"}
    blocking_total = sum(len(v) for k, v in errors.items() if k not in advisory_checks)
    advisory_total = sum(len(v) for k, v in errors.items() if k in advisory_checks)
    print(f"\n{'=' * 60}")
    print(f"  Validierung: {blocking_total} blockierende Probleme, {advisory_total} Hinweise")
    print(f"{'=' * 60}")
    for check, items in errors.items():
        if items:
            marker = "⚠️" if check in advisory_checks else "❌"
            print(f"\n  {marker} {check} ({len(items)}):")
            shown = items if verbose else items[:10]
            for item in shown:
                print(f"     - {item}")
            if not verbose and len(items) > 10:
                print(f"     ... und {len(items) - 10} weitere")
        else:
            print(f"\n  ✅ {check}: 0")

    if repro:
        _write_repro_issues(reg, errors, verbose)

    return errors


# Drift-Kategorien, die beim pipeline full zu Exit-Code != 0 führen (CI-fähig).
# Das sind die Feld-Ownership-Melde-Felder (Config-Felder + GGUF-Header-Drift).
_DRIFT_CHECKS = ("config_context_drift", "config_context_too_small", "gguf_header_drift")


# ── sync command (full) ────────────────────────────────────────────


def cmd_sync(refresh_sampling: bool = False) -> None:
    """Full sync including read-only web sampling research.

    Nur Registry-Pflege aus unveränderlichen Quellen (GGUF-Header, JSON-Configs).
    Sampling-Werte werden nur aus plausiblen, eindeutigen Web-Quellen übernommen;
    bei fehlenden/konfligierenden Werten bleiben Kategorie-Defaults aktiv. Es
    wird NIE in JSON-Configs geschrieben (die GUI ist die Quelle) und die
    Blueprint-YAML wird nicht regeneriert (sie ist die Quelle für assemble).
    Terminale Recherche-Status werden nicht erneut versucht; ein explizites
    --refresh-sampling recherchiert dagegen alle benchmarkbaren Kandidaten
    erneut und aktualisiert dabei auch die Kategorie-Evidenz.
    """
    lms = _benchmark_lms_models(_run_lms_ls())
    reg = load_registry()
    _rekey_registry_to_lms(reg, lms)
    reg = load_registry()
    registry_keys = [k for k, v in reg.items() if isinstance(v, dict)]

    # Find new models
    new_models = []
    for m in lms:
        if not any(_lms_matches_registry_key(m, key) for key in registry_keys):
            new_models.append(m)

    if new_models:
        print(f"[add] {len(new_models)} neue Modelle zur Registry ...")
        cmd_add(new_models, research_web=True)
    else:
        print("[add] Keine neuen Modelle")

    print("[sampling] Fehlende Registry-Sampling-Blöcke per Web-Recherche prüfen ...")
    if refresh_sampling:
        print("  [sampling] Expliziter Voll-Refresh für alle Registry-Kandidaten ...")
    _research_missing_sampling(load_registry(), force=refresh_sampling)

    print("[fill-quant] fehlende @quant-Suffixe aus GGUF-Headern ergänzen ...")
    cmd_fill_quant()

    print("[fill-arch] n_layers/hidden_dim + reasoning aus GGUF-Headern in Registry ...")
    cmd_fill_arch()

    print("[sync-from-gguf] Registry-Auto-Fix aus GGUF-Headern (Feld-Ownership) ...")
    cmd_sync_from_gguf()

    print("[fill-reasoning] Fehlende reasoning-Felder aus GGUF-Headern ergänzen ...")
    cmd_fill_reasoning()

    print(
        "[sync-from-configs] Config-Felder (offload/UKV/context/KV-Quant) abgleichen - Melde-Modus (0 geschrieben) ..."
    )
    cmd_sync_from_configs(installed_models=lms)

    print("[fmt] Blank lines normalisieren ...")
    cmd_fmt()

    print("[OK] Sync abgeschlossen")
    print("Hinweis: Blueprint-YAML ist die Quelle (wird nicht regeneriert).")
    print("  Für Prompts:  python registry_tool.py pipeline full")
    print("  Für Empfehlungen (Dry-run, schreibt nichts): python registry_tool.py suggest")


# ── pipeline command ───────────────────────────────────────────────
# Ersetzt sync_model_configs.ps1 (01.08.-2026): ein Einstiegspunkt fuer
# Status-Report, AutoAdd und FullSync - ohne PowerShell-Wrapper.


def cmd_pipeline(
    mode: str = "status", ignore_drift: bool = False, refresh_sampling: bool = False
) -> None:
    """Ein-Aufruf-Wartungspipeline (ersetzt sync_model_configs.ps1).

    Modus:
      status  -> LMS-Modellzahl + compare-Report (Default, schreibt nichts)
      sync    -> status + registry_tool sync + Klassifikation
      full    -> sync + read-only Prompt-Preview + Validierung

    ignore_drift: beendet full NICHT mit Exit-Code 1, auch wenn Melde-Konflikte
    (Feld-Ownership: Config-Felder, GGUF-Header-Drift) offen sind.
    """
    try:
        lms = _benchmark_lms_models(_run_lms_ls())
        print(f"[1] LMS Modelle: {len(lms)}")
    except Exception as e:
        print(f"[WARN] lms ls fehlgeschlagen: {e}")

    print("[2] Registry <> LMS <> Configs (compare) ...")
    cmd_compare()

    if mode == "status":
        return

    if mode == "full":
        print("[2b] Quarantäne nicht-installierter Modelle (missing, DRY-RUN) ...")
        cmd_quarantine_missing(dry_run=True)

    print("[3] Full sync (add + fill-quant + fill-arch + sync-from-gguf + fill-reasoning + sync-from-configs + fmt) ...")
    cmd_sync(refresh_sampling=refresh_sampling)

    print("[4] Klassifikation (blueprint + reasoning) ...")
    classify_registry()

    if mode == "full":
        print("[5] Prompt-Assembly (PREVIEW, Config-JSONs bleiben unverändert) ...")
        assemble_prompts(preview_only=True)
        print("[5a] GLM-Config-Patch übersprungen (pipeline full ist read-only für Config-JSONs) ...")
        print("[6] Validierung ...")
        validate_prompts()
        print("[6a] Registry-Drift-Validierung (Feld-Ownership) ...")
        errors = cmd_validate()
        open_drift = {k: v for k, v in errors.items() if k in _DRIFT_CHECKS and v}
        if open_drift:
            total_open = sum(len(v) for v in open_drift.values())
            print(f"\n{'=' * 60}")
            print(f"[DRIFT] {total_open} offene Melde-Konflikte (Feld-Ownership):")
            for check, items in open_drift.items():
                print(f"  - {check}: {len(items)}")
            print("  Beheben: sync-from-gguf (auto-fix) laeuft bereits; Config-Felder")
            print("  manuell entscheiden oder --ignore-drift fuer reinen Status.")
            print(f"{'=' * 60}")
            if not ignore_drift:
                print("[ERROR] pipeline full mit Exit-Code 1 (offene Melde-Konflikte)")
                sys.exit(1)
        else:
            print("[DRIFT] Keine offenen Melde-Konflikte - konvergiert.")

    print(f"[OK] pipeline {mode} abgeschlossen")


# ── patch-reasoning-effort command ─────────────────────────────────
# Port von tools/patch_reasoning_effort.py (Fix 2026-07-31): traegt gpt-oss-20b-
# GGUF-Varianten die Reasoning-Effort-Felder idempotent nach (mit Backup).

_PRE_LOCK_PATH = PROJECT_ROOT / "ergebnisse" / ".benchmark.lock"
_PRE_EFFORT_FIELD = {
    "key": "ext.virtualModel.customField.openai.gptOss20b.reasoningEffort",
    "value": GPTOSS_REASONING_EFFORT,
}
_PRE_PARSING_FIELD = {
    "key": "llm.prediction.reasoning.parsing",
    "value": {"enabled": False, "startString": " thinking", "endString": " response"},
}
_PRE_BUDGET_FIELD = {
    "key": "llm.prediction.reasoning.budgetTokens",
    "value": {"checked": True, "value": GPTOSS_REASONING_BUDGET},
}
_PRE_REQUIRED_FIELDS = [_PRE_EFFORT_FIELD, _PRE_PARSING_FIELD, _PRE_BUDGET_FIELD]


def find_gptoss_configs() -> list[str]:
    """Alle gpt-oss-20b-Konfigurationsdateien unter dem LM-Studio-Config-Verzeichnis."""
    configs = []
    for path in sorted(CONFIG_ROOT.glob("**/*gpt-oss*20b*.json")):
        if ".bak" in str(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if "operation" in data and "fields" in data.get("operation", {}):
                configs.append(str(path))
        except (OSError, json.JSONDecodeError):
            continue
    return configs


def gptoss_missing_fields(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Die der Konfiguration fehlenden Pflichtfelder (idempotent)."""
    present_keys = {f.get("key") for f in data.get("operation", {}).get("fields", [])}
    return [f for f in _PRE_REQUIRED_FIELDS if f["key"] not in present_keys]


def _pre_backup_path(path: str) -> str:
    return f"{path}.bak-{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def gptoss_patch_config(path: str, dry_run: bool = False) -> tuple[bool, list[str], list[str], str | None]:
    """Gpt-oss-Config patchen. Returns (changed, added_keys, updated_keys, backup_path)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    missing = gptoss_missing_fields(data)
    present = {f.get("key"): f for f in data.get("operation", {}).get("fields", [])}
    to_overwrite = [
        f for f in _PRE_REQUIRED_FIELDS if f["key"] in present and present[f["key"]].get("value") != f["value"]
    ]
    if not missing and not to_overwrite:
        return False, [], [], None
    if dry_run:
        return True, [m["key"] for m in missing], [f["key"] for f in to_overwrite], None
    backup = _pre_backup_path(path)
    with open(path, encoding="utf-8") as f_src, open(backup, "w", encoding="utf-8") as f_dst:
        f_dst.write(f_src.read())
    data["operation"]["fields"].extend(missing)
    by_key = {f["key"]: f for f in data["operation"]["fields"]}
    for f in to_overwrite:
        by_key[f["key"]]["value"] = f["value"]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return True, [m["key"] for m in missing], [f["key"] for f in to_overwrite], backup


# ── patch-glm-configs command ──────────────────────────────────────
# Fix 2026-08-07: GLM-Modelle lieferten leere Antworten, weil
#   1) reasoning.parsing mit startString " thinking"/endString " response"
#      alles aus dem Content strippt (Modell schreibt keine ' response'-Marker),
#   2) llm.prediction.structured (JSON-Schema) jeden Request auf JSON zwingt,
#   3) stopStrings mit " response" den Content vor der Ausgabe stoppen,
#   4) SystemPrompts eine manuelle "answer structured in following JSON
#      format:"-Zeile enthalten, die nicht aus Blueprints stammt.
# Dieser Patch verankert die Fixes idempotent in den GLM-Configs, damit ein
# `pipeline full` die manuellen Korrekturen nicht mehr ueberschreibt.

_GLM_JSON_LINES = (
    "answer structured in following JSON format",
    "final answer in the language of the user, except for coding",
)


def find_glm_configs() -> list[str]:
    """Alle GLM-Konfigurationsdateien unter dem LM-Studio-Config-Verzeichnis."""
    configs = []
    for path in sorted(CONFIG_ROOT.glob("**/*glm*.json")):
        if ".bak" in str(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if "operation" in data and "fields" in data.get("operation", {}):
                configs.append(str(path))
        except (OSError, json.JSONDecodeError):
            continue
    return configs


def glm_patch_config(path: str, dry_run: bool = False) -> tuple[bool, list[str], str | None]:
    """GLM-Config patchen. Returns (changed, actions, backup_path)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    fields = data.get("operation", {}).get("fields", [])
    actions: list[str] = []

    # 1) structured-Feld entfernen (erzwingt JSON-Ausgabe)
    fields = [f for f in fields if f.get("key") != "llm.prediction.structured"]

    # 2) reasoning.parsing AKTIVIEREN: GLM sind Reasoning-Modelle, der
    #    ` thinking…response`-Block muss aus `content` gestrippt werden
    #    (enabled:false leakt den Block und bricht JSON-Mode; siehe
    #    `Model Specific Hints/GLM 4.5 - 4.7_Structured Output_en.md`).
    for f in fields:
        if f.get("key") == "llm.prediction.reasoning.parsing":
            if isinstance(f.get("value"), dict) and f["value"].get("enabled") is not True:
                f["value"]["enabled"] = True
                actions.append("reasoning.parsing enabled")
            break
    else:
        fields.append({"key": "llm.prediction.reasoning.parsing",
                       "value": {"enabled": True, "startString": " thinking", "endString": " response"}})
        actions.append("reasoning.parsing added (enabled)")

    # 3) stopStrings: " response"-Eintraege entfernen (stoppen vor dem Content)
    for f in fields:
        if f.get("key") == "llm.prediction.stopStrings":
            old = f.get("value")
            if isinstance(old, list):
                cleaned = [s for s in old if " response" not in s]
                if cleaned != old:
                    f["value"] = cleaned
                    actions.append(f"stopStrings: {old} -> {cleaned}")
            break

    # 4) JSON-Anweisung aus SystemPrompt entfernen
    for f in fields:
        if f.get("key") == "llm.prediction.systemPrompt" and isinstance(f.get("value"), str):
            lines = f["value"].splitlines()
            cleaned = [ln for ln in lines if not any(m in ln for m in _GLM_JSON_LINES)]
            if len(cleaned) != len(lines):
                f["value"] = "\n".join(cleaned)
                actions.append("SystemPrompt: JSON-Anweisung entfernt")

    data["operation"]["fields"] = fields
    if not actions:
        return False, [], None
    if dry_run:
        return True, actions, None
    backup = _pre_backup_path(path)
    with open(path, encoding="utf-8") as f_src, open(backup, "w", encoding="utf-8") as f_dst:
        f_dst.write(f_src.read())
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return True, actions, backup


def cmd_patch_glm_configs(dry_run: bool = False) -> None:
    """Traegt GLM-Configs die Reasoning-Fixes nach (parsing enabled, kein JSON-Zwang)."""
    configs = find_glm_configs()
    if not configs:
        print(f"[WARN] Keine GLM-Konfigurationsdateien unter {CONFIG_ROOT} gefunden")
        return
    print(f"[INFO] {len(configs)} GLM-Configs gefunden" + (" (DRY-RUN)" if dry_run else ""))
    changed = 0
    for path in configs:
        did_change, actions, backup = glm_patch_config(path, dry_run=dry_run)
        if did_change:
            changed += 1
            short = str(path).replace(str(CONFIG_ROOT), "")
            print(f"  [{'PATCH' if not dry_run else 'WUERDE PATCHEN'}] {short}")
            for a in actions:
                print(f"      ~ {a}")
            if backup:
                print(f"      Backup: {backup}")
        else:
            print(f"  [OK]   {str(path).replace(str(CONFIG_ROOT), '')} (bereits vollständig)")
    print(f"\n[{'DRY-RUN' if dry_run else 'OK'}] {changed}/{len(configs)} Configs geändert.")


def _pre_lock_held_by_live_process() -> int | None:
    """PID des laufenden Benchmark-Launchers (aus ergebnisse/.benchmark.lock) oder None."""
    if not _PRE_LOCK_PATH.exists():
        return None
    try:
        with open(_PRE_LOCK_PATH, encoding="utf-8") as f:
            pid = int(json.load(f).get("pid", -1))
    except (OSError, ValueError, KeyError):
        return None
    if pid > 0 and psutil.pid_exists(pid):
        try:
            if psutil.Process(pid).is_running():
                return pid
        except psutil.Error:
            return None
    return None


def cmd_patch_reasoning_effort(
    dry_run: bool = False,
    wait_for_lock: bool = False,
    effort: str | None = None,
    budget: int | None = None,
) -> None:
    """Traegt gpt-oss-20b-GGUF-Varianten die Reasoning-Effort-Felder in LMS-Configs nach."""
    if effort is None:
        effort = GPTOSS_REASONING_EFFORT
    if effort not in ("low", "medium", "high"):
        print(f"[ERROR] Ungültiger effort: {effort} (low|medium|high)")
        sys.exit(1)
    if budget is None:
        budget = GPTOSS_REASONING_BUDGET
    budget = max(int(budget), 1)
    _PRE_EFFORT_FIELD["value"] = effort
    _PRE_BUDGET_FIELD["value"]["value"] = budget
    if effort != GPTOSS_REASONING_EFFORT or budget != GPTOSS_REASONING_BUDGET:
        print(
            f"[INFO] Übersteuert: effort={effort} (Default {GPTOSS_REASONING_EFFORT}), "
            f"budget={budget} (Default {GPTOSS_REASONING_BUDGET})"
        )

    while True:
        owner = _pre_lock_held_by_live_process()
        if owner is None:
            break
        if not wait_for_lock:
            print(
                f"[FATAL] Benchmark-Launcher läuft noch (PID {owner}) - Config-Änderung "
                "während eines Laufs würde die Ergebnisse inkonsistent machen. "
                "--wait-for-lock nutzen."
            )
            sys.exit(1)
        print(f"[WAIT] Launcher PID {owner} läuft noch - prüfe in 60s erneut...")
        time.sleep(60)

    configs = find_gptoss_configs()
    if not configs:
        print(f"[WARN] Keine gpt-oss-20b-Konfigurationsdateien unter {CONFIG_ROOT} gefunden")
        return

    print(f"[INFO] {len(configs)} gpt-oss-20b-Configs gefunden" + (" (DRY-RUN)" if dry_run else ""))
    changed = 0
    for path in configs:
        did_change, added, updated, backup = gptoss_patch_config(path, dry_run=dry_run)
        if did_change:
            changed += 1
            short = str(path).replace(str(CONFIG_ROOT), "")
            print(f"  [{'PATCH' if not dry_run else 'WUERDE PATCHEN'}] {short}")
            for key in added:
                print(f"      + {key}")
            for key in updated:
                print(f"      ~ {key} (Wert aktualisiert)")
            if backup:
                print(f"      Backup: {backup}")
        else:
            print(f"  [OK]   {str(path).replace(str(CONFIG_ROOT), '')} (bereits vollständig)")
    print(f"\n[{'DRY-RUN' if dry_run else 'OK'}] {changed}/{len(configs)} Configs geändert.")
    if not dry_run and changed:
        print("[INFO] Wirksam ab dem nächsten Laden des Modells.")


# ── CLI dispatch ──────────────────────────────────────────────────


def _print_menu(cmds: list[tuple[str, str]]) -> None:
    print("=" * 60)
    print("  registry_tool.py - Interactive Menu")
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
        "pipeline": lambda: cmd_pipeline("full"),
        "patch-reasoning-effort": lambda: cmd_patch_reasoning_effort(dry_run=True),
        "patch-glm-configs": lambda: cmd_patch_glm_configs(dry_run=True),
        "validate": cmd_validate,
        "suggest": cmd_suggest,
        "compare": cmd_compare,
        "fmt": cmd_fmt,
        "fix-np": cmd_fix_np,
        "fix-ctx": cmd_fix_ctx,
        "fill-arch": cmd_fill_arch,
        "fill-reasoning": cmd_fill_reasoning,
        "fill-ctx": cmd_fill_ctx,
        "fill-size": cmd_fill_size,
        "sync-from-configs": cmd_sync_from_configs,
        "sync-templates": cmd_sync_templates,
        "migrate-keys": cmd_migrate_keys,
        "quarantine-missing": lambda: cmd_quarantine_missing(dry_run=True),
    }
    if cmd == "add":
        if not sys.stdin.isatty():
            models = json.load(sys.stdin)
            if not isinstance(models, list):
                models = [models]
            cmd_add(models, interactive=True, research_web=True)
        else:
            print("  [add] Ermittle installierte Modelle via LMS ...")
            models = _run_lms_ls()
            if models:
                cmd_add(models, interactive=True, research_web=True)
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
        ("sync", "Full sync: add → fill-quant → fill-arch → sync-from-gguf → fill-reasoning → sync-from-configs → fmt"),
        ("pipeline", "Status/Sync/Full-Wartung: status | sync | full (Exit 1 bei Drift)"),
        ("patch-reasoning-effort", "gpt-oss-20b Reasoning-Effort in LMS-Configs nachtragen"),
        ("validate", "Check model_registry.yaml consistency (inkl. Config-Abweichungen)"),
        ("sync-templates", "promptTemplate aus Registry-Templates in Config-JSONs nachtragen"),
        ("suggest", "Dry-run: VRAM-basierte Unified-KV-cache (UKV)/ctx-Empfehlung (schreibt NICHTS)"),
        ("compare", "Compare registry vs LMS vs JSON configs"),
        ("add", "Add LMS models to registry (pipe JSON or provide file)"),
        ("fmt", "Normalize blank lines in registry YAML"),
        ("fix-np", "DEPRECATED: np ist feste Policy seit 13.08. (zeigt Info, tut nichts)"),
        ("fix-ctx", "Fehlende oder 0 gesetzte context_length-Werte ergänzen"),
        ("fill-arch", "Read n_layers/hidden_dim from GGUF headers"),
        ("sync-from-gguf", "Auto-Fix n_layers/hidden_dim/ctx/arch aus GGUF (Feld-Ownership)"),
        ("fill-reasoning", "Read reasoning from GGUF chat_template"),
        ("fill-ctx", "Add default context_length to missing entries"),
        ("fill-size", "Look up file_size_bytes from LMS"),
        ("fill-quant", "Read @quant from GGUF filename (Source of Truth)"),
        ("sync-from-configs", "GUI-Config-Felder melden; --write übernimmt Offload/UKV/Context/KV-Quant"),
        ("migrate-keys", "Re-key entries without publisher prefix"),
        ("quarantine-missing", "Nicht-installierte Modelle: Configs+Eintrag in Quarantäne (Dry-run)"),
        ("rm", "Remove registry entry (optionally files + configs too)"),
    ]

    _print_menu(cmds)
    while True:
        try:
            choice = input("Select command [1-19] or q: ").strip().lower()
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
    _configure_utf8_output()
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
            with open(sys.argv[2], encoding="utf-8-sig") as f:
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
        cmd_add(models, interactive=True, research_web=True)
    elif cmd == "suggest":
        cmd_suggest()
    elif cmd == "sync-from-configs":
        write_context = "--write-context" in sys.argv[2:]
        # The narrow context repair also covers matching retained configs that
        # are no longer in the current LMS inventory; validation still checks
        # those Registry identities and must be repairable deterministically.
        installed_models = None if write_context else _benchmark_lms_models(_run_lms_ls())
        cmd_sync_from_configs(
            write="--write" in sys.argv[2:] or write_context,
            write_context=write_context,
            installed_models=installed_models,
        )
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
    elif cmd == "sync-from-gguf":
        cmd_sync_from_gguf()
    elif cmd == "fill-reasoning":
        cmd_fill_reasoning()
    elif cmd == "fill-quant":
        cmd_fill_quant()
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
        flags = set(sys.argv[2:])
        errors = cmd_validate(
            verbose="--verbose" in flags,
            repro="--repro" in flags,
            ci="--ci" in flags or "--headless" in flags,
        )
        advisory_checks = {"missing_capabilities"}
        has_blocking_errors = any(
            items for check, items in errors.items() if check not in advisory_checks
        )
        sys.exit(1 if has_blocking_errors else 0)
    elif cmd == "quarantine-missing":
        dry_run = "--dry-run" in sys.argv
        sys.exit(cmd_quarantine_missing(dry_run=dry_run))
    elif cmd == "sync-templates":
        cmd_sync_templates()
    elif cmd == "sync-template-from-gguf":
        if len(sys.argv) < 3:
            print("[ERROR] Nutzung: python registry_tool.py sync-template-from-gguf <model-key>")
            sys.exit(1)
        sys.exit(cmd_sync_template_from_gguf(sys.argv[2]))
    elif cmd == "pipeline":
        mode = sys.argv[2] if len(sys.argv) > 2 else "status"
        if mode.startswith("-"):
            mode = "status"
        if mode not in ("status", "sync", "full"):
            print(f"[ERROR] Unbekannter pipeline-Modus: {mode} (status|sync|full)")
            sys.exit(1)
        ignore_drift = "--ignore-drift" in sys.argv[2:]
        refresh_sampling = "--refresh-sampling" in sys.argv[2:]
        cmd_pipeline(mode, ignore_drift=ignore_drift, refresh_sampling=refresh_sampling)
    elif cmd == "patch-reasoning-effort":
        flags = set(sys.argv[2:])
        effort = budget = None
        if "--effort" in flags:
            effort = sys.argv[sys.argv.index("--effort") + 1]
        if "--budget" in flags:
            budget = int(sys.argv[sys.argv.index("--budget") + 1])
        cmd_patch_reasoning_effort(
            dry_run="--dry-run" in flags,
            wait_for_lock="--wait-for-lock" in flags,
            effort=effort,
            budget=budget,
        )
    elif cmd == "patch-glm-configs":
        cmd_patch_glm_configs(dry_run="--dry-run" in sys.argv)
    elif cmd == "sync":
        cmd_sync(refresh_sampling="--refresh-sampling" in sys.argv[2:])
    else:
        print(f"[ERROR] Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


# Deprecated constants kept for backward compatibility with tests.
# The UKV threshold is now 12.0 (USE_UNIFIED_KV_CACHE_THRESHOLD_GB).
_LEGACY_MODEL_GB_THRESHOLD_GB = 9.0

if __name__ == "__main__":
    main()
