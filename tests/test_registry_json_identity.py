"""Generation extras may cross the JSON boundary only through an IdentityLink."""

import json
from pathlib import Path

import pytest

import benchmark_config as bc
from assemble_blueprint import clear_lms_config_cache


def _config(path: Path, *, top_k: int = 77) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "operation": {
                    "fields": [
                        {"key": "llm.prediction.topKSampling", "value": top_k},
                        {"key": "llm.prediction.reasoning.enableThinking", "value": True},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def config_root(tmp_path, monkeypatch):
    root = tmp_path / "configs"
    root.mkdir()
    monkeypatch.setattr(bc, "LMS_CONFIG_ROOT", root)
    bc._LMS_INDEX_CACHE.clear()
    bc._LMS_JSON_CACHE.clear()
    clear_lms_config_cache()
    return root


def _bound_registry(tmp_path: Path, config_root: Path, *, publisher="publisher-a", quant="Q6_K"):
    model_path = tmp_path / "models" / publisher / "Model-GGUF" / f"Model-{quant}.gguf"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_bytes(b"GGUF fixture")
    config_path = config_root / publisher / "Model-GGUF" / f"Model-{quant}.gguf.json"
    _config(config_path)
    return {
        "publisher-a/model@q6_k": {
            "local": {"model_path": str(model_path), "config_path": str(config_path)}
        }
    }, config_path


def test_json_index_includes_every_active_quant_variant(config_root):
    first = config_root / "publisher-a" / "Model-GGUF" / "Model-Q4_K_M.gguf.json"
    second = first.with_name("Model-Q6_K.gguf.json")
    _config(first)
    _config(second)
    _config(config_root / "_quarantine_old" / "Model-GGUF" / second.name)

    assert {entry["json_path"] for entry in bc._lms_index()} == {first, second}


def test_generation_extras_require_a_verified_config_binding(config_root, monkeypatch):
    _config(config_root / "publisher-b" / "Model-GGUF" / "Model-Q4_K_M.gguf.json")
    monkeypatch.setattr(bc, "_load_quant_registry", lambda: {"publisher-a/model@q6_k": {}})

    assert bc._lms_generation_config("publisher-a/model@q6_k") is None


def test_generation_extras_use_only_the_bound_config(tmp_path, config_root, monkeypatch):
    registry, config_path = _bound_registry(tmp_path, config_root)
    _config(config_path.with_name("Model-Q4_K_M.gguf.json"), top_k=13)
    monkeypatch.setattr(bc, "_load_quant_registry", lambda: registry)

    assert bc._lms_generation_config("publisher-a/model@q6_k") == {
        "top_k": 77,
        "enable_thinking": True,
    }


@pytest.mark.parametrize("requested", ["publisher-b/model@q6_k", "publisher-a/model@q4_k_m", "publisher-a/model"])
def test_request_must_preserve_the_complete_registry_identity(tmp_path, config_root, monkeypatch, requested):
    registry, _ = _bound_registry(tmp_path, config_root)
    monkeypatch.setattr(bc, "_load_quant_registry", lambda: registry)

    assert bc._lms_generation_config(requested) is None


def test_stale_declared_pair_cannot_fall_back_to_another_json(tmp_path, config_root, monkeypatch):
    registry, config_path = _bound_registry(tmp_path, config_root)
    registry["publisher-a/model@q6_k"]["local"]["config_path"] = str(config_path.with_name("missing.gguf.json"))
    monkeypatch.setattr(bc, "_load_quant_registry", lambda: registry)

    assert bc._lms_generation_config("publisher-a/model@q6_k") is None


def test_reused_local_config_is_not_generation_evidence(tmp_path, config_root, monkeypatch):
    registry, _ = _bound_registry(tmp_path, config_root)
    registry["publisher-b/model@q6_k"] = registry["publisher-a/model@q6_k"]
    monkeypatch.setattr(bc, "_load_quant_registry", lambda: registry)

    assert bc._lms_generation_config("publisher-a/model@q6_k") is None


@pytest.mark.parametrize("publisher,quant", [("publisher-b", "Q6_K"), ("publisher-a", "Q4_K_M")])
def test_declared_pair_must_belong_to_the_registry_identity(tmp_path, config_root, monkeypatch, publisher, quant):
    registry, _ = _bound_registry(tmp_path, config_root, publisher=publisher, quant=quant)
    monkeypatch.setattr(bc, "_load_quant_registry", lambda: registry)

    assert bc._lms_generation_config("publisher-a/model@q6_k") is None


@pytest.mark.parametrize("requested", ["publisher-a/other-model@q6_k", "publisher-a/model-qat@q6_k"])
def test_persisted_config_cannot_relabel_the_model_component(tmp_path, config_root, monkeypatch, requested):
    registry, _ = _bound_registry(tmp_path, config_root)
    entry = registry.pop("publisher-a/model@q6_k")
    registry[requested] = entry
    monkeypatch.setattr(bc, "_load_quant_registry", lambda: registry)
    assert bc._lms_generation_config(requested) is None
