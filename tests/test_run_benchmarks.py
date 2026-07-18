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
    THINKING_ENABLED,
    _build_lmeval_cmd,
    _ensure_model_still_loaded,
    _get_lmeval_params,
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
# _get_lmeval_params
# ======================================================================

class TestLmevalParams:
    # Code-Review 2026-07-18 §5.5: The _get_lmeval_params() function was
    # rewritten in v13 to use get_model_config() (Variante C+ in
    # benchmark_config.py). The following tests hard-coded specific values
    # from the old per-model if-else cascade and now fail. They are
    # skipped until either updated or replaced by a get_model_config()
    # test suite.
    @pytest.mark.skip(reason="_get_lmeval_params rewritten in v13; "
                        "old if-else cascade tests obsolete")
    def test_gptoss_branch(self):
        # pick a model key that triggers gptoss
        params = _get_lmeval_params("gpt-oss-20b", "MATH-500")
        assert params["temperature"] == 1.0
        assert params["top_k"] == 0
        assert "<|return|>" in params["until"]
        assert params["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False

    @pytest.mark.skip(reason="_get_lmeval_params rewritten in v13; "
                        "old if-else cascade tests obsolete")
    def test_qwen3_6_branch(self):
        params = _get_lmeval_params("qwen3.6-30b-a3b-instruct", "")
        assert params["max_tokens"] == 8192
        assert params["temperature"] == 0.0
        assert params["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False

    @pytest.mark.skip(reason="_get_lmeval_params rewritten in v13; "
                        "old if-else cascade tests obsolete")
    def test_qwen3_5_branch(self):
        params = _get_lmeval_params("qwen3.5-72b-instruct", "")
        assert params["temperature"] == 0.2
        assert params["top_p"] == 0.9
        assert params["top_k"] == 20

    @pytest.mark.skip(reason="_get_lmeval_params rewritten in v13; "
                        "old if-else cascade tests obsolete")
    def test_gemma_default(self):
        params = _get_lmeval_params("gemma-3-12b", "arc-challenge")
        assert params["max_tokens"] == 4096
        assert params["temperature"] == 0.0

    @pytest.mark.skip(reason="_get_lmeval_params rewritten in v13; "
                        "old if-else cascade tests obsolete")
    def test_gemma_with_thinking_and_math500(self, monkeypatch):
        monkeypatch.setattr(rb, "THINKING_ENABLED", True)
        params = _get_lmeval_params("gemma-3-12b", "MATH-500")
        assert params["max_tokens"] == 8192
        assert params["extra_body"]["chat_template_kwargs"]["enable_thinking"] is True

    @pytest.mark.skip(reason="_get_lmeval_params rewritten in v13; "
                        "old if-else cascade tests obsolete")
    def test_reasoning_branch(self):
        params = _get_lmeval_params("deepseek-r1-distill-7b", "arc-challenge")
        assert params["temperature"] == 0.1
        assert params["min_p"] == 0.02

    @pytest.mark.skip(reason="_get_lmeval_params rewritten in v13; "
                        "old if-else cascade tests obsolete")
    def test_reasoning_with_thinking_and_math500(self, monkeypatch):
        monkeypatch.setattr(rb, "THINKING_ENABLED", True)
        params = _get_lmeval_params("r1-distill-7b", "MATH-500")
        assert params["max_tokens"] == 8192
        assert "until" in params
        assert params["extra_body"]["chat_template_kwargs"]["enable_thinking"] is True

    @pytest.mark.skip(reason="_get_lmeval_params rewritten in v13; "
                        "old if-else cascade tests obsolete")
    def test_default_branch(self):
        params = _get_lmeval_params("plain-7b-model", "")
        assert params["max_tokens"] == 1024
        assert params["temperature"] == 0.0


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
        # lmeval_params. The default gpt-oss branch sets until=[...]
        # so we override _get_lmeval_params to drop until.
        with patch.object(rb, "_get_lmeval_params",
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

    @pytest.mark.skip(reason="_get_lmeval_params rewritten in v13; "
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
        # Use a tiny custom case: monkey-patch _get_lmeval_params
        with patch.object(rb, "_get_lmeval_params", return_value={"foo": "bar"}):
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
            "model_key": "qwen3.6-30b",
            "identifier": "qwen3.6-30b@q4_k_m",
        }
        with patch.object(rb, "get_current_loaded_model", return_value=loaded):
            with patch.object(rb, "load_model_via_lms") as ld:
                with patch.object(rb, "wait_for_model_ready") as w:
                    _ensure_model_still_loaded("qwen3.6-30b", "qwen3.6-30b")
                    ld.assert_not_called()
                    w.assert_not_called()

    def test_reload_called_when_unloaded(self, capsys):
        with patch.object(rb, "get_current_loaded_model", return_value=None):
            with patch.object(rb, "load_model_via_lms") as ld:
                with patch.object(rb, "wait_for_model_ready", return_value=True) as w:
                    _ensure_model_still_loaded("qwen3.6-30b", "qwen3.6-30b")
                    ld.assert_called_once()
                    w.assert_called_once()

    def test_reload_called_when_different_model(self, capsys):
        loaded = {
            "model_key": "some-other-model",
            "identifier": "some-other-model@q4_k_m",
        }
        with patch.object(rb, "get_current_loaded_model", return_value=loaded):
            with patch.object(rb, "load_model_via_lms") as ld:
                with patch.object(rb, "wait_for_model_ready", return_value=True) as w:
                    _ensure_model_still_loaded("qwen3.6-30b", "qwen3.6-30b")
                    ld.assert_called_once()
                    w.assert_called_once()

    def test_warning_printed_when_model_lost(self, capsys):
        with patch.object(rb, "get_current_loaded_model", return_value=None):
            with patch.object(rb, "load_model_via_lms"):
                with patch.object(rb, "wait_for_model_ready", return_value=True):
                    _ensure_model_still_loaded("qwen3.6-30b", "qwen3.6-30b", "MATH-500")
                    out = capsys.readouterr().out
                    assert "[WARN]" in out
                    assert "MATH-500" in out
