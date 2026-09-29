"""The executed KV cache pair follows the shared supported-kernel policy."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import pytest

import assemble_blueprint as ab
import registry_tool as rt
from kv_cache_policy import KVCachePolicyError, normalize_kv_pair
from model_registry import ModelRegistry
from providers.llama_cpp_args import build_runtime_args
from providers.lmstudio_provider import LMStudioProvider
from providers.unsloth_server_provider import UnslothServerProvider


@pytest.mark.parametrize("k,v,expected", [
    ("q8_0", "iq4_nl", "q4_0"),
    ("q5_1", "q4_1", "q4_0"),
    ("q8_0", "q5_1", "q8_0"),
    ("f16", "f32", "q8_0"),
    (None, "q5_1", "q4_0"),
])
def test_actual_llama_argument_pair_is_normalized(k, v, expected):
    command = build_runtime_args({"cache_type_k": k, "cache_type_v": v}, environment={})
    assert command[command.index("--cache-type-k") + 1] == expected
    assert command[command.index("--cache-type-v") + 1] == expected


@pytest.mark.parametrize("provider", ["llama_cpp", "unsloth_server", "lmstudio"])
def test_provider_runtime_normalizes_complete_pair_after_explicit_overrides(provider):
    key = "fixture/model@q4_k_m"
    entry = {"k_cache": "q8_0", "v_cache": "q8_0", provider: {
        ("k_cache" if provider == "lmstudio" else "cache_type_k"): "q4_0",
    }}
    runtime = ModelRegistry(lambda: {key: entry}).provider_runtime(key, provider)
    fields = ("k_cache", "v_cache") if provider == "lmstudio" else ("cache_type_k", "cache_type_v")
    assert tuple(runtime[field] for field in fields) == ("q4_0", "q4_0")
    assert entry["k_cache"] == "q8_0"  # The read boundary stays pure.


def test_save_registry_normalizes_pair_and_keeps_other_fields(tmp_path):
    path = tmp_path / "registry.yaml"
    entry = {"k_cache": "q5_1", "v_cache": "q4_1", "context_length": 16384, "notes": "keep"}
    rt.save_registry({"fixture/model@q4_k_m": entry}, path)
    saved = rt.load_registry(path)["fixture/model@q4_k_m"]
    assert (saved["k_cache"], saved["v_cache"]) == ("q4_0", "q4_0")
    assert saved["context_length"] == 16384
    assert saved["notes"] == "keep"


def test_json_reader_normalizes_pair_before_import_without_writing_source(tmp_path):
    path = tmp_path / "publisher/model/model-Q4_K_M.gguf.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"load": {"fields": [
        {"key": "llm.load.llama.kCacheQuantizationType", "value": {"checked": True, "value": "q8_0"}},
        {"key": "llm.load.llama.vCacheQuantizationType", "value": {"checked": True, "value": "q4_nl"}},
    ]}}), encoding="utf-8")
    before = path.read_bytes()
    ab.clear_lms_config_cache()
    configs = ab.read_lms_configs(tmp_path)
    assert len(configs) == 1
    assert (configs[0]["k_cache"], configs[0]["v_cache"]) == ("q4_0", "q4_0")
    assert path.read_bytes() == before


def test_actual_unsloth_argument_pair_is_normalized():
    provider = UnslothServerProvider("http://fixture/v1", runtime_loader=lambda _key: {
        "cache_type_k": "q8_0", "cache_type_v": "q4_0",
    })
    command = provider._runtime_args("fixture/model@q4_k_m")
    assert command[command.index("--cache-type-k") + 1] == "q4_0"
    assert command[command.index("--cache-type-v") + 1] == "q4_0"


def test_unsloth_server_emits_explicit_q8_pair_when_registry_has_no_cache_policy():
    provider = UnslothServerProvider("http://fixture/v1", runtime_loader=lambda _key: {})
    command = provider._runtime_args("fixture/model@q4_k_m")
    assert command[command.index("--cache-type-k") + 1] == "q8_0"
    assert command[command.index("--cache-type-v") + 1] == "q8_0"


@pytest.mark.parametrize("k,v,expected", [
    ("q5_1", "q5_1", "q4_0"), ("q5_1", "q4_1", "q4_0"),
    ("q5_1", "q4_0", "q4_0"), ("q5_0", "q4_0", "q4_0"),
    ("q8_0", "q5_1", "q8_0"), ("q8_0", "q4_0", "q4_0"),
    ("q8_0", "q4_1", "q8_0"), ("q8_0", "q5_0", "q8_0"),
    ("q5_1", "q4_nl", "q4_0"), ("q4_0", "q4_0", "q4_0"),
    (" Q8-0 ", "Q8_0", "q8_0"), ("fp16", "q4_0", "q8_0"),
    ("f32", "iq4_nl", "q8_0"), ("bf16", "q5_1", "q8_0"),
    (None, "q8_0", "q8_0"), ("iq4_nl", None, "q4_0"),
    ({"checked": False, "value": "q4_0"}, "q4_0", "q8_0"),
])
def test_shared_policy_bit_sum_tie_aliases_missing_and_checkbox(k, v, expected):
    assert normalize_kv_pair(k, v) == (expected, expected)
    assert normalize_kv_pair(v, k) == (expected, expected)
    assert normalize_kv_pair(expected, expected) == (expected, expected)


@pytest.mark.parametrize("bad", [True, False, 4, "", "q6_k", "unknown", {}, {"checked": "false", "value": "q8_0"}])
def test_invalid_explicit_values_fail_closed(bad):
    with pytest.raises(KVCachePolicyError):
        normalize_kv_pair("q8_0", bad)
    with pytest.raises(KVCachePolicyError):
        build_runtime_args({"cache_type_k": bad, "cache_type_v": "q8_0"})


def test_missing_pair_defaults_to_executable_q8_pair_everywhere():
    assert normalize_kv_pair() == (None, None)
    command = build_runtime_args({})
    assert command[command.index("--cache-type-k") + 1] == "q8_0"
    assert command[command.index("--cache-type-v") + 1] == "q8_0"
    assert rt._default_ctx_from_size(9_500_000_000, 4) == 24576
    data = {"operation": {"fields": [{"key": "user", "value": "keep"}]}}
    before = deepcopy(data)
    assert ab.apply_kv_cache_fields(data) is False
    assert data == before


def test_targeted_json_helper_preserves_every_non_kv_value_and_is_idempotent():
    data = {"operation": {"fields": [{"key": "llm.prediction.systemPrompt", "value": "user prompt"}]},
            "load": {"fields": [
                {"key": "llm.load.contextLength", "value": 16384},
                {"key": "llm.load.llama.kCacheQuantizationType", "value": {"checked": False, "value": "f16"}},
            ]}, "custom": {"nested": [1, 2, 3]}}
    before = deepcopy(data)
    assert ab.apply_kv_cache_fields(data, "q5_1", "iq4_nl") is True
    assert data["operation"] == before["operation"]
    assert data["custom"] == before["custom"]
    assert data["load"]["fields"][0] == before["load"]["fields"][0]
    values = {field["key"]: field["value"] for field in data["load"]["fields"]}
    for side in ("k", "v"):
        assert values[f"llm.load.llama.{side}CacheQuantizationType"] == {"checked": True, "value": "q4_0"}
    assert ab.apply_kv_cache_fields(data, "q4_0", "q4_0") is False


def test_assembly_emits_q8_default_pair_when_registry_policy_is_missing():
    data = {"load": {"fields": [{"key": "llm.load.contextLength", "value": 16384}]}}
    assert ab.apply_kv_cache_fields(data) is True
    values = {field["key"]: field["value"] for field in data["load"]["fields"]}
    for side in ("k", "v"):
        assert values[f"llm.load.llama.{side}CacheQuantizationType"] == {
            "checked": True,
            "value": "q8_0",
        }


def test_invalid_registry_pair_never_changes_existing_file_or_other_entries(tmp_path):
    path = tmp_path / "registry.yaml"
    path.write_text("original registry\n", encoding="utf-8")
    registry = {"valid/model@q4_k_m": {"k_cache": "q5_1", "v_cache": "q5_1"},
                "invalid/model@q4_k_m": {"k_cache": "q8_0", "v_cache": "bad"}}
    before = deepcopy(registry)
    with pytest.raises(KVCachePolicyError):
        rt.save_registry(registry, path)
    assert path.read_text() == "original registry\n"
    assert registry == before


def test_preset_normalizes_retained_global_and_manual_sections_only():
    existing = "[*]\ncache-type-k = q8_0\ncache-type-v = q4_0\nparallel = 4\n\n[manual]\nhf = owner/model\ncache-type-k = fp16\ncache-type-v = fp16\ncustom = keep\n"
    result = rt.merge_llama_preset(existing, "")
    assert "parallel = 4" in result
    assert "hf = owner/model" in result
    assert "custom = keep" in result
    assert result.count("cache-type-k = q4_0") == 1
    assert result.count("cache-type-v = q4_0") == 1
    assert result.count("cache-type-k = q8_0") == 1
    assert result.count("cache-type-v = q8_0") == 1
    assert rt.normalize_llama_preset(result) == result


def test_preset_emits_q8_default_pair_when_registry_policy_is_missing(monkeypatch):
    monkeypatch.setattr(rt, "_resolve_model_path_multi", lambda _key, _entry: "C:/models/model.gguf")
    content, skipped = rt.build_llama_preset({"fixture/model@q4_k_m": {}})
    assert skipped == []
    assert "cache-type-k = q8_0" in content
    assert "cache-type-v = q8_0" in content


def test_preset_unknown_manual_cache_fails_before_atomic_write(tmp_path, monkeypatch):
    path = tmp_path / "preset.ini"
    path.write_text("[*]\ncache-type-k = invalid\ncache-type-v = q8_0\n", encoding="utf-8")
    before = path.read_bytes()
    monkeypatch.setattr(rt, "load_registry", lambda: {})
    assert rt.cmd_export_llama_preset(path, merge_existing=True) == 1
    assert path.read_bytes() == before


def test_context_estimate_uses_the_pair_that_will_execute():
    # q8/q5.5 normalizes to q8/q8; q5.5/q4.5 normalizes to q4/q4.
    assert rt._default_ctx_from_size(10_500_000_000, 4, "q8_0", "q5_1") == rt._default_ctx_from_size(
        10_500_000_000, 4, "q8_0", "q8_0"
    )
    assert rt._default_ctx_from_size(9_500_000_000, 4, "q5_1", "q4_1") == 49152


def test_fill_ctx_estimates_missing_pair_using_explicit_q8_runtime_default(tmp_path, monkeypatch):
    path = tmp_path / "registry.yaml"
    path.write_text(
        "fixture/model@q4_k_m:\n  file_size_bytes: 9500000000\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(rt, "REGISTRY_PATH", path)
    rt.cmd_fill_ctx()
    entry = rt.load_registry(path)["fixture/model@q4_k_m"]
    assert entry["context_length"] == 24576


def test_fmt_normalizes_registry_pairs_through_atomic_writer(tmp_path, monkeypatch):
    path = tmp_path / "registry.yaml"
    path.write_text(
        "fixture/model@q4_k_m:\n  k_cache: q5_1\n  v_cache: iq4_nl\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(rt, "REGISTRY_PATH", path)
    rt.cmd_fmt()
    entry = rt.load_registry(path)["fixture/model@q4_k_m"]
    assert (entry["k_cache"], entry["v_cache"]) == ("q4_0", "q4_0")


def test_fmt_rejects_non_mapping_registry_without_overwriting(tmp_path, monkeypatch):
    path = tmp_path / "registry.yaml"
    original = "[]\n"
    path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(rt, "REGISTRY_PATH", path)
    with pytest.raises(ValueError, match="root must be a mapping"):
        rt.cmd_fmt()
    assert path.read_text(encoding="utf-8") == original


def _native_kv_provider(
    effective: dict[str, Any] | None,
    *,
    echo: dict[str, Any] | None = None,
    status: str = "loaded",
) -> tuple[LMStudioProvider, list[dict[str, Any]], str]:
    key = "publisher/model@q4_k_m"
    registry = ModelRegistry(lambda: {key: {"k_cache": "q8_0", "v_cache": "iq4_nl"}})
    calls = []
    def request(endpoint: str, **kwargs: Any) -> dict[str, Any]:
        if endpoint.endswith("/load"):
            calls.append(kwargs["data"])
            return {"status": status, "instance_id": "session", "load_config": echo}
        return {"models": [{"key": key, "loaded_instances": [{"id": "session", "config": effective}]}]}
    provider = LMStudioProvider("http://fixture/v1", rest_request=request,
                               runtime_loader=lambda key: registry.provider_runtime(key, "lmstudio"))
    return provider, calls, key


@pytest.mark.parametrize("effective,valid,verified", [
    (None, True, False), ({}, True, False),
    ({"k_cache": "q4_0", "v_cache": "q4_0"}, True, True),
    ({"k_cache": "q4_0"}, True, False),
    ({"k_cache": "q8_0", "v_cache": "q4_0"}, False, False),
    ({"k_cache": "q5_1", "v_cache": "iq4_nl"}, False, False),
    ({"k_cache": "q8_0", "v_cache": "q8_0"}, False, False),
    ({"k_cache": "f16", "v_cache": "f16"}, False, False),
    ({"k_cache": True, "v_cache": "q4_0"}, False, False),
])
@pytest.mark.parametrize("status", ["loaded", "error"])
def test_native_load_and_reuse_check_only_available_effective_kv(effective, valid, verified, status):
    provider, calls, key = _native_kv_provider(effective, status=status)
    assert provider.load_model(key) == ((True, "session") if valid else (False, None))
    assert calls == [{"model": key, "echo_load_config": True}]
    current = provider.current_model()
    assert current["kv_cache_verified"] is verified
    if not valid:
        assert current["runtime_matches"] is False


def test_native_contradictory_echo_cannot_overrule_bound_instance():
    provider, _, key = _native_kv_provider({"k_cache": "q8_0", "v_cache": "q4_0"},
                                         echo={"k_cache": "q4_0", "v_cache": "q4_0"})
    assert provider.load_model(key) == (False, None)
