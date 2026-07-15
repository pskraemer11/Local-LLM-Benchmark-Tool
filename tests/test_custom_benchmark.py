import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import custom_benchmark_v13 as cb
from custom_benchmark_v13 import (
    _is_bare_statement,
    _patch_matplotlib_compat,
    _repair_indentation,
    _unwrap_solution_for_insert,
    collect_system_metrics,
    evaluate_code,
    exec_sandboxed,
    extract_code,
    get_task_type,
    load_jsonl,
    parse_resource_avgs,
    parse_selection,
    parse_tests_field,
    strip_thinking_tokens,
    subsample_tasks,
)


# ======================================================================
# Pure utilities
# ======================================================================

class TestIsBareStatement:
    def test_short_line_is_not_statement(self):
        assert _is_bare_statement("a") is False
        assert _is_bare_statement("") is False

    def test_simple_assignment(self):
        assert _is_bare_statement("x = 1") is True
        assert _is_bare_statement("x.y = 2") is True

    def test_compound_assignment(self):
        assert _is_bare_statement("x += 1") is True
        assert _is_bare_statement("x -= 2") is True

    def test_function_call(self):
        assert _is_bare_statement("print('hello')") is True
        assert _is_bare_statement("obj.method()") is True
        assert _is_bare_statement("arr[0]()") is True

    def test_import(self):
        assert _is_bare_statement("import os") is True
        assert _is_bare_statement("from sys import argv") is True

    def test_return_yield(self):
        assert _is_bare_statement("return 42") is True
        assert _is_bare_statement("yield x") is True

    def test_block_header(self):
        assert _is_bare_statement("if x > 0:") is True
        # else:/except:/finally: need a preceding block (handled in
        # _repair_indentation, not by _is_bare_statement alone).
        # So `else:` on its own returns False here.
        assert _is_bare_statement("else:") is False
        assert _is_bare_statement("elif x:") is True

    def test_decorator(self):
        assert _is_bare_statement("@decorator") is True

    def test_arithmetic_only_compared_short(self):
        # Just an operator on its own is not valid Python → False
        # (len < 3 returns False anyway)
        assert _is_bare_statement("==") is False


class TestRepairIndentation:
    def test_valid_code_passes_through(self):
        valid = "def f():\n    return 1\n"
        assert _repair_indentation(valid) == valid

    def test_top_level_def_no_body_inserts_pass(self):
        # `def f(): ...` with no body should get `pass` inserted
        code = "def f():\n"
        result = _repair_indentation(code)
        # Should have `pass` after `def f():`
        assert "pass" in result
        # Should compile after repair
        compile(result, "<test>", "exec")

    def test_under_indented_compiles(self):
        # Body indented with 2 spaces instead of 4 — should be normalized
        code = "def f():\n  return 1\n"
        result = _repair_indentation(code)
        compile(result, "<test>", "exec")


class TestUnwrapSolutionForInsert:
    def test_keeps_bare_return(self):
        # If the body is just "return x", don't add a def
        code = "return x"
        # The function is implementation-specific; just check it doesn't crash
        result = _unwrap_solution_for_insert(code, setup_code="")
        assert isinstance(result, str)


class TestPatchMatplotlibCompat:
    def test_patches_set_xticklabels(self):
        # Find the actual pattern
        import custom_benchmark_v13 as cb
        import inspect as _i
        src = _i.getsource(cb._patch_matplotlib_compat)
        # Just verify it exists and doesn't crash on simple code
        result = _patch_matplotlib_compat("x = 1")
        assert isinstance(result, str)
        assert "x = 1" in result

    def test_no_change_for_safe_code(self):
        result = _patch_matplotlib_compat("y = plt.plot([1,2,3])\n")
        assert "plot" in result


# ======================================================================
# extract_code (Granite/Markdown/JSON/Bare)
# ======================================================================

class TestExtractCode:
    def test_returns_empty_for_none(self):
        assert extract_code(None) == ""

    def test_returns_empty_for_empty(self):
        assert extract_code("") == ""

    def test_extracts_markdown_code_block(self):
        text = "Here is the solution:\n```python\ndef hello():\n    return 1\n```\nDone"
        result = extract_code(text)
        assert "def hello():" in result
        assert "return 1" in result

    def test_extracts_code_block_without_language(self):
        text = "```\nx = 1\n```"
        result = extract_code(text)
        assert "x = 1" in result

    def test_extracts_last_block_when_multiple(self):
        text = "```python\nfirst = 1\n```\nThen:\n```python\nsecond = 2\n```"
        result = extract_code(text)
        assert "second = 2" in result
        assert "first" not in result

    def test_extracts_structured_json(self):
        # Properly JSON-escaped string (json.dumps converts \n to \\n)
        text = json.dumps({"code": "def foo():\n    return 42"})
        result = extract_code(text, structured=True)
        assert "def foo():" in result
        assert "return 42" in result

    def test_structured_falls_through_to_text(self):
        # Invalid JSON → fall through to regex fallback
        text = "```python\nx = 1\n```"
        result = extract_code(text, structured=True)
        assert "x = 1" in result

    def test_extracts_bare_python(self):
        text = "def hello():\n    return 1\necho"
        result = extract_code(text)
        assert "def hello():" in result
        assert "return 1" in result

    def test_extracts_bare_statements(self):
        # Granite-style: bare statements without def
        text = "x = 1\ny = 2\nz = x + y"
        result = extract_code(text)
        # Without def/class, bare statements should be picked up
        # (at least some lines)
        assert "x = 1" in result or "y = 2" in result or "z = x + y" in result

    def test_no_code_in_response_returns_empty(self):
        text = "Some natural language explanation with no code."
        result = extract_code(text)
        # Should return "" since no code indicators
        assert result == ""

    def test_high_code_density_fallback(self):
        # Response that looks like code without specific markers
        text = "x = (1 + 2)\nprint(x)\ny = (3 + 4)\nprint(y)"
        result = extract_code(text)
        # Should fallback to returning the text as-is
        assert result != ""


# ======================================================================
# strip_thinking_tokens
# ======================================================================

class TestStripThinkingTokens:
    def test_returns_text_unchanged_when_no_thinking(self):
        text = "def hello(): return 1"
        cleaned, count = strip_thinking_tokens(text)
        assert cleaned == text
        assert count == 0

    def test_strips_legacy_think_tags(self):
        # The legacy stripper recognizes only  content and
        # channel>thought<\/channel|>. Sections of plain text outside those
        # tags are preserved.
        open_tag = "<|channel>thought"  # noqa: tag containing '<|'
        text = f"before {open_tag}\nmy reasoning here\n<channel|> after"
        cleaned, count = strip_thinking_tokens(text)
        assert "my reasoning here" not in cleaned
        assert count > 0

    def test_strips_channel_thought(self):
        # Same pattern as above (channel>thought are alternate names
        # for the Gemma 4 format -- verifying either branch works).
        open_tag = "<|channel>thought"  # noqa
        text = f"before {open_tag}\ninner thought\n<channel|> after"
        cleaned, count = strip_thinking_tokens(text)
        assert "inner thought" not in cleaned
        assert count > 0

    def test_strips_gemma_channel_tags(self):
        text = "before <|channel>thought\nmy thinking\n<channel|> after"
        cleaned, count = strip_thinking_tokens(text)
        assert "my thinking" not in cleaned
        assert count > 0

    def test_empty_text_returns_zero_count(self):
        cleaned, count = strip_thinking_tokens(None)
        assert count == 0


# ======================================================================
# parse_tests_field
# ======================================================================

class TestParseTestsField:
    def test_list_returned_as_is(self):
        assert parse_tests_field(["a", "b"]) == ["a", "b"]

    def test_string_with_brackets_parsed(self):
        assert parse_tests_field("['test1', 'test2']") == ["test1", "test2"]

    def test_empty_string_returns_empty(self):
        assert parse_tests_field("") == []

    def test_string_with_brackets_only(self):
        assert parse_tests_field("[]") == []

    def test_plain_string_returns_as_singleton(self):
        assert parse_tests_field("assert x == 1") == ["assert x == 1"]

    def test_invalid_string_returns_as_singleton(self):
        # ast.literal_eval fails → fallback to singleton
        assert parse_tests_field("not valid python [") == ["not valid python ["]

    def test_none_returns_empty(self):
        assert parse_tests_field(None) == []

    def test_int_returns_empty(self):
        assert parse_tests_field(42) == []


# ======================================================================
# parse_selection
# ======================================================================

class TestParseSelection:
    def test_empty_returns_none(self):
        assert parse_selection("", 5) is None

    def test_single_number(self):
        assert parse_selection("3", 5) == [2]

    def test_range(self):
        result = parse_selection("1-3", 5)
        assert result == [0, 1, 2]

    def test_comma_separated(self):
        result = parse_selection("1,3,5", 5)
        assert result == [0, 2, 4]

    def test_mixed_range_and_singles(self):
        result = parse_selection("1-2,4", 5)
        assert result == [0, 1, 3]

    def test_invalid_range_high_returns_none(self):
        assert parse_selection("1-100", 5) is None

    def test_invalid_range_zero_returns_none(self):
        assert parse_selection("0-3", 5) is None

    def test_inverted_range_returns_none(self):
        assert parse_selection("5-2", 10) is None

    def test_non_numeric_returns_none(self):
        assert parse_selection("abc", 5) is None

    def test_whitespace_tolerated(self):
        result = parse_selection(" 1 , 3 ", 5)
        assert result == [0, 2]

    def test_dedup(self):
        result = parse_selection("1,1,2", 5)
        assert result == [0, 1]


# ======================================================================
# get_task_type
# ======================================================================

class TestGetTaskType:
    def test_data_science(self):
        assert get_task_type("data_science.jsonl") == "data_science"

    def test_codereval(self):
        assert get_task_type("codereval_selfcontained.jsonl") == "codereval"

    def test_unknown(self):
        assert get_task_type("foo.jsonl") == "unknown"


# ======================================================================
# load_jsonl
# ======================================================================

class TestLoadJsonl:
    def test_loads_simple(self, tmp_path):
        f = tmp_path / "data.jsonl"
        f.write_text(
            '{"a": 1}\n{"b": 2}\n',
            encoding="utf-8",
        )
        result = load_jsonl(str(f))
        assert result == [{"a": 1}, {"b": 2}]

    def test_skips_blank_lines(self, tmp_path):
        f = tmp_path / "data.jsonl"
        f.write_text(
            '{"a": 1}\n\n{"b": 2}\n\n',
            encoding="utf-8",
        )
        result = load_jsonl(str(f))
        assert result == [{"a": 1}, {"b": 2}]

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.jsonl"
        f.write_text("", encoding="utf-8")
        assert load_jsonl(str(f)) == []


# ======================================================================
# parse_resource_avgs
# ======================================================================

class TestParseResourceAvgs:
    def test_empty_returns_all_none(self):
        result = parse_resource_avgs([])
        assert result == (None, None, None, None)

    def test_returns_averages(self):
        results = [
            {"cpu_during": 10, "ram_during": 20, "gpu_during": 30, "vram_during": 40},
            {"cpu_during": 20, "ram_during": 40, "gpu_during": 60, "vram_during": 80},
        ]
        cpu, ram, gpu, vram = parse_resource_avgs(results)
        assert cpu == pytest.approx(15.0)
        assert ram == pytest.approx(30.0)
        assert gpu == pytest.approx(45.0)
        assert vram == pytest.approx(60.0)

    def test_missing_values_default_to_zero(self):
        results = [{}, {}]
        cpu, ram, gpu, vram = parse_resource_avgs(results)
        assert cpu == 0.0
        assert ram == 0.0
        assert gpu == 0.0
        assert vram == 0.0

    def test_invalid_values_skipped(self):
        results = [
            {"cpu_during": "garbage", "ram_during": 20},
            {"cpu_during": 10, "ram_during": 30},
        ]
        cpu, ram, _, _ = parse_resource_avgs(results)
        # Only one valid cpu
        assert cpu == 10.0
        assert ram == pytest.approx(25.0)


# ======================================================================
# subsample_tasks
# ======================================================================

class TestSubsampleTasks:
    def test_empty_returns_empty(self):
        assert subsample_tasks([], "data_science", 5) == []

    def test_sample_size_none_returns_all(self):
        tasks = [{"id": i} for i in range(5)]
        assert subsample_tasks(tasks, "data_science", None) == tasks

    def test_sample_size_larger_returns_all(self):
        tasks = [{"id": i} for i in range(5)]
        assert subsample_tasks(tasks, "data_science", 10) == tasks

    def test_random_subsample_no_groups(self):
        tasks = [{"id": i} for i in range(20)]
        result = subsample_tasks(tasks, "data_science", 5)
        assert len(result) == 5

    def test_grouped_subsample(self):
        # Two groups, sample_size=4 → 2 per group
        tasks = [
            {"id": f"a{i}", "_group": "g1"} for i in range(5)
        ] + [
            {"id": f"b{i}", "_group": "g2"} for i in range(5)
        ]
        result = subsample_tasks(tasks, "data_science", 4)
        # Should pick ~per_group=ceil(4/2)=2 from each
        assert len(result) == 4
        # Every task should still be in original list
        for r in result:
            assert r in tasks

    def test_grouped_more_than_pool(self):
        # Group with only 1 item, sample requires 4 per group
        tasks = [
            {"id": "a0", "_group": "g1"},
            {"id": "b0", "_group": "g2"},
            {"id": "b1", "_group": "g2"},
            {"id": "b2", "_group": "g2"},
            {"id": "b3", "_group": "g2"},
        ]
        result = subsample_tasks(tasks, "data_science", 4)
        # per_group = ceil(4/2) = 2
        # g1 only has 1, so take 1; g2 has 4, take 2 → total 3
        assert len(result) == 3


# ======================================================================
# evaluate_code (covers paths via mocked _run_sandbox)
# ======================================================================

class TestEvaluateCode:
    def test_empty_generated_returns_zero(self):
        score, msg = evaluate_code("", "f", [])
        assert score == 0.0
        assert "No code" in msg

    @patch.object(cb, "_run_sandbox")
    def test_direct_tests_passing(self, mock_sandbox):
        mock_sandbox.return_value = {"ok": True, "error": None, "passed": 2, "total": 3}
        score, msg = evaluate_code("def f(): return 1", "f",
                                   ["assert f() == 1", "assert True", "assert False"])
        assert score == pytest.approx(2/3)
        assert "2/3" in msg

    @patch.object(cb, "_run_sandbox")
    def test_direct_tests_code_error(self, mock_sandbox):
        mock_sandbox.return_value = {"ok": False, "error": "NameError", "passed": 0, "total": 0}
        score, msg = evaluate_code("def f(): return 1", "f", ["assert True"])
        assert score == 0.0
        assert "Code error" in msg

    @patch.object(cb, "_run_sandbox")
    def test_no_tests_no_errors_returns_one(self, mock_sandbox):
        mock_sandbox.return_value = {"ok": True, "error": None, "passed": 0, "total": 0}
        score, msg = evaluate_code("def f(): pass", "f", [])
        assert score == 1.0
        assert "OK" in msg

    @patch.object(cb, "_run_sandbox")
    def test_no_tests_with_setup_code(self, mock_sandbox):
        mock_sandbox.return_value = {"ok": True, "error": None, "passed": 0, "total": 0}
        # No tests, no reference → falls through to bare execution
        score, msg = evaluate_code("x = 1", "f", [], setup_code="import os")
        assert score == 1.0


# ======================================================================
# exec_sandboxed
# ======================================================================

class TestExecSandboxed:
    @patch.object(cb, "_run_sandbox")
    def test_returns_ok(self, mock_sandbox):
        mock_sandbox.return_value = {"ok": True, "error": None}
        ok, err = exec_sandboxed("x = 1")
        assert ok is True
        assert err is None

    @patch.object(cb, "_run_sandbox")
    def test_returns_error(self, mock_sandbox):
        mock_sandbox.return_value = {"ok": False, "error": "NameError: x"}
        ok, err = exec_sandboxed("undefined_thing()")
        assert ok is False
        assert "NameError" in err

    @patch.object(cb, "_run_sandbox")
    def test_passes_timeout(self, mock_sandbox):
        mock_sandbox.return_value = {"ok": True, "error": None}
        exec_sandboxed("x = 1", timeout=42)
        # Check sandbox was called with timeout arg
        args, kwargs = mock_sandbox.call_args
        # Either positional or keyword
        assert (len(args) >= 2 and args[1] == 42) or kwargs.get("timeout") == 42


# ======================================================================
# collect_system_metrics
# ======================================================================

class TestCollectSystemMetrics:
    @patch.object(cb, "subprocess")
    @patch("psutil.cpu_percent", return_value=42.0)
    @patch("psutil.virtual_memory")
    def test_returns_cpu_and_ram(self, mock_vm, mock_cpu, mock_subprocess):
        mock_vm.return_value = MagicMock(percent=50.0, used=8 * 1024**3, total=16 * 1024**3)
        mock_subprocess.run.return_value = MagicMock(
            returncode=1, stdout="", stderr=""
        )
        metrics = collect_system_metrics()
        assert metrics["cpu_percent"] == 42.0
        assert metrics["ram_percent"] == 50.0
        assert metrics["ram_used_gb"] == pytest.approx(8.0)
        assert metrics["ram_total_gb"] == pytest.approx(16.0)

    @patch.object(cb, "subprocess")
    @patch("psutil.cpu_percent", return_value=42.0)
    @patch("psutil.virtual_memory")
    def test_parses_nvidia_smi(self, mock_vm, mock_cpu, mock_subprocess):
        mock_vm.return_value = MagicMock(percent=50.0, used=8 * 1024**3, total=16 * 1024**3)
        mock_subprocess.run.return_value = MagicMock(
            returncode=0,
            stdout="55, 42, 4096, 8192, 70\n",
            stderr="",
        )
        metrics = collect_system_metrics()
        assert metrics["gpu_util"] == 55.0
        assert metrics["gpu_mem_util"] == 42.0
        assert metrics["gpu_mem_used_gb"] == pytest.approx(4.0)
        assert metrics["gpu_mem_total_gb"] == pytest.approx(8.0)
        assert metrics["gpu_temp"] == 70.0
