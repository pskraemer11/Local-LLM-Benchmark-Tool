#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Resume-Run: nur Modelle/Benchmarks, die noch NICHT mit SampleSize=8 vollstaendig sind.
"""
import subprocess, sys, os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable
RUNNER = os.path.join(BASE_DIR, "run_benchmarks_v3.py")

# Modelle die NUR SampleSize=5 haben -> 10 Benchmarks komplett neu
NEU_10 = [
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

# Modelle mit SS8-Teildaten -> nur fehlende Benchmarks
# Phi 4: DS1000+PandasEval+HEval++MBPP++ARC+HellaSwag+TruthfulQA OK -> fehlt MMLU-Pro, BBH, MathQA
# Granite 4.1 8B: DS1000+PandasEval+HEval++MBPP++ARC+HellaSwag+TruthfulQA+MathQA OK -> fehlt MMLU-Pro, BBH
# Qwen2.5 Coder 14B: DS1000+PandasEval+HEval++MBPP++ARC+HellaSwag+TruthfulQA+MathQA OK -> fehlt MMLU-Pro, BBH

NUR_MMLU_BBH_MATHQA = ["--benchmarks", "MMLU-Pro,BBH,MathQA"]
NUR_MMLU_BBH = ["--benchmarks", "MMLU-Pro,BBH"]

PARTIAL = [
    ("microsoft/phi-4",                  NUR_MMLU_BBH_MATHQA),
    ("ibm/granite-4.1-8b",               NUR_MMLU_BBH),
    ("qwen/qwen2.5-coder-14b",           NUR_MMLU_BBH),
]

# Granite 4.1 8B und Qwen2.5 Coder 14B sind auch in NEU_10... entfernen wir sie von dort
for m in ["ibm/granite-4.1-8b", "qwen/qwen2.5-coder-14b"]:
    if m in NEU_10:
        NEU_10.remove(m)

def run(cmd, desc):
    print(f"\n{'='*60}")
    print(f"  {desc}")
    print(f"{'='*60}")
    print(f"  {' '.join(cmd)}")
    subprocess.run(cmd, check=False)

# Phase 1: Fehlende Benchmarks fuer Modelle mit SS8-Teildaten
print("="*60)
print("  PHASE 1: Fehlende Benchmarks (MMLU-Pro, BBH, MathQA)")
print("="*60)
for model, bench_args in PARTIAL:
    run([PYTHON, RUNNER,
         "--model", model,
         "--sample-size", "8"] + bench_args,
        f"{model} – fehlende Benchmarks")

# Phase 2: Modelle die komplett SS8 brauchen
print("="*60)
print("  PHASE 2: Modelle ohne SS8-Daten (10 Benchmarks)")
print("="*60)
for model in NEU_10:
    run([PYTHON, RUNNER,
         "--model", model,
         "--sample-size", "8",
         "--benchmarks", "all"],
        f"{model} – alle 10 Benchmarks SS8")

print("\n[OK] Resume-Run abgeschlossen.")
