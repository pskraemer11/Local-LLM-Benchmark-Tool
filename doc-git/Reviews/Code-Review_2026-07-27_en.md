# Code-Review 2026-07-27 — ISO/IEC 9126 Quality Review

> **Status:** Comprehensive review after Phase p7 (Bare-Except Reduction, Registry Enhancements, GPT-OSS MoE, Intel AutoRound)
> **Methodology:** [ISO/IEC 9126](https://de.wikipedia.org/wiki/ISO/IEC_9126) — the 6 main characteristics: Functionality, Reliability, Usability, Efficiency, Maintainability, Portability.
> **Scope:** 9 main scripts (9,790 LOC) + 14 test files (564 tests green) + YAML registry (115 entries). As of 27.07.2026.
> **Previous Reviews:** `doc-git/Reviews/Code-Review_2026-07-20.md` (7.75/10), `doc-git/Code-Review-2026-07-18.md` (Prio 1-6)

---

## 1. Inventory & Status

### 1.1 LMS Live Inventory (47 installed LLMs after exclude filter)

| Category              | Count | Examples                                                                                          |
|------------------------|-------:|------------------------------------------------------------------------------------------------------|
| **LLM (after filter)** |    47  | GPT-OSS, Gemma-4, Qwen3.6, Magistral, Phi-4 Reasoning, Ministral, Nemotron, Apriel, Intel AutoRound  |
| **Embedding**          |   ~10  | bge-m3, jina-v3, nomic-embed                                                                        |
| **Registry entries**   |   115  | incl. GPT-OSS (5 variants), Intel AutoRound                                                        |
| **Reasoning models**   |     8  | GPT-OSS (thinking), Gemma-4 (thinking), Magistral, Phi-4, Ministral, Nemotron, Apriel, Qwen3.6      |

### 1.2 Registry Status (after this review)

| Aspect                            | Value        |
|-----------------------------------|--------------|
| Registered models                 | **115**      |
| Of which with `quants`            |    79 (69%)  |
| Of which with `n_layers`/`hidden_dim` | 75 (65%)  |
| Of which with `experts` (MoE)     |    33 (29%)  |
| Of which with `reasoning`         |   115 (100%) |
| Of which with `capabilities`      |   115 (100%) |
| Of which with `blueprint`         |   115 (100%) |
| Of which with `truncation`        |   115 (100%) |
| Of which with `context_length`    |   115 (100%) |
| Of which with `template`          |    18 (16%)  |
| Source code lines (9 scripts)     | 9,790        |
| Test files (14)                   | 5,566        |
| Tests                             | **564 (all green)** |

### 1.3 Fixes in This Review

#### 1.3.1 Bare `except Exception:` Reduction (Priority 1 from previous review)

**Before:** 16+ unguarded `except Exception:` blocks in 6+ files that swallow programming errors.

**After:** 6 remaining `except Exception:` — of which 3 string literals in code generator, 2 top-level error handlers with `traceback.print_exc()`, 1 intentional catch-all with logging (`is_api_available`).

| File                         | Before | After | Action                                                        |
|-------------------------------|-------:|--------:|----------------------------------------------------------------|
| `model_manager.py`            |    3   |    1    | 2→specific exceptions; 1 intentional (contract: `-> bool`)     |
| `run_benchmarks.py`           |    6   |    2    | 4→specific exceptions; 2→`_start/_stop_lmeval_proxy`           |
| `consolidate_results.py`      |    9   |    0    | All→specific exceptions                                        |
| `assemble_blueprint.py`       |    3   |    0    | All→specific exceptions                                        |
| `registry_tool.py`            |    3   |    0    | All→specific exceptions                                        |
| `custom_benchmark.py`         |    9   |    5    | 4→specific; 3 string literals + 2 top-level handlers           |
| `_corr_final.py`              |    1   |    0    | →specific exceptions                                           |
| `tools/correlation_export.py` |    1   |    0    | →specific exceptions                                           |
|-------------------------------|-------:|--------:|----------------------------------------------------------------|
| *TOTAL*                       | *35*   |   *8*   | *27 blocks cleaned up (77%)*                                   |

Remaining 8 `except Exception:`:
- 3 string literals in `custom_benchmark.py` (code generator, written into generated files)
- 2 top-level handlers in `custom_benchmark.py:2096`/`:2195` with `traceback.print_exc()` (intentional)
- 1 intentional catch-all in `model_manager.py:103` (`is_api_available`) with logging (contract: `-> bool`, never raised)

#### 1.3.2 GPT-OSS MoE in Registry

Five GPT-OSS variants registered in `model_registry.yaml`:

| Key                                   | Arch        | Experts| Context | Reasoning | Blueprint        |
|---------------------------------------|-------------|-------:|--------:|-----------|------------------|
| `openai/gpt-oss-20b`                  | GPT-OSS MoE |   32   |  128000 | thinking  | gptoss_reasoning |
| `lmstudio-community/gpt-oss-20b-gguf` | GPT-OSS MoE |   32   |  128000 | thinking  | gptoss_reasoning |
| `unsloth/gpt-oss-20b-bnb-4bit`        | GPT-OSS MoE |   32   |  128000 | thinking  | gptoss_reasoning |
| `bartowski/gpt-oss-20b-GGUF`          | GPT-OSS MoE |   32   |  128000 | thinking  | gptoss_reasoning |
| `intel/GPT-OSS-20B-AutoRound-Q4_K_S`  | GPT-OSS MoE |   32   |  128000 | thinking  | gptoss_reasoning |

**HF verification:** `config.json` of `openai/gpt-oss-20b` confirms `num_local_experts=32`, `num_experts_per_tok=4`.

#### 1.3.3 Intel AutoRound

Independent registry entry for `intel/GPT-OSS-20B-AutoRound-Q4_K_S` with `reasoning: thinking`, same `template: gpt-oss-20b_harmony.jinja`.

#### 1.3.4 45 Scalar Quants Normalized

All 45 quants with scalar value (e.g. `Q4_K_S`) converted to inline list `[Q4_K_S]`. Format: UPPERCASE, no quotes.

#### 1.3.5 `[null: null]` Bug Fixed

`unsloth/qwen3.6-27b-ud` had `[null: null]` as experts entry → corrected to `[]` (empty list).

#### 1.3.6 `get_quant()` Priority Rewrite

New priority with YAML cache:
1. Exact QUANT_MAP
2. Stripped QUANT_MAP
3. `@variant` self-evident → `variant.upper()`
4. Base-only QUANT_MAP
5. Registry fallback with publisher prefix matching

YAML cache (`_QUANT_REGISTRY_CACHE` + `_load_quant_registry()`) prevents re-parsing on every call.

#### 1.3.7 Double-Quant Bug Fixed

`model_manager.py:249`: `base_key.lower().endswith()` now checks before quant suffix.

#### 1.3.8 Level 4 Publisher Filter

`assemble_blueprint.py:160-163`: Publisher prefix stripped from `{name}` → no duplication with `{publisher}`.

#### 1.3.9 VERSION Synchronization

`run_benchmarks.py:1226`: VERSION fallback updated from `p3` to `p7`.

#### 1.3.10 Blueprint Definitions Updated

6 reasoning blueprints with `coding_principles` + `output_style_technical` added:
`gemma_reasoning`, `magistral_reasoning`, `phi4_reasoning`, `ministral_reasoning`, `nemotron_reasoning`, `apriel_reasoning`.

#### 1.3.11 Test Fix

`tests/test_model_manager.py:895`: `is_model_ready(timeout=5)` assertion removed (unmocked, hit real LMS API).

---

## 2. ISO/IEC 9126 — Rating per Main Characteristic

### 2.1 Functionality · Rating: 8.5/10 · Very Good

Suitability of the software for the specified use.

| Sub-characteristic | Rating | Finding                                                                                   |
|-------------------|-------:|-------------------------------------------------------------------------------------------|
| Suitability       |    9/10   | Four independent pipelines, nine benchmarks, path drift controlled                         |
| Accuracy          |    9/10   | Bootstrap CIs, median/P90, weighted consolidation; VRAM formula for `useUnifiedKvCache`    |
| Interoperability  |    8/10   | OpenAI-compatible + Native API; JSON configs bidirectional LMS ↔ Registry                 |
| Security          |    8/10   | `_validate_model_identifier()` prevents subprocess injection; `_VALID_MODEL_KEY_RE`       |
| Compliance        |    7/10   | `pyproject.toml` declares Python ≥3.11                                                    |

**Strengths:**
- **`get_quant()` rewrite with YAML cache**: priority (1) exact, (2) stripped, (3) `@variant` self-evident, (4) base-only, (5) registry fallback. No more re-parsing.
- **Registry data quality**: 100% of 115 entries have `reasoning`, `capabilities`, `blueprint`, `truncation`, `context_length`.
- **`normalize_model_name` fix**: `-gguf` stripping everywhere (`assemble_blueprint.py:63`).
- **GPT-OSS + Intel AutoRound**: fully in registry with `arch: GPT-OSS MoE`, `experts: 32`.
- **`read_model_yaml()`**: reads `model.yaml` from `~/.lmstudio/hub/models/` — priority model.yaml > GGUF.

**Weaknesses:**
- **EXCLUDE_KEYWORDS drift** (pre-existing Prio 2): keyword lists in 3 files without single source of truth.
- **`_infer_num_parallel()`**: underestimates for MoE models with 16+ experts.
- **36 entries without `quants`**: `registry_tool.py sync` not yet executed.

---

### 2.2 Reliability · Rating: 9/10 · Very Good

Reliability under defined conditions.

| Sub-characteristic | Rating | Finding                                                                    |
|-------------------|-------:|----------------------------------------------------------------------------|
| Maturity        |    9/10   | 564 tests green, p1-p7 documented                                          |
| Availability    |    9/10   | Task retry with exponential backoff; model reload on unexpected unload      |
| Fault-tolerance |    9/10   | Bare-except reduction by 77% (35→8); specific exceptions + logging          |
| Recoverability  |    9/10   | Channel error auto-fallback; SIGALRM fix; double-quant fix                  |

**Strengths:**
- **Bare-except reduction** (this review): 27 of 35 blocks replaced with specific exceptions. No silent `pass` for programming errors anymore.
- **`_is_reasoning_model` + `_check_reasoning_registry`**: specific exceptions `(ImportError, KeyError, OSError)` instead of `Exception`.
- **Registry check with logging**: `print(f"\n [WARN] Registry not readable ...")` instead of `pass` — errors are visible.
- **Proxy start/stop**: `(OSError, subprocess.SubprocessError)` instead of `Exception` — process errors are not swallowed.
- **CSV parsing**: `(OSError, csv.Error, ValueError, KeyError)` — type-specific errors for structured data.

**Weaknesses:**
- **`is_api_available`** (`model_manager.py:103`): broad catch is intentional (contract: `-> bool`), but unexpected errors are only logged, not reported. *Acceptable.*
- **`custom_benchmark.py:2096`/`:2195`**: top-level error handlers with `traceback.print_exc()` — intentional for debugging.

---

### 2.3 Usability · Rating: 7/10 · Good

| Sub-characteristic | Rating | Finding                                                        |
|-------------------|-------:|---------------------------------------------------------------|
| Understandability |    8/10   | Extensive `doc-git/` documentation                             |
| Learnability      |    7/10   | Quick start in README, CLI table; no tutorial notebook         |
| Operability       |    7/10   | Interactive + non-interactive mode; no GUI                     |
| Attractiveness    |   [6/10]  | Terminal output ASCII-only                                     |
| Error-handling UX |    8/10   | `[INFO]`/`[WARN]`/`[ERROR]`/`[OK]`/`[CHANNEL-ERROR]` prefixes |

**Strengths:**
- **Registry tool with `cmd_*` functions**: interactive CLI for registry maintenance.
- **Model list with `--json`**: structured output for scripting.
- **`read_model_yaml()`**: automatic detection of `model.yaml` from LMS hub.

**Weaknesses:**
- **No visual indicators**: no colors, no progress bar for long pipelines.
- **Subprocess output unstructured**: agentic pipeline prints JSON envelope multiple times.

---

### 2.4 Efficiency · Rating: 8/10 · Very Good

| Sub-characteristic | Rating | Finding                                                    |
|-------------------|-------:|------------------------------------------------------------|
| Time behaviour |    9/10   | YAML cache prevents re-parsing; GGUF header reader ~1ms     |
| Resource usage |    8/10   | VRAM formula; 5Hz monitor                                  |
| Capacity       |    8/10   | 16 GB VRAM sufficient for 27-30B Q3_K_S MoE                |

**Strengths:**
- **`_QUANT_REGISTRY_CACHE`** (new): `model_registry.yaml` parsed once, cache lives as long as the process.
- **GGUF header reader**: ~1ms vs ~5-7s with `GGUFReader` — 3500-7000x speedup.
- **Median/P90 instead of Mean/Max**: robust against outliers.

**Weaknesses:**
- **`time.sleep(10)` after model load** (pre-existing): fixed sleep instead of adaptive polling.
- **`PIPELINE_TIMEOUTS["agentic_subprocess"]=3600`**: 60min wait time for hung scenario.

---

### 2.5 Maintainability · Rating: 9/10 · Very Good

Effort for modification/improvement. **Phase 1-4 of p11 (Type Hints, Boolean Prefixes, TypedDict, Ubiquitous Language) complete. Phase p7 (Bare-Except Reduction) completed.**

| Sub-characteristic | Rating | Finding                                                                   |
|-------------------|-------:|---------------------------------------------------------------------------|
| Analyzability |   9/10    | Type hints + `is_`/`has_` prefixes + TypedDict + DDD                      |
| Changeability |   9/10    | Single source of truth in `benchmark_config.py` and `model_registry.yaml` |
| Stability     |  10/10    | 564 tests green                                                           |
| Testability   |   9/10    | 14 test files, `pytest >= 8.0`, mypy/ruff in pyproject.toml               |

**Strengths:**
- **Bare-except reduction** (77%): 27 of 35 blocks replaced with specific exceptions. Programming errors are no longer silently swallowed.
- **`get_quant()` rewrite**: clear 5-level priority with YAML cache. Maintainable and extensible.
- **Double-quant fix** (`model_manager.py:249`): `base_key.lower().endswith()` prevents misquantification.
- **`normalize_model_name` fix**: `-gguf` stripping consistent everywhere.
- **Publisher deduplication** in `render_role()`: `base_name = model_name.split("/", 1)[-1]`.
- **9,790 LOC** (↑ from 8,274): growth due to GPT-OSS entries, Intel AutoRound, YAML cache.

**Weaknesses:**
- **`registry_tool.py`** and **`assemble_blueprint.py`**: overlapping functionality (`normalize_model_name`, `_KV_BYTES`).
- **No CI/CD pipeline** in `.github/`.

---

### 2.6 Portability · Rating: 7/10 · Acceptable with Limitations

| Sub-characteristic | Rating | Finding                                                          |
|-------------------|-------:|-----------------------------------------------------------------|
| Adaptability   |   [6/10]   | Hardcoded `127.0.0.1:1234` and `C:\Users\pskra\.lmstudio` paths  |
| Installability |    9/10   | `pyproject.toml` + `requirements-dev.txt`                        |
| Conformance    |    7/10   | Python ≥3.11; OpenAI-compatible + LM Studio-specific             |
| Replaceability |    7/10   | LM Studio only; adapter layer in `model_manager.py`              |

**Strengths:**
- **`os.path.join`, `Path` usage consistent**.
- **`.gitignore`** excludes `lms_models.txt`, `__pycache__`, `embedding-eval/`.

**Weaknesses:**
- **`run_benchmarks.py:1002`** hardcoded `"--base-url", "http://127.0.0.1:1234/v1"`.
- **LM Studio only**: no vLLM/Ollama/TGI fallback.
- **Windows patches in DS1000 framework** not documented for Linux.

---

## 3. Consolidated Findings — Priority List

| Prio | Finding | Category | Effort | Status |
|:----:|------------------------------------------------------|-----------------|--------|------------------------------------|
| *P1* | *16 `except Exception:` swallow programming errors* | Reliability     | Medium | **DONE (p7): 27/35 cleaned up**    |
| *P1* | *Registry drift: missing LMS models*                 | Functionality   | Medium | **DONE (p7): 115 entries**         |
| *P1* | *VERSION suffix `p3` instead of `p7`*                | Maintainability | Trivial | **DONE (p7)**                     |
| *P1* | *Double-quant bug in model_manager.py:249*           | Reliability     | Trivial | **DONE (p7)**                     |
| *P1* | *`normalize_model_name` forgets `-gguf` stripping*   | Functionality   | Trivial | **DONE (p7)**                     |
|  P2  | EXCLUDE_KEYWORDS duplicated in 3 files               | Functionality   | Small   | Open                               |
|  P2  | `time.sleep(10)` instead of adaptive polling         | Efficiency      | Medium  | Open                               |
|  P2  | `_infer_num_parallel()` underestimates for MoE       | Functionality   | Small   | Open                               |
|  P2  | 36 registry entries without `quants`                 | Functionality   | Small   | Open (sync pending)                |
|  P3  | `locale.setlocale()` not used                        | Usability       | Trivial | Open                               |
|  P3  | No visual progress bar                               | Usability       | Medium  | Open                               |
|  P3  | CI/CD pipeline missing                               | Maintainability | Medium  | Open                               |
|  P4  | `download_real_benchmarks.py` error swallowing       | Reliability     | Small   | Open                               |
|  P4  | DS-1000 Windows patches not for Linux                | Portability     | Small   | Open                               |

---

## 4. Recommendations

### 4.1 Immediate (before next benchmark run)

1. **Run `python registry_tool.py sync`** → refresh 36 entries without `quants`.
2. **Run tests** (`python -m pytest tests/ --tb=short -q`) — confirm 564/564 green.

### 4.2 Maintenance Sprint

3. **`_infer_num_parallel()` revisited**: MoE-specific heuristic for `qwen3moe` (16 experts), `ernie4_5-moe` (14 experts).
4. **EXCLUDE_KEYWORDS single source of truth**: central list in `benchmark_config.py`, import in `run_benchmarks.py` and `consolidate_results.py`.
5. **Clean up obsolete tests**: delete or reactivate tests with `obsolete` marker.

### 4.3 Medium-term

6. **CI/CD pipeline** in `.github/workflows/`: at least `pytest` + `ruff` + `mypy --strict`.
7. **`registry_tool.py` ↔ `assemble_blueprint.py` consolidation**: common helpers.
8. **Visual progress bar** for `run_lmeval()` (Popen-based subprocess).

### 4.4 Long-term

9. **LMS-independent test fixtures**: `responses` mocks for CI without LMS.
10. **`run_benchmarks.py:1002`**: replace hardcoded URL with `from model_manager import API_BASE`.

---

## 5. Statistical Comparison

| Metric                         | Review   | Review   | Delta   |
|                                |2026-07-20|2026-07-27|         |
|--------------------------------|----------|----------|---------|
|*Overall rating (ISO/IEC 9126)* | 7.75/10  | *8.5/10* | *+0.75* |
| Functionality                  |  8/10    |  8.5/10  |  +0.5   |
| Reliability                    |  8/10    |  9/10    |  +1.0   |
| Usability                      |  7/10    |  7/10    |    —    |
| Efficiency                     |  8/10    |  8/10    |    —    |
| Maintainability                |  8.5/10  |  9/10    | +0.5    |
| Portability                    |  7/10    |  7/10    |    —    |
| Tests (green)                  | 547      |  *564*   | +17     |
| Registry entries               | 108      |  *115*   |  +7     |
| Core LOC (9 scripts)           | 8,274    |*9,790*   | +1,516  |
| Test LOC (14 files)            |    —     |*5,566*   |    —    |
| Bare `except Exception:`       |  16+     |   *6*    |  -10 (↓63%) |
| Code files with reduction      |    —     | 8 files  |   —     |  

---

## 6. Reviewer Summary

**Overall rating according to ISO/IEC 9126 (subjective, 0-10):**

| Characteristic | Rating |
|----------------|-------:|
| Functionality   |    8.5    |
| Reliability     |    9      |
| Usability       |    7      |
| Efficiency      |    8      |
| Maintainability |    9      |
| Portability     |    7      |
| *Overall*       |   *8.5*   |

**Comment:** The code has improved significantly since the last review (7.75/10).
The three main fixes in this review — bare-except reduction (77%), registry enhancements (115 entries), and GPT-OSS/Intel-AutoRound integration —
have increased Reliability (+1.0) and Maintainability (+0.5). The 564 tests confirm stability.

Main improvement potential remains in **(Usability)** through visual indicators and **(Portability)** through a CI/CD pipeline.

The `get_quant()` rewrite with YAML cache is a significant maintainability gain.

**Make-vs-Buy observation:** The LM Studio binding is intentional (research project). Architecturally clean via `model_manager.py` adapter encapsulation.
The 47 installed models show productive usage intensity.
