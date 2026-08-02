import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from tools.parallel_ab import (
    build_body,
    build_prompts,
    format_report,
    lock_held_by_live_process,
    mode_sequence,
)


class TestModeSequence:
    def test_abba_order_single_rep(self):
        assert mode_sequence([1, 2, 4], 1) == [1, 2, 4]

    def test_abba_order_two_reps(self):
        assert mode_sequence([1, 2, 4], 2) == [1, 2, 4, 4, 2, 1]

    def test_abba_order_three_reps(self):
        assert mode_sequence([1, 4], 3) == [1, 4, 4, 1, 1, 4]


class TestBuildBody:
    def test_no_reasoning_params(self):
        body = build_body("openai/gpt-oss-20b", "prompt", 2048)
        assert "reasoning_effort" not in body
        assert "max_thinking_tokens" not in body

    def test_non_gptoss_has_no_reasoning_params(self):
        body = build_body("deepseek-r1-distill-qwen-14b", "prompt", 2048)
        assert "reasoning_effort" not in body
        assert "max_thinking_tokens" not in body

    def test_stream_flag_and_params(self):
        body = build_body("llama-3", "p", 64)
        assert body["stream"] is True
        assert body["temperature"] == 0.0
        assert body["max_tokens"] == 64
        assert body["messages"][0]["role"] == "user"


class TestBuildPrompts:
    def test_returns_expected_sample_size(self):
        prompts = build_prompts(5, "ds1000")
        assert len(prompts) == 5
        assert all(p.startswith("Complete the following Python code.") for p in prompts)

    def test_seeded_sampling_is_reproducible(self):
        a = build_prompts(5, "ds1000")
        b = build_prompts(5, "ds1000")
        assert a == b

    def test_explicit_seed_reproducible(self):
        a = build_prompts(5, "ds1000", seed=2026)
        b = build_prompts(5, "ds1000", seed=2026)
        assert a == b

    def test_explicit_seed_matches_default(self):
        default = build_prompts(5, "ds1000")
        seed42 = build_prompts(5, "ds1000", seed=42)
        assert default == seed42


class TestLock:
    def test_no_lock_file_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.parallel_ab.LOCK_PATH",
                            os.path.join(str(tmp_path), ".benchmark.lock"))
        assert lock_held_by_live_process() is None

    def test_live_pid_returns_pid(self, tmp_path, monkeypatch):
        lock = os.path.join(str(tmp_path), ".benchmark.lock")
        monkeypatch.setattr("tools.parallel_ab.LOCK_PATH", lock)
        with open(lock, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "started": "x"}, f)
        assert lock_held_by_live_process() == os.getpid()

    def test_dead_pid_returns_none(self, tmp_path, monkeypatch):
        lock = os.path.join(str(tmp_path), ".benchmark.lock")
        monkeypatch.setattr("tools.parallel_ab.LOCK_PATH", lock)
        with open(lock, "w", encoding="utf-8") as f:
            json.dump({"pid": 2147483647, "started": "x"}, f)
        assert lock_held_by_live_process() is None


class TestFormatReport:
    def test_table_contains_slots_and_ratio(self):
        results = {
            1: [{"wall_s": 100.0, "tok_s": 10.0, "mean_latency_s": 9.0,
                 "median_latency_s": 8.0, "ram_max_gb": 10.0}],
            2: [{"wall_s": 60.0, "tok_s": 16.0, "mean_latency_s": 12.0,
                 "median_latency_s": 11.0, "ram_max_gb": 12.0}],
        }
        report = format_report("m", "ds1000", 20, [1, 2], 1, results)
        assert "| 1 | 100.0 | 10.0 | 1.00x |" in report
        assert "| 2 | 60.0 | 16.0 | 0.60x |" in report
        assert "ABBA" in report
