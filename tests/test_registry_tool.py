"""Tests for registry_tool.py (Code-Review 2026-07-18 §5: test coverage).

The registry tool is the most logic-dense file in the project
(VRAM formula, match cascades). The test coverage was the largest
gap in the review.

Targets:
  5.1  _max_ctx_from_vram() and VRAM constants
  5.2  Match cascade in cmd_configs (registry ↔ JSON config)
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import assemble_blueprint as ab
import registry_tool as rt
from registry_tool import (
    _KV_BYTES,
    _LEGACY_MODEL_GB_THRESHOLD_GB,
    _USABLE_VRAM_GB,
    _USE_UNIFIED_KV_CACHE_THRESHOLD_GB,
    _classify_arch,
    _max_ctx_from_vram,
)


def test_public_help_exposes_short_workflow(monkeypatch, capsys) -> None:
    """The default CLI help should lead with the small routine workflow."""
    monkeypatch.setattr(sys, "argv", ["registry_tool.py", "--help"])
    rt.main()
    help_text = capsys.readouterr().out
    assert "status" in help_text
    assert "sync" in help_text
    assert "full" in help_text
    assert "--import-lms-settings" in help_text
    assert "legacy `pipeline full` command" in help_text
    assert "advanced <command>" in help_text


def test_help_describes_registry_tool_surface() -> None:
    help_text = rt.__doc__ or ""
    assert "model_registry.yaml" in help_text
    assert "Tested runtime evidence; import is opt-in" in help_text
    assert "only missing" in help_text
    assert "full --write-prompts" in help_text
    assert "sync --refresh-sampling" in help_text
    assert "may take several minutes" in help_text
    assert "max_context_length" in help_text
    assert "max_experts" in help_text


def test_inventory_reads_registry_models_and_configs_once() -> None:
    models = [{"type": "llm", "modelKey": "publisher/model"}]
    with (
        patch.object(rt, "load_registry", return_value={"publisher/model": {}}) as load,
        patch.object(rt, "_run_lms_ls", return_value=models) as list_models,
        patch.object(rt, "read_lms_configs", return_value=[]) as read_configs,
    ):
        inventory = rt._collect_registry_inventory()

    load.assert_called_once_with()
    list_models.assert_called_once_with()
    read_configs.assert_called_once_with(rt.CONFIG_ROOT)
    assert inventory.raw_lms_models == models
    assert inventory.gguf_candidates_loaded is False


def test_shared_inventory_reuses_gguf_header_snapshot(tmp_path) -> None:
    path = tmp_path / "model.gguf"
    path.write_bytes(b"test")
    inventory = rt.RegistryInventory({}, [], [], [], [])
    header = (32, 4096, True, 131072, 64)
    with (
        patch.object(
            rt,
            "_read_gguf_header_details",
            return_value=(*header, "qwen3moe"),
        ) as read_header,
    ):
        first = rt._read_gguf_header_snapshot(str(path), inventory)
        second = rt._read_gguf_header_snapshot(str(path), inventory)

    assert first == second == (header, "qwen3moe")
    read_header.assert_called_once_with(str(path.resolve()))


def test_subcommand_help_never_runs_the_subcommand(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["registry_tool.py", "quarantine-missing", "--help"])
    with patch.object(
        rt, "cmd_quarantine_missing", side_effect=AssertionError("help must not mutate")
    ):
        with pytest.raises(SystemExit) as exc_info:
            rt.main()

    assert exc_info.value.code == 0
    assert "quarantine-missing" in capsys.readouterr().out


def test_simple_sync_routes_to_pipeline_with_explicit_import(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(sys, "argv", ["registry_tool.py", "sync", "--import-lms-settings", "--refresh-sampling"])
    monkeypatch.setattr(rt, "cmd_pipeline", lambda *args, **kwargs: calls.append((args, kwargs)))

    rt.main()

    assert calls == [
        (
            ("sync",),
            {"refresh_sampling": True, "import_lms_settings": True},
        )
    ]


@pytest.mark.parametrize(
    "arguments",
    [
        ["full", "--ignore-drift", "--refresh-sampling", "--import-lms-settings"],
        ["pipeline", "full", "--ignore-drift", "--refresh-sampling", "--import-lms-settings"],
    ],
)
def test_full_public_command_and_pipeline_alias_share_the_same_options(monkeypatch, arguments) -> None:
    calls = []
    monkeypatch.setattr(sys, "argv", ["registry_tool.py", *arguments])
    monkeypatch.setattr(rt, "cmd_pipeline", lambda *args, **kwargs: calls.append((args, kwargs)))

    rt.main()

    assert calls == [
        (
            ("full",),
            {
                "ignore_drift": True,
                "refresh_sampling": True,
                "import_lms_settings": True,
                "write_prompts": False,
            },
        )
    ]


def test_advanced_help_does_not_execute_specialist_command(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["registry_tool.py", "advanced", "--help"])
    rt.main()
    output = capsys.readouterr().out
    assert "sync-from-configs" in output
    assert "export-llama-preset" in output


def test_registry_save_keeps_original_when_temporary_serialization_fails(tmp_path) -> None:
    registry_path = tmp_path / "registry.yaml"
    original = "publisher/model:\n  context_length: 12345\n"
    registry_path.write_text(original, encoding="utf-8")

    with patch.object(rt, "_format_blank_lines", side_effect=OSError("simulated failure")):
        with pytest.raises(OSError, match="simulated failure"):
            rt.save_registry({"publisher/model": {"context_length": 67890}}, registry_path)

    assert registry_path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob(".registry.yaml.*.tmp")) == []


def test_fill_size_never_imports_lm_studio_aggregate_size(monkeypatch) -> None:
    registry = {"publisher/model@q4_k_m": {"context_length": 16384}}
    inventory = rt.RegistryInventory(
        registry,
        [{"modelKey": "publisher/model", "sizeBytes": 99_000_000}],
        [{"modelKey": "publisher/model", "sizeBytes": 99_000_000}],
        [],
        [],
        True,
    )
    with patch.object(rt, "save_registry") as save_registry:
        assert rt.cmd_fill_size(inventory=inventory) == 0

    assert "file_size_bytes" not in registry["publisher/model@q4_k_m"]
    save_registry.assert_not_called()


def test_add_uses_main_gguf_size_not_lm_studio_aggregate(tmp_path, monkeypatch) -> None:
    main_gguf = tmp_path / "model-q4_k_m.gguf"
    main_gguf.write_bytes(b"main")
    monkeypatch.setattr(rt, "REGISTRY_PATH", tmp_path / "registry.yaml")
    rt.REGISTRY_PATH.touch()
    saved: dict[str, dict] = {}
    monkeypatch.setattr(rt, "load_registry", lambda: {})
    monkeypatch.setattr(rt, "save_registry", lambda value: saved.update(value))
    monkeypatch.setattr(rt, "is_registry_candidate", lambda _model: True)
    monkeypatch.setattr(rt, "is_support_model_record", lambda _model: False)
    monkeypatch.setattr(rt, "is_blacklisted_model_name", lambda _name: False)
    monkeypatch.setattr(rt, "_is_support_file", lambda *_args: False)
    monkeypatch.setattr(rt, "_find_gguf_relative_path", lambda _path: main_gguf)
    monkeypatch.setattr(rt, "_classify_arch", lambda *_args: "dense")
    monkeypatch.setattr(rt, "_read_gguf_arch", lambda _path: (1, 2, False, 32768, None))

    rt.cmd_add(
        [
            {
                "type": "llm",
                "modelKey": "publisher/model",
                "publisher": "publisher",
                "selectedVariant": "publisher/model@q4_k_m",
                "sizeBytes": 99_000_000,
                "path": "publisher/model/model-q4_k_m.gguf",
            }
        ]
    )

    entry = next(iter(saved.values()))
    assert entry["file_size_bytes"] == 4


def test_fix_ctx_only_fills_missing_or_zero_values(monkeypatch) -> None:
    registry = {
        "publisher/missing": {"file_size_bytes": 4_000_000_000},
        "publisher/zero": {"file_size_bytes": 4_000_000_000, "context_length": 0},
        "publisher/existing": {"file_size_bytes": 4_000_000_000, "context_length": 12345},
    }
    saved: dict[str, dict] = {}
    monkeypatch.setattr(rt, "load_registry", lambda: registry)
    monkeypatch.setattr(rt, "save_registry", lambda value: saved.update(value))

    rt.cmd_fix_ctx()

    expected = rt._default_ctx_from_size(4_000_000_000, rt._NP_POLICY, "q8_0", "iq4_nl")
    assert registry["publisher/missing"]["context_length"] == expected
    assert registry["publisher/zero"]["context_length"] == expected
    assert registry["publisher/existing"]["context_length"] == 12345
    assert saved["publisher/existing"]["context_length"] == 12345


def test_build_llama_preset_uses_local_gguf_and_provider_runtime(tmp_path: Path, monkeypatch) -> None:
    models_root = tmp_path / "models"
    gguf = models_root / "publisher" / "model" / "model-q4_k_m.gguf"
    gguf.parent.mkdir(parents=True)
    gguf.write_bytes(b"fixture")
    monkeypatch.setattr(rt, "MODELS_CACHE", models_root)
    registry = {
        "publisher/model@q4_k_m": {
            "context_length": 32768,
            "k_cache": "q8_0",
            "v_cache": "q8_0",
            "useUnifiedKvCache": True,
            "reasoning_format": "deepseek",
            "batch_size": 512,
            "architecture_family": "gpt-oss",
            "experts": 32,
            "max_experts": 32,
        },
        "publisher/missing@q4_k_m": {},
    }

    content, skipped = rt.build_llama_preset(registry)

    assert "[publisher/model@q4_k_m]" in content
    assert f"model = {gguf}" in content
    assert "ctx-size = 32768" in content
    assert "cache-type-k = q8_0" in content
    assert "kv-unified = true" in content
    assert "reasoning-format = deepseek" in content
    assert "override-kv = gpt-oss.expert_used_count=int:32" in content
    assert skipped == ["publisher/missing@q4_k_m"]


def test_build_llama_preset_exports_speculative_profiles_and_companions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    models_root = tmp_path / "models"
    paths = {
        name: models_root / "publisher" / name / f"{name}.gguf"
        for name in ("integrated-mtp", "separate-mtp", "mtp-sidecar", "dflash-target", "dflash-helper")
    }
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"GGUF fixture")
    monkeypatch.setattr(rt, "MODELS_CACHE", models_root)
    registry = {
        "publisher/integrated-mtp@q4_k_m": {
            "local": {
                "model_path": str(paths["integrated-mtp"]),
                "llama_cpp": {
                    "speculative": {
                        "type": "mtp",
                        "mode": "integrated",
                        "draft_n_max": 3,
                        "draft_n_min": 0,
                        "draft_p_min": 0.0,
                    }
                },
            }
        },
        "publisher/separate-mtp@q4_k_m": {
            "local": {
                "model_path": str(paths["separate-mtp"]),
                "companions": {"mtp": str(paths["mtp-sidecar"])},
                "llama_cpp": {
                    "speculative": {
                        "type": "mtp",
                        "mode": "separate",
                        "companion_role": "mtp",
                        "draft_n_max": 4,
                        "draft_n_min": 1,
                        "draft_p_min": 0.75,
                    }
                },
            }
        },
        "publisher/dflash@q4_k_m": {
            "local": {
                "model_path": str(paths["dflash-target"]),
                "companions": {"draft": str(paths["dflash-helper"])},
                "llama_cpp": {
                    "speculative": {
                        "type": "draft",
                        "method": "dflash",
                        "companion_role": "draft",
                        "draft_n_max": 3,
                        "draft_n_min": 0,
                        "draft_p_min": 0.5,
                    }
                },
            }
        },
    }

    content, skipped = rt.build_llama_preset(registry)

    assert skipped == []
    integrated = content.split("[publisher/integrated-mtp@q4_k_m]", 1)[1].split("\n\n", 1)[0]
    assert "spec-type = draft-mtp" in integrated
    assert "spec-draft-n-max = 3" in integrated
    assert "spec-draft-model =" not in integrated
    assert "spec-type = draft-mtp" in content
    assert f"spec-draft-model = {paths['mtp-sidecar']}" in content
    assert "spec-draft-n-max = 4" in content
    assert "spec-draft-n-min = 1" in content
    assert "spec-draft-p-min = 0.75" in content
    assert "spec-type = draft-dflash" in content
    assert f"spec-draft-model = {paths['dflash-helper']}" in content


def test_build_llama_preset_skips_incompatible_companion_bundle(tmp_path: Path, monkeypatch) -> None:
    models_root = tmp_path / "models"
    main = models_root / "unsloth" / "qwen3.6-27b-GGUF" / "qwen3.6-27b-Q6_K.gguf"
    helper = models_root / "unsloth" / "qwen3.8-27b-GGUF" / "qwen3.8-27b-dflash2-Q8_0.gguf"
    for path in (main, helper):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"GGUF fixture")
    monkeypatch.setattr(rt, "MODELS_CACHE", models_root)
    registry = {
        "unsloth/qwen3.6-27b@q6_k": {
            "local": {
                "model_path": str(main),
                "companions": {"draft": str(helper)},
                "llama_cpp": {
                    "speculative": {"type": "draft", "method": "dflash", "companion_role": "draft"}
                },
            }
        }
    }

    content, skipped = rt.build_llama_preset(registry)

    assert "[unsloth/qwen3.6-27b@q6_k]" not in content
    assert len(skipped) == 1
    assert "Qwen generation mismatch" in skipped[0]


def test_local_bundle_validation_reports_companion_mismatch_and_accepts_fix(tmp_path):
    main = tmp_path / "models" / "unsloth" / "qwen3.6-27b-GGUF" / "qwen3.6-27b-Q6_K.gguf"
    wrong = tmp_path / "models" / "unsloth" / "qwen3.8-27b-GGUF" / "qwen3.8-27b-dflash2-Q8_0.gguf"
    matching = tmp_path / "models" / "unsloth" / "qwen3.6-27b-GGUF" / "qwen3.6-27b-dflash2-Q8_0.gguf"
    config = tmp_path / "configs" / "unsloth" / "qwen3.6-27b-GGUF" / "qwen3.6-27b-Q6_K.gguf.json"
    for path in (main, wrong, matching, config):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"GGUF fixture")
    entry = {
        "local": {
            "model_path": str(main),
            "config_path": str(config),
            "companions": {"draft": str(wrong)},
            "llama_cpp": {
                "speculative": {"type": "draft", "method": "dflash", "companion_role": "draft"}
            },
        }
    }
    registry = {"unsloth/qwen3.6-27b@q6_k": entry}

    errors = rt._registry_local_bundle_errors(registry)
    assert errors["config"] == []
    assert any("Qwen generation mismatch" in message for message in errors["companion"])

    entry["local"]["companions"]["draft"] = str(matching)
    assert rt._registry_local_bundle_errors(registry) == {"config": [], "companion": []}


def test_build_llama_preset_resolves_lm_studio_hub_repository_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    models_root = tmp_path / "models"
    gguf = (
        models_root
        / "lmstudio-community"
        / "rnj-1-instruct-GGUF"
        / "rnj-1-instruct-Q8_0.gguf"
    )
    gguf.parent.mkdir(parents=True)
    gguf.write_bytes(b"fixture")
    monkeypatch.setattr(rt, "MODELS_CACHE", models_root)
    monkeypatch.setattr(rt.Path, "home", staticmethod(lambda: tmp_path))
    hub_model = tmp_path / ".lmstudio" / "hub" / "models" / "essentialai" / "rnj-1" / "model.yaml"
    hub_model.parent.mkdir(parents=True)
    hub_model.write_text(
        """model: essentialai/rnj-1
base:
  - key: lmstudio-community/rnj-1-instruct-gguf
    sources:
      - type: huggingface
        user: lmstudio-community
        repo: rnj-1-instruct-GGUF
""",
        encoding="utf-8",
    )
    registry = {"essentialai/rnj-1@q8_0": {"publisher": "essentialai"}}

    content, skipped = rt.build_llama_preset(registry)

    assert "[essentialai/rnj-1@q8_0]" in content
    assert f"model = {gguf}".casefold() in content.casefold()
    assert skipped == []


def test_build_llama_preset_does_not_guess_expert_override_key(
    tmp_path: Path, monkeypatch
) -> None:
    models_root = tmp_path / "models"
    gguf = models_root / "publisher" / "model" / "model-q4_k_m.gguf"
    gguf.parent.mkdir(parents=True)
    gguf.write_bytes(b"fixture")
    monkeypatch.setattr(rt, "MODELS_CACHE", models_root)
    registry = {"publisher/model@q4_k_m": {"experts": 24}}

    content, skipped = rt.build_llama_preset(registry)

    assert "[publisher/model@q4_k_m]" in content
    assert "override-kv" not in content
    assert skipped == []


def test_merge_llama_preset_preserves_custom_sections_and_is_idempotent() -> None:
    existing = """[*]
parallel = 4

[gpt-oss-20b]
hf = ggml-org/gpt-oss-20b-GGUF:MXFP4
"""
    generated = """# generated

[publisher/model@q4_k_m]
model = D:\\models\\model.gguf
ctx-size = 32768
"""

    merged = rt.merge_llama_preset(existing, generated)
    merged_again = rt.merge_llama_preset(merged, generated)

    assert "parallel = 4" in merged
    assert "hf = ggml-org/gpt-oss-20b-GGUF:MXFP4" in merged
    assert merged.count("[publisher/model@q4_k_m]") == 1
    assert merged_again.count("[publisher/model@q4_k_m]") == 1
    assert merged_again.count("[gpt-oss-20b]") == 1


def test_merge_llama_preset_removes_stale_generated_sections_only() -> None:
    existing = """# Registry-generated llama.cpp model sections; edit the Registry instead.

[*]
parallel = 4

[manual-hf-model]
hf = owner/model:Q4_K_M

[publisher/stale@q4_k_m]
model = D:\\models\\stale.gguf
ctx-size = 16384
"""
    generated = """# Generated by registry_tool.py

[publisher/current@q5_k_m]
# registry_tool:generated-section
model = D:\\models\\current.gguf
ctx-size = 32768
"""

    merged = rt.merge_llama_preset(existing, generated)

    assert "[*]" in merged and "parallel = 4" in merged
    assert "[manual-hf-model]" in merged
    assert "hf = owner/model:Q4_K_M" in merged
    assert "[publisher/current@q5_k_m]" in merged
    assert "[publisher/stale@q4_k_m]" not in merged


def test_build_llama_argument_manifest_contains_runtime_and_provenance(
    tmp_path: Path, monkeypatch
) -> None:
    models_root = tmp_path / "models"
    gguf = models_root / "publisher" / "model" / "model-q4_k_m.gguf"
    gguf.parent.mkdir(parents=True)
    gguf.write_bytes(b"fixture")
    registry_path = tmp_path / "model_registry.yaml"
    registry_path.write_bytes(b"publisher/model@q4_k_m:\n  context_length: 32768\n")
    monkeypatch.setattr(rt, "MODELS_CACHE", models_root)
    monkeypatch.setattr(rt, "REGISTRY_PATH", registry_path)
    registry = {
        "publisher/model@q4_k_m": {
            "context_length": 32768,
            "k_cache": "q8_0",
            "v_cache": "q8_0",
            "useUnifiedKvCache": True,
            "reasoning_format": "deepseek",
            "reasoning_budget": 8192,
            "sampling": {"temperature": 0.7, "top_p": 1.0},
        },
        "publisher/missing@q4_k_m": {},
    }

    manifest, skipped = rt.build_llama_argument_manifest(
        registry,
        executable=tmp_path / "llama-server.exe",
        api_base="http://127.0.0.1:9931/v1",
    )

    assert manifest["schema_version"] == 1
    expected_hash = hashlib.sha256(registry_path.read_bytes()).hexdigest()
    assert manifest["registry_sha256"] == expected_hash
    assert manifest["api_base"] == "http://127.0.0.1:9931/v1"
    assert manifest["server"]["path"].endswith("llama-server.exe")
    assert skipped == ["publisher/missing@q4_k_m"]
    assert len(manifest["models"]) == 1
    model = manifest["models"][0]
    assert model["registry_key"] == "publisher/model@q4_k_m"
    assert model["model_path"] == str(gguf)
    assert "--model" in model["start_args"]
    assert "--ctx-size" in model["start_args"]
    assert model["request_defaults"]["sampling"]["temperature"] == 0.7
    assert model["request_defaults"]["reasoning_format"] == "deepseek"


# ─────────────────────────────────────────────────────────────────────
# 5.1 VRAM-Formel
# ─────────────────────────────────────────────────────────────────────


class TestMaxCtxFromVram:
    """ctx = (usable_vram - model_gb) / (np × nl × hd × 2 × kv_bytes / 1e9)"""

    def test_basic_dense_model(self):
        # 11.47 GB model, 40 layers, 5120 dim, np=1, q8_0+iq4_nl (1.5)
        # kv per token = 1 * 40 * 5120 * 2 * 1.5 / 1e9 = 6.144e-4 GB
        # ctx = (15.3 - 11.47) / 6.144e-4 = 6,229
        ctx = _max_ctx_from_vram(11.47, 1, 40, 5120, 1.5)
        assert 6200 < ctx < 6400, f"unexpected ctx={ctx}"

    def test_dense_model_with_aggressive_quant(self):
        # q5_1 + iq4_nl = 0.625 + 0.5 = 1.125 (less memory)
        # ctx should be larger than with q8_0+iq4_nl
        ctx_aggressive = _max_ctx_from_vram(11.47, 1, 40, 5120, 1.125)
        ctx_default = _max_ctx_from_vram(11.47, 1, 40, 5120, 1.5)
        assert ctx_aggressive > ctx_default

    def test_n_parallel_halves_context(self):
        # np=2 → 2x the kv cache per slot → context ~half
        ctx_1 = _max_ctx_from_vram(11.47, 1, 40, 5120, 1.5)
        ctx_2 = _max_ctx_from_vram(11.47, 2, 40, 5120, 1.5)
        # Allow small tolerance
        assert 0.45 < (ctx_2 / ctx_1) < 0.55, f"ctx should halve with np=2: ctx_1={ctx_1}, ctx_2={ctx_2}"

    def test_returns_minimum_2048(self):
        # Massive model with no room: 14.9 GB of 15.3 GB usable
        ctx = _max_ctx_from_vram(14.9, 1, 40, 5120, 1.5)
        assert ctx >= 2048

    def test_zero_kv_bytes_returns_minimum(self):
        # Edge case: kv_bytes=0 would be division by zero
        ctx = _max_ctx_from_vram(10.0, 1, 40, 5120, 0)
        assert ctx == 2048

    def test_zero_layers_returns_minimum(self):
        # nl=0 → 0 kv per token → division by zero
        ctx = _max_ctx_from_vram(10.0, 1, 0, 5120, 1.5)
        assert ctx == 2048

    def test_larger_model_smaller_context(self):
        ctx_8gb = _max_ctx_from_vram(8.0, 1, 40, 5120, 1.5)
        ctx_12gb = _max_ctx_from_vram(12.0, 1, 40, 5120, 1.5)
        assert ctx_8gb > ctx_12gb

    def test_zero_dim_returns_minimum(self):
        # hd=0 → 0 kv per token
        ctx = _max_ctx_from_vram(10.0, 1, 40, 0, 1.5)
        assert ctx == 2048


class TestVramConstants:
    """VRAM thresholds from benchmark_config.py are correctly exposed."""

    def test_usable_vram_centralized(self):
        # 15.3 GB = 16 GB GPU minus driver/overhead
        assert _USABLE_VRAM_GB == 15.3

    def test_use_unified_threshold(self):
        assert _USE_UNIFIED_KV_CACHE_THRESHOLD_GB == 12.0

    def test_legacy_threshold(self):
        assert _LEGACY_MODEL_GB_THRESHOLD_GB == 9.0


class TestHeadlessValidation:
    """CI validation must not require local LM Studio state or GGUF files."""

    def test_ci_mode_skips_configs_and_gguf(self):
        registry = {
            "unsloth/test@q4_k_m": {
                "arch": "dense",
                "reasoning": "instruct",
                "capabilities": ["text"],
                "blueprint": "default_chat",
            }
        }
        with (
            patch.object(rt, "load_registry", return_value=registry),
            patch.object(rt, "read_lms_configs", side_effect=AssertionError("CI must be headless")),
            patch.object(rt, "_gguf_drift_errors", side_effect=AssertionError("CI must skip GGUF scans")),
        ):
            errors = rt.cmd_validate(ci=True)

        assert not any(errors.values())

    def test_ci_reports_canonical_identity_collision_as_blocker(self):
        registry = {
            "publisher/model@q4_k_m": {
                "arch": "dense",
                "reasoning": "instruct",
                "capabilities": ["text"],
                "blueprint": "default_chat",
            },
            "publisher/model@q4-k-m": {
                "arch": "dense",
                "reasoning": "instruct",
                "capabilities": ["text"],
                "blueprint": "default_chat",
            },
        }
        with (
            patch.object(rt, "load_registry", return_value=registry),
            patch.object(rt, "read_lms_configs", side_effect=AssertionError("CI must be headless")),
            patch.object(rt, "_gguf_drift_errors", side_effect=AssertionError("CI must skip GGUF scans")),
        ):
            errors = rt.cmd_validate(ci=True)

        assert errors["identity_collision"]
        assert "identity_collision" in rt._blocking_validation_errors(errors)

    def test_deepseek_r1_distill_reasoning_overrides_qwen2_base_architecture(self):
        registry = {
            "roleplaiapp/deepseek-r1-distill-qwen-32b@q2_k": {
                "arch": "dense",
                "architecture_family": "qwen2",
                "reasoning": "thinking",
                "capabilities": ["text"],
                "blueprint": "reasoning_assistant",
            },
            "publisher/qwen2-base@q4_k_m": {
                "arch": "dense",
                "architecture_family": "qwen2",
                "reasoning": "thinking",
                "capabilities": ["text"],
                "blueprint": "default_chat",
            },
        }
        with (
            patch.object(rt, "load_registry", return_value=registry),
            patch.object(rt, "read_lms_configs", side_effect=AssertionError("CI must be headless")),
            patch.object(rt, "_gguf_drift_errors", side_effect=AssertionError("CI must skip GGUF scans")),
        ):
            errors = rt.cmd_validate(ci=True)

        assert len(errors["reasoning_arch_mismatch"]) == 1
        assert errors["reasoning_arch_mismatch"][0].startswith("publisher/qwen2-base@q4_k_m:")


class TestGuiConfigRegistrySync:
    """GUI tuning can be imported explicitly without weakening Registry SSOT."""

    def _registry_and_configs(self, tmp_path):
        registry = {
            "publisher/model@q4_k_m": {
                "offload": 1.0,
                "useUnifiedKvCache": False,
                "context_length": 16384,
                "k_cache": "q8_0",
                "v_cache": "q8_0",
            }
        }
        registry_path = tmp_path / "model_registry.yaml"
        registry_path.touch()
        configs = [
            {
                "publisher": "publisher",
                "dir_name": "model",
                "offload": 0.75,
                "use_unified_kv": True,
                "context_length": 8192,
                "k_cache": "q5_1",
                "v_cache": "q5_1",
                "json_path": tmp_path / "model.json",
            }
        ]
        return registry, registry_path, configs

    def test_report_mode_does_not_write(self, tmp_path, capsys):
        registry, registry_path, configs = self._registry_and_configs(tmp_path)
        with (
            patch.object(rt, "REGISTRY_PATH", registry_path),
            patch.object(rt, "load_registry", return_value=registry),
            patch.object(rt, "read_lms_configs", return_value=configs),
            patch.object(rt, "save_registry") as save_registry,
        ):
            rt.cmd_sync_from_configs()

        assert registry["publisher/model@q4_k_m"]["offload"] == 1.0
        assert registry["publisher/model@q4_k_m"]["useUnifiedKvCache"] is False
        save_registry.assert_not_called()
        output = capsys.readouterr().out
        assert "5 Drifts" in output
        assert "[VORSCHLAG] publisher/model@q4_k_m: context_length" in output
        assert str(configs[0]["json_path"]) in output

    def test_write_mode_persists_gui_values(self, tmp_path):
        registry, registry_path, configs = self._registry_and_configs(tmp_path)
        with (
            patch.object(rt, "REGISTRY_PATH", registry_path),
            patch.object(rt, "load_registry", return_value=registry),
            patch.object(rt, "read_lms_configs", return_value=configs),
            patch.object(rt, "save_registry") as save_registry,
        ):
            rt.cmd_sync_from_configs(write=True)

        entry = registry["publisher/model@q4_k_m"]
        assert entry["offload"] == 0.75
        assert entry["useUnifiedKvCache"] is True
        assert entry["context_length"] == 8192
        assert entry["k_cache"] == "q5_1"
        assert entry["v_cache"] == "q5_1"
        save_registry.assert_called_once_with(registry)

    def test_write_context_mode_only_persists_context(self, tmp_path):
        registry, registry_path, configs = self._registry_and_configs(tmp_path)
        with (
            patch.object(rt, "REGISTRY_PATH", registry_path),
            patch.object(rt, "load_registry", return_value=registry),
            patch.object(rt, "read_lms_configs", return_value=configs),
            patch.object(rt, "save_registry") as save_registry,
        ):
            rt.cmd_sync_from_configs(write_context=True)

        entry = registry["publisher/model@q4_k_m"]
        assert entry["context_length"] == 8192
        assert entry["offload"] == 1.0
        assert entry["useUnifiedKvCache"] is False
        assert entry["k_cache"] == "q8_0"
        assert entry["v_cache"] == "q8_0"
        save_registry.assert_called_once_with(registry)

    def test_write_experts_mode_imports_only_tested_runtime_value(self, tmp_path):
        registry, registry_path, configs = self._registry_and_configs(tmp_path)
        registry["publisher/model@q4_k_m"]["experts"] = 16
        configs[0]["num_experts"] = 24
        with (
            patch.object(rt, "REGISTRY_PATH", registry_path),
            patch.object(rt, "load_registry", return_value=registry),
            patch.object(rt, "read_lms_configs", return_value=configs),
            patch.object(rt, "save_registry") as save_registry,
        ):
            rt.cmd_sync_from_configs(write_experts=True)

        entry = registry["publisher/model@q4_k_m"]
        assert entry["experts"] == 24
        assert entry["context_length"] == 16384
        assert entry["offload"] == 1.0
        assert entry["useUnifiedKvCache"] is False
        assert entry["k_cache"] == "q8_0"
        assert entry["v_cache"] == "q8_0"
        save_registry.assert_called_once_with(registry)

    def test_import_mode_reads_loaded_lms_expert_value_when_json_omits_it(self, tmp_path, capsys):
        registry, registry_path, configs = self._registry_and_configs(tmp_path)
        entry = registry["publisher/model@q4_k_m"]
        entry.update({"arch": "moe", "max_experts": 32})
        with (
            patch.object(rt, "REGISTRY_PATH", registry_path),
            patch.object(rt, "load_registry", return_value=registry),
            patch.object(rt, "read_lms_configs", return_value=configs),
            patch.object(
                rt,
                "_read_lms_loaded_models",
                return_value={
                    "models": [
                        {
                            "key": "publisher/model",
                            "publisher": "publisher",
                            "quantization": {"name": "Q4_K_M"},
                            "loaded_instances": [
                                {"id": "loaded-model", "config": {"num_experts": 24}}
                            ],
                        }
                    ]
                },
            ),
            patch.object(rt, "save_registry") as save_registry,
        ):
            rt.cmd_sync_from_configs(write=True)

        assert entry["experts"] == 24
        assert "LM Studio native API loaded instance" in capsys.readouterr().out
        save_registry.assert_called_once_with(registry)

    def test_live_lms_expert_conflict_is_not_imported(self, tmp_path, capsys):
        registry, registry_path, configs = self._registry_and_configs(tmp_path)
        entry = registry["publisher/model@q4_k_m"]
        entry.update({"arch": "moe", "max_experts": 16})
        with (
            patch.object(rt, "REGISTRY_PATH", registry_path),
            patch.object(rt, "load_registry", return_value=registry),
            patch.object(rt, "read_lms_configs", return_value=configs),
            patch.object(
                rt,
                "_read_lms_loaded_models",
                return_value={
                    "models": [
                        {
                            "key": "publisher/model",
                            "publisher": "publisher",
                            "quantization": {"name": "Q4_K_M"},
                            "loaded_instances": [
                                {"id": "loaded-model", "config": {"num_experts": 24}}
                            ],
                        }
                    ]
                },
            ),
            patch.object(rt, "save_registry") as save_registry,
        ):
            rt.cmd_sync_from_configs(write=True)

        assert "experts" not in entry
        assert "exceeds GGUF-owned max_experts=16" in capsys.readouterr().out
        save_registry.assert_called_once_with(registry)

    def test_loaded_lms_expert_instances_with_disagreement_are_ambiguous(self):
        registry = {"publisher/model@q4_k_m": {"arch": "moe"}}
        values, conflicts = rt._loaded_lms_expert_values(
            registry,
            {
                "models": [
                    {
                        "key": "publisher/model",
                        "publisher": "publisher",
                        "quantization": {"name": "Q4_K_M"},
                        "loaded_instances": [
                            {"config": {"num_experts": 16}},
                            {"config": {"num_experts": 24}},
                        ],
                    }
                ]
            },
        )

        assert values == {}
        assert conflicts == {"publisher/model@q4_k_m": (16, 24)}

    def test_report_mode_detects_kv_quantization_drift(self, tmp_path, capsys):
        registry, registry_path, configs = self._registry_and_configs(tmp_path)
        with (
            patch.object(rt, "REGISTRY_PATH", registry_path),
            patch.object(rt, "load_registry", return_value=registry),
            patch.object(rt, "read_lms_configs", return_value=configs),
            patch.object(rt, "save_registry") as save_registry,
        ):
            rt.cmd_sync_from_configs()

        assert registry["publisher/model@q4_k_m"]["k_cache"] == "q8_0"
        save_registry.assert_not_called()
        assert "k_cache" in capsys.readouterr().out

    def test_conflicting_gui_values_are_proposed_but_never_chosen(self, tmp_path):
        registry, _registry_path, configs = self._registry_and_configs(tmp_path)
        second_config = dict(configs[0])
        second_config["context_length"] = 12288
        second_config["json_path"] = tmp_path / "model-duplicate.json"

        proposals, skipped, conflicts = rt._build_config_sync_proposal(
            registry,
            [configs[0], second_config],
            None,
            (("context_length", "context_length"),),
        )

        assert skipped == 0
        assert conflicts == 1
        assert len(proposals) == 1
        assert proposals[0].conflict is True
        assert proposals[0].proposed == (8192, 12288)
        assert registry["publisher/model@q4_k_m"]["context_length"] == 16384

    def test_config_import_uses_canonical_quant_key_when_registry_has_legacy_alias(self, tmp_path):
        canonical_key = "freedomaisvr/gemma-4-12b-it-qat@nvfp4"
        legacy_key = "freedomaisvr/gemma-4-12b-it-qat-nvfp4@nvfp4"
        registry = {
            legacy_key: {"context_length": 131072, "max_context_length": 262144},
            canonical_key: {"context_length": 65536, "max_context_length": 262144},
        }
        config = {
            "publisher": "FreedomAISVR",
            "dir_name": "Gemma-4-12B-it-QAT-NVFP4-GGUF",
            "file_name": "gemma-4-12b-it-qat-nvfp4.gguf.json",
            "quant": "nvfp4",
            "context_length": 262144,
            "json_path": tmp_path / "gemma-nvfp4.json",
        }
        installed_model = {
            "modelKey": "gemma-4-12b-it-qat",
            "publisher": "FreedomAISVR",
            "path": "FreedomAISVR/Gemma-4-12B-it-QAT-NVFP4-GGUF/gemma-4-12b-it-qat-nvfp4.gguf",
        }

        registry_path = tmp_path / "model_registry.yaml"
        registry_path.touch()
        inventory = rt.RegistryInventory(
            registry, [installed_model], [installed_model], [config], []
        )
        with (
            patch.object(rt, "REGISTRY_PATH", registry_path),
            patch.object(rt, "save_registry") as save_registry,
        ):
            proposals = rt.cmd_sync_from_configs(
                write=True,
                installed_models=[installed_model],
                inventory=inventory,
            )

        assert len(proposals) == 1
        assert proposals[0].model_key == canonical_key
        assert proposals[0].current == 65536
        assert proposals[0].proposed == 262144
        assert proposals[0].conflict is False
        assert registry[canonical_key]["context_length"] == 262144
        assert registry[legacy_key]["context_length"] == 131072
        save_registry.assert_called_once_with(registry)

    @pytest.mark.parametrize(
        ("field", "config_field", "current", "proposed", "limit_field", "limit"),
        [
            ("context_length", "context_length", 16384, 32768, "max_context_length", 24576),
            ("experts", "num_experts", 16, 40, "max_experts", 32),
        ],
    )
    def test_values_over_gguf_limits_are_conflicts(
        self, tmp_path, field, config_field, current, proposed, limit_field, limit
    ):
        registry, _registry_path, configs = self._registry_and_configs(tmp_path)
        entry = registry["publisher/model@q4_k_m"]
        entry[field] = current
        entry[limit_field] = limit
        configs[0][config_field] = proposed

        proposals, skipped, conflicts = rt._build_config_sync_proposal(
            registry,
            configs,
            None,
            ((field, config_field),),
        )

        assert skipped == 0
        assert conflicts == 1
        assert len(proposals) == 1
        assert proposals[0].conflict is True
        assert proposals[0].proposed == proposed
        assert "exceeds GGUF-owned" in (proposals[0].problem or "")
        assert entry[field] == current

    def test_lms_parser_extracts_nested_kv_quantization(self, tmp_path):
        root = tmp_path / "configs"
        model_dir = root / "publisher" / "model"
        model_dir.mkdir(parents=True)
        path = model_dir / "model.gguf.json"
        path.write_text(
            json.dumps(
                {
                    "load": {
                        "fields": [
                            {
                                "key": "llm.load.llama.kCacheQuantizationType",
                                "value": {"checked": True, "value": "q5_1"},
                            },
                            {
                                "key": "llm.load.llama.vCacheQuantizationType",
                                "value": {"checked": True, "value": "q8_0"},
                            },
                            {
                                "key": "llm.load.numExperts",
                                "value": 24,
                            },
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        ab._LMS_CONFIGS_CACHE.pop(str(root), None)

        configs = rt.read_lms_configs(root)

        assert configs[0]["k_cache"] == "q5_1"
        assert configs[0]["v_cache"] == "q8_0"
        assert configs[0]["num_experts"] == 24


class TestKVBytesTable:
    """Byte-per-element mapping for each quantization type."""

    def test_q8_0(self):
        assert _KV_BYTES["q8_0"] == 1.0

    def test_q5_1(self):
        assert _KV_BYTES["q5_1"] == 0.625

    def test_iq4_nl(self):
        assert _KV_BYTES["iq4_nl"] == 0.5

    def test_f16(self):
        assert _KV_BYTES["f16"] == 2.0


# ─────────────────────────────────────────────────────────────────────
# 5.2 Match-Kaskade in cmd_configs
# ─────────────────────────────────────────────────────────────────────


class TestMatchCascade:
    """Match priority: exact > suffix > base > None."""

    @pytest.fixture
    def fake_config(self, tmp_path):
        """Create a fake LM Studio config JSON file."""
        cfg_dir = tmp_path / "user-concrete-model-default-config"
        cfg_dir.mkdir()
        return cfg_dir

    def _make_config(self, dir_path, json_path, **fields):
        """Write a JSON config with given load.fields."""
        dir_path.mkdir(parents=True, exist_ok=True)
        data = {
            "operation": {"fields": []},
            "load": {"fields": [{"key": k, "value": v} for k, v in fields.items()]},
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return json_path

    def test_no_arch_data_falls_back_to_benchmark_threshold(self, fake_config, capsys):
        # Model with no n_layers/hidden_dim, model_gb >= 12 → UKV on (Empfehlung)
        sub = fake_config / "publisher"
        json_path = self._make_config(sub, sub / "m.json", **{"llm.load.contextLength": 16384})
        registry = {
            "publisher/m": {
                "file_size_bytes": 14_000_000_000,  # 14 GB (>= 12 GB threshold)
                # No n_layers, no hidden_dim
                "context_length": 16384,
                "num_parallel": 1,
                "k_cache": "q8_0",
                "v_cache": "iq4_nl",
            }
        }
        with (
            patch.object(rt, "load_registry", return_value=registry),
            patch.object(rt, "CONFIG_ROOT", fake_config),
            patch.object(
                rt,
                "read_lms_configs",
                return_value=[
                    {
                        "dir_name": "m",
                        "publisher": "publisher",
                        "context_length": 16384,
                        "offload": 1.0,
                        "num_parallel": 1,
                        "use_unified_kv": True,
                        "json_path": json_path,
                    }
                ],
            ),
        ):
            result = rt.cmd_suggest()
        out = capsys.readouterr().out
        # Dry-run: JSON wurde NICHT verändert (kein UKV-Feld geschrieben)
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        fields = {f["key"]: f["value"] for f in data["load"]["fields"]}
        assert "llm.load.useUnifiedKvCache" not in fields
        assert result["shown"] == 1
        assert "useUnifiedKvCache" in out

    def test_arch_data_uses_precise_formula(self, fake_config, capsys):
        # Model with arch data, np=1, small context → UKV OFF (Empfehlung)
        sub = fake_config / "publisher"
        json_path = self._make_config(sub, sub / "m.json", **{"llm.load.contextLength": 2048})
        # 4 GB model, 40 layers × 5120 dim, q8_0+iq4_nl, ctx=2048
        # total = 4 + (40*5120*2*1.5*2048/1e9) = 4 + 0.63 = 4.63 GB
        # 4.63 < 14.0 → UKV OFF
        registry = {
            "publisher/m": {
                "file_size_bytes": 4_000_000_000,
                "n_layers": 40,
                "hidden_dim": 5120,
                "context_length": 2048,  # Native cap = effective cap
                "num_parallel": 1,
                "k_cache": "q8_0",
                "v_cache": "iq4_nl",
            }
        }
        with (
            patch.object(rt, "load_registry", return_value=registry),
            patch.object(rt, "CONFIG_ROOT", fake_config),
            patch.object(
                rt,
                "read_lms_configs",
                return_value=[
                    {
                        "dir_name": "m",
                        "publisher": "publisher",
                        "context_length": 2048,
                        "offload": 1.0,
                        "num_parallel": 1,
                        "use_unified_kv": False,
                        "json_path": json_path,
                    }
                ],
            ),
        ):
            result = rt.cmd_suggest()
        out = capsys.readouterr().out
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        fields = {f["key"]: f["value"] for f in data["load"]["fields"]}
        # Dry-run: kein UKV-Feld geschrieben
        assert "llm.load.useUnifiedKvCache" not in fields
        assert result["shown"] == 1
        assert "useUnifiedKvCache" in out

    def test_benchmark_context_limit_override(self, fake_config, capsys):
        # contextLength is never touched by cmd_suggest (dry-run):
        # the user's manually set value is preserved.
        sub = fake_config / "publisher"
        json_path = self._make_config(sub, sub / "m.json", **{"llm.load.contextLength": 16384})
        registry = {
            "publisher/m": {
                "file_size_bytes": 8_000_000_000,
                "n_layers": 40,
                "hidden_dim": 5120,
                "context_length": 16384,
                "num_parallel": 1,
                "k_cache": "q8_0",
                "v_cache": "iq4_nl",
                "benchmark_context_limit": 4096,
            }
        }
        with (
            patch.object(rt, "load_registry", return_value=registry),
            patch.object(rt, "CONFIG_ROOT", fake_config),
            patch.object(
                rt,
                "read_lms_configs",
                return_value=[
                    {
                        "dir_name": "m",
                        "publisher": "publisher",
                        "context_length": 16384,
                        "offload": 1.0,
                        "num_parallel": 1,
                        "use_unified_kv": False,
                        "json_path": json_path,
                    }
                ],
            ),
        ):
            result = rt.cmd_suggest()
        capsys.readouterr()
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        fields = {f["key"]: f["value"] for f in data["load"]["fields"]}
        # contextLength was NOT overwritten — user's value (16384) preserved
        assert fields.get("llm.load.contextLength") == 16384
        assert len(fields) == 1
        assert result["shown"] == 1

    def test_context_capped_at_native(self, fake_config, capsys):
        # contextLength is never touched by cmd_suggest (dry-run):
        # the user's manually set value is preserved.
        sub = fake_config / "publisher"
        json_path = self._make_config(sub, sub / "m.json", **{"llm.load.contextLength": 16384})
        # Tiny model: 4 GB
        registry = {
            "publisher/m": {
                "file_size_bytes": 4_000_000_000,
                "n_layers": 40,
                "hidden_dim": 5120,
                "context_length": 16384,
                "num_parallel": 1,
                "k_cache": "q8_0",
                "v_cache": "iq4_nl",
            }
        }
        with (
            patch.object(rt, "load_registry", return_value=registry),
            patch.object(rt, "CONFIG_ROOT", fake_config),
            patch.object(
                rt,
                "read_lms_configs",
                return_value=[
                    {
                        "dir_name": "m",
                        "publisher": "publisher",
                        "context_length": 16384,
                        "offload": 1.0,
                        "num_parallel": 1,
                        "use_unified_kv": False,
                        "json_path": json_path,
                    }
                ],
            ),
        ):
            result = rt.cmd_suggest()
        capsys.readouterr()
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        fields = {f["key"]: f["value"] for f in data["load"]["fields"]}
        # contextLength was NOT overwritten — user's value (16384) preserved
        assert fields.get("llm.load.contextLength") == 16384
        assert len(fields) == 1
        assert result["shown"] == 1


# ─────────────────────────────────────────────────────────────────────
# 5.3 _infer_num_parallel / _classify_arch
# ─────────────────────────────────────────────────────────────────────


class TestClassifyArch:
    """Classification nach Refactoring 2026-07-31: GGUF expert_count als
    Single Source of Truth für MoE, "mtp"-Keyword im Namen, sonst dense."""

    def test_gguf_with_experts_returns_moe(self, tmp_path):
        fake = tmp_path / "model.gguf"
        fake.write_bytes(b"x")
        with patch.object(rt, "_gguf_has_experts", return_value=True) as g:
            assert _classify_arch("some-model", str(fake)) == "moe"
            g.assert_called_once_with(str(fake))

    def test_gguf_without_experts_falls_back_to_mtp_keyword(self, tmp_path):
        fake = tmp_path / "model.gguf"
        fake.write_bytes(b"x")
        with patch.object(rt, "_gguf_has_experts", return_value=False):
            assert _classify_arch("qwen3.6-27b-mtp", str(fake)) == "mtp"

    def test_gguf_without_experts_dense(self, tmp_path):
        fake = tmp_path / "model.gguf"
        fake.write_bytes(b"x")
        with patch.object(rt, "_gguf_has_experts", return_value=False):
            assert _classify_arch("llama-3.1-8b", str(fake)) == "dense"

    def test_missing_path_ignores_gguf(self):
        assert _classify_arch("gemma-4-26b-a4b", "C:/does/not/exist.gguf") == "dense"

    def test_mtp_keyword_in_identifier(self):
        assert _classify_arch("unsloth/qwen3.6-27b-mtp") == "mtp"

    def test_empty_input_returns_dense(self):
        assert _classify_arch("") == "dense"


# ─────────────────────────────────────────────────────────────────────
# Integration: cmd_suggest end-to-end
# ─────────────────────────────────────────────────────────────────────


class TestCmdSuggestIntegration:
    """End-to-end cmd_suggest() with mocked registry + LMS configs."""

    def test_skips_models_with_no_match(self, tmp_path):
        # A JSON config that doesn't match any registry entry is skipped
        cfg_dir = tmp_path / "user-concrete-model-default-config" / "pub"
        cfg_dir.mkdir(parents=True)
        json_path = cfg_dir / "unmatched.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "operation": {"fields": []},
                    "load": {"fields": []},
                },
                f,
            )
        with (
            patch.object(rt, "load_registry", return_value={}),
            patch.object(rt, "CONFIG_ROOT", tmp_path / "user-concrete-model-default-config"),
            patch.object(
                rt,
                "read_lms_configs",
                return_value=[
                    {
                        "dir_name": "unmatched",
                        "publisher": "pub",
                        "context_length": 16384,
                        "offload": 1.0,
                        "num_parallel": 1,
                        "use_unified_kv": False,
                        "json_path": json_path,
                    }
                ],
            ),
        ):
            # Should not raise, should not modify the file
            result = rt.cmd_suggest()
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # JSON should be unchanged (no new fields added)
        assert data["load"]["fields"] == []
        assert result["skipped"] == 1
        assert result["shown"] == 0


# ─────────────────────────────────────────────────────────────────────
# cmd_fix_np: exaktes lms-Matching + Duplikat-Kollaps
# ─────────────────────────────────────────────────────────────────────


class TestFixNp:
    """cmd_fix_np — seit 13.08. deprecated: np ist feste Benchmark-Policy
    (SS<=5 → 1, sonst 4) und kein Registry-Feld mehr. Der Stub informiert
    nur und schreibt NICHT.
    """

    def test_fix_np_is_deprecated_stub(self, capsys):
        saved = {}
        with (
            patch.object(rt, "load_registry", return_value={"x/y": {"file_size_bytes": 1}}),
            patch.object(rt, "save_registry", side_effect=lambda r: saved.update(r)),
        ):
            rt.cmd_fix_np()
        out = capsys.readouterr().out
        assert "fix-np entfällt" in out
        assert saved == {}  # nichts geschrieben

    def test_normalize_variants_strips_publisher_and_underscore(self):
        assert rt._normalize_variants("unsloth/phi-4") == {"phi-4"}
        assert rt._normalize_variants("['microsoft', 'unsloth']/phi-4") == {"phi-4"}
        assert rt._normalize_variants("mistralai_magistral-small-2509") == {
            "mistralai-magistral-small-2509",
        }
        assert rt._normalize_variants("qwen3.6-27b@q5_0") == {"qwen3-6-27b"}


# ─────────────────────────────────────────────────────────────────────
# GGUF-Reasoning-Erkennung (_read_gguf_arch / _detect_reasoning_from_template)
# ─────────────────────────────────────────────────────────────────────


def _make_mini_gguf(
    block_count: int, embedding_length: int, chat_template: str | None, context_length: int = 16384
) -> bytes:
    """Synthetischer GGUF-Header: block_count/embedding_length/context_length VOR chat_template."""
    import struct

    buf = bytearray(b"GGUF")
    buf += struct.pack("<IQ", 3, 0)  # version, tensor_count
    kvs = []
    architecture = b"qwen2"
    for key, vtype, payload in [
        ("general.architecture", 8, struct.pack("<Q", len(architecture)) + architecture),
        ("qwen2.block_count", 4, struct.pack("<I", block_count)),
        ("qwen2.embedding_length", 4, struct.pack("<I", embedding_length)),
        ("qwen2.context_length", 4, struct.pack("<I", context_length)),
    ]:
        kb = key.encode("utf-8")
        kvs.append((kb, vtype, payload))
    if chat_template is not None:
        tb = chat_template.encode("utf-8")
        kvs.append((b"tokenizer.chat_template", 8, struct.pack("<Q", len(tb)) + tb))
    buf += struct.pack("<Q", len(kvs))
    for kb, vtype, payload in kvs:
        buf += struct.pack("<Q", len(kb)) + kb
        buf += struct.pack("<I", vtype)
        buf += payload
    return bytes(buf)


def test_read_gguf_base_arch_returns_general_architecture(tmp_path):
    p = tmp_path / "model.gguf"
    p.write_bytes(_make_mini_gguf(48, 5120, None))
    assert rt._read_gguf_base_arch(str(p)) == "qwen2"


def test_read_gguf_base_arch_does_not_load_tensor_reader(monkeypatch, tmp_path):
    class ForbiddenReader:
        def __init__(self, _path):
            raise AssertionError("header scan must not construct GGUFReader")

    import types

    path = tmp_path / "model.gguf"
    path.write_bytes(_make_mini_gguf(48, 5120, None))
    monkeypatch.setitem(sys.modules, "gguf", types.SimpleNamespace(GGUFReader=ForbiddenReader))
    assert rt._read_gguf_base_arch(str(path)) == "qwen2"


class TestReadGgufArchReasoning:
    """_read_gguf_arch liest tokenizer.chat_template auch NACH block_count/embedding_length."""

    def test_reasoning_detected_when_template_after_arch(self, tmp_path):
        p = tmp_path / "model.gguf"
        p.write_bytes(_make_mini_gguf(48, 5120, "{% if enable_thinking %}<think>{% endif %}"))
        nl, hd, is_reasoning, ctx, exp = rt._read_gguf_arch(str(p))
        assert nl == 48
        assert hd == 5120
        assert is_reasoning is True
        assert ctx == 16384
        assert exp is None  # kein expert_count-Key in Mini-GGUF

    def test_no_template_yields_false(self, tmp_path):
        p = tmp_path / "model.gguf"
        p.write_bytes(_make_mini_gguf(48, 5120, None))
        nl, hd, is_reasoning, ctx, exp = rt._read_gguf_arch(str(p))
        assert (nl, hd, is_reasoning, ctx) == (48, 5120, False, 16384)
        assert exp is None

    def test_corrupt_file_yields_none(self, tmp_path):
        p = tmp_path / "broken.gguf"
        p.write_bytes(b"not a gguf file")
        assert rt._read_gguf_arch(str(p)) == (None, None, None, None, None)


class TestDetectReasoningFromTemplate:
    """Template-Marker der real installierten Modelle (deepseek-r1-distill, gpt-oss Harmony)."""

    def test_enable_thinking_marker(self):
        assert rt._detect_reasoning_from_template("{% if enable_thinking %}...{% endif %}") is True

    def test_reasoning_effort_marker(self):
        assert rt._detect_reasoning_from_template("{% if reasoning_effort %}...{% endif %}") is True

    def test_think_tag_marker(self):
        assert rt._detect_reasoning_from_template("{% if '</think>' in content %}") is True

    def test_analysis_channel_marker(self):
        assert rt._detect_reasoning_from_template("<|start|>assistant<|channel|>analysis<|message|>") is True

    def test_plain_qwen2_template_is_not_reasoning(self):
        assert rt._detect_reasoning_from_template("{% for message in messages %}...{% endfor %}") is False


# ─────────────────────────────────────────────────────────────────────
# 5.8 rm command (Fix 2026-07-31: Registry bereinigen)
# ─────────────────────────────────────────────────────────────────────


class TestCmdRm:
    """registry_tool.py rm – Registry-Eintrag löschen (+ optional Dateien)."""

    def _write_registry(self, path, entries):
        with open(path, "w", encoding="utf-8") as f:
            rt.y.dump(entries, f)

    def test_removes_entry_by_full_key(self, tmp_path, monkeypatch):
        reg_path = tmp_path / "registry.yaml"
        self._write_registry(
            reg_path,
            {
                "Intel/gpt-oss-20b-gguf-q4ks-AutoRound": {"reasoning": "thinking", "offload": 1.0},
                "openai/gpt-oss-20b": {"reasoning": "thinking"},
            },
        )
        monkeypatch.setattr(rt, "REGISTRY_PATH", reg_path)
        monkeypatch.setattr(rt, "CONFIG_ROOT", tmp_path / "empty")
        rc = rt.cmd_rm("Intel/gpt-oss-20b-gguf-q4ks-AutoRound", assume_yes=True)
        assert rc == 0
        reg = rt.load_registry(reg_path)
        assert "Intel/gpt-oss-20b-gguf-q4ks-AutoRound" not in reg
        assert "openai/gpt-oss-20b" in reg

    def test_removes_entry_by_short_key(self, tmp_path, monkeypatch):
        reg_path = tmp_path / "registry.yaml"
        self._write_registry(reg_path, {"Intel/gpt-oss-20b-gguf-q4ks-AutoRound": {"reasoning": "thinking"}})
        monkeypatch.setattr(rt, "REGISTRY_PATH", reg_path)
        monkeypatch.setattr(rt, "CONFIG_ROOT", tmp_path / "empty")
        assert rt.cmd_rm("gpt-oss-20b-gguf-q4ks-AutoRound", assume_yes=True) == 0
        assert rt.load_registry(reg_path) == {}

    def test_unknown_key_returns_error(self, tmp_path, monkeypatch):
        reg_path = tmp_path / "registry.yaml"
        self._write_registry(reg_path, {"openai/gpt-oss-20b": {"reasoning": "thinking"}})
        monkeypatch.setattr(rt, "REGISTRY_PATH", reg_path)
        monkeypatch.setattr(rt, "CONFIG_ROOT", tmp_path / "empty")
        assert rt.cmd_rm("nicht-vorhanden", assume_yes=True) == 1
        assert "openai/gpt-oss-20b" in rt.load_registry(reg_path)

    def test_abort_without_yes(self, tmp_path, monkeypatch):
        reg_path = tmp_path / "registry.yaml"
        self._write_registry(reg_path, {"openai/gpt-oss-20b": {"reasoning": "thinking"}})
        monkeypatch.setattr(rt, "REGISTRY_PATH", reg_path)
        monkeypatch.setattr(rt, "CONFIG_ROOT", tmp_path / "empty")
        monkeypatch.setattr("builtins.input", lambda *a, **k: "n")
        assert rt.cmd_rm("openai/gpt-oss-20b") == 0
        assert "openai/gpt-oss-20b" in rt.load_registry(reg_path)

    def test_delete_files_removes_config_and_backup(self, tmp_path, monkeypatch):
        reg_path = tmp_path / "registry.yaml"
        self._write_registry(
            reg_path,
            {
                "Intel/gpt-oss-20b-gguf-q4ks-AutoRound": {"reasoning": "thinking"},
            },
        )
        cfg_dir = tmp_path / "configs" / "Intel" / "gpt-oss-20b-gguf-q4ks-AutoRound"
        cfg_dir.mkdir(parents=True)
        cfg_file = cfg_dir / "gpt-oss-20b-32x2.4B-Q4_K_S.gguf.json"
        cfg_file.write_text(json.dumps({"operation": {"fields": []}}), encoding="utf-8")
        backup = cfg_dir / "gpt-oss-20b-32x2.4B-Q4_K_S.gguf.json.bak-20260731_120000"
        backup.write_text("backup", encoding="utf-8")
        monkeypatch.setattr(rt, "REGISTRY_PATH", reg_path)
        monkeypatch.setattr(rt, "CONFIG_ROOT", tmp_path / "configs")
        assert rt.cmd_rm("Intel/gpt-oss-20b-gguf-q4ks-AutoRound", delete_files=True, assume_yes=True) == 0
        assert not cfg_file.exists()
        assert not backup.exists()
        assert rt.load_registry(reg_path) == {}


class TestCmdQuarantineMissing:
    """registry_tool.py quarantine-missing – nicht-installierte Modelle in Quarantäne."""

    def _setup(self, tmp_path, monkeypatch, lms_models, entries, with_config=True):
        reg_path = tmp_path / "registry.yaml"
        with open(reg_path, "w", encoding="utf-8") as f:
            rt.y.dump(entries, f)
        cfg_root = tmp_path / "configs"
        if with_config:
            cfg_dir = cfg_root / "mradermacher" / "Nemotron-Cascade-14B-Thinking-MXFP4-GGUF"
            cfg_dir.mkdir(parents=True)
            cfg_file = cfg_dir / "Nemotron-Cascade-14B-Thinking-MXFP4.gguf.json"
            cfg_file.write_text(json.dumps({"operation": {"fields": []}}), encoding="utf-8")
        monkeypatch.setattr(rt, "REGISTRY_PATH", reg_path)
        monkeypatch.setattr(rt, "CONFIG_ROOT", cfg_root)
        monkeypatch.setattr(rt, "MODELS_CACHE", tmp_path / "models")
        monkeypatch.setattr(rt, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(rt, "_run_lms_ls", lambda: lms_models)
        monkeypatch.setattr(rt, "_gguf_for_key_exists", lambda key, candidates=None: False)

        def collect_inventory():
            benchmark_models = rt._benchmark_lms_models(lms_models)
            return rt.RegistryInventory(
                rt.load_registry(reg_path), lms_models, benchmark_models,
                rt.read_lms_configs(cfg_root), [], True,
            )

        monkeypatch.setattr(rt, "_collect_registry_inventory", collect_inventory)
        return reg_path

    def test_missing_entry_quarantined(self, tmp_path, monkeypatch):
        reg_path = self._setup(
            tmp_path,
            monkeypatch,
            lms_models=[{"modelKey": "openai/gpt-oss-20b"}],
            entries={
                "mradermacher/nemotron-cascade-14b-thinking": {"reasoning": "thinking", "blueprint": "full"},
                "openai/gpt-oss-20b": {"reasoning": "thinking", "blueprint": "full"},
            },
        )
        assert rt.cmd_quarantine_missing(dry_run=False) == 0
        reg = rt.load_registry(reg_path)
        assert "mradermacher/nemotron-cascade-14b-thinking" not in reg
        assert "openai/gpt-oss-20b" in reg
        moved = list((tmp_path / "configs").glob("_quarantine_missing_*/**/*.json"))
        assert len(moved) == 1
        assert "Nemotron-Cascade-14B-Thinking-MXFP4.gguf.json" in str(moved[0])

    def test_missing_kept_when_gguf_exists(self, tmp_path, monkeypatch):
        reg_path = self._setup(
            tmp_path,
            monkeypatch,
            lms_models=[{"modelKey": "openai/gpt-oss-20b"}],
            entries={
                "mradermacher/nemotron-cascade-14b-thinking": {"reasoning": "thinking", "blueprint": "full"},
            },
            with_config=False,
        )
        monkeypatch.setattr(rt, "_gguf_for_key_exists", lambda key, candidates=None: True)
        assert rt.cmd_quarantine_missing(dry_run=False) == 2
        assert "mradermacher/nemotron-cascade-14b-thinking" in rt.load_registry(reg_path)
        assert not list((tmp_path / "configs").glob("_quarantine_missing_*"))

    def test_dry_run_writes_nothing(self, tmp_path, monkeypatch):
        reg_path = self._setup(
            tmp_path,
            monkeypatch,
            lms_models=[{"modelKey": "openai/gpt-oss-20b"}],
            entries={
                "mradermacher/nemotron-cascade-14b-thinking": {"reasoning": "thinking", "blueprint": "full"},
            },
        )
        assert rt.cmd_quarantine_missing() == 0
        assert "mradermacher/nemotron-cascade-14b-thinking" in rt.load_registry(reg_path)
        assert not list((tmp_path / "configs").glob("_quarantine_missing_*"))

    def test_quarantine_registry_write_failure_restores_moved_config(self, tmp_path, monkeypatch):
        reg_path = self._setup(
            tmp_path,
            monkeypatch,
            lms_models=[{"modelKey": "openai/gpt-oss-20b"}],
            entries={
                "mradermacher/nemotron-cascade-14b-thinking": {
                    "reasoning": "thinking",
                    "blueprint": "full",
                    "context_length": 32768,
                },
            },
        )
        source_config = next((tmp_path / "configs").glob("**/*.json"))
        monkeypatch.setattr(
            rt, "save_registry", lambda _registry: (_ for _ in ()).throw(OSError("disk full"))
        )

        assert rt.cmd_quarantine_missing(dry_run=False) == 1

        assert "mradermacher/nemotron-cascade-14b-thinking" in rt.load_registry(reg_path)
        assert source_config.exists()
        assert not list((tmp_path / "configs").glob("_quarantine_missing_*"))
        assert not list((tmp_path / "doc-git" / "Review-Artifacts").glob("quarantine_registry_*.yaml"))

    def test_no_lms_data_aborts(self, tmp_path, monkeypatch):
        reg_path = self._setup(
            tmp_path,
            monkeypatch,
            lms_models=[],
            entries={
                "mradermacher/nemotron-cascade-14b-thinking": {"reasoning": "thinking", "blueprint": "full"},
            },
        )
        assert rt.cmd_quarantine_missing() == 1
        assert "mradermacher/nemotron-cascade-14b-thinking" in rt.load_registry(reg_path)
        assert not list((tmp_path / "configs").glob("_quarantine_missing_*"))

    def test_quant_variant_quarantined_when_not_installed(self, tmp_path, monkeypatch):
        reg_path = self._setup(
            tmp_path,
            monkeypatch,
            lms_models=[{"modelKey": "unsloth/ernie-4.5-21b-a3b-pt"}],
            entries={
                "unsloth/ernie-4.5-21b-a3b-pt@iq4_nl": {"reasoning": "thinking", "blueprint": "full"},
                "unsloth/ernie-4.5-21b-a3b-pt": {"reasoning": "thinking", "blueprint": "full"},
            },
            with_config=False,
        )
        assert rt.cmd_quarantine_missing(dry_run=False) == 0
        reg = rt.load_registry(reg_path)
        assert "unsloth/ernie-4.5-21b-a3b-pt" in reg
        assert "unsloth/ernie-4.5-21b-a3b-pt@iq4_nl" not in reg
        assert not list((tmp_path / "configs").glob("_quarantine_missing_*"))

    def test_config_shared_with_survivor_stays(self, tmp_path, monkeypatch):
        reg_path = self._setup(
            tmp_path,
            monkeypatch,
            lms_models=[{"modelKey": "unsloth/gemma-4-26b-a4b-it@iq3_s"}],
            entries={
                "google/gemma-4-26b-a4b-it-qat": {"reasoning": "thinking", "blueprint": "full"},
                "unsloth/gemma-4-26b-a4b-it@iq3_s": {"reasoning": "thinking", "blueprint": "full"},
            },
            with_config=False,
        )
        cfg_dir = tmp_path / "configs" / "unsloth" / "gemma-4-26B-A4B-it-GGUF"
        cfg_dir.mkdir(parents=True)
        cfg_file = cfg_dir / "gemma-4-26B-A4B-it-UD-IQ3_S.gguf.json"
        cfg_file.write_text(json.dumps({"operation": {"fields": []}}), encoding="utf-8")
        assert rt.cmd_quarantine_missing(dry_run=False) == 0
        reg = rt.load_registry(reg_path)
        assert "google/gemma-4-26b-a4b-it-qat" not in reg
        assert "unsloth/gemma-4-26b-a4b-it@iq3_s" in reg
        assert cfg_file.exists()

    def test_lms_record_matches_duplicate_quant_suffix_in_model_name(self):
        model = {
            "type": "llm",
            "modelKey": "gemma-4-12b-it-qat",
            "publisher": "FreedomAISVR",
            "path": "FreedomAISVR/Gemma-4-12B-it-QAT-NVFP4-GGUF/gemma-4-12b-it-qat-nvfp4.gguf",
        }

        assert (
            rt._lms_record_for_registry_key(
                "freedomaisvr/gemma-4-12b-it-qat-nvfp4@nvfp4", [model]
            )
            is model
        )

    def test_unknown_quant_registry_key_matches_lms_base_and_known_quant(self):
        model = {
            "type": "llm",
            "modelKey": "muse-glimmer-30b@?",
            "publisher": "gguf-org",
            "path": "gguf-org/muse-glimmer-30b-gguf/muse-glimmer-30b-nvfp4.gguf",
        }

        assert rt._lms_record_for_registry_key("gguf-org/muse-glimmer-30b@?", [model]) is model
        assert rt._lms_record_for_registry_key("gguf-org/muse-glimmer-30b@nvfp4", [model]) is model

    def test_mini_quant_is_inferred_from_lms_filename(self):
        model = {
            "type": "llm",
            "modelKey": "gemma-4-26b-a4b-it-apex",
            "publisher": "mudler",
            "path": "mudler/gemma-4-26B-A4B-it-APEX-GGUF/gemma-4-26B-A4B-APEX-I-Mini.gguf",
        }

        assert rt._quant_from_lms_record(model) == "mini"
        assert rt._lms_record_for_registry_key("mudler/gemma-4-26b-a4b-it-apex@mini", [model]) is model

    def test_same_model_with_different_quant_remains_unmatched(self):
        model = {
            "type": "llm",
            "modelKey": "mellum2-12b-a2.5b-instruct",
            "publisher": "JetBrains",
            "path": "JetBrains/Mellum2-12B-A2.5B-Instruct-GGUF-Q6_K/Mellum2-12B-A2.5B-Instruct-Q6_K.gguf",
        }

        assert rt._lms_record_for_registry_key(
            "jetbrains/mellum2-12b-a2.5b-instruct@q4_k_m", [model]
        ) is None

    def test_physical_gguf_check_requires_exact_quant(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rt, "MODELS_CACHE", tmp_path)
        gguf = tmp_path / "publisher" / "example-model-GGUF" / "example-model-Q6_K.gguf"
        gguf.parent.mkdir(parents=True)
        gguf.touch()

        assert rt._gguf_for_key_exists("publisher/example-model@q6_k")
        assert rt._gguf_for_key_exists("publisher/example-model@?")
        assert not rt._gguf_for_key_exists("publisher/example-model@q4_k_m")

    def test_physical_gguf_check_ignores_mmproj_only(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rt, "MODELS_CACHE", tmp_path)
        mmproj = tmp_path / "publisher" / "example-model-GGUF" / "mmproj-example-model-Q6_K.gguf"
        mmproj.parent.mkdir(parents=True)
        mmproj.touch()

        assert not rt._gguf_for_key_exists("publisher/example-model@q6_k")


# ─────────────────────────────────────────────────────────────────────
# MTP-/Draft-/mmproj-Support: Zusatzdateien ≠ eigenständige Standardmodelle
# ─────────────────────────────────────────────────────────────────────


class TestIsSupportFile:
    """_is_support_file(): mtp-*, dflash-* und mmproj* sind Zusatzdateien,
    legitime MTP-Modelle (qwen3.6-27b-mtp, ...-MTP-...) nicht."""

    def test_separate_mtp_prefix_detected(self):
        assert rt._is_support_file("unsloth/gemma-4-12B-it-qat-GGUF/mtp-gemma-4-12B-it-Q8_0.gguf")

    def test_separate_mtp_subfolder_detected(self):
        assert rt._is_support_file("unsloth/gemma-4-12B-it-qat-GGUF/MTP/mtp-gemma-4-12B-it.gguf")

    def test_mmproj_detected(self):
        assert rt._is_support_file("unsloth/gemma-4-12B-it-qat-GGUF/mmproj-F32.gguf")

    def test_dflash_support_file_detected(self):
        assert rt._is_support_file("gguf-org/muse-glimmer-30b-gguf/dflash-q4_0.gguf")

    def test_dflash2_architecture_is_support_file_independent_of_filename(self):
        assert rt._is_support_file(
            "ProCreations/Ternary-Bonsai-2-27B-DFlash2/Bonsai-2-27B-DFlash2-Q8_0.gguf",
            architecture="dflash",
        )

    def test_dspark_architecture_is_support_file_independent_of_filename(self):
        assert rt._is_support_file(
            "prism-ml/Ternary-Bonsai-27B-gguf/Ternary-Bonsai-27B-dspark-Q4_1.gguf",
            architecture="dspark",
        )

    def test_dflash_and_dspark_names_are_filtered_without_header_metadata(self):
        assert rt._is_support_file(
            "Alittlehammmer/Qwen3.6-35B-A3B-DFlash-GGUF-llama.cpp/"
            "Qwen3.6-35B-A3B-DFlash-Q6_K.gguf"
        )
        assert rt._is_support_file(
            "prism-ml/Ternary-Bonsai-27B-gguf/Ternary-Bonsai-27B-dspark-Q4_1.gguf"
        )

    def test_standalone_mtp_model_not_detected(self):
        # Eigenständige MTP-Modelle sind KEINE Zusatzdateien
        assert not rt._is_support_file("unsloth/Qwen3.6-27B-MTP-GGUF/Qwen3.6-27B-UD-IQ3_XXS.gguf")

    def test_standalone_mtp_model_with_dash_not_detected(self):
        assert not rt._is_support_file("vinpix/Ternary-Bonsai-27B-Stock-MTP-GGUF/Ternary-Bonsai-27B-MTP-Q2_K.gguf")

    def test_normal_model_not_detected(self):
        assert not rt._is_support_file("unsloth/gemma-4-12B-it-qat-GGUF/gemma-4-12B-it-qat-UD-Q4_K_XL.gguf")
        assert not rt._is_support_file("openai/gpt-oss-20b/Qwen.gguf")

    def test_mtp_directory_name_is_not_detected(self):
        # "mtp" als Teil eines Ordnernamens (nicht exakt 'MTP' als Segment)
        assert not rt._is_support_file("unsloth/Qwen3.6-27B-MTP-GGUF/model.gguf")

    def test_assistant_architecture_detected(self):
        # Separate MTP-Sidecars haben die eigene Architekturklasse
        # (gemma4-assistant).
        assert rt._is_support_file("unsloth/gemma-4-12B-it-qat-GGUF/model.gguf", architecture="gemma4-assistant")

    def test_plain_architecture_not_detected(self):
        # Normale Modelle (gemma4, qwen3moe, ...) sind keine Zusatzdateien
        assert not rt._is_support_file("unsloth/gemma-4-12B-it-qat-GGUF/model.gguf", architecture="gemma4")
        assert not rt._is_support_file("unsloth/qwen3.6-27b-mtp/model.gguf", architecture="qwen35")
        # No global size cutoff: compact OCR/embedding models remain main
        # artifacts unless their type or metadata identifies a sidecar.
        assert not rt._is_support_file("Keyven/german-ocr-3.1/german-ocr-3.1-Q8_0.gguf")
        assert not rt._is_support_file(
            "nomic-ai/nomic-embed-text-v1.5/model-Q4_K_M.gguf",
            architecture="nomic-bert",
        )

    def test_mmproj_model_record_is_detected_without_path(self):
        # LM Studio may expose only modelKey/displayName for an inventory row.
        assert rt.is_support_model_record(
            {
                "modelKey": "llmsforall/millie-35b-a3b-mmproj.gguf",
                "displayName": "Millie 35B A3B Mmproj",
                "architecture": "clip",
            }
        )

    def test_dspark_catalog_record_is_detected_as_support_model(self):
        assert rt.is_support_model_record(
            {
                "modelKey": "ternary-bonsai-27b@q4_1",
                "path": (
                    "prism-ml/Ternary-Bonsai-27B-gguf/"
                    "Ternary-Bonsai-27B-dspark-Q4_1.gguf"
                ),
                "architecture": "dspark",
            }
        )

    def test_main_millie_record_is_not_detected_as_support_file(self):
        assert not rt.is_support_model_record(
            {
                "modelKey": "millie-35b-a3b-11gb",
                "path": "llmsforall/Millie-35B-A3B-11GB/Millie-35B-A3B-11GB.gguf",
                "displayName": "Millie 35B A3B 11GB",
                "architecture": "qwen35moe",
            }
        )


class TestCmdAddSkipsSupportFiles:
    """cmd_add(): MTP-/Draft-Support und mmproj bleiben Bundle-Artefakte."""

    def test_add_skips_mtp_drafter(self, tmp_path, monkeypatch):
        reg_path = tmp_path / "registry.yaml"
        reg_path.write_text("{}\n", encoding="utf-8")
        monkeypatch.setattr(rt, "REGISTRY_PATH", reg_path)
        monkeypatch.setattr(rt, "MODELS_CACHE", tmp_path / "models")

        models = [
            {
                "key": "gemma-4-12b-it-qat@q4_k_xl",
                "publisher": "unsloth",
                "path": "unsloth/gemma-4-12B-it-qat-GGUF/gemma-4-12B-it-qat-UD-Q4_K_XL.gguf",
                "architecture": "gemma4",
                "size_bytes": 6716356800,
            },
            {
                "key": "gemma-4-12b-it-qat@q8_0",
                "publisher": "unsloth",
                "path": "unsloth/gemma-4-12B-it-qat-GGUF/mtp-gemma-4-12B-it-Q8_0.gguf",
                "architecture": "gemma4-assistant",
                "size_bytes": 674650176,
            },
        ]
        result = rt.cmd_add(models)
        reg = rt.load_registry(reg_path)
        assert "unsloth/gemma-4-12b-it-qat@q4_k_xl" in reg
        assert "unsloth/gemma-4-12b-it-qat@q8_0" not in reg
        assert any("Zusatzdatei" in msg for _, msg in result["skipped"])

    def test_add_keeps_standalone_mtp_model(self, tmp_path, monkeypatch):
        reg_path = tmp_path / "registry.yaml"
        reg_path.write_text("{}\n", encoding="utf-8")
        monkeypatch.setattr(rt, "REGISTRY_PATH", reg_path)
        monkeypatch.setattr(rt, "MODELS_CACHE", tmp_path / "models")

        models = [
            {
                "key": "qwen3.6-27b-mtp",
                "publisher": "unsloth",
                "path": "unsloth/Qwen3.6-27B-MTP-GGUF/Qwen3.6-27B-UD-IQ3_XXS.gguf",
                "size_bytes": 12203615360,
            },
        ]
        result = rt.cmd_add(models)
        reg = rt.load_registry(reg_path)
        assert "unsloth/qwen3.6-27b-mtp@iq3_xxs" in reg
        assert result["added"] == ["unsloth/qwen3.6-27b-mtp@iq3_xxs"]

    def test_add_skips_embeddings_and_ocr_records(self, tmp_path, monkeypatch):
        reg_path = tmp_path / "registry.yaml"
        reg_path.write_text("{}\n", encoding="utf-8")
        monkeypatch.setattr(rt, "REGISTRY_PATH", reg_path)
        monkeypatch.setattr(rt, "MODELS_CACHE", tmp_path / "models")

        result = rt.cmd_add(
            [
                {
                    "type": "embedding",
                    "modelKey": "text-embedding-bge-m3",
                    "publisher": "gpustack",
                },
                {
                    "type": "llm",
                    "modelKey": "chandra-ocr-2",
                    "publisher": "mradermacher",
                },
                {
                    "type": "llm",
                    "modelKey": "example-coder-7b",
                    "publisher": "example",
                },
            ]
        )

        reg = rt.load_registry(reg_path)
        assert "example/example-coder-7b@?" in reg
        assert "gpustack/text-embedding-bge-m3" not in reg
        assert "mradermacher/chandra-ocr-2" not in reg
        assert len(result["skipped"]) == 2

    @pytest.mark.parametrize(
        ("old_key", "expected_key"),
        [
            ("llmsforall/millie-35b-a3b-11gb", "llmsforall/millie-35b-a3b-11gb@?"),
            ("llmsforall/millie-35b-a3b-11gb@?", "llmsforall/millie-35b-a3b-11gb@?"),
        ],
    )
    def test_rekey_keeps_unknown_quant_placeholder(self, old_key, expected_key, monkeypatch):
        model = {
            "type": "llm",
            "modelKey": "millie-35b-a3b-11gb",
            "publisher": "llmsforall",
            "path": "llmsforall/Millie-35B-A3B-11GB/Millie-35B-A3B-11GB.gguf",
        }
        registry = {old_key: {"context_length": 16384}}
        monkeypatch.setattr(rt, "_lms_record_for_registry_key", lambda _key, _models: model)
        monkeypatch.setattr(rt, "save_registry", lambda _registry: None)

        changed = rt._rekey_registry_to_lms(registry, [model])

        assert list(registry) == [expected_key]
        assert changed == (old_key != expected_key)

    def test_add_keeps_a_new_quant_variant_of_an_existing_base(self, tmp_path, monkeypatch):
        reg_path = tmp_path / "registry.yaml"
        reg_path.write_text(
            "qwen/qwen3.5-9b@q6_k:\n  blueprint: default_chat\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(rt, "REGISTRY_PATH", reg_path)
        monkeypatch.setattr(rt, "MODELS_CACHE", tmp_path / "models")

        result = rt.cmd_add(
            [
                {
                    "type": "llm",
                    "modelKey": "qwen3.5-9b",
                    "publisher": "qwen",
                    "quantization": {"name": "Q5_K_S"},
                }
            ]
        )

        registry = rt.load_registry(reg_path)
        assert result["added"] == ["qwen/qwen3.5-9b@q5_k_s"]
        assert "qwen/qwen3.5-9b@q6_k" in registry
        assert "qwen/qwen3.5-9b@q5_k_s" in registry

def test_registry_matching_accepts_lms_punctuation_and_quant_metadata(monkeypatch):
    registry = {
        "byteshape/qwen3-6-35b-a3b@iq3_s": {"blueprint": "full"},
        "byteshape/qwen3-6-35b-a3b@q3_k_s": {"blueprint": "full"},
    }
    monkeypatch.setattr(rt, "load_registry", lambda: registry)
    lms = [
        {
            "type": "llm",
            "modelKey": "qwen3.6-35b-a3b",
            "publisher": "byteshape",
            "quantization": {"name": "IQ3_S"},
        }
    ]

    assert rt._missing_registry_keys(lms) == ["byteshape/qwen3-6-35b-a3b@q3_k_s"]


def test_unknown_quant_placeholder_matches_lms_base_record():
    model = {
        "type": "llm",
        "modelKey": "millie-35b-a3b-11gb",
        "publisher": "llmsforall",
        "path": "llmsforall/Millie-35B-A3B-11GB/Millie-35B-A3B-11GB.gguf",
    }
    key = "llmsforall/millie-35b-a3b-11gb@?"

    assert rt._lms_matches_registry_key(model, key)
    assert rt._lms_record_for_registry_key(key, [model]) == model


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("Ternary-Bonsai-27B-Q2_g64.gguf", "Q2_G64"),
        ("gemma-4-26B-APEX-I-Mini.gguf", "MINI"),
    ],
)
def test_gguf_quant_parser_recognizes_special_quant_names(filename, expected):
    assert rt._gguf_quant_from_header(filename) == expected


def test_sync_from_configs_keeps_provider_and_quant_variants_separate(tmp_path, monkeypatch, capsys):
    registry = {
        "openai/gpt-oss-20b@mxfp4": {"context_length": 65536},
        "unsloth/gpt-oss-20b-GGUF@q8_0": {"context_length": 65536},
    }
    configs = [
        {
            "publisher": "openai",
            "dir_name": "gpt-oss-20b",
            "file_name": "gpt-oss-20b.json",
            "context_length": 131072,
            "json_path": tmp_path / "openai.json",
        },
        {
            "publisher": "unsloth",
            "dir_name": "gpt-oss-20b-GGUF",
            "file_name": "gpt-oss-20b-Q8_0.gguf.json",
            "context_length": 65536,
            "json_path": tmp_path / "unsloth.json",
        },
    ]
    registry_path = tmp_path / "registry.yaml"
    registry_path.touch()
    saved: dict[str, dict] = {}
    monkeypatch.setattr(rt, "REGISTRY_PATH", registry_path)
    monkeypatch.setattr(rt, "load_registry", lambda: registry)
    monkeypatch.setattr(rt, "read_lms_configs", lambda _root: configs)
    monkeypatch.setattr(rt, "save_registry", lambda value: saved.update(value))

    rt.cmd_sync_from_configs(
        write=True,
        installed_models=[{"modelKey": "gpt-oss-20b", "publisher": "openai"}],
    )

    assert registry["openai/gpt-oss-20b@mxfp4"]["context_length"] == 131072
    assert registry["unsloth/gpt-oss-20b-GGUF@q8_0"]["context_length"] == 65536
    output = capsys.readouterr().out
    assert "0 Konflikte" in output
    assert "ohne eindeutige Zuordnung/alte Configs" in output


def test_fill_quant_uses_lms_quantization_without_gguf_path(monkeypatch):
    registry = {
        "mistralai/ministral-3-14b-reasoning": {"blueprint": "full"},
    }
    saved: dict[str, dict] = {}
    monkeypatch.setattr(rt, "load_registry", lambda: registry)
    monkeypatch.setattr(rt, "save_registry", lambda value: saved.update(value))
    monkeypatch.setattr(
        rt,
        "_run_lms_ls",
        lambda: [
            {
                "type": "llm",
                "modelKey": "mistralai/ministral-3-14b-reasoning",
                "publisher": "mistralai",
                "quantization": {"name": "Q6_K"},
            }
        ],
    )

    rt.cmd_fill_quant()

    assert "mistralai/ministral-3-14b-reasoning@q6_k" in saved
    assert saved["mistralai/ministral-3-14b-reasoning@q6_k"]["quants"] == "Q6_K"


def test_rekey_registry_to_exact_lms_identity(monkeypatch):
    registry = {
        "qwen/qwen2-5-coder-14b-instruct@q6_k": {"blueprint": "coding_agent"},
    }
    saved: dict[str, dict] = {}
    monkeypatch.setattr(rt, "save_registry", lambda value: saved.update(value))
    models = [
        {
            "type": "llm",
            "modelKey": "qwen2.5-coder-14b-instruct",
            "publisher": "Qwen",
            "quantization": {"name": "Q6_K"},
        }
    ]

    changed = rt._rekey_registry_to_lms(registry, models)

    assert changed == 1
    assert "qwen/qwen2.5-coder-14b-instruct@q6_k" in saved
    assert saved["qwen/qwen2.5-coder-14b-instruct@q6_k"]["blueprint"] == "coding_agent"


def test_lms_namespace_is_not_mistaken_for_publisher():
    model = {
        "modelKey": "qwen/qwen3.5-9b",
        "publisher": "lmstudio-community",
        "quantization": {"name": "Q6_K"},
    }

    assert rt._canonical_lms_key(model) == "lmstudio-community/qwen/qwen3.5-9b@q6_k"


def test_lms_gguf_display_path_uses_parent_model_directory_for_identity():
    model = {
        "modelKey": "byteshape/qwen3.5-9b/Qwen3.5-9B-Q5_K_S-5.10bpw.gguf",
        "publisher": "byteshape",
        "quantization": {"name": "Q5_K_S"},
    }

    assert rt._canonical_lms_key(model) == "byteshape/qwen3.5-9b@q5_k_s"
    assert rt._lms_matches_registry_key(model, "byteshape/qwen3.5-9b@q5_k_s")
    assert not rt._lms_matches_registry_key(
        model,
        "byteshape/qwen3.5-9b/qwen3.5-9b-q5_k_s-5.10bpw@q5_k_s",
    )


def test_lms_gguf_display_path_can_bind_its_publisher_config():
    config = {
        "publisher": "byteshape",
        "dir_name": "qwen3.5-9b",
        "quant": None,
    }
    model = {
        "modelKey": "byteshape/qwen3.5-9b/Qwen3.5-9B-Q5_K_S-5.10bpw.gguf",
        "publisher": "byteshape",
        "quantization": {"name": "Q5_K_S"},
    }

    assert rt._config_matches_lms_model(config, model)


def test_config_matches_lms_model_by_namespaced_model_key_not_config_folder_publisher(tmp_path):
    config = {
        "publisher": "qwen",
        "dir_name": "qwen3.5-9b",
        "quant": None,
        "json_path": tmp_path / "qwen3.5-9b.json",
    }
    model = {
        "modelKey": "qwen/qwen3.5-9b",
        "publisher": "lmstudio-community",
        "quantization": {"name": "Q6_K"},
    }

    assert rt._config_matches_lms_model(config, model)


def test_config_matching_prefers_concrete_gguf_json_over_logical_model_json(tmp_path):
    artifact_path = tmp_path / "models" / "lmstudio-community" / "Qwen3.5-9B-GGUF" / "Qwen3.5-9B-Q6_K.gguf"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"GGUF fixture")
    logical_config = {
        "publisher": "qwen",
        "dir_name": "qwen3.5-9b",
        "json_path": tmp_path / "configs" / "qwen" / "qwen3.5-9b.json",
    }
    concrete_config = {
        "publisher": "lmstudio-community",
        "dir_name": "Qwen3.5-9B-GGUF",
        "json_path": tmp_path / "configs" / "lmstudio-community" / "Qwen3.5-9B-GGUF" / "Qwen3.5-9B-Q6_K.gguf.json",
    }
    Path(concrete_config["json_path"]).parent.mkdir(parents=True)
    Path(concrete_config["json_path"]).write_text("{}", encoding="utf-8")

    assert not rt._config_matches_artifact(logical_config, artifact_path)
    assert rt._config_matches_artifact(concrete_config, artifact_path)


def test_physical_gguf_evidence_suppresses_logical_lms_auto_add(tmp_path):
    from types import SimpleNamespace

    from model_identity import ArtifactIdentityEvidence

    artifact_path = tmp_path / "lmstudio-community" / "Qwen3.5-9B-GGUF" / "Qwen3.5-9B-Q6_K.gguf"
    evidence = ArtifactIdentityEvidence.from_reference(
        artifact_path,
        "lmstudio-community/Qwen3.5-9B-GGUF",
        "Q6_K",
    )
    candidate = SimpleNamespace(
        registry_key="lmstudio-community/qwen/qwen3.5-9b@q6_k",
        identity_evidence=evidence,
        path=artifact_path,
    )
    model = {
        "modelKey": "qwen/qwen3.5-9b",
        "publisher": "qwen",
        "path": "qwen/qwen3.5-9b",
        "selectedVariant": "qwen/qwen3.5-9b@q6_k",
        "quantization": {"name": "Q6_K"},
    }

    assert rt._physical_registry_matches_lms_model(
        model,
        [candidate],
        {"lmstudio-community/qwen/qwen3.5-9b@q6_k"},
    ) == ("lmstudio-community/qwen/qwen3.5-9b@q6_k",)


def test_compare_uses_unique_physical_evidence_for_lms_publisher_alias(tmp_path):
    from types import SimpleNamespace

    from model_identity import ArtifactIdentityEvidence

    artifact_path = tmp_path / "lmstudio-community" / "Qwen3.5-9B-GGUF" / "Qwen3.5-9B-Q6_K.gguf"
    registry_key = "lmstudio-community/qwen/qwen3.5-9b@q6_k"
    model = {
        "modelKey": "qwen/qwen3.5-9b",
        "publisher": "qwen",
        "path": "qwen/qwen3.5-9b",
        "selectedVariant": "qwen/qwen3.5-9b@q6_k",
        "quantization": {"name": "Q6_K"},
    }
    candidate = SimpleNamespace(
        registry_key=registry_key,
        identity_evidence=ArtifactIdentityEvidence.from_reference(
            artifact_path,
            "lmstudio-community/Qwen3.5-9B-GGUF",
            "Q6_K",
        ),
        path=artifact_path,
    )
    inventory = rt.RegistryInventory(
        {registry_key: {}},
        [model],
        [model],
        [],
        [candidate],
        True,
    )

    report = rt.cmd_compare(inventory)

    assert report["new"] == 0
    assert report["missing"] == 0


def test_identity_link_does_not_replace_stale_config_with_logical_model_config(tmp_path, monkeypatch):
    from local_model_resolver import LocalModelResolver

    artifact_path = tmp_path / "lmstudio-community" / "Qwen3.5-9B-GGUF" / "Qwen3.5-9B-Q6_K.gguf"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"GGUF test placeholder")
    config_path = tmp_path / "configs" / "qwen" / "qwen3.5-9b.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{}", encoding="utf-8")
    stale_config_path = tmp_path / "configs" / "lmstudio-community" / "old-Q6_K.gguf.json"
    registry_key = "lmstudio-community/qwen/qwen3.5-9b@q6_k"
    registry = {
        registry_key: {
            "local": {
                "model_path": str(artifact_path),
                "config_path": str(stale_config_path),
            }
        }
    }
    model = {
        "type": "llm",
        "modelKey": "qwen/qwen3.5-9b",
        "publisher": "qwen",
        "path": "qwen/qwen3.5-9b",
        "selectedVariant": "qwen/qwen3.5-9b@q6_k",
        "quantization": {"name": "Q6_K"},
    }
    config = {
        "publisher": "qwen",
        "dir_name": "qwen3.5-9b",
        "json_path": config_path,
        "quant": None,
        "context_length": 262144,
    }
    candidates = LocalModelResolver(tmp_path, registry_loader=lambda: registry).candidates()
    inventory = rt.RegistryInventory(registry, [model], [model], [config], candidates, True)
    monkeypatch.setattr(rt, "save_registry", lambda _registry: None)

    rt._refresh_identity_links(inventory)
    link = inventory.identity_links[registry_key]
    assert link.config_paths == ()

    rt._materialize_local_bindings(inventory)

    assert registry[registry_key]["local"]["config_path"] == str(stale_config_path)

    report = rt.cmd_compare(inventory)
    assert report["orphan"] == 1


def test_identity_link_binds_runtime_config_to_one_gguf_artifact(tmp_path):
    from local_model_resolver import LocalModelResolver

    artifact_path = (
        tmp_path
        / "lmstudio-community"
        / "qwen"
        / "qwen3.5-9b"
        / "Qwen3.5-9B-Q6_K.gguf"
    )
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"GGUF test placeholder")
    registry_key = "lmstudio-community/qwen/qwen3.5-9b@q6_k"
    registry = {registry_key: {}}
    model = {
        "modelKey": "qwen/qwen3.5-9b",
        "publisher": "lmstudio-community",
        "quantization": {"name": "Q6_K"},
        "path": str(artifact_path),
    }
    config_path = (
        tmp_path / "configs" / "qwen" / "qwen3.5-9b" / "Qwen3.5-9B-Q6_K.gguf.json"
    )
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{}", encoding="utf-8")
    config = {
        "publisher": "qwen",
        "dir_name": "qwen3.5-9b",
        "json_path": config_path,
        "sampling": {"temperature": 0.7, "top_p": 0.95, "top_k": 40},
        "context_length": 131072,
        "use_unified_kv": True,
        "num_parallel": 4,
        "k_cache": "q8_0",
        "v_cache": "q5_1",
    }
    candidates = LocalModelResolver(tmp_path, registry_loader=lambda: registry).candidates()
    inventory = rt.RegistryInventory(registry, [model], [model], [config], candidates, True)

    rt._refresh_identity_links(inventory)

    link = inventory.identity_links[registry_key]
    assert link.artifact_paths == (artifact_path,)
    assert link.config_paths == (config_path,)
    assert link.artifact_evidence[0].identity == registry_key
    runtime = link.runtime_bindings[0]
    assert runtime.config_path == config_path
    assert dict(runtime.sampling) == {"temperature": 0.7, "top_k": 40, "top_p": 0.95}
    assert runtime.context_length == 131072
    assert runtime.use_unified_kv is True
    assert runtime.num_parallel == 4
    assert runtime.k_cache == "q8_0"
    assert runtime.v_cache == "q5_1"


def test_canonical_lms_identity_recovers_quant_from_path_when_selected_variant_is_unknown():
    model = {
        "modelKey": "ternary-bonsai-27b",
        "publisher": "prism-ml",
        "selectedVariant": "ternary-bonsai-27b@?",
        "path": (
            "prism-ml/Ternary-Bonsai-27B-gguf/"
            "Ternary-Bonsai-27B-Q2_g64.gguf"
        ),
    }

    assert rt._canonical_lms_key(model) == "prism-ml/ternary-bonsai-27b@q2_g64"


def test_identity_link_uses_unique_concrete_lms_path_when_package_name_differs(tmp_path):
    from local_model_resolver import LocalModelResolver

    artifact_path = (
        tmp_path
        / "mradermacher"
        / "Muse-Glimmer-30B-Heretic-Abliterated-BF16-i1-GGUF"
        / "Muse-Glimmer-30B-Heretic-Abliterated-BF16.i1-IQ3_M.gguf"
    )
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"GGUF test placeholder")
    registry_key = "mradermacher/muse-glimmer-30b-heretic-abliterated-i1@iq3_m"
    registry = {registry_key: {}}
    model = {
        "modelKey": "mradermacher/muse-glimmer-30b-heretic-abliterated-i1",
        "publisher": "mradermacher",
        "quantization": {"name": "IQ3_M"},
        "selectedVariant": registry_key,
        "path": (
            "mradermacher/Muse-Glimmer-30B-Heretic-Abliterated-BF16-i1-GGUF/"
            "Muse-Glimmer-30B-Heretic-Abliterated-BF16.i1-IQ3_M.gguf"
        ),
    }
    config_path = (
        tmp_path
        / "configs"
        / "mradermacher"
        / "Muse-Glimmer-30B-Heretic-Abliterated-BF16-i1-GGUF"
        / "Muse-Glimmer-30B-Heretic-Abliterated-BF16.i1-IQ3_M.gguf.json"
    )
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{}", encoding="utf-8")
    config = {
        "publisher": "mradermacher",
        "dir_name": "Muse-Glimmer-30B-Heretic-Abliterated-BF16-i1-GGUF",
        "file_name": config_path.name,
        "json_path": config_path,
        "speculative": {"type": "draft", "method": "dflash"},
    }
    candidates = LocalModelResolver(tmp_path, registry_loader=lambda: registry).candidates()
    assert len(candidates) == 1
    assert candidates[0].registry_key is None
    inventory = rt.RegistryInventory(registry, [model], [model], [config], candidates, True)

    rt._refresh_identity_links(inventory)

    link = inventory.identity_links[registry_key]
    assert link.artifact_paths == (artifact_path,)
    assert link.config_paths == (config_path,)
    assert link.artifact_evidence[0].identity != registry_key
    assert link.runtime_bindings[0].speculative == (("method", "dflash"), ("type", "draft"))


def test_identity_link_does_not_use_logical_path_for_mismatched_artifact(tmp_path):
    from local_model_resolver import LocalModelResolver

    artifact_path = (
        tmp_path
        / "mradermacher"
        / "Muse-Glimmer-30B-Heretic-Abliterated-BF16-i1-GGUF"
        / "Muse-Glimmer-30B-Heretic-Abliterated-BF16.i1-IQ3_M.gguf"
    )
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"GGUF test placeholder")
    registry_key = "mradermacher/muse-glimmer-30b-heretic-abliterated-i1@iq3_m"
    registry = {registry_key: {}}
    model = {
        "modelKey": "mradermacher/muse-glimmer-30b-heretic-abliterated-i1",
        "publisher": "mradermacher",
        "quantization": {"name": "IQ3_M"},
        "path": "mradermacher/muse-glimmer-30b-heretic-abliterated-i1",
    }
    config = {
        "publisher": "mradermacher",
        "dir_name": artifact_path.parent.name,
        "file_name": f"{artifact_path.name}.json",
        "json_path": tmp_path / "configs" / "m.json",
    }
    candidates = LocalModelResolver(tmp_path, registry_loader=lambda: registry).candidates()
    inventory = rt.RegistryInventory(registry, [model], [model], [config], candidates, True)

    rt._refresh_identity_links(inventory)

    link = inventory.identity_links[registry_key]
    assert link.artifact_paths == ()
    assert link.config_paths == ()


def test_identity_link_uses_persisted_local_model_config_pair_without_live_model(monkeypatch):
    artifact_path = Path("D:/models/bartowski/GLM-4.6V-Flash-GGUF/GLM-4.6V-Flash-Q6_K_L.gguf")
    config_path = Path(
        "C:/lms-config/bartowski/GLM-4.6V-Flash-GGUF/GLM-4.6V-Flash-Q6_K_L.gguf.json"
    )
    monkeypatch.setattr(Path, "is_file", lambda _path: True)
    monkeypatch.setattr("artifact_bundle._has_gguf_magic", lambda _path: True)
    registry_key = "bartowski/zai-org_glm-4.6v-flash@q6_k_l"
    registry = {
        registry_key: {
            "local": {
                "model_path": str(artifact_path),
                "config_path": str(config_path),
            }
        }
    }
    config = {
        "publisher": "bartowski",
        "dir_name": "GLM-4.6V-Flash-GGUF",
        "file_name": "GLM-4.6V-Flash-Q6_K_L.gguf.json",
        "quant": "q6_k_l",
        "json_path": config_path,
        "context_length": 32768,
        "use_unified_kv": True,
        "num_parallel": 4,
    }
    inventory = rt.RegistryInventory(registry, [], [], [config], [], False)

    rt._refresh_identity_links(inventory)

    link = inventory.identity_links[registry_key]
    assert link.artifact_paths == ()
    assert link.config_paths == (config_path,)
    assert link.runtime_bindings[0].config_path == config_path
    assert link.runtime_bindings[0].context_length == 32768
    assert link.runtime_bindings[0].use_unified_kv is True
    assert link.runtime_bindings[0].num_parallel == 4


def test_identity_link_allows_explicit_unique_model_scoped_config_pair(tmp_path):
    from pathlib import Path

    from registry_tool import RegistryInventory, _refresh_identity_links

    main_path = tmp_path / "models" / "lmstudio-community" / "Qwen3.5-9B-GGUF" / "Qwen3.5-9B-Q6_K.gguf"
    config_path = tmp_path / "configs" / "qwen" / "qwen3.5-9b.json"
    main_path.parent.mkdir(parents=True)
    config_path.parent.mkdir(parents=True)
    main_path.write_bytes(b"GGUF fixture")
    config_path.write_text("{}", encoding="utf-8")
    registry_key = "lmstudio-community/qwen/qwen3.5-9b@q6_k"
    registry = {
        registry_key: {
            "local": {
                "model_path": str(main_path),
                "config_path": str(config_path),
                "config_scope": "model",
            }
        }
    }
    config = {
        "publisher": "qwen",
        "dir_name": "qwen3.5-9b",
        "json_path": config_path,
        "context_length": 131072,
    }
    inventory = RegistryInventory(registry, [], [], [config], [], False)

    _refresh_identity_links(inventory)

    link = inventory.identity_links[registry_key]
    assert link.config_paths == (Path(config_path),)
    assert link.runtime_bindings[0].config_scope == "model"
    assert link.runtime_bindings[0].context_length == 131072


def test_model_scoped_config_must_have_one_registry_owner(tmp_path):
    from registry_tool import _registry_local_bundle_errors

    config_path = tmp_path / "configs" / "qwen" / "qwen3.5-9b.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{}", encoding="utf-8")
    registry = {}
    for quant in ("Q6_K", "Q8_0"):
        main_path = tmp_path / "models" / "publisher" / "Qwen3.5-9B-GGUF" / f"Qwen3.5-9B-{quant}.gguf"
        main_path.parent.mkdir(parents=True, exist_ok=True)
        main_path.write_bytes(b"GGUF fixture")
        key = f"publisher/qwen3.5-9b@{quant.casefold()}"
        registry[key] = {
            "local": {
                "model_path": str(main_path),
                "config_path": str(config_path),
                "config_scope": "model",
            }
        }

    errors = _registry_local_bundle_errors(registry)

    assert len(errors["config"]) == 2
    assert all("assigned to multiple Registry entries" in message for message in errors["config"])


def test_identity_link_rejects_mismatched_persisted_local_config_path(monkeypatch):
    artifact_path = Path("D:/models/lmstudio-community/Qwen-GGUF/Qwen-Q6_K.gguf")
    wrong_config = Path("C:/configs/lmstudio-community/Qwen-GGUF/Qwen-Q5_K.gguf.json")
    monkeypatch.setattr(Path, "is_file", lambda _path: True)
    registry_key = "lmstudio-community/qwen/model@q6_k"
    registry = {
        registry_key: {
            "local": {
                "model_path": str(artifact_path),
                "config_path": str(wrong_config),
            }
        }
    }
    config = {
        "publisher": "lmstudio-community",
        "dir_name": "Qwen-GGUF",
        "file_name": wrong_config.name,
        "quant": "Q5_K",
        "json_path": wrong_config,
        "context_length": 32768,
    }
    inventory = rt.RegistryInventory(registry, [], [], [config], [], False)

    rt._refresh_identity_links(inventory)

    assert inventory.identity_links[registry_key].config_paths == ()


def test_identity_link_joins_logical_lms_snapshot_to_flat_physical_qwen_path(tmp_path):
    from local_model_resolver import LocalModelResolver

    artifact_path = tmp_path / "lmstudio-community" / "Qwen3.5-9B-GGUF" / "Qwen3.5-9B-Q6_K.gguf"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"GGUF test placeholder")
    registry_key = "lmstudio-community/qwen/qwen3.5-9b@q6_k"
    registry = {registry_key: {}}
    # This is the shape found in the supplied `lms ls --json` snapshot:
    # the logical Hub publisher differs from the physical local root.
    model = {
        "type": "llm",
        "modelKey": "qwen/qwen3.5-9b",
        "publisher": "qwen",
        "path": "qwen/qwen3.5-9b",
        "selectedVariant": "qwen/qwen3.5-9b@q6_k",
        "quantization": {"name": "Q6_K"},
    }
    config_path = (
        tmp_path
        / "configs"
        / "lmstudio-community"
        / "Qwen3.5-9B-GGUF"
        / "Qwen3.5-9B-Q6_K.gguf.json"
    )
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{}", encoding="utf-8")
    config = {
        "publisher": "qwen",
        "dir_name": "qwen3.5-9b",
        "json_path": config_path,
        "context_length": 131072,
    }
    candidates = LocalModelResolver(tmp_path, registry_loader=lambda: registry).candidates()
    inventory = rt.RegistryInventory(registry, [model], [model], [config], candidates, True)

    rt._refresh_identity_links(inventory)

    link = inventory.identity_links[registry_key]
    assert link.artifact_paths == (artifact_path,)
    assert link.config_paths == (config_path,)
    assert link.runtime_bindings[0].config_path == config_path


def test_identity_link_prefers_flat_physical_config_for_flat_qwen_path(tmp_path):
    from local_model_resolver import LocalModelResolver

    artifact_path = tmp_path / "lmstudio-community" / "Qwen3.5-9B-GGUF" / "Qwen3.5-9B-Q6_K.gguf"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"GGUF test placeholder")
    registry_key = "lmstudio-community/qwen/qwen3.5-9b@q6_k"
    registry = {registry_key: {}}
    model = {
        "type": "llm",
        "modelKey": "qwen/qwen3.5-9b",
        "publisher": "qwen",
        "path": "qwen/qwen3.5-9b",
        "selectedVariant": "qwen/qwen3.5-9b@q6_k",
        "quantization": {"name": "Q6_K"},
    }
    logical_path = tmp_path / "configs" / "qwen" / "qwen3.5-9b.json"
    concrete_path = (
        tmp_path
        / "configs"
        / "lmstudio-community"
        / "Qwen3.5-9B-GGUF"
        / "Qwen3.5-9B-Q6_K.gguf.json"
    )
    for path in (logical_path, concrete_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    logical_path.write_text("{}", encoding="utf-8")
    concrete_path.write_text("{}", encoding="utf-8")
    configs = [
        {"publisher": "qwen", "dir_name": "qwen3.5-9b", "json_path": logical_path},
        {
            "publisher": "lmstudio-community",
            "dir_name": "Qwen3.5-9B-GGUF",
            "json_path": concrete_path,
        },
    ]
    candidates = LocalModelResolver(tmp_path, registry_loader=lambda: registry).candidates()
    inventory = rt.RegistryInventory(registry, [model], [model], configs, candidates, True)

    rt._refresh_identity_links(inventory)

    assert inventory.identity_links[registry_key].config_paths == (concrete_path,)


def test_materialize_local_binding_persists_main_config_and_mtp_companion(tmp_path, monkeypatch):
    from local_model_resolver import LocalModelResolver

    main_path = tmp_path / "unsloth" / "gemma-4-12b-it-GGUF" / "gemma-4-12b-it-Q6_K.gguf"
    companion_path = (
        tmp_path
        / "unsloth"
        / "gemma-4-12b-it-GGUF"
        / "mtp-gemma-4-12B-it-Q8_0.gguf"
    )
    for path in (main_path, companion_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"GGUF test placeholder")
    config_path = (
        tmp_path
        / "configs"
        / "unsloth"
        / "gemma-4-12b-it-GGUF"
        / "gemma-4-12b-it-Q6_K.gguf.json"
    )
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{}", encoding="utf-8")
    registry_key = "unsloth/gemma-4-12b-it@q6_k"
    registry = {registry_key: {}}
    model = {
        "type": "llm",
        "modelKey": "gemma-4-12b-it",
        "publisher": "unsloth",
        "quantization": {"name": "Q6_K"},
        "path": str(main_path),
    }
    config = {
        "publisher": "unsloth",
        "dir_name": "gemma-4-12b-it",
        "json_path": config_path,
        "context_length": 65536,
        "speculative": {
            "type": "mtp",
            "mode": "separate",
            "draft_model_reference": "unsloth/gemma-4-12b-it-GGUF/mtp-gemma-4-12B-it-Q8_0.gguf",
            "draft_n_max": 4,
            "draft_n_min": 0,
            "draft_p_min": 0.0,
        },
    }
    candidates = LocalModelResolver(tmp_path, registry_loader=lambda: registry).candidates()
    inventory = rt.RegistryInventory(registry, [model], [model], [config], candidates, True)
    monkeypatch.setattr(rt, "MODELS_CACHE", tmp_path)
    saved: list[dict] = []
    monkeypatch.setattr(rt, "save_registry", lambda value: saved.append(value))

    rt._refresh_identity_links(inventory)
    changed = rt._materialize_local_bindings(inventory)

    assert changed > 0
    local = registry[registry_key]["local"]
    assert local["model_path"] == str(main_path)
    assert local["config_path"] == str(config_path)
    assert local["companions"]["mtp"] == str(companion_path)
    assert local["llama_cpp"]["speculative"] == {
        "type": "mtp",
        "mode": "separate",
        "companion_role": "mtp",
        "draft_n_max": 4,
        "draft_n_min": 0,
        "draft_p_min": 0.0,
    }
    assert saved == [registry]


def test_materialize_local_binding_persists_dflash_companion_role(tmp_path, monkeypatch):
    from local_model_resolver import LocalModelResolver

    main_path = tmp_path / "gguf-org" / "muse-glimmer-30b-gguf" / "muse-glimmer-30b-nvfp4.gguf"
    drafter_path = tmp_path / "gguf-org" / "muse-glimmer-30b-gguf" / "dflash-q4_0.gguf"
    for path in (main_path, drafter_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"GGUF test placeholder")
    config_path = (
        tmp_path
        / "configs"
        / "gguf-org"
        / "muse-glimmer-30b-gguf"
        / "muse-glimmer-30b-nvfp4.gguf.json"
    )
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{}", encoding="utf-8")
    registry_key = "gguf-org/muse-glimmer-30b@nvfp4"
    registry = {registry_key: {}}
    model = {
        "type": "llm",
        "modelKey": "muse-glimmer-30b",
        "publisher": "gguf-org",
        "quantization": {"name": "NVFP4"},
        "path": str(main_path),
    }
    config = {
        "publisher": "gguf-org",
        "dir_name": "muse-glimmer-30b-gguf",
        "json_path": config_path,
        "speculative": {
            "type": "draft",
            "method": "dflash",
            "draft_model_reference": "gguf-org/muse-glimmer-30b-gguf/dflash-q4_0.gguf",
            "draft_n_max": 3,
            "draft_n_min": 0,
            "draft_p_min": 0.0,
        },
    }
    candidates = LocalModelResolver(tmp_path, registry_loader=lambda: registry).candidates()
    inventory = rt.RegistryInventory(registry, [model], [model], [config], candidates, True)
    monkeypatch.setattr(rt, "MODELS_CACHE", tmp_path)
    monkeypatch.setattr(rt, "save_registry", lambda _value: None)

    rt._refresh_identity_links(inventory)
    rt._materialize_local_bindings(inventory)

    local = registry[registry_key]["local"]
    assert local["model_path"] == str(main_path)
    assert local["companions"]["draft"] == str(drafter_path)
    assert local["llama_cpp"]["speculative"] == {
        "type": "draft",
        "method": "dflash",
        "companion_role": "draft",
        "draft_n_max": 3,
        "draft_n_min": 0,
        "draft_p_min": 0.0,
    }


def test_sync_does_not_persist_incompatible_dflash_companion(tmp_path, monkeypatch):
    from local_model_resolver import LocalModelResolver

    main_path = tmp_path / "unsloth" / "qwen3.6-27b-GGUF" / "qwen3.6-27b-Q6_K.gguf"
    wrong_helper = tmp_path / "unsloth" / "qwen3.8-27b-GGUF" / "qwen3.8-27b-dflash2-Q8_0.gguf"
    config_path = (
        tmp_path
        / "configs"
        / "unsloth"
        / "qwen3.6-27b-GGUF"
        / "qwen3.6-27b-Q6_K.gguf.json"
    )
    for path in (main_path, wrong_helper, config_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"GGUF fixture")
    registry_key = "unsloth/qwen3.6-27b@q6_k"
    registry = {registry_key: {}}
    model = {
        "modelKey": "qwen3.6-27b",
        "publisher": "unsloth",
        "quantization": {"name": "Q6_K"},
        "path": str(main_path),
    }
    config = {
        "publisher": "unsloth",
        "dir_name": "qwen3.6-27b-GGUF",
        "json_path": config_path,
        "speculative": {
            "type": "draft",
            "method": "dflash",
            "draft_model_reference": str(wrong_helper),
        },
    }
    candidates = LocalModelResolver(tmp_path, registry_loader=lambda: registry).candidates()
    inventory = rt.RegistryInventory(registry, [model], [model], [config], candidates, True)
    monkeypatch.setattr(rt, "MODELS_CACHE", tmp_path)
    monkeypatch.setattr(rt, "_resolve_local_companion", lambda _reference: wrong_helper)
    monkeypatch.setattr(rt, "save_registry", lambda _value: None)

    rt._refresh_identity_links(inventory)
    rt._materialize_local_bindings(inventory)

    assert "draft" not in registry[registry_key]["local"].get("companions", {})
    errors = rt._registry_local_bundle_errors(registry)
    assert any("required draft companion path is not configured" in message for message in errors["companion"])


def test_identity_link_rejects_lms_path_that_does_not_name_local_artifact(tmp_path):
    from local_model_resolver import LocalModelResolver

    artifact_path = tmp_path / "lmstudio-community" / "qwen" / "qwen3.5-9b" / "model-Q6_K.gguf"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"GGUF test placeholder")
    registry_key = "lmstudio-community/qwen/qwen3.5-9b@q6_k"
    registry = {registry_key: {}}
    model = {
        "modelKey": "qwen/qwen3.5-9b",
        "publisher": "lmstudio-community",
        "quantization": {"name": "Q6_K"},
        "path": str(tmp_path / "another-copy" / "model-Q6_K.gguf"),
    }
    config_path = tmp_path / "configs" / "qwen" / "qwen3.5-9b.json"
    config_path.parent.mkdir(parents=True)
    config = {
        "publisher": "qwen",
        "dir_name": "qwen3.5-9b",
        "json_path": config_path,
        "context_length": 131072,
    }
    candidates = LocalModelResolver(tmp_path, registry_loader=lambda: registry).candidates()
    inventory = rt.RegistryInventory(registry, [model], [model], [config], candidates, True)

    rt._refresh_identity_links(inventory)

    link = inventory.identity_links[registry_key]
    assert link.artifact_paths == (artifact_path,)
    assert link.config_paths == ()
    assert link.runtime_bindings[0].config_path is None


def test_identity_link_rejects_one_config_reused_by_two_quant_identities(tmp_path):
    from local_model_resolver import LocalModelResolver

    q5_path = tmp_path / "qwen" / "qwen3.5-9b" / "model-Q5_K_S.gguf"
    q6_path = tmp_path / "qwen" / "qwen3.5-9b" / "model-Q6_K.gguf"
    for path in (q5_path, q6_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"GGUF test placeholder")
    registry = {
        "qwen/qwen3.5-9b@q5_k_s": {},
        "qwen/qwen3.5-9b@q6_k": {},
    }
    model_q5 = {
        "modelKey": "qwen3.5-9b",
        "publisher": "qwen",
        "quantization": {"name": "Q5_K_S"},
        "path": str(q5_path),
    }
    model_q6 = {
        "modelKey": "qwen3.5-9b",
        "publisher": "qwen",
        "quantization": {"name": "Q6_K"},
        "path": str(q6_path),
    }
    config_path = tmp_path / "configs" / "qwen" / "qwen3.5-9b.json"
    config_path.parent.mkdir(parents=True)
    config = {
        "publisher": "qwen",
        "dir_name": "qwen3.5-9b",
        "json_path": config_path,
        "context_length": 32768,
    }
    candidates = LocalModelResolver(tmp_path, registry_loader=lambda: registry).candidates()
    inventory = rt.RegistryInventory(
        registry,
        [model_q5, model_q6],
        [model_q5, model_q6],
        [config],
        candidates,
        True,
    )

    rt._refresh_identity_links(inventory)

    assert inventory.identity_links["qwen/qwen3.5-9b@q5_k_s"].config_paths == ()
    assert inventory.identity_links["qwen/qwen3.5-9b@q6_k"].config_paths == ()


# ─────────────────────────────────────────────────────────────────────
# cmd_sync_from_gguf: Auto-Fix aus GGUF-Headern (Feld-Ownership)
# ─────────────────────────────────────────────────────────────────────


def _write_registry(tmp_path, data):
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


class TestFindGgufArchForKey:
    def test_exact_normalized_match(self):
        gguf = {"glm-4-7-flash": (61, 5120, True, 131072)}
        assert rt._find_gguf_arch_for_key("unsloth/glm-4.7-flash", gguf) == (61, 5120, True, 131072)

    def test_quant_strip_match(self):
        gguf = {"qwen3-14b": (40, 5120, True, 32768)}
        assert rt._find_gguf_arch_for_key("qwen/qwen3-14b@q4_0", gguf) == (40, 5120, True, 32768)

    def test_no_match_returns_none(self):
        assert rt._find_gguf_arch_for_key("unknown/model", {"other": (1, 2, False, 3)}) is None


class TestCmdSyncFromGguf:
    """Auto-Fix-Verhalten: Abweichungen werden korrigiert, Konformität bleibt stehen."""

    def _run(self, tmp_path, registry, lms_models, gguf_data, gguf_moe):
        path = _write_registry(tmp_path, registry)
        models_dir = tmp_path / "models"
        with (
            patch.object(rt, "REGISTRY_PATH", path),
            patch.object(rt, "_run_lms_ls", return_value=lms_models),
            patch.object(rt, "MODELS_CACHE", models_dir),
            patch.object(rt, "_read_gguf_header_details") as read,
        ):
            read.side_effect = lambda p: (
                *gguf_data.get(p, (None, None, None, None)),
                int(bool(gguf_moe.get(p, False))),
                None,
            )
            rt.cmd_sync_from_gguf()
        return rt.load_registry(path)

    def _lms(self, model_key, path):
        return {"modelKey": model_key, "path": path}

    def _gguf_path(self, tmp_path, rel):
        full = tmp_path / "models" / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(b"x")
        return str(full)

    def test_fixes_drift_from_gguf(self, tmp_path):
        reg = {
            "unsloth/glm-4.7-flash": {
                "arch": "dense",
                "n_layers": 60,
                "hidden_dim": 5000,
                "max_context_length": 65536,
                "reasoning": "instruct",
            }
        }
        gguf_path = self._gguf_path(tmp_path, "unsloth/GLM-4.7-Flash-GGUF/x.gguf")
        lms = [self._lms("GLM-4.7-Flash", "unsloth/GLM-4.7-Flash-GGUF/x.gguf")]
        gguf = {gguf_path: (61, 5120, True, 131072)}
        out = self._run(tmp_path, reg, lms, gguf, {gguf_path: True})
        e = out["unsloth/glm-4.7-flash"]
        assert e["n_layers"] == 61
        assert e["hidden_dim"] == 5120
        assert e["max_context_length"] == 131072
        assert e["arch"] == "moe"
        assert e["reasoning"] == "instruct"  # gesetzt -> unangetastet

    def test_conformant_entries_untouched(self, tmp_path):
        reg = {
            "unsloth/glm-4.7-flash": {
                "arch": "moe",
                "n_layers": 61,
                "hidden_dim": 5120,
                "max_context_length": 131072,
                "reasoning": "thinking",
            }
        }
        gguf_path = self._gguf_path(tmp_path, "unsloth/GLM-4.7-Flash-GGUF/x.gguf")
        lms = [self._lms("GLM-4.7-Flash", "unsloth/GLM-4.7-Flash-GGUF/x.gguf")]
        gguf = {gguf_path: (61, 5120, True, 131072)}
        out = self._run(tmp_path, reg, lms, gguf, {gguf_path: True})
        assert out["unsloth/glm-4.7-flash"] == {
            "arch": "moe",
            "n_layers": 61,
            "hidden_dim": 5120,
            "max_context_length": 131072,
            "reasoning": "thinking",
            "max_experts": 1,
        }

    def test_models_without_gguf_match_untouched(self, tmp_path):
        reg = {"unsloth/glm-4.7-flash": {"arch": "dense", "n_layers": 60}}
        self._gguf_path(tmp_path, "unsloth/GLM-4.7-Flash-GGUF/x.gguf")
        lms = [self._lms("GLM-4.7-Flash", "unsloth/GLM-4.7-Flash-GGUF/x.gguf")]
        out = self._run(tmp_path, reg, lms, {}, {})
        assert out["unsloth/glm-4.7-flash"]["n_layers"] == 60

    def test_empty_registry_exits_with_error(self, tmp_path):
        path = _write_registry(tmp_path, {})
        with (
            patch.object(rt, "REGISTRY_PATH", path),
            patch.object(rt, "_run_lms_ls", return_value=[]),
            pytest.raises(SystemExit),
        ):
            rt.cmd_sync_from_gguf()


# ─────────────────────────────────────────────────────────────────────
# pipeline full: Exit-Code-Logik bei offenen Melde-Konflikten
# ─────────────────────────────────────────────────────────────────────


class TestPipelineDriftExitCode:
    """pipeline full endet mit Exit 1, wenn Melde-Konflikte (Feld-Ownership)
    offen sind; mit --ignore-drift bzw. konvergiertem Zustand Exit 0."""

    def _run_pipeline(self, validate_errors, ignore_drift=False):
        with (
            patch.object(
                rt,
                "_collect_registry_inventory",
                return_value=rt.RegistryInventory({}, [], [], [], [], True),
            ),
            patch.object(rt, "cmd_compare"),
            patch.object(rt, "cmd_sync"),
            patch.object(rt, "classify_registry"),
            patch.object(rt, "assemble_prompts"),
            patch.object(rt, "cmd_patch_glm_configs"),
            patch.object(rt, "validate_prompts"),
            patch.object(rt, "cmd_validate", return_value=validate_errors),
        ):
            return rt.cmd_pipeline("full", ignore_drift=ignore_drift)

    def test_drift_checks_constant(self):
        assert "config_context_drift" not in rt._DRIFT_CHECKS
        assert "config_context_too_small" not in rt._DRIFT_CHECKS
        assert "config_experts_drift" in rt._DRIFT_CHECKS
        assert "runtime_experts_missing" in rt._DRIFT_CHECKS
        assert "gguf_header_drift" in rt._DRIFT_CHECKS

    def test_no_drift_exits_0(self):
        assert self._run_pipeline({"config_np_ukv_drift": [], "gguf_header_drift": []}) is None

    def test_open_drift_exits_1(self):
        with pytest.raises(SystemExit) as exc:
            self._run_pipeline({"runtime_experts_missing": ["unsloth/x: experts missing"]})
        assert exc.value.code == 1

    def test_ignore_drift_exits_0(self):
        assert self._run_pipeline({"runtime_experts_missing": ["unsloth/x: experts missing"]}, ignore_drift=True) is None

    def test_lm_studio_context_drift_does_not_block_pipeline(self):
        errors = {
            "config_context_drift": ["unsloth/x: LMS context differs from Registry"],
            "config_context_too_small": ["unsloth/x: LMS context exceeds native limit"],
        }
        assert self._run_pipeline(errors) is None

    def test_non_drift_errors_do_not_exit(self):
        # template_missing_file etc. sind keine Melde-Konflikte -> kein Exit
        assert self._run_pipeline({"template_missing_file": ["unsloth/x: fehlt"]}) is None

    @pytest.mark.parametrize("import_lms_settings", [False, True])
    def test_full_prints_explicit_write_paths_after_previews(self, import_lms_settings, capsys):
        calls = []

        def record_quarantine(*, dry_run=False, inventory=None):
            calls.append(("quarantine", dry_run))
            return 0

        def record_assemble(*, preview_only=False, identity_links=None):
            calls.append(("assemble", preview_only))

        def record_templates(*_args, **_kwargs):
            calls.append(("templates",))

        with (
            patch.object(
                rt,
                "_collect_registry_inventory",
                return_value=rt.RegistryInventory({}, [], [], [], [], True),
            ),
            patch.object(rt, "cmd_compare"),
            patch.object(rt, "cmd_quarantine_missing", side_effect=record_quarantine),
            patch.object(rt, "cmd_sync"),
            patch.object(rt, "classify_registry"),
            patch.object(rt, "cmd_sync_templates", side_effect=record_templates),
            patch.object(rt, "assemble_prompts", side_effect=record_assemble),
            patch.object(rt, "cmd_patch_glm_configs", side_effect=AssertionError("config patch must not run")),
            patch.object(rt, "validate_prompts"),
            patch.object(rt, "cmd_validate", return_value={"gguf_header_drift": []}),
        ):
            assert rt.cmd_pipeline("full", import_lms_settings=import_lms_settings) is None

        assert calls == [("quarantine", True), ("templates",), ("assemble", True)]
        output = capsys.readouterr().out
        assert "py -3.12 .\\src\\registry_tool.py quarantine-missing --apply" in output
        assert "py -3.12 .\\src\\registry_tool.py full --write-prompts" in output
        assert output.index("quarantine-missing --apply") < output.index("Prompt-Assembly")
        assert output.index("Prompt-Assembly") < output.index("registry_tool.py full --write-prompts")
        if import_lms_settings:
            assert "LM-Studio-Werte wurden nur berichtet" not in output
        else:
            assert "py -3.12 .\\src\\registry_tool.py sync --import-lms-settings" in output


def test_lm_studio_local_findings_are_advisory_for_backend_validation() -> None:
    errors = {
        "template_missing_config": ["model: promptTemplate missing"],
        "registry_no_config": ["model: no LM Studio config"],
        "config_context_drift": ["model: local context differs"],
        "config_context_too_small": ["model: local context exceeds native maximum"],
        "config_np_ukv_drift": ["model: local UKV differs"],
        "runtime_experts_missing": ["model: runtime experts missing"],
        "missing_quant": ["model: quant identity missing"],
    }

    blockers = rt._blocking_validation_errors(errors)

    assert blockers == {
        "runtime_experts_missing": ["model: runtime experts missing"],
        "missing_quant": ["model: quant identity missing"],
    }


def test_assemble_adds_system_prompt_without_touching_load_fields(tmp_path, monkeypatch):
    config_root = tmp_path / "configs"
    publisher_dir = config_root / "mistralai"
    publisher_dir.mkdir(parents=True)
    config_path = publisher_dir / "ministral-3-14b-reasoning.json"
    original_load_fields = [
        {"key": "llm.load.llama.kCacheQuantizationType", "value": "q8_0"},
        {"key": "llm.load.llama.vCacheQuantizationType", "value": "q5_1"},
    ]
    config_path.write_text(
        json.dumps(
            {
                "preset": "",
                "operation": {"fields": [{"key": "custom.field", "value": "keep"}]},
                "load": {"fields": original_load_fields},
            }
        ),
        encoding="utf-8",
    )

    registry_path = tmp_path / "model_registry.yaml"
    registry_path.write_text(
        "mistralai/ministral-3-14b-reasoning:\n"
        "  publisher: mistralai\n"
        "  arch: ministral\n"
        "  reasoning: thinking\n"
        "  blueprint: default_chat\n"
        "  truncation: full\n",
        encoding="utf-8",
    )
    blueprint_path = tmp_path / "blueprint_definitions.yaml"
    blueprint_path.write_text(
        "blueprints:\n"
        "  default_chat:\n"
        "    role: A helpful assistant.\n"
        "    modules: []\n"
        "modules: {}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(ab, "CONFIG_ROOT", config_root)
    monkeypatch.setattr(ab, "REGISTRY_PATH", registry_path)
    monkeypatch.setattr(ab, "BLUEPRINT_PATH", blueprint_path)
    monkeypatch.setattr(ab, "TEMPLATE_DIR", tmp_path / "templates")
    ab._LMS_CONFIGS_CACHE.clear()

    ab.assemble_prompts(preview_only=False)

    written = json.loads(config_path.read_text(encoding="utf-8"))
    fields = written["operation"]["fields"]
    assert next(field["value"] for field in fields if field["key"] == "custom.field") == "keep"
    assert next(field["value"] for field in fields if field["key"] == "llm.prediction.systemPrompt")
    assert written["load"]["fields"] == original_load_fields


# =========================================================================
# _registry_template_name (Blueprint SSOT, Refactor 14.08.)
# =========================================================================


class TestRegistryTemplateName:
    def test_resolves_from_blueprint_template_map(self):
        # gemma4-26b -> gemma_reasoning -> template_map 26b
        model_key = "unsloth/gemma-4-26b-a4b-it@iq3_s"
        registry = {model_key: {"blueprint": "gemma_reasoning"}}
        with patch.object(rt, "load_registry", return_value=registry):
            name = rt._registry_template_name(model_key)
        assert name == "google_gemma-4-26B-A4B-it_chat_template.jinja"

    def test_resolves_from_blueprint_direct_template(self):
        # openai/gpt-oss-20b@mxfp4 -> gptoss_reasoning -> template
        registry = {
            "openai/gpt-oss-20b@mxfp4": {"blueprint": "gptoss_reasoning"}
        }
        with patch.object(rt, "load_registry", return_value=registry):
            name = rt._registry_template_name("openai/gpt-oss-20b@mxfp4")
        assert name == "gpt-oss-20b_harmony.jinja"

    def test_explicit_registry_template_overrides_blueprint(self) -> None:
        registry = {
            "unsloth/gpt-oss-20b-GGUF@q8_0": {
                "blueprint": "gptoss_reasoning",
                "template_policy": "explicit_file",
                "template_variant": "unsloth_harmony_fix",
                "template": "gpt-oss-20b-template_unsloth.jinja",
            }
        }
        with patch.object(rt, "load_registry", return_value=registry):
            name = rt._registry_template_name("unsloth/gpt-oss-20b-GGUF@q8_0")
        assert name == "gpt-oss-20b-template_unsloth.jinja"

    def test_legacy_registry_field_fallback(self):
        # Blueprint ohne Template -> Fallback auf das (veraltete) Registry-Feld.
        fake_reg = {"unsloth/legacy-model@q4_k_m": {"blueprint": "default_chat", "template": "legacy.jinja"}}
        with (
            patch.object(rt, "load_registry", return_value=fake_reg),
            patch.object(rt, "_load_blueprints", return_value={"default_chat": {"role": "r"}}),
        ):
            name = rt._registry_template_name("unsloth/legacy-model@q4_k_m")
        assert name == "legacy.jinja"

    def test_returns_none_when_no_template_anywhere(self):
        name = rt._registry_template_name("lmstudio-community/plain-7b@q4_k_m")
        assert name is None


# =========================================================================
# glm_patch_config (Fix 14.08.: GLM sind Reasoning-Modelle -> parsing enabled)
# =========================================================================


class TestGlmPatchConfig:
    def _config(self, enabled: bool | None = None) -> dict:
        fields = [{"key": "llm.prediction.structured", "value": {"type": "json_object"}}]
        if enabled is not None:
            fields.append(
                {
                    "key": "llm.prediction.reasoning.parsing",
                    "value": {"enabled": enabled, "startString": " thinking", "endString": " response"},
                }
            )
        fields.append({
            "key": "llm.prediction.reasoning.budgetTokens",
            "value": {"checked": True, "value": 4096},
        })
        return {"operation": {"fields": fields}}

    def _write(self, tmp_path, data) -> Path:
        p = tmp_path / "glm.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        return p

    def _parsing(self, data) -> dict:
        return next(f for f in data["operation"]["fields"] if f["key"] == "llm.prediction.reasoning.parsing")

    def test_sets_parsing_enabled_when_false(self, tmp_path: Path) -> None:
        p = self._write(tmp_path, self._config(enabled=False))
        with patch.object(rt, "_pre_backup_path", return_value=str(tmp_path / "backup.json")):
            changed, actions, _ = rt.glm_patch_config(str(p))
        assert changed is True
        assert "reasoning.parsing synchronized" in actions
        assert self._parsing(json.loads(p.read_text(encoding="utf-8")))["value"]["enabled"] is True

    def test_adds_parsing_when_missing(self, tmp_path: Path) -> None:
        p = self._write(tmp_path, self._config(enabled=None))
        with patch.object(rt, "_pre_backup_path", return_value=str(tmp_path / "backup.json")):
            changed, actions, _ = rt.glm_patch_config(str(p))
        assert changed is True
        assert "reasoning.parsing added" in actions
        rp = self._parsing(json.loads(p.read_text(encoding="utf-8")))
        assert rp["value"]["enabled"] is True
        assert rp["value"]["startString"] == " thinking"
        assert rp["value"]["endString"] == " response"

    def test_leaves_enabled_config_untouched(self, tmp_path: Path) -> None:
        p = self._write(tmp_path, self._config(enabled=True))
        with patch.object(rt, "_pre_backup_path", return_value=str(tmp_path / "backup.json")):
            changed, actions, _ = rt.glm_patch_config(str(p))
        assert changed is False
        assert actions == []

    def test_preserves_gui_structured_field(self, tmp_path: Path) -> None:
        p = self._write(tmp_path, self._config(enabled=False))
        with patch.object(rt, "_pre_backup_path", return_value=str(tmp_path / "backup.json")):
            rt.glm_patch_config(str(p))
        data = json.loads(p.read_text(encoding="utf-8"))
        keys = [f["key"] for f in data["operation"]["fields"]]
        assert "llm.prediction.structured" in keys

    def test_does_not_add_gui_structured_field(self, tmp_path: Path) -> None:
        config = self._config(enabled=False)
        config["operation"]["fields"] = [
            field for field in config["operation"]["fields"]
            if field["key"] != "llm.prediction.structured"
        ]
        p = self._write(tmp_path, config)
        with patch.object(rt, "_pre_backup_path", return_value=str(tmp_path / "backup.json")):
            rt.glm_patch_config(str(p))
        data = json.loads(p.read_text(encoding="utf-8"))
        keys = [f["key"] for f in data["operation"]["fields"]]
        assert "llm.prediction.structured" not in keys

    def test_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        p = self._write(tmp_path, self._config(enabled=False))
        original = p.read_text(encoding="utf-8")
        changed, _actions, backup = rt.glm_patch_config(str(p), dry_run=True)
        assert changed is True
        assert backup is None
        assert p.read_text(encoding="utf-8") == original
