"""Sync must migrate and retain only full, current artifact evidence."""

import hashlib
import json

import pytest

import registry_tool as rt
from gguf_evidence import read_gguf_evidence
from tests.gguf_fixture import write_gguf
from inventory import IdentityLink, RuntimeBinding
from model_identity import ArtifactIdentityEvidence


@pytest.mark.parametrize("files, expected", [
    ([("wanted", "Q6_K")], "wanted/model@q6_k"),
    ([("foreign", "Q4_K_M")], None),
    ([("wanted", "Q6_K"), ("wanted", "Q4_K_M")], None),
    ([], None),
])
def test_fill_quant_requires_unique_full_artifact_identity(tmp_path, monkeypatch, files, expected):
    for publisher, quant in files:
        write_gguf(tmp_path / publisher / "model-GGUF" / f"model-{quant}.gguf")
    registry = {"wanted/model": {"publisher": "wanted", "context_length": 123}}
    saved = []
    monkeypatch.setattr(rt, "MODELS_CACHE", tmp_path)
    monkeypatch.setattr(rt, "load_registry", lambda: registry)
    monkeypatch.setattr(rt, "save_registry", lambda value: saved.append(value))
    models = [{"modelKey": "model", "publisher": publisher,
               "quantization": {"name": quant},
               "path": str(tmp_path / publisher / "model-GGUF" / f"model-{quant}.gguf")}
              for publisher, quant in files]
    rt.cmd_fill_quant(lms_models=models)
    if expected:
        assert list(registry) == [expected]
        assert registry[expected]["context_length"] == 123
        assert len(saved) == 1
    else:
        assert list(registry) == ["wanted/model"]
        assert saved == []


@pytest.mark.parametrize("change", [None, "fingerprint", "method", "path"])
def test_sync_retains_pairing_only_for_current_unchanged_bundle(tmp_path, monkeypatch, change):
    main, helper = tmp_path / "main.gguf", tmp_path / "helper.gguf"
    write_gguf(main)
    write_gguf(helper, architecture="dflash", helper="dflash")
    proof = tmp_path / "pairing.json"
    raw = json.dumps({
        "method": "dflash", "main_path": str(main), "companion_path": str(helper),
        "main_fingerprint": read_gguf_evidence(main).fingerprint,
        "companion_fingerprint": read_gguf_evidence(helper).fingerprint,
        "validation": {"status": "passed", "check": "speculative_pairing",
                       "provider": "llama_cpp", "source": "fixture-successful-run.json"},
    }).encode()
    proof.write_bytes(raw)
    pairing = {"evidence_path": str(proof), "evidence_sha256": hashlib.sha256(raw).hexdigest()}
    profile = {"type": "draft", "method": "dflash", "pairing": pairing}
    registry = {"owner/model@q6_k": {"local": {
        "model_path": str(main), "companions": {"draft": str(helper)},
        "llama_cpp": {"speculative": profile},
    }}}
    new_method = "dspark" if change == "method" else "dflash"
    if change == "fingerprint":
        write_gguf(helper, architecture="dflash", helper="dflash", metadata={"general.name": "modified"})
    if change == "path":
        new_helper = tmp_path / "different-helper.gguf"
        new_helper.write_bytes(helper.read_bytes())
        helper = new_helper
    binding = RuntimeBinding(config_path=tmp_path / "config.json", speculative=(
        ("type", "draft"), ("method", new_method), ("draft_model_reference", str(helper)),
    ))
    inventory = rt.RegistryInventory(registry, [], [], [], [])
    inventory.identity_links["owner/model@q6_k"] = IdentityLink(
        registry_key="owner/model@q6_k", runtime_bindings=(binding,),
        artifact_evidence=(ArtifactIdentityEvidence.from_reference(main, "owner/model", "q6_k"),),
    )
    monkeypatch.setattr(rt, "_resolve_local_companion", lambda _: helper)
    monkeypatch.setattr(rt, "save_registry", lambda _: None)
    rt._materialize_local_bindings(inventory)
    local = registry["owner/model@q6_k"]["local"]
    if change is None:
        assert local["llama_cpp"]["speculative"]["pairing"] == pairing
        assert local["companions"]["draft"] == str(helper)
    else:
        assert "pairing" not in local["llama_cpp"]["speculative"]
        assert "draft" not in local["companions"]


def test_saved_snapshot_limits_scanning_to_verified_roots(tmp_path, monkeypatch):
    roots = tmp_path / "primary", tmp_path / "fallback"
    files = []
    for root in roots:
        file = root / "owner" / "model-GGUF" / "model-Q6_K.gguf"
        write_gguf(file)
        files.append(file)
    snapshot, models = tmp_path / "files.txt", tmp_path / "models.json"
    snapshot.write_text(str(files[0]), encoding="utf-8")
    models.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(rt, "_gguf_roots", lambda: roots)
    monkeypatch.setattr(rt, "load_registry", lambda: {})
    monkeypatch.setattr(rt, "read_lms_configs", lambda _: [])
    inventory = rt._collect_registry_inventory(models, snapshot)
    candidates = rt._ensure_gguf_inventory(inventory)
    assert inventory.gguf_roots == (roots[0],)
    assert [candidate.path for candidate in candidates] == [files[0]]
