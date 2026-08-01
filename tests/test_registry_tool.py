"""Tests for registry_tool.py (Code-Review 2026-07-18 §5: test coverage).

The registry tool is the most logic-dense file in the project
(VRAM formula, match cascades, _infer_num_parallel rules). The
test coverage was the largest gap in the review.

Targets:
  5.1  _max_ctx_from_vram() and VRAM constants
  5.2  Match cascade in cmd_configs (registry ↔ JSON config)
  5.3  _infer_num_parallel() classification rules (post-refactoring)
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import registry_tool as rt
from registry_tool import (
    _classify_arch,
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
        # contextLength is no longer overwritten by cmd_configs;
        # the user's manually set value is preserved.
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
                "context_length": 16384,
                "num_parallel": 1,
                "k_cache": "q8_0",
                "v_cache": "iq4_nl",
                "benchmark_context_limit": 4096,
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
        # contextLength was NOT overwritten — user's value (16384) preserved
        assert fields.get("llm.load.contextLength") == 16384

    def test_context_capped_at_native(self, fake_config):
        # contextLength is no longer overwritten by cmd_configs;
        # the user's manually set value is preserved.
        sub = fake_config / "publisher"
        json_path = self._make_config(
            sub, sub / "m.json",
            **{"llm.load.contextLength": 16384}
        )
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
        # contextLength was NOT overwritten — user's value (16384) preserved
        assert fields.get("llm.load.contextLength") == 16384


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


class TestInferNumParallel:
    """Rules (nach Refactoring 2026-07-31): ``"moe"`` / ``"mtp"`` → 4, sonst → 1.

    Die alte Heuristik (ERNIE→1, GPT-OSS→4, MTP→2, a3b/a4b-Keywords) wurde
    entfernt: MoE-Erkennung kommt jetzt aus dem GGUF-``expert_count``
    (Single Source of Truth, siehe ``_classify_arch``).
    """

    def test_moe_returns_4(self):
        assert _infer_num_parallel("moe") == 4

    def test_mtp_returns_4(self):
        assert _infer_num_parallel("mtp") == 4

    def test_dense_returns_1(self):
        assert _infer_num_parallel("dense") == 1

    def test_unknown_classification_returns_1(self):
        assert _infer_num_parallel("unknown-arch") == 1

    def test_empty_returns_1(self):
        assert _infer_num_parallel("") == 1


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


# ─────────────────────────────────────────────────────────────────────
# cmd_fix_np: exaktes lms-Matching + Duplikat-Kollaps
# ─────────────────────────────────────────────────────────────────────

class TestFixNp:
    """cmd_fix_np nach Verschärfung 2026-07-31.

    Früher genügte der Besitz von ≥2 signifikanten Wörtern (Fuzz-Match),
    wodurch Phantom-Varianten (-ud, -mxfp4, -imatrix, doppelte Publisher)
    und Duplikate in der Registry überlebten. Jetzt gilt:
    - exakter normalize-Match gegen die lms-Key-Varianten, oder
    - eigene GGUF-Datei, oder
    - Auflösung auf eine Datei, die einem lms-Modell gehört → Duplikat
    Mehrere Registry-Keys auf dasselbe Ziel → nur der beste bleibt.
    """

    def _run(self, registry, lms_models, tmp_path, resolve="", gguf_experts=False):
        saved = {}
        if callable(resolve):
            resolve_patch = patch.object(rt, "_resolve_model_path_multi", side_effect=resolve)
        else:
            resolve_patch = patch.object(rt, "_resolve_model_path_multi", return_value=resolve)
        with patch.object(rt, "load_registry", return_value=registry), \
             patch.object(rt, "save_registry", side_effect=lambda r: saved.update(r)), \
             patch.object(rt, "_run_lms_ls", return_value=lms_models), \
             patch.object(rt, "MODELS_CACHE", tmp_path), \
             patch.object(rt, "_GGUF_FILE_CACHE", None), \
             resolve_patch, \
             patch.object(rt, "_gguf_has_experts", return_value=gguf_experts):
            rt.cmd_fix_np()
        return saved

    def test_normalize_variants_strips_publisher_and_underscore(self):
        assert rt._normalize_variants("unsloth/phi-4") == {"phi-4"}
        assert rt._normalize_variants("['microsoft', 'unsloth']/phi-4") == {"phi-4"}
        assert rt._normalize_variants("mistralai_magistral-small-2509") == {
            "mistralai-magistral-small-2509",
        }
        assert rt._normalize_variants("qwen3.6-27b@q5_0") == {"qwen3-6-27b"}

    def test_quant_suffixed_keys_stay_distinct(self, tmp_path):
        # lms unterscheidet Quants; @-Keys dürfen NICHT als Duplikate
        # voneinander gelöscht werden (ehemalige Kollision: base-Variante
        # ist für alle Quants identisch).
        (tmp_path / "q").mkdir(parents=True)
        for f in ("q5_0.gguf", "q6_k.gguf"):
            (tmp_path / "q" / f).write_bytes(b"x")
        lms = [
            {"modelKey": "qwen2.5-coder-14b-instruct@q5_0", "path": "q/q5_0.gguf"},
            {"modelKey": "qwen2.5-coder-14b-instruct@q6_k", "path": "q/q6_k.gguf"},
        ]
        registry = {
            "qwen2.5-coder-14b-instruct@q5_0": {"file_size_bytes": 1},
            "qwen2.5-coder-14b-instruct@q6_k": {"file_size_bytes": 2},
        }
        saved = self._run(registry, lms, tmp_path)
        assert set(saved) == {
            "qwen2.5-coder-14b-instruct@q5_0",
            "qwen2.5-coder-14b-instruct@q6_k",
        }

    def test_duplicate_publisher_keys_collapse_keeping_best(self, tmp_path):
        # unsloth/phi-4 (Publisher im lms-Key enthalten → Score-Bonus)
        # gewinnt gegen ['microsoft', 'unsloth']/phi-4.
        p = tmp_path / "unsloth" / "phi-4"
        p.mkdir(parents=True)
        (p / "phi-4-Q5_K_M.gguf").write_bytes(b"x")
        lms = [{"modelKey": "unsloth/phi-4", "path": "unsloth/phi-4/phi-4-Q5_K_M.gguf"}]
        registry = {
            "unsloth/phi-4": {"file_size_bytes": 1},
            "['microsoft', 'unsloth']/phi-4": {"file_size_bytes": 1},
        }
        saved = self._run(registry, lms, tmp_path)
        assert set(saved) == {"unsloth/phi-4"}

    def test_phantom_without_lms_and_without_file_is_removed(self, tmp_path):
        lms = [{"modelKey": "unsloth/phi-4", "path": "unsloth/phi-4/phi-4-Q5_K_M.gguf"}]
        registry = {
            "unsloth/phi-4": {"file_size_bytes": 1},
            "bartowski/gpt-oss-20b": {"file_size_bytes": 1},          # kein lms, keine Datei
            "unsloth/qwen3.6-27b-ud": {"file_size_bytes": 1},         # Varianten-Phantom
            "google/gemma-4-26b-a4b-it-quat@q4_0": {"file_size_bytes": 1},
        }
        saved = self._run(registry, lms, tmp_path)
        assert set(saved) == {"unsloth/phi-4"}

    def test_duplicate_via_file_resolution_is_removed(self, tmp_path):
        # mistralai/magistral-small-2509 hat KEINEN exakten Key-Match,
        # löst aber auf die Datei von lms 'mistralai_magistral-small-2509'
        # auf → Duplikat. Der exakt passende bartowski-Key bleibt.
        p = tmp_path / "bartowski" / "mistralai_Magistral-Small-2509-GGUF"
        p.mkdir(parents=True)
        mag = p / "mistralai_Magistral-Small-2509-Q3_K_M.gguf"
        mag.write_bytes(b"x")

        lms = [{
            "modelKey": "mistralai_magistral-small-2509",
            "path": "bartowski/mistralai_Magistral-Small-2509-GGUF/mistralai_Magistral-Small-2509-Q3_K_M.gguf",
        }]
        registry = {
            "bartowski/mistralai_magistral-small-2509": {"file_size_bytes": 1},
            "mistralai/magistral-small-2509": {"file_size_bytes": 1},
            "mistralai/magistral-small": {"file_size_bytes": 1},
        }
        saved = self._run(registry, lms, tmp_path)
        assert set(saved) == {"bartowski/mistralai_magistral-small-2509"}

    def test_ud_entry_resolving_to_base_file_is_duplicate(self, tmp_path):
        # unsloth/qwen3.6-27b-ud besitzt keine eigene Datei; die Auflösung
        # landet auf der Datei des MTP-Modells → Duplikat, Basismodelle
        # bleiben beide erhalten.
        p = tmp_path / "unsloth" / "qwen3.6-27b-mtp"
        p.mkdir(parents=True)
        ud_file = p / "Qwen3.6-27B-UD-IQ3_XXS.gguf"
        ud_file.write_bytes(b"x")
        lms = [
            {"modelKey": "qwen3.6-27b", "path": "unsloth/qwen3.6-27b/Qwen3.6-27B-Q3_K_S.gguf"},
            {"modelKey": "qwen3.6-27b-mtp", "path": "unsloth/qwen3.6-27b-mtp/Qwen3.6-27B-UD-IQ3_XXS.gguf"},
        ]
        registry = {
            "unsloth/qwen3.6-27b": {"file_size_bytes": 1},
            "unsloth/qwen3.6-27b-mtp": {"file_size_bytes": 1},
            "unsloth/qwen3.6-27b-ud": {"file_size_bytes": 1},
        }

        def fake_resolve(key):
            if key == "unsloth/qwen3.6-27b-ud":
                return str(ud_file)
            return ""

        with patch.object(rt, "_resolve_model_path_multi", side_effect=fake_resolve):
            saved = self._run(registry, lms, tmp_path)
        assert set(saved) == {"unsloth/qwen3.6-27b", "unsloth/qwen3.6-27b-mtp"}

    def test_directory_models_keep_best_publisher_key(self, tmp_path):
        # openai/gpt-oss-20b ist ein Verzeichnis-Modell (kein GGUF).
        # Alle drei Registry-Keys matchen exakt; der mit dem Publisher,
        # der im lms-Key vorkommt, gewinnt.
        lms = [{"modelKey": "openai/gpt-oss-20b", "path": "openai/gpt-oss-20b"}]
        registry = {
            "openai/gpt-oss-20b": {"file_size_bytes": 1},
            "lmstudio-community/gpt-oss-20b": {"file_size_bytes": 1},
            "unsloth/gpt-oss-20b": {"file_size_bytes": 1},
        }
        saved = self._run(registry, lms, tmp_path)
        assert set(saved) == {"openai/gpt-oss-20b"}

    def test_classification_applied_to_survivors(self, tmp_path):
        p = tmp_path / "unsloth" / "qwen3.6-27b"
        p.mkdir(parents=True)
        (p / "Qwen3.6-27B-Q3_K_S.gguf").write_bytes(b"x")
        lms = [{"modelKey": "qwen3.6-27b", "path": "unsloth/qwen3.6-27b/Qwen3.6-27B-Q3_K_S.gguf"}]
        registry = {"unsloth/qwen3.6-27b": {"file_size_bytes": 1}}
        saved = self._run(registry, lms, tmp_path, gguf_experts=True)
        assert saved["unsloth/qwen3.6-27b"]["arch"] == "moe"
        assert saved["unsloth/qwen3.6-27b"]["num_parallel"] == 4

    def test_no_lms_data_means_no_duplicate_collapse(self, tmp_path):
        # lms ls fehlgeschlagen (leere Liste): Quant-Varianten dürfen NICHT
        # kollabieren (Regression: qwen2.5-coder-14b-instruct@q6_k wurde
        # fälschlich als "Duplikat von @q5_0" gelöscht). Jede Quant-Datei
        # existiert eigenständig → beide Einträge bleiben erhalten.
        p = tmp_path / "Qwen" / "Qwen2.5-Coder-14B-Instruct-GGUF"
        p.mkdir(parents=True)
        (p / "qwen2.5-coder-14b-instruct-q5_0.gguf").write_bytes(b"x")
        (p / "qwen2.5-coder-14b-instruct-q6_k.gguf").write_bytes(b"x")
        registry = {
            "qwen/qwen2.5-coder-14b-instruct@q5_0": {"file_size_bytes": 1},
            "qwen/qwen2.5-coder-14b-instruct@q6_k": {"file_size_bytes": 1},
        }
        saved = self._run(registry, [], tmp_path)
        assert set(saved) == {
            "qwen/qwen2.5-coder-14b-instruct@q5_0",
            "qwen/qwen2.5-coder-14b-instruct@q6_k",
        }


# ─────────────────────────────────────────────────────────────────────
# GGUF-Reasoning-Erkennung (_read_gguf_arch / _detect_reasoning_from_template)
# ─────────────────────────────────────────────────────────────────────

def _make_mini_gguf(block_count: int, embedding_length: int, chat_template: str | None) -> bytes:
    """Synthetischer GGUF-Header: block_count/embedding_length VOR chat_template."""
    import struct

    buf = bytearray(b"GGUF")
    buf += struct.pack("<IQ", 3, 0)  # version, tensor_count
    kvs = []
    for key, vtype, payload in [
        ("qwen2.block_count", 4, struct.pack("<I", block_count)),
        ("qwen2.embedding_length", 4, struct.pack("<I", embedding_length)),
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


class TestReadGgufArchReasoning:
    """_read_gguf_arch liest tokenizer.chat_template auch NACH block_count/embedding_length."""

    def test_reasoning_detected_when_template_after_arch(self, tmp_path):
        p = tmp_path / "model.gguf"
        p.write_bytes(_make_mini_gguf(48, 5120, "{% if enable_thinking %}<think>{% endif %}"))
        nl, hd, is_reasoning = rt._read_gguf_arch(str(p))
        assert nl == 48
        assert hd == 5120
        assert is_reasoning is True

    def test_no_template_yields_false(self, tmp_path):
        p = tmp_path / "model.gguf"
        p.write_bytes(_make_mini_gguf(48, 5120, None))
        nl, hd, is_reasoning = rt._read_gguf_arch(str(p))
        assert (nl, hd, is_reasoning) == (48, 5120, False)

    def test_corrupt_file_yields_none(self, tmp_path):
        p = tmp_path / "broken.gguf"
        p.write_bytes(b"not a gguf file")
        assert rt._read_gguf_arch(str(p)) == (None, None, None)


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
        self._write_registry(reg_path, {
            "Intel/gpt-oss-20b-gguf-q4ks-AutoRound": {"reasoning": "thinking", "offload": 1.0},
            "openai/gpt-oss-20b": {"reasoning": "thinking"},
        })
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
        self._write_registry(reg_path, {
            "Intel/gpt-oss-20b-gguf-q4ks-AutoRound": {"reasoning": "thinking"},
        })
        cfg_dir = tmp_path / "configs" / "Intel" / "gpt-oss-20b-gguf-q4ks-AutoRound"
        cfg_dir.mkdir(parents=True)
        cfg_file = cfg_dir / "gpt-oss-20b-32x2.4B-Q4_K_S.gguf.json"
        cfg_file.write_text(json.dumps({"operation": {"fields": []}}), encoding="utf-8")
        backup = cfg_dir / "gpt-oss-20b-32x2.4B-Q4_K_S.gguf.json.bak-20260731_120000"
        backup.write_text("backup", encoding="utf-8")
        monkeypatch.setattr(rt, "REGISTRY_PATH", reg_path)
        monkeypatch.setattr(rt, "CONFIG_ROOT", tmp_path / "configs")
        assert rt.cmd_rm("Intel/gpt-oss-20b-gguf-q4ks-AutoRound",
                         delete_files=True, assume_yes=True) == 0
        assert not cfg_file.exists()
        assert not backup.exists()
        assert rt.load_registry(reg_path) == {}
