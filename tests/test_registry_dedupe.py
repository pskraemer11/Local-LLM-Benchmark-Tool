"""Registry dedupe only removes aliases of the same physical GGUF."""

from __future__ import annotations

from typing import TYPE_CHECKING

import registry_tool as rt
from tests.gguf_fixture import write_gguf

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _registry_with_shared_artifact(tmp_path: Path, *, conflicting_context: bool) -> tuple[Path, Path]:
    models_root = tmp_path / "models"
    artifact = models_root / "lmstudio-community" / "model-GGUF" / "model-Q4_K_M.gguf"
    write_gguf(artifact)
    registry_path = tmp_path / "model_registry.yaml"
    canonical = {
        "publisher": "lmstudio-community",
        "context_length": 16384,
        "local": {"model_path": str(artifact)},
        "notes": "physical artifact owner",
    }
    alias = {
        "publisher": "qwen",
        "context_length": 32768 if conflicting_context else 16384,
        "hf_url": "https://huggingface.co/qwen/model",
        "local": {"model_path": str(artifact)},
        "capabilities": ["text", "coding"],
    }
    rt.save_registry(
        {
            "qwen/model@q4_k_m": alias,
            "lmstudio-community/model@q4_k_m": canonical,
        },
        registry_path,
    )
    return registry_path, models_root


def test_dedupe_dry_run_reports_same_artifact_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry_path, models_root = _registry_with_shared_artifact(tmp_path, conflicting_context=False)
    before = registry_path.read_bytes()
    monkeypatch.setattr(rt, "_gguf_roots", lambda: (models_root,))

    result = rt.cmd_dedupe_registry(registry_path=registry_path)

    output = capsys.readouterr().out
    assert result == 0
    assert "DUPLICATE" in output
    assert "lmstudio-community/model@q4_k_m" in output
    assert registry_path.read_bytes() == before


def test_dedupe_apply_removes_unambiguous_shared_artifact_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path, models_root = _registry_with_shared_artifact(tmp_path, conflicting_context=False)
    monkeypatch.setattr(rt, "_gguf_roots", lambda: (models_root,))

    result = rt.cmd_dedupe_registry(registry_path=registry_path, apply=True)

    saved = rt.load_registry(registry_path)
    assert result == 0
    assert list(saved) == ["lmstudio-community/model@q4_k_m"]
    assert saved["lmstudio-community/model@q4_k_m"]["capabilities"] == ["text", "coding"]
    assert len(list(tmp_path.glob("model_registry.yaml.bak-dedupe-*"))) == 1


def test_dedupe_apply_requires_keep_choice_for_conflicting_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path, models_root = _registry_with_shared_artifact(tmp_path, conflicting_context=True)
    before = registry_path.read_bytes()
    monkeypatch.setattr(rt, "_gguf_roots", lambda: (models_root,))

    result = rt.cmd_dedupe_registry(registry_path=registry_path, apply=True)

    assert result == 1
    assert registry_path.read_bytes() == before
    assert not list(tmp_path.glob("model_registry.yaml.bak-dedupe-*"))

    result = rt.cmd_dedupe_registry(
        registry_path=registry_path,
        apply=True,
        keep_keys=["lmstudio-community/model@q4_k_m"],
    )

    saved = rt.load_registry(registry_path)
    assert result == 0
    assert list(saved) == ["lmstudio-community/model@q4_k_m"]
    assert saved["lmstudio-community/model@q4_k_m"]["context_length"] == 16384
    assert saved["lmstudio-community/model@q4_k_m"]["capabilities"] == ["text", "coding"]
    assert len(list(tmp_path.glob("model_registry.yaml.bak-dedupe-*"))) == 1


def test_dedupe_preserves_same_name_quant_from_distinct_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    models_root = tmp_path / "models"
    unsloth_file = models_root / "unsloth" / "model-GGUF" / "model-IQ3_S.gguf"
    byteshape_file = models_root / "byteshape" / "model-GGUF" / "model-IQ3_S.gguf"
    write_gguf(unsloth_file, source_repo="unsloth/model")
    write_gguf(byteshape_file, source_repo="byteshape/model")
    registry_path = tmp_path / "model_registry.yaml"
    rt.save_registry(
        {
            "unsloth/model@iq3_s": {"local": {"model_path": str(unsloth_file)}},
            "byteshape/model@iq3_s": {"local": {"model_path": str(byteshape_file)}},
        },
        registry_path,
    )
    before = registry_path.read_bytes()
    monkeypatch.setattr(rt, "_gguf_roots", lambda: (models_root,))

    result = rt.cmd_dedupe_registry(registry_path=registry_path, apply=True)

    assert result == 0
    assert "DISTINCT" in capsys.readouterr().out
    assert registry_path.read_bytes() == before


def test_dedupe_apply_is_all_or_nothing_when_any_shared_path_is_unproven(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry_path, models_root = _registry_with_shared_artifact(tmp_path, conflicting_context=False)
    missing_artifact = models_root / "unknown" / "model-GGUF" / "model-Q4_K_M.gguf"
    registry = rt.load_registry(registry_path)
    registry["unknown/model@q4_k_m"] = {"local": {"model_path": str(missing_artifact)}}
    registry["unknown-alias/model@q4_k_m"] = {"local": {"model_path": str(missing_artifact)}}
    rt.save_registry(registry, registry_path)
    before = registry_path.read_bytes()
    monkeypatch.setattr(rt, "_gguf_roots", lambda: (models_root,))

    result = rt.cmd_dedupe_registry(registry_path=registry_path, apply=True)

    assert result == 1
    assert "UNPROVEN" in capsys.readouterr().out
    assert registry_path.read_bytes() == before
    assert not list(tmp_path.glob("model_registry.yaml.bak-dedupe-*"))
