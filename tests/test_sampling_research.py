"""Tests for read-only web sampling research and plausibility filtering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import registry_tool as rt
from sampling_research import research_sampling, research_sampling_report


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


def test_research_resolves_quantizer_through_huggingface_base_model_api() -> None:
    requested: list[str] = []

    def fetcher(url: str, _timeout: float) -> str | None:
        requested.append(url)
        if url == "https://huggingface.co/api/models/byteshape/example?full=false":
            return json.dumps({"tags": ["base_model:Qwen/Qwen3.6-35B-A3B"]})
        if url == "https://huggingface.co/Qwen/Qwen3.6-35B-A3B/raw/main/README.md":
            return 'Recommended: {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0.0}'
        return None

    result = research_sampling(
        {"publisher": "byteshape", "modelKey": "byteshape/example"},
        fetcher=fetcher,
    )

    assert result is not None
    assert result["sampling"]["coding"]["temperature"] == 0.7
    assert any("Qwen3.6-35B-A3B/raw/main" in url for url in requested)


def test_research_follows_relative_official_documentation_link() -> None:
    requested: list[str] = []

    def fetcher(url: str, _timeout: float) -> str | None:
        requested.append(url)
        if url.endswith("/raw/main/README.md"):
            return "See [generation documentation](https://qwen.readthedocs.io/en/latest/)."
        if url == "https://qwen.readthedocs.io/en/latest":
            return "See [sampling](generation/sampling.html)."
        if url == "https://qwen.readthedocs.io/en/latest/generation/sampling.html":
            return "Recommended generation: temperature=0.7, top_p=0.8, top_k=20"
        return None

    result = research_sampling(
        {"publisher": "qwen", "modelKey": "qwen/example"},
        fetcher=fetcher,
    )

    assert result is not None
    assert result["sampling"]["coding"]["top_k"] == 20
    assert "https://qwen.readthedocs.io/en/latest/generation/sampling.html" in requested


def test_research_report_marks_unresolved_and_persists_status_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = research_sampling_report(
        {"publisher": "example", "modelKey": "example/missing"},
        fetcher=lambda _url, _timeout: None,
    )
    assert report["sampling_research_status"] == "not_found"

    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        "example/missing@q4_k:\n"
        "  publisher: example\n"
        "  hf_url: https://huggingface.co/example/missing\n"
        "  arch: dense\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(rt, "REGISTRY_PATH", registry_path)
    calls = 0

    def patched(_model: dict[str, object]) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"sampling_research_status": "unresolved", "sampling_sources": []}

    monkeypatch.setattr(rt, "research_sampling", patched)
    reg = rt.load_registry(registry_path)
    assert rt._research_missing_sampling(reg) == ["example/missing@q4_k"]
    assert rt._research_missing_sampling(rt.load_registry(registry_path)) == []
    assert calls == 1
    assert rt.load_registry(registry_path)["example/missing@q4_k"]["sampling_research_status"] == "unresolved"


def test_manual_review_uses_validated_registry_write_seam(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        "example/model@q4_k:\n  publisher: example\n  hf_url: https://huggingface.co/example/model\n  arch: dense\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(rt, "REGISTRY_PATH", registry_path)

    rt.apply_sampling_review(
        "example/model@q4_k",
        {
            "coding": {"temperature": 0.6, "top_p": 0.95},
            "thinking": {"enabled": True, "temperature": 0.6, "top_p": 0.95},
        },
        ["https://example.com/model-card"],
        [{"field": "temperature", "url": "https://example.com/model-card", "excerpt": "temperature=0.6"}],
    )

    entry = rt.load_registry(registry_path)["example/model@q4_k"]
    assert entry["sampling_source"] == "manual-web-review"
    assert entry["sampling_research_status"] == "confirmed"
    assert entry["sampling"]["thinking"]["enabled"] is True


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
        "example/model@q4_k_m:\n  publisher: example\n  hf_url: https://huggingface.co/example/model\n  arch: dense\n",
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
