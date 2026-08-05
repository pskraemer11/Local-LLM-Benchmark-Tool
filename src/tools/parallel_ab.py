#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A/B-Messung: sequenziell vs. parallele Slots (ein Modell, einmal geladen).

Sendet DENSELBEN Sample-Satz durch die OpenAI-kompatible API mit K
parallelen Worker-Threads (K = 1, 2, 4, ...) und misst:
  - Wall-Time fuer den gesamten Satz  (die entscheidende Groesse)
  - Aggregat-Tok/s                    (Durchsatz)
  - Mittlere/Median-Per-Sample-Latenz (inkl. Warteschlange bei K > 1)
  - Max. System-RAM waehrend der Messung

Regimes:
  --benchmark ds1000   echte DS1000-Tasks (stream-lastig, lange Generierung)
  --benchmark short    gleiche Prompts, max_tokens=64 (prefill-lastig)

WICHTIG: respektiert den Single-Instance-Lock von run_benchmarks.py.
Ohne --wait-for-lock bricht das Skript ab, wenn ein Launcher laeuft.

Usage:
  python src/tools/parallel_ab.py --model openai/gpt-oss-20b \
      --sample-size 20 --slots 1,2,4 --reps 2 --benchmark ds1000
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import random
import statistics
import sys
import threading
import time
from datetime import datetime
from typing import Any, Optional

import psutil
import requests

SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(SRC_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from custom_benchmark import (API_BASE, load_jsonl, subsample_tasks,
                              _make_datascience_prompt)  # noqa: E402
from model_manager import (has_unloaded_all_models, is_model_ready,
                           load_model_via_lms)  # noqa: E402

LOCK_PATH = os.path.join(PROJECT_ROOT, "ergebnisse", ".benchmark.lock")
DS1000_FILE = os.path.join(PROJECT_ROOT, "tests", "data", "data_science.jsonl")
OUT_DIR = os.path.join(PROJECT_ROOT, "ergebnisse")

MAX_TOKENS_DS1000 = 4096
MAX_TOKENS_SHORT = 64
WARMUP_SAMPLES = 1
REQUEST_TIMEOUT_TOTAL = 900.0
RANDOM_SEED = 42


def build_prompts(sample_size: int, benchmark: str, seed: Optional[int] = None) -> list[str]:
    """Echte DS1000-Prompts (identische Konstruktion wie custom_benchmark.py)."""
    seed = RANDOM_SEED if seed is None else seed
    tasks = load_jsonl(DS1000_FILE)
    random.seed(seed)
    tasks = subsample_tasks(tasks, "data_science", sample_size=sample_size)
    prompts = []
    for task in tasks:
        entry_point = task.get("entry_point", "")
        prompts.append(_make_datascience_prompt(task["prompt"], entry_point))
    return prompts


def build_body(model: str, prompt: str, max_tokens: int) -> dict[str, Any]:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "top_p": 1.0,
        "max_tokens": max_tokens,
        "stream": True,
    }
    return body


def _stream_request(body: dict[str, Any]) -> tuple[float, int, Optional[str]]:
    """Ein Streaming-Request. Returns (latency_s, out_tokens, error)."""
    start = time.time()
    url = f"{API_BASE}/chat/completions"
    headers = {"Content-Type": "application/json"}
    try:
        with requests.post(url, headers=headers, json=body, stream=True,
                           timeout=(30, REQUEST_TIMEOUT_TOTAL)) as resp:
            resp.raise_for_status()
            content_len = 0
            reasoning_len = 0
            usage_completion = 0
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                text = line.strip()
                if text == "data: [DONE]":
                    break
                if text.startswith("data: "):
                    try:
                        chunk = json.loads(text[6:])
                    except json.JSONDecodeError:
                        continue
                    usage = chunk.get("usage") or {}
                    usage_completion = usage.get("completion_tokens", usage_completion)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content_len += len(delta.get("content") or "")
                    reasoning_len += len(delta.get("reasoning") or delta.get("reasoning_content") or "")
        elapsed = time.time() - start
        if usage_completion > 0:
            out_tokens = usage_completion
        else:
            out_tokens = max(1, int((content_len + reasoning_len) / 4))
        return elapsed, out_tokens, None
    except (requests.exceptions.RequestException, OSError, ValueError) as e:
        return time.time() - start, 0, str(e)


def run_mode(prompts: list[str], slots: int, max_tokens: int, model: str) -> dict[str, Any]:
    """Alle Prompts mit `slots` parallelen Workern verarbeiten."""
    ram_samples: list[float] = []
    stop = threading.Event()

    def _ram_watchdog() -> None:
        while not stop.is_set():
            ram_samples.append(psutil.virtual_memory().used / (1024 ** 3))
            time.sleep(1.0)

    watchdog = threading.Thread(target=_ram_watchdog, daemon=True)
    watchdog.start()

    latencies: list[float] = []
    total_out = 0
    errors: list[str] = []
    wall_start = time.time()

    def _one(prompt: str) -> tuple[float, int, Optional[str]]:
        return _stream_request(build_body(model, prompt, max_tokens))

    with concurrent.futures.ThreadPoolExecutor(max_workers=slots) as pool:
        for latency, out_tokens, error in pool.map(_one, prompts):
            latencies.append(latency)
            total_out += out_tokens
            if error:
                errors.append(error)

    wall = time.time() - wall_start
    stop.set()
    watchdog.join(timeout=2)

    if not latencies:
        return {"wall_s": wall, "tok_s": 0.0, "mean_latency_s": 0.0,
                "median_latency_s": 0.0, "total_out": 0, "ram_max_gb": 0.0,
                "errors": errors}

    return {
        "wall_s": wall,
        "tok_s": total_out / wall if wall > 0 else 0.0,
        "mean_latency_s": sum(latencies) / len(latencies),
        "median_latency_s": statistics.median(latencies),
        "total_out": total_out,
        "ram_max_gb": max(ram_samples) if ram_samples else 0.0,
        "errors": errors,
    }


def mode_sequence(slots: list[int], reps: int) -> list[int]:
    """ABBA-Reihenfolge: [1,2,4,4,2,1,1,2,4] fuer reps=3 -> Drift neutralisieren."""
    base = list(slots)
    seq = list(base)
    rev = list(reversed(base))
    for i in range(1, reps):
        seq.extend(rev if i % 2 else base)
    return seq


def lock_held_by_live_process() -> Optional[int]:
    if not os.path.exists(LOCK_PATH):
        return None
    try:
        with open(LOCK_PATH, "r", encoding="utf-8") as f:
            pid = int(json.load(f).get("pid", -1))
    except (OSError, ValueError, KeyError):
        return None
    if pid > 0 and psutil.pid_exists(pid):
        try:
            if psutil.Process(pid).is_running():
                return pid
        except psutil.Error:
            return None
    return None


def format_report(model: str, benchmark: str, sample_size: int, slots: list[int],
                  reps: int, results: dict[int, list[dict[str, Any]]]) -> str:
    lines = [
        "# Parallel-Slots A/B-Messung",
        "",
        f"- Datum: {datetime.now().isoformat(timespec='seconds')}",
        f"- Modell: `{model}`",
        f"- Benchmark-Regime: `{benchmark}` (SampleSize={sample_size})",
        f"- Slots: {slots} | Wiederholungen: {reps} (ABBA-Reihenfolge)",
        "",
        "| Slots | Wall-Time (s) | Aggregat tok/s | Verhaeltnis | Mittlere Latenz (s) | Median (s) | Max RAM (GB) |",
        "|-------|--------------:|---------------:|------------:|---------------------:|-----------:|-------------:|",
    ]
    base_wall: Optional[float] = None
    for slot in slots:
        runs = results[slot]
        wall = min(r["wall_s"] for r in runs)
        tok_s = max(r["tok_s"] for r in runs)
        ratio = wall / base_wall if base_wall else 1.0
        mean_lat = statistics.mean(r["mean_latency_s"] for r in runs)
        med_lat = statistics.median(r["median_latency_s"] for r in runs)
        ram = max(r["ram_max_gb"] for r in runs)
        lines.append(
            f"| {slot} | {wall:.1f} | {tok_s:.1f} | {ratio:.2f}x | "
            f"{mean_lat:.1f} | {med_lat:.1f} | {ram:.1f} |"
        )
        if base_wall is None:
            base_wall = wall
    lines.append("")
    lines.append("Verhaeltnis = Wall-Time relativ zu Slots=1 (kleiner = schneller).")
    lines.append("ABBA-Reihenfolge neutralisiert Thermik-Drift des GPUs.")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="A/B: sequenziell vs. parallele Slots")
    parser.add_argument("--model", default="openai/gpt-oss-20b")
    parser.add_argument("--benchmark", choices=["ds1000", "short"], default="ds1000")
    parser.add_argument("--sample-size", type=int, default=20)
    parser.add_argument("--slots", default="1,2,4")
    parser.add_argument("--reps", type=int, default=2)
    parser.add_argument("--wait-for-lock", action="store_true",
                        help="Auf das Ende eines laufenden Benchmark-Laufs warten")
    parser.add_argument("--dry-run", action="store_true",
                        help="Nur Prompts laden und ausgeben, kein Modell laden")
    parser.add_argument("--seed", type=int, default=None,
                        help="Seed für reproduzierbare Prompt-Auswahl (default: fest 42)")
    args = parser.parse_args()

    slots = [int(s) for s in args.slots.split(",") if s.strip()]
    if not slots or min(slots) < 1:
        parser.error("--slots muss positive Zahlen enthalten (z.B. 1,2,4)")

    if args.dry_run:
        prompts = build_prompts(args.sample_size, args.benchmark, seed=args.seed)
        print(f"[DRY-RUN] {len(prompts)} Prompts, erster Prompt "
              f"({len(prompts[0])} Zeichen):")
        print(prompts[0][:300])
        return

    while True:
        owner = lock_held_by_live_process()
        if owner is None:
            break
        if not args.wait_for_lock:
            print(f"[FATAL] Benchmark-Launcher laeuft (PID {owner}) – "
                  f"Parallel-Messung wuerde das Modell stoeren. "
                  f"--wait-for-lock nutzen oder warten.")
            sys.exit(1)
        print(f"[WAIT] Launcher PID {owner} laeuft noch – pruefe in 60s erneut...")
        time.sleep(60)

    max_tokens = MAX_TOKENS_DS1000 if args.benchmark == "ds1000" else MAX_TOKENS_SHORT
    prompts = build_prompts(args.sample_size, args.benchmark, seed=args.seed)
    print(f"[INFO] {len(prompts)} Prompts, Modell {args.model}, "
          f"max_tokens={max_tokens}, Slots {slots}, {args.reps} Wiederholungen")

    ok_loaded, instance_id = load_model_via_lms(args.model)
    if not ok_loaded:
        print("[FATAL] Modell konnte nicht geladen werden.")
        sys.exit(1)
    is_model_ready()
    model = instance_id or args.model

    seq = mode_sequence(slots, args.reps)
    results: dict[int, list[dict[str, Any]]] = {s: [] for s in slots}
    for i, slot in enumerate(seq, 1):
        if WARMUP_SAMPLES:
            run_mode(prompts[:WARMUP_SAMPLES], 1, max_tokens, model)
        print(f"[RUN {i}/{len(seq)}] Slots={slot} ...", flush=True)
        res = run_mode(prompts, slot, max_tokens, model)
        results[slot].append(res)
        print(f"  wall={res['wall_s']:.1f}s tok/s={res['tok_s']:.1f} "
              f"mean_lat={res['mean_latency_s']:.1f}s "
              f"ram_max={res['ram_max_gb']:.1f}GB"
              + (f" FEHLER={len(res['errors'])}" if res["errors"] else ""),
              flush=True)

    report = format_report(args.model, args.benchmark, args.sample_size, slots,
                           args.reps, results)
    print("\n" + report)
    os.makedirs(OUT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(OUT_DIR, f"parallel_ab_{ts}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report + "\n")
    print(f"\n[OK] Report: {out_path}")

    print("[INFO] Entlade Modell(e)...")
    has_unloaded_all_models()


if __name__ == "__main__":
    main()
