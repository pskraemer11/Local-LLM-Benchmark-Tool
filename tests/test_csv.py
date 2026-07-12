import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest
from consolidate_results_v13 import read_custom_csv, _auto_delimiter

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "test_tasks.csv")


class TestReadCustomCSV:
    def test_returns_scores(self):
        score, tps, latency, metrics = read_custom_csv(FIXTURE)
        assert score is not None
        assert score == pytest.approx(2.0 / 3.0)  # 1+0+1 / 3

    def test_tokens_per_sec(self):
        score, tps, latency, metrics = read_custom_csv(FIXTURE)
        assert tps is not None
        assert tps == pytest.approx((9.6 + 9.9 + 10.5) / 3.0)

    def test_total_latency(self):
        score, tps, latency, metrics = read_custom_csv(FIXTURE)
        assert latency is not None
        assert latency == pytest.approx(5.2 + 8.1 + 3.8)

    def test_metrics_median(self):
        score, tps, latency, metrics = read_custom_csv(FIXTURE)
        assert metrics["CPU_avg"] == pytest.approx((45 + 52 + 38) / 3.0)
        assert metrics["CPU_med"] == pytest.approx(45.0)
        assert metrics["GPU_max"] == pytest.approx(72.0)
        assert metrics["GPU_p90"] is not None

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            read_custom_csv("nonexistent.csv")


class TestAutoDelimiter:
    def test_semicolon(self):
        assert _auto_delimiter(FIXTURE) == ";"
