#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rerun v2: DS1000 + MMLU-Pro mit SampleSize=8 für Modelle mit Timeout/broken Scores.
- DS1000: test_execution-Harness-Fix, extract_code bare-statement-Fix (v21)
- MMLU-Pro: Timeout skaliert, eos_string in model_args, try/except in run_lmeval (v4)
"""
import subprocess, sys, os

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable
RUNNER = os.path.join(BASE_DIR, "run_benchmarks_v11.py")

BENCH_ARGS = ["--benchmarks", "DS1000,MMLU-Pro"]
SS = ["--sample-size", "8"]

# Phase 1: Hatten SS8-Teildaten, nur DS1000 + MMLU-Pro fehlt/ist broken
PHASE1 = [
    "microsoft/phi-4",
    "ibm/granite-4.1-8b",
    "qwen/qwen2.5-coder-14b",
]

# Phase 2: SS8-Komplettlauf mit Timeout bei MMLU-Pro + broken DS1000
PHASE2 = [
    "codestral-22b-v0.1",
    "essentialai/rnj-1",
    "mistral-nemo-instruct-2407",
    "mistral-7b-instruct-v0.3",
    "qwen3.5-9b",
    "qwopus3.5-9b-coder-mtp",
    "gpt-oss-20b",
    "gemma-4-12b",
    "starcoder2-15b-instruct-v0.1",
    "pandalyst_13b_v1.0",
    "wizardcoder-python-13b-v1.0-i1",
    "ministral-3-14b-reasoning",
]

# Phase 3: Fertige SS8-Runs mit broken DS1000 (test_execution-Fix)
PHASE3 = [
    "januscoder-14b",  # Unsloth – DS1000 hatte Namespace-Fallback
]

ALL_MODELS = PHASE1 + PHASE2 + PHASE3

def run(cmd, desc):
    print(f"\n{'='*60}", flush=True)
    print(f"  {desc}", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"  {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=False)
    sys.stdout.flush()

def main():
    print("="*60)
    print("  RERUN: DS1000 + MMLU-Pro (SampleSize=8)")
    print(f"  Modelle: {len(ALL_MODELS)}")
    print("="*60)

    for i, model in enumerate(ALL_MODELS, 1):
        run([PYTHON, RUNNER,
             "--model", model] + SS + BENCH_ARGS,
            f"Modell {i}/{len(ALL_MODELS)}: {model} – DS1000 + MMLU-Pro SS8")

    print("\n" + "="*60)
    print("  RERUN ABGESCHLOSSEN")
    print("="*60)

if __name__ == "__main__":
    main()
