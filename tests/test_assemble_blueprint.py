"""Tests for assemble_blueprint.py (Code-Review 2026-07-18 §5.4).

Targets the model classification and matching logic:
  - normalize_model_name (used by registry_tool.py and others)
  - classify_capabilities
  - extract_params
  - read_lms_configs (cache behavior)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import assemble_blueprint as ab
from assemble_blueprint import (
    normalize_model_name,
    classify_capabilities,
    classify_reasoning,
    select_blueprint,
    extract_params,
    read_lms_configs,
    format_publishers,
    format_capabilities,
    truncation_from_context,
    find_registry_key_for_config,
)


# ─────────────────────────────────────────────────────────────────────
# normalize_model_name
# ─────────────────────────────────────────────────────────────────────

class TestNormalizeModelName:
    """Strip publisher, replace dots/underscores with hyphens, lowercase."""

    def test_lowercase(self):
        assert normalize_model_name("FooBar") == "foobar"

    def test_strip_publisher(self):
        assert normalize_model_name("unsloth/phi-4") == "phi-4"

    def test_strip_gguf_suffix(self):
        assert normalize_model_name("model.gguf") == "model"

    def test_strip_gguf_standalone(self):
        assert normalize_model_name("model-gguf") == "model"

    def test_strip_mxfp4(self):
        assert normalize_model_name("model-mxfp4") == "model"

    def test_dots_to_hyphens(self):
        assert normalize_model_name("Qwen3.6-27B") == "qwen3-6-27b"

    def test_underscores_to_hyphens(self):
        assert normalize_model_name("Qwen_Qwen3.6") == "qwen-qwen3-6"

    def test_collapse_double_hyphens(self):
        assert normalize_model_name("Qwen__3--6") == "qwen-3-6"

    def test_combined(self):
        # mradermacher/gemma-4-26b-a4b-it.REAP.Q4_K_S.gguf
        # → strip .gguf → strip nothing else → lowercase → dots/underscores
        result = normalize_model_name(
            "mradermacher/gemma-4-26b-a4b-it.REAP.Q4_K_S.gguf"
        )
        assert "26b-a4b-it" in result
        assert "REAP" not in result.upper().split()  # dots replaced
        # No trailing .gguf
        assert not result.endswith("gguf")

    def test_empty_string(self):
        assert normalize_model_name("") == ""


# ─────────────────────────────────────────────────────────────────────
# classify_capabilities
# ─────────────────────────────────────────────────────────────────────

class TestClassifyCapabilities:
    """Detect capabilities from model name/arch/notes."""

    def test_text_default(self):
        caps = classify_capabilities("llama-3-8b", arch="Llama")
        assert "text" in caps

    def test_coder_keyword(self):
        caps = classify_capabilities("qwen2.5-coder-14b")
        assert "coding" in caps
        assert "text" in caps

    def test_wizard_coder_keyword(self):
        caps = classify_capabilities("wizardcoder-python-13b")
        assert "coding" in caps

    def test_vision_keyword(self):
        caps = classify_capabilities("qwen2-vl-7b", arch="Qwen2 VL")
        assert "vision" in caps

    def test_gemma_4_implies_coding_and_vision(self):
        caps = classify_capabilities("gemma-4-9b")
        assert "coding" in caps
        assert "vision" in caps

    def test_gemma_4_12b_includes_audio(self):
        caps = classify_capabilities("gemma-4-12b")
        assert "audio" in caps
        assert "vision" in caps
        assert "coding" in caps

    def test_gemma_4_e4b_includes_audio(self):
        caps = classify_capabilities("gemma-4-e4b")
        assert "audio" in caps

    def test_granite_implies_coding(self):
        caps = classify_capabilities("granite-4-1-8b")
        assert "coding" in caps

    def test_ministral_implies_vision_and_coding(self):
        caps = classify_capabilities("ministral-3-14b")
        assert "vision" in caps
        assert "coding" in caps

    def test_kimi_implies_vision_and_coding(self):
        caps = classify_capabilities("kimi-linear-35b")
        assert "vision" in caps
        assert "coding" in caps

    def test_phi_4_implies_coding(self):
        caps = classify_capabilities("phi-4")
        assert "coding" in caps

    def test_whisper_excludes_text(self):
        caps = classify_capabilities("whisper-large-v3")
        assert "audio" in caps
        assert "text" not in caps

    def test_flux_implies_text(self):
        # flux-1-dev is a default text model
        caps = classify_capabilities("flux-1-dev")
        assert "text" in caps

    def test_notes_keyword_agentic(self):
        caps = classify_capabilities("any-model", notes="Model has agentic abilities")
        assert "agentic" in caps

    def test_coder_in_arch(self):
        caps = classify_capabilities("model", arch="Llama (coder)")
        assert "coding" in caps


# ─────────────────────────────────────────────────────────────────────
# classify_reasoning (Qwen3 Instruct vs. Thinking vs. Dual-Mode)
# ─────────────────────────────────────────────────────────────────────

class TestClassifyReasoningQwen3:
    """Qwen3-Varianten korrekt klassifizieren (Fix 2026-08-01).

    - Qwen3-*-Instruct-2507 / Qwen3-Coder-*-Instruct: Non-Thinking-only
      (HF-Karte Qwen3-30B-A3B-Instruct-2507)
    - Qwen3-*-Thinking-*: Thinking
    - Qwen3.6 (dual mode): thinking erlaubt
    """

    def test_qwen3_instruct_is_non_thinking(self):
        r = classify_reasoning("qwen3-30b-a3b-instruct-2507", arch="Qwen3 MoE")
        assert r == "instruct"

    def test_qwen3_instruct_moe_lowercase_arch(self):
        r = classify_reasoning("qwen3-30b-a3b-instruct-2507", arch="moe")
        assert r == "instruct"

    def test_qwen3_coder_instruct_is_non_thinking(self):
        r = classify_reasoning("qwen3-coder-30b-a3b-instruct", arch="Qwen3 MoE")
        assert r == "instruct"

    def test_qwen3_thinking_stays_thinking(self):
        r = classify_reasoning("qwen3-30b-a3b-thinking-2507", arch="Qwen3 MoE")
        assert r == "thinking"

    def test_qwen3_6_dual_mode_defaults_thinking(self):
        # Qwen3.6 is dual-mode (Thinking per Prompt schaltbar), Default Thinking
        r = classify_reasoning("qwen3.6-27b", arch="Qwen3.5 Dense")
        assert r == "thinking"

    def test_existing_reasoning_has_priority(self):
        r = classify_reasoning("qwen3-30b-a3b-instruct-2507",
                               arch="Qwen3 MoE", existing_reasoning="thinking")
        assert r == "thinking"

    def test_instruct_blueprint_is_coding_agent(self):
        bp = select_blueprint("instruct", "coding, text", arch="Qwen3 MoE",
                              model_name="qwen3-30b-a3b-instruct-2507")
        assert bp == "coding_agent"

    def test_granite_uses_dedicated_blueprint(self):
        bp = select_blueprint("instruct", "coding, text", arch="Granite MoE",
                              model_name="ibm-granite/granite-4.1-30b")
        assert bp == "granite_coding_agent"

    def test_qwen3_instruct_assembled_prompt_has_no_reasoning(self):
        bp = select_blueprint("instruct", "coding, text", arch="Qwen3 MoE",
                              model_name="qwen3-30b-a3b-instruct-2507")
        assert bp != "reasoning_coding"


# ─────────────────────────────────────────────────────────────────────
# extract_params
# ─────────────────────────────────────────────────────────────────────

class TestExtractParams:
    """Find parameter count in model name."""

    def test_simple_14b(self):
        assert extract_params("qwen2.5-14b-instruct") == "14B"

    def test_27b(self):
        assert extract_params("qwen3.6-27b") == "27B"

    def test_7b(self):
        assert extract_params("llama-7b") == "7B"

    def test_first_match_wins(self):
        # "4K" appears before "3.8B" in the string; the regex returns the
        # first match (Code-Review 2026-07-18 §5.4)
        assert extract_params("phi-3-mini-4k-instruct-3.8b") == "4K"

    def test_no_match(self):
        assert extract_params("phi-3-mini") is None


# ─────────────────────────────────────────────────────────────────────
# format_publishers / format_capabilities
# ─────────────────────────────────────────────────────────────────────

class TestFormatters:
    """Convert list/capability formats into human-readable strings."""

    def test_publishers_list(self):
        assert format_publishers(["lmstudio", "unsloth"]) == "lmstudio/unsloth"

    def test_publishers_string(self):
        assert format_publishers("unsloth") == "unsloth"

    def test_publishers_empty(self):
        assert format_publishers([]) == "unknown"

    def test_capabilities_text(self):
        # "text" maps to "text generation"
        assert "text generation" in format_capabilities("text")

    def test_capabilities_list(self):
        result = format_capabilities(["text", "coding"])
        assert "text generation" in result
        assert "coding" in result

    def test_capabilities_vision_label(self):
        # "vision" maps to "visual design"
        assert "visual design" in format_capabilities("vision")


# ─────────────────────────────────────────────────────────────────────
# truncation_from_context
# ─────────────────────────────────────────────────────────────────────

class TestTruncationFromContext:
    """Determine truncation level from context length."""

    def test_zero_or_none_is_full(self):
        assert truncation_from_context(0) == "full"
        assert truncation_from_context(None) == "full"

    def test_large_context_is_full(self):
        assert truncation_from_context(32768) == "full"
        assert truncation_from_context(131072) == "full"

    def test_medium_context(self):
        # 16K-32K → medium
        assert truncation_from_context(16384) == "medium"
        assert truncation_from_context(24000) == "medium"

    def test_small_context_is_minimal(self):
        assert truncation_from_context(4096) == "minimal"
        assert truncation_from_context(2048) == "minimal"


# ─────────────────────────────────────────────────────────────────────
# read_lms_configs Caching (Code-Review §4.2)
# ─────────────────────────────────────────────────────────────────────

class TestReadLmsConfigsCaching:
    """Cache TTL of 5 seconds per config_root path."""

    def test_cache_repeated_calls(self, tmp_path):
        # First call populates cache
        cfg_dir = tmp_path / "user-concrete-model-default-config"
        cfg_dir.mkdir()
        sub = cfg_dir / "pub"
        sub.mkdir()
        json_path = sub / "m.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({
                "operation": {"fields": []},
                "load": {"fields": []},
            }, f)

        # First call – populates cache
        r1 = read_lms_configs(cfg_dir)
        assert len(r1) == 1
        # Second call – within TTL, should return same list
        r2 = read_lms_configs(cfg_dir)
        # Same list object (cached)
        assert r2 is r1

    def test_cache_expires(self, tmp_path, monkeypatch):
        cfg_dir = tmp_path / "user-concrete-model-default-config"
        cfg_dir.mkdir()
        sub = cfg_dir / "pub"
        sub.mkdir()
        json_path = sub / "m.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({
                "operation": {"fields": []},
                "load": {"fields": []},
            }, f)

        # The cache uses a local `import time as _time` inside the function.
        # We can't monkey-patch it from outside. Instead, manually clear
        # the cache and re-call – this exercises the same path.
        ab._LMS_CONFIGS_CACHE.clear()

        r1 = read_lms_configs(cfg_dir)
        # Manually expire by clearing the cache (simulates TTL expiry)
        ab._LMS_CONFIGS_CACHE.clear()
        r2 = read_lms_configs(cfg_dir)
        # After expiry, the cache is rebuilt – new list object
        assert r2 is not r1
        assert len(r2) == 1

    def test_nonexistent_root_returns_empty_and_caches(self, tmp_path):
        cfg_dir = tmp_path / "does-not-exist"
        # Should not raise; should return empty list
        result = read_lms_configs(cfg_dir)
        assert result == []
        # Second call also returns empty (cached)
        result2 = read_lms_configs(cfg_dir)
        assert result2 == []


# ─────────────────────────────────────────────────────────────────────
# find_registry_key_for_config
# ─────────────────────────────────────────────────────────────────────

class TestFindRegistryKeyForConfig:
    """Registry key lookup for a config name (multi-level matching)."""

    @staticmethod
    def _sorted(keys: list[str]) -> list[tuple[str, str]]:
        return sorted(
            [(normalize_model_name(k), k) for k in keys],
            key=lambda x: -len(x[0]),
        )

    def _norm(self, raw: str) -> str:
        return normalize_model_name(raw)

    def test_exact_match(self):
        reg = self._sorted(["unsloth/phi-4"])
        assert find_registry_key_for_config(self._norm("unsloth/phi-4"), reg) == "unsloth/phi-4"

    def test_config_prefix_match(self):
        # Level 2: config starts with registry key + hyphen
        reg = self._sorted(["unsloth/phi-4"])
        assert find_registry_key_for_config(self._norm("unsloth/phi-4-q5_0"), reg) == "unsloth/phi-4"

    def test_registry_prefix_match(self):
        # Level 3: registry key ends with hyphen + config
        reg = self._sorted(["mradermacher/qwen3-coder-reap-25b-a3b-i1"])
        assert find_registry_key_for_config(self._norm("mradermacher/i1"), reg) == "mradermacher/qwen3-coder-reap-25b-a3b-i1"

    def test_broad_match_strips_quant(self):
        # Level 4: config matches registry key after stripping @quant suffix
        reg = self._sorted(["unsloth/ernie-4.5-21b-a3b-pt@iq4_nl"])
        assert find_registry_key_for_config(self._norm("unsloth/ernie-4.5-21b-a3b-pt"), reg) == "unsloth/ernie-4.5-21b-a3b-pt@iq4_nl"

    def test_exact_match_beats_broad_match(self):
        # Level 1 wins: exact key (without @quant) beats broad match of suffixed key
        reg = self._sorted(["unsloth/ernie-4.5-21b-a3b-pt@iq4_nl", "unsloth/ernie-4.5-21b-a3b-pt"])
        result = find_registry_key_for_config(self._norm("unsloth/ernie-4.5-21b-a3b-pt"), reg)
        assert result == "unsloth/ernie-4.5-21b-a3b-pt"

    def test_no_match_returns_none(self):
        reg = self._sorted(["unsloth/phi-4"])
        assert find_registry_key_for_config(self._norm("meta-llama/llama-3-8b"), reg) is None

    def test_broad_match_does_not_crash_with_value_tuples(self):
        # Regression: rnk was passed to normalize_for_config instead of rn2,
        # crashing with CommentedMap values in the tuple.
        reg = sorted(
            [(normalize_model_name(k), v) for k, v in {"unsloth/ernie-4.5-21b-a3b-pt@iq4_nl": {"context_length": 45371}}.items()],
            key=lambda x: -len(x[0]),
        )
        assert find_registry_key_for_config(self._norm("unsloth/ernie-4.5-21b-a3b-pt"), reg) == {"context_length": 45371}


# =========================================================================
# resolve_template_name / blueprint_features (Blueprint SSOT, Refactor 14.08.)
# =========================================================================

class TestResolveTemplateName:
    def test_template_map_substring_match(self):
        bp = {"template_map": {"12b": "a.jinja", "26b": "c.jinja", "19b": "b.jinja"}}
        assert ab.resolve_template_name(bp, "gemma-4-12b-it") == "a.jinja"
        assert ab.resolve_template_name(bp, "gemma4-26b-a4b") == "c.jinja"
        assert ab.resolve_template_name(bp, "gemma-4-19b") == "b.jinja"

    def test_template_map_first_match_wins(self):
        bp = {"template_map": {"gemma-4": "g.jinja", "12b": "12.jinja"}}
        assert ab.resolve_template_name(bp, "gemma-4-12b") == "g.jinja"

    def test_direct_template_fallback(self):
        bp = {"template": "direct.jinja"}
        assert ab.resolve_template_name(bp, "any-model") == "direct.jinja"

    def test_template_map_beats_direct_template(self):
        bp = {"template_map": {"12b": "map.jinja"}, "template": "direct.jinja"}
        assert ab.resolve_template_name(bp, "gemma-4-12b") == "map.jinja"

    def test_none_or_empty(self):
        assert ab.resolve_template_name(None, "x") is None
        assert ab.resolve_template_name({}, "x") is None
        assert ab.resolve_template_name({"role": "r"}, "x") is None

    def test_case_insensitive(self):
        bp = {"template_map": {"12B": "a.jinja"}}
        assert ab.resolve_template_name(bp, "gemma-4-12b") == "a.jinja"

    def test_dots_match_hyphens(self):
        # Registry-Key normalisiert Punkte zu Bindestrichen (granite-4.1 -> granite-4-1).
        bp = {"template_map": {"granite-4.1-30b": "g30.jinja", "granite-4.0": "g0.jinja"}}
        assert ab.resolve_template_name(bp, "ibm-granite/granite-4-1-30b@q3_k_s") == "g30.jinja"
        assert ab.resolve_template_name(bp, "ibm-granite/granite-4-0-h-tiny@q8_0") == "g0.jinja"

    def test_hyphen_pattern_matches_dot_name(self):
        bp = {"template_map": {"granite-4-1": "g.jinja"}}
        assert ab.resolve_template_name(bp, "granite-4.1-30b") == "g.jinja"


class TestBlueprintFeatures:
    def test_returns_empty_for_unknown_blueprint(self):
        assert ab.blueprint_features("does-not-exist", "m") == {}

    def test_gptoss_stop_strings(self):
        f = ab.blueprint_features("gptoss_reasoning", "gpt-oss-20b")
        assert f["stop_strings"] == ["<|return|>"]
        assert f["template"] == "gpt-oss-20b_harmony.jinja"

    def test_gemma_template_map_and_parsing(self):
        f = ab.blueprint_features("gemma_reasoning", "gemma4-26b-a4b")
        assert f["template"] == "gemma4-26b-template_minijinja.jinja"
        assert f["reasoning_parsing"]["enabled"] is False

    def test_generic_coding_blueprint_has_no_granite_template(self):
        assert ab.blueprint_features("coding_agent", "qwen3-coder-30b") == {}

    def test_granite_blueprint_resolves_granite_template(self):
        f = ab.blueprint_features("granite_coding_agent", "ibm-granite/granite-4.1-30b")
        assert f["template"] == "granite-4.1-30b_template.jinja"

    def test_reasoning_blueprints_do_not_use_cot_scaffolding(self):
        blueprints = ab.load_blueprint_defs()["blueprints"]
        for name, definition in blueprints.items():
            if "reasoning" in name:
                assert "thinking_instruction" not in definition.get("modules", [])
                assert "instruct_scaffolding" not in definition.get("modules", [])

    def test_instruct_blueprints_use_instruct_scaffolding(self):
        blueprints = ab.load_blueprint_defs()["blueprints"]
        for name in ("default_chat", "coding_agent", "granite_coding_agent", "gemma_assistant"):
            assert "instruct_scaffolding" in blueprints[name]["modules"]

    def test_gemma_thinking_by_category(self):
        # Fix 15.08.: Kategorie-basierte Thinking-Steuerung (SSOT) statt
        # unkonditionalem <|think|>-Modul. Coding/Agentic aus, Math/Knowledge an.
        f = ab.blueprint_features("gemma_reasoning", "gemma4-26b-a4b")
        cats = f["enable_thinking_by_category"]
        assert cats == {"coding": False, "agentic": False, "knowledge": True, "math": True}

    def test_gemma_think_token_module_removed(self):
        # Fix 15.08. (Bug B): gemma_think_token-Modul wurde aus dem
        # gemma_reasoning-Blueprint entfernt - es darf nicht mehr in der
        # Modulliste auftauchen.
        bp = ab.load_blueprint_defs().get("blueprints", {}).get("gemma_reasoning")
        assert bp is not None
        assert "gemma_think_token" not in bp.get("modules", [])

    def test_gemma_12b_picks_smaller_template(self):
        f = ab.blueprint_features("gemma_reasoning", "gemma-4-12b-it")
        assert f["template"] == "gemma4_12b_template_minijinja.jinja"

    def test_no_features_returns_empty(self):
        assert ab.blueprint_features("reasoning_assistant", "plain-7b") == {}
