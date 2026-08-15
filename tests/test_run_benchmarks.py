import json
import io
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import run_benchmarks as rb
from run_benchmarks import (
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
        # Mock registry with reasoning field using real normalized keys
        registry_data = {
            "deepseek-r1-distill-7b": {
                "reasoning": "thinking",
                "context_length": 16384,
            },
            "o1-reasoning": {
                "reasoning": "thinking",
                "context_length": 16384,
            },
            "think-model": {
                "reasoning": "thinking",
                "context_length": 16384,
            },
            "llama-3b": {
                "reasoning": "instruct",
                "context_length": 8192,
            },
        }
        norm_map = {
            "deepseek-r1-distill-7b": "deepseek-r1-distill-7b",
            "o1-reasoning": "o1-reasoning",
            "think-model": "think-model",
            "llama-3b": "llama-3b",
        }
        with patch.object(rb, "_load_registry_for_context", return_value=(registry_data, norm_map)):
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
    """Tests fuer _get_evaluation_parameters() (Sampling-Design 2026-08-06).

    Seit 2026-08-05: MODEL_TEMP_OVERRIDES und der Knowledge-Floor sind entfernt.
    Seit 2026-08-06: temperature/top_p kommen aus MODEL_CATEGORY_SAMPLING bzw.
    den Kategorie-Defaults; LMS-JSON liefert nur noch Nicht-Temperatur-Felder.
    Diese Tests patchen LMS_CONFIG_ROOT auf ein leeres Verzeichnis, damit sie
    maschinenunabhaengig bleiben.
    """

    @pytest.fixture(autouse=True)
    def _no_lms_configs(self, tmp_path, monkeypatch):
        import benchmark_config as bc
        monkeypatch.setattr(bc, "LMS_CONFIG_ROOT", tmp_path / "no-lms-configs")

    @staticmethod
    def _write_lms_config(root, publisher, model_dir, fields):
        d = root / publisher / model_dir
        d.mkdir(parents=True, exist_ok=True)
        data = {
            "operation": {"fields": [{"key": k, "value": v} for k, v in fields.items()]},
            "load": {"fields": []},
        }
        (d / "model.gguf.json").write_text(json.dumps(data), encoding="utf-8")
        return d

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

    # Region: Category-Defaults (Fallback ohne JSON-Config) ----------------
    def test_coding_default_is_deterministic(self):
        params = _get_evaluation_parameters("plain-7b-model", "coding")
        assert params["temperature"] == 0.2        # coding (Research 06.08.)
        assert params["top_p"] == 1.0
        assert params["max_tokens"] == 4096

    def test_math_default_has_higher_max_tokens(self):
        params = _get_evaluation_parameters("plain-7b-model", "math")
        assert params["max_tokens"] == 4096        # math erlaubt mehr Tokens

    def test_knowledge_default(self):
        params = _get_evaluation_parameters("plain-7b-model", "arc")
        assert params["temperature"] == 0.6
        assert params["max_tokens"] == 4096

    def test_agentic_default(self):
        params = _get_evaluation_parameters("plain-7b-model", "ifeval")
        assert params["temperature"] == 0.6        # leicht stochastisch fuer tool-use
        assert params["max_tokens"] == 4096

    def test_sampling_table_replaces_model_overrides(self):
        # MODEL_TEMP_OVERRIDES sind entfernt; stattdessen entscheidet
        # MODEL_CATEGORY_SAMPLING (Modell x Kategorie) ueber die Defaults.
        expected = {
            "unsloth/phi-4": 0.0,                       # Zeile phi-4
            "unsloth/gpt-oss-20b": 1.0,                 # Zeile gpt-oss
            "vinpix/bonsai-8b-llama.cpp": 0.2,          # Bonsai 06.08. entfernt -> Kategorie-Default
            "lmstudio-community/deepseek-coder-v2-lite-instruct": 0.3,  # Zeile deepseek-coder-v2
            "qwen3.5-72b-instruct": 0.2,                # keine Zeile -> Kategorie-Default
            "gemma-3-12b": 0.2,                         # keine Zeile -> Kategorie-Default
        }
        for model, temp in expected.items():
            params = _get_evaluation_parameters(model, "coding")
            assert params["temperature"] == temp, model
            assert "top_k" not in params
            assert "min_p" not in params
            if "gpt-oss" not in model:
                # gpt-oss liefert until aus der Blueprint-Definition (eigener Test).
                assert "until" not in params
                assert "stop" not in params

    def test_gptoss_until_from_blueprint(self):
        # Seit 14.08.: stop_strings kommen aus der Blueprint-Definition (SSOT).
        # gptoss_reasoning definiert <|return|> (Harmony-EOS, Template-Kommentar:
        # "<|return|> indicates the end of generation, <|end|> does not").
        params = _get_evaluation_parameters("unsloth/gpt-oss-20b", "coding")
        assert params.get("until") == ["<|return|>"]

    def test_enable_thinking_false_emits_chat_template_kwargs(self):
        # Wenn enable_thinking=False, wird chat_template_kwargs mit enable_thinking=False gesetzt
        # (OpenAI-kompatibles API statt Native REST API).
        params = _get_evaluation_parameters("plain-7b-model", "coding")
        chat_template_kwargs = params.get("chat_template_kwargs", {})
        if "enable_thinking" in chat_template_kwargs and chat_template_kwargs["enable_thinking"] is False:
            # Kein reasoning="off" mehr (Native API entfernt)
            assert "reasoning" not in params or params.get("reasoning") != "off"

    # Region: LMS-JSON-Config liefert nur Nicht-Temperatur-Felder ----------
    def test_lms_temp_ignored_non_temp_merged(self, tmp_path):
        # JSON-temperature zaehlt nicht mehr (2026-08-06); min_p aus der
        # Config wird weiterhin uebernommen.
        self._write_lms_config(tmp_path, "pub1", "fake-model-7b",
                               {"llm.prediction.temperature": 0.6,
                                "llm.prediction.minPSampling": 0.02})
        import benchmark_config as bc
        with patch.object(bc, "LMS_CONFIG_ROOT", tmp_path):
            params = _get_evaluation_parameters("pub1/fake-model-7b", "coding")
        assert params["temperature"] == 0.2
        assert params["min_p"] == 0.02

    def test_lms_temp_ignored_category_variation_applies(self, tmp_path):
        # Gleiche Config -> Kategorie-Differenzierung greift (2026-08-06):
        # ohne Tabellen-Zeile gelten pro Kategorie die Defaults, nicht der
        # eine GUI-Wert.
        self._write_lms_config(tmp_path, "pub1", "fake-model-7b",
                               {"llm.prediction.temperature": 0.6})
        import benchmark_config as bc
        expected = {"arc": 0.6, "ifeval": 0.6, "ds1000": 0.2, "math-500": 0.7}
        with patch.object(bc, "LMS_CONFIG_ROOT", tmp_path):
            for bench, temp in expected.items():
                params = _get_evaluation_parameters("pub1/fake-model-7b", bench)
                assert params["temperature"] == temp, bench

    def test_lms_thinking_enabled_emits_chat_template_kwargs(self, tmp_path):
        self._write_lms_config(tmp_path, "pub1", "fake-model-7b",
                               {"llm.prediction.reasoning.enableThinking": True})
        import benchmark_config as bc
        with patch.object(bc, "LMS_CONFIG_ROOT", tmp_path):
            params = _get_evaluation_parameters("pub1/fake-model-7b", "coding")
        chat_template_kwargs = params.get("chat_template_kwargs", {})
        assert chat_template_kwargs.get("enable_thinking") is True

    # Region: --thinking Flag + REASONING_PATTERNS ---------------------
    def test_thinking_flag_with_reasoning_pattern_enables_thinking(self, monkeypatch):
        monkeypatch.setattr(rb, "IS_THINKING_ENABLED", True)
        # "r1" ist in REASONING_PATTERNS, "deepseek-r1-distill" ebenfalls
        params = _get_evaluation_parameters("r1-distill-7b", "coding")
        chat_template_kwargs = params.get("chat_template_kwargs", {})
        assert chat_template_kwargs.get("enable_thinking") is True
        # Und reasoning="off" darf NICHT gesetzt sein (Native API entfernt)
        assert "reasoning" not in params or params.get("reasoning") != "off"

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
        # evaluation_parameters. The default gpt-oss branch sets until=[<|return|>]
        # (Blueprint-SSOT), so we override _get_evaluation_parameters to drop until.
        with patch.object(rb, "_get_evaluation_parameters",
                          return_value={"max_tokens": 4096, "temperature": 1.0}):
            cmd = _build_lmeval_cmd("gpt-oss-20b", "gpt-oss-20b", "task1", 5, "/tmp/out")
            idx = cmd.index("--model_args")
            args_json = json.loads(cmd[idx + 1])
            assert args_json["eos_string"] == "<|return|>"

    def test_gptoss_default_has_until_from_blueprint(self):
        # Seit 14.08.: stop_strings aus Blueprint (SSOT). gptoss_reasoning
        # liefert until=["<|return|>"], daher greift der eos_string-Fallback
        # fuer gpt-oss NICHT mehr (bis 13.08.: eos_string=<|endoftext|>).
        cmd = _build_lmeval_cmd("gpt-oss-20b", "gpt-oss-20b", "task1", 5, "/tmp/out")
        idx = cmd.index("--gen_kwargs")
        kwargs = json.loads(cmd[idx + 1])
        assert kwargs["until"] == ["<|return|>"]
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


# ======================================================================
# run_agentic – JSON-Pfad (Fix 2026-07-31)
# ======================================================================

class TestWindowsSignalShim:
    """Regressionstest für den evalplus-Windows-Fix (14.08.2026).

    evalplus.gen.util.openai_request macht signal.signal/SIGALRM-Aufrufe, die
    auf Windows nicht existieren. Der _WindowsSignalShim ersetzt das Modul-
    level `signal` durch No-Ops, damit make_auto_request nicht endlos retried.
    """

    def test_shim_signal_and_alarm_are_noops(self) -> None:
        shim = rb._WindowsSignalShim()
        assert shim.signal(0, None) is None
        assert shim.alarm(100) == 0

    def test_shim_exposes_alarm_attribute(self) -> None:
        # evalplus ruft signal.alarm(...) ab - auf echtem Windows-signal fehlt
        # das Attribut komplett (AttributeError -> Endlos-Retry in make_auto_request).
        assert hasattr(rb._WindowsSignalShim(), "alarm")
        assert hasattr(rb._WindowsSignalShim(), "signal")

    def test_shim_exposes_sigalrm_attribute(self) -> None:
        # evalplus liest signal.SIGALRM als Attribut (signal.signal(SIGALRM, handler)).
        # Ohne dieses Attribut: AttributeError -> Endlos-Retry (Fix 14.08., 2. Iteration).
        assert hasattr(rb._WindowsSignalShim(), "SIGALRM")
        assert isinstance(rb._WindowsSignalShim.SIGALRM, int)


class TestEvalplusSubsetEval:
    """Regressionstests für die Subset-Evaluation (16.08.2026).

    evalplus' evaluate() lädt das volle Dataset (164/378 Tasks) und assertiert
    len(completion_id) == len(problems) -> AssertionError bei Stichproben.
    evalplus_subset_eval.py bewertet nur die gesampelten Tasks.
    """

    def test_module_importable_and_exposes_main(self) -> None:
        import evalplus_subset_eval as ese

        assert callable(ese.main)
        assert callable(ese._evaluate_subset)

    def test_subset_cache_hash_is_stable_and_base_independent(self) -> None:
        import evalplus_subset_eval as ese

        h1 = ese._subset_cache_hash("base", ["HumanEval/0", "HumanEval/1"])
        h2 = ese._subset_cache_hash("base", ["HumanEval/0", "HumanEval/1"])
        h3 = ese._subset_cache_hash("base", ["HumanEval/1", "HumanEval/0"])
        h4 = ese._subset_cache_hash("other", ["HumanEval/0", "HumanEval/1"])
        assert h1 == h2
        assert h1 == h3  # Reihenfolge egal (sortiert)
        assert h1 != h4  # Basis-Hash fliesst ein
        assert h1.startswith("base_subset_")

    def test_windows_signal_timer_shim(self) -> None:
        # time_limit (evalplus/eval/utils.py) ruft signal.setitimer/signal.signal
        # ab - UNIX-only. Der Shim muss die Attribute des signal-Moduls anbieten.
        import evalplus_subset_eval as ese

        if not hasattr(ese, "_WindowsSignalTimerShim"):
            pytest.skip("nur auf Windows aktiv")
        shim = ese._WindowsSignalTimerShim()
        assert shim.setitimer(shim.ITIMER_REAL, 5) == 0
        assert shim.signal(shim.SIGALRM, None) is None


class TestRunAgentic:
    def test_json_path_uses_safe_identifier_not_slash(self, monkeypatch, tmp_path):
        # Fix 2026-07-31: model_identifier mit Slash (z.B. "essentialai/rnj-1@q8_0")
        # erzeugte einen Unterordner im JSON-Pfad ("agentic_essentialai/rnj-1@...").
        # Der Pfad muss den "safe"-Namen verwenden.
        monkeypatch.setattr(rb, "RESULTS_DIR", str(tmp_path))
        fake_proc = MagicMock()
        fake_proc.returncode = 0
        fake_proc.stdout = io.StringIO("")
        fake_proc.stderr = io.StringIO("")
        model_info = {"key": "essentialai/rnj-1@q8_0", "display": "RNJ-1"}
        with patch.object(rb.subprocess, "Popen", return_value=fake_proc) as popen:
            rb.run_agentic(model_info, limit=2)
        cmd = popen.call_args.args[0]
        json_idx = cmd.index("--json-file")
        json_path = cmd[json_idx + 1]
        expected_dir = os.path.join(str(tmp_path), "agentic_essentialai_rnj-1@q8_0")
        assert os.path.dirname(json_path) == expected_dir
        assert os.path.basename(json_path).startswith("agentic_essentialai_rnj-1@q8_0_")
        assert "essentialai/rnj-1" not in json_path

    def test_safety_mode_uses_only_category_k(self, monkeypatch, tmp_path):
        monkeypatch.setattr(rb, "RESULTS_DIR", str(tmp_path))
        fake_proc = MagicMock()
        fake_proc.returncode = 0
        fake_proc.stdout = io.StringIO("")
        fake_proc.stderr = io.StringIO("")
        model_info = {"key": "test-model", "display": "Test Model"}
        with patch.object(rb.subprocess, "Popen", return_value=fake_proc) as popen:
            rb.run_agentic(model_info, limit=13, mode="safety", seed=42)
        cmd = popen.call_args.args[0]
        sc_idx = cmd.index("--scenarios")
        selected = set(cmd[sc_idx + 1:sc_idx + 1 + 13])
        assert selected == set(rb.AGENTIC_SAFETY_SCENARIO_IDS)

    def test_safety_mode_honours_limit(self, monkeypatch, tmp_path):
        monkeypatch.setattr(rb, "RESULTS_DIR", str(tmp_path))
        fake_proc = MagicMock()
        fake_proc.returncode = 0
        fake_proc.stdout = io.StringIO("")
        fake_proc.stderr = io.StringIO("")
        model_info = {"key": "test-model", "display": "Test Model"}
        with patch.object(rb.subprocess, "Popen", return_value=fake_proc) as popen:
            rb.run_agentic(model_info, limit=3, mode="safety", seed=42)
        cmd = popen.call_args.args[0]
        sc_idx = cmd.index("--scenarios")
        selected = cmd[sc_idx + 1:sc_idx + 1 + 3]
        assert len(selected) == 3
        assert all(s in rb.AGENTIC_SAFETY_SCENARIO_IDS for s in selected)

    def test_seed_reproduces_selection(self, monkeypatch, tmp_path):
        monkeypatch.setattr(rb, "RESULTS_DIR", str(tmp_path))
        calls = []
        def _fake_popen(cmd, *args, **kwargs):
            fake = MagicMock()
            fake.returncode = 0
            fake.stdout = io.StringIO("")
            fake.stderr = io.StringIO("")
            calls.append(cmd)
            return fake
        with patch.object(rb.subprocess, "Popen", side_effect=_fake_popen):
            rb.run_agentic({"key": "m1", "display": "M1"}, limit=6, seed=2026)
            rb.run_agentic({"key": "m1", "display": "M1"}, limit=6, seed=2026)
            rb.run_agentic({"key": "m1", "display": "M1"}, limit=6, seed=7)
        def _selected(cmd):
            sc_idx = cmd.index("--scenarios")
            return tuple(cmd[sc_idx + 1:sc_idx + 1 + 6])
        assert _selected(calls[0]) == _selected(calls[1])
        assert _selected(calls[0]) != _selected(calls[2])


# ======================================================================
# Single-Instance Lock (Fix 2026-07-31: parallele Launcher)
# ======================================================================

class TestSingleInstanceLock:
    DEAD_PID = 2147483647  # max int32 – no live process

    def test_acquire_creates_lock_file(self, tmp_path):
        lock_path = os.path.join(str(tmp_path), ".benchmark.lock")
        assert rb._acquire_single_instance_lock(lock_path) is None
        assert os.path.exists(lock_path)
        with open(lock_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["pid"] == os.getpid()
        assert "started" in data

    def test_acquire_blocks_live_owner(self, tmp_path):
        lock_path = os.path.join(str(tmp_path), ".benchmark.lock")
        with open(lock_path, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "started": "2026-07-31T22:00:00"}, f)
        err = rb._acquire_single_instance_lock(lock_path)
        assert err is not None
        assert "FATAL" in err
        assert str(os.getpid()) in err

    def test_acquire_overwrites_stale_lock(self, tmp_path):
        lock_path = os.path.join(str(tmp_path), ".benchmark.lock")
        with open(lock_path, "w", encoding="utf-8") as f:
            json.dump({"pid": self.DEAD_PID, "started": "2026-07-31T22:00:00"}, f)
        assert rb._acquire_single_instance_lock(lock_path) is None
        with open(lock_path, "r", encoding="utf-8") as f:
            assert json.load(f)["pid"] == os.getpid()

    def test_acquire_overwrites_corrupt_lock(self, tmp_path):
        lock_path = os.path.join(str(tmp_path), ".benchmark.lock")
        with open(lock_path, "w", encoding="utf-8") as f:
            f.write("not-json")
        assert rb._acquire_single_instance_lock(lock_path) is None

    def test_release_removes_own_lock(self, tmp_path):
        lock_path = os.path.join(str(tmp_path), ".benchmark.lock")
        assert rb._acquire_single_instance_lock(lock_path) is None
        rb._release_single_instance_lock(lock_path)
        assert not os.path.exists(lock_path)

    def test_release_keeps_foreign_lock(self, tmp_path):
        lock_path = os.path.join(str(tmp_path), ".benchmark.lock")
        with open(lock_path, "w", encoding="utf-8") as f:
            json.dump({"pid": self.DEAD_PID, "started": "x"}, f)
        rb._release_single_instance_lock(lock_path)
        assert os.path.exists(lock_path)


# ======================================================================
# Run-Spec (YAML) support
# ======================================================================

class _RunSpecArgs:
    """Minimales Namespace-Objekt mit den CLI-Defaults des Launchers."""
    def __init__(self, **overrides):
        for dest, default in rb.RUN_SPEC_PARSER_DEFAULTS.items():
            setattr(self, dest, default)
        for k, v in overrides.items():
            setattr(self, k, v)


class TestRunSpec:
    def _write_spec(self, tmp_path, content):
        p = os.path.join(str(tmp_path), "run.yaml")
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return p

    def test_load_basic_spec(self, tmp_path):
        p = self._write_spec(tmp_path, """\
models: ["m1", "m2"]
benchmarks: ["DS1000", "Agentic"]
sample_size: 3
seed: 2026
agentic_mode: safety
thinking: true
""")
        spec = rb._load_run_spec(p)
        assert spec == {
            "model": "m1,m2",
            "benchmarks": "DS1000,Agentic",
            "sample_size": 3,
            "seed": 2026,
            "agentic_mode": "safety",
            "thinking": True,
        }

    def test_load_spec_list_to_csv(self, tmp_path):
        p = self._write_spec(tmp_path, "benchmarks:\n  - DS1000\n  - CoderEval\nmodels: [a, b]\n")
        spec = rb._load_run_spec(p)
        assert spec["benchmarks"] == "DS1000,CoderEval"
        assert spec["model"] == "a,b"

    def test_load_spec_unknown_key_warns(self, tmp_path, capsys):
        p = self._write_spec(tmp_path, "bogus_key: 1\nseed: 5\n")
        spec = rb._load_run_spec(p)
        assert "seed" in spec
        assert "bogus_key" not in spec
        assert "unbekannter Schlüssel" in capsys.readouterr().out

    def test_load_spec_bad_bool_ignored(self, tmp_path, capsys):
        p = self._write_spec(tmp_path, "thinking: [nope]\n")
        spec = rb._load_run_spec(p)
        assert "thinking" not in spec
        assert "erwartet bool" in capsys.readouterr().out

    def test_load_spec_bad_sample_size_ignored(self, tmp_path, capsys):
        p = self._write_spec(tmp_path, "sample_size: -3\n")
        spec = rb._load_run_spec(p)
        assert "sample_size" not in spec

    def test_load_spec_missing_file_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            rb._load_run_spec(os.path.join(str(tmp_path), "nope.yaml"))

    def test_load_spec_invalid_yaml_exits(self, tmp_path):
        p = self._write_spec(tmp_path, "models: [unclosed\n")
        with pytest.raises(SystemExit):
            rb._load_run_spec(p)

    def test_apply_spec_fills_defaults(self):
        args = _RunSpecArgs()
        out = rb._apply_run_spec(args, {"sample_size": 3, "seed": 7})
        assert out.sample_size == 3
        assert out.seed == 7

    def test_apply_spec_cli_overrides_yaml(self):
        args = _RunSpecArgs(sample_size=9)
        out = rb._apply_run_spec(args, {"sample_size": 3, "seed": 7})
        assert out.sample_size == 9
        assert out.seed == 7

    def test_parse_args_run_spec_end_to_end(self, tmp_path, capsys):
        p = self._write_spec(tmp_path, "sample_size: 3\nseed: 2026\n")
        args, _ = rb._parse_args(["--run-spec", p])
        assert args.sample_size == 3
        assert args.seed == 2026

    def test_parse_args_unknown_key_warns(self, tmp_path, capsys):
        p = self._write_spec(tmp_path, "sample_size: 3\nbogus_flag: true\n")
        rb._parse_args(["--run-spec", p])
        assert "unbekannter Schlüssel" in capsys.readouterr().out

    def test_parse_args_cli_flags_win_over_run_spec(self, tmp_path):
        p = self._write_spec(tmp_path, "sample_size: 3\nseed: 2026\n")
        args, _ = rb._parse_args(["--run-spec", p, "--sample-size", "19", "--seed", "7"])
        assert args.sample_size == 19
        assert args.seed == 7


# ======================================================================
# _check_registry_for_model (Fix 14.08.: Template-Skip-Bug)
# ======================================================================

class TestCheckRegistryForModel:
    """Template-Skip-Bug: `return None` stand auf falscher Ebene und übersprang
    ALLE Modelle mit Template (auch wenn die Template-Datei existierte)."""

    def _registry(self, template=None, blueprint="default_chat"):
        entry = {"reasoning": "thinking", "capabilities": ["chat"],
                 "blueprint": blueprint}
        if template:
            entry["template"] = template
        reg = {"unsloth/gemma-4-26b-a4b-it": entry}
        norm = {"gemma-4-26b-a4b-it": "unsloth/gemma-4-26b-a4b-it"}
        return reg, norm

    def test_returns_true_when_template_file_exists(self, tmp_path):
        # Fix: vorhandene Template-Datei -> KEIN Skip
        reg, norm = self._registry(blueprint="default_chat")
        with (
            patch.object(rb, "_load_registry_for_context", return_value=(reg, norm)),
            patch("assemble_blueprint.resolve_template_name", return_value="gemma4-26b-template_minijinja.jinja"),
            patch("registry_tool._load_blueprints", return_value={"default_chat": {}}),
            patch("registry_tool.TEMPLATE_DIR", tmp_path),
        ):
            (tmp_path / "gemma4-26b-template_minijinja.jinja").write_text("{{ x }}", encoding="utf-8")
            result = rb._check_registry_for_model("unsloth/gemma-4-26b-a4b-it", "Gemma 4")
        assert result is not None

    def test_returns_none_when_template_file_missing(self, tmp_path):
        reg, norm = self._registry(blueprint="default_chat")
        with (
            patch.object(rb, "_load_registry_for_context", return_value=(reg, norm)),
            patch("assemble_blueprint.resolve_template_name", return_value="missing.jinja"),
            patch("registry_tool._load_blueprints", return_value={"default_chat": {}}),
            patch("registry_tool.TEMPLATE_DIR", tmp_path),
        ):
            result = rb._check_registry_for_model("unsloth/gemma-4-26b-a4b-it", "Gemma 4")
        assert result is None

    def test_returns_none_when_blueprint_missing(self):
        reg, norm = self._registry(blueprint=None)
        with patch.object(rb, "_load_registry_for_context", return_value=(reg, norm)):
            result = rb._check_registry_for_model("unsloth/gemma-4-26b-a4b-it", "Gemma 4")
        assert result is None
