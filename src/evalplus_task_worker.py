"""Evaluate one EvalPlus task in a standalone subprocess.

The parent evaluator uses ordinary subprocesses instead of calling EvalPlus'
own multiprocessing API from a thread. This avoids a Windows deadlock while
keeping the untrusted test execution in EvalPlus' child process.
"""

from __future__ import annotations

import json
import sys

from evalplus.evaluate import check_correctness

if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(0)

import evalplus_subset_eval  # noqa: F401 - applies Windows EvalPlus shims


def _jsonable_details(details: object) -> object:
    return details.tolist() if hasattr(details, "tolist") else details


def main() -> None:
    payload = json.load(sys.stdin)
    result = check_correctness(
        payload["dataset"],
        payload["completion_id"],
        payload["problem"],
        payload["solution"],
        payload["expected"],
        base_only=False,
        fast_check=True,
        identifier=payload["identifier"],
    )
    base_stat, base_details = result["base"]
    plus_stat, plus_details = result["plus"]
    json.dump(
        {
            "completion_id": payload["completion_id"],
            "solution": payload["solution"],
            "base": [base_stat, _jsonable_details(base_details)],
            "plus": [plus_stat, _jsonable_details(plus_details)],
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
