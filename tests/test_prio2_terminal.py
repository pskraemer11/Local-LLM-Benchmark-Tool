"""Tests for the IFEval + DS1000 + CoderEval fixes from
Code-Review_2026-07-12.md §7.7 (Prio 0/2/3 terminal-output findings).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from custom_benchmark_v13 import (
    _patch_matplotlib_compat,
    _unwrap_solution_for_insert,
    extract_code,
)


class TestPatchMatplotlibCompat:
    """Prio 2.4: Forward-port deprecated matplotlib API calls."""

    def test_set_xticklabels_ported(self):
        code = "plt.set_xticklabels(['a', 'b'])"
        patched = _patch_matplotlib_compat(code)
        assert "plt.gca().set_xticklabels" in patched
        assert "plt.set_xticklabels(" not in patched

    def test_set_yticklabels_ported(self):
        code = "plt.set_yticklabels(['a', 'b'])"
        patched = _patch_matplotlib_compat(code)
        assert "plt.gca().set_yticklabels" in patched

    def test_set_xlabel_ported(self):
        code = "plt.set_xlabel('x')"
        patched = _patch_matplotlib_compat(code)
        assert "plt.gca().set_xlabel" in patched

    def test_set_title_ported(self):
        code = "plt.set_title('My Plot')"
        patched = _patch_matplotlib_compat(code)
        assert "plt.gca().set_title" in patched

    def test_unchanged_when_no_plt(self):
        code = "import os\nprint('hello')\nx = 5 + 3"
        assert _patch_matplotlib_compat(code) == code

    def test_unchanged_when_method_already_correct(self):
        code = "ax.set_xticklabels(['a'])"
        assert _patch_matplotlib_compat(code) == code

    def test_multiple_patches(self):
        code = (
            "plt.set_xticklabels(['a'])\n"
            "plt.set_yticklabels(['b'])\n"
            "plt.set_title('T')\n"
        )
        patched = _patch_matplotlib_compat(code)
        assert "plt.gca().set_xticklabels" in patched
        assert "plt.gca().set_yticklabels" in patched
        assert "plt.gca().set_title" in patched
        # No bare `plt.set_*` left
        assert "plt.set_xticklabels" not in patched
        assert "plt.set_yticklabels" not in patched
        assert "plt.set_title" not in patched


class TestUnwrapSolutionForInsertGranite:
    """Prio 2.2: Handle Granite-style code emission."""

    def test_unwrap_when_names_match(self):
        setup = '''
exec_context = """
def helper(x):
    [insert]
"""
'''
        solution = '''def helper(x):
    return x * 2
'''
        result = _unwrap_solution_for_insert(solution, setup)
        # Function name matches → body unwrapped, indented 4 spaces
        assert "return x * 2" in result
        assert "def helper" not in result

    def test_wrap_when_names_differ(self):
        """Prio 2.2: Granite sometimes writes helper functions with
        different names. We wrap in a synthetic function with the
        expected name.
        """
        setup = '''
exec_context = """
def expected_func(x):
    [insert]
"""
'''
        solution = '''def different_name(x):
    return x * 2
'''
        result = _unwrap_solution_for_insert(solution, setup)
        assert "def expected_func" in result
        assert "return different_name(*args, **kwargs)" in result

    def test_handle_multiple_insert_markers(self):
        """Prio 2.2: DS1000 problems with helper functions sometimes
        have nested insertion points.
        """
        setup = '''
exec_context = """
def outer(x):
    [insert]
    y = 2
    [insert]
"""
'''
        solution = '''def outer(x):
    return x
'''
        result = _unwrap_solution_for_insert(solution, setup)
        # Should use the innermost [insert] (last one before the
        # final block header before [insert])
        assert "return x" in result

    def test_skip_comments_to_find_def(self):
        """Prio 2.2: Granite emits docstrings/comments before the def.
        We skip them to find the actual def line.
        """
        setup = '''
exec_context = """
def helper(x):
    [insert]
"""
'''
        solution = '''"""Module docstring."""
# This is a comment

def helper(x):
    return x * 2
'''
        result = _unwrap_solution_for_insert(solution, setup)
        # Function name matches → body unwrapped (docstring+comment skipped)
        assert "return x * 2" in result
        # The def line itself is removed
        assert "def helper" not in result

    def test_no_def_in_solution_creates_synthetic(self):
        """Prio 2.2: Granite sometimes emits bare statements.
        We create a synthetic function with the expected name.
        """
        setup = '''
exec_context = """
def expected_func(x):
    [insert]
"""
'''
        solution = "return x * 2"
        result = _unwrap_solution_for_insert(solution, setup)
        assert "def expected_func" in result
        assert "pass" in result

    def test_no_insert_marker_returns_solution_unchanged(self):
        setup = '''
exec_context = """
def helper(x):
    pass
"""
'''
        solution = "return 5"
        # No [insert] in exec_context → return unchanged
        assert _unwrap_solution_for_insert(solution, setup) == "return 5"

    def test_no_exec_context_returns_solution_unchanged(self):
        setup = "# no exec_context here"
        solution = "def helper(): return 1"
        assert _unwrap_solution_for_insert(solution, setup) == solution


class TestExtractCodeGraniteFallbacks:
    """Prio 2.3: Handle Granite's bare-statement and alt-block outputs."""

    def test_standard_markdown_block(self):
        text = "Some prose\n```python\ndef foo():\n    return 1\n```\nMore prose"
        result = extract_code(text)
        assert "def foo" in result
        assert "return 1" in result

    def test_unlabelled_block(self):
        """Granite sometimes omits the language tag."""
        text = "```\nx = 5\n```"
        result = extract_code(text)
        assert "x = 5" in result

    def test_three_or_more_backticks(self):
        text = "````python\ndef foo():\n    return 1\n````"
        result = extract_code(text)
        assert "def foo" in result

    def test_bare_statements_granite_style(self):
        """Prio 2.3: Granite emits bare statements with no def/class."""
        text = "plt.plot([1, 2, 3])\nplt.show()"
        result = extract_code(text)
        assert "plt.plot" in result
        assert "plt.show" in result

    def test_no_def_with_bare_return(self):
        """Granite sometimes returns just the return value."""
        text = "return x * 2"
        result = extract_code(text)
        # Should be captured (bare statement detection)
        assert "return x * 2" in result

    def test_no_code_at_all(self):
        text = "I cannot help with that request."
        result = extract_code(text)
        # Returns empty when no code is detected
        assert result == ""

    def test_structured_json_uses_code_field(self):
        text = '{"code": "def foo():\\n    return 1"}'
        result = extract_code(text, structured=True)
        assert "def foo" in result
        assert "return 1" in result

    def test_structured_json_falls_back_on_bad_json(self):
        text = '```python\ndef foo():\n    return 1\n```'
        result = extract_code(text, structured=True)
        # Should still extract via regex even though structured failed
        assert "def foo" in result

    def test_last_code_block_wins(self):
        """When multiple code blocks are present, take the LAST one."""
        text = (
            "First:\n```python\nx = 1\n```\n"
            "Second:\n```python\ny = 2\n```"
        )
        result = extract_code(text)
        assert "y = 2" in result
        assert "x = 1" not in result


class TestTruthfulQATaskSwitch:
    """Prio 2.1: truthfulqa_mc1 (loglikelihood) → truthfulqa_gen (generate_until)."""

    def test_truthfulqa_gen_in_registry(self):
        """truthfulqa_gen should be the default task name (chat-compatible)."""
        from run_benchmarks_v13 import LMEVAL_BENCHMARKS
        truthfulqa = next(b for b in LMEVAL_BENCHMARKS if b["name"] == "TruthfulQA")
        assert truthfulqa["task"] == "truthfulqa_gen"

    def test_truthfulqa_gen_alias_in_consolidation(self):
        """consolidate_results_v13 must handle truthfulqa_gen alias."""
        import consolidate_results_v13
        import inspect
        source = inspect.getsource(consolidate_results_v13)
        assert '"truthfulqa_gen"' in source
        assert '"truthfulqa_mc2"' in source
