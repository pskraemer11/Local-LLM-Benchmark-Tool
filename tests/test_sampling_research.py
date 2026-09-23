"""Tests for read-only web sampling research and plausibility filtering."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import registry_tool as rt
from sampling_research import (
    SourceDocument,
    _manufacturer_urls,
    _normalise_url,
    _research_source_urls,
    compact_sampling_block,
    research_sampling,
    research_sampling_report,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_research_uses_explicit_profiles_and_marks_fallbacks() -> None:
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
    assert {
        key: result["sampling"]["coding"][key]
        for key in ("temperature", "top_p", "top_k", "min_p")
    } == {
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
        "min_p": 0.05,
    }
    assert all(
        result["sampling"]["math"][key] == result["sampling"]["coding"][key]
        for key in ("temperature", "top_p", "top_k", "min_p")
    )
    assert result["sampling"]["math"]["evidence_kind"] == "derived"
    assert result["sampling"]["math"]["derived_from"] == "coding"
    assert "sampling_evidence" not in result
    assert result["sampling"]["thinking"]["enabled"] is True
    assert result["sampling"]["thinking"]["temperature"] == 0.6
    assert result["sampling"]["sampling_sources"]


def test_research_prefers_direct_category_profiles() -> None:
    def fetcher(url: str, _timeout: float) -> str | None:
        if url.endswith("/raw/main/README.md"):
            return """
            General tasks: temperature=0.7, top_p=0.8, top_k=20
            Precise coding tasks: temperature=0.6, top_p=0.95, top_k=20
            Math problems: temperature=0.4, top_p=0.9, top_k=10
            Agentic tool use: temperature=0.8, top_p=0.92, top_k=30
            Thinking mode: temperature=1.0, top_p=0.95, top_k=20
            """
        return None

    result = research_sampling(
        {"publisher": "example", "modelKey": "example/model"},
        fetcher=fetcher,
    )

    assert result is not None
    assert result["sampling"]["coding"]["temperature"] == 0.6
    assert result["sampling"]["math"]["temperature"] == 0.4
    assert result["sampling"]["knowledge"]["temperature"] == 0.7
    assert result["sampling"]["agentic"]["temperature"] == 0.8
    assert result["sampling"]["math"]["evidence_kind"] == "direct"


def test_research_maps_named_benchmarks_and_preserves_partial_agentic_profile() -> None:
    def fetcher(url: str, _timeout: float) -> str | None:
        if url.endswith("/raw/main/README.md"):
            return """
            Default settings (most tasks): temperature 1.0, top-p 0.95, max new tokens 131072.
            Terminal Bench and SWE-bench Verified settings: temperature 0.7, top-p 1.0, max new tokens 16384.
            τ²-Bench settings: temperature 0, max new tokens 16384.
            """
        return None

    result = research_sampling(
        {"publisher": "zai-org", "modelKey": "zai-org/glm-4.7-flash"},
        fetcher=fetcher,
    )

    assert result is not None
    assert result["sampling"]["knowledge"]["temperature"] == 1.0
    assert result["sampling"]["knowledge"]["top_p"] == 0.95
    assert result["sampling"]["coding"]["temperature"] == 0.7
    assert result["sampling"]["coding"]["top_p"] == 1.0
    assert result["sampling"]["math"]["temperature"] == 0.7
    assert result["sampling"]["math"]["top_p"] == 1.0
    assert result["sampling"]["math"]["derived_from"] == "coding"
    assert result["sampling"]["agentic"]["temperature"] == 0.0
    assert "top_p" not in result["sampling"]["agentic"]
    assert result["sampling"]["agentic"]["evidence_kind"] == "direct"


def test_partial_registry_sampling_fills_only_omitted_pair_value(mocker) -> None:
    mocker.patch.object(
        __import__("benchmark_config"),
        "_load_quant_registry",
        return_value={
            "zai-org/glm-4.7-flash@q3_k_s": {
                "sampling": {
                    "agentic": {"temperature": 0.0},
                    "sampling_research_status": "confirmed",
                }
            }
        },
    )

    from benchmark_config import get_model_config

    config = get_model_config("zai-org/glm-4.7-flash", category="agentic")
    assert (config["temperature"], config["top_p"]) == (0.0, 0.95)
    assert config["_source"] == "registry-sampling"


def test_research_separates_profiles_sharing_one_markdown_line() -> None:
    def fetcher(url: str, _timeout: float) -> str | None:
        if url.endswith("/raw/main/README.md"):
            return (
                "> - Thinking mode for precise coding tasks: temperature=0.6, top_p=0.95, top_k=20 "
                "> - Instruct (or non-thinking) mode for general tasks: temperature=0.7, top_p=0.8, top_k=20"
            )
        return None

    result = research_sampling(
        {"publisher": "example", "modelKey": "example/model"},
        fetcher=fetcher,
    )

    assert result is not None
    assert result["sampling"]["coding"]["temperature"] == 0.6
    assert result["sampling"]["knowledge"]["temperature"] == 0.7
    assert result["sampling"]["math"]["temperature"] == 0.6
    assert result["sampling"]["math"]["evidence_kind"] == "derived"
    assert result["sampling"]["math"]["derived_from"] == "coding"


def test_research_marks_math_unresolved_without_any_sampling_profile() -> None:
    result = research_sampling_report(
        {"publisher": "example", "modelKey": "example/missing"},
        fetcher=lambda _url, _timeout: None,
    )

    assert result["sampling_research_status"] == "not_found"
    assert result["sampling"]["math"]["evidence_kind"] == "unresolved"
    assert result["sampling"]["math"] == {
        "evidence_kind": "unresolved",
        "reason": "Kein allgemeines Profil; Coding-/Math-Fallback kann nicht belastbar bestimmt werden.",
    }
    assert "sampling_evidence" not in result


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


def test_research_ignores_unresolved_template_links() -> None:
    assert _normalise_url("/oobabooga/text-generation-webui/pull/5677/{{ revealButtonHref }}", "https://github.com") is None


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


def test_granite_manufacturer_source_is_generation_specific() -> None:
    assert _manufacturer_urls(
        {"publisher": "ibm-granite", "modelKey": "ibm-granite/granite-4.1-30b"}
    ) == ["https://www.ibm.com/granite/docs/models/granite4-1"]
    assert _manufacturer_urls(
        {"publisher": "mradermacher", "modelKey": "mradermacher/granite-4.2-30b-i1"}
    ) == ["https://www.ibm.com/granite/docs/models/granite4-2"]


def test_terminal_source_list_discards_crawler_navigation_links() -> None:
    documents = [
        SourceDocument("https://example.test/navigation", "", 1),
        SourceDocument("https://example.test/model-card", "", 4),
    ]

    assert _research_source_urls(documents) == ["https://example.test/model-card"]
    assert _research_source_urls(
        documents,
        {"temperature": {"url": "https://example.test/evidence", "excerpt": "..."}},
    ) == ["https://example.test/evidence"]


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
    entry = rt.load_registry(registry_path)["example/missing@q4_k"]
    assert entry["sampling"]["sampling_research_status"] == "unresolved"


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
    assert entry["sampling"]["sampling_research_status"] == "confirmed"
    assert entry["sampling"]["sampling_sources"] == ["https://example.com/model-card"]
    assert entry["sampling"]["thinking"]["enabled"] is True


def test_sampling_report_persists_category_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        "example/model@q4_k:\n  publisher: example\n  arch: dense\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(rt, "REGISTRY_PATH", registry_path)

    entry = rt.load_registry(registry_path)["example/model@q4_k"]
    changed = rt._apply_sampling_report(
        entry,
        {
            "sampling_research_status": "confirmed",
            "sampling": {
                "coding": {"temperature": 0.6, "top_p": 0.95},
                "math": {"temperature": 0.6, "top_p": 0.95},
            },
            "sampling_category_status": {"coding": "direct", "math": "derived"},
            "sampling_sources": ["https://example.com/model-card"],
            "sampling_evidence": [
                {"profile": "math", "evidence_kind": "derived", "derived_from": "coding"}
            ],
        },
    )

    assert changed is True
    assert entry["sampling"]["coding"]["evidence_kind"] == "direct"
    assert entry["sampling"]["math"]["evidence_kind"] == "derived"
    assert entry["sampling"]["math"]["derived_from"] == "coding"


def test_forced_sampling_refresh_researches_existing_sampling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        "example/model@q4_k:\n"
        "  publisher: example\n"
        "  arch: dense\n"
        "  sampling:\n"
        "    coding: {temperature: 0.7, top_p: 0.9}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(rt, "REGISTRY_PATH", registry_path)
    calls = 0

    def patched(_model: dict[str, object]) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {
            "sampling_research_status": "confirmed",
            "sampling": {"coding": {"temperature": 0.6, "top_p": 0.95}},
            "sampling_category_status": {"coding": "direct", "math": "derived"},
            "sampling_sources": ["https://example.com/model-card"],
        }

    monkeypatch.setattr(rt, "research_sampling", patched)
    assert rt._research_missing_sampling(rt.load_registry(registry_path), force=True) == []
    assert calls == 1
    entry = rt.load_registry(registry_path)["example/model@q4_k"]
    assert entry["sampling"]["coding"]["temperature"] == 0.6
    assert entry["sampling"]["math"]["evidence_kind"] == "derived"
    assert entry["sampling"]["math"]["derived_from"] == "coding"


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

    entry = rt.load_registry(registry_path)["example/example-coder-7b@?"]
    assert result["added"] == ["example/example-coder-7b@?"]
    assert entry["sampling"]["coding"]["temperature"] == 0.7
    assert entry["sampling"]["sampling_sources"] == ["https://huggingface.co/example/model"]


def test_compact_sampling_block_removes_normal_and_repeated_urls() -> None:
    compact = compact_sampling_block(
        {
            "coding": {"temperature": 0.6, "top_p": 0.95},
            "knowledge": {"temperature": 0.6, "top_p": 0.95},
            "math": {"temperature": 0.6, "top_p": 0.95},
        },
        status="confirmed",
        researched_at="2026-09-21T00:00:00+00:00",
        sources=["https://example.com/model-card", "https://example.com/model-card"],
        evidence=[
            {"profile": "normal", "evidence_kind": "direct", "url": "https://example.com/model-card"},
            {"profile": "coding", "evidence_kind": "derived", "derived_from": "normal"},
            {"profile": "math", "evidence_kind": "derived", "derived_from": "coding"},
        ],
    )

    assert "normal" not in compact
    assert compact["coding"]["evidence_kind"] == "direct"
    assert compact["math"]["derived_from"] == "coding"
    assert compact["sampling_sources"] == ["https://example.com/model-card"]
    assert "sampling_evidence" not in compact


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
