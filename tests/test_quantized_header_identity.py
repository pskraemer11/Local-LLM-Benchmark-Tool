"""Publisher-scoped fork formats require real header and tensor-type evidence."""

from __future__ import annotations

import json
import struct

import pytest
import yaml

import registry_tool as rt
from assemble_blueprint import clear_lms_config_cache, read_lms_configs
from gguf_evidence import read_gguf_evidence, resolve_artifact_quant
from local_model_resolver import LocalModelResolver, ModelResolutionError
from quantization import extract_quant_from_text, is_known_quant, quant_from_gguf_evidence
from tests.gguf_fixture import write_gguf


def _write_fork_gguf(path, *, file_type=56, tensor_type=56):
    name = "blk.0.ffn_gate.weight"
    write_gguf(path, metadata={"general.file_type": file_type}, tensors={name: (4, 4)})
    encoded = name.encode("utf-8")
    prefix = struct.pack("<Q", len(encoded)) + encoded + struct.pack("<IQQ", 2, 4, 4)
    original = prefix + struct.pack("<IQ", 0, 0)
    raw = path.read_bytes()
    assert raw.count(original) == 1
    path.write_bytes(raw.replace(original, prefix + struct.pack("<IQ", tensor_type, 0)))
    return path


def test_naked_llmsforall_file_requires_matching_header_and_tensor_type(tmp_path):
    artifact = _write_fork_gguf(tmp_path / "llmsforall" / "Millie-35B-A3B-11GB" / "Millie-35B-A3B-11GB.gguf")
    evidence = read_gguf_evidence(artifact)
    assert evidence.tensor_types == {"blk.0.ffn_gate.weight": 56}
    assert resolve_artifact_quant(artifact, publisher="llmsforall") == "q2_sym32k4"
    assert resolve_artifact_quant(artifact, publisher="LLMSFORALL") == "q2_sym32k4"
    assert is_known_quant("Q2_SYM32K4")
    assert extract_quant_from_text("Millie-Q2-SYM32K4.gguf") == "q2_sym32k4"


@pytest.mark.parametrize("publisher,file_type,tensor_type", [
    ("foreign", 56, 56), (None, 56, 56), ("llmsforall", 56, 1),
    ("llmsforall", 54, 56), ("llmsforall", True, 56),
])
def test_fork_enum_or_filename_does_not_supply_unproven_quant(tmp_path, publisher, file_type, tensor_type):
    artifact = _write_fork_gguf(tmp_path / "Millie-35B-A3B-11GB.gguf", file_type=file_type, tensor_type=tensor_type)
    assert resolve_artifact_quant(artifact, publisher=publisher) is None


def test_filename_quant_remains_precise_when_fork_header_has_other_format(tmp_path):
    artifact = _write_fork_gguf(tmp_path / "Millie-Q6_K.gguf")
    assert resolve_artifact_quant(artifact, publisher="llmsforall") == "q6_k"


def test_naked_unreadable_artifact_and_missing_tensor_evidence_stay_unresolved(tmp_path):
    path = tmp_path / "Millie.gguf"
    assert resolve_artifact_quant(path, publisher="llmsforall") is None
    path.write_bytes(b"GGUF truncated header")
    assert resolve_artifact_quant(path, publisher="llmsforall") is None
    assert quant_from_gguf_evidence("Millie.gguf", publisher="llmsforall", file_type=56, tensor_types={}) is None


def test_tensor_type_evidence_cannot_be_mutated_through_cached_reader(tmp_path):
    artifact = _write_fork_gguf(tmp_path / "Millie.gguf")
    read_gguf_evidence(artifact).tensor_types["blk.0.ffn_gate.weight"] = 1
    assert resolve_artifact_quant(artifact, publisher="llmsforall") == "q2_sym32k4"


def test_local_discovery_and_persisted_binding_preserve_complete_fork_identity(tmp_path):
    artifact = _write_fork_gguf(tmp_path / "llmsforall" / "Millie-35B-A3B-11GB" / "Millie-35B-A3B-11GB.gguf")
    key = "llmsforall/millie-35b-a3b-11gb@q2_sym32k4"
    registry = {key: {"local": {"model_path": str(artifact)}}}
    resolver = LocalModelResolver(tmp_path, registry_loader=lambda: registry)
    candidates = resolver.candidates(registry_only=True)
    assert len(candidates) == 1
    assert candidates[0].registry_key == key
    resolved = resolver.resolve(key)
    assert resolved.quant == "Q2_SYM32K4"
    assert resolved.identity_evidence.identity == key


@pytest.mark.parametrize("publisher,tensor_type,registry_quant", [
    ("foreign", 56, "q2_sym32k4"), ("llmsforall", 1, "q2_sym32k4"), ("llmsforall", 56, "mixed"),
])
def test_persisted_binding_rejects_foreign_unproven_or_wildcard_quant(tmp_path, publisher, tensor_type, registry_quant):
    artifact = _write_fork_gguf(
        tmp_path / publisher / "Millie-35B-A3B-11GB" / "Millie-35B-A3B-11GB.gguf", tensor_type=tensor_type,
    )
    key = f"llmsforall/millie-35b-a3b-11gb@{registry_quant}"
    resolver = LocalModelResolver(tmp_path, registry_loader=lambda: {key: {"local": {"model_path": str(artifact)}}})
    with pytest.raises(ModelResolutionError, match="Identitaet"):
        resolver.resolve(key)


def _fork_inventory(monkeypatch, tmp_path, *, publisher="llmsforall", file_type=56, tensor_type=56, quant="?"):
    models_root = tmp_path / "models"
    artifact = _write_fork_gguf(
        models_root / publisher / "Millie-35B-A3B-11GB" / "Millie-35B-A3B-11GB.gguf",
        file_type=file_type, tensor_type=tensor_type,
    )
    key = f"llmsforall/millie-35b-a3b-11gb@{quant}"
    registry = {key: {"local": {"model_path": str(artifact)}}}
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(yaml.safe_dump(registry), encoding="utf-8")
    monkeypatch.setattr(rt, "REGISTRY_PATH", registry_path)
    monkeypatch.setattr(rt, "MODELS_CACHE", models_root)
    monkeypatch.setattr(rt, "_gguf_roots", lambda: [models_root])
    monkeypatch.setattr(rt, "_read_lms_loaded_models", lambda: None)
    config_root = tmp_path / "configs"
    monkeypatch.setattr(rt, "CONFIG_ROOT", config_root)
    config_path = config_root / artifact.relative_to(models_root).with_suffix(".gguf.json")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({
        "load": {"fields": [{"key": "llm.load.llama.acceleration.offloadRatio", "value": 0.75}]},
    }), encoding="utf-8")
    clear_lms_config_cache()
    lms_models = [{
        "modelKey": "millie-35b-a3b-11gb", "publisher": publisher,
        "path": str(artifact.relative_to(models_root)),
        "indexedModelIdentifier": str(artifact.relative_to(models_root)).replace("\\", "/"),
    }]
    monkeypatch.setattr(rt, "_run_lms_ls", lambda: lms_models)
    inventory = rt.RegistryInventory(registry, lms_models, lms_models, read_lms_configs(config_root), [])
    return inventory, config_path


def test_fill_unknown_quant_then_sync_import_keeps_one_complete_fork_identity(monkeypatch, tmp_path):
    inventory, config_path = _fork_inventory(monkeypatch, tmp_path)
    expected = "llmsforall/millie-35b-a3b-11gb@q2_sym32k4"
    config_before = config_path.read_bytes()

    rt.cmd_fill_quant(lms_models=inventory.lms_models, inventory=inventory)

    assert list(rt.load_registry()) == [expected]
    assert rt.load_registry()[expected]["quants"] == "Q2_SYM32K4"
    inventory.registry = rt.load_registry()
    rt.cmd_sync(inventory=inventory, show_inventory_report=False, import_lms_settings=True)

    result = rt.load_registry()
    assert list(result) == [expected]
    assert result[expected]["offload"] == 0.75
    assert inventory.identity_links[expected].config_paths == (config_path,)
    assert config_path.read_bytes() == config_before


@pytest.mark.parametrize("publisher,file_type,tensor_type,quant", [
    ("foreign", 56, 56, "?"), ("llmsforall", 54, 56, "?"),
    ("llmsforall", 56, 1, "?"), ("llmsforall", 56, 56, "q6_k"),
])
def test_fill_quant_does_not_relabel_known_or_unproven_identity(
    monkeypatch, tmp_path, publisher, file_type, tensor_type, quant,
):
    inventory, _ = _fork_inventory(
        monkeypatch, tmp_path, publisher=publisher, file_type=file_type, tensor_type=tensor_type, quant=quant,
    )
    before = rt.REGISTRY_PATH.read_bytes()

    rt.cmd_fill_quant(lms_models=inventory.lms_models, inventory=inventory)

    assert rt.REGISTRY_PATH.read_bytes() == before


def test_fill_unknown_quant_requires_one_physical_artifact(monkeypatch, tmp_path):
    inventory, _ = _fork_inventory(monkeypatch, tmp_path)
    second_root = tmp_path / "other-models"
    _write_fork_gguf(second_root / "llmsforall" / "Millie-35B-A3B-11GB" / "Millie-35B-A3B-11GB.gguf")
    inventory.gguf_roots = (tmp_path / "models", second_root)
    before = rt.REGISTRY_PATH.read_bytes()

    rt.cmd_fill_quant(lms_models=inventory.lms_models, inventory=inventory)

    assert rt.REGISTRY_PATH.read_bytes() == before
