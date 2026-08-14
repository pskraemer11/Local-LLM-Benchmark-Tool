"""Subset-Evaluation für EvalPlus (HumanEval+/MBPP+).

evalplus' ``evaluate()`` (CLI ``python -m evalplus.evaluate``) lädt intern immer
das VOLLE Dataset (164/378 Tasks) und assertiert, dass jede Task des Datasets
in den Samples vorkommt (``assert len(completion_id) == len(problems)``). Bei
einer Stichprobe (sample_size < voller Dataset-Größe) schlägt das fehl mit
``AssertionError: Missing problems in samples``.

Dieses Modul repliziert die Evaluierungslogik (ground truth + check_correctness
+ pass@1), wendet sie aber NUR auf die in der Samples-Datei vorhandenen
Task-IDs an. Output-Format bleibt identisch zur evalplus-CLI (``humaneval+
(base + extra tests)`` + ``pass@1``), sodass der bestehende Score-Regex in
run_benchmarks.py unverändert weiter funktioniert.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from typing import Any

import numpy as np

# evalplus' query_maximum_memory_bytes() defaults to 4GB, so reliability_guard
# calls ``import resource`` (UNIX-only) in the sandboxed child process. On
# Windows that ModuleNotFoundError crashes every check_correctness() call.
# Setting it to -1 makes query_maximum_memory_bytes() return None and skips
# the resource import entirely (evalplus/eval/utils.py:114ff).
os.environ.setdefault("EVALPLUS_MAX_MEMORY_BYTES", "-1")

# evalplus' time_limit (evalplus/eval/utils.py) calls
# ``signal.setitimer``/``signal.signal(SIGALRM, ...)`` - both UNIX-only. The
# sandbox runs check_correctness() in a spawned multiprocessing child, which
# re-imports this module (__main__) on Windows, so this module-level patch is
# active inside the sandbox child as well. Without it, every input test raises
# AttributeError and everything is marked "fail". The outer untrusted_check
# timeout (p.join + terminate) remains as safety net.
if os.name == "nt":
    import evalplus.eval.utils as _evalplus_eval_utils

    class _WindowsSignalTimerShim:
        """No-op stand-in for the signal module attribute lookups time_limit uses."""

        ITIMER_REAL: int = 0
        SIGALRM: int = 14

        def setitimer(self, which: int, seconds: int) -> int:
            return 0

        def signal(self, signum: int, handler: object) -> None:
            return None

    _evalplus_eval_utils.signal = _WindowsSignalTimerShim()  # type: ignore[attr-defined]

from evalplus.data.mbpp import mbpp_serialize_inputs
from evalplus.data.utils import load_solutions
from evalplus.eval import PASS, estimate_pass_at_k
from evalplus.eval._special_oracle import MBPP_OUTPUT_NOT_NONE_TASKS
from evalplus.evaluate import check_correctness, get_groundtruth


def _load_problems(dataset: str) -> dict[str, dict[str, Any]]:
    """Lade das volle Dataset und liefere es als dict {task_id: problem}."""
    from evalplus.data import get_human_eval_plus, get_mbpp_plus

    fn = get_human_eval_plus if dataset == "humaneval" else get_mbpp_plus
    return fn()


def _load_problem_hashes(dataset: str) -> tuple[str, list[str]]:
    """Liefere (dataset_hash, tasks_only_output_not_none)."""
    from evalplus.data import get_human_eval_plus_hash, get_mbpp_plus_hash

    if dataset == "humaneval":
        return get_human_eval_plus_hash(), []
    return get_mbpp_plus_hash(), list(MBPP_OUTPUT_NOT_NONE_TASKS)


def _subset_cache_hash(base_hash: str, task_ids: list[str]) -> str:
    """Cache-Schlüssel für die Ground-Truth einer Task-Stichprobe.

    evalplus' get_groundtruth cached unter ``{hashcode}.pkl`` (appdirs
    user_cache_dir("evalplus")). Ein Stichproben-Lauf darf den vollen
    Dataset-Cache nicht mit unvollständigen Ground-Truth-Daten überschreiben -
    daher kombinieren wir den vollen Hash mit den selektierten Task-IDs.
    """
    import hashlib

    digest = hashlib.sha256(",".join(sorted(task_ids)).encode("utf-8")).hexdigest()[:12]
    return f"{base_hash}_subset_{digest}"


def _evaluate_subset(
    dataset: str,
    samples_path: str,
    problems: dict[str, dict[str, Any]],
    dataset_hash: str,
    tasks_only_output_not_none: list[str],
    parallel: int = 1,
) -> float | None:
    """Bewerte nur die Tasks, die in der Samples-Datei vorkommen.

    Mirrors evalplus.evaluate() aber beschränkt auf die gesampelten Tasks.
    Gibt pass@1 (0-1) zurück oder None, falls keine Samples evaluiert werden.
    """
    # Ground truth NUR für die vorhandenen Tasks berechnen (get_groundtruth
    # iteriert über das übergebene problems-Dict). Der Cache-Schlüssel wird aus
    # dem vollen dataset_hash UND den selektierten Task-IDs abgeleitet, damit
    # ein Stichproben-Lauf den vollen Dataset-Cache NICHT mit unvollständigen
    # Ground-Truth-Daten überschreibt (ein späterer voller Lauf würde sonst den
    # Teil-Cache laden).
    samples = list(load_solutions(samples_path))
    present_ids = {s["task_id"] for s in samples}
    subset_problems = {tid: problems[tid] for tid in present_ids if tid in problems}
    if not subset_problems:
        return None

    subset_hash = _subset_cache_hash(dataset_hash, sorted(subset_problems))
    expected_output = get_groundtruth(
        subset_problems, subset_hash, tasks_only_output_not_none
    )

    eval_results: dict[str, list[dict[str, Any]]] = defaultdict(list)
    completion_id: Counter[str] = Counter()
    for sample in samples:
        task_id = sample["task_id"]
        if task_id not in subset_problems:
            continue
        solution = (
            sample["solution"]
            if "solution" in sample
            else problems[task_id]["prompt"] + sample["completion"]
        )
        res = check_correctness(
            dataset,
            completion_id[task_id],
            subset_problems[task_id],
            solution,
            expected_output[task_id],
            base_only=False,
            fast_check=True,
            identifier=sample["_identifier"],
        )
        eval_results[task_id].append(res)
        completion_id[task_id] += 1

    if not eval_results:
        return None

    # Resultat-Format kompatibel zu evalplus.evaluate() aufbereiten
    results: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task_id, task_results in eval_results.items():
        task_results.sort(key=lambda x: x["completion_id"])
        for res in task_results:
            base_stat, base_details = res["base"]
            plus_stat, plus_details = res["plus"]
            base_fail_tests = _failed_tests(base_stat, base_details, subset_problems[task_id]["base_input"])
            plus_fail_tests = _failed_tests(plus_stat, plus_details, subset_problems[task_id]["plus_input"])
            if dataset == "mbpp":
                base_fail_tests = mbpp_serialize_inputs(task_id, base_fail_tests)
                plus_fail_tests = mbpp_serialize_inputs(task_id, plus_fail_tests)
            results[task_id].append(
                {
                    "task_id": task_id,
                    "solution": res["solution"],
                    "base_status": base_stat,
                    "plus_status": plus_stat,
                    "base_fail_tests": base_fail_tests,
                    "plus_fail_tests": plus_fail_tests,
                }
            )

    total = np.array([len(r) for r in results.values()])
    new_correct = np.array(
        [
            sum(r["base_status"] == r["plus_status"] == PASS for r in res)
            for res in results.values()
        ]
    )
    if (total >= 1).all():
        pass_at_1 = estimate_pass_at_k(total, new_correct, 1).mean()
        return float(pass_at_1)
    return None


def _failed_tests(stat: str, details: Any, inputs: list[Any]) -> list[Any]:
    """Extrahiere die fehlgeschlagenen Tests im evalplus-Format."""
    if stat == PASS or not details:
        return []
    return [inputs[len(details) - 1]]


def main() -> None:
    parser = argparse.ArgumentParser(description="Subset-Evaluation für EvalPlus.")
    parser.add_argument("--dataset", required=True, choices=["humaneval", "mbpp"])
    parser.add_argument("--samples", required=True, help="Pfad zur samples.jsonl")
    parser.add_argument("--parallel", type=int, default=1)
    args = parser.parse_args()

    dataset_hash, tasks_only = _load_problem_hashes(args.dataset)
    problems = _load_problems(args.dataset)
    score = _evaluate_subset(
        args.dataset,
        args.samples,
        problems,
        dataset_hash,
        tasks_only,
        parallel=args.parallel,
    )
    if score is None:
        print(f"{args.dataset}+ (base + extra tests)")
        print("pass@1:\t0.000")
        sys.exit(0)
    print(f"{args.dataset}+ (base + extra tests)")
    print(f"pass@1:\t{score:.3f}")
    # evalplus-CLI schreibt zusätzlich die eval_results.json; hier optional.
    result_path = args.samples.replace(".jsonl", "_eval_results.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump({"score": score, "dataset": args.dataset}, f)


if __name__ == "__main__":
    main()