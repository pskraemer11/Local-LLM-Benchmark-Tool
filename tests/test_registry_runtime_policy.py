"""Shared policies must survive assembly and the real request builders."""
import json

import pytest
import yaml

import assemble_blueprint as ab
import benchmark_config as bc
import custom_benchmark as cb
import registry_tool as rt
import run_benchmarks as rb
from inventory import IdentityLink, RuntimeBinding
from runtime_policy import resolve_context_length, resolve_template
from type_defs import GenerationConfig


@pytest.mark.parametrize("entry,expected", [
    ({"max_context_length": 32768}, 32768),
    ({"context_length": 65536, "max_context_length": 32768}, 32768),
    ({"context_length": True, "max_context_length": 32768}, 32768),
    ({"context_length": 8192, "max_context_length": 32768}, 8192),
])
def test_context_boundary(entry, expected):
    assert resolve_context_length(entry) == expected


def test_explicit_template_policy_is_shared_with_assembly(monkeypatch, tmp_path):
    key = "vendor/model@q6_k"
    entry = {"publisher": "vendor", "blueprint": "review", "template_policy": "explicit_file", "template": "explicit.jinja"}
    blueprint = {"role": "review", "template": "blueprint.jinja", "modules": []}
    registry = tmp_path / "registry.yaml"
    blueprints = tmp_path / "blueprints.yaml"
    registry.write_text(yaml.safe_dump({key: entry}), encoding="utf-8")
    blueprints.write_text(yaml.safe_dump({"blueprints": {"review": blueprint}, "modules": {}}), encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"operation": {"fields": []}}), encoding="utf-8")
    (tmp_path / "explicit.jinja").write_text("EXPLICIT_TEMPLATE", encoding="utf-8")
    (tmp_path / "blueprint.jinja").write_text("BLUEPRINT_TEMPLATE", encoding="utf-8")
    monkeypatch.setattr(ab, "REGISTRY_PATH", registry)
    monkeypatch.setattr(ab, "BLUEPRINT_PATH", blueprints)
    monkeypatch.setattr(ab, "TEMPLATE_DIR", tmp_path)
    monkeypatch.setattr(ab, "read_lms_configs", lambda _root: [{"publisher": "vendor", "json_path": config}])
    link = IdentityLink(key, runtime_bindings=(RuntimeBinding(config_path=config),))
    ab.assemble_prompts(preview_only=False, identity_links={key: link})
    fields = json.loads(config.read_text())["operation"]["fields"]
    assert next(field["value"] for field in fields if field["key"] == "llm.prediction.promptTemplate") == "EXPLICIT_TEMPLATE"
    monkeypatch.setattr(rt, "load_registry", lambda: {key: entry})
    monkeypatch.setattr(rt, "_load_blueprints", lambda: {"review": blueprint})
    assert rt._registry_template_name(key) == resolve_template(entry, blueprint, key) == "explicit.jinja"


@pytest.mark.parametrize("template,expected_control", [("{% if enable_thinking %}<think>{% endif %}", True), ("{{ messages }}", False)])
def test_neutral_registry_thinking_uses_profile_and_template_in_both_requests(monkeypatch, tmp_path, template, expected_control):
    key = "vendor/neutral@q6_k"
    entry = {"reasoning": "thinking", "sampling": {
        "sampling_research_status": "confirmed",
        "coding": {"temperature": 0.12, "top_p": 0.99},
        "thinking": {"temperature": 0.93, "top_p": 0.81},
    }}
    (tmp_path / "native.jinja").write_text(template, encoding="utf-8")
    monkeypatch.setattr(bc, "_load_quant_registry", lambda: {key: entry})
    monkeypatch.setattr(bc, "_lms_generation_config", lambda _key: {})
    monkeypatch.setattr(bc, "_blueprint_features", lambda _key: {"template": "native.jinja"})
    monkeypatch.setattr(bc, "_TEMPLATE_ROOT", tmp_path)
    config = bc.get_model_config(key, is_thinking_enabled=True)
    assert (config["temperature"], config["top_p"], config["enable_thinking"]) == (0.93, 0.81, True)
    monkeypatch.setattr(rb, "IS_THINKING_ENABLED", True)
    lmeval = rb._get_evaluation_parameters(key, "coding")
    captured = {}
    def send(_url, _headers, body, **_kwargs):
        captured.update(body)
        return "answer", 0.1, 2, 3, 30.0, 0, False, None, None
    monkeypatch.setattr(cb, "_stream_chat_completion", send)
    cb.generate_answer(GenerationConfig(prompt="hello", model_identifier="instance-alias", native_model_identifier=key, is_thinking_enabled=True))
    assert captured.get("chat_template_kwargs") == lmeval.get("chat_template_kwargs")
    assert ("chat_template_kwargs" in captured) is expected_control
    assert captured["model"] == "instance-alias"


def test_registry_instruct_wins_over_name_and_force(monkeypatch):
    key = "vendor/reasoning-thinker@q6_k"
    monkeypatch.setattr(bc, "_load_quant_registry", lambda: {key: {"reasoning": "instruct"}})
    monkeypatch.setattr(bc, "_lms_generation_config", lambda _key: {})
    config = bc.get_model_config(key, is_thinking_enabled=True)
    assert config["enable_thinking"] is False


@pytest.mark.parametrize("profile", [{"type": "typo"}, {"type": "mtp", "mode": "typo"}])
def test_invalid_profile_is_blocking_in_validation_and_provider(profile):
    from model_registry import ModelRegistry

    key = "vendor/model@q6_k"
    entry = {"local": {"llama_cpp": {"speculative": profile}}}
    assert rt._registry_local_bundle_errors({key: entry})["companion"]
    resolved = ModelRegistry(lambda: {key: entry}).resolve(key)
    with pytest.raises(ValueError, match="unsupported"):
        resolved.provider_runtime("llama_cpp")


def test_embedded_template_controls_reach_request_policy(monkeypatch, tmp_path):
    from local_model_resolver import LocalModelResolver
    from tests.gguf_fixture import write_gguf

    key = "vendor/neutral@q6_k"
    model_path = tmp_path / "vendor/Neutral-GGUF/Neutral-Q6_K.gguf"
    write_gguf(model_path, metadata={"tokenizer.chat_template": "{% if reasoning_effort %}think{% endif %}"})
    registry = {key: {"reasoning": "thinking", "local": {"model_path": str(model_path)}}}
    monkeypatch.setattr(bc, "_load_quant_registry", lambda: registry)
    monkeypatch.setattr(bc, "_lms_generation_config", lambda _key: {"reasoning_effort": "high"})
    monkeypatch.setattr(bc, "_blueprint_features", lambda _key: {})
    monkeypatch.setattr(LocalModelResolver, "_model_base_id", lambda _self, _path: "vendor/Neutral-GGUF")
    config = bc.get_model_config(key, is_thinking_enabled=True)
    assert config["_reasoning_template_controls"] == frozenset({"reasoning_effort"})
