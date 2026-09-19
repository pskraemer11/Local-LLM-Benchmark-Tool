"""Create one-time benchmark input manifests.

Usage: python src/prepare_task_manifests.py --input DS1000=path.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from task_manifest import build_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Create checked benchmark input manifests")
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        metavar="BENCHMARK=PATH",
        help="JSONL input; may be supplied more than once",
    )
    parser.add_argument("--output", type=Path, default=Path("ergebnisse/task_manifest.json"))
    parser.add_argument(
        "--allow-warnings",
        action="store_true",
        help="write the manifest successfully even when obvious injection warnings exist",
    )
    args = parser.parse_args()

    manifests = []
    for specification in args.input:
        try:
            benchmark, raw_path = specification.split("=", 1)
        except ValueError as exc:
            parser.error(f"invalid --input {specification!r}; expected BENCHMARK=PATH")
            raise AssertionError from exc
        source = Path(raw_path).resolve()
        if not benchmark or not source.is_file():
            parser.error(f"input file not found or benchmark empty: {specification}")
        manifests.append(build_manifest(benchmark, source))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format": "benchmark-task-manifests-v1",
        "manifests": manifests,
    }
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    warning_count = sum(len(item["prompt_injection_warnings"]) for item in manifests)
    print(f"Wrote {args.output} ({len(manifests)} datasets, {warning_count} warnings)")
    return 0 if warning_count == 0 or args.allow_warnings else 2


if __name__ == "__main__":
    raise SystemExit(main())
