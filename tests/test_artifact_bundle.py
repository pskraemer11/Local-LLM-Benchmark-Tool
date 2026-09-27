from __future__ import annotations

from artifact_bundle import config_matches_gguf, validate_companion_binding, validate_config_gguf_pair


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
    assert "same GGUF file/package" in " ".join(
        validate_config_gguf_pair(model, wrong_config, scope="model")
    )


def test_mtp_sidecar_requires_explicit_mtp_file_and_matching_declared_shape(tmp_path):
    main = tmp_path / "gemma-4-26b-a4b-it-Q4_K_M.gguf"
    companion = tmp_path / "mtp-gemma-4-26b-a4b-it-Q8_0.gguf"
    wrong = tmp_path / "mtp-gemma-4-12b-it-Q8_0.gguf"
    not_mtp = tmp_path / "gemma-4-26b-a4b-it-Q8_0.gguf"
    for path in (main, companion, wrong, not_mtp):
        path.write_bytes(b"GGUF fixture")

    profile = {"type": "mtp", "mode": "separate"}
    assert validate_companion_binding(main, companion, profile) == ()
    assert any("parameter-size mismatch" in e for e in validate_companion_binding(main, wrong, profile))
    assert any("not identified as a separate MTP" in e for e in validate_companion_binding(
        main, not_mtp, profile
    ))


def test_speculative_helper_rejects_version_size_and_role_mismatches(tmp_path):
    main = tmp_path / "qwen3.6-27b.gguf"
    matching = tmp_path / "qwen3.6-27b-dflash2-q8_0.gguf"
    wrong_version = tmp_path / "qwen3.8-27b-dflash2-q8_0.gguf"
    wrong_size = tmp_path / "qwen3.6-35b-dflash2-q8_0.gguf"
    simple_draft_profile = {"type": "draft", "method": "simple"}
    dflash_profile = {"type": "draft", "method": "dflash"}
    for path in (main, matching, wrong_version, wrong_size):
        path.write_bytes(b"GGUF fixture")

    assert validate_companion_binding(main, matching, dflash_profile) == ()
    assert any("Qwen generation mismatch" in e for e in validate_companion_binding(
        main, wrong_version, dflash_profile
    ))
    assert any("parameter-size mismatch" in e for e in validate_companion_binding(
        main, wrong_size, dflash_profile
    ))
    assert any("simple draft profile" in e for e in validate_companion_binding(
        main, matching, simple_draft_profile
    ))
    assert any("does not exist" in e for e in validate_companion_binding(
        main, tmp_path / "missing-dflash.gguf", dflash_profile
    ))


def test_one_compatible_dflash_helper_can_be_shared_by_model_variants(tmp_path):
    first_main = tmp_path / "qwen3.6-27b-instruct.gguf"
    second_main = tmp_path / "qwen3.6-27b-reap.gguf"
    shared_helper = tmp_path / "qwen3.6-27b-dflash2-q8_0.gguf"
    for path in (first_main, second_main, shared_helper):
        path.write_bytes(b"GGUF")

    profile = {"type": "draft", "method": "dflash"}
    assert validate_companion_binding(first_main, shared_helper, profile) == ()
    assert validate_companion_binding(second_main, shared_helper, profile) == ()
