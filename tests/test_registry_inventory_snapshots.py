"""Saved inventory inputs must agree with disk before Registry maintenance."""

import json
from pathlib import Path

import pytest

import registry_tool as rt


def test_saved_lms_inventory_does_not_query_live_cli(tmp_path, monkeypatch):
    model_list = tmp_path / "models.json"
    models = [{"modelKey": "owner/model", "publisher": "owner", "quantization": {"name": "Q6_K"}}]
    model_list.write_text(json.dumps(models), encoding="utf-8")
    monkeypatch.setattr(rt, "load_registry", lambda: {})
    monkeypatch.setattr(rt, "read_lms_configs", lambda _: [])
    monkeypatch.setattr(rt, "_refresh_identity_links", lambda _: None)
    monkeypatch.setattr(rt, "_run_lms_ls", lambda: pytest.fail("Live CLI must not replace the provided list"))
    inventory = rt._collect_registry_inventory(model_list=model_list)
    assert inventory.raw_lms_models == models


@pytest.mark.parametrize("content", ['{"models": []}', '[1]', '[null]'])
def test_malformed_lms_inventory_is_rejected(tmp_path, content):
    model_list = tmp_path / "models.json"
    model_list.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="JSON list of model objects"):
        rt.load_lms_json(model_list)


def test_complete_gguf_snapshot_includes_helpers(tmp_path, monkeypatch):
    files = [tmp_path / "model-Q6_K.gguf", tmp_path / "model-dspark-Q4_K_M.gguf"]
    for file in files:
        file.touch()
    snapshot = tmp_path / "files.txt"
    snapshot.write_text("\n".join(map(str, files)), encoding="utf-8")
    monkeypatch.setattr(rt, "_gguf_roots", lambda: (tmp_path,))
    rt._validate_gguf_snapshot(snapshot)


@pytest.mark.parametrize("kind", ["deleted", "unlisted", "duplicate", "outside", "relative", "empty"])
def test_gguf_snapshot_mismatch_fails_before_registry_read(tmp_path, monkeypatch, kind):
    root = tmp_path / "models"
    root.mkdir()
    model = root / "model-Q6_K.gguf"
    model.touch()
    snapshot = tmp_path / "files.txt"
    lines = [str(model)]
    if kind == "deleted":
        lines.append(str(root / "deleted.gguf"))
    elif kind == "unlisted":
        (root / "new-helper.gguf").touch()
    elif kind == "duplicate":
        lines.append(str(model))
    elif kind == "outside":
        outside = tmp_path / "outside.gguf"
        outside.touch()
        lines.append(str(outside))
    elif kind == "relative":
        lines = ["model-Q6_K.gguf"]
    elif kind == "empty":
        lines = []
    snapshot.write_text("\n".join(lines), encoding="utf-8")
    monkeypatch.setattr(rt, "_gguf_roots", lambda: (root,))
    monkeypatch.setattr(rt, "load_registry", lambda: pytest.fail("Snapshot failure must precede Registry access"))
    with pytest.raises(ValueError):
        rt._collect_registry_inventory(gguf_list=snapshot)


def test_public_sync_accepts_both_snapshots(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(rt, "cmd_pipeline", lambda *args, **kwargs: calls.append((args, kwargs)))
    models, files = tmp_path / "models.json", tmp_path / "ggufs.txt"
    assert rt._run_public_cli(["sync", "--model-list", str(models), "--gguf-list", str(files)])
    assert calls[0][1]["model_list"] == models
    assert calls[0][1]["gguf_list"] == files


def test_headless_validation_rejects_local_snapshots(tmp_path):
    with pytest.raises(SystemExit) as error:
        rt._run_public_cli(["validate", "--ci", "--model-list", str(tmp_path / "models.json")])
    assert error.value.code == 2


def test_snapshot_flags_have_actionable_help(capsys):
    with pytest.raises(SystemExit) as result:
        rt._run_public_cli(["sync", "--help"])
    assert result.value.code == 0
    output = capsys.readouterr().out
    assert "--model-list" in output and "live CLI" in output
    assert "--gguf-list" in output and "against disk" in output
