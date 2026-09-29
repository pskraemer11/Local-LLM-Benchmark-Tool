"""Identity contracts exercised through real miniature GGUF files and YAML."""
import struct
from pathlib import Path

import pytest
import yaml

import registry_tool as rt
from model_identity import Unmatched, resolve_registry_match
from model_registry import ModelRegistry


def write_gguf(path: Path, *, layers=12, dimension=256, context=8192, template="chat"):
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "general.architecture": "llama",
        "llama.block_count": layers,
        "llama.embedding_length": dimension,
        "llama.context_length": context,
        "tokenizer.chat_template": template,
    }
    data = bytearray(struct.pack("<4sIQQ", b"GGUF", 3, 0, len(metadata)))
    for key, value in metadata.items():
        encoded = key.encode()
        data += struct.pack("<Q", len(encoded)) + encoded
        if isinstance(value, str):
            encoded = value.encode()
            data += struct.pack("<IQ", 8, len(encoded)) + encoded
        else:
            data += struct.pack("<II", 4, value)
    path.write_bytes(data)
    return path


@pytest.mark.parametrize("requested_id", ["vendor/model@q6_k", "model@q6_k", "vendor/model-qat@q6_k"])
def test_requested_quant_never_falls_back(requested_id):
    assert isinstance(resolve_registry_match(requested_id, ["vendor/model@q4_k_m"]), Unmatched)


def test_registry_resolve_cannot_change_requested_quant(tmp_path):
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump({"vendor/model@q4_k_m": {"n_layers": 12}}), encoding="utf-8")
    assert ModelRegistry(lambda: rt.load_registry(path)).resolve("vendor/model@q6_k") is None


def setup_registry(monkeypatch, tmp_path, entries):
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump(entries), encoding="utf-8")
    monkeypatch.setattr(rt, "REGISTRY_PATH", path)
    monkeypatch.setattr(rt, "MODELS_CACHE", tmp_path / "models")
    monkeypatch.setattr(rt, "_run_lms_ls", lambda: [])
    return path


def test_header_sync_updates_two_quantizations_independently(monkeypatch, tmp_path):
    first = "vendor/model@q4_k_m"
    second = "vendor/model@q6_k"
    path = setup_registry(monkeypatch, tmp_path, {first: {}, second: {}})
    write_gguf(tmp_path / "models/vendor/Model-GGUF/Model-Q4_K_M.gguf", layers=12, context=8192)
    write_gguf(tmp_path / "models/vendor/Model-GGUF/Model-Q6_K.gguf", layers=24, context=16384)
    rt.cmd_sync_from_gguf()
    result = rt.load_registry(path)
    assert result[first]["n_layers"] == 12
    assert result[second]["n_layers"] == 24
    assert result[second]["max_context_length"] == 16384
    assert rt._gguf_drift_errors(result) == []


@pytest.mark.parametrize("other_publisher,other_quant", [("foreign", "Q6_K"), ("vendor", "Q4_K_M")])
def test_header_sync_rejects_foreign_identity(monkeypatch, tmp_path, other_publisher, other_quant):
    key = "vendor/model@q6_k"
    path = setup_registry(monkeypatch, tmp_path, {key: {"n_layers": 99}})
    artifact = write_gguf(tmp_path / f"models/{other_publisher}/Model-GGUF/Model-{other_quant}.gguf")
    models = [{"modelKey": f"{other_publisher}/model", "path": str(artifact)}]
    rt.cmd_sync_from_gguf(lms_models=models)
    assert rt.load_registry(path)[key] == {"n_layers": 99}
    assert rt._gguf_drift_errors(rt.load_registry(path)) == []


def test_ambiguous_physical_artifacts_do_not_sync(monkeypatch, tmp_path):
    key = "vendor/model@q6_k"
    path = setup_registry(monkeypatch, tmp_path, {key: {"n_layers": 99}})
    write_gguf(tmp_path / "models/vendor/Model-GGUF/Model-Q6_K.gguf")
    write_gguf(tmp_path / "models/vendor/Model-GGUF/Model-other-Q6_K.gguf", layers=24)
    rt.cmd_sync_from_gguf()
    assert rt.load_registry(path)[key] == {"n_layers": 99}


def test_fill_reasoning_persists_missing_field_after_architecture_was_filled(monkeypatch, tmp_path):
    key = "vendor/neutral@q6_k"
    path = setup_registry(monkeypatch, tmp_path, {key: {"n_layers": 12, "hidden_dim": 256}})
    write_gguf(tmp_path / "models/vendor/Neutral-GGUF/Neutral-Q6_K.gguf", template="{% if enable_thinking %}<think>{% endif %}")
    rt.cmd_fill_arch()
    assert "reasoning" not in rt.load_registry(path)[key]
    rt.cmd_fill_reasoning()
    assert rt.load_registry(path)[key]["reasoning"] == "thinking"
    rt.cmd_fill_reasoning()
    assert rt.load_registry(path)[key]["reasoning"] == "thinking"


@pytest.mark.parametrize("candidate", ["foreign/model@q6_k", "vendor/model-qat@q6_k", "vendor/model-instruct@q6_k"])
def test_full_identity_never_crosses_publisher_or_variant(candidate):
    assert isinstance(resolve_registry_match("vendor/model@q6_k", [candidate]), Unmatched)


@pytest.mark.parametrize("folder,filename", [
    ("vendor/Model-GGUF", "Model-Q4_K_M.gguf"),
    ("foreign/Model-GGUF", "Model-Q6_K.gguf"),
    ("vendor/Model-QAT-GGUF", "Model-Q6_K.gguf"),
])
def test_persisted_path_does_not_relabel_artifact(tmp_path, folder, filename):
    from local_model_resolver import LocalModelResolver, ModelResolutionError

    key = "vendor/model@q6_k"
    artifact = write_gguf(tmp_path / folder / filename)
    resolver = LocalModelResolver(tmp_path, registry_loader=lambda: {key: {"local": {"model_path": str(artifact)}}})
    with pytest.raises(ModelResolutionError, match="Identitaet"):
        resolver.resolve(key)


def test_header_missing_template_is_unknown_and_metadata_order_is_irrelevant(tmp_path):
    from tests.gguf_fixture import write_gguf as write_complete_gguf

    path = tmp_path / "Model-Q6_K.gguf"
    write_complete_gguf(path, architecture="qwen3moe", metadata={
        "qwen3moe.context_length": 8192,
        "tokenizer.chat_template": "chat",
        "qwen3moe.expert_count": 64,
    })
    assert rt._read_gguf_header_details(str(path))[4] == 64
    write_complete_gguf(path, architecture="qwen3moe")
    assert rt._read_gguf_header_details(str(path))[2] is None


def test_custom_model_selection_uses_full_identity(monkeypatch):
    from types import SimpleNamespace
    import custom_benchmark as cb

    monkeypatch.setattr(cb, "get_available_models", lambda **_kwargs: [{
        "key": "publisher-a/model@q6_k", "registry_key": "publisher-a/model@q6_k", "display": "A",
    }])
    with pytest.raises(SystemExit) as caught:
        cb._resolve_models(SimpleNamespace(model_key="publisher-b/model@q6_k"))
    assert caught.value.code == 1
