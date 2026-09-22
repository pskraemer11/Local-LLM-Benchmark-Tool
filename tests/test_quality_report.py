from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from tools.quality_report import latest_task_rows, read_task_rows, summarize


def _write(path: Path, content: str) -> None:
    path.write_text(
        "pipeline;model;benchmark;timestamp;task_index;score;score_detail;latency_s;tokens_per_sec;error_type;output_status\n"
        + content,
        encoding="utf-8",
    )


def test_latest_task_rows_and_classification(tmp_path: Path) -> None:
    _write(
        tmp_path / "tasks_a.csv",
        "custom;m1;DS1000;2026-09-21T10-00-00;1;0.0;No code generated;1;2;;empty\n"
        "custom;m1;DS1000;2026-09-22T10-00-00;1;1.0;ok;2;3;;ok\n"
        "custom;m2;DS1000;2026-09-22T10-00-00;1;0.0;Harness error: failed;1;2;harness;bare\n",
    )
    rows = latest_task_rows(read_task_rows(tmp_path))
    summaries = {item.model: item for item in summarize(rows)}
    assert len(rows) == 2
    assert summaries["m1"].mean_score_evaluable == 1.0
    assert summaries["m1"].empty_outputs == 0
    assert summaries["m2"].infrastructure_errors == 1


def test_read_task_rows_filters_model_and_date(tmp_path: Path) -> None:
    _write(tmp_path / "tasks_a.csv", "custom;m1;Math;2026-09-21T10-00-00;1;1;ok;1;2;;ok\n")
    assert read_task_rows(tmp_path, models={"m2"}) == []
    assert len(read_task_rows(tmp_path, since="2026-09-21")) == 1
    assert read_task_rows(tmp_path, since="2026-09-22") == []
