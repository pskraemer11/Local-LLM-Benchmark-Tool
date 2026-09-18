"""Tests for read-only web sampling research and plausibility filtering."""

from __future__ import annotations

from pathlib import Path

import pytest

import registry_tool as rt
from sampling_research import research_sampling


def test_research_extracts_profile_and_applies_it_to_categories() -> None:
    requested: list[str] = []

    def fetcher(url: str, _timeout: float) -> str | None:
        requested.append(url)
        if url.endswith("/raw/main/README.md"):
            return """
            ## Recommended generation settings
            For non-thinking mode: temperature: 0.7, top_p: 0.9, top_k: 40, min_p: 0.05
            For thinking mode: temperature: 0.6, top_p: 0.95, top_k: 20, min_p: 0
            """
        return None

    result = research_sampling(
        {"publisher": "example", "modelKey": "example/model", "path": "example/model/model.gguf"},
        fetcher=fetcher,
    )

    assert result is not None
    assert requested[0].endswith("https://huggingface.co/example/model/raw/main/README.md")
    assert result["sampling"]["coding"] == {
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
        "min_p": 0.05,
    }
    assert result["sampling"]["math"] == result["sampling"]["coding"]
    assert result["sampling"]["thinking"]["enabled"] is True
    assert result["sampling"]["thinking"]["temperature"] == 0.6
    assert result["sampling_source"] == "web-research"


def test_research_rejects_implausible_or_incomplete_values() -> None:
    def fetcher(url: str, _timeout: float) -> str | None:
        if url.endswith("/raw/main/README.md"):
            return "temperature: 3.0\ntop_p: 0.9\n"
        return None

    result = research_sampling(
        {"publisher": "example", "modelKey": "example/model"},
        fetcher=fetcher,
    )

    assert result is None


def test_research_checks_known_manufacturer_sources() -> None:
    requested: list[str] = []

    def fetcher(url: str, _timeout: float) -> str | None:
        requested.append(url)
        if url.endswith("/raw/main/README.md"):
            return "temperature: 0.7\ntop_p: 0.9\n"
        return None

    result = research_sampling(
        {"publisher": "qwen", "modelKey": "qwen/example-model"},
        fetcher=fetcher,
    )

    assert result is not None
    assert any(url.startswith("https://qwenlm.github.io") for url in requested)
    assert any(url.startswith("https://qwen.readthedocs.io") for url in requested)


def test_research_rejects_conflicting_values_at_same_source_priority() -> None:
    def fetcher(url: str, _timeout: float) -> str | None:
        if url.endswith("/raw/main/README.md"):
            return "temperature: 0.7\ntop_p: 0.9\n"
        if url.endswith("/raw/master/README.md"):
            return "temperature: 0.8\ntop_p: 0.9\n"
        return None

    result = research_sampling(
        {"publisher": "example", "modelKey": "example/model"},
        fetcher=fetcher,
    )

    assert result is None


def test_cmd_add_persists_researched_sampling_without_touching_lms_configs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(rt, "REGISTRY_PATH", registry_path)
    monkeypatch.setattr(rt, "MODELS_CACHE", tmp_path / "models")
    monkeypatch.setattr(
        rt,
        "research_sampling",
        lambda _model: {
            "sampling": {"coding": {"temperature": 0.7, "top_p": 0.9}},
            "sampling_source": "web-research",
            "sampling_sources": ["https://huggingface.co/example/model"],
        },
    )

    result = rt.cmd_add(
        [{"modelKey": "example-coder-7b", "publisher": "example", "size_bytes": 1_000_000_000}],
        research_web=True,
    )

    entry = rt.load_registry(registry_path)["example/example-coder-7b"]
    assert result["added"] == ["example/example-coder-7b"]
    assert entry["sampling"]["coding"]["temperature"] == 0.7
    assert entry["sampling_sources"] == ["https://huggingface.co/example/model"]


def test_sync_researches_existing_entry_without_sampling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        "example/model@q4_k_m:\n"
        "  publisher: example\n"
        "  hf_url: https://huggingface.co/example/model\n"
        "  arch: dense\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(rt, "REGISTRY_PATH", registry_path)
    monkeypatch.setattr(
        rt,
        "research_sampling",
        lambda _model: {
            "sampling": {"coding": {"temperature": 0.7, "top_p": 0.9}},
            "sampling_source": "web-research",
            "sampling_sources": ["https://example.com/model-card"],
        },
    )

    unresolved = rt._research_missing_sampling(rt.load_registry(registry_path))

    assert unresolved == []
    entry = rt.load_registry(registry_path)["example/model@q4_k_m"]
    assert entry["sampling"]["coding"]["temperature"] == 0.7
