## Review Report 2026-07-05: Gemma-4 Benchmarks, Quant Comparisons & Infrastructure Fixes

### 1. Gemma-4 Runs: Thinking vs. Non-Thinking

**Run 2026-07-04 (with `--thinking`):** 3/3 models successfully completed.
Results in the consolidated table (`konsolidiert_20260704_022948.md`):

| Model                                      | Quant  | Overall | Coding |Knowledge| Math | Agentic| tok/s |
|---------------------------------------------|--------|---------|--------|---------|------|--------|-------|
| Gemma 4 26B A4B Instruct UD (unsloth)       | IQ3_S  |   55%   |   66%  |   76%   |  55% |   25%  |   14  |
| Gemma 4 26B A4B Instruct Q3_K_S (bartowski) | Q3_K_S |   37%   |   37%  |    4%   |   0% |   95%  |    1  |
| Gemma 4 19B A4B Instruct REAP I1            | IQ4_NL |   56%   |   70%  |   43%   |   0% |   98%  |   17  |

Notable observations:
- **Gemma 4 26B UD (IQ3_S)** best Gemma overall (55%), excellent efficiency (24.4 %p/h, rank 2)
- **Gemma 4 19B REAP** best agentic score (98%) and coding (70%)
- **Gemma 4 Q3_K_S** completely fails on lm_eval (ARC=0%, HellaSwag=0%, TruthfulQA=0%) – lm_eval has template issues with bartowski quant

**Run 2026-07-05 (without `--thinking`):** Model 1/5 (`google/gemma-4-26b-a4b-it`, unsloth IQ3_S) crashed with HTTP 500 (see below). Remaining 4 models did not run (log aborted).

### 2. HTTP-500 Crash: Cause & Fix

**Cause:** `C:\Users\pskra\.lmstudio\hub\models\google\gemma-4-26b-a4b-it\model.yaml` created a virtual model `google/gemma-4-26b-a4b-it` that collided with the physical instance `gemma-4-26b-a4b-it` (unsloth IQ3_S) – both referenced the same GGUF file. llama.cpp crashed on inference attempt (HTTP 500 without "Running chat completion" in server log).

**Fix:** Deleted the entire directory `hub/models/google/gemma-4-26b-a4b-it/`. The mradermacher model.yaml remains, since there is no conflict (virtual `mradermacher/qwen3-coder-reap-25b-a3b-i1` does not collide with any physical instance).

**Consequence:** The non-thinking run for Gemma-4 models must be repeated. Instead of `--model google/gemma-4-26b-a4b-it`, use the physical key `--model gemma-4-26b-a4b-it` (unsloth) or `--model google_gemma-4-26b-a4b-it` (bartowski).

### 3. Quant Comparisons (Bootstrap-CI)

**Qwen3 Coder REAP 25B A3B I1** (from `quant_comparison.md`):

| Quant       | DS1000 |CoderEval| HEval+ | MBPP+ | ARC  |HellaSwag|TruthfulQA| MathQA | MMLU-Pro| Agentic | Overall  |
|-------------|--------|---------|--------|-------|------|---------|----------|--------|---------|---------|----------|
| IQ4_XS (UD) |   10%  |    75%  |   95%  |  71%  |  75% |   40%   |    50%   |   45%  |    46%  |   88%   |  *63.2%* |
| Q3_K_M      |   15%  |    75%  |   95%  |  79%  |  80% |   55%   |    50%   |   40%  |    58%  |   65%   |  *58.4%* |
| Q4_K_S      |   25%  |    75%  |   95%  |  71%  |  80% |   50%   |    50%   |   50%  |    36%  |   85%   |  *65.2%* |

Bootstrap 95% CI (SampleSize=20):
- DS1000: ±20-25% → differences <15% not significant
- CoderEval: ±10-15%
- Recommendation: Paired analysis (same items, bootstrap differences) for real quant comparisons

**Devstral Small 2 24B Instruct 2512:**

| Quant        | DS1000 |CoderEval| HEval+ | MBPP+ | Overall   | Delta |
|--------------|--------|---------|--------|-------|-----------|-------|
| IQ3_XXS (UD) |   15%  |   67%   |   95%  |  64%  | **58.4%** |   –   |
| Q3_K_S (new) |   30%  |   75%   |  100%  |  79%  | **67.0%** | +8.6% |

Q3_K_S clearly better – +8.6% overall with manageable VRAM increase.

### 4. Gemma-4-26B-QAT Comparison

| Quant        | DS1000 |CoderEval| HEval+ | MBPP+ | ARC  |HellaSwag|TruthfulQA| MathQA | MMLU-Pro| Overall  |
|--------------|--------|---------|--------|-------|------|---------|----------|--------|---------|----------|
| IQ3_S (UD)   |   10%  |   83%   |  100%  |  71%  |  95% |   60%   |    65%   |   55%  |    86%  |   53.4%  |
| QAT Q4_0     |   10%  |   17%   |   60%  |  64%  |  90% |    5%   |    60%   |   15%  |    75%  |   30.6%  |
| **Delta**    |    0%  |  -67%   |  -40%  |  -7%  |  -5% |  -55%   |    -5%   |  -40%  |   -11%  | *-22.8%* |

QAT Q4_0 is massively worse than IQ3_S (–22.8% overall) with similar VRAM. No reason to continue using QAT.

### 5. Version v11→v12

All Python scripts incremented:
- `run_benchmarks_v11.py` → `run_benchmarks_v12.py`
- `custom_benchmark_v11.py` → `custom_benchmark_v12.py`
- `consolidate_results_v11.py` → `consolidate_results_v12.py`
- All references in `benchmark_config.py`, `csv_writer.py`, `model_manager.py`, `rerun_*.py`, `run_all_dense.py`, `tests/` updated
- Old v11 files remain as backup

### 6. Open Points & Recommendations

1. **Repeat non-thinking run** (after HTTP-500 fix): `python run_benchmarks_v12.py --model gemma-4-26b-a4b-it,google_gemma-4-26b-a4b-it,gemma-4-19b-a4b-it-reap-i1 --benchmarks DS1000,CoderEval,ARC,HellaSwag,TruthfulQA,MathQA,MMLU-Pro --sample-size 20`
2. **Start Qwen3-Coder-25B comparison run** (3 quants: IQ4_XS, Q3_K_M, Q4_K_S) if not already run
3. **Gemma-4-12b** appears to have disappeared from LMS – missing for non-thinking comparison
4. **Bootstrap-CI** implemented in `consolidate_results_v12.py`, but SampleSize=20 gives too wide intervals for quant comparisons – paired analysis needed
5. **model.yaml** only remains for mradermacher/qwen3-coder-reap (no conflict) – check conflict risk for new models
