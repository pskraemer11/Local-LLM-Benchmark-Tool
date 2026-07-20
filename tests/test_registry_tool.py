"""Tests for registry_tool.py (Code-Review 2026-07-18 §5: test coverage).

The registry tool is the most logic-dense file in the project
(VRAM formula, match cascades, _infer_num_parallel rules). The
test coverage was the largest gap in the review.

Targets:
  5.1  _max_ctx_from_vram() and VRAM constants
  5.2  Match cascade in cmd_configs (registry ↔ JSON config)
  5.3  _infer_num_parallel() with all keyword rules
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import registry_tool as rt
from registry_tool import (
    _infer_num_parallel,
    _max_ctx_from_vram,
    _KV_BYTES,
    _USABLE_VRAM_GB,
    _USE_UNIFIED_KV_CACHE_THRESHOLD_GB,
    _LEGACY_MODEL_GB_THRESHOLD_GB,
)


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
        assert 0.45 < (ctx_2 / ctx_1) < 0.55, (
            f"ctx should halve with np=2: ctx_1={ctx_1}, ctx_2={ctx_2}"
        )

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
        assert _USE_UNIFIED_KV_CACHE_THRESHOLD_GB == 14.0

    def test_legacy_threshold(self):
        assert _LEGACY_MODEL_GB_THRESHOLD_GB == 9.0


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
            "load": {
                "fields": [
                    {"key": k, "value": v}
                    for k, v in fields.items()
                ]
            },
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return json_path

    def test_no_arch_data_falls_back_to_legacy_threshold(self, fake_config):
        # Model with no n_layers/hidden_dim, model_gb >= 9 → UKV on
        sub = fake_config / "publisher"
        json_path = self._make_config(
            sub, sub / "m.json",
            **{"llm.load.contextLength": 8192}
        )
        registry = {
            "publisher/m": {
                "file_size_bytes": 10_000_000_000,  # 10 GB
                # No n_layers, no hidden_dim
                "context_length": 16384,
                "num_parallel": 1,
                "k_cache": "q8_0",
                "v_cache": "iq4_nl",
            }
        }
        with patch.object(rt, "load_registry", return_value=registry), \
             patch.object(rt, "CONFIG_ROOT", fake_config), \
             patch.object(rt, "read_lms_configs",
                          return_value=[{
                              "dir_name": "m",
                              "publisher": "publisher",
                              "context_length": 8192,
                              "offload": 1.0,
                              "num_parallel": 1,
                              "use_unified_kv": True,
                              "json_path": json_path,
                          }]):
            rt.cmd_configs()
        # Re-read the JSON
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        fields = {f["key"]: f["value"] for f in data["load"]["fields"]}
        # Legacy threshold: model_gb (10) >= 9.0 → UKV ON
        assert fields.get("llm.load.useUnifiedKvCache") is True

    def test_arch_data_uses_precise_formula(self, fake_config):
        # Model with arch data, np=1, small context → UKV OFF
        sub = fake_config / "publisher"
        json_path = self._make_config(
            sub, sub / "m.json",
            **{"llm.load.contextLength": 2048}
        )
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
        with patch.object(rt, "load_registry", return_value=registry), \
             patch.object(rt, "CONFIG_ROOT", fake_config), \
             patch.object(rt, "read_lms_configs",
                          return_value=[{
                              "dir_name": "m",
                              "publisher": "publisher",
                              "context_length": 2048,
                              "offload": 1.0,
                              "num_parallel": 1,
                              "use_unified_kv": False,
                              "json_path": json_path,
                          }]):
            rt.cmd_configs()
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        fields = {f["key"]: f["value"] for f in data["load"]["fields"]}
        assert fields.get("llm.load.useUnifiedKvCache") is False

    def test_benchmark_context_limit_override(self, fake_config):
        # If registry has benchmark_context_limit, it overrides
        # the formula-computed bcl
        sub = fake_config / "publisher"
        json_path = self._make_config(
            sub, sub / "m.json",
            **{"llm.load.contextLength": 16384}
        )
        registry = {
            "publisher/m": {
                "file_size_bytes": 8_000_000_000,
                "n_layers": 40,
                "hidden_dim": 5120,
                "context_length": 16384,  # Native
                "num_parallel": 1,
                "k_cache": "q8_0",
                "v_cache": "iq4_nl",
                "benchmark_context_limit": 4096,  # Override
            }
        }
        with patch.object(rt, "load_registry", return_value=registry), \
             patch.object(rt, "CONFIG_ROOT", fake_config), \
             patch.object(rt, "read_lms_configs",
                          return_value=[{
                              "dir_name": "m",
                              "publisher": "publisher",
                              "context_length": 16384,
                              "offload": 1.0,
                              "num_parallel": 1,
                              "use_unified_kv": False,
                              "json_path": json_path,
                          }]):
            rt.cmd_configs()
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        fields = {f["key"]: f["value"] for f in data["load"]["fields"]}
        # Override → 4096, not 16384 and not formula-computed
        assert fields.get("llm.load.contextLength") == 4096

    def test_context_capped_at_native(self, fake_config):
        # If formula gives more than native context_length, native wins
        sub = fake_config / "publisher"
        json_path = self._make_config(
            sub, sub / "m.json",
            **{"llm.load.contextLength": 16384}
        )
        # Tiny model: 4 GB → can fit huge context, but capped at native 16384
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
        with patch.object(rt, "load_registry", return_value=registry), \
             patch.object(rt, "CONFIG_ROOT", fake_config), \
             patch.object(rt, "read_lms_configs",
                          return_value=[{
                              "dir_name": "m",
                              "publisher": "publisher",
                              "context_length": 16384,
                              "offload": 1.0,
                              "num_parallel": 1,
                              "use_unified_kv": False,
                              "json_path": json_path,
                          }]):
            rt.cmd_configs()
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        fields = {f["key"]: f["value"] for f in data["load"]["fields"]}
        # 4 GB model can fit 15+ GB of KV cache → ctx capped at 16384
        assert fields.get("llm.load.contextLength") == 16384


# ─────────────────────────────────────────────────────────────────────
# 5.3 _infer_num_parallel
# ─────────────────────────────────────────────────────────────────────

class TestInferNumParallel:
    """Rules: ERNIE → 1, MoE → 4, GPT-OSS → 4, MTP → 2, Dense → 1."""

    def test_dense_default(self):
        # No keywords → 1
        assert _infer_num_parallel("Llama Dense", "llama-3.1-8b") == 1

    def test_ernie_forced_to_1(self):
        # ERNIE always gets np=1 (CUDA kernel overhead)
        assert _infer_num_parallel("ERNIE MoE", "baidu/ernie-4.5-21b") == 1

    def test_ernie_substring(self):
        # "ernie" anywhere in arch → 1
        assert _infer_num_parallel("Something-ernie-like", "any-model") == 1

    def test_moe_in_arch(self):
        # "moe" in arch field → 4
        assert _infer_num_parallel("Llama MoE", "model") == 4

    def test_moe_substring_in_key_a4b(self):
        # a4b = active params → MoE
        assert _infer_num_parallel("Llama Dense", "gemma-4-26b-a4b") == 4

    def test_moe_substring_in_key_a3b(self):
        assert _infer_num_parallel("Llama Dense", "kimi-linear-35b-a3b") == 4

    def test_moe_substring_a2b(self):
        assert _infer_num_parallel("Llama Dense", "lfm2-24b-a2b") == 4

    def test_moe_substring_kimi(self):
        assert _infer_num_parallel("Llama Dense", "kimi-linear-48b-a3b") == 4

    def test_moe_substring_glm_flash(self):
        assert _infer_num_parallel("Llama Dense", "glm-4.7-flash") == 4

    def test_gpt_oss_forced_to_4(self):
        # GPT-OSS despite being Dense benefits from parallel
        assert _infer_num_parallel("GPT-OSS Dense", "openai/gpt-oss-20b") == 4

    def test_gpt_oss_underscore_alias(self):
        assert _infer_num_parallel("Llama", "gpt_oss_20b") == 4

    def test_mtp_forced_to_2(self):
        # MTP models need np >= Max Draft Tokens
        assert _infer_num_parallel("Qwen Dense", "qwen3.6-27b-mtp") == 2

    def test_priority_ernie_beats_moe(self):
        # Even if both "ernie" and "moe" appear, ERNIE rule wins (early check)
        assert _infer_num_parallel("ERNIE MoE", "model-a4b") == 1

    def test_priority_moe_beats_a4b_keyword(self):
        # arch says "moe" → 4 regardless of model_identifier
        assert _infer_num_parallel("Custom MoE", "model-a4b") == 4

    def test_priority_kimi_beats_a4b(self):
        # kimi in key OR a4b in key → 4 (kimi hits first in substring list)
        assert _infer_num_parallel("Llama", "kimi-a4b") == 4


# ─────────────────────────────────────────────────────────────────────
# Integration: cmd_configs end-to-end
# ─────────────────────────────────────────────────────────────────────

class TestCmdConfigsIntegration:
    """End-to-end cmd_configs() with mocked registry + LMS configs."""

    def test_skips_models_with_no_match(self, tmp_path):
        # A JSON config that doesn't match any registry entry is skipped
        cfg_dir = tmp_path / "user-concrete-model-default-config" / "pub"
        cfg_dir.mkdir(parents=True)
        json_path = cfg_dir / "unmatched.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({
                "operation": {"fields": []},
                "load": {"fields": []},
            }, f)
        with patch.object(rt, "load_registry", return_value={}), \
             patch.object(rt, "CONFIG_ROOT", tmp_path / "user-concrete-model-default-config"), \
             patch.object(rt, "read_lms_configs",
                          return_value=[{
                              "dir_name": "unmatched",
                              "publisher": "pub",
                              "context_length": 8192,
                              "offload": 1.0,
                              "num_parallel": 1,
                              "use_unified_kv": False,
                              "json_path": json_path,
                          }]):
            # Should not raise, should not modify the file
            rt.cmd_configs()
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # JSON should be unchanged (no new fields added)
        assert data["load"]["fields"] == []
