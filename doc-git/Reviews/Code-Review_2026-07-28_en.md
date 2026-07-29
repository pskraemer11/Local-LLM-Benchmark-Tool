# Code-Review 2026-07-28 — ISO/IEC 9126 Quality Review

> **Status:** Deep-Dive Code Analysis after Phase p8 (Rename-Cleanup, CI/CD, further Registry Cleanup)
> **Methodology:** [ISO/IEC 9126](https://de.wikipedia.org/wiki/ISO/IEC_9126) — the 6 main characteristics: Functionality, Reliability, Usability, Efficiency, Maintainability, Portability.
> **Scope:** 9 main scripts (7,925 LOC code-only) + 14 test files (3,948 LOC, 559 tests green) + YAML registry (124 entries). As of 28.07.2026.
> **Previous Reviews:** `doc-git/Reviews/Code-Review_2026-07-27.md` (8.5/10), `doc-git/Reviews/Code-Review_2026-07-20.md` (7.75/10)

---

## 1. Inventory & Status

### 1.1 Source Code Inventory (9 scripts, code lines without comments/blank lines)

| File                       |   LOC  | Funcs | Classes | Typ-Hints | Docstrings | Note                                 |
|-----------------------------|-------:|------:|--------:|-----------|------------|--------------------------------------|
| `run_benchmarks.py`         |  1,162 |   33  |    0    |   97%     | ~34%       | `main()` 329 lines — largest function    |
| `custom_benchmark.py`       |  1,736 |   55  |    2    |   88%     | ~44%       | `generate_answer()` with 16 parameters  |
| `consolidate_results.py`    |  1,333 |   39  |    1    |   81%     | ~48%       | `read_data()` 206 lines                   |
| `registry_tool.py`          |  1,477 |   44  |    0    |   93%     | ~55%       | `cmd_validate()` 156 lines                |
| `assemble_blueprint.py`     |    880 |   23  |    0    |  *59%*    | ~65%       | *Weakest type-hint coverage*         |
| `benchmark_config.py`       |    336 |    4  |    0    |  100%     | ~75%       | Smallest file, best ratio             |
| `model_manager.py`          |    453 |   13  |    0    |   92%     | ~77%       | Best docstring coverage               |
| `csv_writer.py`             |    382 |   11  |    0    |  *55%*    | ~55%       | *Second weakest type hints*             |
| `tools/lmeval_proxy.py`     |    166 |   12  |    1    |   N/A     | N/A        | Proxy for LM-Eval Native API          |
|-----------------------------|-------:|------:|--------:|-----------|------------|----------------------------------------|
| *TOTAL*                     | *7,925*| *234* |   *4*   | *~87%*    | *~50-60%*  |                                        |

** => after the review all retrofitted with 100% type hints!

### 1.2 Test Inventory (14 test files)

| Metric                    | Value         |
|---------------------------|--------------:|
| Test files                |    14         |
| Test functions            |   559         |
| Test LOC                  | 3,948         |
| Test-to-Source Ratio      |   1:2         |
| Status                    | **All green** (4.06s)     |
| CI/CD                     |`.github/workflows/ci.yml` |
|                           |   with pytest + ruff + mypy |

### 1.3 Registry Status

| Aspect                            | Value         | Delta to 27.07. |
|-----------------------------------|--------------:|----------------:|
| Registered models                 | **124**       |    +9           |
| Of which with `quants`            |    88 (71%)   |    +9           |
| Of which with `reasoning`         |   124 (100%)  |     —           |
| Of which with `capabilities`      |   124 (100%)  |     —           |
| Of which with `blueprint`         |   124 (100%)  |     —           |
| Of which with `context_length`    |   124 (100%)  |     —           |
| Of which with `truncation`        |   115 (93%)   |     —           |
| Of which with `arch`              |   124 (100%)  |     —           |
| Of which with `n_layers`/`hidden_dim` | 87 (70%)   |   +12           |
| Of which with `template`          |    18 (15%)   |     —           |
| Of which with `experts` (MoE)     |    33 (27%)   |     —           |
| Reasoning modes: `thinking`       |    61         |     —           |
| Reasoning modes: `instruct`       |    63         |     —           |

### 1.4 Fixes Since Last Review

#### 1.4.1 Rename Cleanup (p8)

Three `_v13`-suffixed files renamed to clean names:

| Old Name                       | New Name                 | Action                           |
|--------------------------------|--------------------------|----------------------------------|
| `run_benchmarks_v13.py`        | `run_benchmarks.py`      | `git mv` + versioning removed    |
| `custom_benchmark_v13.py`      | `custom_benchmark.py`    | `git mv` + versioning removed    |
| `consolidate_results_v13.py`   | `consolidate_results.py` | `git mv` + versioning removed    |

**Versioning logic removed:** `VERSION`, `VERSION_SUFFIX`, `VERSION_FILE` deleted from all 3 files. No more `version.txt` write access.

#### 1.4.2 CI/CD Pipeline (new)

`.github/workflows/ci.yml` with 4 jobs:
- **test**: pytest on Python 3.11/3.12/3.13 with `lm-eval`, `evalplus`, `nvidia-ml-py3`
- **lint**: `ruff --select E,F` (Errors + Pyflakes)
- **typecheck**: `mypy` lenient on `benchmark_config.py`, `csv_writer.py`
- **summary**: Aggregated status of all jobs

#### 1.4.3 Registry Extended to 124 Entries (+9)

New entries (from `registry_tool.py sync` or manual):
- Intel AutoRound variants (Qwen3, Qwen3-Coder, Mirothinker)
- Additional MoE variants (Qwen3-Coder-Reap, GLM-4.7-Flash-Reap)
- MXFP4 entry (`jetbrains/mellum2-12b-a2.5b-thinking-mxfp4`)

#### 1.4.4 `truncation` Gaps Closed

9 entries without `truncation` identified (all Intel AutoRound + 2 new MXFP4 entries). ~93% coverage, 9% still open.

#### 1.4.5 `tools/lmeval_proxy.py` Native API Integration

Proxy for LM-Eval Native API endpoint:
- `reasoning='off'` via NATIVE API (`/api/v1/chat/completions`)
- Timeout 300s → 900s for MATH-500 (8192 tokens at 10 tok/s = 819s)
- Single `except Exception:` in error-body parsing (acceptable)

#### 1.4.6 DS1000 Broken API Filter

`custom_benchmark.py`: Filter for tasks with broken APIs (e.g. `interp2d` in `code_context`) — prevents silent failures.

#### 1.4.7 Chat Template Injection for Gemma-4 + Granite

`assemble_blueprint.py`: `find_all_configs_for_registry_key()` + chat template injection for models without Jinja template in LMS.

---

## 2. ISO/IEC 9126 — Rating per Main Characteristic

### 2.1 Functionality · Rating: 8.5/10 · Very Good

| Sub-characteristic | Rating | Finding                                                                              |
|-------------------|-------:|--------------------------------------------------------------------------------------|
| Suitability       |    9/10   | Four independent pipelines, 9 benchmarks, DS1000-broken-API filter                    |
| Accuracy          |    9/10   | Bootstrap CIs, median/P90, weighted consolidation; VRAM formula for `useUnifiedKvCache` |
| Interoperability  |    8/10   | OpenAI-compatible + Native API; JSON configs bidirectional LMS ↔ Registry            |
| Security          |    8/10   | `_validate_model_identifier()` prevents subprocess injection; `_VALID_MODEL_KEY_RE`   |
| Compliance        |    8/10   | CI/CD with 3 Python versions; `pyproject.toml` declares Python ≥3.11                  |

**Strengths:**
- **CI/CD pipeline** (new): GitHub Actions with test/lint/typecheck — first-time automated quality assurance
- **Registry data quality**: 100% of 124 entries have `reasoning`, `capabilities`, `blueprint`, `context_length`, `arch`
- **`get_quant()` rewrite**: 5-level priority with YAML cache (since p7)
- **DS1000 broken API filter**: tasks with broken APIs are sorted out before the run

**Weaknesses:**
- **EXCLUDE_KEYWORDS drift** (Prio 2, unchanged): keyword lists in 3 files without single source of truth
- **`_infer_num_parallel()`**: underestimates for MoE models with 16+ experts (unchanged)
- **36 entries without `quants`**: `registry_tool.py sync` not yet executed
- **9 entries without `truncation`**: Intel AutoRound + MXFP4 entries

---

### 2.2 Reliability · Rating: 9/10 · Very Good

| Sub-characteristic | Rating | Finding                                                                   |
|-------------------|-------:|---------------------------------------------------------------------------|
| Maturity        |    9/10   | 559 tests green, p1-p8 documented, CI/CD validated                          |
| Availability    |    9/10   | Task retry with exponential backoff; model reload on unexpected unload      |
| Fault-tolerance |    9/10   | Bare-except reduction to 3 remaining (from 35 in p1)                        |
| Recoverability  |    9/10   | Channel error auto-fallback; SIGALRM fix; proxy timeout increase            |

**Strengths:**
- **Bare-except reduction**: 3 remaining `except Exception:`:
  1. `custom_benchmark.py:1080` — string literal in code generator (acceptable, written into generated files)
  2. `model_manager.py:128` — error-body JSON parsing in REST API helper (acceptable, fallback to text)
  3. `tools/lmeval_proxy.py:57` — error-body parsing in proxy (acceptable, fallback to `str(e)`)
- **Proxy timeout**: 300s → 900s for MATH-500 (8192 tokens at 10 tok/s)
- **559 tests in 4.06s**: all green, fast execution

**Weaknesses:**
- **`test_model_manager.py:895`**: `is_model_ready(timeout=5)` assertion removed (unmocked, hit real LMS API)
- **`is_api_available()`**: broad catch in `model_manager.py:128` is intentional but notoriously hard to test

---

### 2.3 Usability · Rating: 7/10 · Good

| Sub-characteristic | Rating | Finding                                                         |
|-------------------|-------:|----------------------------------------------------------------|
| Understandability |    8/10   | Extensive `doc-git/` documentation (7+ Markdown files)           |
| Learnability      |    7/10   | Quick start in README, CLI table; no tutorial notebook           |
| Operability       |    7/10   | Interactive + non-interactive mode; `--json` output              |
| Attractiveness    |    6/10   | Terminal output ASCII-only, no colors/progress bars              |
| Error-handling UX |    8/10   | `[INFO]`/`[WARN]`/`[ERROR]`/`[OK]`/`[CHANNEL-ERROR]` prefixes   |

**Strengths:**
- **Registry tool**: interactive CLI for registry maintenance (`cmd_*` functions)
- **`--json` flag**: structured output for scripting
- **`read_model_yaml()`**: automatic detection of `model.yaml` from LMS hub

**Weaknesses:**
- **No visual indicators**: no colors, no progress bar for long pipelines
- **Subprocess output unstructured**: agentic pipeline prints JSON envelope multiple times
- **`generate_answer()` with 16 parameters**: extremely hard to call manually

---

### 2.4 Efficiency · Rating: 8/10 · Very Good

| Sub-characteristic | Rating | Finding                                                       |
|-------------------|-------:|---------------------------------------------------------------|
| Time behaviour |    9/10   | YAML cache prevents re-parsing; GGUF header reader ~1ms         |
| Resource usage |    8/10   | VRAM formula for `useUnifiedKvCache`; 5Hz monitor              |
| Capacity       |    8/10   | 16 GB VRAM sufficient for 27-30B Q3_K_S MoE                    |

**Strengths:**
- **YAML cache** (`get_quant()`): `model_registry.yaml` parsed once
- **GGUF header reader**: ~1ms vs ~5-7s with `GGUFReader` — 3500-7000x speedup
- **Median/P90 instead of Mean/Max**: robust against outliers

**Weaknesses:**
- **`time.sleep(10)` after model load** (unchanged): fixed sleep instead of adaptive polling
- **`PIPELINE_TIMEOUTS["agentic_subprocess"]=3600`**: 60min wait time for hung scenario

---

### 2.5 Maintainability · Rating: 8.5/10 · Very Good

**Phase p8 (rename cleanup) completed. CI/CD pipeline new. Code quality analysis performed for the first time.**

| Sub-characteristic | Rating | Finding                                                                        |
|-------------------|-------:|--------------------------------------------------------------------------------|
| Analyzability |   8/10    | Type hints ~87%, but 2 files <60%; many `main()` functions >200 lines          |
| Changeability |   9/10    | Single source of truth in `benchmark_config.py` and `model_registry.yaml`       |
| Stability     |   9/10    | 559 tests green, CI/CD validated                                               |
| Testability   |   9/10    | 14 test files, `pytest >= 8.0`, mypy/ruff in CI                                |

**Strengths:**
- **Rename cleanup**: `_v13` suffix removed, versioning logic deleted. Clean root directory.
- **CI/CD pipeline** (new): automated quality assurance on every push/PR
- **Type hints**: ~87% of functions have return type annotations
- **Exception handling**: only 3 remaining `except Exception:` — all documented and acceptable
- **`get_quant()` rewrite**: clear 5-level priority with YAML cache

**Weaknesses (code quality):**
- **18+ functions >100 lines**: the largest are `run_benchmarks.main()` (329 lines), `custom_benchmark.main()` (248 lines), `consolidate_results.read_data()` (206 lines)
- **`generate_answer()` with 16 parameters**: strongest design smell in the entire project
- **Global mutable state**: 10+ module variables (`IS_THINKING_ENABLED`, `_REGISTRY_CACHE`, etc.) — acceptable for single-threaded, but hindering for parallelization
- **Code duplication**: `run_task()` in `custom_benchmark.py` has `data_science`/`codereval` branches with ~80% identical code
- **Type hint gaps**: `assemble_blueprint.py` (59%) and `csv_writer.py` (55%) have significant catching up to do
- **`registry_tool.py` ↔ `assemble_blueprint.py`**: overlapping functionality (normalize_model_name)

---

### 2.6 Portability · Rating: 7/10 · Acceptable with Limitations

| Sub-characteristic | Rating | Finding                                                             |
|-------------------|-------:|---------------------------------------------------------------------|
| Adaptability   |    6/10   | Hardcoded `127.0.0.1:1234` and `C:\Users\pskra\.lmstudio` paths      |
| Installability |    9/10   | `pyproject.toml` + `requirements-dev.txt`; CI/CD installs            |
| Conformance    |    7/10   | Python ≥3.11; OpenAI-compatible + LM Studio-specific                 |
| Replaceability |    7/10   | LM Studio only; adapter layer in `model_manager.py`                  |

**Strengths:**
- **`os.path.join`, `Path` usage consistent**
- **`.gitignore`**: excludes `lms_models.txt`, `__pycache__`, `embedding-eval/`
- **CI/CD on Ubuntu**: Linux compatibility tested (3 Python versions)

**Weaknesses:**
- **`run_benchmarks.py:1002`**: hardcoded `"--base-url", "http://127.0.0.1:1234/v1"`
- **LM Studio only**: no vLLM/Ollama/TGI fallback
- **Windows patches in DS1000 framework** not documented for Linux
- **Hardcoded user paths**: `C:\Users\pskra` in multiple configurations

---

## 3. Consolidated Findings — Priority List

| Prio | Finding                                               | Category       | Effort | Status                             |
|:----:|-------------------------------------------------------|----------------|--------|------------------------------------|
| *P1* | *`_v13` rename + versioning removed*                  | Maintainability | Small  | **DONE (p8)**                      |
| *P1* | *CI/CD pipeline missing*                              | Maintainability | Medium | **DONE (p8): .github/workflows/ci.yml** |
| *P1* | *last bare `except Exception:` blocks*                | Reliability     | Small  | **DONE (p8): 3 remaining, all acceptable** |
|  P2  | EXCLUDE_KEYWORDS duplicated in 3 files                | Functionality   | Small  | Open                                |
|  P2  | `time.sleep(10)` instead of adaptive polling          | Efficiency      | Medium | Open                                |
|  P2  | `_infer_num_parallel()` underestimates for MoE        | Functionality   | Small  | Open                                |
|  P2  | 36 registry entries without `quants`                  | Functionality   | Small  | Open (sync pending)                 |
|  P2  | 9 entries without `truncation`                        | Functionality   | Small  | Open (new)                          |
|  P3  | `generate_answer()` with 16 parameters                | Maintainability | Medium | Open (new)                          |
|  P3  | `main()` functions >200 lines (3 locations)           | Maintainability | Medium | Open (new)                          |
|  P3  | `assemble_blueprint.py` + `csv_writer.py` type hints  | Maintainability | Small  | Open (new)                          |
|  P3  | Global mutable state variables (10+)                  | Maintainability | Medium | Open (new)                          |
|  P3  | No visual progress bar                                | Usability       | Medium | Open                                |
|  P3  | `run_task()` duplication (data_science/codereval)    | Maintainability | Medium | Open (new)                          |
|  P4  | DS-1000 Windows patches not for Linux                 | Portability     | Small  | Open                                |
|  P4  | `registry_tool.py` ↔ `assemble_blueprint.py` consolidation | Maintainability | Medium | Open                          |

---

## 4. Recommendations

### 4.1 Immediate (before next benchmark run)

1. **Run `python registry_tool.py sync`** → refresh 36 entries without `quants`.
2. **Add `truncation` for 9 Intel AutoRound/MXFP4 entries**.
3. **Run tests** (`python -m pytest tests/ --tb=short -q`) — confirm 559/559 green.

### 4.2 Maintenance Sprint

4. **`generate_answer()` refactoring**: 16 parameters → config object or `**kwargs`. Largest design smell.
5. **Split `main()` functions**: `run_benchmarks.py:329` lines, `custom_benchmark.py:248` lines, `consolidate_results.py:143` lines — each should be decomposed into orchestration phases.
6. **Bring type hints in `assemble_blueprint.py` and `csv_writer.py`** to 100%.
7. **Resolve `run_task()` duplication**: extract common logic for `data_science`/`codereval` branches.
8. **Encapsulate global state variables**: `IS_THINKING_ENABLED`, `_REGISTRY_CACHE`, etc. into classes or config objects.

### 4.3 Medium-term

9. **EXCLUDE_KEYWORDS single source of truth**: central list in `benchmark_config.py`, import in `run_benchmarks.py` and `consolidate_results.py`.
10. **`_infer_num_parallel()` revisited**: MoE-specific heuristic for qwen3moe (16 experts), ernie4_5-moe (14 experts).
11. **`time.sleep(10)` → adaptive polling**: replace with polling loop with timeout.

### 4.4 Long-term

12. **LMS-independent test fixtures**: `responses` mocks for CI without LMS.
13. **`run_benchmarks.py:1002`**: replace hardcoded URL with `from model_manager import API_BASE`.
14. **`registry_tool.py` ↔ `assemble_blueprint.py` consolidation**: common helpers into own module.

---

## 5. Code Quality Detail Analysis (first time)

### 5.1 Type Hint Coverage per File

| File                       | Coverage | Rating      |
|-----------------------------|----------|-------------|
| `benchmark_config.py`       |    100%   | Excellent   |
| `run_benchmarks.py`         |     97%   | Excellent   |
| `registry_tool.py`          |     93%   | Very good   |
| `model_manager.py`          |     92%   | Very good   |
| `custom_benchmark.py`       |     88%   | Good        |
| `consolidate_results.py`    |     81%   | Good        |
| `assemble_blueprint.py`     |     59%   | **Needs improvement** |
| `csv_writer.py`             |     55%   | **Needs improvement** |
| **TOTAL**                   |   **~87%**| Very good   |

### 5.2 Exception Handling Quality

| File                       | `except Exception:` | Rating      |
|-----------------------------|--------------------:|-------------|
| `run_benchmarks.py`         | 0                   | Perfect     |
| `custom_benchmark.py`       | 1 (string literal)  | Acceptable  |
| `consolidate_results.py`    | 0                   | Perfect     |
| `registry_tool.py`          | 0                   | Perfect     |
| `assemble_blueprint.py`     | 0                   | Perfect     |
| `benchmark_config.py`       | 0                   | Perfect     |
| `model_manager.py`          | 1 (error-body parse)| Acceptable  |
| `csv_writer.py`             | 0                   | Perfect     |
| `tools/lmeval_proxy.py`     | 1 (error-body parse)| Acceptable  |
| **TOTAL**                   | **3**               | **Very good (from 35 in p1)** |

**All 3 remaining are documented and acceptable (no `pass`, always fallback logic).**

### 5.3 Largest Functions (>100 lines)

| Function                                 | File                     | Lines | Problem |
|------------------------------------------|---------------------------|------:|---------|
| `main()`                                 | `run_benchmarks.py`       |  329   | 7 concerns: model-load, registry-validation (7 checks), benchmark-dispatch, summary |
| `main()`                                 | `custom_benchmark.py`     |  248   | 4 concerns: config, model-load, pipeline-dispatch, error-handling |
| `read_data()`                            | `consolidate_results.py`  |  206   | 2 concerns: CSV parsing + data transformation |
| `cmd_validate()`                         | `registry_tool.py`        |  156   | 3 concerns: schema check, GGUF read, reporting |
| `create_blueprint_definitions()`          | `assemble_blueprint.py`   |  154   | Mostly data definition (acceptable) |
| `assemble_prompts()`                     | `assemble_blueprint.py`   |  152   | 4 concerns: registry lookup, blueprint selection, prompt assembly, validation |
| `run_task()`                             | `custom_benchmark.py`     |  148   | Duplicated data_science/codereval branches |
| `main()`                                 | `consolidate_results.py`  |  143   | 4 modes: normal, compare, merge, paired bootstrap |
| `cmd_fill_arch()`                        | `registry_tool.py`        |  138   | GGUF reading + registry update |
| `benchmark_model()`                      | `custom_benchmark.py`     |  135   | Pipeline orchestration |
| `_unwrap_solution_for_insert()`          | `custom_benchmark.py`     |  129   | DS1000 insert logic |
| `find_latest_csvs()`                     | `consolidate_results.py`  |  124   | CSV discovery + filter |
| `_worker()`                              | `custom_benchmark.py`     |  116   | Streaming + rate limiting (nested) |

### 5.4 Functions with Too Many Parameters (>6)

| Function                       | File                     | Parameters |
|--------------------------------|---------------------------|----------:|
| `generate_answer()`            | `custom_benchmark.py`     | **16**    |
| `_stream_chat_completion()`    | `custom_benchmark.py`     | 10        |
| `get_model_config()`           | `benchmark_config.py`     | 9         |
| `_call_lm_studio()`            | `custom_benchmark.py`     | 7         |
| `run_lmeval()`                 | `run_benchmarks.py`       | 7         |
| `_download_with_progress()`    | `custom_benchmark.py`     | 7         |
| `cmd_validate()`               | `registry_tool.py`        | 6         |

---

## 6. Statistical Comparison

| Metric                         | Review   | Review   | Review   | Delta to |
|                                |2026-07-20|2026-07-27|2026-07-28| 27.07.   |
|--------------------------------|----------|----------|----------|----------|
| *Overall rating (ISO/IEC 9126)* | 7.75/10  | *8.5/10* | *8.5/10* |    —     |
| Functionality                  |  8/10    |  8.5/10  |  8.5/10  |    —     |
| Reliability                    |  8/10    |  9/10    |  9/10    |    —     |
| Usability                      |  7/10    |  7/10    |  7/10    |    —     |
| Efficiency                     |  8/10    |  8/10    |  8/10    |    —     |
| Maintainability                |  8.5/10  |  9/10    |  8.5/10  | **-0.5** |
| Portability                    |  7/10    |  7/10    |  7/10    |    —     |
| Tests (green)                  | 547      | 564      | 559      |  -5      |
| Registry entries               | 108      | 115      | **124**  |  +9      |
| Core LOC (9 scripts, code-only)|   —      |    —     | 7,925    |    —     |
| Test LOC (14 files)            |   —      | 5,566*   | 3,948    |    —     |
| Bare `except Exception:`       |  16+     |   6      |   **3**  |  -3 (↓50%) |
| CI/CD pipeline                 | No       | No       | **Yes**  |  +1      |

*\* Note 27.07.: 5,566 LOC was presumably total lines (incl. blank lines/comments). 3,948 LOC is code-only.*

**Important note on Maintainability -0.5:** The reduction from 9/10 to 8.5/10 is not a regression, but a **more precise rating** thanks to the first-time in-depth code quality analysis. The 18+ functions >100 lines, `generate_answer()` with 16 parameters, and 10+ global state variables were already present before, but were not captured in detail.

---

## 7. Reviewer Summary

**Overall rating according to ISO/IEC 9126 (subjective, 0-10):**

| Characteristic | Rating | Trend |
|----------------|-------:|-------|
| Functionality   |    8.5    | Stable |
| Reliability     |    9      | Stable |
| Usability       |    7      | Stable |
| Efficiency      |    8      | Stable |
| Maintainability |    8.5    | *Refined* |
| Portability     |    7      | Stable |
| *Overall*       |   *8.5*   | Stable |

**Comment:** The codebase remains at a high level (8.5/10). The three new items in this review — rename cleanup (p8), CI/CD pipeline, and first in-depth code quality analysis — improve maintainability sustainability.

**For the first time**, concrete code smells were quantified: 18+ functions >100 lines, `generate_answer()` with 16 parameters, 10+ global mutable state variables. These were not explicitly captured in earlier reviews because the focus was on registry correctness and exception handling.

**Main improvement potential** remains in **maintainability** (code smell reduction) and **portability** (hardcoded paths, LM Studio lock-in). The CI/CD pipeline is an important step to automatically detect regressions.

**Next logical step:** A refactoring sprint (p9) focusing on:
1. `generate_answer()` → config object
2. `main()` splitting in 3 files
3. Type hints in the 2 laggards
4. Resolve duplication in `run_task()`
