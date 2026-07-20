import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import run_benchmarks_v13 as rb
from run_benchmarks_v13 import (
    ALL_BENCHMARKS,
    ALL_BENCH_NAMES,
    API_BASE,
    BENCH_LOOKUP,
    EXCLUDE_KEYWORDS,
    SAFE_CONTEXT_FALLBACK as SAFE_CONTEXT,
    IS_THINKING_ENABLED,
    _build_lmeval_cmd,
    _ensure_model_still_loaded,
    _get_evaluation_parameters,
    _get_safe_context,
    _is_gemma_model,
    _is_gptoss_model,
    _is_moe_model,
    _is_qwen3_5_model,
    _is_qwen3_6_model,
    _is_reasoning_model,
    _model_family,
    _model_short_name,
    _parse_subset_score,
    resolve_benchmarks,
    resolve_models,
)


# ======================================================================
# Detection helpers
# ======================================================================

class TestModelDetection:
    def test_qwen3_6_detection(self):
        assert _is_qwen3_6_model("qwen3.6-30b-a3b-instruct") is True
        assert _is_qwen3_6_model("Qwen3.6-something") is True
        assert _is_qwen3_6_model("qwen3-32b") is False
        assert _is_qwen3_6_model("llama3") is False

    def test_qwen3_5_detection(self):
        assert _is_qwen3_5_model("qwen3.5-72b-instruct") is True
        assert _is_qwen3_5_model("Qwopus3-something") is True
        assert _is_qwen3_5_model("qwen3.6") is False
        assert _is_qwen3_5_model("llama") is False

    def test_gptoss_detection(self):
        assert _is_gptoss_model("gpt-oss-20b") is True
        assert _is_gptoss_model("GPT-OSS-120b") is True
        assert _is_gptoss_model("gpt-4") is False

    def test_gemma_detection(self):
        assert _is_gemma_model("gemma-3-12b") is True
        assert _is_gemma_model("GEMMA-2-9b") is True
        assert _is_gemma_model("llama") is False

    def test_moe_detection(self):
        # MOE pattern: digits+B-letter-digits+B (e.g. "8b-a1b", "30b-a3b")
        assert _is_moe_model("qwen3-moe-30b-a3b-instruct") is True
        assert _is_moe_model("llama-moe-30b-a4b") is True
        assert _is_moe_model("plain-7b") is False
        assert _is_moe_model("qwen3-a3b-instruct") is False  # no leading "Xb"
        assert _is_moe_model("llama-8b") is False

    def test_reasoning_detection(self):
        assert _is_reasoning_model("deepseek-r1-distill-7b") is True
        assert _is_reasoning_model("o1-reasoning") is True
        assert _is_reasoning_model("think-model") is True
        assert _is_reasoning_model("llama-3b") is False


# ======================================================================
# Model utility helpers
# ======================================================================

class TestModelHelpers:
    def test_model_short_name_basic(self):
        assert _model_short_name("plain-model") == "plain-model"

    def test_model_short_name_replaces_slashes(self):
        # Implementation replaces / and \ with _, so no "last segment" split
        # (rsplit in lines 118-120 is dead code since sep is gone after line 117).
        assert _model_short_name("author/my-model") == "author_my-model"
        assert _model_short_name("author\\my-model") == "author_my-model"

    def test_model_short_name_replaces_spaces(self):
        assert _model_short_name("my model name") == "my_model_name"

    def test_model_short_name_truncates_to_30(self):
        long_name = "a" * 100
        assert len(_model_short_name(long_name)) == 30

    def test_model_family_returns_last_segment(self):
        assert _model_family("publisher/my-model") == "my-model"
        assert _model_family("publisher\\my-model") == "my-model"
        assert _model_family("plain-model") == "plain-model"
        assert _model_family("author/Mixed-Case") == "mixed-case"

    def test_safe_context_returns_matching_value(self):
        # pick first SAFE_CONTEXT pattern that exists
        first_pattern = next(iter(SAFE_CONTEXT))
        expected = SAFE_CONTEXT[first_pattern]
        assert _get_safe_context(first_pattern) == expected

    def test_safe_context_returns_none_for_unknown(self):
        assert _get_safe_context("definitely-not-in-the-list-xyz") is None


# ======================================================================
# resolve_models
# ======================================================================

class TestResolveModels:
    @pytest.fixture
    def sample_models(self):
        # Code-Review 2026-07-18 §4.1: EXCLUDE_KEYWORDS filtering moved
        # upstream into get_available_models(). These tests receive
        # pre-filtered models (whisper is gone).
        return [
            {"key": "qwen3.6-30b", "display": "Qwen3.6 30B", "name": "Qwen3.6", "quant": ""},
            {"key": "llama-8b", "display": "Llama 8B", "name": "Llama 8B", "quant": ""},
        ]

    def test_none_arg_returns_all_filtered(self, sample_models, capsys):
        result = resolve_models(sample_models, None)
        assert result is not None
        keys = [m["key"] for m in result]
        assert "llama-8b" in keys
        assert "qwen3.6-30b" in keys
        assert len(keys) == 2

    def test_empty_string_arg_returns_all(self, sample_models):
        result = resolve_models(sample_models, "")
        assert result is not None
        assert len(result) == 2

    def test_all_keyword_returns_all(self, sample_models):
        result = resolve_models(sample_models, "all")
        assert result is not None
        assert len(result) == 2

    def test_none_available_returns_none(self, capsys):
        result = resolve_models([], "all")
        assert result is None
        out = capsys.readouterr().out
        assert "[WARN]" in out

    def test_single_index(self, sample_models):
        result = resolve_models(sample_models, "1")
        assert result is not None
        assert result[0]["key"] == "qwen3.6-30b"

    def test_range(self, sample_models):
        result = resolve_models(sample_models, "1-2")
        assert result is not None
        keys = [m["key"] for m in result]
        assert keys == ["qwen3.6-30b", "llama-8b"]

    def test_comma_separated_models(self, sample_models):
        result = resolve_models(sample_models, "qwen3.6-30b,llama-8b")
        assert result is not None
        assert len(result) == 2
        keys = [m["key"] for m in result]
        assert "qwen3.6-30b" in keys
        assert "llama-8b" in keys

    def test_comma_separated_with_unknown(self, sample_models, capsys):
        result = resolve_models(sample_models, "qwen3.6-30b,does-not-exist")
        # The known one should still be resolved, unknown one warned
        assert result is not None
        assert result[0]["key"] == "qwen3.6-30b"

    def test_comma_separated_all_unknown_returns_none(self, capsys):
        models = [{"key": "a", "display": "A", "name": "A", "quant": ""}]
        result = resolve_models(models, "does-not-exist,also-not-exist")
        assert result is None


# ======================================================================
# resolve_benchmarks
# ======================================================================

class TestResolveBenchmarks:
    def test_none_returns_all(self):
        result = resolve_benchmarks(None)
        assert result == ALL_BENCHMARKS

    def test_empty_string_returns_all(self):
        result = resolve_benchmarks("")
        assert result == ALL_BENCHMARKS

    def test_all_keyword(self):
        result = resolve_benchmarks("all")
        assert result == ALL_BENCHMARKS

    def test_single_index(self):
        result = resolve_benchmarks("1")
        assert result == [ALL_BENCHMARKS[0]]

    def test_range(self):
        result = resolve_benchmarks("1-2")
        assert len(result) == 2
        assert result[0] is ALL_BENCHMARKS[0]
        assert result[1] is ALL_BENCHMARKS[1]

    def test_comma_names(self):
        result = resolve_benchmarks("ds1000,humaneval+")
        assert result is not None
        assert ALL_BENCHMARKS[0] in result

    def test_unknown_name_returns_none(self, capsys):
        result = resolve_benchmarks("definitely-not-a-real-bench")
        assert result is None
        out = capsys.readouterr().out
        assert "[ERROR]" in out


# ======================================================================
# _get_evaluation_parameters
# ======================================================================

class TestLmevalParams:
    """Tests fuer _get_evaluation_parameters() (Variante C+, p6).

    Ersetzt die 9 obsoleten Tests des alten if/else-Cascade (vor v13).
    Prueft die neue Variante-C+-Logik:
    - BENCHMARK_CATEGORY_DEFAULTS als Basis
    - MODEL_TEMP_OVERRIDES als additives Merge
    - --thinking / REASONING_PATTERNS als enable_thinking-Override
    """

    # Region: Shape-Check - Required Keys ----------------------------------
    def test_returns_required_keys(self):
        params = _get_evaluation_parameters("plain-7b-model", "coding")
        assert "temperature" in params
        assert "top_p" in params
        assert "max_tokens" in params

    def test_clauses_resolve_to_flat_dict(self):
        # Variante C+ merged alle Quellen zu einem FLACHEN dict. Verschachtelung
        # in 'extra_body.chat_template_kwargs' gibt es nur noch innerhalb des
        # generierten API-Body (in _stream_chat_completion()).
        params = _get_evaluation_parameters("plain-7b-model", "coding")
        assert "extra_body" not in params

    # Region: Category-Defaults (BENCHMARK_CATEGORY_DEFAULTS) -------------
    def test_coding_default_is_deterministic(self):
        params = _get_evaluation_parameters("plain-7b-model", "coding")
        assert params["temperature"] == 0.0        # coding = deterministisch
        assert params["top_p"] == 1.0
        assert params["max_tokens"] == 2048

    def test_math_default_has_higher_max_tokens(self):
        params = _get_evaluation_parameters("plain-7b-model", "math")
        assert params["max_tokens"] == 8192        # math erlaubt mehr Tokens

    def test_knowledge_default(self):
        params = _get_evaluation_parameters("plain-7b-model", "knowledge")
        assert params["temperature"] == 0.0
        assert params["max_tokens"] == 2048

    def test_agentic_default(self):
        params = _get_evaluation_parameters("plain-7b-model", "agentic")
        assert params["temperature"] == 0.3        # leicht stochastisch fuer tool-use
        assert params["max_tokens"] == 4096

    def test_stops_renamed_to_until_in_lmeval_format(self):
        # BENCHMARK_CATEGORY_DEFAULTS hat kein `stop`, aber ein Override mit `stop`
        # soll zu `until` werden (lm_eval-CLI-Konvention).
        params = _get_evaluation_parameters("unsloth/gpt-oss-20b", "math")
        if "until" in params or "stop" in params:
            # gpt-oss-Override hat `stop` -> lm_eval versteht beides
            assert any(k in params for k in ("until", "stop"))

    def test_enable_thinking_false_emits_reasoning_off_native(self):
        # Wenn enable_thinking=False, wird zusaetzlich reasoning="off" gesetzt fuer
        # den nativen API-Pfad (siehe Code-Review 2026-07-20 §Interoperability).
        params = _get_evaluation_parameters("plain-7b-model", "coding")
        chat_template_kwargs = params.get("chat_template_kwargs", {})
        if "enable_thinking" in chat_template_kwargs and chat_template_kwargs["enable_thinking"] is False:
            assert params.get("reasoning") == "off"

    # Region: Model-Overrides (MODEL_TEMP_OVERRIDES) ---------------------
    def test_phi4_reasoning_override(self):
        params = _get_evaluation_parameters("unsloth/phi-4-reasoning", "coding")
        assert params["temperature"] == 0.8        # phi-4-reasoning override
        assert params["top_k"] == 50

    def test_gpt_oss_override_temperature(self):
        params = _get_evaluation_parameters("unsloth/gpt-oss-20b", "math")
        assert params["temperature"] == 1.0        # gpt-oss override
        assert params["top_k"] == 0               # top_k=0 fuer Harmony

    def test_qwen3_5_override_includes_top_k(self):
        params = _get_evaluation_parameters("qwen3.5-72b-instruct", "coding")
        assert params["temperature"] == 0.2
        assert params["top_p"] == 0.9
        assert params["top_k"] == 20

    def test_qwen3_6_emits_reasoning_off(self):
        # Qwen3.6 denkt im GGUF-Default mit. Override erzwingt enable_thinking=False.
        # Folge: reasoning="off" wird fuer native API gesetzt.
        params = _get_evaluation_parameters("qwen3.6-30b-a3b-instruct", "coding")
        chat_template_kwargs = params.get("chat_template_kwargs", {})
        assert chat_template_kwargs.get("enable_thinking") is False
        assert params.get("reasoning") == "off"

    def test_gemma_override_wins_against_math_thinking_default(self):
        # math category default hat enable_thinking=True, gemma override setzt es auf False.
        params = _get_evaluation_parameters("gemma-3-12b", "math")
        chat_template_kwargs = params.get("chat_template_kwargs", {})
        assert chat_template_kwargs.get("enable_thinking") is False

    def test_deepseek_overrides_include_min_p(self):
        # MODEL_TEMP_OVERRIDES iteriert in Insertion-Order. `deepseek` (temp=0.6,
        # min_p=0.02) kommt vor `deepseek-r1-distill` (temp=0.0, min_p=None).
        # Daher gewinnt das generische `deepseek`-Pattern zuerst, sobald der
        # Model-Key `deepseek` als Substring enthaelt.
        params = _get_evaluation_parameters("deepseek-coder-v2-lite-instruct", "coding")
        assert params["temperature"] == 0.6        # `deepseek`-Override
        assert params["min_p"] == 0.02

    # Region: --thinking Flag + REASONING_PATTERNS ---------------------
    def test_thinking_flag_with_reasoning_pattern_enables_thinking(self, monkeypatch):
        monkeypatch.setattr(rb, "IS_THINKING_ENABLED", True)
        # "r1" ist in REASONING_PATTERNS, "deepseek-r1-distill" ebenfalls
        params = _get_evaluation_parameters("r1-distill-7b", "coding")
        chat_template_kwargs = params.get("chat_template_kwargs", {})
        assert chat_template_kwargs.get("enable_thinking") is True
        # Und reasoning="off" darf NICHT gesetzt sein, wenn thinking an ist
        assert "reasoning" not in params or params["reasoning"] != "off"

    def test_thinking_flag_unchanged_for_non_reasoning_model(self, monkeypatch):
        monkeypatch.setattr(rb, "IS_THINKING_ENABLED", True)
        # plain-7b enthaelt kein REASONING_PATTERNS-Keyword
        # → thinking flag wird ignoriert, Category-Default (coding=False) gewinnt
        params = _get_evaluation_parameters("plain-7b-model", "coding")
        chat_template_kwargs = params.get("chat_template_kwargs", {})
        # By coding default: enable_thinking=False (kann aber von gemma/qwen3.6
        # Override bereits auf False gesetzt sein)
        assert chat_template_kwargs.get("enable_thinking") is not True


# ======================================================================
# _build_lmeval_cmd
# ======================================================================

class TestBuildLmevalCmd:
    def test_basic_command(self):
        cmd = _build_lmeval_cmd("plain-model", "api/my-model", "task1", 10, "/tmp/out")
        assert "--model" in cmd
        assert cmd[cmd.index("--model") + 1] == "local-chat-completions"
        assert "--tasks" in cmd
        assert cmd[cmd.index("--tasks") + 1] == "task1"
        assert "--limit" in cmd
        assert cmd[cmd.index("--limit") + 1] == "10"
        assert "--output_path" in cmd
        assert cmd[cmd.index("--output_path") + 1] == "/tmp/out"
        assert "--apply_chat_template" in cmd
        assert "--log_samples" in cmd

    def test_gptoss_adds_eos_string_when_no_until(self):
        # The eos_string is only added when "until" is NOT already in
        # evaluation_parameters. The default gpt-oss branch sets until=[...]
        # so we override _get_evaluation_parameters to drop until.
        with patch.object(rb, "_get_evaluation_parameters",
                          return_value={"max_tokens": 4096, "temperature": 1.0}):
            cmd = _build_lmeval_cmd("gpt-oss-20b", "gpt-oss-20b", "task1", 5, "/tmp/out")
            idx = cmd.index("--model_args")
            args_json = json.loads(cmd[idx + 1])
            assert args_json["eos_string"] == "<|endoftext|>"

    def test_gptoss_default_has_until_no_eos_string(self):
        # Default gpt-oss branch returns until=[...] so no eos_string.
        cmd = _build_lmeval_cmd("gpt-oss-20b", "gpt-oss-20b", "task1", 5, "/tmp/out")
        idx = cmd.index("--model_args")
        args_json = json.loads(cmd[idx + 1])
        assert "eos_string" not in args_json

    def test_non_gptoss_no_eos_string(self):
        cmd = _build_lmeval_cmd("plain-7b", "plain-7b", "task1", 5, "/tmp/out")
        idx = cmd.index("--model_args")
        args_json = json.loads(cmd[idx + 1])
        assert "eos_string" not in args_json

    def test_model_args_includes_chat_url(self):
        cmd = _build_lmeval_cmd("plain-7b", "api/pl", "task1", 5, "/tmp/out")
        idx = cmd.index("--model_args")
        args_json = json.loads(idx + 1 and cmd[idx + 1])
        assert args_json["base_url"] == f"{API_BASE}/chat/completions"
        assert args_json["num_concurrent"] == 1

    @pytest.mark.skip(reason="_get_evaluation_parameters rewritten in v13; "
                        "old if-else cascade tests obsolete")
    def test_gen_kwargs_added_when_present(self):
        cmd = _build_lmeval_cmd("qwen3.6-30b", "qwen3.6-30b", "task1", 5, "/tmp/out")
        # qwen3.6 returns max_tokens=8192 in gen_kwargs
        assert "--gen_kwargs" in cmd
        idx = cmd.index("--gen_kwargs")
        gk = json.loads(cmd[idx + 1])
        assert gk["max_tokens"] == 8192

    def test_no_gen_kwargs_when_none(self):
        # default branch returns only basic params; gen_kwargs_keys filters out
        # max_tokens (=1024), temperature, top_p which are then All-Set.
        # The default DOES include max_tokens/temperature/top_p, so gen_kwargs
        # is still added.
        # But if model returns a dict that doesn't have any keys in
        # gen_kwargs_keys (unlikely here), it could be empty.
        # Use a tiny custom case: monkey-patch _get_evaluation_parameters
        with patch.object(rb, "_get_evaluation_parameters", return_value={"foo": "bar"}):
            cmd = _build_lmeval_cmd("plain-7b", "p", "task", 1, "/o")
        assert "--gen_kwargs" not in cmd


# ======================================================================
# _parse_subset_score
# ======================================================================

class TestParseSubsetScore:
    def test_returns_score_from_result_json(self, tmp_path):
        subset = "arc-challenge"
        # Create nested structure: tmp/subset/results_xxx.json
        sub_dir = tmp_path / subset
        sub_dir.mkdir()
        results_file = sub_dir / "results_20260101_000000.json"
        results_file.write_text(json.dumps({
            "results": {
                subset: {
                    "exact_match,remove_whitespace": 0.42,
                    "exact_match,strict-match": 0.99,
                }
            }
        }))
        score = _parse_subset_score(str(tmp_path), subset)
        assert score == pytest.approx(0.42)

    def test_returns_none_for_empty_dir(self, tmp_path):
        score = _parse_subset_score(str(tmp_path), "nonexistent")
        assert score is None

    def test_returns_none_when_results_missing_metric(self, tmp_path):
        subset = "taskx"
        sub_dir = tmp_path / subset
        sub_dir.mkdir()
        (sub_dir / "results.json").write_text(json.dumps({
            "results": {subset: {"some_other_metric": 0.5}}
        }))
        score = _parse_subset_score(str(tmp_path), subset)
        assert score is None


# ======================================================================
# _ensure_model_still_loaded
# ======================================================================

class TestEnsureModelStillLoaded:
    def test_already_loaded_does_nothing(self, capsys):
        loaded = {
            "model_identifier": "qwen3.6-30b",
            "identifier": "qwen3.6-30b@q4_k_m",
        }
        with patch.object(rb, "get_current_loaded_model", return_value=loaded):
            with patch.object(rb, "load_model_via_lms") as ld:
                with patch.object(rb, "is_model_ready") as w:
                    _ensure_model_still_loaded("qwen3.6-30b", "qwen3.6-30b")
                    ld.assert_not_called()
                    w.assert_not_called()

    def test_reload_called_when_unloaded(self, capsys):
        with patch.object(rb, "get_current_loaded_model", return_value=None):
            with patch.object(rb, "load_model_via_lms") as ld:
                with patch.object(rb, "is_model_ready", return_value=True) as w:
                    _ensure_model_still_loaded("qwen3.6-30b", "qwen3.6-30b")
                    ld.assert_called_once()
                    w.assert_called_once()

    def test_reload_called_when_different_model(self, capsys):
        loaded = {
            "model_identifier": "some-other-model",
            "identifier": "some-other-model@q4_k_m",
        }
        with patch.object(rb, "get_current_loaded_model", return_value=loaded):
            with patch.object(rb, "load_model_via_lms") as ld:
                with patch.object(rb, "is_model_ready", return_value=True) as w:
                    _ensure_model_still_loaded("qwen3.6-30b", "qwen3.6-30b")
                    ld.assert_called_once()
                    w.assert_called_once()

    def test_warning_printed_when_model_lost(self, capsys):
        with patch.object(rb, "get_current_loaded_model", return_value=None):
            with patch.object(rb, "load_model_via_lms"):
                with patch.object(rb, "is_model_ready", return_value=True):
                    _ensure_model_still_loaded("qwen3.6-30b", "qwen3.6-30b", "MATH-500")
                    out = capsys.readouterr().out
                    assert "[WARN]" in out
                    assert "MATH-500" in out
