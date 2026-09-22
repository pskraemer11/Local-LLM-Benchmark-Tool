"""Create an evidence-preserving quality review from task result CSV files.

The report separates score, empty output, and harness/provider failures.  This
is important for local-model comparisons: a zero caused by a failed sandbox or
an invalid response must not be presented as a model-quality score.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TaskRow:
    """Normalized fields needed for the quality review."""

    model: str
    benchmark: str
    timestamp: str
    task_index: str
    score: float | None
    score_detail: str
    error_type: str
    output_status: str
    latency_s: float | None
    tokens_per_sec: float | None
    source_file: str


@dataclass
class ModelSummary:
    """Aggregated quality and execution outcomes for one model."""

    model: str
    total_tasks: int
    scored_tasks: int
    mean_score_all: float | None
    mean_score_evaluable: float | None
    infrastructure_errors: int
    empty_outputs: int
    nonempty_outputs: int
    mean_latency_s: float | None
    mean_tokens_per_sec: float | None
    status_counts: Counter[str]
    error_counts: Counter[str]


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def read_task_rows(results_dir: Path, *, models: set[str] | None = None, since: str | None = None) -> list[TaskRow]:
    """Read task CSVs, preserving source file and malformed-value gaps."""
    rows: list[TaskRow] = []
    for path in sorted(results_dir.rglob("tasks_*.csv")):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for raw in csv.DictReader(handle, delimiter=";"):
                    model = _text(raw.get("model"))
                    timestamp = _text(raw.get("timestamp"))
                    if not model or (models is not None and model not in models):
                        continue
                    if since and timestamp[:10] < since:
                        continue
                    rows.append(
                        TaskRow(
                            model=model,
                            benchmark=_text(raw.get("benchmark")) or "unknown",
                            timestamp=timestamp,
                            task_index=_text(raw.get("task_index")) or "unknown",
                            score=_float(raw.get("score")),
                            score_detail=_text(raw.get("score_detail")),
                            error_type=_text(raw.get("error_type")),
                            output_status=_text(raw.get("output_status")) or "unknown",
                            latency_s=_float(raw.get("latency_s")),
                            tokens_per_sec=_float(raw.get("tokens_per_sec")),
                            source_file=str(path),
                        )
                    )
        except (OSError, UnicodeError, csv.Error):
            continue
    return rows


def latest_task_rows(rows: list[TaskRow]) -> list[TaskRow]:
    """Keep the latest observed result for each model/benchmark/task index."""
    latest: dict[tuple[str, str, str], TaskRow] = {}
    for row in rows:
        key = (row.model, row.benchmark, row.task_index)
        previous = latest.get(key)
        if previous is None or row.timestamp >= previous.timestamp:
            latest[key] = row
    return sorted(latest.values(), key=lambda row: (row.model.casefold(), row.benchmark.casefold(), row.task_index))


def _is_infrastructure_error(row: TaskRow) -> bool:
    detail = row.score_detail.casefold()
    error_type = row.error_type.casefold()
    return bool(
        error_type
        or "harness error" in detail
        or "provider" in detail
        or "connection" in detail
        or "timeout" in detail
    )


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def summarize(rows: list[TaskRow]) -> list[ModelSummary]:
    """Aggregate rows while keeping evaluability separate from execution health."""
    by_model: dict[str, list[TaskRow]] = defaultdict(list)
    for row in rows:
        by_model[row.model].append(row)
    summaries: list[ModelSummary] = []
    for model, model_rows in sorted(by_model.items(), key=lambda item: item[0].casefold()):
        infrastructure = [row for row in model_rows if _is_infrastructure_error(row)]
        empty = [row for row in model_rows if row.output_status.casefold() in {"empty", "blank"}]
        evaluable = [row for row in model_rows if not _is_infrastructure_error(row)]
        scores_all = [row.score for row in model_rows if row.score is not None]
        scores_evaluable = [row.score for row in evaluable if row.score is not None]
        latencies = [row.latency_s for row in model_rows if row.latency_s is not None]
        speeds = [row.tokens_per_sec for row in model_rows if row.tokens_per_sec is not None]
        summaries.append(
            ModelSummary(
                model=model,
                total_tasks=len(model_rows),
                scored_tasks=len(scores_all),
                mean_score_all=_mean(scores_all),
                mean_score_evaluable=_mean(scores_evaluable),
                infrastructure_errors=len(infrastructure),
                empty_outputs=len(empty),
                nonempty_outputs=len(model_rows) - len(empty),
                mean_latency_s=_mean(latencies),
                mean_tokens_per_sec=_mean(speeds),
                status_counts=Counter(row.output_status for row in model_rows),
                error_counts=Counter(row.error_type for row in model_rows if row.error_type),
            )
        )
    return summaries


def _number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def render_markdown(rows: list[TaskRow], summaries: list[ModelSummary], *, source: str) -> str:
    """Render a concise report with explicit limitations."""
    benchmarks = sorted({row.benchmark for row in rows})
    lines = [
        "# Local-model quality review",
        "",
        f"Source: `{source}`  ",
        f"Models: {len(summaries)}  ",
        f"Latest deduplicated tasks: {len(rows)}  ",
        f"Benchmarks: {', '.join(benchmarks) if benchmarks else 'none'}",
        "",
        "The score is reported twice: `all` includes every recorded score, while `evaluable` excludes rows classified as harness/provider/transport failures. Empty outputs remain visible and are not silently removed.",
        "",
        "| Model | Tasks | Scored | Score all | Score evaluable | Infra errors | Empty | Mean latency (s) | Mean tok/s |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summaries:
        lines.append(
            f"| `{item.model}` | {item.total_tasks} | {item.scored_tasks} | {_number(item.mean_score_all)} | {_number(item.mean_score_evaluable)} | {item.infrastructure_errors} | {item.empty_outputs} | {_number(item.mean_latency_s)} | {_number(item.mean_tokens_per_sec)} |"
        )
    lines.extend(["", "## Outcome classifications", ""])
    for item in summaries:
        statuses = ", ".join(f"{key or 'no-status'}={value}" for key, value in sorted(item.status_counts.items()))
        errors = ", ".join(f"{key}={value}" for key, value in sorted(item.error_counts.items())) or "none"
        lines.append(f"- `{item.model}`: statuses {statuses}; infrastructure errors {errors}.")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This is a diagnostic quality review, not a replacement for a controlled multi-sample benchmark. A model with infrastructure errors or empty outputs requires a harness/template/backend fix before its score can be compared as model quality. Repeated runs are reduced to the latest row per model, benchmark, and task index.",
            "",
        ]
    )
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=Path("ergebnisse"))
    parser.add_argument("--models", nargs="*", default=None)
    parser.add_argument("--since", default=None, help="ISO date YYYY-MM-DD; filter by result timestamp")
    parser.add_argument("--output", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    model_filter = set(args.models) if args.models else None
    raw_rows = read_task_rows(args.results_dir, models=model_filter, since=args.since)
    rows = latest_task_rows(raw_rows)
    summaries = summarize(rows)
    report = render_markdown(rows, summaries, source=str(args.results_dir))
    output = args.output or args.results_dir / f"quality-review-{datetime.now():%Y%m%d-%H%M%S}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(output)
    print(f"models={len(summaries)} tasks={len(rows)} raw_rows={len(raw_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
