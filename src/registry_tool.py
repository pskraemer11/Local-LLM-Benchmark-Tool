#!/usr/bin/env python3
r"""
Registry and prompt-policy tool for local LLM benchmarks.

This program prepares models for `run_benchmarks.py`. It discovers benchmarkable
LM Studio models, uses the canonical identity `publisher/model@quant`, reads
technical facts from GGUF files, maintains `data\model_registry.yaml`, and
checks prompt and runtime drift.

1. RECOMMENDED WORKFLOW

  py -3.12 .\src\registry_tool.py status
      Read-only inventory and Registry comparison.

  py -3.12 .\src\registry_tool.py sync
      Refresh the Registry from the installed models and technical files;
      show LM Studio tuning differences as field-level proposals.

  py -3.12 .\src\registry_tool.py sync --import-lms-settings
      Also import valid, unambiguous LM Studio JSON settings and loaded native
      API expert counts into the Registry. Values beyond GGUF limits are rejected.

  py -3.12 .\src\registry_tool.py full
      Run synchronization, prompt-template maintenance, preview, and checks.

  py -3.12 .\src\registry_tool.py full --write-prompts
      Additionally write assembled system prompts to uniquely joined configs.

  py -3.12 .\src\registry_tool.py preset <path> --merge-existing
      Export Registry runtime values into a llama.cpp preset, preserving
      existing global settings and manual sections.

  py -3.12 .\src\registry_tool.py quarantine-missing
      Preview stale entries. Moving configs and removing Registry entries
      requires the explicit --apply option.

`full` writes only missing LM Studio `promptTemplate` fields and runs prompt
assembly as a preview. It does not write assembled system prompts by default.
After reviewing the preview, `full --write-prompts` writes them atomically and
only through the shared per-run IdentityLink table. `pipeline full` remains a
compatibility spelling of `full`; both use the same workflow and options.

2. SOURCE OF TRUTH AND WRITE BOUNDARIES

  Registry policy       data\model_registry.yaml
  Technical limits      Main GGUF file and header
  Prompt policy         docs\blueprint_definitions.yaml and templates
  LM Studio settings    Tested runtime evidence; import is opt-in
  llama.cpp preset      Generated runtime output; never the Registry source

Model identity is `publisher/model@quant`. LM Studio's displayed model size
may include helper files such as `mmproj`; `file_size_bytes` comes from the
main GGUF file. `max_context_length` and `max_experts` are immutable GGUF
limits; `context_length` and `experts` are selected Registry runtime values.

Sampling research is not automatic. `sync --refresh-sampling` performs a web
search and may take several minutes. Models without a local benchmark pipeline
are excluded.

3. ADDITIONAL COMMANDS

  validate [--ci]       Validate Registry, GGUF facts, templates, and ownership.
  preset <path>         Generate a derived llama.cpp preset INI.
  advanced --help       Show specialist maintenance commands.
  full --write-prompts             Explicitly write joined LM Studio prompts.

The earlier command names remain available directly and through `advanced`
for compatibility. The public workflow above is the recommended interface.

"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from collections.abc import Callable

import psutil

from artifact_resolver import ArtifactResolver

_SRC_DIR = Path(__file__).resolve().parent
# Make `src` importable regardless of how the tool is invoked
# (python -m src.registry_tool from the repo root puts only the CWD
# on sys.path, not `src/`). Fix for Code-Review_2026-08-03.md F4.
sys.path.insert(0, str(_SRC_DIR))

if TYPE_CHECKING:
    from type_defs import RegistryEntry

PROJECT_ROOT = _SRC_DIR.parent
REGISTRY_PATH = PROJECT_ROOT / "data" / "model_registry.yaml"
CONFIG_ROOT = Path.home() / ".lmstudio" / ".internal" / "user-concrete-model-default-config"


@dataclass(frozen=True)
class SyncProposalItem:
    """One field-level value proposed for import from a named source."""

    model_key: str
    field: str
    current: Any
    proposed: Any
    sources: tuple[Path, ...]
    conflict: bool = False
    problem: str | None = None

# ── ruamel.yaml setup ──────────────────────────────────────────────
from ruamel.yaml import YAML

y = YAML()
y.preserve_quotes = True
y.indent(mapping=2, sequence=4, offset=2)

# ── assemble_blueprint helpers ─────────────────────────────────────
from artifact_bundle import validate_companion_binding, validate_config_gguf_pair
from assemble_blueprint import (
    _registry_quant,
    assemble_prompts,
    blueprint_features,
    classify_registry,
    clear_lms_config_cache,
    configs_for_registry_key,
    find_all_configs_for_registry_key,
    find_config_for_registry_key,
    find_registry_key_for_config,
    find_registry_matches_for_config,
    normalize_model_name,
    read_lms_configs,
    validate_prompts,
)
from benchmark_config import (
    GPTOSS_REASONING_BUDGET,
    GPTOSS_REASONING_EFFORT,
    is_blacklisted_model_name,
    is_registry_candidate,
    is_support_file,
    is_support_model_record,
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
from inventory import IdentityLink, InventorySnapshot, RuntimeBinding
from kv_cache_policy import (
    KVCachePolicyError,
    kv_cache_type,
    normalize_kv_pair,
    runtime_kv_pair,
)
from model_identity import (
    ArtifactIdentityEvidence,
    UniqueMatch,
    build_model_identity,
    canonicalize_source_identity,
    decompose_model_identity,
    find_match_collisions,
    normalize_for_config,
    normalize_model_reference,
    normalize_registry_identity,
    normalize_variants,
    resolve_registry_match,
)
from model_paths import configured_gguf_roots
from model_registry import ModelRegistry
from parameter_bindings import config_sync_fields
from providers.llama_cpp_args import build_server_command
from quantization import KNOWN_QUANTS, extract_quant_from_text, is_known_quant, normalize_quant
from runtime_policy import resolve_template
from sampling_research import (
    RESEARCH_STATUSES,
    compact_sampling_block,
    research_sampling,
    research_sampling_report,
    validate_sampling_block,
)
from speculative import companion_role, normalize_speculative_profile, registry_speculative_policy


class RegistryInventory(InventorySnapshot):  # type: ignore[misc]
    """Backward-compatible runtime name for the shared inventory snapshot."""

_DEFAULT_RESEARCH_SAMPLING = research_sampling

# ── I/O helpers ────────────────────────────────────────────────────


def load_registry(path: Path | None = None) -> dict[str, RegistryEntry]:
    if path is None:
        path = REGISTRY_PATH
    if not path.is_file():
        return {}
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
    target = path or REGISTRY_PATH
    # Validate every pair before mutating data or creating the output file.
    cache_updates: list[tuple[dict[str, Any], str, str, tuple[str | None, str | None]]] = []
    for entry in reg.values():
        if not isinstance(entry, dict):
            continue
        cache_updates.append((entry, "k_cache", "v_cache", normalize_kv_pair(entry.get("k_cache"), entry.get("v_cache"))))
        for provider in ("llama_cpp", "unsloth_server", "lmstudio", "lm_studio"):
            explicit = entry.get(provider)
            if isinstance(explicit, dict):
                fields = ("k_cache", "v_cache") if provider in {"lmstudio", "lm_studio"} else ("cache_type_k", "cache_type_v")
                cache_updates.append((explicit, *fields, normalize_kv_pair(*(explicit.get(field) for field in fields))))
    for entry, k_field, v_field, pair in cache_updates:
        if pair[0] is not None:
            entry[k_field], entry[v_field] = pair
    _normalize_sampling_schema(reg)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            y.dump(reg, stream)
        _format_blank_lines(temporary_path)
        _normalize_quants_flow_style(temporary_path)
        os.replace(temporary_path, target)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _atomic_write_text(path: Path, content: str) -> None:
    """Replace a text file only after the complete new content is ready."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _atomic_write_yaml(path: Path, data: dict[str, Any]) -> None:
    """Write a YAML artifact atomically without touching the active Registry."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            y.dump(data, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


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
    return cast("dict[str, Any]", research_sampling_report(model))


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
        data = json.load(f)
    if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
        raise ValueError("LM Studio inventory must be a JSON list of model objects")
    return data


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


def _validate_gguf_snapshot(path: Path) -> tuple[Path, ...]:
    """Reject stale or incomplete file snapshots before any Registry mutation."""
    lines = [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    listed: set[Path] = set()
    roots = [root.resolve() for root in _gguf_roots() if root.is_dir()]
    covered_roots: set[Path] = set()
    for line in lines:
        file = Path(line)
        if not file.is_absolute() or file.suffix.lower() != ".gguf" or not file.is_file():
            raise ValueError(f"Invalid or deleted GGUF snapshot file: {line}")
        resolved = file.resolve(strict=True)
        owners = [root for root in roots if resolved.is_relative_to(root)]
        if not owners:
            raise ValueError(f"GGUF snapshot file is outside configured model roots: {line}")
        if resolved in listed:
            raise ValueError(f"Duplicate GGUF snapshot file: {line}")
        listed.add(resolved)
        covered_roots.update(owners)
    if not listed:
        raise ValueError("GGUF snapshot is empty")
    actual = {file.resolve() for root in covered_roots for file in root.rglob("*.gguf") if file.is_file()}
    if actual != listed:
        raise ValueError(f"GGUF snapshot differs from disk: {len(actual - listed)} unlisted, {len(listed - actual)} stale files")
    return tuple(sorted(covered_roots))


def _collect_registry_inventory(
    model_list: Path | None = None, gguf_list: Path | None = None,
) -> RegistryInventory:
    """Read Registry, LM Studio, and config data once for one run.

    The potentially large local GGUF tree is scanned lazily only when a step
    needs physical-file facts or quarantine evidence.
    """
    snapshot_roots = _validate_gguf_snapshot(gguf_list) if gguf_list is not None else None
    registry = load_registry()
    raw_lms_models = load_lms_json(model_list) if model_list is not None else _run_lms_ls()
    lms_models = _benchmark_lms_models(raw_lms_models)
    configs = read_lms_configs(CONFIG_ROOT)
    snapshot = RegistryInventory(registry, raw_lms_models, lms_models, configs, [], gguf_roots=snapshot_roots)
    _refresh_identity_links(snapshot)
    return snapshot


def _refresh_identity_links(inventory: RegistryInventory) -> None:
    """Rebuild the per-run identity table from all available evidence.

    A config is linked either by a unique live LMS/GGUF/config join or by the
    exact local GGUF/config path pair already persisted in this machine-local
    Registry.  The latter is important for unloaded models and for LMS rows
    whose logical Hub publisher differs from the local GGUF publisher.  A
    basename-only or publisherless match is never sufficient.
    """
    registry_keys = sorted(
        [key for key, value in inventory.registry.items() if isinstance(value, dict)],
        key=lambda item: len(item),
    )
    candidates = inventory.gguf_candidates
    artifact_by_key: dict[str, list[Any]] = {key: [] for key in registry_keys}
    if inventory.gguf_candidates_loaded:
        for candidate in candidates:
            evidence = getattr(candidate, "identity_evidence", None)
            if not isinstance(evidence, ArtifactIdentityEvidence) or not evidence.is_complete:
                continue
            registry_key = getattr(candidate, "registry_key", None)
            if isinstance(registry_key, str) and registry_key in registry_keys:
                owner, _, quant = decompose_model_identity(registry_key)
                if owner != evidence.publisher or normalize_quant(quant) != normalize_quant(evidence.quant):
                    continue
                artifact_by_key.setdefault(registry_key, []).append(candidate)
                continue
            identity = evidence.identity
            match = resolve_registry_match(identity, registry_keys)
            if isinstance(match, UniqueMatch) and decompose_model_identity(match.key)[0] == evidence.publisher:
                artifact_by_key.setdefault(match.key, []).append(candidate)

    local_artifact_owners: dict[str, set[str]] = {}
    for registry_key, entry in inventory.registry.items():
        local = entry.get("local") if isinstance(entry, dict) else None
        model_path = local.get("model_path") if isinstance(local, dict) else None
        if isinstance(model_path, (str, os.PathLike)) and str(model_path).strip():
            local_artifact_owners.setdefault(_path_identity(Path(model_path)), set()).add(registry_key)

    persisted_config_owners: dict[str, set[str]] = {}
    for registry_key, entry in inventory.registry.items():
        if not isinstance(entry, dict):
            continue
        declared, model_path, matches = _registry_local_config_matches(
            registry_key, entry, inventory.configs
        )
        if (
            declared
            and model_path is not None
            and local_artifact_owners.get(_path_identity(model_path)) == {registry_key}
            and len(matches) == 1
        ):
            config_path = matches[0].get("json_path")
            if config_path:
                persisted_config_owners.setdefault(_path_identity(config_path), set()).add(registry_key)

    joined: dict[
        str,
        tuple[
            tuple[dict[str, Any], ...],
            tuple[Any, ...],
            tuple[Any, ...],
            tuple[dict[str, Any], ...],
            bool,
        ],
    ] = {}
    config_owners: dict[str, set[str]] = {}
    for registry_key in registry_keys:
        entry = inventory.registry[registry_key]
        linked_models = tuple(
            model
            for model in inventory.lms_models
            if _lms_matches_registry_key(model, registry_key)
        )
        identity_artifacts = tuple(artifact_by_key.get(registry_key, ()))
        if not linked_models and len(identity_artifacts) == 1:
            # Some ``lms ls --json`` snapshots expose the Hub publisher in
            # ``publisher`` while the physical GGUF root exposes the local
            # publisher (for example ``qwen/qwen3.5-9b`` vs.
            # ``lmstudio-community/Qwen3.5-9B-GGUF``).  Once one exact local
            # artifact has already been assigned to the Registry key, the
            # normalized LMS model/quant may complete that join.  This is
            # deliberately unique-only and never chooses among artifacts.
            linked_models = tuple(
                model
                for model in inventory.lms_models
                if _lms_logical_model_matches_registry_key(model, registry_key)
        )
        linked_artifacts = identity_artifacts
        if len(linked_models) == 1:
            # A concrete LMS GGUF path can join a Registry identity even when
            # the physical package directory spells the model differently
            # (for example a derived Muse variant or an MTP-labeled package).
            # Require exactly one path match; never use this fallback for a
            # logical Hub key or basename-only evidence.
            path_matches = tuple(
                candidate
                for candidate in candidates
                if _lms_path_matches_candidate(linked_models[0], candidate.path)
                and candidate.identity_evidence.publisher == decompose_model_identity(registry_key)[0]
                and normalize_quant(candidate.identity_evidence.quant) == normalize_quant(_registry_quant(registry_key))
                and candidate.registry_key in (None, registry_key)
            )
            if _lms_has_concrete_artifact_path(linked_models[0]):
                linked_artifacts = path_matches
            else:
                # Without a concrete LMS path, identity-derived candidates
                # remain the only admissible evidence.
                linked_artifacts = tuple(
                    candidate
                    for candidate in identity_artifacts
                    if _lms_path_matches_candidate(linked_models[0], candidate.path)
                )
        local_path_declared, local_model_path, local_config_matches = (
            _registry_local_config_matches(registry_key, entry, inventory.configs)
        )
        local_artifact_is_unique = (
            local_model_path is not None
            and local_artifact_owners.get(_path_identity(local_model_path)) == {registry_key}
        )
        persisted_local_binding = (
            local_path_declared
            and local_artifact_is_unique
            and len(local_config_matches) == 1
        )
        matching_configs: tuple[dict[str, Any], ...] = ()
        if local_path_declared:
            # A declared local path pair is explicit identity evidence. If it
            # is stale, mismatched, or reused, fail closed instead of falling
            # through to a looser name-based match or silently replacing it.
            matching_configs = (
                local_config_matches
                if persisted_local_binding
                and persisted_config_owners.get(
                    _path_identity(local_config_matches[0].get("json_path") or "")
                ) == {registry_key}
                else ()
            )
        elif len(linked_artifacts) == 1:
            artifact_config_matches = tuple(
                config
                for config in inventory.configs
                if _config_matches_artifact(config, linked_artifacts[0].path)
                and persisted_config_owners.get(_path_identity(config.get("json_path") or ""))
                in (None, {registry_key})
            )
            matching_configs = artifact_config_matches
        joined[registry_key] = (
            linked_models,
            identity_artifacts,
            linked_artifacts,
            matching_configs,
            persisted_local_binding,
        )
        if len(matching_configs) == 1:
            config_path = str(matching_configs[0].get("json_path") or "")
            if config_path:
                config_owners.setdefault(_path_identity(config_path), set()).add(registry_key)

    inventory.identity_links.clear()
    for registry_key in registry_keys:
        (
            linked_models,
            identity_artifacts,
            linked_artifacts,
            matching_configs,
            persisted_local_binding,
        ) = joined[registry_key]
        runtime_records: list[RuntimeBinding] = []
        runtime_config: dict[str, Any] | None
        if persisted_local_binding:
            runtime_config = matching_configs[0]
            if config_owners.get(_path_identity(str(runtime_config.get("json_path") or ""))) != {registry_key}:
                runtime_config = None
            runtime_records.append(_build_runtime_binding(runtime_config))
        elif len(linked_artifacts) == 1:
            # Dynamic imports require a one-to-one LMS-model/GGUF/config link.
            # A physical GGUF identity can establish the join without a live
            # LMS inventory; this is the bootstrap path for users who have
            # local GGUFs/configs but no installed LM Studio runtime. Zero,
            # multiple, or globally reused configs remain diagnostics only.
            artifact = linked_artifacts[0] if len(linked_artifacts) == 1 else None
            runtime_config = matching_configs[0] if len(matching_configs) == 1 and artifact else None
            if runtime_config is not None:
                config_path = _path_identity(str(runtime_config.get("json_path") or ""))
                if config_owners.get(config_path) != {registry_key}:
                    runtime_config = None
            runtime_records.append(
                _build_runtime_binding(runtime_config)
            )
        else:
            # Keep all source rows visible for diagnostics, but do not invent
            # a runtime join when the LMS side itself is ambiguous.
            runtime_records.extend(
                _build_runtime_binding(None) for _model in linked_models
            )
        inventory.with_identity_link(
            IdentityLink(
                registry_key=registry_key,
                runtime_bindings=tuple(runtime_records),
                # Keep independently proven Registry-path and concrete LMS-
                # path evidence; a mismatch blocks config/runtime joins but
                # must not erase the other source's valid artifact evidence.
                artifact_evidence=tuple(
                    candidate.identity_evidence
                    for candidate in {
                        _path_identity(candidate.path): candidate
                        for candidate in (*identity_artifacts, *linked_artifacts)
                    }.values()
                ),
                hf_urls=tuple(
                    str(model.get("hf_url") or "")
                    for model in linked_models
                    if model.get("hf_url")
                ),
            )
        )


def _path_identity(value: str | Path) -> str:
    """Normalize an absolute or relative Windows path for comparison."""
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        return ""
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            return str(candidate.resolve(strict=False)).replace("\\", "/").rstrip("/").casefold()
        except OSError:
            return str(candidate.absolute()).replace("\\", "/").rstrip("/").casefold()
    return raw.rstrip("/").casefold()


def _lms_path_matches_candidate(model: dict[str, Any], artifact_path: Path) -> bool:
    """Return whether an LMS source path identifies the local GGUF candidate."""
    source = str(model.get("path") or model.get("modelPath") or "").strip()
    if not source:
        return True
    # ``lms ls --json`` can expose a logical Hub key (for example
    # ``qwen/qwen3.5-9b``) instead of a concrete filesystem path.  Only an
    # absolute path or an explicit GGUF filename is strong enough to reject a
    # physically proven candidate.
    if not Path(source).is_absolute() and not source.casefold().endswith(".gguf"):
        return True
    source_identity = _path_identity(source)
    artifact_identity = _path_identity(artifact_path)
    if not source_identity or not artifact_identity:
        return False
    if Path(source).is_absolute():
        return source_identity == artifact_identity
    return artifact_identity == source_identity or artifact_identity.endswith(f"/{source_identity}")


def _lms_has_concrete_artifact_path(model: dict[str, Any]) -> bool:
    """Return whether the LMS row provides an absolute path or GGUF filename."""
    source = str(model.get("path") or model.get("modelPath") or "").strip()
    return bool(source) and (Path(source).is_absolute() or source.casefold().endswith(".gguf"))


def _lms_logical_model_matches_registry_key(model: dict[str, Any], registry_key: str) -> bool:
    """Match an LMS logical model to a physical Registry identity uniquely.

    This bridges the documented LM Studio shape where ``publisher``/``modelKey``
    describe the Hub namespace while the physical artifact already supplied
    the authoritative local publisher.  Quantization remains mandatory.
    """
    lms_identity = _canonical_lms_key(model)
    _lms_publisher, lms_model, lms_quant = decompose_model_identity(lms_identity)
    _registry_publisher, registry_model, registry_quant = decompose_model_identity(registry_key)
    if not lms_model or not registry_model:
        return False
    if lms_quant != registry_quant:
        return False
    from model_identity import normalize_artifact_model_name

    return bool(normalize_artifact_model_name(lms_model, lms_quant) == normalize_artifact_model_name(
        registry_model, registry_quant
    ))


def _config_matches_artifact(config: dict[str, Any], artifact_path: Path) -> bool:
    """Return whether a JSON config names the concrete GGUF artifact.

    LM Studio may keep both a logical model config (``publisher/model.json``)
    and a file-specific config (``publisher/model-GGUF/model-Q6_K.gguf.json``).
    The latter is the only safe source for runtime values when several GGUF
    variants share one logical model.  Compare the concrete filename and the
    two trailing directory components (publisher and model package), while
    deliberately ignoring the unrelated config/model root drives.
    """
    json_path = config.get("json_path")
    return bool(json_path) and not validate_config_gguf_pair(artifact_path, str(json_path))


def _registry_local_config_matches(
    registry_key: str,
    entry: dict[str, Any],
    configs: list[dict[str, Any]],
) -> tuple[bool, Path | None, tuple[dict[str, Any], ...]]:
    """Resolve a concrete config from the Registry's persisted local path pair.

    The local Registry is generated for this installation, so its absolute
    ``model_path`` and ``config_path`` are first-class join evidence. A
    file-specific JSON config must name the same GGUF filename/package. If the
    Registry declares either path but the pair is stale or inconsistent, the
    caller must fail closed rather than pick a fuzzy alternative.
    """
    local = entry.get("local")
    if not isinstance(local, dict):
        return False, None, ()
    raw_model_path = local.get("model_path")
    raw_config_path = local.get("config_path")
    raw_config_scope = local.get("config_scope", "gguf")
    model_declared = isinstance(raw_model_path, (str, os.PathLike)) and bool(str(raw_model_path).strip())
    config_declared = isinstance(raw_config_path, (str, os.PathLike)) and bool(str(raw_config_path).strip())
    if not model_declared and not config_declared:
        return False, None, ()
    if not model_declared:
        return True, None, ()

    model_path = Path(str(raw_model_path))
    try:
        if not model_path.is_file():
            return True, None, ()
    except OSError:
        return True, None, ()

    if config_declared:
        config_path = Path(str(raw_config_path))
        try:
            if not config_path.is_file():
                return True, model_path, ()
        except OSError:
            return True, model_path, ()
        registry_quant = _registry_quant(registry_key)
        from gguf_evidence import resolve_artifact_quant
        from local_model_resolver import LocalModelResolver

        resolver = LocalModelResolver()
        resolver.model_roots = _gguf_roots()
        physical_reference = resolver._model_base_id(model_path)
        artifact_quant = resolve_artifact_quant(model_path, publisher=decompose_model_identity(physical_reference)[0])
        if not registry_quant or not artifact_quant:
            return True, model_path, ()
        pair_errors = validate_config_gguf_pair(
            model_path,
            config_path,
            scope=str(raw_config_scope),
        )
        if pair_errors:
            return True, model_path, ()
        candidates: list[dict[str, Any]] = []
        for config in configs:
            if _path_identity(config.get("json_path") or "") != _path_identity(config_path):
                continue
            registry_publisher, registry_model, _ = decompose_model_identity(registry_key)
            config_publisher = str(config.get("publisher") or "").casefold()
            if config_publisher and config_publisher != registry_publisher:
                # A declared model-scoped Hub namespace can intentionally
                # differ from the physical package owner. Its complete
                # namespace must already be preserved in the Registry key.
                config_namespace = f"{config_publisher}/{config.get('dir_name') or ''}"
                if str(raw_config_scope) != "model" or (
                    normalize_model_reference(registry_model) != normalize_model_reference(config_namespace)
                ):
                    continue
            else:
                from local_model_resolver import LocalModelResolver

                reference = f"{config_publisher}/{config.get('dir_name') or ''}"
                if LocalModelResolver._match_registry(reference, artifact_quant, {registry_key: entry}) != registry_key:
                    continue
            config_quant = config.get("quant") or extract_quant_from_text(
                f"{config.get('dir_name', '')} {config.get('file_name', '')}"
            )
            config_quant = str(config_quant) if config_quant else None
            if registry_quant and artifact_quant and normalize_quant(registry_quant) != normalize_quant(artifact_quant):
                continue
            if registry_quant and config_quant and normalize_quant(registry_quant) != normalize_quant(config_quant):
                continue
            if artifact_quant and config_quant and normalize_quant(artifact_quant) != normalize_quant(config_quant):
                continue
            candidates.append({**config, "_registry_config_scope": str(raw_config_scope)})
        return True, model_path, tuple(candidates)

    artifact_configs = tuple(
        config for config in configs if _config_matches_artifact(config, model_path)
    )
    return True, model_path, artifact_configs


def _physical_registry_matches_lms_model(
    model: dict[str, Any],
    candidates: list[Any],
    registry_keys: set[str],
) -> tuple[str, ...]:
    """Find existing Registry keys proven by a physical GGUF path.

    This is the bridge for LMS rows whose logical ``publisher/modelKey`` does
    not preserve the publisher encoded by the local GGUF directory.  A
    physical candidate can suppress Registry auto-add only when its existing
    Registry key, quantization, model basename, and LMS path evidence all
    agree uniquely.  Ambiguous candidates intentionally return no result.
    """
    lms_identity = _canonical_lms_key(model)
    _lms_publisher, lms_model, lms_quant = decompose_model_identity(lms_identity)
    if not lms_model:
        return ()
    model_name = str(normalize_for_config(lms_model))
    matches: set[str] = set()
    for candidate in candidates:
        registry_key = getattr(candidate, "registry_key", None)
        evidence = getattr(candidate, "identity_evidence", None)
        path = getattr(candidate, "path", None)
        if (
            not isinstance(evidence, ArtifactIdentityEvidence)
            or not evidence.is_complete
            or not isinstance(path, Path)
        ):
            continue
        # A fill-quant stage may have replaced the key since this immutable
        # artifact snapshot was collected. Join its complete evidence again;
        # an unknown LMS quant must not downgrade a proven GGUF identity.
        if registry_key not in registry_keys:
            match = resolve_registry_match(evidence.identity, registry_keys)
            if not isinstance(match, UniqueMatch):
                continue
            registry_key = match.key
        if not isinstance(registry_key, str):
            continue
        _publisher, _candidate_model, candidate_quant = decompose_model_identity(registry_key)
        if normalize_quant(candidate_quant) != normalize_quant(evidence.quant):
            continue
        if is_known_quant(lms_quant) and normalize_quant(candidate_quant) != normalize_quant(lms_quant):
            continue
        if str(normalize_for_config(evidence.model_name)) != model_name:
            continue
        if not _lms_path_matches_candidate(model, path):
            continue
        matches.add(registry_key)
    return tuple(sorted(matches))


def _positive_int(value: Any) -> int | None:
    """Parse a positive LM Studio runtime integer without accepting booleans."""
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _build_runtime_binding(
    config: dict[str, Any] | None,
) -> RuntimeBinding:
    """Build runtime data after identity/artifact/config uniqueness is proven."""
    sampling = config.get("sampling") if config else None
    sampling_items = (
        tuple(sorted((str(key), value) for key, value in sampling.items()))
        if isinstance(sampling, dict)
        else ()
    )
    offload = config.get("offload") if config else None
    try:
        offload_value = float(offload) if offload is not None else None
    except (TypeError, ValueError):
        offload_value = None
    speculative = config.get("speculative") if config else None
    speculative_items = (
        tuple(sorted((str(key), value) for key, value in speculative.items()))
        if isinstance(speculative, dict)
        else ()
    )
    cache_pair = normalize_kv_pair(config.get("k_cache") if config else None, config.get("v_cache") if config else None)
    return RuntimeBinding(
        config_path=Path(config["json_path"]) if config and config.get("json_path") else None,
        config_scope=str(config.get("_registry_config_scope", "gguf")) if config else None,
        sampling=sampling_items,
        context_length=config.get("context_length") if config else None,
        use_unified_kv=config.get("use_unified_kv") if config else None,
        num_parallel=_positive_int(config.get("num_parallel")) if config else None,
        offload=offload_value,
        k_cache=cache_pair[0],
        v_cache=cache_pair[1],
        num_experts=_positive_int(config.get("num_experts")) if config else None,
        speculative=speculative_items,
    )


def _resolve_local_companion(reference: str) -> Path | None:
    """Resolve an explicitly configured bundle artifact, including support files."""
    if not reference.strip():
        return None
    resolver = ArtifactResolver()
    resolver.model_roots = _gguf_roots()
    result = resolver.resolve(reference, include_support=True)
    return result.path if result.is_unique else None


def _materialize_local_bindings(inventory: RegistryInventory) -> int:
    """Persist exact local bundle paths and llama.cpp speculative settings.

    The local Registry is the effective machine-local catalog. Only unique
    joins are materialized; unresolved or ambiguous evidence is left out so a
    stale/guessed companion can never reach ``llama-server``.
    """
    changed = 0
    for registry_key, link in inventory.identity_links.items():
        entry = inventory.registry.get(registry_key)
        if not isinstance(entry, dict) or len(link.artifact_evidence) != 1:
            continue
        local = entry.setdefault("local", {})
        if not isinstance(local, dict):
            local = {}
            entry["local"] = local
        main_path = str(link.artifact_evidence[0].path)
        if local.get("model_path") != main_path:
            local["model_path"] = main_path
            changed += 1

        policy = registry_speculative_policy(entry)
        if policy == "disabled":
            local_llama = local.get("llama_cpp")
            if isinstance(local_llama, dict) and "speculative" in local_llama:
                del local_llama["speculative"]
                changed += 1
            companions = local.get("companions")
            if isinstance(companions, dict):
                for role in ("mtp", "draft", "drafter"):
                    if role in companions:
                        del companions[role]
                        changed += 1

        bindings = [binding for binding in link.runtime_bindings if binding.config_path is not None]
        if len(bindings) != 1:
            continue
        binding = bindings[0]
        config_path = str(binding.config_path)
        if local.get("config_path") != config_path:
            local["config_path"] = config_path
            changed += 1
        if binding.config_scope and local.get("config_scope") != binding.config_scope:
            local["config_scope"] = binding.config_scope
            changed += 1

        if policy in {"disabled", "registry"}:
            continue
        speculative = dict(binding.speculative)
        normalized = normalize_speculative_profile(speculative)
        local_llama = local.get("llama_cpp")
        if normalized:
            if not isinstance(local_llama, dict):
                local_llama = {}
                local["llama_cpp"] = local_llama
            # The resolved absolute companion path is the persisted evidence;
            # the LMS logical reference is only an input to that resolution.
            local_speculative = {
                key: value
                for key, value in normalized.items()
                if key != "draft_model_reference"
            }
            role = companion_role(normalized)
            reference = str(speculative.get("draft_model_reference") or "").strip()
            persisted_role: str | None = None
            if role is not None:
                companion = _resolve_local_companion(reference) if reference else None
                if companion is not None:
                    previous = local_llama.get("speculative")
                    previous_companions = local.get("companions")
                    previous_path = previous_companions.get(role) if isinstance(previous_companions, dict) else None
                    if (
                        isinstance(previous, dict)
                        and isinstance(previous.get("pairing"), dict)
                        and previous.get("type") == normalized.get("type")
                        and previous.get("method") == normalized.get("method")
                        and previous.get("mode") == normalized.get("mode")
                        and isinstance(previous_path, str)
                        and _path_identity(previous_path) == _path_identity(companion)
                    ):
                        normalized["pairing"] = previous["pairing"]
                    bundle_errors = validate_companion_binding(main_path, companion, normalized)
                    if bundle_errors:
                        print(
                            f"  [WARN] {registry_key}: ungueltige {role}-Companion-Bindung: "
                            + "; ".join(bundle_errors)
                        )
                        companion = None
                    elif "pairing" in normalized:
                        local_speculative["pairing"] = normalized["pairing"]
                if companion is not None:
                    companions = local.setdefault("companions", {})
                    if not isinstance(companions, dict):
                        companions = {}
                        local["companions"] = companions
                    companion_path = str(companion)
                    if companions.get(role) != companion_path:
                        companions[role] = companion_path
                        changed += 1
                    local_speculative["companion_role"] = role
                    persisted_role = role
                elif role is not None:
                    print(
                        f"  [WARN] {registry_key}: erforderliche {role}-Companion-Datei "
                        "konnte nicht eindeutig und kompatibel aufgeloest werden"
                    )
            companions = local.get("companions")
            if isinstance(companions, dict):
                # Remove obsolete bundle links after a mode/type switch. Do
                # not touch unrelated future roles such as an mmproj link.
                for stale_role in {"mtp", "draft", "drafter"} - (
                    {persisted_role} if persisted_role is not None else set()
                ):
                    if stale_role in companions:
                        del companions[stale_role]
                        changed += 1
            for field in ("draft_n_max", "draft_n_min", "draft_p_min"):
                if field in speculative:
                    local_speculative[field] = speculative[field]
            if local_llama.get("speculative") != local_speculative:
                local_llama["speculative"] = local_speculative
                changed += 1
        elif isinstance(local_llama, dict) and "speculative" in local_llama:
            del local_llama["speculative"]
            changed += 1

    if changed:
        save_registry(inventory.registry)
    return changed


def _ensure_gguf_inventory(inventory: RegistryInventory) -> list[Any]:
    """Populate the shared local-file inventory once on first demand."""
    if inventory.gguf_candidates_loaded:
        # Registry maintenance may have rekeyed entries after the physical
        # scan. Re-evaluate the immutable artifact evidence against the latest
        # in-memory Registry without rescanning the filesystem.
        _refresh_identity_links(inventory)
        return cast("list[Any]", inventory.gguf_candidates)
    from local_model_resolver import LocalModelResolver

    roots: tuple[Path | None, ...] = inventory.gguf_roots if inventory.gguf_roots is not None else (
        *_gguf_roots(),
        *((Path.home() / ".lmstudio" / "hub" / "models",) if MODELS_CACHE == _DEFAULT_MODELS_CACHE else ()),
    )
    candidates_by_path: dict[str, Any] = {}
    seen_roots: set[str] = set()
    for root in roots:
        if root is None:
            root_identity = "configured-gguf-roots"
        else:
            try:
                root_identity = str(root.resolve(strict=False)).casefold()
            except OSError:
                root_identity = str(root.absolute()).casefold()
        if root_identity in seen_roots or (root is not None and not root.is_dir()):
            continue
        seen_roots.add(root_identity)
        resolver = LocalModelResolver(root, registry_loader=lambda: inventory.registry)
        for candidate in resolver.candidates():
            try:
                path_identity = str(candidate.path.resolve(strict=True)).casefold()
            except OSError:
                path_identity = str(candidate.path.absolute()).casefold()
            candidates_by_path.setdefault(path_identity, candidate)

    inventory.gguf_candidates = sorted(
        candidates_by_path.values(), key=lambda candidate: str(candidate.path).casefold()
    )
    inventory.gguf_candidates_loaded = True
    # Refresh after the scan so config links are based on the complete
    # path-derived artifact identity, not on a publisherless filename guess.
    _refresh_identity_links(inventory)
    return cast("list[Any]", inventory.gguf_candidates)


def _configure_utf8_output() -> None:
    """Make direct CLI output safe for Windows consoles and CI runners."""
    for stream in (sys.stdout, sys.stderr):
        try:
            reconfigure = getattr(stream, "reconfigure", None)
            if callable(reconfigure):
                reconfigure(encoding="utf-8", errors="replace")
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
    # Reuse the atomic writer so formatting also enforces the KV pair contract.
    if not REGISTRY_PATH.is_file():
        raise FileNotFoundError(f"Registry not found: {REGISTRY_PATH}")
    with REGISTRY_PATH.open(encoding="utf-8") as stream:
        reg = y.load(stream)
    if reg is None:
        reg = {}
    if not isinstance(reg, dict):
        raise ValueError(f"Registry root must be a mapping: {REGISTRY_PATH}")
    save_registry(reg)
    print(f"[OK] Blank lines formatted in {REGISTRY_PATH.name}")


# ── fill-ctx command ───────────────────────────────────────────────


# Feste Benchmark-Policy: np=1 bei SampleSize <= 5, sonst 4.
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
            kc = entry.get("k_cache")
            vc = entry.get("v_cache")
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
            kc = entry.get("k_cache")
            vc = entry.get("v_cache")
            new_ctx = _default_ctx_from_size(int(sb), _NP_POLICY, kc, vc)
            if entry.get("context_length") in (None, 0):
                entry["context_length"] = new_ctx
                updated += 1
    if updated:
        save_registry(reg)
    print(f"[OK] {updated} entries updated context_length")


# ── fill-size command ──────────────────────────────────────────────


def cmd_fill_size(
    inventory: RegistryInventory | None = None,
    refresh_existing: bool = False,
) -> int:
    """Fill/reconcile file_size_bytes from exact main GGUF files on disk.

    LM Studio's aggregate ``sizeBytes`` is deliberately never a fallback: it
    can include multimodal support files and is not the main GGUF's file size.
    """
    inventory = inventory or _collect_registry_inventory()
    reg = inventory.registry
    proposals: dict[str, dict[str, tuple[int, Path]]] = {}
    for candidate in _ensure_gguf_inventory(inventory):
        model = {
            "type": "llm",
            "modelKey": candidate.model_identifier,
            "path": str(candidate.path),
        }
        try:
            file_size = candidate.path.stat().st_size
        except OSError:
            continue
        if file_size <= 0:
            continue
        for key, entry in reg.items():
            if not isinstance(entry, dict):
                continue
            if _lms_record_for_registry_key(key, [model]) is not None:
                proposals.setdefault(key, {})[str(candidate.path)] = (file_size, candidate.path)

    updated = conflicts = 0
    for key, sources in proposals.items():
        sizes = {size for size, _path in sources.values()}
        if len(sizes) > 1:
            conflicts += 1
            paths = ", ".join(str(path) for _size, path in sources.values())
            print(f"[KONFLIKT] {key}: mehrere GGUF-Dateigrößen gefunden ({paths}); nicht geändert")
            continue
        size = next(iter(sizes))
        entry = reg[key]
        current = entry.get("file_size_bytes")
        if current == size or (current and not refresh_existing):
            continue
        entry["file_size_bytes"] = size
        updated += 1
        print(f"[VORSCHLAG] {key}: file_size_bytes {current!r} -> {size} (Haupt-GGUF auf Datenträger)")

    if updated:
        save_registry(reg)
    print(f"[OK] GGUF-Dateigröße: {updated} aktualisiert, {conflicts} mehrdeutig")
    return updated


def _find_gguf_for_key(key: str) -> Path | None:
    """Find the GGUF file for a registry key by scanning configured roots.

    Returns the Path or None if not found.
    """
    resolver = ArtifactResolver()
    resolver.model_roots = _gguf_roots()
    result = resolver.resolve(key)
    return result.path if result.is_unique else None


_GGUF_FILE_CACHE: list[Path] | None = None
_GGUF_FILE_CACHE_ROOTS: tuple[str, ...] | None = None


def _get_all_ggufs() -> list[Path]:
    """Return (and cache) all ``.gguf`` files under the configured roots."""
    global _GGUF_FILE_CACHE, _GGUF_FILE_CACHE_ROOTS
    roots = _gguf_roots()
    root_key = tuple(str(root).casefold() for root in roots)
    if _GGUF_FILE_CACHE is None or _GGUF_FILE_CACHE_ROOTS != root_key:
        resolver = ArtifactResolver()
        resolver.model_roots = roots
        _GGUF_FILE_CACHE = [path for _root_index, path in resolver.files(include_support=True)]
        _GGUF_FILE_CACHE_ROOTS = root_key
    return _GGUF_FILE_CACHE


# Zentralisiert in benchmark_config.py (Code-Review 2026-08-03 §F1):
# wird identisch von model_manager.get_available_models() genutzt.
_is_support_file = is_support_file


def _resolve_hub_source_gguf(key: str, entry: dict[str, Any]) -> Path | None:
    """Resolve a Registry model through its local LM Studio Hub source mapping.

    Hub identities can point at a differently named GGUF repository, e.g.
    ``essentialai/rnj-1`` -> ``lmstudio-community/rnj-1-instruct-GGUF``.
    Only a file with the exact Registry quant suffix is accepted.
    """
    hub_model = _hub_model_yaml(entry, key)
    if hub_model is None or "@" not in key:
        return None
    _hub_path, metadata = hub_model
    source_paths: list[tuple[str, ...]] = []
    bases = metadata.get("base", [])
    if not isinstance(bases, list):
        return None
    for base in bases:
        if not isinstance(base, dict):
            continue
        base_key = base.get("key")
        if isinstance(base_key, str):
            parts = tuple(part for part in base_key.replace("\\", "/").split("/") if part)
            if len(parts) >= 2 and all(part not in {".", ".."} for part in parts):
                source_paths.append(parts)
        sources = base.get("sources", [])
        if not isinstance(sources, list):
            continue
        for source in sources:
            if not isinstance(source, dict) or str(source.get("type", "")).casefold() != "huggingface":
                continue
            user = source.get("user")
            repo = source.get("repo")
            if isinstance(user, str) and isinstance(repo, str):
                parts = (user.strip(), repo.strip())
                if all(part and part not in {".", ".."} and "/" not in part and "\\" not in part for part in parts):
                    source_paths.append(parts)

    resolver = ArtifactResolver()
    resolver.model_roots = _gguf_roots()
    resolved = resolver.resolve(key, source_paths=tuple(dict.fromkeys(source_paths)))
    return resolved.path if resolved.is_unique else None


def _resolve_model_path_multi(key: str, entry: dict[str, Any] | None = None) -> str:
    """Resolve a GGUF path through the shared fail-closed artifact resolver.

    1. Exact ``GGUF root / key`` — library-level path from LM Studio.
    2. Explicit Hub source mapping, when available.
    3. Unique normalized filename match.
    Ambiguous and fuzzy matches return ``""`` instead of selecting a first
    path; diagnostics can inspect ``ArtifactResolution.candidates``.
    """
    if entry is not None:
        local = entry.get("local")
        configured_path = local.get("model_path") if isinstance(local, dict) else None
        if isinstance(configured_path, str) and configured_path.strip():
            path = Path(configured_path.strip())
            if path.is_file() and path.suffix.casefold() == ".gguf":
                return str(path)
            # A persisted local binding is authoritative. Do not silently
            # substitute another similarly named file when it is stale.
            return ""

    candidate = _find_gguf_relative_path(key)
    if candidate is not None:
        return str(candidate)
    if entry is not None:
        hub_candidate = _resolve_hub_source_gguf(key, entry)
        if hub_candidate is not None:
            return str(hub_candidate)

    resolver = ArtifactResolver()
    resolver.model_roots = _gguf_roots()
    resolved = resolver.resolve(key)
    return str(resolved.path) if resolved.is_unique else ""


def _preset_value(value: Any) -> str:
    """Serialize a Registry value in the conservative preset INI form."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def build_llama_preset(
    registry: dict[str, Any],
) -> tuple[str, list[str]]:
    """Build a llama.cpp preset from locally resolvable Registry entries.

    The generated file is a derived launch artifact.  Registry policy remains
    authoritative; entries without a local GGUF are reported and omitted
    instead of causing a remote download or an invented model path.
    """
    runtime_registry = ModelRegistry(registry_loader=lambda: registry)
    lines = [
        "# Generated by src/registry_tool.py export-llama-preset.",
        "# Derived launch artifact; edit model_registry.yaml instead.",
        "# Sampling defaults stay request-level and are intentionally omitted.",
        "",
    ]
    skipped: list[str] = []
    option_map = (
        ("context_length", "ctx-size"),
        ("parallel", "parallel"),
        ("cache_type_k", "cache-type-k"),
        ("cache_type_v", "cache-type-v"),
        ("kv_unified", "kv-unified"),
        ("batch_size", "batch-size"),
        ("ubatch_size", "ubatch-size"),
        ("gpu_layers", "gpu-layers"),
        ("flash_attn", "flash-attn"),
        ("cont_batching", "cont-batching"),
        ("jinja", "jinja"),
        ("chat_template_file", "chat-template-file"),
        ("reasoning_format", "reasoning-format"),
        ("reasoning_effort", "reasoning-effort"),
        ("reasoning_budget", "reasoning-budget"),
        ("spec_type", "spec-type"),
        ("draft_model_path", "spec-draft-model"),
        ("draft_n_max", "spec-draft-n-max"),
        ("draft_n_min", "spec-draft-n-min"),
        ("draft_p_min", "spec-draft-p-min"),
    )
    for key in sorted(registry, key=str.casefold):
        entry = registry.get(key)
        if not isinstance(entry, dict):
            continue
        model_path = _resolve_model_path_multi(key, entry)
        if not model_path:
            skipped.append(key)
            continue
        try:
            runtime = runtime_registry.provider_runtime(key, "llama_cpp")
        except KVCachePolicyError:
            raise
        except ValueError as exc:
            skipped.append(f"{key} (invalid local bundle: {exc})")
            continue
        runtime["cache_type_k"], runtime["cache_type_v"] = runtime_kv_pair(
            runtime.get("cache_type_k"), runtime.get("cache_type_v")
        )
        lines.extend((f"[{key}]", "# registry_tool:generated-section", f"model = {model_path}"))
        for source_key, preset_key in option_map:
            value = runtime.get(source_key)
            if value is not None and _preset_value(value):
                lines.append(f"{preset_key} = {_preset_value(value)}")
        # ``experts`` is a Registry runtime value, while the llama.cpp
        # metadata key depends on the model architecture.  ModelRegistry
        # derives the architecture-specific key from ``architecture_family``;
        # never guess a key when that information is missing.
        expert_count = runtime.get("num_experts")
        expert_key = runtime.get("expert_override_key")
        if (
            isinstance(expert_count, int)
            and not isinstance(expert_count, bool)
            and expert_count > 0
            and isinstance(expert_key, str)
            and expert_key.strip()
        ):
            lines.append(
                f"override-kv = {expert_key.strip()}=int:{expert_count}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n", skipped


def _ini_blocks(content: str) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """Split an INI into preamble and ordered named blocks."""
    preamble: list[str] = []
    blocks: list[tuple[str, list[str]]] = []
    current_name: str | None = None
    current_lines: list[str] = []
    for line in content.splitlines():
        match = re.match(r"^\s*\[([^]]+)\]\s*$", line)
        if match:
            if current_name is not None:
                blocks.append((current_name, current_lines))
            current_name = match.group(1).strip()
            current_lines = [line]
        elif current_name is None:
            preamble.append(line)
        else:
            current_lines.append(line)
    if current_name is not None:
        blocks.append((current_name, current_lines))
    return preamble, blocks


def merge_llama_preset(existing: str, generated: str) -> str:
    """Merge generated model sections into an existing llama.cpp preset.

    Existing global settings and custom sections are retained.  A generated
    section with the same name replaces the old generated section, making
    repeated exports idempotent without creating duplicate INI sections.
    """
    existing_preamble, existing_blocks = _ini_blocks(existing)
    _, generated_blocks = _ini_blocks(generated)
    generated_by_name = dict(generated_blocks)
    legacy_generated_file = any(
        "Registry-generated llama.cpp model sections" in line for line in existing_preamble
    )
    merged: list[tuple[str, list[str]]] = []
    replaced: set[str] = set()
    for name, lines in existing_blocks:
        if name in generated_by_name:
            merged.append((name, generated_by_name[name]))
            replaced.add(name)
        elif name != "*" and (
            any("registry_tool:generated-section" in line for line in lines)
            or (
                legacy_generated_file
                and any(re.match(r"^\s*model\s*=", line, re.IGNORECASE) for line in lines)
            )
        ):
            # Remove sections produced by older exports when the current
            # inventory no longer contains that model. Manual `hf = ...`
            # sections and the user-owned `[*]` defaults are retained.
            continue
        else:
            merged.append((name, lines))
    merged.extend(
        (name, lines)
        for name, lines in generated_blocks
        if name not in replaced and name not in {item[0] for item in existing_blocks}
    )
    output = [
        line
        for line in existing_preamble
        if "Registry-generated llama.cpp model sections" not in line
    ]
    if output and output[-1].strip():
        output.append("")
    for _, lines in merged:
        if output and output[-1].strip():
            output.append("")
        output.extend(lines)
    return normalize_llama_preset("\n".join(output).rstrip() + "\n")


def normalize_llama_preset(content: str) -> str:
    """Normalize every explicit KV pair, including retained global/manual blocks."""
    preamble, blocks = _ini_blocks(content)
    output: list[str] = []
    for name, lines in [("preamble", preamble), *blocks]:
        cache_lines: dict[str, list[tuple[int, re.Match[str]]]] = {"k": [], "v": []}
        for index, line in enumerate(lines):
            match = re.match(r"^(\s*cache-type-([kv])\s*[=:]\s*)([^#;]*)(.*)$", line, re.IGNORECASE)
            if match:
                cache_lines[match.group(2).lower()].append((index, match))
        values: dict[str, str | None] = {}
        for side, matches in cache_lines.items():
            observed = [kv_cache_type(match.group(3)) for _index, match in matches]
            if len(set(observed)) > 1:
                raise KVCachePolicyError(f"Conflicting cache-type-{side} values in preset section {name}")
            values[side] = observed[0] if observed else None
        pair = normalize_kv_pair(values["k"], values["v"])
        if pair[0] is not None:
            for side, value in zip(("k", "v"), pair, strict=True):
                for index, match in cache_lines[side]:
                    suffix = match.group(4)
                    lines[index] = f"{match.group(1)}{value}" + (f" {suffix}" if suffix else "")
                if not cache_lines[side]:
                    lines.append(f"cache-type-{side} = {value}")
        output.extend(lines)
    return "\n".join(output).rstrip() + "\n"


def cmd_export_llama_preset(
    output_path: str | Path | None = None,
    merge_existing: bool = False,
) -> int:
    """Write the derived local llama.cpp preset and report skipped entries."""
    target = Path(output_path) if output_path else PROJECT_ROOT / "ergebnisse" / "llama-cpp-generated" / "preset.ini"
    try:
        registry = load_registry()
        content, skipped = build_llama_preset(registry)
        generated_count = content.count("\n[")
        if merge_existing and target.exists():
            content = merge_llama_preset(target.read_text(encoding="utf-8"), content)
        content = normalize_llama_preset(content)
        _atomic_write_text(target, content)
    except (OSError, KVCachePolicyError) as exc:
        print(f"[ERROR] Could not write llama.cpp preset {target}: {exc}")
        return 1
    written = generated_count
    action = "Merged into" if merge_existing else "Wrote"
    print(f"[OK] {action} llama.cpp preset: {target} ({written} local models)")
    if skipped:
        print(f"[WARN] Skipped {len(skipped)} Registry entries without a resolvable main GGUF or with an invalid local bundle")
        for key in skipped:
            print(f"       - {key}")
    return 0


def _llama_server_metadata(executable: Path) -> dict[str, Any]:
    """Read the selected llama-server version without starting a server."""
    metadata: dict[str, Any] = {"path": str(executable), "version": None}
    if not executable.is_file():
        return metadata
    try:
        result = subprocess.run(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, TimeoutError):
        return metadata
    version = (result.stdout or result.stderr or "").strip()
    if version:
        metadata["version"] = version[:2000]
    return metadata


def build_llama_argument_manifest(
    registry: dict[str, Any],
    executable: str | Path | None = None,
    api_base: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Build a reproducible direct llama.cpp argument manifest."""
    runtime_registry = ModelRegistry(registry_loader=lambda: registry)
    selected_executable = Path(
        executable
        or os.environ.get("LLAMA_CPP_SERVER_EXE")
        or r"C:\Program Files\llama.cpp\llama-server.exe"
    )
    base = api_base or os.environ.get("LLAMA_CPP_API_BASE", "http://127.0.0.1:8080/v1")
    parsed_base = urlsplit(base)
    port = parsed_base.port or 8080
    warnings: list[str] = []
    models: list[dict[str, Any]] = []
    skipped: list[str] = []

    for key in sorted(registry, key=str.casefold):
        entry = registry.get(key)
        if not isinstance(entry, dict):
            continue
        model_path = _resolve_model_path_multi(key, entry)
        if not model_path:
            skipped.append(key)
            continue
        benchmark_runtime = runtime_registry.benchmark_runtime(key)
        runtime = runtime_registry.provider_runtime(key, "llama_cpp")
        command = build_server_command(
            selected_executable,
            model_path,
            key,
            port,
            runtime,
            warning=warnings.append,
        )
        request_defaults: dict[str, Any] = {}
        sampling = benchmark_runtime.get("sampling")
        if isinstance(sampling, dict):
            request_defaults["sampling"] = sampling
        for field in ("reasoning", "reasoning_format"):
            value = runtime.get(field, benchmark_runtime.get(field))
            if value is not None:
                request_defaults[field] = value
        models.append(
            {
                "registry_key": key,
                "model_path": model_path,
                "start_args": command[1:],
                "request_defaults": request_defaults,
            }
        )

    registry_bytes = REGISTRY_PATH.read_bytes() if REGISTRY_PATH.exists() else b""
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "registry_sha256": hashlib.sha256(registry_bytes).hexdigest(),
        "provider": "llama_cpp",
        "server": _llama_server_metadata(selected_executable),
        "api_base": base,
        "models": models,
        "skipped_registry_entries": skipped,
        "warnings": sorted(set(warnings)),
    }
    return manifest, skipped


def cmd_export_llama_args(output_path: str | Path | None = None) -> int:
    """Write a JSON manifest with direct llama.cpp start/request arguments."""
    target = Path(output_path) if output_path else PROJECT_ROOT / "ergebnisse" / "llama-cpp-generated" / "args-manifest.json"
    registry = load_registry()
    manifest, skipped = build_llama_argument_manifest(registry)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    except OSError as exc:
        print(f"[ERROR] Could not write llama.cpp argument manifest {target}: {exc}")
        return 1
    print(f"[OK] Wrote llama.cpp argument manifest: {target} ({len(manifest['models'])} local models)")
    if skipped:
        print(f"[WARN] Skipped {len(skipped)} Registry entries without a local GGUF")
    if manifest["warnings"]:
        for message in manifest["warnings"]:
            print(f"[WARN] {message}")
    return 0


# ── fix-np command ─────────────────────────────────────────────────


def _normalize_variants(key: str) -> set[str]:
    """All normalized spellings of a model key.

    Covers publisher prefixes (``unsloth/x`` vs ``x`` vs ``unsloth_x``),
    quant suffixes are stripped via the ``@`` split. Only used for
    **exact** comparisons, never for fuzzy word matching.
    """
    # Konsolidiert in model_identity.py (Fix 2026-08-09).
    return cast("set[str]", normalize_variants(key))


def _quant_variant(key: str) -> str:
    """Normalized spelling of a quant-suffixed key (``...@q5_0`` → ``...@q5-0``).

    Keeps the quant, so keys with different quantizations stay distinct.
    """
    return str(normalize_model_name(key))


def _resolve_exact(reg_key: str, lms_path_map: dict[str, str]) -> str:
    """Resolve one exact LMS/artifact identity without fuzzy fallback.

    Deliberately no substring or word-match fallback: only a unique artifact
    may end up in the same duplicate-collapse group.
    """
    candidate = _find_gguf_relative_path(reg_key)
    if candidate is not None:
        return str(candidate)
    for probe in (reg_key.lower(), normalize_model_name(reg_key)):
        mp = lms_path_map.get(probe, "")
        if mp and os.path.isfile(mp):
            return mp
    return ""


def cmd_fix_np() -> None:
    """Seit 13.08. überflüssig: np ist feste Policy (SS<=5 → 1, sonst 4),
    kein Registry-Feld mehr. Arch-Reclassification erledigt sync-from-gguf."""
    print("[INFO] fix-np entfällt: num_parallel ist seit 13.08. eine feste")
    print("       Benchmark-Policy (SS<=5 → 1, sonst 4) und kein Registry-Feld.")
    print("       Arch-Reclassification: registry_tool.py sync-from-gguf.")


# ── compare command ────────────────────────────────────────────────


def cmd_compare(inventory: RegistryInventory | None = None) -> dict[str, Any]:
    inventory = inventory or _collect_registry_inventory()
    _ensure_gguf_inventory(inventory)
    reg = inventory.registry
    lms = inventory.lms_models
    cfgs = inventory.configs

    registry_keys = [k for k, v in reg.items() if isinstance(v, dict)]
    registry_key_set = set(registry_keys)
    physical_matches_by_model = {
        id(model): _physical_registry_matches_lms_model(
            model,
            inventory.gguf_candidates,
            registry_key_set,
        )
        for model in lms
    }

    def model_matches_registry(model: dict[str, Any], registry_key: str) -> bool:
        if _lms_matches_registry_key(model, registry_key):
            return True
        physical_matches = physical_matches_by_model.get(id(model), ())
        return len(physical_matches) == 1 and physical_matches[0] == registry_key

    new_models: list[dict[str, Any]] = []
    for model in lms:
        if not any(model_matches_registry(model, key) for key in registry_keys):
            new_models.append(model)

    missing: list[str] = []
    for rn, re_ in reg.items():
        if (
            not isinstance(re_, dict)
            or re_.get("blueprint") == "none"
            or not is_registry_candidate({"modelKey": rn})
        ):
            continue
        if not any(model_matches_registry(model, rn) for model in lms):
            missing.append(rn)

    orphan: set[str] = set()
    registry_key_sorted = sorted(
        [(normalize_model_name(k), k) for k in registry_keys],
        key=lambda x: -len(x[0]),
    )
    identity_linked_configs = {
        _path_identity(config_path)
        for link in inventory.identity_links.values()
        for config_path in link.config_paths
    }
    for c in cfgs:
        if _path_identity(c.get("json_path") or "") in identity_linked_configs:
            continue
        n = normalize_model_name(c["dir_name"])
        if find_registry_key_for_config(n, registry_key_sorted, config=c) is None:
            orphan.add(f"{c['publisher']}/{c['dir_name']}")

    active_config_count = sum(
        1
        for config in cfgs
        if any(_config_matches_lms_model(config, model) for model in lms)
    )
    config_proposals, skipped_config_count, config_conflicts = _build_config_sync_proposal(
        reg,
        cfgs,
        lms,
        (
            ("offload", "offload"),
            ("useUnifiedKvCache", "use_unified_kv"),
            ("context_length", "context_length"),
            ("k_cache", "k_cache"),
            ("v_cache", "v_cache"),
            ("experts", "num_experts"),
        ),
        inventory.identity_links,
    )

    report = {
        "lms_all": len(inventory.raw_lms_models),
        "lms": len(lms),
        "reg": len(registry_keys),
        "cfg": len(cfgs),
        "active_cfg": active_config_count,
        "local_gguf": (
            len(inventory.gguf_candidates) if inventory.gguf_candidates_loaded else None
        ),
        "local_gguf_scanned": inventory.gguf_candidates_loaded,
        "new": len(new_models),
        "missing": len(missing),
        "orphan": len(orphan),
        "config_changes": len(config_proposals),
        "config_conflicts": config_conflicts,
        "unmatched_or_stale_configs": skipped_config_count,
        "proposals": [
            {
                "model": item.model_key,
                "field": item.field,
                "registry": item.current,
                "lms": item.proposed,
                "sources": [str(source) for source in item.sources],
            }
            for item in config_proposals
            if not item.conflict and not item.problem
        ],
        "conflicts": [
            {
                "model": item.model_key,
                "field": item.field,
                "values": item.proposed,
                "sources": [str(source) for source in item.sources],
                "reason": item.problem or "different values across active configs",
            }
            for item in config_proposals
            if item.conflict or item.problem
        ],
        "newd": [
            {
                "key": m.get("modelKey", "?"),
                "publisher": m.get("publisher", "?"),
                "arch": m.get("architecture", "?"),
                "params": m.get("paramsString", "?"),
                "ctx": m.get("maxContextLength", 0),
                "vision": m.get("vision", False),
                "tools": m.get("trainedForToolUse", False),
                "path": m.get("path", ""),
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


def _missing_registry_keys(
    lms: list[dict[str, Any]], registry: dict[str, Any] | None = None
) -> list[str]:
    """Registry-Keys ohne passendes installiertes LMS-Modell.

    Strenge Erkennung: @-Quant-Varianten nur installiert, wenn LMS exakt
    diese Variante führt. (compare nutzt bewusst Substring - dort ist der
    Report konservativ; Quarantäne entfernt nur nachweislich fehlende.)
    """
    reg = registry if registry is not None else load_registry()
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


def _gguf_for_key_exists(key: str, candidates: list[Any] | None = None) -> bool:
    """Return whether an exact local model identity exists outside LMS inventory.

    Resolve GGUF files using the shared local-model scanner, then compare
    publisher/model/quant identities. Similar filenames, other quantizations,
    and auxiliary files such as ``mmproj`` do not count as the requested GGUF.
    """
    if candidates is None:
        from local_model_resolver import LocalModelResolver

        candidates = []
        for root in (*_gguf_roots(), Path.home() / ".lmstudio" / "hub" / "models"):
            if root.is_dir():
                candidates.extend(LocalModelResolver(root).candidates())
    candidate_models = [
        {
            "type": "llm",
            "modelKey": candidate.model_identifier,
            "path": str(candidate.path),
        }
        for candidate in candidates
    ]
    return _lms_record_for_registry_key(key, candidate_models) is not None


def _config_claimed_by_other(
    cfg: dict[str, Any],
    key: str,
    reg: dict[str, Any],
    cfgs: list[dict[str, Any]],
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


def cmd_quarantine_missing(
    dry_run: bool = True,
    inventory: RegistryInventory | None = None,
    move_configs: bool = True,
) -> int:
    """Registry-Einträge nicht-installierter Modelle in Quarantäne verschieben.

    Für jeden Registry-Key ohne passendes LMS-Modell (missing-Liste wie
    ``compare``):
      1. GGUF physisch noch vorhanden? -> nur melden (Index-Problem vermutet).
      2. Sonst: zugehörige JSON-Configs nach ``_quarantine_missing_<ts>``
         verschieben (nicht löschen), Registry-Eintrag entfernen.
      3. Entfernte Einträge als YAML-Backup sichern (reversibel).
    Standardmäßig wird nur ein Vorschlag angezeigt. Schreiben/Verschieben
    ist ausschließlich mit ``dry_run=False`` zulässig.
    """
    inventory = inventory or _collect_registry_inventory()
    _ensure_gguf_inventory(inventory)
    lms = inventory.lms_models
    if not lms:
        print("[WARN] lms ls lieferte keine Modelle - Quarantäne übersprungen (kein Auto-Löschen).")
        return 1

    reg = inventory.registry
    cfgs = inventory.configs
    missing = _missing_registry_keys(lms, registry=reg)
    gguf_candidates = _ensure_gguf_inventory(inventory)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    quarantine_dir = CONFIG_ROOT / f"_quarantine_missing_{ts}"
    backup_path = (
        PROJECT_ROOT / "docs" / "Review-Artifacts" / f"quarantine_registry_{ts}.yaml"
    )

    quarantined: list[str] = []
    reported: list[str] = []
    backup_entries: dict[str, Any] = {}
    for key in sorted(missing):
        if _gguf_for_key_exists(key, gguf_candidates):
            reported.append(key)
            print(f"  [HINWEIS] {key}: GGUF existiert physisch - nur gemeldet (Index-Problem vermutet)")
            continue
        quarantined.append(key)
        entry = reg.get(key)
        is_partial = isinstance(entry, dict) and set(entry.keys()) <= {"reasoning", "blueprint"}
        if not is_partial:
            backup_entries[key] = entry

    remaining = {key: value for key, value in reg.items() if key not in quarantined}
    planned_moves: list[tuple[str, Path, Path]] = []
    for key in quarantined if move_configs else []:
        for config in find_all_configs_for_registry_key(key, cfgs):
            claimed = _config_claimed_by_other(config, key, remaining, cfgs)
            if claimed:
                print(
                    f"  [BEHALTEN] {key}: Config {config['publisher']}/{config['dir_name']}/"
                    f"{config['file_name']} wird auch von {claimed} verwendet"
                )
                continue
            flat = CONFIG_ROOT / config["publisher"] / config["file_name"]
            nested = CONFIG_ROOT / config["publisher"] / config["dir_name"] / config["file_name"]
            source = nested if nested.is_file() else flat
            if source.is_file():
                destination = quarantine_dir / source.relative_to(CONFIG_ROOT)
                planned_moves.append((key, source, destination))

    for key in quarantined:
        action = "würde verschieben/entfernen" if dry_run else "wird verschoben/entfernt"
        print(f"  [{'VORSCHLAG' if dry_run else 'PLAN'}] {key}: Configs und Registry-Eintrag {action}")
    for _key, source, destination in planned_moves:
        print(f"      Config: {source} -> {destination}")

    moved: list[tuple[Path, Path]] = []
    backup_written = False
    if not dry_run and quarantined:
        try:
            for _key, source, destination in planned_moves:
                if destination.exists():
                    raise FileExistsError(f"Quarantäne-Ziel existiert bereits: {destination}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(destination))
                moved.append((source, destination))
            if backup_entries:
                _atomic_write_yaml(backup_path, backup_entries)
                backup_written = True
            updated_registry = {key: value for key, value in reg.items() if key not in quarantined}
            save_registry(updated_registry)
            reg.clear()
            reg.update(updated_registry)
        except Exception as exc:
            for source, destination in reversed(moved):
                try:
                    source.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(destination), str(source))
                except OSError as rollback_error:
                    print(f"[ERROR] Rückverschieben fehlgeschlagen {destination}: {rollback_error}")
            if quarantine_dir.is_dir():
                for directory in sorted(
                    (path for path in quarantine_dir.rglob("*") if path.is_dir()),
                    key=lambda path: len(path.parts),
                    reverse=True,
                ):
                    try:
                        directory.rmdir()
                    except OSError:
                        pass
                try:
                    quarantine_dir.rmdir()
                except OSError:
                    pass
            if backup_written:
                try:
                    backup_path.unlink(missing_ok=True)
                except OSError as rollback_error:
                    print(f"[ERROR] Registry-Backup konnte nicht entfernt werden: {rollback_error}")
            print(f"[ERROR] Quarantäne abgebrochen; Änderungen soweit möglich zurückgerollt: {exc}")
            return 1

    verb = "vorgeschlagen" if dry_run else "quarantänisiert"
    print(
        f"[OK] {len(quarantined)} Modelle {verb}, "
        f"{len(planned_moves) if not dry_run else 0} Config(s) verschoben, "
        f"{len(reported)} nur gemeldet (GGUF vorhanden)."
    )
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

    Seit 13.08.: num_parallel ist eine feste Benchmark-Policy (SS<=5 → 1, sonst 4),
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
        if is_support_model_record(m):
            skipped.append(
                (
                    str(m.get("modelKey") or m.get("key") or "?"),
                    "Zusatzdatei (MTP-/Draft-Sidecar/mmproj/imatrix) - kein eigenständiges Modell",
                )
            )
            continue
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
        if "@" not in canonical:
            canonical = f"{canonical}@?"
        canonical_base = canonical.split("@", 1)[0]
        sk = normalize_registry_identity(canonical)
        # Exact match (including @quant) — always a duplicate
        exact_match = resolve_registry_match(canonical, list(reg))
        if isinstance(exact_match, UniqueMatch) and normalize_registry_identity(exact_match.key) == sk:
            skipped.append((mk, "bereits vorhanden"))
            continue
        # Base entry (without @quant) when a @quant variant already exists,
        # e.g. skip "model" if "model@q3_k_s" exists. Multiple @quant variants
        # (@q3_k_s, @q6_k) should coexist. @? variants filtered by is_support_file.
        if "@" not in sk:
            if any(
                "@" in k and normalize_registry_identity(k, include_quant=False) == sk
                for k in reg
            ):
                skipped.append((mk, "bereits vorhanden (Quant-Variante existiert)"))
                continue
        else:
            # @quant variant: remove existing base entry (without @) if present.
            # The base entry is ambiguous; the @quant entry is specific and has a
            # unique file_size_bytes.
            base_key = normalize_registry_identity(canonical, include_quant=False)
            base_entry = next(
                (
                    k
                    for k in reg
                    if "@" not in k and normalize_registry_identity(k, include_quant=False) == base_key
                ),
                None,
            )
            if base_entry is not None:
                print(f"  [CLEANUP] Entferne Base-Eintrag '{base_key}' (ersetzt durch {mk})")
                del reg[base_entry]
        if is_blacklisted_model_name(mk):
            skipped.append((mk, "blacklisted"))
            continue
        rp = m.get("path", "")
        if rp and _is_support_file(rp, str(m.get("architecture") or "")):
            skipped.append((mk, "Zusatzdatei (MTP-/Draft-Sidecar/mmproj/imatrix) - kein eigenständiges Modell"))
            continue
        model_path = ""
        full_path: Path | None = None
        if rp:
            mp_candidate = _find_gguf_relative_path(rp)
            if mp_candidate is not None and not _is_support_file(str(mp_candidate)):
                full_path = mp_candidate
                model_path = str(full_path)
        try:
            size_bytes = full_path.stat().st_size if full_path is not None else 0
        except OSError:
            size_bytes = 0
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
        entry: dict[str, Any] = {
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
            entry["context_length"] = _default_ctx_from_size(
                int(size_bytes), _NP_POLICY, entry.get("k_cache"), entry.get("v_cache")
            )
        else:
            entry["context_length"] = 16384

        # Auto-fill arch data from GGUF file if available
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
            research_inventory = RegistryInventory({**reg, canonical: entry}, models, models, [], [])
            _ensure_gguf_inventory(research_inventory)
            _refresh_identity_links(research_inventory)
            research_model = _sampling_research_model(canonical, entry, research_inventory)
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


def _sampling_research_model(
    model_key: str,
    entry: dict[str, Any],
    inventory: RegistryInventory,
) -> dict[str, Any]:
    """Bind web roots to the concrete artifact proven by the IdentityLink."""
    repositories: list[str] = []
    link = inventory.identity_links.get(model_key)
    if link is not None and len(link.artifact_evidence) == 1:
        evidence = link.artifact_evidence[0]
        publisher, _, quant = decompose_model_identity(model_key)
        reference = evidence.source_reference.split("@", 1)[0]
        if (
            evidence.is_complete and reference.count("/") == 1
            and evidence.publisher == publisher
            and normalize_quant(evidence.quant) == normalize_quant(quant)
        ):
            repositories.append(reference)
    return {
        **entry,
        "modelKey": model_key,
        "publisher": entry.get("publisher") or model_key.split("/", 1)[0],
        "proven_hf_repositories": repositories,
    }


def _research_missing_sampling(
    reg: dict[str, Any],
    force: bool = False,
    *,
    inventory: RegistryInventory | None = None,
    model_keys: set[str] | None = None,
) -> list[str]:
    """Research sampling incrementally, or every candidate when forced."""
    if inventory is None:
        inventory = RegistryInventory(reg, [], [], [], [])
    inventory.registry = reg
    _ensure_gguf_inventory(inventory)
    _refresh_identity_links(inventory)
    unresolved: list[str] = []
    changed = False
    for model_key, entry in reg.items():
        if model_keys is not None and model_key not in model_keys:
            continue
        if not isinstance(entry, dict):
            continue
        if not force and "sampling" in entry:
            continue
        raw_sampling = entry.get("sampling")
        sampling_block = raw_sampling if isinstance(raw_sampling, dict) else {}
        if not force and (
            entry.get("sampling_research_status")
            or sampling_block.get("sampling_research_status")
        ):
            continue
        if not is_registry_candidate({"modelKey": model_key}):
            continue
        model = _sampling_research_model(model_key, entry, inventory)
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
            kc, vc = normalize_kv_pair(entry.get("k_cache"), entry.get("v_cache"))
            kv_bytes = _KV_BYTES.get(kc or "q8_0", 1.0) + _KV_BYTES.get(vc or "q8_0", 1.0)
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


def _build_config_sync_proposal(
    registry: dict[str, Any],
    configs: list[dict[str, Any]],
    installed_models: list[dict[str, Any]] | None,
    fields_to_sync: tuple[tuple[str, str], ...],
    identity_links: dict[str, IdentityLink] | None = None,
) -> tuple[list[SyncProposalItem], int, int]:
    """Build field-level import proposals without changing source files."""
    active_configs = configs
    stale_count = 0
    if installed_models is not None:
        linked_config_paths = {
            _path_identity(path)
            for link in (identity_links or {}).values()
            for path in link.config_paths
        }
        active_configs = [
            config
            for config in configs
            if _path_identity(config.get("json_path") or "") in linked_config_paths
            or any(_config_matches_lms_model(config, model) for model in installed_models)
        ]
        stale_count = len(configs) - len(active_configs)

    registry_keys = sorted(
        [(normalize_model_name(key), key) for key, value in registry.items() if isinstance(value, dict)],
        key=lambda item: -len(item[0]),
    )
    observations: dict[str, dict[str, list[tuple[Any, Path]]]] = {}
    unmatched_count = 0
    issues: list[SyncProposalItem] = []
    for config in active_configs:
        source_path = Path(config["json_path"])
        if identity_links is not None:
            matching_keys = [
                model_key
                for model_key, link in identity_links.items()
                if source_path in link.config_paths
            ]
        else:
            matching_keys = find_registry_matches_for_config(
                normalize_model_name(config["dir_name"]), registry_keys, config=config
            )
        if not matching_keys:
            unmatched_count += 1
            continue
        if len(matching_keys) > 1:
            issues.append(
                SyncProposalItem(
                    f"{config['publisher']}/{config['dir_name']}",
                    "model identity",
                    None,
                    tuple(matching_keys),
                    (source_path,),
                    conflict=True,
                    problem="multiple Registry keys match this config",
                )
            )
            continue
        model_key = matching_keys[0]
        if is_blacklisted_model_name(model_key):
            continue
        config = dict(config)
        if any(field in {"k_cache", "v_cache"} for field, _source in fields_to_sync):
            try:
                config["k_cache"], config["v_cache"] = normalize_kv_pair(config.get("k_cache"), config.get("v_cache"))
            except KVCachePolicyError as exc:
                issues.append(SyncProposalItem(
                    model_key, "KV-cache pair", None, (config.get("k_cache"), config.get("v_cache")),
                    (source_path,), conflict=True, problem=str(exc),
                ))
                continue
        for field, config_field in fields_to_sync:
            value = config.get(config_field)
            if value is None:
                continue
            if field in {"context_length", "experts"}:
                try:
                    if isinstance(value, bool):
                        raise ValueError
                    value = int(value)
                except (TypeError, ValueError):
                    issues.append(
                        SyncProposalItem(
                            model_key,
                            field,
                            registry.get(model_key, {}).get(field),
                            value,
                            (source_path,),
                            conflict=True,
                            problem="invalid integer value",
                        )
                    )
                    continue
                if value <= 0:
                    issues.append(
                        SyncProposalItem(
                            model_key,
                            field,
                            registry.get(model_key, {}).get(field),
                            value,
                            (source_path,),
                            conflict=True,
                            problem="value must be greater than zero",
                        )
                    )
                    continue
            elif field == "offload":
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    issues.append(
                        SyncProposalItem(
                            model_key,
                            field,
                            registry.get(model_key, {}).get(field),
                            value,
                            (source_path,),
                            conflict=True,
                            problem="invalid offload value",
                        )
                    )
                    continue
                if not 0 <= value <= 1:
                    issues.append(
                        SyncProposalItem(
                            model_key,
                            field,
                            registry.get(model_key, {}).get(field),
                            value,
                            (source_path,),
                            conflict=True,
                            problem="offload must be between zero and one",
                        )
                    )
                    continue
            elif field == "useUnifiedKvCache":
                if not isinstance(value, bool):
                    issues.append(
                        SyncProposalItem(
                            model_key,
                            field,
                            registry.get(model_key, {}).get(field),
                            value,
                            (source_path,),
                            conflict=True,
                            problem="value must be boolean",
                        )
                    )
                    continue
            elif field in {"k_cache", "v_cache"}:
                if not isinstance(value, str) or not value.strip():
                    issues.append(
                        SyncProposalItem(
                            model_key,
                            field,
                            registry.get(model_key, {}).get(field),
                            value,
                            (source_path,),
                            conflict=True,
                            problem="cache type must be a non-empty string",
                        )
                    )
                    continue
                value = value.strip().lower()
            entry = registry.get(model_key, {})
            upper_limit_field = {
                "context_length": "max_context_length",
                "experts": "max_experts",
            }.get(field)
            upper_limit = entry.get(upper_limit_field) if upper_limit_field else None
            if (
                isinstance(upper_limit, int)
                and not isinstance(upper_limit, bool)
                and upper_limit > 0
                and isinstance(value, int)
                and value > upper_limit
            ):
                issues.append(
                    SyncProposalItem(
                        model_key,
                        field,
                        entry.get(field),
                        value,
                        (source_path,),
                        conflict=True,
                        problem=f"value exceeds GGUF-owned {upper_limit_field}={upper_limit}",
                    )
                )
                continue
            observations.setdefault(model_key, {}).setdefault(field, []).append(
                (value, source_path)
            )

    proposals = issues.copy()
    conflicts = len(issues)
    for model_key, field_values in observations.items():
        entry = registry.get(model_key)
        if not isinstance(entry, dict):
            continue
        for field, values in field_values.items():
            unique_values = {json.dumps(value, sort_keys=True): value for value, _ in values}
            sources = tuple(sorted({path for _value, path in values}, key=lambda path: str(path).casefold()))
            if len(unique_values) > 1:
                conflicts += 1
                proposals.append(
                    SyncProposalItem(
                        model_key,
                        field,
                        entry.get(field),
                        tuple(unique_values.values()),
                        sources,
                        conflict=True,
                    )
                )
                continue
            proposed = next(iter(unique_values.values()))
            current = entry.get(field)
            if current != proposed:
                proposals.append(SyncProposalItem(model_key, field, current, proposed, sources))
    return proposals, unmatched_count + stale_count, conflicts


def _read_lms_loaded_models() -> dict[str, Any] | None:
    """Read LM Studio's native model list, including active load configs.

    Per-model JSON defaults do not always persist ``numExperts``. The native
    API reports the effective ``num_experts`` for loaded instances, so that
    value can be imported without substituting GGUF's architectural maximum.
    """
    api_base = os.environ.get("LMSTUDIO_API_BASE", "http://127.0.0.1:1234/v1").rstrip("/")
    if api_base.endswith("/api/v1"):
        url = f"{api_base}/models"
    elif api_base.endswith("/v1"):
        url = f"{api_base[:-3]}/api/v1/models"
    else:
        url = f"{api_base}/api/v1/models"
    headers = {"Accept": "application/json"}
    token = os.environ.get("LMS_OpenAI_AUTH_TOKEN") or os.environ.get("LMS_OPENAI_AUTH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=3) as response:
            payload = json.load(response)
    except (OSError, TimeoutError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _loaded_lms_expert_values(
    registry: dict[str, Any], payload: dict[str, Any]
) -> tuple[dict[str, int], dict[str, tuple[int, ...]]]:
    """Resolve effective expert counts only from unique loaded model identities."""
    registry_keys = [key for key, value in registry.items() if isinstance(value, dict)]
    observations: dict[str, set[int]] = {}
    rows = payload.get("models")
    if not isinstance(rows, list):
        return {}, {}
    for model in rows:
        if not isinstance(model, dict):
            continue
        instances = model.get("loaded_instances")
        if not isinstance(instances, list) or not instances:
            continue
        reference = str(model.get("selected_variant") or model.get("key") or "").strip()
        if not reference:
            continue
        quantization = model.get("quantization")
        quant = str(quantization.get("name") or "") if isinstance(quantization, dict) else ""
        canonical = canonicalize_source_identity(
            reference,
            publisher=str(model.get("publisher") or ""),
            quant=quant,
        )
        match = resolve_registry_match(canonical, registry_keys)
        if not isinstance(match, UniqueMatch):
            continue
        for instance in instances:
            if not isinstance(instance, dict):
                continue
            config = instance.get("config")
            value = config.get("num_experts") if isinstance(config, dict) else None
            if isinstance(value, bool) or value is None:
                continue
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                observations.setdefault(match.key, set()).add(parsed)
    values = {key: next(iter(items)) for key, items in observations.items() if len(items) == 1}
    conflicts = {key: tuple(sorted(items)) for key, items in observations.items() if len(items) > 1}
    return values, conflicts


def _registry_keys_with_configured_experts(
    registry: dict[str, Any],
    configs: list[dict[str, Any]],
    identity_links: dict[str, IdentityLink] | None,
) -> set[str]:
    """Find exact config joins that already contain an expert setting."""
    registry_keys = sorted(
        [(normalize_model_name(key), key) for key, value in registry.items() if isinstance(value, dict)],
        key=lambda item: -len(item[0]),
    )
    configured: set[str] = set()
    for config in configs:
        value = config.get("num_experts")
        if value is None:
            continue
        source_path = Path(config["json_path"])
        if identity_links is not None:
            matches = [
                model_key
                for model_key, link in identity_links.items()
                if source_path in link.config_paths
            ]
        else:
            matches = find_registry_matches_for_config(
                normalize_model_name(config["dir_name"]), registry_keys, config=config
            )
        if len(matches) == 1:
            configured.add(matches[0])
    return configured


def cmd_sync_from_configs(
    write: bool = False,
    write_context: bool = False,
    write_experts: bool = False,
    installed_models: list[dict[str, Any]] | None = None,
    inventory: RegistryInventory | None = None,
) -> list[SyncProposalItem]:
    """Compare GUI load settings and optionally persist them in the registry.

    ``write=False`` is the safe report mode. With ``write=True``, values from
    LM Studio configs are copied; effective expert counts are also read from
    loaded instances through the native API when the per-model JSON omits them.
    ``write_context=True`` is the narrow variant
    that persists only ``context_length`` and leaves offload/UKV/KV settings
    untouched. Conflicting values across configs for one registry entry are
    reported and skipped. When ``installed_models`` is provided by ``sync``,
    configs with no matching current LMS inventory entry are ignored as stale
    runtime artifacts. ``write_experts=True`` is the narrow variant for the
    selected LM Studio runtime expert count. The GGUF architectural maximum
    is kept separately as ``max_experts``.
    """
    if write_context or write_experts:
        write = True
    if not REGISTRY_PATH.exists():
        print(f"[ERROR] Registry not found: {REGISTRY_PATH}")
        sys.exit(1)

    print("[1] Registry laden ...")
    reg = inventory.registry if inventory is not None else load_registry()
    if not reg:
        print("[ERROR] Leere Registry")
        sys.exit(1)

    print("[2] JSON-Configs scannen ...")
    configs = inventory.configs if inventory is not None else read_lms_configs(CONFIG_ROOT)
    print(f"  -> {len(configs)} Config-Dateien gefunden")
    print(f"[3] Registry-Einträge mit Configs abgleichen ({'Schreibmodus' if write else 'Melde-Modus'}) ...")
    fields_to_sync = config_sync_fields(context_only=write_context, experts_only=write_experts)
    identity_links = None
    if inventory is not None:
        use_identity_links = bool(inventory.identity_links)
        _ensure_gguf_inventory(inventory)
        # A populated link table is authoritative.  Hand-built test or
        # compatibility inventories without links retain the old direct
        # matcher until they are migrated to the shared snapshot contract.
        if use_identity_links:
            identity_links = inventory.identity_links
    proposals, skipped, conflicts = _build_config_sync_proposal(
        reg, configs, installed_models, fields_to_sync, identity_links
    )
    has_moe_registry_models = any(
        isinstance(entry, dict) and str(entry.get("arch", "")).casefold() == "moe"
        for entry in reg.values()
    )
    if (
        not write_context
        and has_moe_registry_models
        and any(field == "experts" for field, _ in fields_to_sync)
    ):
        live_payload = _read_lms_loaded_models()
        if live_payload is None:
            if write:
                print(
                    "[INFO] LM Studio native API unavailable; no loaded runtime expert values imported"
                )
        else:
            live_values, live_conflicts = _loaded_lms_expert_values(reg, live_payload)
            configured_experts = _registry_keys_with_configured_experts(
                reg, configs, identity_links
            )
            live_source = Path("LM Studio native API loaded instance")
            for model_key, values in live_conflicts.items():
                if model_key in configured_experts:
                    continue
                proposals.append(
                    SyncProposalItem(
                        model_key,
                        "experts",
                        reg.get(model_key, {}).get("experts"),
                        values,
                        (live_source,),
                        conflict=True,
                        problem="loaded LM Studio instances report different num_experts values",
                    )
                )
                conflicts += 1
            for model_key, value in live_values.items():
                if model_key in configured_experts:
                    continue
                entry = reg.get(model_key)
                if not isinstance(entry, dict) or entry.get("experts") == value:
                    continue
                max_experts = entry.get("max_experts")
                if (
                    isinstance(max_experts, int)
                    and not isinstance(max_experts, bool)
                    and max_experts > 0
                    and value > max_experts
                ):
                    proposals.append(
                        SyncProposalItem(
                            model_key,
                            "experts",
                            entry.get("experts"),
                            value,
                            (live_source,),
                            conflict=True,
                            problem=f"value exceeds GGUF-owned max_experts={max_experts}",
                        )
                    )
                    conflicts += 1
                    continue
                proposals.append(
                    SyncProposalItem(
                        model_key,
                        "experts",
                        entry.get("experts"),
                        value,
                        (live_source,),
                    )
                )
    for proposal in proposals:
        source_names = ", ".join(str(path) for path in proposal.sources)
        if proposal.conflict:
            print(
                f"[KONFLIKT] {proposal.model_key}: {proposal.field} "
                f"{proposal.proposed!r} ({proposal.problem or 'different config values'}; "
                f"Quelle: {source_names}); nicht geschrieben"
            )
        else:
            print(
                f"[VORSCHLAG] {proposal.model_key}: {proposal.field} "
                f"{proposal.current!r} -> {proposal.proposed!r}; Quelle: {source_names}"
            )

    writes = 0
    if write:
        for proposal in proposals:
            if proposal.conflict:
                continue
            entry = reg.get(proposal.model_key)
            if isinstance(entry, dict):
                entry[proposal.field] = proposal.proposed
                writes += 1

    if write and writes:
        save_registry(reg)
    print(
        f"[OK] sync-from-configs: {len(proposals)} Drifts/Änderungsvorschläge, "
        f"{writes} geschrieben, {conflicts} Konflikte, {skipped} ohne eindeutige Zuordnung/alte Configs"
    )
    return proposals


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


def _default_ctx_from_size(
    size_bytes: int,
    np: int = 1,
    k_cache: str | None = None,
    v_cache: str | None = None,
) -> int:
    normalized_k, normalized_v = runtime_kv_pair(k_cache, v_cache)
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
    kv_actual = _KV_BYTES.get(normalized_k or "q8_0", 1.0) + _KV_BYTES.get(normalized_v or "q8_0", 1.0)
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


def _looks_like_lms_artifact_name(value: str) -> bool:
    """Return whether one LMS reference component is a concrete GGUF file."""
    lowered = value.strip().lower()
    return (
        lowered.endswith(".gguf")
        or lowered.endswith("-gguf")
        or ".bpw" in lowered
    )


def _clean_lms_model_reference(reference: str, publisher: str = "") -> str:
    """Remove a concrete GGUF filename from an LMS model reference.

    LM Studio can expose either a logical key (for example
    ``qwen/qwen3.5-9b``) or a display/path-shaped reference that includes the
    filename (for example
    ``byteshape/qwen3.5-9b/Qwen3.5-9B-Q5_K_S-5.10bpw.gguf``).  The filename is
    artifact evidence, not part of the semantic model identity.  When a full
    local path is supplied, the explicit LMS publisher anchors the useful
    suffix while preserving nested model namespaces such as ``qwen/...``.
    """
    raw = str(reference or "").strip().replace("\\", "/")
    if not raw:
        return ""
    base, separator, embedded_quant = raw.partition("@")
    parts = [part for part in base.split("/") if part and part != "."]
    explicit_publisher = str(publisher or "").strip().casefold()
    if explicit_publisher:
        for index, part in enumerate(parts):
            if part.casefold() == explicit_publisher:
                parts = parts[index:]
                break
    if parts:
        # A terminal ``.gguf``/BPW component is a concrete filename and is
        # removed.  ``-GGUF`` itself is normally a directory format marker
        # (for example ``publisher/model-GGUF``) and must be stripped from
        # the component instead of dropping the whole model component.
        lowered_last = parts[-1].casefold()
        if lowered_last.endswith(".gguf") or ".bpw" in lowered_last:
            parts.pop()
    if parts:
        parts[-1] = re.sub(r"-(gguf|mxpr4)$", "", parts[-1], flags=re.IGNORECASE)
    cleaned = "/".join(parts)
    if separator and embedded_quant:
        cleaned = f"{cleaned}@{embedded_quant}"
    return cleaned


def _canonical_key(mk: str, pub: str) -> str:
    """Build canonical registry key: publisher/model-name (cleaned)."""
    s = _clean_lms_model_reference(mk, pub).lower()
    s = re.sub(r"\.gguf$", "", s)
    s = re.sub(r"-(gguf|mxpr4)$", "", s)
    return str(canonicalize_source_identity(s, publisher=pub))


def _benchmark_lms_models(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only installed records eligible for this benchmark registry."""
    eligible: list[dict[str, Any]] = []
    for model in models:
        if is_support_model_record(model):
            continue
        if not is_registry_candidate(model):
            continue
        path = str(model.get("path") or model.get("indexedModelIdentifier") or "")
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
    normalized_quant = normalize_model_name(quant) if quant and quant != "?" else ""
    # Some LMS model keys omit the quant, while the Registry model component
    # repeats it (for example ``...-nvfp4@nvfp4``). Compare this repeated
    # suffix as one quant field, not as part of the model name.
    if normalized_quant and normalized_model.endswith(f"-{normalized_quant}"):
        normalized_model = normalized_model[: -(len(normalized_quant) + 1)]
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
    base_publisher, base_model, base_quant = decompose_model_identity(base)
    identities = {build_model_identity(base_publisher, base_model)}
    if base_quant and base_quant != "?":
        identities.add(base)

    variant_values: list[str] = []
    selected = str(model.get("selectedVariant") or "").strip()
    if selected:
        variant_values.append(selected)
    raw_variants = model.get("variants") or []
    if isinstance(raw_variants, list):
        variant_values.extend(str(value).strip() for value in raw_variants if value)
    quant = _quant_from_lms_record(model) or ""
    # LMS can expose an unknown-quant key (``@?``) while the actual GGUF path
    # or metadata identifies the loaded/downloaded quant. Keep the unqualified
    # base identity above, and add the concrete identity when available.
    if quant:
        variant_values.append(build_model_identity(base_publisher, base_model, quant))

    for variant in variant_values:
        canonical_variant = _canonical_key(variant, publisher)
        variant_publisher, variant_model, variant_quant = decompose_model_identity(canonical_variant)
        identities.add(build_model_identity(variant_publisher, variant_model))
        if variant_quant and variant_quant != "?":
            identities.add(canonical_variant)
        elif quant:
            identities.add(build_model_identity(variant_publisher, variant_model, quant))
    return identities


def _lms_record_for_registry_key(
    registry_key: str,
    models: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Find one eligible LMS record; return ``None`` for ambiguity."""
    registry_aliases = _identity_aliases(registry_key)
    # ``@?`` is the explicit unknown-quant placeholder and therefore matches
    # an LMS base record whose quantization metadata is absent.
    has_quant = _registry_quant(registry_key) is not None
    matches: list[dict[str, Any]] = []
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
                if model not in matches:
                    matches.append(model)
                break
    return matches[0] if len(matches) == 1 else None


def _lms_matches_registry_key(model: dict[str, Any], registry_key: str) -> bool:
    """Return whether one LMS row represents a registry base/quant identity."""
    registry_aliases = _identity_aliases(registry_key)
    # ``@?`` is a wildcard placeholder, not an identity-bearing quantization.
    has_quant = _registry_quant(registry_key) is not None
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
        selected_quant = selected.rsplit("@", 1)[1].lower()
        if selected_quant not in {"", "?", "unknown"}:
            return selected_quant
    quantization = model.get("quantization") or {}
    if isinstance(quantization, dict):
        quant = str(quantization.get("name", "")).strip()
        if quant:
            return quant.lower()
    searchable = " ".join(
        str(model.get(field, ""))
        for field in ("modelKey", "path", "indexedModelIdentifier")
    ).lower()
    if re.search(r"(?<![a-z0-9])i[-_]mini(?![a-z0-9])", searchable):
        return "mini"
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
        selected_key = _canonical_key(selected, publisher)
        selected_quant = _registry_quant(selected_key)
        if selected_quant not in {None, "?", "unknown"}:
            return selected_key
    quant = _quant_from_lms_record(model)
    if quant:
        publisher_name, model_name, _existing_quant = decompose_model_identity(base)
        return str(build_model_identity(publisher_name, model_name, quant))
    if "@" in selected:
        return _canonical_key(selected, publisher)
    return base


def _config_matches_lms_model(config: dict[str, Any], model: dict[str, Any]) -> bool:
    """Return whether a local config belongs to an installed LMS model.

    Config directory names are LMS namespaces, not necessarily Hub publishers.
    Compare the complete config reference with the LMS ``modelKey`` before
    falling back to the bare directory name.  The separate LMS publisher is
    still used to disambiguate equal model keys and the quant remains
    identity-bearing when either side exposes it.
    """
    model_key = str(model.get("modelKey") or model.get("key") or "").strip()
    if not model_key:
        return False
    model_reference = normalize_model_reference(
        _clean_lms_model_reference(model_key, str(model.get("publisher") or ""))
    )
    config_dir = str(config.get("dir_name") or "").strip()
    config_publisher = str(config.get("publisher") or "").strip()
    references = {
        normalize_model_reference(config_dir),
        normalize_model_reference(f"{config_publisher}/{config_dir}"),
    }
    references.discard("")
    if model_reference not in references:
        # Legacy configs may append format/quant markers to the directory
        # name.  Permit the broad fallback only when the config namespace is
        # also the explicit LMS publisher; never erase a nested model
        # namespace such as ``qwen/qwen3.5-9b`` across publishers.
        model_publisher = str(model.get("publisher") or "").strip().casefold()
        if not config_publisher or config_publisher.casefold() != model_publisher:
            return False
        cleaned_model_key = _clean_lms_model_reference(
            model_key,
            str(model.get("publisher") or ""),
        )
        if not any(
            normalize_for_config(reference) == normalize_for_config(cleaned_model_key)
            for reference in references
        ):
            return False

    config_quant = config.get("quant")
    model_quant = _quant_from_lms_record(model)
    if config_quant and model_quant:
        if normalize_quant(str(config_quant)) != normalize_quant(str(model_quant)):
            return False
    return True


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
        if "@" not in new_key:
            old_publisher, old_model, old_quant = decompose_model_identity(old_key)
            new_key = build_model_identity(
                old_publisher,
                old_model,
                old_quant or "?",
            )
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


def _read_gguf_header_details(
    model_path: str,
) -> tuple[int | None, int | None, bool | None, int | None, int | None, str | None]:
    """Read required architecture/runtime metadata directly from the GGUF header.

    Returns (block_count, embedding_length, is_reasoning, context_length,
    expert_count, general.architecture)
    where is_reasoning is True/False if the chat_template was readable (else None),
    and expert_count is the MoE expert count or None if the key is absent.

    This intentionally reads only GGUF metadata. ``gguf.GGUFReader`` may map the
    entire tensor file and is therefore unsuitable for parallel inventory scans.
    """
    from gguf_evidence import read_gguf_evidence

    try:
        metadata = read_gguf_evidence(model_path).metadata
        architecture = metadata.get("general.architecture")
        architecture = architecture.strip().lower() if isinstance(architecture, str) else None

        def integer(suffix: str) -> int | None:
            values = [
                value for key, value in metadata.items()
                if key.endswith(suffix) and isinstance(value, int) and not isinstance(value, bool)
                and (not architecture or key == f"{architecture}{suffix}")
            ]
            return values[0] if len(values) == 1 else None

        template = metadata.get("tokenizer.chat_template")
        reasoning = (
            _detect_reasoning_from_template(template)
            if isinstance(template, str) and template.strip() else None
        )
        return (
            integer(".block_count"), integer(".embedding_length"), reasoning,
            integer(".context_length"), integer(".expert_count"), architecture,
        )
    except (OSError, ValueError, struct.error):
        return None, None, None, None, None, None


def _read_gguf_arch(
    model_path: str,
) -> tuple[int | None, int | None, bool | None, int | None, int | None]:
    """Read n_layers, hidden_dim, reasoning, context_length and expert_count."""
    return _read_gguf_header_details(model_path)[:5]


def _read_gguf_base_arch(model_path: str) -> str | None:
    """Read the provider-neutral ``general.architecture`` without mapping tensors."""
    return _read_gguf_header_details(model_path)[5]


def _read_gguf_header_snapshot(
    model_path: str,
    inventory: RegistryInventory | None = None,
) -> tuple[tuple[int | None, int | None, bool | None, int | None, int | None], str | None]:
    """Read and, for a sync run, reuse all GGUF metadata needed by its stages."""
    if inventory is None:
        details = _read_gguf_header_details(model_path)
        return details[:5], details[5]
    try:
        resolved_path = Path(model_path).resolve(strict=True)
        stat = resolved_path.stat()
    except OSError:
        details = _read_gguf_header_details(model_path)
        return details[:5], details[5]
    cache_key = (os.path.normcase(str(resolved_path)).casefold(), stat.st_size, stat.st_mtime_ns)
    cached = inventory.gguf_header_cache.get(cache_key)
    if cached is None:
        details = _read_gguf_header_details(str(resolved_path))
        cached = (details[:5], details[5])
        inventory.gguf_header_cache[cache_key] = cached
    return cast("tuple[tuple[int | None, int | None, bool | None, int | None, int | None], str | None]", cached)


_REASONING_TOKEN_RE = re.compile(
    r"<\s*/?\s*(?:think|thinking|thought)\s*>|"
    r"<\|channel>\s*(?:thought|think)|"
    r"<\|channel\|>\s*analysis",
    re.IGNORECASE,
)


_KNOWN_QUANTS = KNOWN_QUANTS


def _gguf_quant_from_header(gguf_path: str) -> str | None:
    """Extract quantization type from GGUF filename.

    The GGUF header does not store the quant type directly, but the filename
    follows conventions like ``model-name-Q3_K_S.gguf``. This function parses
    the filename to extract the quant suffix.

    Returns the quant string (e.g. "Q3_K_S") or None if not determinable.
    """
    fname = os.path.basename(gguf_path).lower()
    fname = fname.removesuffix(".gguf")

    quant = extract_quant_from_text(fname)
    if quant:
        return str(quant.upper())

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
    from gguf_evidence import read_gguf_evidence

    try:
        value = read_gguf_evidence(model_path).metadata.get("tokenizer.chat_template")
        return value if isinstance(value, str) and value.strip() else None
    except (OSError, ValueError):
        return None


_DEFAULT_GGUF_ROOTS = configured_gguf_roots()
MODELS_CACHE = _DEFAULT_GGUF_ROOTS[0]
_DEFAULT_MODELS_CACHE = MODELS_CACHE


def _gguf_roots() -> tuple[Path, ...]:
    """Return the configured roots, honoring the legacy test seam."""
    if MODELS_CACHE != _DEFAULT_MODELS_CACHE:
        # Existing callers and tests patch MODELS_CACHE to isolate a scan.
        return (MODELS_CACHE,)
    return cast("tuple[Path, ...]", _DEFAULT_GGUF_ROOTS)


def _find_gguf_relative_path(relative_path: str | Path) -> Path | None:
    """Find one unique explicit GGUF path through the shared resolver."""
    resolver = ArtifactResolver()
    resolver.model_roots = _gguf_roots()
    result = resolver.resolve(str(relative_path))
    return result.path if result.is_unique else None

# ── GGUF expert_count check (for MoE detection) ───────────────────
def _gguf_has_experts(model_path: str) -> bool:
    """Read GGUF header and return True if expert_count > 0 (MoE).

    Uses the shared bounded header reader. The GGUF stores expert_count in an
    architecture-specific key like ``{arch}.expert_count`` (e.g.
    ``ernie4_5-moe.expert_count``). Dense models have no such key.
    Header evidence is cached by file size and modification time; weights
    are never mapped and replacement files cannot reuse stale counts.
    """
    count = _read_gguf_header_details(model_path)[4]
    return count is not None and count > 0


def cmd_fill_arch(
    lms_models: list[dict[str, Any]] | None = None,
    inventory: RegistryInventory | None = None,
) -> None:
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

    headers = _identity_gguf_headers(reg, lms_models, inventory)
    gguf_arch = {
        key: (facts[0], facts[1], facts[2], facts[3])
        for key, (facts, _family) in headers.items() if facts[0] and facts[1]
    }

    total = len([k for k, v in reg.items() if isinstance(v, dict)])
    updated = skipped_has = skipped_no = 0
    reasoning_updated = 0
    print(f"[4] {total} Registry-Einträge durchgehen ...")

    for key, entry in reg.items():
        if not isinstance(entry, dict):
            continue

        # Always try to fill max_context_length (even if n_layers/hidden_dim already set)
        if entry.get("max_context_length") is None:
            found = _find_gguf_arch_for_key(key, gguf_arch)
            if found and found[3] is not None:
                entry["max_context_length"] = int(found[3])
                reasoning_updated += 1  # reuse counter

        if entry.get("n_layers") and entry.get("hidden_dim"):
            skipped_has += 1
            continue

        found = _find_gguf_arch_for_key(key, gguf_arch)
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
            found = _find_gguf_arch_for_key(key, gguf_arch)
            if found and found[2] is not None:
                entry["reasoning"] = "thinking" if found[2] else "instruct"
                reasoning_updated += 1

    print(
        f"[OK] fill-arch: {updated} n_layers/hidden_dim gesetzt, {reasoning_updated} reasoning gesetzt, {skipped_has} bereits vorhanden, {skipped_no} kein GGUF-Match ({len(gguf_arch)} GGUF-Dateien ausgewertet)"
    )

    if updated or reasoning_updated:
        save_registry(reg)


def cmd_fill_quant(
    lms_models: list[dict[str, Any]] | None = None,
    inventory: RegistryInventory | None = None,
) -> None:
    """Fill missing or unknown @quant from a unique physical IdentityLink.

    For registry entries without a known quantization (including ``@?``),
    reads the installed GGUF evidence to determine the actual quantization.
    Renames the key to publisher/model@quant and sets the quants field.

    Source of Truth: GGUF header (via lms ls path -> file -> header parse).
    Entries without a known @quant are ambiguous — the triple
    (publisher, model, quant) is the unique identity.
    """
    reg = load_registry()
    if not reg:
        print("[ERROR] Leere Registry")
        sys.exit(1)

    if lms_models is None:
        lms_models = _benchmark_lms_models(_run_lms_ls())
    from local_model_resolver import LocalModelResolver
    from quantization import is_known_quant

    inventory = inventory or RegistryInventory(reg, lms_models, lms_models, [], [])
    candidates = _ensure_gguf_inventory(inventory)
    proposed: dict[str, set[str]] = {}
    for key, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        publisher, model_name, quant = decompose_model_identity(key)
        if not publisher or not model_name or is_known_quant(quant):
            continue
        for candidate in candidates:
            evidence = candidate.identity_evidence
            if not evidence.is_complete or evidence.publisher != publisher or not is_known_quant(evidence.quant):
                continue
            full_key = str(build_model_identity(publisher, model_name, evidence.quant))
            if LocalModelResolver._match_registry(evidence.source_reference, evidence.quant, {full_key: entry}) == full_key:
                proposed.setdefault(key, set()).add(full_key)

    joined_registry = dict(reg)
    for key, keys in proposed.items():
        for full_key in keys:
            joined_registry.setdefault(full_key, reg[key])
    full_inventory = RegistryInventory(joined_registry, lms_models, lms_models, [], candidates, True)
    _refresh_identity_links(full_inventory)

    updated = 0
    for key in list(reg.keys()):
        if not isinstance(reg[key], dict):
            continue
        if is_known_quant(decompose_model_identity(key)[2]):
            continue

        identities = proposed.get(key, set())
        if len(identities) != 1:
            print(f"  [SKIP] {key}: keine eindeutige vollständige GGUF-Identität")
            continue
        new_key = next(iter(identities))
        link = full_inventory.identity_links.get(new_key)
        if link is None or len(link.artifact_evidence) != 1:
            print(f"  [SKIP] {key}: GGUF-Artefaktbindung fehlt oder ist mehrdeutig")
            continue
        quant = decompose_model_identity(new_key)[2]

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


def _identity_gguf_headers(
    reg: dict[str, Any],
    lms_models: list[dict[str, Any]] | None = None,
    inventory: RegistryInventory | None = None,
) -> dict[str, tuple[tuple[int | None, int | None, bool | None, int | None, int | None], str | None]]:
    """Read headers only through an unambiguous, complete IdentityLink."""
    if inventory is None:
        models = lms_models if lms_models is not None else _benchmark_lms_models(_run_lms_ls())
        inventory = RegistryInventory(reg, models, models, [], [])
    else:
        inventory.registry = reg
    _ensure_gguf_inventory(inventory)
    paths: dict[str, str] = {}
    for key, link in inventory.identity_links.items():
        evidence = link.artifact_evidence
        if len(evidence) != 1 or not evidence[0].is_complete:
            continue
        publisher, _, quant = decompose_model_identity(key)
        if publisher != evidence[0].publisher or normalize_quant(quant) != normalize_quant(evidence[0].quant):
            continue
        paths[key] = str(evidence[0].path)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {key: pool.submit(_read_gguf_header_snapshot, path, inventory) for key, path in paths.items()}
        return {key: future.result() for key, future in futures.items()}


def _find_gguf_arch_for_key(
    reg_key: str, gguf_arch: dict[str, tuple[int, int, bool | None, int | None]]
) -> tuple[int, int, bool | None, int | None] | None:
    """Compatibility lookup; facts must be indexed by the complete Registry key."""
    return gguf_arch.get(reg_key)


def cmd_sync_from_gguf(
    lms_models: list[dict[str, Any]] | None = None,
    inventory: RegistryInventory | None = None,
) -> None:
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

    headers = _identity_gguf_headers(reg, lms_models, inventory)
    gguf_arch = {
        key: (facts[0], facts[1], facts[2], facts[3])
        for key, (facts, _family) in headers.items() if facts[0] and facts[1]
    }
    gguf_family = {key: family for key, (_facts, family) in headers.items() if family}
    gguf_moe = {key: bool(facts[4]) for key, (facts, _family) in headers.items() if facts[4] is not None}
    gguf_max_experts = {key: int(facts[4]) for key, (facts, _family) in headers.items() if facts[4]}
    print(f"  -> {len(headers)} eindeutig gebundene GGUF-Header")

    print("[4] Registry-Einträge mit GGUF-Quelle abgleichen (Auto-Fix) ...")
    fixes: list[str] = []
    for key, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        found = _find_gguf_arch_for_key(key, gguf_arch)
        if not found:
            continue

        nl, hd, _is_reasoning, ctx = found
        # arch: moe/mtp/dense aus GGUF expert_count
        architecture_family = gguf_family.get(key)
        if architecture_family and entry.get("architecture_family") != architecture_family:
            old = entry.get("architecture_family")
            entry["architecture_family"] = architecture_family
            fixes.append(
                f"{key}: architecture_family {old!r} -> {architecture_family!r} (GGUF general.architecture)"
            )
        exp = gguf_moe.get(key)
        expected_arch = "moe" if exp else None
        if expected_arch is not None and entry.get("arch") != expected_arch:
            old = entry.get("arch")
            entry["arch"] = expected_arch
            fixes.append(f"{key}: arch {old!r} -> {expected_arch!r} (GGUF expert_count={exp})")

        max_experts = gguf_max_experts.get(key)
        if max_experts is not None and entry.get("max_experts") != max_experts:
            old = entry.get("max_experts")
            entry["max_experts"] = max_experts
            fixes.append(f"{key}: max_experts {old!r} -> {max_experts} (GGUF expert_count)")

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


def cmd_fill_reasoning(
    lms_models: list[dict[str, Any]] | None = None,
    inventory: RegistryInventory | None = None,
) -> None:
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

    headers = _identity_gguf_headers(reg, lms_models, inventory)
    gguf_reasoning = {key: facts[2] for key, (facts, _family) in headers.items() if facts[2] is not None}

    total = len([k for k, v in reg.items() if isinstance(v, dict)])
    updated = skipped_has = skipped_no_match = 0
    print(f"[4] {total} Registry-Einträge durchgehen ...")

    for key, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("reasoning") is not None:
            skipped_has += 1
            continue
        if key in gguf_reasoning:
            entry["reasoning"] = "thinking" if gguf_reasoning[key] else "instruct"
            updated += 1
        else:
            skipped_no_match += 1

    print(
        f"[OK] fill-reasoning: {updated} reasoning gesetzt, {skipped_has} bereits vorhanden, {skipped_no_match} kein GGUF-Match ({len(gguf_reasoning)} GGUF-Dateien ausgewertet)"
    )

    if updated:
        save_registry(reg)


# ── sync-templates command ─────────────────────────────────────────

TEMPLATE_DIR = PROJECT_ROOT / "docs" / "Jinja-Chat-Templates"

_BLUEPRINT_CACHE: dict[str, Any] | None = None


def _load_blueprints() -> dict[str, Any]:
    """Load blueprint_definitions.yaml (SSOT fuer custom templates/stop-strings)."""
    global _BLUEPRINT_CACHE
    if _BLUEPRINT_CACHE is None:
        from ruamel.yaml import YAML
        y = YAML()
        bp_path = PROJECT_ROOT / "docs" / "blueprint_definitions.yaml"
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
    bp_name = entry.get("blueprint") or "default_chat"
    return cast("str | None", resolve_template(entry, _load_blueprints().get(bp_name), model_key))


def cmd_sync_templates(
    configs: list[dict[str, Any]] | None = None,
    installed_models: list[dict[str, Any]] | None = None,
    identity_links: dict[str, IdentityLink] | None = None,
) -> None:
    """Write promptTemplate from blueprint-defined templates into configs missing it.

    Blueprint-driven (SSOT): jedes Registry-Entry, dessen Blueprint eine
    ``template``/``template_map``-Definition besitzt, wird gegen seine Config
    geprueft; fehlt/leer ist das Feld ``llm.prediction.promptTemplate``, wird
    der Inhalt der .jinja-Datei geschrieben. Behebt die validate-Kategorie
    ``template_missing_config``. Das Registry-``template:``-Feld gilt als
    veraltet (Fallback). ``pipeline full`` ruft diesen idempotenten Schritt
    ebenfalls auf; befuellte Templates werden nicht ueberschrieben.
    """
    reg = load_registry()
    cfgs = configs if configs is not None else read_lms_configs(CONFIG_ROOT)
    if installed_models is not None:
        linked_config_paths = {
            _path_identity(path)
            for link in (identity_links or {}).values()
            for path in link.config_paths
        }
        cfgs = [
            config
            for config in cfgs
            if _path_identity(config.get("json_path") or "") in linked_config_paths
            or any(_config_matches_lms_model(config, model) for model in installed_models)
        ]
    registry_keys = sorted(
        [(normalize_model_name(key), key) for key, value in reg.items() if isinstance(value, dict)],
        key=lambda item: -len(item[0]),
    )
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
        if identity_links is not None and model_key in identity_links:
            matches = configs_for_registry_key(model_key, cfgs, identity_links)
        else:
            matches = [
                config
                for config in cfgs
                if find_registry_matches_for_config(
                    normalize_model_name(config["dir_name"]), registry_keys, config=config
                ) == [model_key]
            ]
        if not matches:
            print(f"  [SKIP] {model_key}: keine eindeutig passende Config-JSON gefunden")
            skipped += 1
            continue
        if len(matches) > 1:
            paths = ", ".join(str(config["json_path"]) for config in matches)
            print(f"  [KONFLIKT] {model_key}: mehrere aktive Configs ({paths}); nicht geschrieben")
            skipped += 1
            continue
        json_path = Path(matches[0]["json_path"])
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
                        _atomic_write_text(
                            json_path, json.dumps(data, indent=2, ensure_ascii=False) + "\n"
                        )
                        print(f"  [FIX] {model_key}: promptTemplate ergänzt")
                        added += 1
                    else:
                        skipped += 1
                    break
            if not found:
                fields.append({"key": "llm.prediction.promptTemplate", "value": template_content})
                _atomic_write_text(
                    json_path, json.dumps(data, indent=2, ensure_ascii=False) + "\n"
                )
                print(f"  [FIX] {model_key}: promptTemplate ergänzt")
                added += 1
        except Exception as e:
            print(f"  [ERROR] {model_key}: {e}")
            errors += 1
    clear_lms_config_cache(CONFIG_ROOT)
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
        _atomic_write_text(json_path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
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
    base_key = model_key.split("@", 1)[0]
    name = base_key.split("/", 1)[-1] if "/" in base_key else base_key
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
    """Write docs/Review-Artifacts/repro_issues.md: validate errors + hub diffs.

    Repro artifact for the review: every registry decision (context_length,
    max_context_length, arch, reasoning, capabilities) is checked against the
    LM Studio Hub model.yaml (metadataOverrides); deviations are documented as
    'REPRO-Check'. An existing file is overwritten.
    """
    artifacts_dir = PROJECT_ROOT / "docs" / "Review-Artifacts"
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


def _gguf_drift_errors(reg: dict[str, Any], inventory: RegistryInventory | None = None) -> list[str]:
    """GGUF-Header vs. Registry: auto_fix-Felder (Feld-Ownership) abgleichen.

    Liest die GGUF-Header (via lms ls, parallel) und meldet Abweichungen bei
    n_layers/hidden_dim/max_context_length/arch. Fixbar durch
    'sync-from-gguf' (kein Schreiben hier - validate bleibt read-only).
    reasoning wird bewusst nicht geprueft (Interpretationsspielraum).
    """
    headers = _identity_gguf_headers(reg, inventory=inventory)
    gguf_arch = {
        key: (facts[0], facts[1], facts[2], facts[3])
        for key, (facts, _family) in headers.items() if facts[0] and facts[1]
    }
    gguf_moe = {key: bool(facts[4]) for key, (facts, _family) in headers.items() if facts[4] is not None}
    gguf_max_experts = {key: int(facts[4]) for key, (facts, _family) in headers.items() if facts[4]}

    out: list[str] = []
    for key, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        found = _find_gguf_arch_for_key(key, gguf_arch)
        if not found:
            continue
        nl, hd, _is_reasoning, ctx = found
        exp = gguf_moe.get(key)
        max_experts = gguf_max_experts.get(key)

        if exp is True and entry.get("arch") != "moe":
            out.append(
                f"{key}: arch={entry['arch']} vs GGUF expert_count=True (Quelle: gguf, Auto-Fix via sync-from-gguf)"
            )
        if max_experts is not None and entry.get("max_experts") != max_experts:
            out.append(
                f"{key}: max_experts={entry.get('max_experts')} vs GGUF={max_experts} "
                "(Quelle: gguf, Auto-Fix via sync-from-gguf)"
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


def cmd_validate(
    verbose: bool = False,
    repro: bool = False,
    ci: bool = False,
    inventory: RegistryInventory | None = None,
) -> dict[str, Any]:
    """Validate model_registry.yaml consistency: templates, configs, overrides.

    verbose: zeigt alle Einzelprobleme (statt nur die ersten 10 je Kategorie).
    repro:   schreibt zusätzlich docs/Review-Artifacts/repro_issues.md mit
             GGUF-Hub-Abweichungen (Registry vs. LM-Studio-Hub model.yaml).
    ci:      headless static checks only; skips LM-Studio configs and local GGUFs.

    Returns dict with error counts per check category.
    """
    reg = load_registry()
    cfgs = [] if ci else (inventory.configs if inventory is not None else read_lms_configs(CONFIG_ROOT))
    identity_links = inventory.identity_links if inventory is not None else None

    def configs_for_key(model_key: str) -> list[dict[str, Any]]:
        if identity_links is not None:
            return cast("list[dict[str, Any]]", configs_for_registry_key(model_key, cfgs, identity_links))
        return cast("list[dict[str, Any]]", find_all_configs_for_registry_key(model_key, cfgs))

    linked_config_keys: dict[str, str] = {}
    if identity_links is not None:
        for model_key, link in identity_links.items():
            for config_path in link.config_paths:
                linked_config_keys[_path_identity(config_path)] = model_key
    errors: dict[str, list[str]] = {
        "template_missing_file": [],
        "template_missing_config": [],
        "missing_reasoning": [],
        "missing_capabilities": [],
        "missing_blueprint": [],
        "sampling_invalid": [],
        "sampling_research_status_invalid": [],
        "identity_collision": [],
        "publisherless_identity_ambiguity": [],
        "registry_no_config": [],
        "local_config_pair_invalid": [],
        "local_companion_invalid": [],
        "reasoning_arch_mismatch": [],
        "config_context_drift": [],
        "config_experts_drift": [],
        "runtime_experts_missing": [],
        "runtime_experts_exceed_max": [],
        "config_np_ukv_drift": [],
        "config_context_too_small": [],
        "gguf_header_drift": [],
    }

    if not ci:
        bundle_errors = _registry_local_bundle_errors(reg)
        errors["local_config_pair_invalid"].extend(bundle_errors["config"])
        errors["local_companion_invalid"].extend(bundle_errors["companion"])

    # Canonical publisher/model/quant identities must be unique.  The
    # publisher-stripped namespace is retained only as a diagnostic because
    # two explicitly published Registry entries may legitimately share a base
    # model name; all runtime consumers must fail closed for that ambiguity.
    canonical_groups: dict[str, list[str]] = {}
    for model_key in reg:
        canonical_groups.setdefault(normalize_registry_identity(model_key), []).append(model_key)
    for normalized, candidates in canonical_groups.items():
        if len(candidates) > 1:
            errors["identity_collision"].append(
                f"{normalized}: mehrere kanonische Registry-Keys {', '.join(candidates)}"
            )
    for normalized, candidates in find_match_collisions(list(reg)).items():
        errors["publisherless_identity_ambiguity"].append(
            f"{normalized}: publisherlose Eingabe ist mehrdeutig: {', '.join(candidates)}"
        )

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
        matching_configs = configs_for_key(model_key)
        if not matching_configs:
            errors["template_missing_config"].append(
                f"{model_key}: template='{tpl}' definiert, "
                f"aber Config-JSON nicht gefunden (auch nach fallback matching)"
            )
            continue
        json_path = Path(matching_configs[0]["json_path"])
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
        raw_sampling = entry.get("sampling")
        sampling_block = raw_sampling if isinstance(raw_sampling, dict) else {}
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

    # ── Check 5: installed LMS model has one concrete config binding ──
    active_registry_keys: set[str] = set()
    if inventory is not None and identity_links is not None:
        registry_keys = [key for key, value in reg.items() if isinstance(value, dict)]
        for model in inventory.lms_models:
            exact_matches = [
                key for key in registry_keys if _lms_matches_registry_key(model, key)
            ]
            candidates = exact_matches or [
                key for key in registry_keys if _lms_logical_model_matches_registry_key(model, key)
            ]
            if len(candidates) == 1:
                active_registry_keys.add(candidates[0])

    for model_key, entry in reg.items():
        if ci:
            continue
        if not isinstance(entry, dict):
            continue
        if identity_links is not None:
            local = entry.get("local")
            has_declared_config = (
                isinstance(local, dict)
                and isinstance(local.get("config_path"), (str, os.PathLike))
                and bool(str(local.get("config_path")).strip())
            )
            # file_size_bytes is a GGUF property, not proof that a model is
            # installed in LM Studio. Only active LMS identities or explicit
            # local config bindings require a config JSON.
            if model_key not in active_registry_keys and not has_declared_config:
                continue
        elif not entry.get("file_size_bytes"):
            continue
        if not configs_for_key(model_key):
            if identity_links is not None and has_declared_config and not any(
                message.startswith(f"{model_key}:") for message in errors["local_config_pair_invalid"]
            ):
                errors["local_config_pair_invalid"].append(
                    f"{model_key}: declared local GGUF/JSON binding does not prove the complete model identity"
                )
            rk = normalize_model_name(model_key)
            errors["registry_no_config"].append(f"{model_key}: keine passende Config-JSON gefunden (normalized: {rk})")

    # ── Check 7: reasoning stimmt mit Architektur-Map überein ──────
    for model_key, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        reasoning = entry.get("reasoning")
        from runtime_policy import resolve_reasoning

        # Explicit Registry policy is authoritative. Architecture defaults
        # cannot reject a fine-tune's declared reasoning behavior.
        if reasoning and resolve_reasoning(entry, model_key) != reasoning:
            errors["reasoning_arch_mismatch"].append(
                f"{model_key}: unsupported reasoning policy {reasoning!r}"
            )

    # ── Check 8: LM Studio runtime evidence vs. Registry ───────────
    # Registry.context_length is the benchmark SSOT. LM Studio context values
    # are local tuning artifacts and differences are reported as advisory.
    registry_key_sorted = sorted(
        [(normalize_model_name(k), k) for k, v in reg.items() if isinstance(v, dict)],
        key=lambda x: -len(x[0]),
    )

    for cfg in cfgs:
        if identity_links is not None:
            match = linked_config_keys.get(_path_identity(cfg["json_path"]))
        else:
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
        cfg_experts = load_fields.get("llm.load.numExperts")

        # Report local LM Studio context differences without changing the
        # benchmark context selected from the Registry.
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

        # experts is the selected LM Studio runtime value. It is distinct
        # from the immutable GGUF max_experts architecture limit.
        reg_experts = entry.get("experts")
        cfg_experts_valid = (
            isinstance(cfg_experts, int)
            and not isinstance(cfg_experts, bool)
            and cfg_experts > 0
        )
        reg_experts_valid = (
            isinstance(reg_experts, int)
            and not isinstance(reg_experts, bool)
            and reg_experts > 0
        )
        if cfg_experts is not None and not cfg_experts_valid:
            errors["config_experts_drift"].append(
                f"{match}: Config numExperts={cfg_experts!r} is not a positive integer "
                f"({cfg['json_path']})"
            )
        elif cfg_experts_valid and (not reg_experts_valid or cfg_experts != reg_experts):
            errors["config_experts_drift"].append(
                f"{match}: Config numExperts={cfg_experts} != Registry experts={reg_experts!r} "
                f"({cfg['json_path']})"
            )
        max_experts = entry.get("max_experts")
        if (
            cfg_experts_valid
            and isinstance(max_experts, int)
            and not isinstance(max_experts, bool)
            and max_experts > 0
            and isinstance(cfg_experts, int)
            and cfg_experts > max_experts
        ):
            errors["runtime_experts_exceed_max"].append(
                f"{match}: Config numExperts={cfg_experts} > Registry max_experts={max_experts} "
                f"({cfg['json_path']})"
            )

        # np/UKV/offload: Registry ist SSOT (Stand 11.08.2026).
        # JSON-Configs werden ignoriert — Benchmark überschreibt alle Parameter
        # explizit via API. Drift-Check entfernt, da Configs irrelevant.

    # Every MoE Registry entry must document the selected runtime value. Do
    # not silently use max_experts as a fallback: it may exceed available VRAM.
    for model_key, entry in reg.items():
        if not isinstance(entry, dict) or str(entry.get("arch", "")).casefold() != "moe":
            continue
        runtime_experts = entry.get("experts")
        if not (
            isinstance(runtime_experts, int)
            and not isinstance(runtime_experts, bool)
            and runtime_experts > 0
        ):
            errors["runtime_experts_missing"].append(
                f"{model_key}: MoE runtime experts missing; import the tested LM Studio "
                "value with sync --import-lms-settings while its model is loaded"
            )
        max_experts = entry.get("max_experts")
        if (
            isinstance(runtime_experts, int)
            and not isinstance(runtime_experts, bool)
            and runtime_experts > 0
            and isinstance(max_experts, int)
            and not isinstance(max_experts, bool)
            and max_experts > 0
            and runtime_experts > max_experts
        ):
            errors["runtime_experts_exceed_max"].append(
                f"{model_key}: Registry experts={runtime_experts} > max_experts={max_experts}"
            )

    # ── Check 9: GGUF-Header vs. Registry (Feld-Ownership) ──────────
    # auto_fix-Felder (n_layers/hidden_dim/max_context_length/arch) aus den
    # unveraenderlichen GGUF-Headern; Abweichungen werden gemeldet (fixbar
    # durch 'sync-from-gguf'). reasoning bleibt bewusst außen vor
    # (Interpretationsspielraum, wird nur als fill-if-missing behandelt).
    gguf_drift_errors = [] if ci else _gguf_drift_errors(reg, inventory)
    errors["gguf_header_drift"] = gguf_drift_errors

    # ── Report ─────────────────────────────────────────────────────
    advisory_checks = _VALIDATION_ADVISORY_CHECKS
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


def _registry_local_bundle_errors(registry: dict[str, Any]) -> dict[str, list[str]]:
    """Validate explicitly persisted machine-local GGUF/JSON/companion bindings."""
    errors: dict[str, list[str]] = {"config": [], "companion": []}
    scoped_config_owners: dict[str, list[str]] = {}
    for model_key, entry in registry.items():
        local = entry.get("local") if isinstance(entry, dict) else None
        config_path = local.get("config_path") if isinstance(local, dict) else None
        if (
            isinstance(local, dict)
            and local.get("config_scope") == "model"
            and isinstance(config_path, str)
            and config_path.strip()
        ):
            scoped_config_owners.setdefault(_path_identity(config_path), []).append(model_key)

    for model_key, entry in registry.items():
        if not isinstance(entry, dict):
            continue
        try:
            speculative_policy = registry_speculative_policy(entry)
        except ValueError as exc:
            errors["companion"].append(f"{model_key}: {exc}")
            continue
        local = entry.get("local")
        if not isinstance(local, dict):
            continue
        main_path = local.get("model_path")
        config_path = local.get("config_path")
        if isinstance(config_path, str) and config_path.strip():
            if local.get("config_scope") == "model":
                owners = scoped_config_owners.get(_path_identity(config_path), [])
                if len(owners) > 1:
                    errors["config"].append(
                        f"{model_key}: model-scoped config is assigned to multiple Registry entries: "
                        + ", ".join(sorted(owners))
                    )
            errors["config"].extend(
                f"{model_key}: {message}"
                for message in validate_config_gguf_pair(
                    main_path if isinstance(main_path, str) else "",
                    config_path,
                    scope=str(local.get("config_scope", "gguf")),
                )
            )

        local_llama = local.get("llama_cpp")
        speculative = local_llama.get("speculative") if isinstance(local_llama, dict) else None
        if speculative_policy == "disabled":
            continue
        if not isinstance(speculative, dict):
            continue
        normalized = normalize_speculative_profile(speculative)
        role = companion_role(normalized)
        if not speculative:
            continue
        companions = local.get("companions")
        companion_path = companions.get(role) if isinstance(companions, dict) else None
        if role == "draft" and not isinstance(companion_path, str) and isinstance(companions, dict):
            companion_path = companions.get("drafter")
        errors["companion"].extend(
            f"{model_key}: {message}"
            for message in validate_companion_binding(
                main_path if isinstance(main_path, str) else None,
                companion_path if isinstance(companion_path, str) else None,
                speculative,
            )
        )
    return errors


# These local LM Studio observations do not block Registry validation or the
# direct llama.cpp workflow. They remain visible so LMS-specific maintenance
# can be performed deliberately.
_VALIDATION_ADVISORY_CHECKS = frozenset(
    {
        "missing_capabilities",
        "template_missing_config",
        "registry_no_config",
        "config_context_drift",
        "config_context_too_small",
        "config_np_ukv_drift",
        "publisherless_identity_ambiguity",
    }
)


def _blocking_validation_errors(errors: dict[str, list[str]]) -> dict[str, list[str]]:
    """Return validation findings that invalidate Registry/backend readiness."""
    return {
        check: items
        for check, items in errors.items()
        if items and check not in _VALIDATION_ADVISORY_CHECKS
    }


# Registry/runtime ownership conflicts that make pipeline full fail.
# LM Studio context values are local runtime artifacts; Registry context is SSOT.
_DRIFT_CHECKS = (
    "config_experts_drift",
    "runtime_experts_missing",
    "runtime_experts_exceed_max",
    "gguf_header_drift",
)


def _local_candidates_as_model_records(candidates: list[Any]) -> list[dict[str, Any]]:
    """Project physical GGUF identities into the narrow ``cmd_add`` input shape."""
    records: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        evidence = getattr(candidate, "identity_evidence", None)
        path = getattr(candidate, "path", None)
        quant = str(getattr(candidate, "quant", "") or "").strip()
        if not isinstance(evidence, ArtifactIdentityEvidence) or not evidence.is_complete:
            continue
        if not isinstance(path, Path) or not quant:
            continue
        identity = evidence.identity
        records.setdefault(
            identity.casefold(),
            {
                "type": "llm",
                "modelKey": evidence.model_name,
                "publisher": evidence.publisher,
                "quantization": {"name": quant},
                "path": str(path),
            },
        )
    return list(records.values())


# ── sync command (full) ────────────────────────────────────────────


def cmd_sync(
    refresh_sampling: bool = False,
    inventory: RegistryInventory | None = None,
    show_inventory_report: bool = True,
    import_lms_settings: bool = False,
) -> None:
    """Synchronize local inventory and print proposed LM Studio imports.

    Nur Registry-Pflege aus unveränderlichen Quellen (GGUF-Header, JSON-Configs).
    Sampling-Werte werden nur aus plausiblen, eindeutigen Web-Quellen übernommen;
    bei fehlenden/konfligierenden Werten bleiben Kategorie-Defaults aktiv. Es
    wird NIE in JSON-Configs geschrieben (die GUI ist die Quelle) und die
    Blueprint-YAML wird nicht regeneriert (sie ist die Quelle für assemble).
    Sampling-Websuche läuft ausschließlich auf ausdrückliche Anforderung mit
    ``refresh_sampling=True``. Der übergebene Inventurstand verhindert, dass
    Modellliste und Config-Dateien für denselben Lauf mehrfach eingelesen werden.
    """
    inventory = inventory or _collect_registry_inventory()
    if not inventory.gguf_candidates_loaded:
        _ensure_gguf_inventory(inventory)
    lms = inventory.lms_models
    if not lms:
        lms = _local_candidates_as_model_records(inventory.gguf_candidates)
        if lms:
            print(
                f"[BOOTSTRAP] LM Studio liefert keine Modelle; "
                f"{len(lms)} benchmarkfähige GGUF-Identitäten aus dem lokalen Bestand werden verwendet"
            )
            inventory.lms_models = lms
    reg = inventory.registry
    if show_inventory_report:
        print("[INVENTUR UND ÄNDERUNGSVORSCHLÄGE]")
        cmd_compare(inventory=inventory)
    _rekey_registry_to_lms(reg, lms)
    reg = load_registry()
    registry_keys = [k for k, v in reg.items() if isinstance(v, dict)]

    # Find new models
    new_models = []
    for m in lms:
        if any(_lms_matches_registry_key(m, key) for key in registry_keys):
            continue
        physical_matches = _physical_registry_matches_lms_model(
            m,
            inventory.gguf_candidates,
            set(registry_keys),
        )
        if len(physical_matches) == 1:
            print(
                f"  [INFO] LMS-Identität {m.get('modelKey')}: physisch bereits gebunden an "
                f"{physical_matches[0]} - kein neuer Registry-Key"
            )
            continue
        if not physical_matches:
            new_models.append(m)

    if new_models:
        print(f"[add] {len(new_models)} neue Modelle zur Registry ...")
        cmd_add(new_models, research_web=False)
    else:
        print("[add] Keine neuen Modelle")

    if not REGISTRY_PATH.is_file():
        print(
            "[ERROR] Es konnte keine erste Registry erzeugt werden: "
            "keine benchmarkfähigen LM-Studio-Modelle oder eindeutig identifizierbaren lokalen GGUF-Dateien gefunden."
        )
        return

    if refresh_sampling:
        print("[sampling] Explizite Websuche für alle Registry-Kandidaten ...")
        _research_missing_sampling(load_registry(), force=True, inventory=inventory)
    else:
        print("[sampling] Websuche ausgelassen; nur lokale Bestandsdaten verwendet")

    print("[fill-quant] fehlende @quant-Suffixe aus GGUF-Headern ergänzen ...")
    cmd_fill_quant(lms_models=lms, inventory=inventory)

    print("[fill-arch] n_layers/hidden_dim + reasoning aus GGUF-Headern in Registry ...")
    cmd_fill_arch(lms_models=lms, inventory=inventory)

    print("[sync-from-gguf] Registry-Auto-Fix aus GGUF-Headern (Feld-Ownership) ...")
    cmd_sync_from_gguf(lms_models=lms, inventory=inventory)

    print("[fill-reasoning] Fehlende reasoning-Felder aus GGUF-Headern ergänzen ...")
    cmd_fill_reasoning(lms_models=lms, inventory=inventory)

    inventory.registry.clear()
    inventory.registry.update(load_registry())
    print("[fill-size] Haupt-GGUF-Dateigrößen aus dem gemeinsamen Inventar abgleichen ...")
    cmd_fill_size(inventory=inventory, refresh_existing=True)

    inventory.registry.clear()
    inventory.registry.update(load_registry())
    _refresh_identity_links(inventory)
    materialized = _materialize_local_bindings(inventory)
    print(f"[local-bindings] {materialized} lokale Bundle-/llama.cpp-Felder aktualisiert")

    print(
        "[sync-from-configs] LM Studio settings importieren ..."
        if import_lms_settings
        else "[sync-from-configs] LM Studio settings vergleichen (Melde-Modus; 0 geschrieben) ..."
    )
    inventory.registry.clear()
    inventory.registry.update(load_registry())
    cmd_sync_from_configs(
        write=import_lms_settings,
        installed_models=lms,
        inventory=inventory,
    )

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
    mode: str = "status",
    ignore_drift: bool = False,
    refresh_sampling: bool = False,
    import_lms_settings: bool = False,
    write_prompts: bool = False,
    model_list: Path | None = None,
    gguf_list: Path | None = None,
) -> None:
    """Ein-Aufruf-Wartungspipeline (ersetzt sync_model_configs.ps1).

    Modus:
      status  -> LMS-Modellzahl + compare-Report (Default, schreibt nichts)
      sync    -> status + registry_tool sync + Klassifikation
      full    -> sync + fehlende Template-Felder + Prompt-Preview + Validierung
                 (mit --write-prompts werden System-Prompts atomar geschrieben)

    ignore_drift: beendet full NICHT mit Exit-Code 1, auch wenn Melde-Konflikte
    (Feld-Ownership: Config-Felder, GGUF-Header-Drift) offen sind.
    """
    inventory = (_collect_registry_inventory(model_list, gguf_list)
                 if model_list is not None or gguf_list is not None else _collect_registry_inventory())
    _ensure_gguf_inventory(inventory)
    print(
        f"[INVENTUR] LM Studio: {len(inventory.lms_models)} passende Modelle "
        f"({len(inventory.raw_lms_models)} gesamt); Configs: {len(inventory.configs)}; "
        f"GGUF-Dateien: {len(inventory.gguf_candidates)}"
    )

    print("[2] Registry <> LMS <> Configs (compare) ...")
    cmd_compare(inventory=inventory)

    if mode == "status":
        return

    if mode == "full":
        print("[2b] Quarantäne nicht-installierter Modelle (missing, DRY-RUN) ...")
        cmd_quarantine_missing(dry_run=True, inventory=inventory)
        print("[HINWEIS] Nur ein Vorschlag; nach Prüfung explizit verschieben mit:")
        print("  py -3.12 .\\src\\registry_tool.py quarantine-missing --apply")

    print("[3] Full sync (add + fill-quant + fill-arch + sync-from-gguf + fill-reasoning + sync-from-configs + fmt) ...")
    cmd_sync(
        refresh_sampling=refresh_sampling,
        inventory=inventory,
        show_inventory_report=False,
        import_lms_settings=import_lms_settings,
    )
    if mode == "full" and not import_lms_settings:
        print("[HINWEIS] LM-Studio-Werte wurden nur berichtet. Geprüfte, eindeutige Werte")
        print("  explizit importieren mit: py -3.12 .\\src\\registry_tool.py sync --import-lms-settings")

    print("[4] Klassifikation (blueprint + reasoning) ...")
    classify_registry()

    if mode == "full":
        print("[4a] Fehlende LM-Studio-Prompt-Templates ergänzen ...")
        cmd_sync_templates(
            configs=inventory.configs,
            installed_models=inventory.lms_models,
            identity_links=inventory.identity_links,
        )
        if write_prompts:
            print("[5] Prompt-Assembly (WRITE; eindeutige IdentityLinks) ...")
        else:
            print("[5] Prompt-Assembly (PREVIEW; System-Prompts werden nicht geschrieben) ...")
        assemble_prompts(
            preview_only=not write_prompts,
            identity_links=inventory.identity_links,
        )
        if not write_prompts:
            print("[HINWEIS] System-Prompts nach Prüfung schreiben mit:")
            print("  py -3.12 .\\src\\registry_tool.py full --write-prompts")
        print("[5a] GLM-Config-Patch übersprungen (separater Schreibbefehl) ...")
        print("[6] Validierung ...")
        validate_prompts()
        print("[6a] Registry-Drift-Validierung (Feld-Ownership) ...")
        errors = cmd_validate(inventory=inventory)
        open_drift = _blocking_validation_errors(errors)
        if ignore_drift:
            open_drift = {key: items for key, items in open_drift.items() if key not in _DRIFT_CHECKS}
        if open_drift:
            total_open = sum(len(v) for v in open_drift.values())
            print(f"\n{'=' * 60}")
            print(f"[VALIDATION] {total_open} offene blockierende Vertragsverletzungen:")
            for check, items in open_drift.items():
                print(f"  - {check}: {len(items)}")
            print("  Identitäts-, Template-, Bundle- und Runtime-Verträge vor dem Start beheben.")
            print(f"{'=' * 60}")
            print("[ERROR] pipeline full mit Exit-Code 1 (offene Vertragsverletzungen)")
            sys.exit(1)
        else:
            print("[DRIFT] Keine offenen Melde-Konflikte - konvergiert.")

    print(f"[OK] {mode} abgeschlossen")


# ── patch-reasoning-effort command ─────────────────────────────────
# Port von tools/patch_reasoning_effort.py (Fix 2026-07-31): traegt gpt-oss-20b-
# GGUF-Varianten die Reasoning-Effort-Felder idempotent nach (mit Backup).

_PRE_LOCK_PATH = PROJECT_ROOT / "ergebnisse" / ".benchmark.lock"
_PRE_EFFORT_FIELD: dict[str, Any] = {
    "key": "ext.virtualModel.customField.openai.gptOss20b.reasoningEffort",
    "value": GPTOSS_REASONING_EFFORT,
}
_PRE_PARSING_FIELD = {
    "key": "llm.prediction.reasoning.parsing",
    "value": {"enabled": False, "startString": " thinking", "endString": " response"},
}
_PRE_BUDGET_FIELD: dict[str, Any] = {
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
    with open(path, encoding="utf-8") as input_file:
        data = json.load(input_file)
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
    with open(path, "w", encoding="utf-8") as output_file:
        json.dump(data, output_file, ensure_ascii=False, indent=2)
    return True, [m["key"] for m in missing], [f["key"] for f in to_overwrite], backup


# ── patch-glm-configs command ──────────────────────────────────────
# GLM runtime policy (2026-09-21): the benchmark API decides structured
# output per request. ``llm.prediction.structured`` is a GUI default and must
# not be deleted or enabled globally by this maintenance command. The patch
# only synchronizes the model-family parser and reasoning budget that belong
# in LM Studio's concrete model config.

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
        lowered = str(path).lower()
        if any(part in lowered for part in ("ocr", "mmproj", "vision-projector", "_quarantine_")):
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
    """Patch only GLM reasoning fields; preserve Structured Output ownership.

    The maintenance command may repair parsing, reasoning budget, stop
    strings, and stale JSON prompt instructions. It deliberately neither
    creates nor removes ``llm.prediction.structured``: the LM Studio GUI
    default remains user-owned, while benchmark Structured Output is an
    explicit request-level policy.

    Returns ``(changed, actions, backup_path)``.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    fields = data.get("operation", {}).get("fields", [])
    actions: list[str] = []

    # Resolve the same model-family policy used by benchmark_config.py. GLM
    # 4.7 Flash/REAP (DeepSeek2) and GLM-4.6V (glm4) remain separate.
    lowered = str(path).lower()
    blueprint_name = "glm4v_reasoning" if "glm-4.6v" in lowered else "glm_reasoning_coding"
    profile = blueprint_features(blueprint_name, str(path))
    parsing_cfg = profile.get("reasoning_parsing") or {
        "enabled": True, "startString": " thinking", "endString": " response"
    }

    # Do not infer or normalize the GUI Structured Output setting here. A
    # missing field stays missing and an existing field stays unchanged.

    # reasoning.parsing must be active so the model's thought channel does
    # not leak into final content. The exact markers come from the blueprint.
    for f in fields:
        if f.get("key") == "llm.prediction.reasoning.parsing":
            if f.get("value") != parsing_cfg:
                f["value"] = dict(parsing_cfg)
                actions.append("reasoning.parsing synchronized")
            break
    else:
        fields.append({"key": "llm.prediction.reasoning.parsing", "value": dict(parsing_cfg)})
        actions.append("reasoning.parsing added")

    # Keep a bounded but generous reasoning budget. This is distinct from the
    # request's total max_tokens and from the GUI structured-output toggle.
    runtime = profile.get("benchmark_runtime")
    budget = runtime.get("reasoning_budget_tokens") if isinstance(runtime, dict) else None
    if isinstance(budget, int) and budget > 0:
        for f in fields:
            if f.get("key") == "llm.prediction.reasoning.budgetTokens":
                current = f.get("value")
                normalized = {"checked": True, "value": budget}
                if current != normalized:
                    f["value"] = normalized
                    actions.append(f"reasoning.budgetTokens={budget}")
                break
        else:
            fields.append({"key": "llm.prediction.reasoning.budgetTokens",
                           "value": {"checked": True, "value": budget}})
            actions.append(f"reasoning.budgetTokens={budget}")

    # stopStrings: " response"-Eintraege entfernen (stoppen vor dem Content)
    for f in fields:
        if f.get("key") == "llm.prediction.stopStrings":
            old = f.get("value")
            if isinstance(old, list):
                cleaned = [s for s in old if " response" not in s]
                if cleaned != old:
                    f["value"] = cleaned
                    actions.append(f"stopStrings: {old} -> {cleaned}")
            break

    # JSON-Anweisung aus SystemPrompt entfernen
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


_ADVANCED_COMMAND_HELP = r"""Specialist registry_tool.py commands (compatibility interface)

  compare, add, suggest, fill-ctx, fix-ctx, fix-np, fill-size, fill-quant,
  fill-arch, sync-from-gguf, fill-reasoning, fmt, migrate-keys, rm,
  sync-from-configs, sync-templates, sync-template-from-gguf,
  export-llama-preset, export-llama-args, patch-reasoning-effort,
  patch-glm-configs, pipeline

Examples:
  py -3.12 .\src\registry_tool.py advanced sync-from-configs --write
  py -3.12 .\src\registry_tool.py advanced export-llama-preset <path> --merge-existing
  py -3.12 .\src\registry_tool.py advanced pipeline full

These commands remain available for existing workflows. Prefer the short
public commands shown by `registry_tool.py --help` for routine maintenance.
"""


def _run_public_cli(arguments: list[str]) -> bool:
    """Handle the small documented CLI surface; retain old commands as aliases."""
    if arguments and arguments[0] == "advanced":
        if len(arguments) == 1 or arguments[1] in {"-h", "--help"}:
            print(_ADVANCED_COMMAND_HELP)
            return True
        sys.argv = [sys.argv[0], *arguments[1:]]
        return False

    public_commands = {"status", "sync", "full", "validate", "preset", "quarantine-missing"}
    if arguments and arguments[0] not in public_commands and arguments[0] not in {"-h", "--help"}:
        return False

    parser = argparse.ArgumentParser(
        prog="registry_tool.py",
        description="Inspect and maintain the benchmark model Registry from one shared local inventory.",
        epilog="Specialist commands remain available as `registry_tool.py advanced <command>`.",
    )
    subparsers = parser.add_subparsers(dest="command")

    status_parser = subparsers.add_parser("status", help="Read-only model inventory and Registry report")

    sync_parser = subparsers.add_parser(
        "sync", help="Refresh Registry data and report proposed LM Studio settings"
    )
    sync_parser.add_argument(
        "--import-lms-settings",
        action="store_true",
        help="import valid, unambiguous LM Studio settings into the Registry",
    )
    sync_parser.add_argument(
        "--refresh-sampling",
        action="store_true",
        help="search the web for sampling evidence; may take several minutes",
    )

    full_parser = subparsers.add_parser(
        "full",
        help="Run the full maintenance workflow (short form of the legacy `pipeline full` command)",
    )
    full_parser.add_argument("--ignore-drift", action="store_true", help="report open drift without failing")
    full_parser.add_argument(
        "--import-lms-settings",
        action="store_true",
        help="import valid, unambiguous LM Studio settings into the Registry",
    )
    full_parser.add_argument(
        "--refresh-sampling",
        action="store_true",
        help="search the web for sampling evidence; may take several minutes",
    )
    full_parser.add_argument(
        "--write-prompts",
        action="store_true",
        help="write assembled system prompts into uniquely joined LM Studio configs",
    )

    validate_parser = subparsers.add_parser("validate", help="Validate Registry and runtime ownership rules")
    validate_parser.add_argument("--ci", "--headless", action="store_true", help="skip local LM Studio state")
    validate_parser.add_argument("--verbose", action="store_true")
    validate_parser.add_argument("--repro", action="store_true")
    for inventory_parser in (status_parser, sync_parser, full_parser, validate_parser):
        inventory_parser.add_argument(
            "--model-list", type=Path,
            help="read a saved `lms ls --json` list instead of querying the live CLI",
        )
        inventory_parser.add_argument(
            "--gguf-list", type=Path,
            help="verify an absolute GGUF file list against disk before reading or changing the Registry",
        )

    preset_parser = subparsers.add_parser("preset", help="Export a derived llama.cpp preset INI")
    preset_parser.add_argument("path", nargs="?", help="output path (defaults to the project export folder)")
    preset_parser.add_argument(
        "--merge-existing", action="store_true", help="preserve global and manual settings in the target INI"
    )

    quarantine_parser = subparsers.add_parser(
        "quarantine-missing", help="Preview stale Registry entries; moving them requires --apply"
    )
    quarantine_parser.add_argument("--apply", action="store_true", help="move configs and remove stale entries")

    if not arguments or arguments[0] in {"-h", "--help"}:
        parser.print_help()
        print("\nRecommended sequence: status -> sync -> full")
        print("Import tested GUI tuning only after reviewing the proposals: sync --import-lms-settings")
        print("Write uniquely joined LM Studio system prompts explicitly: full --write-prompts")
        return True

    args = parser.parse_args(arguments)
    snapshot_options = {
        name: value for name in ("model_list", "gguf_list")
        if (value := getattr(args, name, None)) is not None
    }
    if args.command == "status":
        cmd_pipeline("status", **snapshot_options)
    elif args.command == "sync":
        cmd_pipeline(
            "sync",
            refresh_sampling=args.refresh_sampling,
            import_lms_settings=args.import_lms_settings,
            **snapshot_options,
        )
    elif args.command == "full":
        cmd_pipeline(
            "full",
            ignore_drift=args.ignore_drift,
            refresh_sampling=args.refresh_sampling,
            import_lms_settings=args.import_lms_settings,
            write_prompts=args.write_prompts,
            **snapshot_options,
        )
    elif args.command == "validate":
        if args.ci and (args.model_list is not None or args.gguf_list is not None):
            parser.error("--ci cannot be combined with local inventory snapshots")
        inventory = (None if args.ci else _collect_registry_inventory(args.model_list, args.gguf_list)
                     if args.model_list is not None or args.gguf_list is not None else _collect_registry_inventory())
        if inventory is not None:
            _ensure_gguf_inventory(inventory)
        errors = cmd_validate(
            verbose=args.verbose,
            repro=args.repro,
            ci=args.ci,
            inventory=inventory,
        )
        sys.exit(1 if _blocking_validation_errors(errors) else 0)
    elif args.command == "preset":
        sys.exit(cmd_export_llama_preset(args.path, merge_existing=args.merge_existing))
    elif args.command == "quarantine-missing":
        sys.exit(cmd_quarantine_missing(dry_run=not args.apply))
    return True


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
        "export-llama-preset": cmd_export_llama_preset,
        "export-llama-args": cmd_export_llama_args,
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
        ("pipeline", "Status/Sync/Full-Wartung: status | sync | full (Exit 1 bei blockierendem Registry-/Runtime-Konflikt)"),
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
        ("sync-from-configs", "GUI-Config-Felder melden; --write-experts importiert nur den getesteten MoE-Laufzeitwert"),
        ("export-llama-preset", "Abgeleitetes llama.cpp preset.ini aus lokalen GGUFs und Registry-Runtime erzeugen"),
        ("export-llama-args", "Direkte llama.cpp Start- und Request-Argumente als JSON exportieren"),
        ("migrate-keys", "Re-key entries without publisher prefix"),
        ("quarantine-missing", "Nicht-installierte Modelle: Configs+Eintrag in Quarantäne (Dry-run)"),
        ("rm", "Remove registry entry (optionally files + configs too)"),
    ]

    _print_menu(cmds)
    while True:
        try:
            choice = input("Select command or q: ").strip().lower()
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
    if _run_public_cli(sys.argv[1:]):
        return
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        if len(sys.argv) < 2:
            _interactive_menu()
        else:
            print(__doc__)
        return

    cmd = sys.argv[1]

    # A subcommand's help must never fall through to its normal action. This
    # guard is deliberately in place before any dispatch, including commands
    # which can move files or write configuration data.
    if any(argument in {"-h", "--help"} for argument in sys.argv[2:]):
        print(__doc__)
        return

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
        write_experts = "--write-experts" in sys.argv[2:]
        inventory = _collect_registry_inventory()
        # The narrow context repair can include a retained config no longer
        # present in LMS; other imports are restricted to the active snapshot.
        installed_models = None if write_context else inventory.lms_models
        cmd_sync_from_configs(
            write="--write" in sys.argv[2:] or write_context or write_experts,
            write_context=write_context,
            write_experts=write_experts,
            installed_models=installed_models,
            inventory=inventory,
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
        ci = "--ci" in flags or "--headless" in flags
        validation_inventory = None if ci else _collect_registry_inventory()
        if validation_inventory is not None:
            _ensure_gguf_inventory(validation_inventory)
        errors = cmd_validate(
            verbose="--verbose" in flags,
            repro="--repro" in flags,
            ci=ci,
            inventory=validation_inventory,
        )
        has_blocking_errors = bool(_blocking_validation_errors(errors))
        sys.exit(1 if has_blocking_errors else 0)
    elif cmd == "quarantine-missing":
        if "--apply" in sys.argv[2:] and "--dry-run" in sys.argv[2:]:
            print("[ERROR] --apply und --dry-run schließen sich aus")
            sys.exit(2)
        dry_run = "--apply" not in sys.argv[2:]
        sys.exit(cmd_quarantine_missing(dry_run=dry_run))
    elif cmd == "sync-templates":
        cmd_sync_templates()
    elif cmd == "sync-template-from-gguf":
        if len(sys.argv) < 3:
            print("[ERROR] Nutzung: python registry_tool.py sync-template-from-gguf <model-key>")
            sys.exit(1)
        sys.exit(cmd_sync_template_from_gguf(sys.argv[2]))
    elif cmd == "export-llama-preset":
        arguments = sys.argv[2:]
        output_path = next((item for item in arguments if not item.startswith("-")), None)
        sys.exit(cmd_export_llama_preset(output_path, merge_existing="--merge-existing" in arguments))
    elif cmd == "export-llama-args":
        output_path = next((item for item in sys.argv[2:] if not item.startswith("-")), None)
        sys.exit(cmd_export_llama_args(output_path))
    elif cmd == "pipeline":
        mode = sys.argv[2] if len(sys.argv) > 2 else "status"
        if mode.startswith("-"):
            mode = "status"
        if mode not in ("status", "sync", "full"):
            print(f"[ERROR] Unbekannter pipeline-Modus: {mode} (status|sync|full)")
            sys.exit(1)
        ignore_drift = "--ignore-drift" in sys.argv[2:]
        refresh_sampling = "--refresh-sampling" in sys.argv[2:]
        import_lms_settings = "--import-lms-settings" in sys.argv[2:]
        write_prompts = "--write-prompts" in sys.argv[2:]
        cmd_pipeline(
            mode,
            ignore_drift=ignore_drift,
            refresh_sampling=refresh_sampling,
            import_lms_settings=import_lms_settings,
            write_prompts=write_prompts,
        )
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
