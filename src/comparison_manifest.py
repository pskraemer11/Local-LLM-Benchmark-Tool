"""Build and validate the four-pipeline comparison manifest (Variant B).

Variant B is intentionally small: it proves that one benchmark from every
pipeline is executed with the same seed/sample-size contract.  It is not a
replacement for the full task manifests used for long quality runs.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import random
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

FORMAT = "benchmark-comparison-manifest-v2"
VARIANT = "B"
MAX_CUSTOM_TASKS = 1000
CUSTOM_BROKEN_PATTERNS = ("interp2d",)

PIPELINE_BENCHMARKS: dict[str, dict[str, str]] = {
    "custom": {"benchmark": "DS1000", "file": "simple_evals/data_science.jsonl"},
    "evalplus": {"benchmark": "HumanEval+", "dataset": "humaneval"},
    "lmeval": {"benchmark": "ARC-Challenge", "task": "arc_challenge_chat"},
    "agentic": {"benchmark": "Agentic", "mode": "random"},
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_task_id(task: dict[str, Any], ordinal: int) -> str:
    """Use the same stable identity precedence as the task manifest."""
    value = next(
        (task.get(key) for key in ("task_id", "id", "question_id", "problem_id") if task.get(key) is not None),
        ordinal,
    )
    return str(value)


def _select_stratified_tasks(tasks: list[dict[str, Any]], sample_size: int, seed: int) -> list[dict[str, Any]]:
    """Mirror custom_benchmark.subsample_tasks without importing its runtime."""
    if sample_size >= len(tasks):
        return tasks
    rng = random.Random(seed)
    groups: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        group = task.get("_group")
        if group is not None:
            groups.setdefault(str(group), []).append(task)
    if not groups:
        return rng.sample(tasks, min(sample_size, len(tasks)))
    per_group = math.ceil(sample_size / len(groups))
    selected: list[dict[str, Any]] = []
    for group in sorted(groups):
        pool = groups[group]
        selected.extend(rng.sample(pool, min(len(pool), per_group)))
    if len(selected) > sample_size:
        selected = rng.sample(selected, sample_size)
    return selected


def select_custom_task_ids(source: Path, sample_size: int, seed: int) -> list[str]:
    """Reproduce the custom pipeline's DS1000 selection contract."""
    tasks: list[dict[str, Any]] = []
    with source.open(encoding="utf-8") as handle:
        for ordinal, line in enumerate(handle):
            if not line.strip():
                continue
            task = json.loads(line)
            if not isinstance(task, dict):
                raise ValueError(f"{source}: line {ordinal + 1} is not a JSON object")
            task["_manifest_ordinal"] = len(tasks)
            tasks.append(task)
    tasks = tasks[:MAX_CUSTOM_TASKS]
    tasks = [
        task
        for task in tasks
        if not any(pattern in str(task.get("code_context", "")) for pattern in CUSTOM_BROKEN_PATTERNS)
    ]
    selected = _select_stratified_tasks(tasks, sample_size, seed)
    return [canonical_task_id(task, int(task["_manifest_ordinal"])) for task in selected]


def select_evalplus_task_ids(dataset: str, sample_size: int, seed: int) -> list[str]:
    """Reproduce run_evalplus's sorted numeric task selection."""
    from evalplus.data import get_human_eval_plus, get_mbpp_plus

    loader = get_human_eval_plus if dataset == "humaneval" else get_mbpp_plus
    task_ids = sorted(loader().keys(), key=lambda value: int(value.split("/")[1]))
    return random.Random(seed).sample(task_ids, min(sample_size, len(task_ids)))


def select_agentic_ids(sample_size: int, seed: int) -> list[str]:
    """Reproduce the random agentic scenario selection."""
    from benchmark_config import TOOL_EVAL_SCENARIO_IDS

    return random.Random(seed).sample(TOOL_EVAL_SCENARIO_IDS, min(sample_size, len(TOOL_EVAL_SCENARIO_IDS)))


def select_lmeval_doc_ids(sample_size: int) -> list[str]:
    """Name the first N lm-eval docs whose logged indices are verified at runtime."""
    return [f"doc:{index}" for index in range(sample_size)]


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def build_comparison_manifest(project_root: Path, sample_size: int = 1, seed: int = 42) -> dict[str, Any]:
    """Create a deterministic Variant-B manifest for the current checkout."""
    if sample_size < 1:
        raise ValueError("sample_size must be positive")
    root = project_root.resolve()
    custom_source = root / PIPELINE_BENCHMARKS["custom"]["file"]
    config_source = root / "src" / "benchmark_config.py"
    if not custom_source.is_file():
        raise FileNotFoundError(custom_source)
    if not config_source.is_file():
        raise FileNotFoundError(config_source)

    pipelines: dict[str, dict[str, Any]] = {
        "custom": {
            **PIPELINE_BENCHMARKS["custom"],
            "source": str(custom_source),
            "source_sha256": sha256_file(custom_source),
            "selected_ids": select_custom_task_ids(custom_source, sample_size, seed),
            "selection_contract": "custom_benchmark.subsample_tasks after DS1000 broken-task filtering",
        },
        "evalplus": {
            **PIPELINE_BENCHMARKS["evalplus"],
            "package_version": _package_version("evalplus"),
            "selected_ids": select_evalplus_task_ids("humaneval", sample_size, seed),
            "selection_contract": "evalplus task IDs sorted numerically, then random.sample(seed)",
        },
        "lmeval": {
            **PIPELINE_BENCHMARKS["lmeval"],
            "package_version": _package_version("lm-eval"),
            "limit": sample_size,
            "selected_ids": select_lmeval_doc_ids(sample_size),
            "selection_contract": "first N task documents; verified from lm_eval --log_samples doc_id values",
        },
        "agentic": {
            **PIPELINE_BENCHMARKS["agentic"],
            "source": str(config_source),
            "source_sha256": sha256_file(config_source),
            "selected_ids": select_agentic_ids(sample_size, seed),
            "selection_contract": "TOOL_EVAL_SCENARIO_IDS random.sample(seed)",
        },
    }
    return {
        "format": FORMAT,
        "variant": VARIANT,
        "sample_size": sample_size,
        "seed": seed,
        "pipelines": pipelines,
    }


def load_comparison_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"comparison manifest cannot be read: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("comparison manifest must be a JSON object")
    return data


def validate_comparison_manifest(
    manifest: dict[str, Any],
    requested_benchmarks: list[str],
    sample_size: int,
    seed: int | None,
    project_root: Path,
) -> list[str]:
    """Return actionable validation errors; an empty list means accepted."""
    errors: list[str] = []
    if manifest.get("format") != FORMAT or manifest.get("variant") != VARIANT:
        errors.append(f"expected {FORMAT} / variant {VARIANT}")
    if manifest.get("sample_size") != sample_size:
        errors.append(f"sample_size mismatch: manifest={manifest.get('sample_size')!r}, run={sample_size}")
    if seed is None or manifest.get("seed") != seed:
        errors.append(f"seed mismatch: manifest={manifest.get('seed')!r}, run={seed!r}")
    pipelines = manifest.get("pipelines")
    if not isinstance(pipelines, dict):
        return [*errors, "pipelines must be an object"]
    requested = {name.casefold() for name in requested_benchmarks}
    for pipeline, contract in PIPELINE_BENCHMARKS.items():
        entry = pipelines.get(pipeline)
        if not isinstance(entry, dict):
            errors.append(f"missing pipeline entry: {pipeline}")
            continue
        benchmark = str(entry.get("benchmark", ""))
        if benchmark.casefold() not in requested:
            errors.append(f"missing requested benchmark for pipeline {pipeline}: {benchmark}")
        for field, expected in contract.items():
            if entry.get(field) != expected:
                errors.append(f"pipeline {pipeline} {field} mismatch: expected {expected!r}")
        selected_ids = entry.get("selected_ids")
        if (
            not isinstance(selected_ids, list)
            or not selected_ids
            or any(not isinstance(value, str) or not value for value in selected_ids)
        ):
            errors.append(f"pipeline {pipeline} has no valid selected_ids")
        elif len(selected_ids) > sample_size or len(set(selected_ids)) != len(selected_ids):
            errors.append(f"pipeline {pipeline} selected_ids must be unique and no longer than sample_size")
        if pipeline == "lmeval":
            if entry.get("limit") != sample_size:
                errors.append("lmeval limit must equal sample_size")
            if selected_ids != select_lmeval_doc_ids(sample_size):
                errors.append("lmeval selected_ids must bind the first N logged document indices")
        if pipeline in {"evalplus", "lmeval"} and not isinstance(entry.get("package_version"), str):
            errors.append(f"pipeline {pipeline} package_version is required")

        relative_source = contract.get("file")
        if pipeline == "agentic":
            relative_source = "src/benchmark_config.py"
        if relative_source:
            source = project_root.resolve() / relative_source
            expected_hash = entry.get("source_sha256")
            if not source.is_file():
                errors.append(f"manifest source missing: {source}")
            elif not isinstance(expected_hash, str) or len(expected_hash) != 64:
                errors.append(f"pipeline {pipeline} source_sha256 is required")
            elif expected_hash != sha256_file(source):
                errors.append(f"manifest source changed: {source}")
    return errors
