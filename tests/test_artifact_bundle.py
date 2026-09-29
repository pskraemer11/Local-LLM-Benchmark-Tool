from __future__ import annotations

import hashlib
import json

import pytest

from artifact_bundle import config_matches_gguf, validate_companion_binding, validate_config_gguf_pair
from gguf_evidence import read_gguf_evidence
from model_registry import ModelRegistry
from tests.gguf_fixture import write_gguf


def _write_integrated_mtp(path, *, layer_count=1, projection_shape=(10240, 5120), include_projection=True):
    tensors = {
        "token_embd.weight": (5120, 4),
        "blk.0.attn_q.weight": (5120, 5120),
        "blk.3.nextn.enorm.weight": (5120,),
        "blk.3.nextn.hnorm.weight": (5120,),
    }
    if include_projection:
        tensors["blk.3.nextn.eh_proj.weight"] = projection_shape
    write_gguf(path, block_count=4, metadata={"qwen35.nextn_predict_layers": layer_count}, tensors=tensors)


def test_integrated_mtp_requires_physical_main_and_nextn_layers(tmp_path):
    main = tmp_path / "model-MTP.gguf"
    profile = {"type": "mtp", "mode": "integrated"}
    assert validate_companion_binding(None, None, profile)
    assert validate_companion_binding(main, None, profile)
    main.write_bytes(b"not a GGUF")
    assert validate_companion_binding(main, None, profile)
    write_gguf(main)
    assert validate_companion_binding(main, None, profile)
    _write_integrated_mtp(main)
    assert validate_companion_binding(main, None, profile) == ()


@pytest.mark.parametrize("layer_count", [0, True, "1", 4])
def test_integrated_mtp_rejects_invalid_layer_metadata(tmp_path, layer_count):
    main = tmp_path / "model-MTP.gguf"
    _write_integrated_mtp(main, layer_count=layer_count)
    assert validate_companion_binding(main, None, {"type": "mtp", "mode": "integrated"})


@pytest.mark.parametrize("missing_projection,projection_shape", [(True, (10240, 5120)), (False, (4096, 2048))])
def test_integrated_mtp_requires_actual_matching_projection(tmp_path, missing_projection, projection_shape):
    main = tmp_path / "model-MTP.gguf"
    _write_integrated_mtp(main, include_projection=not missing_projection, projection_shape=projection_shape)
    errors = validate_companion_binding(main, None, {"type": "mtp", "mode": "integrated"})
    assert any("projection" in error for error in errors)


def test_integrated_mtp_cannot_use_an_assistant_sidecar_as_main(tmp_path):
    sidecar = tmp_path / "mtp-sidecar.gguf"
    write_gguf(sidecar, architecture="gemma4-assistant", helper="mtp")
    assert validate_companion_binding(sidecar, None, {"type": "mtp", "mode": "integrated"})


def test_non_speculative_models_do_not_require_a_local_gguf():
    assert validate_companion_binding(None, None, {}) == ()


def test_provider_runtime_blocks_unproven_integrated_mtp_before_emitting_spec_type(tmp_path):
    main = tmp_path / "model-MTP.gguf"
    write_gguf(main)
    registry = {
        "publisher/model@q6_k": {
            "local": {
                "model_path": str(main),
                "llama_cpp": {"speculative": {"type": "mtp", "mode": "integrated"}},
            }
        }
    }
    resolver = ModelRegistry(lambda: registry)
    with pytest.raises(ValueError, match="integrated MTP"):
        resolver.provider_runtime("publisher/model@q6_k", "llama_cpp")
    _write_integrated_mtp(main)
    runtime = resolver.provider_runtime("publisher/model@q6_k", "llama_cpp")
    assert runtime["spec_type"] == "draft-mtp"


@pytest.mark.parametrize("target_layer,valid", [(62, True), (64, False)])
def test_dflash_target_layers_exclude_integrated_nextn_layers(tmp_path, target_layer, valid):
    main, helper = tmp_path / "main.gguf", tmp_path / "dspark.gguf"
    write_gguf(main, block_count=65, metadata={"qwen35.nextn_predict_layers": 1})
    write_gguf(
        helper,
        architecture="dflash",
        helper="dspark",
        target_repo="Qwen/Qwen3.6-27B",
        metadata={"dflash.target_layers": (1, target_layer)},
    )
    errors = validate_companion_binding(main, helper, {"type": "draft", "method": "dspark"})
    assert (errors == ()) is valid
    if not valid:
        assert any("target layers" in error for error in errors)


@pytest.mark.parametrize("block_count,nextn,target_layer", [
    (True, 0, 0), (65, True, 62), (65, "1", 62), (65, 65, 62), (65, 66, 62), (65, 1, True),
])
def test_dflash_target_layer_counts_and_indices_require_valid_integers(tmp_path, block_count, nextn, target_layer):
    main, helper = tmp_path / "main.gguf", tmp_path / "dspark.gguf"
    write_gguf(main, block_count=block_count, metadata={"qwen35.nextn_predict_layers": nextn})
    write_gguf(
        helper,
        architecture="dflash",
        helper="dspark",
        target_repo="Qwen/Qwen3.6-27B",
        metadata={"dflash.target_layers": (target_layer,)},
        tensors={"fc.weight": (5120, 5120), "markov_w1.weight": (32, 4), "markov_w2.weight": (32, 4)},
    )
    assert validate_companion_binding(main, helper, {"type": "draft", "method": "dspark"})


def test_config_pair_requires_same_concrete_gguf_package(tmp_path):
    model = tmp_path / "models" / "publisher" / "model-GGUF" / "model-Q5_K_S.gguf"
    config = tmp_path / "configs" / "publisher" / "model-GGUF" / "model-Q5_K_S.gguf.json"
    wrong_config = tmp_path / "configs" / "publisher" / "other-GGUF" / "model-Q5_K_S.gguf.json"
    for path in (model, config, wrong_config):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"GGUF fixture")

    assert config_matches_gguf(config, model)
    assert validate_config_gguf_pair(model, config) == ()
    assert not config_matches_gguf(wrong_config, model)
    assert "same GGUF file/package" in " ".join(validate_config_gguf_pair(model, wrong_config))


def test_generic_config_requires_explicit_model_scope_and_matching_package(tmp_path):
    model = tmp_path / "models" / "publisher" / "Qwen3.5-9B-GGUF" / "Qwen3.5-9B-Q6_K.gguf"
    config = tmp_path / "configs" / "qwen" / "qwen3.5-9b.json"
    wrong_config = tmp_path / "configs" / "qwen" / "qwen3.6-9b.json"
    for path in (model, config, wrong_config):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"GGUF fixture")

    assert not config_matches_gguf(config, model)
    assert config_matches_gguf(config, model, scope="model")
    assert validate_config_gguf_pair(model, config, scope="model") == ()
    assert "same GGUF file/package" in " ".join(validate_config_gguf_pair(model, wrong_config, scope="model"))


def test_mtp_sidecar_requires_mtp_header_and_matching_target_projection(tmp_path):
    main = tmp_path / "gemma-4-26b-a4b-it-Q4_K_M.gguf"
    companion = tmp_path / "mtp-gemma-4-26b-a4b-it-Q8_0.gguf"
    wrong = tmp_path / "mtp-gemma-4-12b-it-Q8_0.gguf"
    not_mtp = tmp_path / "gemma-4-26b-a4b-it-Q8_0.gguf"
    write_gguf(main, architecture="gemma4", hidden_dim=2816, source_repo="google/gemma-4-26B-A4B-it")
    for path, target_dim in ((companion, 2816), (wrong, 3840)):
        write_gguf(
            path,
            architecture="gemma4-assistant",
            hidden_dim=1024,
            helper="mtp",
            target_dim=target_dim,
            target_repo="google/gemma-4-26B-A4B-it",
        )
    write_gguf(not_mtp, architecture="gemma4", hidden_dim=2816)

    profile = {"type": "mtp", "mode": "separate"}
    assert validate_companion_binding(main, companion, profile) == ()
    assert any("target projection dimensions mismatch" in e for e in validate_companion_binding(main, wrong, profile))
    assert any(
        "profile conflicts with companion header kind" in e for e in validate_companion_binding(main, not_mtp, profile)
    )


def test_speculative_helper_rejects_target_shape_and_role_mismatches(tmp_path):
    main = tmp_path / "qwen3.6-27b.gguf"
    matching = tmp_path / "qwen3.6-27b-dflash2-q8_0.gguf"
    wrong_version = tmp_path / "qwen3.8-27b-dflash2-q8_0.gguf"
    wrong_size = tmp_path / "qwen3.6-35b-dflash2-q8_0.gguf"
    simple_draft_profile = {"type": "draft", "method": "simple"}
    dflash_profile = {"type": "draft", "method": "dflash"}
    write_gguf(main)
    write_gguf(matching, architecture="dflash", helper="dflash", target_repo="Qwen/Qwen3.6-27B")
    write_gguf(wrong_version, architecture="dflash", helper="dflash", target_repo="Qwen/Qwen3.8-27B")
    write_gguf(wrong_size, architecture="dflash", helper="dflash", target_repo="Qwen/Qwen3.6-27B", target_dim=2048)

    assert validate_companion_binding(main, matching, dflash_profile) == ()
    assert any(
        "target identity is unproven" in e for e in validate_companion_binding(main, wrong_version, dflash_profile)
    )
    assert any(
        "target feature projection dimensions mismatch" in e
        for e in validate_companion_binding(main, wrong_size, dflash_profile)
    )
    assert any("simple draft profile" in e for e in validate_companion_binding(main, matching, simple_draft_profile))
    assert any(
        "does not exist" in e
        for e in validate_companion_binding(main, tmp_path / "missing-dflash.gguf", dflash_profile)
    )


def test_one_compatible_dflash_helper_can_be_shared_by_model_variants(tmp_path):
    first_main = tmp_path / "qwen3.6-27b-instruct.gguf"
    second_main = tmp_path / "qwen3.6-27b-reap.gguf"
    shared_helper = tmp_path / "qwen3.6-27b-dflash2-q8_0.gguf"
    for path in (first_main, second_main):
        write_gguf(path)
    write_gguf(shared_helper, architecture="dflash", helper="dflash", target_repo="Qwen/Qwen3.6-27B")

    profile = {"type": "draft", "method": "dflash"}
    assert validate_companion_binding(first_main, shared_helper, profile) == ()
    assert validate_companion_binding(second_main, shared_helper, profile) == ()


def test_ordinary_smaller_drafter_needs_no_draft_filename_or_equal_parameter_count(tmp_path):
    main, helper = tmp_path / "Qwen3-8B-Q6_K.gguf", tmp_path / "Qwen3-0.6B-Q8_0.gguf"
    write_gguf(main, hidden_dim=4096)
    write_gguf(helper, architecture="qwen3", hidden_dim=1024, block_count=8, source_repo="Qwen/Qwen3-0.6B")
    assert validate_companion_binding(main, helper, {"type": "draft", "method": "simple"}) == ()


@pytest.mark.parametrize("requested,actual", [("dflash", "dspark"), ("dspark", "dflash")])
def test_helper_algorithm_is_proven_by_headers_not_filename(tmp_path, requested, actual):
    main, helper = tmp_path / "main.gguf", tmp_path / f"misleading-{requested}.gguf"
    write_gguf(main)
    write_gguf(helper, architecture="dflash", helper=actual, target_repo="Qwen/Qwen3.6-27B")
    assert any(
        "profile conflicts" in e
        for e in validate_companion_binding(main, helper, {"type": "draft", "method": requested})
    )


def test_partial_dspark_markov_head_is_rejected(tmp_path):
    main, helper = tmp_path / "main.gguf", tmp_path / "dspark.gguf"
    write_gguf(main)
    write_gguf(
        helper,
        architecture="dflash",
        helper="dspark",
        target_repo="Qwen/Qwen3.6-27B",
        tensors={"fc.weight": (10240, 5120), "markov_w1.weight": (32, 4)},
    )
    assert any(
        "invalid-dspark" in e for e in validate_companion_binding(main, helper, {"type": "draft", "method": "dspark"})
    )


def test_same_size_and_tokenizer_do_not_prove_specialized_target(tmp_path):
    main, helper = tmp_path / "same-size.gguf", tmp_path / "same-size-dflash.gguf"
    write_gguf(main)
    write_gguf(helper, architecture="dflash", helper="dflash")
    assert any(
        "target identity is unproven" in e
        for e in validate_companion_binding(
            main, helper, {"type": "draft", "method": "dflash", "pairing": {"validated": True}}
        )
    )


def test_tokenizer_table_mismatch_rejects_ordinary_draft(tmp_path):
    main, helper = tmp_path / "main.gguf", tmp_path / "small.gguf"
    write_gguf(main)
    write_gguf(helper, tokens=("a", "b", "wrong", "d"))
    assert any(
        "token-table mismatch" in e
        for e in validate_companion_binding(main, helper, {"type": "draft", "method": "simple"})
    )


def test_target_bound_helper_does_not_require_ordinary_bos_eos_defaults(tmp_path):
    main, helper = tmp_path / "main.gguf", tmp_path / "helper.gguf"
    write_gguf(main)
    write_gguf(
        helper,
        architecture="dflash",
        helper="dflash",
        target_repo="Qwen/Qwen3.6-27B",
        metadata={"tokenizer.ggml.eos_token_id": 3, "tokenizer.ggml.add_bos_token": True},
    )
    assert validate_companion_binding(main, helper, {"type": "draft", "method": "dflash"}) == ()


def test_ordinary_draft_requires_matching_bos_eos_defaults(tmp_path):
    main, helper = tmp_path / "main.gguf", tmp_path / "helper.gguf"
    write_gguf(main)
    write_gguf(helper, metadata={"tokenizer.ggml.eos_token_id": 3})
    assert any(
        "eos_token_id mismatch" in e
        for e in validate_companion_binding(main, helper, {"type": "draft", "method": "simple"})
    )


def test_truncated_magic_is_not_header_evidence(tmp_path):
    main, helper = tmp_path / "main.gguf", tmp_path / "dflash.gguf"
    write_gguf(main)
    helper.write_bytes(b"GGUF")
    assert any(
        "truncated GGUF header" in e
        for e in validate_companion_binding(main, helper, {"type": "draft", "method": "dflash"})
    )


def test_pairing_evidence_is_bound_to_artifacts_method_and_provenance(tmp_path):
    main, helper = tmp_path / "main.gguf", tmp_path / "helper.gguf"
    write_gguf(main)
    write_gguf(helper, architecture="dflash", helper="dflash")
    record = {
        "method": "dflash",
        "main_path": str(main),
        "companion_path": str(helper),
        "main_fingerprint": read_gguf_evidence(main).fingerprint,
        "companion_fingerprint": read_gguf_evidence(helper).fingerprint,
        "validation": {
            "status": "passed",
            "check": "speculative_pairing",
            "provider": "llama_cpp",
            "source": "fixture-provider-load-result.json",
        },
    }
    evidence_path = tmp_path / "pairing.json"
    raw = json.dumps(record).encode()
    evidence_path.write_bytes(raw)
    profile = {
        "type": "draft",
        "method": "dflash",
        "pairing": {"evidence_path": str(evidence_path), "evidence_sha256": hashlib.sha256(raw).hexdigest()},
    }
    assert validate_companion_binding(main, helper, profile) == ()
    evidence_path.write_bytes(raw + b" ")
    assert any("target identity is unproven" in e for e in validate_companion_binding(main, helper, profile))
    evidence_path.write_bytes(raw)
    write_gguf(helper, architecture="dflash", helper="dflash", metadata={"general.name": "changed-helper"})
    assert any("target identity is unproven" in e for e in validate_companion_binding(main, helper, profile))


def test_complete_large_token_array_and_chat_template_are_read_without_tensor_data(tmp_path):
    path = tmp_path / "tokens.gguf"
    write_gguf(
        path,
        tokens=tuple(f"token-{i}" for i in range(5000)),
        metadata={"tokenizer.chat_template": "{{ enable_thinking }}"},
    )
    evidence = read_gguf_evidence(path)
    assert evidence.metadata["tokenizer.ggml.tokens"].count == 5000
    assert evidence.metadata["tokenizer.chat_template"] == "{{ enable_thinking }}"
    assert len(evidence.header_sha256) == 64


def test_same_ancestor_does_not_prove_finetuned_main_target(tmp_path):
    main, helper = tmp_path / "finetune.gguf", tmp_path / "dflash.gguf"
    write_gguf(
        main,
        source_repo="publisher/finetune",
        metadata={
            "general.finetune": "sft",
            "general.base_model.0.repo_url": "https://huggingface.co/Qwen/Qwen3.6-27B",
        },
    )
    write_gguf(helper, architecture="dflash", helper="dflash", target_repo="Qwen/Qwen3.6-27B")
    assert any(
        "target identity is unproven" in e
        for e in validate_companion_binding(main, helper, {"type": "draft", "method": "dflash"})
    )


def test_mtp_projection_metadata_does_not_replace_actual_tensor_shape(tmp_path):
    main, helper = tmp_path / "main.gguf", tmp_path / "assistant.gguf"
    write_gguf(main, architecture="gemma4", hidden_dim=2816, source_repo="google/gemma-4-26B-A4B-it")
    write_gguf(
        helper,
        architecture="gemma4-assistant",
        hidden_dim=1024,
        helper="mtp",
        target_dim=2816,
        target_repo="google/gemma-4-26B-A4B-it",
        tensors={"nextn.pre_projection.weight": (7680, 1024), "nextn.post_projection.weight": (1024, 3840)},
    )
    assert any(
        "projection tensor dimensions mismatch" in e
        for e in validate_companion_binding(main, helper, {"type": "mtp", "mode": "separate"})
    )


def test_header_cache_does_not_expose_mutable_cached_evidence(tmp_path):
    path = tmp_path / "main.gguf"
    write_gguf(path)
    read_gguf_evidence(path).metadata["general.architecture"] = "wrong"
    assert read_gguf_evidence(path).metadata["general.architecture"] == "qwen35"


@pytest.mark.parametrize("profile", [{"type": "draft", "method": "typo"}, {"type": "unknown"}])
def test_invalid_speculative_classifications_fail_closed(tmp_path, profile):
    main, helper = tmp_path / "main.gguf", tmp_path / "helper.gguf"
    write_gguf(main)
    write_gguf(helper)
    assert validate_companion_binding(main, helper, profile)


@pytest.mark.parametrize("field,value", [("pre", "qwen2"), ("add_bos_token", True), ("bos_token_id", 2)])
def test_ordinary_draft_rejects_one_sided_tokenizer_settings(tmp_path, field, value):
    main, draft = tmp_path / "main.gguf", tmp_path / "draft.gguf"
    write_gguf(main, metadata={f"tokenizer.ggml.{field}": value})
    write_gguf(draft, hidden_dim=128)
    errors = validate_companion_binding(main, draft, {"type": "draft", "method": "simple"})
    assert any("tokenizer" in message for message in errors)


def test_specialized_helper_cannot_use_an_untyped_shared_base_as_target(tmp_path):
    main, helper = tmp_path / "main.gguf", tmp_path / "helper.gguf"
    write_gguf(main, source_repo="vendor/Model-Heretic", metadata={
        "general.base_model.0.repo_url": "https://huggingface.co/Qwen/Qwen3.6-27B",
    })
    write_gguf(helper, architecture="dflash", helper="dflash", target_repo="Qwen/Qwen3.6-27B")
    errors = validate_companion_binding(main, helper, {"type": "draft", "method": "dflash"})
    assert any("target identity" in message for message in errors)
