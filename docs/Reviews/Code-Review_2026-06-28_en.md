# Review: Benchmark Evaluation System (as of 2026-06-28)

## 1. Architecture Overview

```
run_benchmarks_v8.py  (Launcher – load/unload + Dispatch)
  ├── model_manager_v3.py      (lms CLI helper functions)
  ├── custom_benchmark_v25.py  (Subprocess: DS1000, CoderEval)
  ├── csv_writer_v3.py         (unified CSV output)
  ├── evalplus                 (HumanEval+, MBPP+)
  ├── lm_eval                  (ARC, HellaSwag, TruthfulQA, MathQA, MMLU-Pro)
  └── tool_eval_bench          (Agentic)
       ↓
consolidate_results_v9.py     (Reads CSVs + JSON → MD/CSV report)
```

**Total 5 active main scripts (1743 + 997 + 914 + 330 + 210 = 4,194 lines)**  
Plus 6 helper scripts/wrappers (run_all_dense, rerun_*, resume_*, check_*, top5_report – approx. 450 lines total)  
Legacy: benchmark_lmstudio_v22.py (1,692 lines, no longer in use)

---

## 2. Data Flow

```
custom_benchmark_v25.py
  → tasks_{ts}_{bench}_{model}.csv  (per-task raw data, semicolon delimiter)

run_benchmarks_v8.py  (Pipelines)
  → modell_{model_key}.csv           (accumulated model summary)
  → evalplus_{safe}/                 (JSON result directory)
  → lmeval_{safe}/                   (JSON result directory)
  → agentic_{safe}/                  (JSON result directory)

consolidate_results_v9.py
  ← tasks_*.csv, modell_*.csv, 2026*_*.csv (?), evalplus_*, lmeval_*, agentic_*
  → konsolidiert_{ts}.csv            (33 models × benchmarks, semicolon delimiter)
  → konsolidiert_{ts}.md             (human-readable report)
```

---

## 3. Assessment

### Strengths

1. **Clear separation of responsibilities**  
   - Launcher (run_benchmarks_v8.py) only manages pipeline dispatch + model lifecycle
   - model_manager_v3.py completely encapsulates lms-CLI
   - csv_writer_v3.py defines unified CSV schema for all pipelines
   - consolidate_results_v9.py is a pure reader (no imports of own scripts)

2. **Dynamic script detection**  
   - run_benchmarks_v8.py:130-142 automatically searches for `custom_benchmark_v*.py` with highest version – no hardcoding needed

3. **Robust CSV handling**  
   - Fallback on `tasks_*` names (new pipeline) and `2026*_*` format (old pipeline)
   - Auto-delimiter detection (`,` or `;`) with semicolon as default
   - Column aliases (e.g., `latency`/`latency_s`)

4. **Weighting system**  
   - `compute_category_scores()` automatically normalizes based on available benchmarks
   - Categories: Coding (35%), Math (25%), Agentic (25%), Knowledge (15%)
   - Missing benchmarks are skipped without null score

5. **Model timeout configuration**  
   - PIPELINE_TIMEOUTS centrally defined in model_manager_v3.py
   - Base values automatically doubled for reasoning models

### Weaknesses / Problems

1. **Two parallel file formats**  
   - Old pipeline: `20260617_193457_DS1000_Modell.csv`  
   - New pipeline: `tasks_20260617_193457_DS1000_Modell.csv`  
   - consolidate_results_v9.py must parse both → increased complexity (find_latest_csvs has two nearly identical blocks)

2. **No central test framework**  
   - There are no automated tests for core logic (e.g., compute_category_scores, CSV parsing, weight normalization)
   - Changes must be manually tested through full runs

3. **Version number chaos**  
   - Historically grown: `v23` to `v25`, `v2`/`v3`, `v7`/`v11` – inconsistent scheme  
   - Internal numbers were sometimes asynchronous to the filename (e.g., filename v24, internal v25)
   - Legacy wrappers (run_all_dense.py, rerun_lmeval.py) call `run_benchmarks_v3.py` – not the current v8

4. **Hardcoded code in tool-eval-bench**  
   - `run_benchmarks_v8.py` starts `tool_eval_bench` hardwired (path, args, model)
   - No dynamic discovery (unlike custom_benchmark)

5. **System metrics mixing**  
   - CPU/GPU/RAM/VRAM are averaged across all custom benchmarks (DS1000, CoderEval)  
   - Mixing per-task peak (`cpu_during`) and benchmark overall maximum leads to inconsistent values

6. **Legacy scripts in main directory**  
   - `benchmark_lmstudio_v18.py`–`v22.py`, `consolidate_results_v6.py`–`v7.py`, etc. are directly in the main directory  
   - Only manually outsourced versions are in `alte_skripte/`
   - Makes it harder to find active scripts

7. **No type checking**  
   - No type hints in core modules (despite Python 3.10+)
   - `consolidate_results_v9.py` mixes `int`, `float`, `str`, `None` in dicts without structure

8. **Configuration via comments**  
   - WHITELIST, DISPLAY_NAMES, CAT_WEIGHTS, OVERALL_WEIGHTS are hardcoded in `consolidate_results_v9.py`
   - Changes require code modifications, no external configuration

9. **Error handling inconsistent**  
   - `read_custom_csv()` returns `None` on errors → callers must check  
   - `try_read_evalplus()` catches exceptions internally and returns `None`  
   - Readability suffers from try/except variety

---

## 4. Detailed Critique per Script

### model_manager_v3.py (210 lines) ⭐⭐⭐⭐⭐
- Cleanest unit: clear API, no side effects
- Only weakness: `API_BASE` is hardcoded to `localhost:1234`

### csv_writer_v3.py (330 lines) ⭐⭐⭐⭐
- Well structured, four clearly separated CSV types
- Backward-compat aliases (save_csv etc.) increase maintenance cost
- Field definitions redundant between `write_*` functions and field lists

### custom_benchmark_v25.py (1743 lines) ⭐⭐⭐
- ✅ Dynamic JSONL loader
- ✅ Correct per-task output with GPU/CPU/latency
- ❌ Too long: contains legacy code (interactive mode, PandasEval remnants)
- ❌ No task retry mechanism
- ❌ Two code paths for DS1000 (old format + new format side by side)

### run_benchmarks_v8.py (997 lines) ⭐⭐⭐
- ✅ Good pipeline orchestration
- ✅ Dynamic custom_benchmark detection
- ❌ `run_lmeval()` and `run_evalplus()` nearly identical → high redundancy
- ❌ MMLU-Pro subset logic is 150 lines inline (better to extract)
- ❌ Error handling in parallel processing missing

### consolidate_results_v9.py (914 lines) ⭐⭐⭐
- ✅ Flexible CSV reader routine with auto-delimiter
- ✅ TOP5/BOTTOM5/benchmark tables in MD
- ❌ Column width logic duplicated (`widths` + `widths2`)
- ❌ No caching: reads all CSVs fresh every time
- ❌ No incremental update

---

## 5. Recommendations

1. **Clean up old scripts**: Move all `benchmark_lmstudio_v18–v22`, `consolidate_v6–v7`, `run_benchmarks_v1–v6` into `alte_skripte/`
2. **Introduce tests**: `pytest` for `compute_category_scores()`, `read_custom_csv()`, `find_latest_csvs()` with fixtures from real CSV files
3. **Type Hints**: Add type annotations to all functions in the 5 core scripts
4. **Externalize configuration**: Outsource `WHITELIST`, `DISPLAY_NAMES`, `CAT_WEIGHTS`, `OVERALL_WEIGHTS` to YAML/JSON
5. **Improve parallel execution**: Merge `run_evalplus()` and `run_lmeval()` into a generic `run_subprocess()` function
6. **Unified file naming scheme**: `tasks_` for all custom benchmarks, `modell_` for everything else – simplify `find_latest_csvs`
7. **Extract MMLU-Pro logic**: Into its own function/module (manageable + testable)
8. **Update legacy wrappers**: Switch `run_all_dense.py` etc. to current `run_benchmarks_v8.py`

---

*Review created from code analysis of the 5 core scripts + 6 helper scripts.*
*All paths relative to `C:\Users\pskra\Python-Projekte\Benchmarks\`.*
