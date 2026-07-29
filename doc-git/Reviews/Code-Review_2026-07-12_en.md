# Code-Review – LLM Benchmark Suite
**Date:** 2026-07-12
**Scope:** Active Python code in project root + `doc-git/` + `Doku-intern/` + LM Studio Server Logs (3 most recent from 2026-07-12)
**Methodology:** Static analysis + Cross-reference with README, architecture docs, model profiles and log data

**Prio-1-Fix-Status (2026-07-12):**
- ✅ `tests/test_csv.py:4` fixed: Import `v12` → `v13`, created fixture `tests/fixtures/test_tasks.csv` (31 columns via `csv.DictWriter` from `TASK_FIELDS`)
- ✅ Channel-Error Auto-Fallback: `custom_benchmark.py` writes `[CHANNEL-ERROR]` marker on "Cannot combine structured output" / "Channel Error"; `run_benchmarks.py:run_custom_benchmark` detects marker and recursively calls itself with `no_structured_output=True`
- ✅ `wait_for_model_ready` timeout 30s → 60s: in `run_benchmarks.py` (3 locations: initial load, reload between benchmarks, reload after custom); default `TIMEOUT_MODEL_READY` 90s → 120s in `model_manager.py` as safety net
- ✅ Reload logic extended to all 4 pipelines: `_ensure_model_still_loaded()` helper function extracted in `run_benchmarks.py:469`, called after **every** benchmark (not only `is_custom`); unused variable `is_custom` removed
- ✅ Test suite: `pytest tests/` → **15/15 passed** (previously: 9/15 functional, since 6/6 in `test_csv.py` broken)

**Prio-2-Fix-Status (2026-07-12):**
- ✅ **D1: `_lookup_vram` Fuzzy-Match**: Substring match replaced by length-ratio guard (>=0.85); expanded publisher prefix list (ibm/google/microsoft/mistralai/essentialai/qwen/lmstudio-community/openai/mradermacher/jetbrains/unsloth/modelgraft/fb/meta/deepseek/cerebras/moonshotai/zai-org/baidu/alibaba); `best_score` tracking instead of first-match
- ✅ **C1: `strip_thinking_tokens` Token Estimation**: Content-aware heuristic `max(word_count * 1.3, char // 4)`, whitespace special case (1 token per 64 chars for Gemma-4 whitespace-heavy chains); Capped at `char_count`
- ✅ **K1: `QUANT_MAP` Conflict Resolution**: `get_quant()` helper with explicit priority (exact > suffix > base); Distinct entries for gpt-oss-20b variants (Q6_K, MXFP4, Q6_K) and Qwen3-Coder-REAP variants (Q3_K_M, Q4_K_S)
- ✅ **W1: `response` column compressed**: `--keep-response` CLI flag, `_truncate_response()` helper (default 200 chars + "…[truncated, X chars]" marker); `--keep-response` passed to subprocess
- ✅ **H2: Bootstrap-CI ported to NumPy**: `bootstrap_ci` and `paired_bootstrap_ci` use `np.random.randint` + `np.partition`; **300-500x speedup** (9-12ms instead of 3-5s for 100x10k); Pure-Python fallback preserved
- ✅ **Test suite extended**: `tests/test_prio2.py` with 21 new tests for get_quant, strip_thinking_tokens, _truncate_response, bootstrap_ci; **36/36 tests green** (previously 15/15)

**Remaining Prio-3 findings (refactoring):** Remove MMLU-Pro-Code, remove legacy aliases in csv_writer.py, subprocess path logging, merge duplicate thinking configuration, update `download_real_benchmarks.py`

---

## 1. Executive Summary

The project is a mature, well-structured benchmark suite for local LLMs via LM Studio REST API. The architecture follows a clean 4-pipeline design with a central launcher, dedicated model manager, and unified CSV schema. The modularization into `benchmark_config.py`, `model_manager.py`, `csv_writer.py`, and `consolidate_results.py` is exemplary.

**Strengths:**
- Clean separation: Launcher orchestrates, subprocesses execute, no load/unload outside the launcher
- Deterministic reproducibility via `--seed`
- Statistical significance through bootstrap-CI and pair comparisons
- Consolidated, variant-unique model keys (no quant conflict)
- Robust streaming logic with dual timeout monitoring (start/finish)
- Structured JSON output with regex fallback (eliminates 12% parsing errors)
- System monitoring (CPU/GPU/RAM/VRAM/Temp) per task
- 10 Pytest tests for core functions

**Critical findings (fix immediately):**
1. ✅ `tests/test_csv.py:4` imports from `consolidate_results_v12` (does not exist) → **FIXED** (import + fixture)
2. ✅ `run_benchmarks.py:1132-1137` reload logic only fires for custom benchmarks → **FIXED** (`_ensure_model_still_loaded()` helper)
3. 🟠 `model_manager.py:274-280` Success path returns `model_key` as fallback identifier if `get_current_loaded_model()` returns `None` for 10s → **Subprocesses receive wrong model_id → HTTP 400 hang** (documentation in line 672-676 points to exactly this risk, but the fallback is the trap)
4. ✅ `custom_benchmark.py:641-670` `strip_thinking_tokens` estimates tokens via `total_chars // 4` → **FIXED** (content-aware: `max(word_count * 1.3, char // 4)` + whitespace special case)
5. ✅ `benchmark_config.py:31,59-60` QUANT_MAP duplicates → **FIXED** (`get_quant()` helper with explicit priority, distinct entries for all variants)
6. ✅ `consolidate_results.py:152-192` `_lookup_vram` fuzzy match → **FIXED** (Length-ratio guard >=0.85, expanded publisher prefix list, `best_score` tracking)
7. 🆕 **🔴 `langdetect` missing** → IFEval fails on **all 14 models** (see 7.7.1)
8. 🆕 **🔴 `math_verify`/`sympy`/`antlr4-python3-runtime` missing** → MATH-500 fails on **all 14 models** (see 7.7.2)
9. 🆕 **🟠 DS1000-Harness Errors** for Granite models and Qwen3.6-28b: `set_xticklists`, `get_title`, `list index out of range`, `invalid syntax` (see 7.7.3)
10. 🆕 **🟠 TruthfulQA wrong metric** (`bleu_acc=0` for all) — should be `mc1` instead of `gen` (see 7.7.5)
11. 🆕 **🟠 Granite DS1000/CoderEval 0%** despite working HumanEval+ (0.86) — code parsing problem (see 7.7.7)
12. 🆕 **🟢 PowerShell encoding bugs** in terminal output (`▒`, `�?` instead of Unicode symbols) (see 7.7.10)

**Significant findings (fix soon):**
7. `consolidate_results.py:230-264` `bootstrap_ci` and `paired_bootstrap_ci` are **pure Python loops without NumPy** — at 10000 resamples × N items: noticeable CPU load (>5s per benchmark)
8. `model_manager.py:120-132` `unload_all_models` validates unload through 15× POST with `model="check"` — wastes ~30s on every benchmark switch, **especially when the model was already unloaded**
9. `run_benchmarks.py:1015-1020` `--exclude-benchmarks` filters only **after** resolving — if there is a typo in capitalization (`MATH-500` vs `math-500`), nothing is silently filtered
10. `custom_benchmark.py:530-545` `subsample_tasks` stratified via `_group` field, but for custom benchmarks with missing `_group` (e.g., CoderEval `prompt` without group), **plain random** is used → distribution loss at small sample sizes

**From Log Analysis (2026-07-12):**
- ✅ **2× "Channel Error: Cannot combine structured output constraints with lazy grammar"** with `granite-4.1-30b` (14:28) and `qwen3-30b-a3b-instruct-2507` (15:04) → **FIXED**: `custom_benchmark.py` now writes `[CHANNEL-ERROR]` marker to stdout when `error_detail` contains "Cannot combine structured output" or "Channel Error"; `run_benchmarks.py:run_custom_benchmark` detects the marker and recursively calls itself with `no_structured_output=True`
- ✅ **13× "No models loaded"** in log 5 between 09:03–15:04 → **FIXED**: `wait_for_model_ready` timeout 30s → 60s (3 locations in launcher); default `TIMEOUT_MODEL_READY` 90s → 120s in `model_manager.py` as safety net
- 5× "Unexpected endpoint" `/v1/version` (GET) — does **not** originate from the Python code (no `/v1/version` in the repo); likely LM Studio GUI/update check. Cannot be fixed through code, but worth documenting.

---

## 2. Architecture Assessment

### 2.1 Positive Aspects

**Clear layer separation** (see `doc-git/Architektur+Flow_Python-Benchmark-Skript_v24.md:59-123`):
```
Launcher (run_benchmarks.py)   → orchestrates, load/unload
├── custom_benchmark.py        → subprocess for DS1000/CoderEval
├── model_manager.py               → shared: lms CLI wrapper
├── csv_writer.py                  → shared: unified schema
├── evalplus (external)            → HumanEval+, MBPP+
├── lm_eval (external)             → ARC, HellaSwag, TruthfulQA, IFEval, MATH-500
└── tool_eval_bench (external)     → Agentic
```

**Central configuration** in `benchmark_config.py`:
- `CAT_WEIGHTS` (Coding 35% / Math 25% / Agentic 25% / Knowledge 15%)
- `PIPELINE_TIMEOUTS` (14400s custom, 600s evalplus, 600s lmeval, 3600s agentic)
- `EXCLUDE_KEYWORDS` (whisper/vision/ocr/audio/embed/vl/flux)
- `MMLU_PRO_SUBSETS` (14 subsets, although MMLU-Pro is no longer in the LMEVAL_BENCHMARKS set — dead code, see below)
- `TOOL_EVAL_SCENARIO_IDS` (TC-01..TC-69)

**Reproducibility**: `--seed` is passed through all pipelines (`custom_benchmark.py:1625-1630`, `run_evalplus` line 540-543), `paired_bootstrap_ci` uses seed for deterministic comparisons.

**Statistical robustness**:
- `bootstrap_ci` with 10000 resamples (lines 220-239) — standard for 95% CI
- `paired_bootstrap_ci` for quant comparisons (lines 241-264) — paired instead of unpaired, since the same tasks
- `compute_category_scores` normalizes sub-categories (lines 658-685) — important when a benchmark is missing

### 2.2 Design Weaknesses

**D1: Dynamic versioning via glob discovery** (`run_benchmarks.py:139-148`)
```python
_custom_scripts = glob.glob(os.path.join(BASE_DIR, "custom_benchmark_v*.py"))
...
CUSTOM_BENCHMARK_SCRIPT = max(_versions, key=lambda x: x[0])[1]
```
**Problem:** Only works because currently there is only one `custom_benchmark.py`. With future versions, the highest v-number will be selected — without visible logging of which path is being used. **Invisible regressions** possible.
**Fix:** Explicitly configure the active version in `benchmark_config.py` (`ACTIVE_CUSTOM_BENCHMARK = "custom_benchmark"`), log the path.

**D2: Two parallel "Thinking configurations"** (`thinking_config.md:23-50` vs `custom_benchmark.py:141-237` vs `run_benchmarks.py:351-390`)
- `MODEL_CONFIG` in `custom_benchmark.py` controls the custom pipeline
- `_get_lmeval_params` in `run_benchmarks.py` controls the lm_eval pipeline
- Documentation says: "Since v13 centralized in `_get_lmeval_params`" — **this is incorrect**: the custom pipeline still has its own `MODEL_CONFIG`. Dual maintenance, drift risk.
**Fix:** Centralize `MODEL_CONFIG` in `benchmark_config.py`, import into both pipelines.

**D3: Subprocess orchestration without health check** (`run_benchmarks.py:1084-1140`)
- For custom benchmarks: after each task, checks if model is still loaded (lines 1123-1137)
- For EvalPlus/LM-Eval/Agentic: **no analogous check** — if the subprocess unloads the model (e.g., due to an error), the next task crashes
**Fix:** Uniform health check for all pipelines.

**D4: MMLU-Pro-Code paths still present** (`benchmark_config.py:70-76`, `consolidate_results.py:601-617`)
- `MMLU_PRO_SUBSETS` is defined
- `read_lmeval_per_model` has a special MMLU-Pro loop
- But: `LMEVAL_BENCHMARKS` (`run_benchmarks.py:173-179`) contains **no** MMLU-Pro anymore
- `Architektur+Flow` line 17 explicitly says "MMLU-Pro (too expensive, 14 subsets)" — removed
- → **Dead code** that complicates consolidation without benefit
**Fix:** Remove `MMLU_PRO_SUBSETS` and MMLU-Pro loop in `read_lmeval_per_model`.

**D5: Legacy aliases without migration path** (`csv_writer.py:421-432`)
```python
def save_csv(results, benchmark_name, model_id): ...
def save_model_summary(model_display, model_results, ...): ...
def save_model_summary_csv(results, model_info): ...
```
These aliases forward to v10 functions, but are no longer called in the current code. Confusing for new contributors.
**Fix:** Remove them (one major version cycle is complete, no more backward-compat needed).

---

## 3. Code Quality per File

### 3.1 `run_benchmarks.py` (1175 LOC)

**Strengths:**
- Clean pipeline functions with clear returns (all return `dict` or `None`)
- Good error handling with `try/except subprocess.TimeoutExpired`
- Subprocess timeouts correctly with reasoning ×2 factor (`run_lmeval` lines 717-719)

**Bugs/Problems:**

| # | Line | Problem | Severity |
|---|------|---------|----------|
| B1 | 270-287 | `resolve_benchmarks` only matches exact lowercase names, but `ALL_BENCH_NAMES` are also lowercase → if a benchmark is displayed as "MATH-500" in the UI and the user capitalizes it, an `Unknown benchmark` error occurs. Should match case-insensitively. | Low |
| B2 | 666-676 | **Critical documentation conflict:** Documentation says "ALWAYS use api_model" but `model_manager.load_model_via_lms` returns `model_key` (not `identifier`) when `get_current_loaded_model` fails for 10s. Subprocesses then receive `model_key` (e.g., `qwen/qwen3-coder-30b`) instead of identifier (e.g., `qwen/qwen3-coder-30b@q3_k_s`) → HTTP 400 hang | **High** |
| B3 | 1015-1024 | `exclude_benchmarks` sets `b["name"].lower()` but does not match case-insensitively against `b["name"]` (line 1019) | Low |
| B4 | 1062-1065 | If `load_model_via_lms` fails, jumps to next model with `continue` — **without** checking if other benchmarks should possibly be skipped. Correct, but logging could be better. | Low |
| B5 | 1115-1117 | `all_summary.append(result)` is in the custom pipeline, `model_results.append(result)` is in all pipelines — asymmetry is clean, but **the condition `if result:`** at lines 1116-1121 is redundant: an empty `result` (None) is already covered by `result = run_*()`. | Low |
| B6 | 1132-1137 | **Reload logic only for Custom** — with `if is_custom`, checks if model is still loaded. EvalPlus/LM-Eval/Agentic do not have this check. If their subprocesses accidentally unload, the next task crashes. | Medium |

**Stylistic issues:**
- `import csv_writer as csv_writer` (line 53) — `as csv_writer` is redundant
- `_get_safe_context` (lines 204-210) searches linearly through 6 patterns — inefficient with more models; should be a dict with O(1) lookup
- Module-level `THINKING_ENABLED = False` (line 349) as global configuration is an anti-pattern; should be explicitly passed as a parameter

### 3.2 `custom_benchmark.py` (1819 LOC)

**Strengths:**
- Very robust streaming implementation in `_stream_chat_completion` (lines 504-627) with dual timeout monitoring
- Solid sandbox implementation in `_build_sandbox_script` (lines 909-996) with explicit blocklist
- Structured error handling with `error_type`/`error_detail` tuple (line 504)
- Per-task metrics with `monitor.start_sampling`/`stop_sampling` (lines 1404-1431)

**Bugs/Problems:**

| # | Line | Problem | Severity |
|---|------|---------|----------|
| C1 | 640-651 | `strip_thinking_tokens`: Estimates tokens via `total_chars // 4` — for Gemma-4 with `<|channel>thought\n...<channel|>` markup this is **drastically too high**, because `4` is calibrated for English text. Can lead to `thinking_ratio` > 100% | **High** |
| C2 | 1268-1271 | Prompt construction: `f"Create the function \`{entry_point}\`."` is hardcoded text; CoderEval tasks already contain `entry_point` in the docstring — can lead to duplicates in the prompt | Low |
| C3 | 1310-1319 | `# SOLUTION START` marker handling: If the marker is missing (e.g., newer DS1000 versions), `setup_code` becomes empty → sandbox cannot execute → score 0% without error message | Medium |
| C4 | 1706-1708 | `MAX_TASKS_PER_BENCHMARK = 100` — hardcoded limit; with 1000-task benchmarks, 90% are ignored without warning | Medium |
| C5 | 504-627 | `_stream_chat_completion` has 8-tuple return (`content, elapsed, t_in, t_out, tps, thinking_tokens, error_type, error_detail`) — should be a `@dataclass` (see `consolidate_results.py:688-757` for positive examples) | Medium |
| C6 | 1700-1732 | In non-interactive mode, iterates over `for bench in benchmarks`, but `non_interactive` does **not** automatically execute `--thinking` — is this intentional? Not documented in README. | Low |

**Performance:**
- `Monitor` (lines 282-373) allocates 4 lists per instance with `MONITOR_HISTORY_MAX = 500` elements — on long benchmarks (>500 tasks), oldest samples are removed with `del lst[:-MONITOR_HISTORY_MAX]`. O(1) per append, but `get_snapshot` calls `update` — can block the actual sampling thread. Should be implemented as a lock-free ring buffer.

**Logic errors:**
- `subsample_tasks` (lines 258-279): Stratified only when `_group` field is present. For `CoderEval` tasks (see `download_codereval.py`) `_group` is missing → plain random. Inconsistent with DS1000.

### 3.3 `consolidate_results.py` (1359 LOC)

**Strengths:**
- `ModelData` dataclass (lines 688-757) — typed CSV rows, prevents dict key typos
- `_normalize_model_keys` (lines 77-108) — robust variant deduplication
- `_get_display_name` with 3-tier fallback (lines 111-145) — exact, modelKey match, fuzzy
- `bootstrap_ci` and `paired_bootstrap_ci` (lines 220-264) — cleanly implemented
- `_percentile` linear interpolation (lines 211-218) — standard NIST algorithm

**Bugs/Problems:**

| # | Line | Problem | Severity |
|---|------|---------|----------|
| D1 | 152-192 | `_lookup_vram` fuzzy match with `dk_short = re.sub("(ibm\|google\|microsoft\|mistralai\|essentialai)/", "", dk_norm)` and `len(dk_short) > 5`: with `gemma-4-12b` (10 chars), **everything** containing `gemma4...` is matched → wrong VRAM assignment | **High** |
| D2 | 220-264 | `bootstrap_ci` and `paired_bootstrap_ci` in pure Python — 10000 resamples × N tasks. With N=100, that's 1M `random.choice` calls per benchmark. **NumPy not used** — wasted CPU time | Medium |
| D3 | 504-560 | `_read_results_json` and `read_lmeval_per_model` parse JSON files unsorted, **the newest file is found through filename sorting** (line 609), but if old and new files exist (e.g., after reload), the newest is not guaranteed to be selected | Medium |
| D4 | 621-655 | `read_agentic` does `os.walk` and sorts by timestamp substring in filenames — fragile: if the file is named `agentic_qwen3-30b_20260712_120000.json`, `_extract_ts` looks for 14-digit numbers, but if the name is `_v2_20260712_120000`, `v2` can collide with `v2_20260712...` | Low |
| D5 | 762-790 | `read_data` with `model_keys=None` does auto-discovery via filenames, **not** via the `model_key` from CSV content. When re-running a model with a different quant variant (e.g., `qwen3-coder-30b@q4_k_s` vs `@q3_k_s`), only the **newest** CSV is found — **old results are overwritten** instead of merged | Medium |
| D6 | 1079-1118 | `_write_tbl` manually builds a markdown table with complex width calculation. Code reuse of 50 LOC for a single table — should use `tabulate` library (already present as transitive dependency via evalplus) | Low |

**Documentation problems:**
- Docstring lines 7-21 says: "1. Overall ranking", "2. Category scores" etc. — but the `main()` function (line 950-...) uses `--compare` mode (paired bootstrap) that runs **before** normal consolidation. The main function branches very early — unusual for Python `main()`.

### 3.4 `model_manager.py` (329 LOC)

**Strengths:**
- `_ensure_lmstudio_running` (lines 218-249) with llmster path fallback
- `load_model_via_lms` with double attempt (lines 259-294) — recovery on "No LM Runtime"
- `wait_for_model_ready` with polling (lines 298-329) — correct handling of HTTP 400 "No models loaded"

**Bugs/Problems:**

| # | Line | Problem | Severity |
|---|------|---------|----------|
| M1 | 274-280 | **Critical fallback bug:** If `get_current_loaded_model()` returns `None` for 10×1s = 10s, `model_key` is returned as identifier. LM Studio API accepts `model_key` but **only** if `lms load` was called without `--yes`. With `--yes` load (line 254), a variant with `@quant` suffix is loaded — `model_key` without suffix mismatch → HTTP 400 hang | **High** |
| M2 | 120-132 | `unload_all_models` makes 15× POST calls to `/v1/chat/completions` with `model="check"` — **30s wait time** on every benchmark switch, **even if the model was already unloaded**. Should check with `lms ps --json` whether anything is loaded at all | Medium |
| M3 | 80-97 | `get_current_loaded_model` parses `lms ps --json` and returns only the **first** element (`entries[0]`). With multiple loaded models, returns the "wrong" one | Medium |
| M4 | 252-295 | `load_model_via_lms` has `context_length` and `gpu_offload` as parameters, but in the launcher (`run_benchmarks.py:1057, 1062, 1090`) **only** `context_length` is passed — `gpu_offload` is dead | Low |
| M5 | 218-249 | `_ensure_lmstudio_running` starts `llmster.exe` from `~/.lmstudio/llmster/0.0.12-1/llmster.exe` — **absolute version number in path**. Breaks on LM Studio update | Low |
| M6 | 70-77 | `check_api_available` and `TIMEOUT_HEALTH_CHECK` are imported but **never** called outside `model_manager.py` — dead code (lines 19-20 in `custom_benchmark.py:78-83` import them but do not use them) | Low |

### 3.5 `benchmark_config.py` (124 LOC)

**Strengths:**
- Clean configuration single-source-of-truth
- `QUANT_MAP` with auto-generator (`generate_quant_map.py`)
- `MMLU_PRO_SUBSETS` is the single source of truth for all 14 subset names

**Bugs/Problems:**

| # | Line | Problem | Severity |
|---|------|---------|----------|
| K1 | 23-67 | `QUANT_MAP` contains **three entries** for `gpt-oss-20b`: `gpt-oss-20b` (Q6_K), `lmstudio-community/gpt-oss-20b` (MXFP4), `unsloth/gpt-oss-20b` (Q6_K). `_lookup_vram` uses the first match — if a different quant is desired, the wrong one is returned | **High** |
| K2 | 85-104 | `CAT_WEIGHTS` uses `HumanEval+_plus` and `MBPP+_plus` as keys (lines 88-89), but `custom_benchmark.py` writes `"HumanEval+"` to CSV. Inconsistency leads to score=0 for these benchmarks in `compute_category_scores` | **High** |
| K3 | 70-76 | `MMLU_PRO_SUBSETS` is dead code (see D4 in Architecture) | Low |
| K4 | 108-115 | `PIPELINE_TIMEOUTS["custom_subprocess"] = 14400` (4h!) — very long, blocks error detection. With hanging tasks, you run 4h without feedback | Low |

**Bug K2 is particularly critical** — the keys in `CAT_WEIGHTS` (`HumanEval+_plus`, `MBPP+_plus`) do not match the keys in `bench_scores` (comes from `try_read_evalplus` lines 518-542 with key `humaneval_plus` and `mbpp_plus` — so also not!). Chain of bugs:
- `try_read_evalplus` returns `{"humaneval_plus": 0.x, "mbpp_plus": 0.x}` (lowercase, without `+`)
- These are assigned in `read_data` lines 849-850 as `bench_scores["HumanEval+_plus"]`/`bench_scores["MBPP+_plus"]`
- `compute_category_scores` uses `CAT_WEIGHTS["coding"]` with keys `"HumanEval+_plus"`, `"MBPP+_plus"` (uppercase)
- `bench_scores` has `"HumanEval+_plus"` — so it does match? **Yes, in this case it matches — false alarm, but the inconsistency remains risky.**

### 3.6 `csv_writer.py` (432 LOC)

**Strengths:**
- Unified CSV schema across 4 pipelines
- Clear workflow: TASK_FIELDS → MODEL_FIELDS → SUMMARY_FIELDS → CONSOLIDATED_FIELDS
- `write_quant_comparison` (lines 375-417) for statistically significant quant comparisons

**Bugs/Problems:**

| # | Line | Problem | Severity |
|---|------|---------|----------|
| W1 | 68-100 | `TASK_FIELDS` contains `response` (line 99) — for DS1000/CoderEval, `response` can be several KB of JSON code. With 100 tasks × 50KB = 5MB CSV. **Bloat** | Medium |
| W2 | 152-166 | `CONSOLIDATED_FIELDS` contains no columns for runtime/efficiency/VRAM — the important engineering metrics are missing in the consolidated overview | Medium |
| W3 | 271 | `f"{e.get('avg_score', 0) * 100:.1f}"` — multiplication by 100 hardcoded. If `avg_score` is already in 0-100 (which it is, see `run_task` lines 1283-1295), it becomes 100 times too large! | **High** |

**W3 is a real bug:** in `benchmark_model` line 1473, `avg_score = sum(scores) / len(scores)` is calculated, and `scores` contains values from `result["score"]` (line 1283: 0.0 or 1.0 for pass/fail). So 0-1. In `write_per_model_csv` line 271, `* 100` is done → correct. But the `avg_score` in `model_results` (lines 1738-1752) is **passed as float (0-1)**, and `e.get("avg_score")` is that float. `* 100` is therefore correct. **False alarm.**

But: in `write_per_task_csv` line 218, `r.get("score", "")` is taken directly **without** `* 100` — so the CSV value is 0-1 in tasks, 0-100 in models. **Real inconsistency!**

### 3.7 `tests/` (2 files, 99 LOC)

**`test_scores.py`:** ✅ 10 tests, all meaningful, test `compute_category_scores` and `_percentile`. Covers edge cases (partial scores, zero scores, single value).

**`test_csv.py`:** ❌ **Completely broken:**
- Line 4: `from consolidate_results_v12 import read_custom_csv, _auto_delimiter` — `v12` does not exist
- `read_custom_csv` is in `v13`, line 347
- `_auto_delimiter` is in `v13`, line 340
- Should be: `from consolidate_results import read_custom_csv, _auto_delimiter`
- Fixture path `tests/fixtures/test_tasks.csv` is nowhere visible in the repo — tests fail with `FileNotFoundError`

→ **CI runs green (because no CI is configured in `.github/`), but the tests do not work.** High priority.

### 3.8 Helper Scripts

**`download_codereval.py`** (296 LOC):
- Downloads CoderEval4Python.json, converts to self-contained tasks
- `PARAM_RULES` (lines 13-37) heuristic, well documented
- `_is_blocked` (lines 140-147) blocks dangerous modules — good
- **Bug D1:** Line 127 `if isinstance(expected, types.FunctionType): return None` — leads to `skip_task = True` line 261, task is skipped. But: a `return None` is the only return for this case — the subsequent assertion (line 259) is `if assertion is None: skip_task = True`. Correct.
- **But:** `_make_assertion_code` for functions with `*args` (line 145) becomes skip reason "has *args/**kwargs" — many CoderEval tasks have this

**`download_real_benchmarks.py`** (594 LOC):
- Downloads 11 benchmark datasets
- **Completely outdated:** The fields `type: "coding"`, `type: "math"` etc. are set but not used by the current code (custom pipeline uses `task_type` from the BENCHMARKS dict lines 137-139)
- The file `simple_evals/coding.jsonl` is generated, but not referenced by the current launcher (only `data_science.jsonl` and `codereval_selfcontained.jsonl` are used)
- **Dead code** — should either be deleted or reused in CI

**`generate_quant_map.py`** (296 LOC):
- Multi-source QUANT_MAP generator
- 5-tier priority cascade (lms ls → Config → GGUF-Cache → Display-Name → Filename)
- `_normalize_key` (lines 131-140) removes publisher + quant — robust
- **Bug:** `_format_quant_map` (lines 209-224) sorts by `name_map` but uses `name_map = {k: k for k in all_keys}` (line 242) — i.e., by model_key instead of display name. Sorting is non-deterministic between runs

**`backup_model_configs.py`** (82 LOC):
- Backup/Restore of LM Studio per-model configs
- Clean path resolution
- No backup of `user-concrete-model-default-config` if directory does not exist (lines 18-19) — good

**`gguf_full_metadata_reader.py`** & `gguf_moe_full_metadata_reader.py`:
- Reads GGUF metadata, extracts MoE info
- **Not** referenced by the active benchmark code — dead code
- Has umlaut bugs in output (see `Möchten` instead of `Möchten`)

**`check_agentic.py`** (29 LOC):
- Smoke test: lists models that have agentic scores
- Hardcoded on `konsolidiert_2026*.csv` pattern (line 3) — does not work with `konsolidiert_SS4_*.csv` (new naming convention)
- **Bug:** With `konsolidiert_SS4_20260712_125230.csv`, the script shows 0/41 agentic scores even though agentic scores exist

---

## 4. Performance Analysis

### 4.1 Identified Hotspots

**H1: Subprocess overhead per benchmark** (architecture doc confirms this)
- Each LM-Eval task starts its own `python -m lm_eval` subprocess
- EvalPlus: `evalplus_codegen` subprocess per dataset (humaneval/mbpp)
- With 4 benchmarks × 28 models = **112 subprocesses**, each with Python startup (~2s) + lm_eval init (~5s) = **~15 min overhead** for nothing

**H2: Bootstrap-CI without NumPy** (`consolidate_results.py:220-264`)
- `bootstrap_ci` does 10000 × `random.choice(scores)` → 1M calls at N=100
- NumPy: `np.random.choice(scores, (10000, N), replace=True).mean(axis=1)` → 100x faster

**H3: `unload_all_models` validates with 15 POST calls** (`model_manager.py:118-132`)
- 30s wait time on every benchmark switch
- With 4 benchmarks × 28 models = **112 × 30s = 56 min** pure wait time
- **Fix suggestion:** `lms ps --json` check (sub-second), only POST if model is still there

**H4: Per-task `monitor.start_sampling`** (`custom_benchmark.py:1404`)
- 5Hz sampling during inference — minimal overhead
- But: `MONITOR_HISTORY_MAX = 500` × 4 lists = 2000 floats per task
- With 100 tasks × 28 models = 5.6M floats stored — minimal (40MB)

**H5: Token estimation via `len(content.split())`** (`custom_benchmark.py:624`)
- Works for English text (~0.75 tokens/word)
- Faulty for code with special characters (e.g., `==` as 1 word instead of 1 token)
- Should use tokenizer (already included in `requests` response, line 617)

### 4.2 Scaling Problems

With 100+ models or SS=100, the system becomes noticeably slower:
- Consolidation: 100 models × 4 benchmarks = 400 CSV reads = linear
- Display-Name-Resolution: 100 × 3-tier fallback per model = 300 `lms ls --json` calls
  - **Bug:** `_get_model_info()` caches only one session (`_MODEL_INFO_CACHE` line 38), but with `--compare` it is called multiple times — cache helps

---

## 5. Test Coverage

**Current:** 10 tests in `test_scores.py` + ~5 tests in `test_csv.py` (broken)

**Gaps:**
- No tests for `model_manager.py` (critical, many bug sources)
- No tests for `custom_benchmark.py` streaming logic
- No tests for `consolidate_results.py` (except `compute_category_scores`)
- No tests for `csv_writer.py` schema consistency
- No tests for `download_codereval.py` heuristics
- No integration tests (real LM Studio calls)
- No CI config in `.github/` (only ISSUE_TEMPLATE/bug_report.md)

**Recommendation:**
1. Fix `test_csv.py` (create import + fixture)
2. Add mocking layer for LM Studio API calls (e.g., with `responses` library)
3. CI with GitHub Actions: `pytest + ruff + mypy`
4. Property-based tests for `_get_display_name` fuzzy match

---

## 6. Documentation Consistency

### 6.1 README.md

- Line 17 lists `lm_eval (ARC, HellaSwag, TruthfulQA, MathQA, MMLU-Pro)` — **MMLU-Pro has been removed**, should be updated
- Line 17 lists `MathQA` — **replaced by MATH-500** (see `run_benchmarks.py:178`)
- Lines 39-40 GitHub URL `pskraer11/llm-benchmark-suite` — does this repo exist? Not verifiable, but matches local `git remote -v` data
- Lines 61-63 shows `--benchmarks DS1000,CoderEval --sample-size 10` — works with v13
- Lines 65-67 shows `python consolidate_results_v12.py --bootstrap` — **`--bootstrap` was removed in v13** (line 144 of thinking_config.md confirms), must be updated
- Lines 73-80 CLI options table is accurate
- Lines 91-92 architecture diagram is correct
- Lines 99-104 pipeline table lists **4 pipelines, 10 benchmarks** but current v13 has **5 pipelines** (`custom`, `evalplus`, `lmeval`, `agentic` + the `_parse_subset_score` helper, plus `MMLU-Pro-modified`) — and only **9 benchmarks** (without MMLU-Pro)
- Lines 105-114 weighting table is correct for active set, but **MATH-500 instead of MathQA** is missing from the enumeration
- Lines 115-127 "Thinking Mode" section is outdated — mentions `--thinking` activation for MathQA/MMLU-Pro (no longer existing benchmarks)
- Lines 130-145 Project Structure matches the current directory structure

### 6.2 `doc-git/Architektur+Flow_Python-Benchmark-Skript_v24.md`

- Line 1: "As of 2026-07-12 (v33)" — **Version confusion**: README says v13, file says v33. Documentation inconsistency
- Line 17: "Removed: BBH, PandasEval, MMLU-Pro" — correct
- Line 17: "Added: Agentic pipeline and MATH-500" — correct
- Lines 59-123: Structure description is accurate
- Line 66: "MMLU-Pro helper (removed in v13): _get_lmeval_params, _build_lmeval_cmd, _parse_subset_score" — **INCORRECT**: These helpers still exist in v13 (lines 351, 393, 431 in `run_benchmarks.py`)
- Line 85: "Version internal: 'Unified Benchmark Launcher v10'" — confusing, since the file is named `v13`
- Lines 122-123: Duplicate paragraph: "Complete Type Hints (27 functions)" appears twice
- Line 142: "BBH (too expensive, 8x multiplier)" — BBH is removed, but still implemented in `download_real_benchmarks.py` (lines 231-292)
- **Review 2026-06-28 section (lines 125-146):** Very detailed, good history. But "Type Hints 55+20+27 = 102 functions" (line 129) — current numbers should be verified (v13 likely has more)

### 6.3 `doc-git/thinking_config.md`

- Lines 23-41: Current patterns are correct for v13
- Lines 42-57: `--thinking` flag behavior is very clearly documented
- Lines 58-72: "Since v13 centralized in `_get_lmeval_params()`" — **incorrect** as noted in D2 above
- Line 85: "MathQA `20→512`, HellaSwag `20→100`" — these YAML changes are not findable in the repo (`lm_eval_tasks/` only contains `mathqa_gen/utils.py`)

### 6.4 `doc-git/Parallel-Slots-Optimierung.md`

- Lines 30-37: Dense vs MoE recommendation (np=1 vs np=4) — excellent empirical data
- Lines 42-55: LCP/LRU mechanism correctly explained
- Lines 78-101: Log evidence is concrete and comprehensible
- **But:** Script recommendations are not implemented in Python code — `model_manager.py` has no `np` parameter. Manual via JSON config required (also mentioned in Doku-intern/)

### 6.5 `Doku-intern/Modell_Steckbriefe_20260711.md`

- Very comprehensive, good practical information
- Inconsistency: Archive entries are marked with `(deleted)`, but **3 of them (LFM2 24B, qwen3.6-28b, GPT-OSS 20B) were reactivated for the SS=4 run** — cross-reference to `ergebnisse/` and `consolidate_results.py:684-688` shows reactivated models

### 6.6 `Doku-intern/Reviews/`

- Three review files present (`Code-Review_30-06-2026.md`, `review_20260628.md`, `Review_20260705.md`)
- Consistency between reviews unclear — different structures

---

## 7. LM Studio Server Log Analysis (2026-07-12)

### 7.1 Data Volume

| Log | Size | Lines | Models (top) |
|-----|------|-------|--------------|
| `2026-07-12.5.log` | 10.0 MB | 110,902 | qwen3.6-28b-reap-i1@q3_k_s (30k), qwen3.6-27b-mtp (15k) |
| `2026-07-12.6.log` | 10.0 MB | 110,370 | qwen3.6-27b-mtp (73k), qwen3.6-28b-reap-i1@iq3_s (32k) |
| `2026-07-12.7.log` | 1.3 MB | 12,997 | qwen3.6-28b-reap-i1@iq3_s (12.5k) |

### 7.2 Error Categorization

| Error Type | Log 5 | Log 6 | Log 7 | Total |
|------------|-------|-------|-------|-------|
| "No models loaded" | 13 | 1 | 0 | **14** |
| "Unexpected endpoint /v1/version" | 5 | 1 | 0 | **6** |
| **"Channel Error: Cannot combine structured output constraints with lazy grammar"** | **2** | 0 | 0 | **2** |
| TIMEOUT pattern | 0 | 0 | 0 | 0 |
| OOM (not enough space) | 0 | 0 | 0 | 0 |

### 7.3 Channel Error – Critical Finding

**Log 5 lines 58671, 94468:** With `granite-4.1-30b` (14:28:29) and `qwen3-30b-a3b-instruct-2507` (15:04:56), the following error occurs:
```
[ERROR] Error: Channel Error
- Caused By: Error: Cannot combine structured output constraints with lazy grammar
```

**Cause:** LM Studio accepts `response_format: {type: "json_schema", ...}` but not together with internal lazy grammar constraints. `custom_benchmark.py:1311-1335` and `STRUCTURED_OUTPUT_SCHEMA` (lines 103-116) set this schema unconditionally for all custom benchmarks, **without checking model compatibility**.

**Code locations:**
- `custom_benchmark.py:103-116` (`STRUCTURED_OUTPUT_SCHEMA` definition)
- `custom_benchmark.py:1311-1335` (passing to `generate_answer`)
- `custom_benchmark.py:1611-1612` (`--no-structured-output` flag)

**Previous workaround:** Manually set `--no-structured-output`, but:
1. No auto-fallback on channel error
2. Subprocess output parsing in `run_custom_benchmark` lines 509-512 reads "Average score" from output — on channel error the subprocess output is empty → Score 0% for these models

**Recommended Fix:**
- Detect channel-error exception in `run_custom_benchmark`
- Auto-retry with `--no-structured-output` for exactly these models
- Or: Per-model whitelist in `MODEL_CONFIG` for `structured_output: True/False`

### 7.4 "No models loaded" – Health-Check Gap

**Log 5 lines 25901, 31380, 32207, ... 83268 (13 occurrences):**
```
[ERROR] No models loaded. Please load a model in the developer page or use the 'lms load' command.
```

**Time correlation:** All occurrences between 09:03 and 15:04 — consistent with the SS=4 run that, according to `Architektur+Flow` and CSV data, ran around this time.

**Likely cause:** `model_manager.wait_for_model_ready(timeout=30)` (lines 298-329) sends POST with `model="check"` — if the server is not yet ready (LM Studio just started after `lms load`), it responds with `No models loaded`. The 30s wait time may be too short for 30B models (load time often 30-60s).

**Code location for fix:**
- `model_manager.py:298-329` — increase timeout to 60-90s OR insert multiple load status checks between load and subprocess start

### 7.5 Performance Pattern from Logs

**LCP cache works very well:**
- Log 5: 1131 LCP selections vs 20 LRU selections (98% LCP hit rate)
- Log 6: 224 LCP vs 2 LRU
- Log 7: 34 LCP vs 0 LRU

**This confirms the np=1 recommendation from `Parallel-Slots-Optimierung.md`** — the practical data matches the theory.

**Tool call density (Log 5):** 1358 tool calls for qwen3.6-28b-reap-i1@q3_k_s + other models — expected for agentic benchmark.

### 7.6 `/v1/version` Requests

**Log 5, 6:** 5+1 requests to `GET /v1/version` (lines 44562, 54288, 70364, 82284, 92784 + 71260). **Not** referenced in Python code (verified with grep). Likely LM Studio GUI health check or auto-update mechanism. **Cannot be fixed through code, but can be documented as a known phenomenon** (e.g., in architecture docs).

### 7.7 Terminal Output Findings (Run 2026-07-12, submitted subsequently)

**Source:** `Doku-intern/Terminalausgabe Benchmark Run mit neuen Benchmarks und SampleSize 10.md` (NOT part of the original review scope — subsequently added on 2026-07-12).

#### 7.7.1 IFEval fails on ALL 14 models — `langdetect` missing

**Severity: 🔴 Critical** | **Frequency: 14/14 models × 2 runs = 28 subprocess errors**

When calling `lm_eval --tasks ifeval`, every model fails with:
```
ModuleNotFoundError: No module named 'langdetect'
```
Call path: `lm_eval/tasks/ifeval/instructions.py:36` → `import langdetect`. lm_eval's IFEval tasks require `langdetect` for language detection of LLM outputs.

**Code location:** `run_benchmarks.py:run_lmeval` calls `python -m lm_eval --tasks ifeval` as a subprocess, which loads the `langdetect` dependency at the module level. Since the subprocess hangs **before** `simple_evaluate` with the `import`, there is no score result.

**Impact:** `consolidate_results.py:read_lmeval_per_model` finds no `IFEval` scores in `ergebnisse/lmeval_<model>/` → `bench_scores["IFEval"] = None` → no aggregation possible.

**Recommended Fix:** Add `pip install langdetect` to the install script (`Doku-intern/Doku-intern/install_benchmark-data_windows.ps1`) and supplement in `README.md:42`.

#### 7.7.2 MATH-500 fails on ALL 14 models — `math_verify`/`sympy`/`antlr4-python3-runtime` missing

**Severity: 🔴 Critical** | **Frequency: 14/14 models × 2 runs = 28 subprocess errors**

When calling `lm_eval --tasks minerva_math500`, every model fails with:
```
ModuleNotFoundError: No module named 'math_verify'
ModuleNotFoundError: `sympy`, `math_verify` and `antlr4-python3-runtime==4.11` are required
```
Call path: `lm_eval/tasks/minerva_math/utils.py:16` → `from math_verify import parse, verify`. lm_eval's MATH tasks (minerva_math) require these dependencies.

**Code location:** Same code path as IFEval (see 7.7.1).

**Impact:** Consolidation cannot compute `Math` score. `CAT_WEIGHTS["math"] = {"MATH-500": 1.0}` in `benchmark_config.py:97-99` is a deadlock without these dependencies.

**Recommended Fix:** Add `pip install lm-eval[math]` (installs sympy + math_verify + antlr4-python3-runtime) to the install script. Alternative: `pip install sympy math_verify antlr4-python3-runtime==4.11`.

#### 7.7.3 DS1000-Harness Errors (multiple recurring patterns)

**Severity: 🟠 High** | **Frequency: 30+ occurrences across all Granite models**

DS1000 tasks fail with the following error messages:
- `'NoneType' object has no attribute 'get_title'` (Matplotlib missing `set_title` call in generated code)
- `list index out of range` (test generation fails)
- `invalid syntax (<string>, line N)` (unwrap logic in code does not work)
- `Arrays are not equal (shapes (2,) (10,) mismatch)` (DS1000 tests expect more values than generated)
- `module 'matplotlib.pyplot' has no attribute 'set_xticklabels'`

**Affected models:** Granite 4.1 30B I1, Granite 4.0 H Tiny, Granite 4.1 8B (all 3 Granite models), Qwen3.6 28B REAP I1

**Code location:** `custom_benchmark.py:1113-1146` (`_try_ds1000_harness`) — the `_unwrap_solution_for_insert` function (lines 1036-1110) attempts to format code, but the official DS-1000 harness (`ds1000_official/execution.py`) expects an exact defined code structure.

**Possible causes:**
1. Code is generated with `enable_thinking=True` → thinks instead of coding
2. `set_xticklabels` is an old Matplotlib API — newer versions have `ax.set_xticklabels()`
3. `_unwrap_solution_for_insert` strips too much code with some patterns

**Recommended fixes:**
- Test DS1000 YAML with `do_sample=False` and explicit `temperature=0.0`
- Add `set_xticklabels` patches in `_try_ds1000_harness` (replace with `ax.set_xticklabels(...)`)
- Handle more DS1000 tasks as "expected_outputs" with `0` or `array([])`

#### 7.7.4 ARC-Challenge Score=0 for almost all models

**Severity: 🟠 High** | **Affected: 13/14 models**

| Model | ARC-Challenge Score |
|---|---|
| Granite 4.1 30B I1 | 0 |
| Granite 4.1 30B | 0 |
| Granite 4.0 H Tiny | 0 |
| Granite 4.1 8B | 0 |
| Qwen3 30B A3B Instruct 2507 | **0.9** (only non-zero) |
| Qwen3.6 27B | 0 |
| Qwen3.6 28B REAP I1 | 0 |

**Likely cause:** ARC-Challenge has 1170 multiple-choice questions — with limit=10, 8 out of 10 are likely "easy" while 2-3 are the "hard" ones. With SampleSize=10, the sample is too small for statistical significance. **BUT:** Even Qwen3 30B A3B achieves 0.9, so score=0 for all other models is suspicious.

**Possible explanation:** The YAML configuration for `arc_challenge_chat` filters the answer with `remove_whitespace`. Granite models may return letters + additional text, which after whitespace stripping destroys the "correct" answer.

**Code location:** `lm_eval_tasks/arc_challenge.yaml` (not in current code — deleted?) or `lm_eval/tasks/arc/arc_challenge_chat.yaml` (lm_eval built-in).

#### 7.7.5 TruthfulQA `bleu_acc=0` everywhere — wrong metric

**Severity: 🟠 High** | **Affected: 13/14 models**

`truthfulqa_gen` returns for almost all models:
```
|truthfulqa_gen|3|none|0|bleu_acc   |↑ |0.0000|± |0.0000|
|              |  |none|0|bleu_diff  |↑ |-0.0675|± |0.0467|
```

**Cause:** lm_eval's `truthfulqa_gen` (generation task) expects the model to generate the **complete answer** (e.g., "The moon is made of cheese") and compares it against the ground truth with `bleu_acc` (BLEU score). Most LLMs however return **only the letter A/B/C/D** (multiple choice), not the full answer text → BLEU = 0.

**Code location:** lm_eval built-in YAML `truthfulqa_gen` — the `bleu_acc` metric is the wrong choice for multiple-choice answers.

**Recommended Fix:** Switch to `mc1` (Multiple-Choice 1) or `mc2` (Multiple-Choice 2). In the current code (`run_benchmarks.py:176`), `truthfulqa_gen` is used — should be changed to `truthfulqa_mc1`.

#### 7.7.6 HellaSwag Score=0 for Granite models

**Severity: 🟡 Medium** | **Affected: 3/3 Granite models**

| Model | HellaSwag |
|---|---|
| Granite 4.1 30B I1 | 0 |
| Granite 4.0 H Tiny | 0.23 |
| Granite 4.1 8B | 0 |
| Qwen3 30B A3B | 0.72 |

**Likely cause:** Similar to ARC — Granite models return **only the letter A/B/C/D**, not the full sentence completion → `custom-extract` regex does not match.

**Code location:** `lm_eval/tasks/hellaswag/hellaswag_gen.yaml` (lm_eval built-in) — the `custom-extract` regex extracts text before the letter, which is empty with pure letter answers.

#### 7.7.7 DS1000 + CoderEval Score=0 for Granite models

**Severity: 🟠 High** | **Affected: 3/3 Granite models**

Granite 4.1 30B I1: DS1000 0% (all 10 tasks FAILED), CoderEval 0% (all 10 tasks 0/N tests passed)
Granite 4.0 H Tiny: DS1000 0% (FAILED), CoderEval 0% (all 0/N)
Granite 4.1 8B: DS1000 0% (FAILED), CoderEval 0% (all 0/N)

**But:** Granite 4.1 30B (non-i1): HumanEval+ 0.860, MBPP+ 0.619 — so EvalPlus works normally.

**Hypothesis:** Granite models write **valid Python**, but the code is incorrectly processed by `_unwrap_solution_for_insert` (DS1000) or `extract_code` (CoderEval). Granite may have a different code block style (e.g., `def` without `class`, or imports in a different order).

#### 7.7.8 DS1000 + CoderEval 0% for Granite is NOT a sandbox error

The errors in the terminal output are specific: "Harness error: failed: <numpy comparison>" for DS1000 and "Direct tests: 0/N passed" for CoderEval. The **sandbox system itself works** (no `Permission denied`, no crashes). It is a **code parsing problem**.

**Possible cause:** Granite models write code in a different style than expected (e.g., without the `[insert]` marker the DS1000 harness looks for). See `custom_benchmark.py:1036-1110` (`_unwrap_solution_for_insert`).

#### 7.7.9 Granite 4.0 H Tiny loads with 24 instead of 64 experts — Workaround in LM Studio

See `Modell_Steckbriefe_20260711.md:448-456` for `num_experts=16-24` workaround. This is not directly a Python bug, but an indication that the model profile configuration is not applied automatically — the user must set it manually in LM Studio.

#### 7.7.10 Encoding Bugs in PowerShell Terminal Output

**Severity: 🟢 Low**

The markdown file contains multiple broken Unicode characters:
- `�?` instead of `×` (multiplication sign)
- `�%^0%` instead of `≈0%` (approximately equal)
- `▒` instead of arrow codepoints
- `�?` instead of emojis

**Cause:** PowerShell console on Windows uses cp1252 or Windows-1252, not UTF-8. The code sets `sys.stdout.reconfigure(encoding="utf-8")` in `custom_benchmark.py:1588-1592`, but this only affects Python output. PowerShell redirect to file can switch to Windows codepage in between.

**Recommended Fix:** Set `PYTHONIOENCODING=utf-8` and `chcp 65001` as subprocess environment variables in `run_benchmarks.py` (already partially set in line 715, but not for launcher).

#### 7.7.11 Run was prematurely aborted with Ctrl-C

**Severity: ℹ️ Info**

The terminal output ends with "aborted with Ctrl-C in PowerShell" (line 2753). The run only completed 8/14 models fully. Models 9-14 (GLM 4.7 Flash, LFM2 24B, GPT-OSS 20B × 2) were not processed.

**Impact:** Consolidated results for models 9-14 are missing from the evaluation.

---

## 8. Recommendations (prioritized)

### 🔴 Prio 1 (immediate) — ✅ ALL FIXED (2026-07-12)

1. ✅ **Fix `tests/test_csv.py:4`** — Import to v13, fixture created
2. ✅ **Channel error handling** in `custom_benchmark.py` — Auto-fallback to `--no-structured-output` via `[CHANNEL-ERROR]` marker
3. ✅ **`wait_for_model_ready` timeout** to 60s — Default 90s → 120s as safety net
4. ✅ **Reload logic** via `_ensure_model_still_loaded()` helper extended to all 4 pipelines

### 🟠 Prio 2 (soon) — ✅ ALL FIXED (2026-07-12)

5. ✅ **Fix `_lookup_vram` fuzzy match** — Length-ratio guard >=0.85, expanded publisher prefix list, `best_score` tracking
6. ✅ **`strip_thinking_tokens` token estimation** — `max(word_count * 1.3, char // 4)` + whitespace special case (1 token per 64 chars)
7. ✅ **`QUANT_MAP` conflict resolution** — `get_quant()` helper with explicit priority (exact > suffix > base)
8. ✅ **`response` column compressed** — `--keep-response` CLI flag, `_truncate_response()` (default 200 chars)
9. ✅ **Bootstrap-CI on NumPy** — `np.random.randint` + `np.partition`, 300-500x speedup (9-12ms instead of 3-5s)

### 🟡 Prio 3 (refactoring) — ✅ ALL FIXED (2026-07-12)

10. ✅ **MMLU-Pro-Code** — `run_mmlupro_modified` + MMLU aggregation removed from `consolidate_results.py`. **Self-contained archive script** created: `Archiv/run_mmlupro_benchmark.py` (can be called standalone if needed, without touching the active launcher). `MMLU_PRO_SUBSETS` remains in `benchmark_config.py` with `MMLU_PRO_ENABLED = False`.
11. ✅ **Legacy aliases** in `csv_writer.py` + callers in `run_benchmarks.py` + `custom_benchmark.py` — `save_csv`, `save_model_summary`, `save_model_summary_csv` removed. Use the official function names directly.
12. ✅ **Subprocess path logging** in `run_benchmarks.py:139-153` — now outputs at startup: `[INFO] Using custom_benchmark script: custom_benchmark.py (version v13)`, subprocess interpreter, repo root.
13. ✅ **Duplicate thinking configuration** centralized in `benchmark_config.THINKING_CONFIG` (Prio 3.13). `MODEL_CONFIG` in `custom_benchmark.py` is now an alias to `THINKING_CONFIG`. Documentation in `thinking_config.md` is now correct.
14. ✅ **`download_real_benchmarks.py`** marked with DEPRECATED header. Install scripts now report `[INFO] download_real_benchmarks.py is DEPRECATED`.

### 🟢 Prio 4 (long-term) — ✅ MOSTLY FIXED (2026-07-12)

15. ✅ **CI with GitHub Actions** — `.github/workflows/ci.yml` with 3 jobs (test, lint, typecheck). `pyproject.toml` with `ruff` + `pytest` + `mypy` configuration.
16. 🟡 **Test coverage to 60%+** — currently estimated ~10% (previously 5%; added: `test_dependencies.py` 7, `test_prio2_terminal.py` 25). Increasing to 60% would require LM-Studio mocking.
17. ✅ **README + doc versioning** — `VERSION` file (Single Source of Truth) created. README now points to `VERSION`. Architecture doc updated with `v13.0.0-p3`. Launcher reads version from `VERSION` file.
18. ✅ **Version convention** — `VERSION` file + `pyproject.toml` + `__version__` in `run_benchmarks.py` synced.

---

## 7.8 Subsequently Discovered Findings (2026-07-12)

**These findings were identified after the initial review through the user's reference to the file `Terminalausgabe Benchmark Run mit neuen Benchmarks und SampleSize 10.md`. They were NOT part of the original review scope.**

### Fix Status of all Prio-0/2/3 findings (2026-07-12)

| # | Finding | Severity | Status | Changed Files |
|---|---------|----------|--------|---------------|
| 19 | `langdetect` missing → IFEval 14/14 fail | 🔴 | ✅ FIXED | `install_benchmark-data_windows.ps1`, `install_benchmark-data_debian.sh`, `README.md`, `tests/test_dependencies.py` |
| 20 | `math_verify`/`sympy`/`antlr4==4.11` missing → MATH-500 14/14 fail | 🔴 | ✅ FIXED | (same files) |
| 20+ | `immutabledict` missing → IFEval transitive dep | 🔴 | ✅ FIXED | (same files) |
| 21 | Update install scripts | 🟠 | ✅ FIXED | `install_benchmark-data_windows.ps1` + Debian + README |
| 22 | `truthfulqa_gen` → `truthfulqa_mc1` | 🟠 | ✅ FIXED | `run_benchmarks.py:176`, `consolidate_results.py:661`, `run_np_calibration.ps1:93` |
| 23 | DS1000 `_unwrap_solution_for_insert` | 🟠 | ✅ FIXED | `custom_benchmark.py:1090-1175` — multiple `[insert]` markers, comment-skip, synthetic function wrapper |
| 24 | DS1000 matplotlib `set_xticklabels` patch | 🟠 | ✅ FIXED | `custom_benchmark.py:_patch_matplotlib_compat()` (new) |
| 25 | CoderEval `extract_code` Granite | 🟠 | ✅ FIXED | `custom_benchmark.py:775-832` — alternative code-block patterns, bare-statement fallback |
| 26 | PowerShell UTF-8 encoding | 🟢 | ✅ FIXED | `run_missing_benchmarks.ps1`, `run_np_calibration.ps1`, `run_v18_models.ps1` |

**Test suite:** `pytest tests/` → **43/43 passed** (previously 36/36; +7 for `tests/test_dependencies.py`).

### Original Findings (for reference)

### 🔴 Prio 0 — Dependencies missing (all IFEval + MATH-500 runs are data garbage)

19. **`pip install langdetect`** — IFEval cannot be executed, all 14 models return `ModuleNotFoundError: No module named 'langdetect'`. **Consequence:** IFEval scores completely missing, consolidation cannot compute Agentic+IFEval mix.
20. **`pip install lm-eval[math]`** (or `sympy` + `math_verify` + `antlr4-python3-runtime==4.11`) — MATH-500 cannot be executed, all 14 models return `ModuleNotFoundError`. **Consequence:** `Math` score in `consolidate_results.py:compute_category_scores` is `None` for all models, **the entire `cat_weights["math"]` is useless**.
21. **Update install script** — `Doku-intern/Doku-intern/install_benchmark-data_windows.ps1` must install these dependencies. Currently this hint is completely missing.

### 🟠 Prio 2 — Benchmark Configuration

22. **`truthfulqa_gen` → `truthfulqa_mc1`** in `benchmark_config.py:177` and `run_benchmarks.py:176` — `bleu_acc=0` because models only return letters A/B/C/D, not full answer texts. `mc1` extracts the correct choice.
23. **Revise DS1000-Harness `_unwrap_solution_for_insert`** (`custom_benchmark.py:1036-1110`) — the code-stripping logic loses too much code with Granite models. Tests with longer `[insert]` markers fail.
24. **DS1000 matplotlib-API compat:** `set_xticklabels` patches → `ax.set_xticklabels(...)`. Generated code calls `plt.set_xticklabels`, which no longer exists in newer Matplotlib versions.
25. **Improve CoderEval `extract_code`** (`custom_benchmark.py:721-764`) — Granite models write code in a different style (no markdown wrapper) and are extracted as empty string.

### 🟡 Prio 3 — Log/Encoding

26. **Fix PowerShell encoding** — `PYTHONIOENCODING=utf-8` and `chcp 65001` in PowerShell wrapper scripts (`run_missing_benchmarks.ps1`, `run_np_calibration.ps1`) for clean Unicode output in terminal logs.

---

## 9. Overall Positive Assessment

Despite the above findings, the code quality is above average:

- **Clear architecture** with clean layer separation
- **Deterministic reproducibility** (--seed, Bootstrap-CI)
- **Robust error handling** (streaming retries, sandbox blocklist, timeouts)
- **Structured logging** (CPU/GPU/RAM/VRAM per task, thinking ratio)
- **Statistical significance** (weighted, bootstrap-CI, pair comparisons)
- **Comprehensive documentation** (model profiles, architecture, thinking config, parallel slots optimization)

The main areas of concern are: (a) broken tests, (b) channel error handling with `response_format`+`lazy grammar` incompatibility, (c) some fuzzy match bugs in consolidation. All can be specifically fixed in 1-2 sprints.

---

*Review created on 2026-07-12 (Plan Mode) – no code changes made.*
