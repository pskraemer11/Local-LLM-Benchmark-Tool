import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest
from benchmark_config import CAT_WEIGHTS, OVERALL_WEIGHTS
from consolidate_results_v13 import compute_category_scores, _percentile

class TestComputeCategoryScores:
    def test_all_present(self):
        scores = {"DS1000": 0.5, "CoderEval": 0.8,
                  "HumanEval+_plus": 1.0, "MBPP+_plus": 0.6}
        cats = compute_category_scores(scores)
        assert cats["coding"] == pytest.approx(0.725)
        assert cats["knowledge"] is None
        assert cats["math"] is None
        assert cats["agentic"] is None
        assert cats["overall"] == pytest.approx(0.725)

    def test_fully_loaded(self):
        scores = {"DS1000": 0.5, "CoderEval": 0.8, "HumanEval+_plus": 1.0, "MBPP+_plus": 0.6,
                  "ARC-Challenge": 0.5, "HellaSwag": 0.5, "TruthfulQA": 0.5, "MMLU-Pro": 0.5,
                  "MATH-500": 0.5, "Agentic": 0.5}
        cats = compute_category_scores(scores)
        assert cats["coding"] == pytest.approx(0.725)
        assert cats["knowledge"] == 0.5
        assert cats["math"] == 0.5
        assert cats["agentic"] == 0.5
        expected = (0.725*0.35 + 0.5*0.25 + 0.5*0.25 + 0.5*0.15)
        assert cats["overall"] == pytest.approx(expected)

    def test_partial_coding(self):
        scores = {"DS1000": 0.5}
        cats = compute_category_scores(scores)
        assert cats["coding"] == 0.5
        assert cats["knowledge"] is None

    def test_empty_scores(self):
        cats = compute_category_scores({})
        assert all(v is None for k, v in cats.items() if k != "overall")
        assert cats["overall"] is None

    def test_zero_scores(self):
        scores = {"DS1000": 0.0, "CoderEval": 0.0,
                  "HumanEval+_plus": 0.0, "MBPP+_plus": 0.0}
        cats = compute_category_scores(scores)
        assert cats["coding"] == 0.0
        assert cats["overall"] == 0.0


class TestPercentile:
    def test_median(self):
        assert _percentile([1, 2, 3, 4, 5], 50) == 3.0

    def test_p90(self):
        assert _percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 90) == pytest.approx(9.1)

    def test_single_value(self):
        assert _percentile([42], 90) == 42

    def test_two_values(self):
        assert _percentile([0, 100], 50) == 50.0
