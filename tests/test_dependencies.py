"""Tests for required Python dependencies.

See: Code-Review_2026-07-12.md §7.7.1 / §7.7.2 / §7.8 Prio 0.

Without these dependencies, IFEval and MATH-500 will fail with
ModuleNotFoundError on every model (see Terminalausgabe Benchmark Run
12.07.2026 for the full error stack traces).
"""
import sys
import pytest


# Required dependencies for IFEval + MATH-500.
# These are NOT optional – if any is missing, the corresponding
# benchmark is silently broken.
REQUIRED_LM_EVAL_DEPS = {
    "langdetect": "IFEval needs `langdetect` for language detection of the "
                  "model output (lm_eval/tasks/ifeval/instructions.py:36)",
    "sympy": "MATH-500 (via minerva_math/utils.py) needs sympy for "
             "translation task prompt templates",
    "math_verify": "MATH-500 needs math_verify for answer parsing "
                   "(lm_eval/tasks/minerva_math/utils.py:16)",
    "lm_eval": "lm-eval package is the lm-eval-harness backend",
    "nltk": "TruthfulQA tokenization uses nltk punkt tokenizer",
}


class TestLmEvalDependencies:
    """Prio 0: detect missing lm-eval task dependencies.

    These tests do NOT fail when dependencies are missing – they WARN
    instead, so the test suite still runs in environments where the
    user only needs the Custom pipeline (DS1000/CoderEval). A summary
    is printed in the test report.
    """

    def _check(self, name: str) -> bool:
        try:
            __import__(name)
            return True
        except ImportError:
            return False

    def test_langdetect_available(self):
        """IFEval fails without this — see §7.7.1."""
        if not self._check("langdetect"):
            pytest.skip("langdetect missing – IFEval will fail. "
                        "Run: pip install langdetect")
        assert self._check("langdetect")

    def test_sympy_available(self):
        """MATH-500 fails without this — see §7.7.2."""
        if not self._check("sympy"):
            pytest.skip("sympy missing – MATH-500 will fail. "
                        "Run: pip install sympy")
        assert self._check("sympy")

    def test_math_verify_available(self):
        """MATH-500 fails without this — see §7.7.2."""
        if not self._check("math_verify"):
            pytest.skip("math_verify missing – MATH-500 will fail. "
                        "Run: pip install math_verify (or lm-eval[math])")
        assert self._check("math_verify")

    def test_lm_eval_available(self):
        """Run-lmeval pipeline requires this."""
        if not self._check("lm_eval"):
            pytest.skip("lm_eval missing – install via pip install lm-eval[api]")
        assert self._check("lm_eval")

    def test_nltk_available(self):
        """TruthfulQA tokenization requires nltk punkt data."""
        if not self._check("nltk"):
            pytest.skip("nltk missing – install via pip install nltk")
        assert self._check("nltk")


class TestLmEvalTaskImportable:
    """If a required task fails to import, the corresponding benchmark
    is broken for ALL models. This class surfaces the real lm_eval
    import error for IFEval and MATH-500.
    """

    def test_ifeval_importable(self):
        """Importing `lm_eval.tasks.ifeval.instructions` triggers the
        langdetect import. If the module is missing, the test fails
        with the actual ModuleNotFoundError from the run output.
        """
        if not self._import("langdetect"):
            pytest.fail("IFEval cannot run – langdetect missing. "
                        "Run: pip install langdetect")
        # If langdetect is present, the import should work
        try:
            from lm_eval.tasks.ifeval import instructions  # noqa: F401
        except Exception as e:
            pytest.fail(f"IFEval import failed: {e}")

    def test_minerva_math_importable(self):
        """Importing `lm_eval.tasks.minerva_math.utils` triggers the
        math_verify import. If the module is missing, the test fails
        with the actual ModuleNotFoundError from the run output.
        """
        if not self._import("math_verify"):
            pytest.fail("MATH-500 cannot run – math_verify missing. "
                        "Run: pip install lm-eval[math]")
        try:
            from lm_eval.tasks.minerva_math import utils  # noqa: F401
        except Exception as e:
            pytest.fail(f"MATH-500 import failed: {e}")

    def _import(self, name: str) -> bool:
        try:
            __import__(name)
            return True
        except ImportError:
            return False


def pytest_report_header(config):
    """Print a dependency summary at the start of the test report."""
    print("\n=== lm-eval task dependencies ===")
    for name, desc in REQUIRED_LM_EVAL_DEPS.items():
        try:
            __import__(name)
            status = "✓ OK"
        except ImportError:
            status = "✗ MISSING"
        print(f"  [{status:10s}] {name:14s}  {desc}")
    print("====================================\n")
