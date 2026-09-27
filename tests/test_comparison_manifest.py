from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from comparison_manifest import (
    FORMAT,
    PIPELINE_BENCHMARKS,
    VARIANT,
    select_custom_task_ids,
    validate_comparison_manifest,
)


def test_custom_selection_is_seeded_and_skips_known_broken_task(tmp_path: Path) -> None:
    source = tmp_path / "data_science.jsonl"
    rows = [
        {"task_id": "broken", "code_context": "scipy.interpolate.interp2d"},
        {"task_id": "a", "code_context": "numpy"},
        {"task_id": "b", "code_context": "pandas"},
    ]
    source.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    assert select_custom_task_ids(source, sample_size=1, seed=42) == select_custom_task_ids(
        source, sample_size=1, seed=42
    )
    assert select_custom_task_ids(source, sample_size=3, seed=42) == ["a", "b"]


def test_variant_b_requires_all_pipeline_benchmarks(tmp_path: Path) -> None:
    custom_source = tmp_path / "simple_evals" / "data_science.jsonl"
    custom_source.parent.mkdir()
    custom_source.write_text(json.dumps({"task_id": "a"}) + "\n", encoding="utf-8")
    config_source = tmp_path / "src" / "benchmark_config.py"
    config_source.parent.mkdir()
    config_source.write_text("SCENARIOS = []\n", encoding="utf-8")
    manifest = {
        "format": FORMAT,
        "variant": VARIANT,
        "sample_size": 1,
        "seed": 42,
        "pipelines": {},
    }
    for pipeline, contract in PIPELINE_BENCHMARKS.items():
        entry = {
            **contract,
            "selected_ids": ["doc:0"] if pipeline == "lmeval" else ["a"],
        }
        if pipeline in {"custom", "agentic"}:
            source = custom_source if pipeline == "custom" else config_source
            entry["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        if pipeline in {"evalplus", "lmeval"}:
            entry["package_version"] = "test-version"
        if pipeline == "lmeval":
            entry["limit"] = 1
        manifest["pipelines"][pipeline] = entry
    errors = validate_comparison_manifest(
        manifest,
        [contract["benchmark"] for contract in PIPELINE_BENCHMARKS.values()],
        sample_size=1,
        seed=42,
        project_root=tmp_path,
    )
    assert errors == []

    errors = validate_comparison_manifest(
        manifest,
        ["DS1000"],
        sample_size=1,
        seed=42,
        project_root=tmp_path,
    )
    assert any("missing requested benchmark" in error for error in errors)

    missing_hash = json.loads(json.dumps(manifest))
    del missing_hash["pipelines"]["custom"]["source_sha256"]
    errors = validate_comparison_manifest(
        missing_hash,
        [contract["benchmark"] for contract in PIPELINE_BENCHMARKS.values()],
        sample_size=1,
        seed=42,
        project_root=tmp_path,
    )
    assert any("source_sha256 is required" in error for error in errors)

    missing_selection = json.loads(json.dumps(manifest))
    del missing_selection["pipelines"]["agentic"]["selected_ids"]
    errors = validate_comparison_manifest(
        missing_selection,
        [contract["benchmark"] for contract in PIPELINE_BENCHMARKS.values()],
        sample_size=1,
        seed=42,
        project_root=tmp_path,
    )
    assert any("agentic has no valid selected_ids" in error for error in errors)
