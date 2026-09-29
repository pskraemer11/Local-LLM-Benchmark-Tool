"""Explicit user policy survives sync and reaches the derived provider files."""

import json
import os

import pytest
import yaml

import assemble_blueprint as ab
import benchmark_config as bc
import registry_tool as rt
from inventory import IdentityLink, RuntimeBinding
from model_identity import ArtifactIdentityEvidence
from model_registry import ModelRegistry
from runtime_policy import reasoning_request_kwargs
from speculative import lms_speculative_values, registry_speculative_policy
from tests.gguf_fixture import write_gguf


@pytest.mark.parametrize("policy", ["disabled", "registry"])
def test_explicit_companion_policy_survives_lms_sync(tmp_path, monkeypatch, policy):
    main = tmp_path / "owner/model/model-Q6_K.gguf"
    write_gguf(main)
    profile = {"type": "draft", "method": "dspark"}
    local = {"model_path": str(main), "llama_cpp": {"speculative": profile.copy()},
             "companions": {"draft": "old-helper.gguf", "mmproj": "vision.gguf"}}
    entry = {"speculative_policy": policy, "local": local}
    key = "owner/model@q6_k"
    inventory = rt.RegistryInventory({key: entry}, [], [], [], [])
    inventory.identity_links[key] = IdentityLink(
        key, artifact_evidence=(ArtifactIdentityEvidence.from_reference(main, "owner/model", "q6_k"),),
        runtime_bindings=(RuntimeBinding(config_path=tmp_path / "config.json", speculative=(
            ("type", "mtp"), ("mode", "separate"), ("draft_model_reference", "foreign-helper.gguf"),
        )),),
    )
    monkeypatch.setattr(rt, "save_registry", lambda _: None)
    rt._materialize_local_bindings(inventory)
    assert local["companions"]["mmproj"] == "vision.gguf"
    if policy == "disabled":
        assert "speculative" not in local["llama_cpp"]
        assert "draft" not in local["companions"]
        runtime = ModelRegistry(registry_loader=lambda: {key: entry}).provider_runtime(key, "llama_cpp")
        assert runtime["spec_type"] == "none"
        assert "draft_model_path" not in runtime
    else:
        assert local["llama_cpp"]["speculative"] == profile
        assert local["companions"]["draft"] == "old-helper.gguf"


@pytest.mark.parametrize("policy", ["unknown", {}, True])
def test_unknown_companion_policy_blocks(policy):
    with pytest.raises(ValueError, match="speculative_policy"):
        registry_speculative_policy({"speculative_policy": policy})
    assert rt._registry_local_bundle_errors({"vendor/model@q6_k": {"speculative_policy": policy}})["companion"]


def test_classification_preserves_registry_owned_blueprint(tmp_path, monkeypatch):
    registry = tmp_path / "registry.yaml"
    registry.write_text(yaml.safe_dump({"vendor/muse@q6_k": {
        "reasoning": "thinking", "blueprint": "muse_reasoning_low", "blueprint_policy": "registry",
    }}), encoding="utf-8")
    monkeypatch.setattr(ab, "REGISTRY_PATH", registry)
    monkeypatch.setattr(ab, "read_lms_configs", lambda _: [])
    ab.classify_registry()
    entry = yaml.safe_load(registry.read_text())["vendor/muse@q6_k"]
    assert entry["blueprint"] == "muse_reasoning_low"


def test_invalid_explicit_blueprint_leaves_registry_intact(tmp_path, monkeypatch):
    registry = tmp_path / "registry.yaml"
    registry.write_text(yaml.safe_dump({"vendor/muse@q6_k": {
        "blueprint": "typo", "blueprint_policy": "registry",
    }}), encoding="utf-8")
    before = registry.read_bytes()
    monkeypatch.setattr(ab, "REGISTRY_PATH", registry)
    monkeypatch.setattr(ab, "read_lms_configs", lambda _: [])
    with pytest.raises(ValueError, match="Invalid explicit blueprint"):
        ab.classify_registry()
    assert registry.read_bytes() == before


@pytest.mark.parametrize("profile,role,field", [
    ({"type": "mtp", "mode": "separate"}, "mtp", "draft_mtp_sidecar"),
    ({"type": "draft", "method": "dspark"}, "draft", "draft_dspark_sidecar"),
    ({"type": "draft", "method": "dflash"}, "draft", "draft_dflash_sidecar"),
    ({"type": "draft", "method": "simple"}, "draft", "draft_simple"),
])
def test_registry_companion_values_select_only_one_algorithm(profile, role, field):
    values = lms_speculative_values({"speculative_policy": "registry", "local": {
        "llama_cpp": {"speculative": profile}, "companions": {role: "helper.gguf"},
    }})
    assert values[field] is True
    assert sum(v is True for v in values.values()) == 1
    assert values["draft_model_reference"] == "helper.gguf"


def test_assembly_disables_all_saved_lms_drafter_flags(tmp_path, monkeypatch):
    key = "vendor/model@q6_k"
    registry = tmp_path / "registry.yaml"
    registry.write_text(yaml.safe_dump({key: {"speculative_policy": "disabled", "blueprint": "default_chat"}}), encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"load": {"fields": [
        {"key": "llm.load.llama.speculativeDecoding.draftMtp", "value": True},
        {"key": "llm.load.llama.speculativeDecoding.draftModel", "value": "old-helper.gguf"},
    ]}}), encoding="utf-8")
    monkeypatch.setattr(ab, "REGISTRY_PATH", registry)
    monkeypatch.setattr(ab, "read_lms_configs", lambda _: [{"publisher": "vendor", "json_path": config}])
    link = IdentityLink(key, runtime_bindings=(RuntimeBinding(config_path=config),))
    ab.assemble_prompts(preview_only=False, identity_links={key: link})
    fields = {f["key"]: f["value"] for f in json.loads(config.read_text())["load"]["fields"]}
    assert fields["llm.load.llama.speculativeDecoding.draftModel"] == ""
    for suffix in ("draftMtp", "draftSimple", "draftDflashSidecar", "draftDsparkSidecar", "draftMtpSidecar"):
        assert fields[f"llm.load.llama.speculativeDecoding.{suffix}"] is False


def test_muse_blueprint_limits_reach_lms_and_request_kwargs(tmp_path, monkeypatch):
    key = "vendor/muse@q6_k"
    entry = {"publisher": "vendor", "reasoning": "thinking", "blueprint": "muse_reasoning_low",
             "template_policy": "explicit_file", "template": "muse.jinja"}
    blueprint = yaml.safe_load(ab.BLUEPRINT_PATH.read_text(encoding="utf-8"))["blueprints"]["muse_reasoning_low"]
    registry, blueprints = tmp_path / "registry.yaml", tmp_path / "blueprints.yaml"
    registry.write_text(yaml.safe_dump({key: entry}), encoding="utf-8")
    blueprints.write_text(yaml.safe_dump({"blueprints": {"muse_reasoning_low": blueprint}, "modules": {}}), encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"operation": {"fields": [
        {"key": "llm.prediction.maxPredictedTokens", "value": {"checked": False, "value": -1}},
        {"key": "llm.prediction.reasoning.budgetTokens", "value": {"checked": True, "value": 0}},
    ]}}), encoding="utf-8")
    (tmp_path / "muse.jinja").write_text("{{ reasoning_strength }}", encoding="utf-8")
    monkeypatch.setattr(ab, "REGISTRY_PATH", registry)
    monkeypatch.setattr(ab, "BLUEPRINT_PATH", blueprints)
    monkeypatch.setattr(ab, "TEMPLATE_DIR", tmp_path)
    monkeypatch.setattr(ab, "read_lms_configs", lambda _: [{"publisher": "vendor", "json_path": config}])
    link = IdentityLink(key, runtime_bindings=(RuntimeBinding(config_path=config),))
    ab.assemble_prompts(preview_only=False, identity_links={key: link})
    fields = {field["key"]: field["value"] for field in json.loads(config.read_text())["operation"]["fields"]}
    assert fields["llm.prediction.maxPredictedTokens"] == {"checked": True, "value": 8192}
    assert fields["llm.prediction.reasoning.budgetTokens"] == {"checked": True, "value": 512}
    assert "Keep reasoning brief" in fields["llm.prediction.systemPrompt"]
    monkeypatch.setattr(bc, "_load_quant_registry", lambda: {key: entry})
    monkeypatch.setattr(bc, "_blueprint_features", lambda _: {
        "template": "muse.jinja", "benchmark_runtime": blueprint["benchmark_runtime"],
    })
    monkeypatch.setattr(bc, "_TEMPLATE_ROOT", tmp_path)
    monkeypatch.setattr(bc, "_lms_generation_config", lambda _: {})
    request_policy = bc.get_model_config(key)
    assert request_policy["max_tokens"] == 8192
    assert reasoning_request_kwargs(request_policy) == {"reasoning_strength": "low"}


def test_preset_keeps_disabled_speculation_and_explicit_template(tmp_path, monkeypatch):
    main = tmp_path / "model-Q6_K.gguf"
    write_gguf(main)
    registry = {"owner/model@q6_k": {"speculative_policy": "disabled", "template_policy": "explicit_file",
                "template": "muse.jinja", "local": {"model_path": str(main)}}}
    content, skipped = rt.build_llama_preset(registry)
    assert not skipped
    assert "spec-type = none" in content
    assert "chat-template-file = " in content
    assert "spec-draft-model" not in content


def test_moe_detection_reads_header_without_weight_mapping_and_refreshes(tmp_path):
    main = tmp_path / "model-Q6_K.gguf"
    write_gguf(main, metadata={"qwen35.expert_count": 64})
    assert rt._gguf_has_experts(str(main)) is True
    before = main.stat()
    write_gguf(main, metadata={"qwen35.expert_count": 0})
    # Equal-size writes can share an mtime on Windows runners. Exercise the
    # stat-keyed refresh contract explicitly, without sleeping or clearing it.
    os.utime(main, ns=(before.st_atime_ns, before.st_mtime_ns + 2_000_000_000))
    assert main.stat().st_mtime_ns != before.st_mtime_ns
    assert rt._gguf_has_experts(str(main)) is False
