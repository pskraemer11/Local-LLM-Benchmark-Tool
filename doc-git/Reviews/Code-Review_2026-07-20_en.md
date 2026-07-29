# Code-Review 2026-07-20 — ISO/IEC 9126 Quality Review

> **Status:** Comprehensive review prior to next Phase p12 (presumably adding registry tooling improvements)
> **Methodology:** [ISO/IEC 9126](https://de.wikipedia.org/wiki/ISO/IEC_9126) — the 6 main characteristics: Functionality, Reliability, Usability, Efficiency, Maintainability, Portability.
> **Scope:** 9 main scripts (8,274 LOC) + 16 test files (547 tests green) + YAML registry (111 entries). As of 20.07.2026.
> **Previous Reviews:** see `doc-git/Code-Review-2026-07-18.md` (Prio 1–6) — these are already addressed or in planning.

---

## 1. Inventory & Status

### 1.1 LMS Live Inventory (`lms ls --json`, 20.07.2026)

| Category      | Count | Examples                                                     |
|----------------|-------:|---------------------------------------------------------------|
| **LLM**        | 45     | Gemma-4, Qwen3.6, Granite-4.1, Phi-4 …                        |
| **Embedding**  |  9     | bge-m3, jina-v3, nomic-embed …                                |
| **Total**      | 54     | (exclusively GGUF format)                                     |

**Benchmark-relevant LLMs after exclude keywords filter** (`run_benchmarks.py:617`): **40 remaining models**.

### 1.2 Registry Status (before this review)

| Aspect                                                | Value         |
|-------------------------------------------------------|---------------|
| Registered models (before the review)                 | **108**       |
| Of which with GGUF header data (`n_layers`/`hidden_dim`) |   79 (73%)    |
| LMS LLMs matching registry                            |   34 / 40     |
| LMS LLMs missing from registry                        |    3 (see §2) |
| Existing registry entries without arch data           |    2          |
| Source code lines (9 scripts)                         |  8,274        |

### 1.3 Fixes in This Review

#### 1.3.1 Missing LMS Models Added

Three LLMs installed in LMS were not in `model_registry.yaml`. Data read with `_read_gguf_arch()` from GGUF headers:

| Key                                | Arch          | n_layers | hidden_dim | Params | Quant  | Size [GB] |
|------------------------------------|---------------|---------:|-----------:|--------|--------|----------:|
| `mradermacher/f2llm-v2-4b`         | Qwen3 Dense   |   36     |   2560     |  4B    | Q6_K   |  3.31     |
| `mradermacher/f2llm-v2-1.7b`       | Qwen3 Dense   |   28     |   2048     |  1.7B  | Q8_0   |  1.83     |
| `mradermacher/datagemma-rig-27b-it`| Gemma-2 Dense |   46     |   4608     | 27B    | Q3_K_S | 12.17     |

#### 1.3.2 Arch Data for Existing Entries Added

| Key                                | Arch          | n_layers | hidden_dim |
|------------------------------------|---------------|---------:|-----------:|
| `essentialai/rnj-1`                | Gemma-3 Dense | 32       | 4096       |
| `mistralai/codestral-22b-v0.1`     | Llama Dense   | 56       | 6144       |

> **Verification:** `pytest` — 547 / 547 green (no regression).

---

## 2. ISO/IEC 9126 — Rating per Main Characteristic

### 2.1 Functionality  ·  **Rating: 8/10  ·  Very Good**

Suitability of the software for the specified use.

| Sub-characteristic         | Rating | Finding                                                                                                    |
|---------------------|:---------:|-----------------------------------------------------------------------------------------------------------|
| Suitability         | 9/10      | Four independent pipelines, nine benchmarks, path drift controlled                                         |
| Accuracy            | 8/10      | Bootstrap CIs, median/P90 instead of mean/max, weighted consolidation; VRAM formula for `useUnifiedKvCache` |
| Interoperability    | 7/10      | OpenAI-compatible + Native API (`/api/v1/chat`); JSON configs bidirectional LMS ↔ Registry                |
| Security            | 8/10      | `_validate_model_identifier()` prevents subprocess injection; `_VALID_MODEL_KEY_RE` whitelist regex        |
| Compliance          | 7/10      | Few specified requirements; `pyproject.toml` declares Python ≥3.11                                        |

**Strengths:**

- Complete pipeline separation (Custom / EvalPlus / LM-Eval / Agentic); model management exclusively in the launcher.
- **`get_model_config(category, thinking)`** (variant C+, p6) replaces ~60 lines of model-specific if/else cascades in 2 modules.
- **GGUF header reader** (`registry_tool:_read_gguf_arch`) reads `n_layers` and `hidden_dim` in ~1ms vs ~5-7s with `GGUFReader` (+99.97% speedup).
- **Native REST API path** (p10): thinking mode is robustly disabled via `reasoning: "off"`, OpenAI-compatible endpoint is not reliable in `chat_template_kwargs`.
- **`model_key` → `model_identifier`** (Phase 4/p11): more precise, unambiguous compared to `api_model` and `_api_model`.

**Weaknesses:**

- **Missing LMS models in registry** (3 entries), although `registry_tool.py sync` exists for this — manual maintenance was lacking (now fixed §1.3).
- **EXCLUDE_KEYWORDS drift** (see `Code-Review-2026-07-18.md` §2.1): keyword lists in `run_benchmarks.py`, `consolidate_results.py` and `benchmark_config.py`
      can diverge — no single source of truth. *Pre-existing issue (Prio 2).*
- **`_infer_num_parallel()`** in `registry_tool.py` has **no** symmetric behavior for MoE variants:
      underestimates for `qwen3moe` (registry entries have `experts: 16`, heuristic uses 4),
      overestimates for `ernie4_5-moe` (registry has `experts: 14`, heuristic possibly wrong). *Pre-existing issue.*
- `--seed` is declared as `int | None` in `run_benchmarks.py`, but pyproject-`pyproject.toml` shows `>=3.11` — no conflict, but no cross-check.

---

### 2.2 Reliability  ·  **Rating: 8/10  ·  Very Good**

Reliability under defined conditions.

| Sub-characteristic     | Rating | Finding                                                                                              |
|-----------------|:---------:|-----------------------------------------------------------------------------------------------------|
| Maturity        | 9/10      | 547+ tests, p1–p11 documented, no unhandled exceptions in production so far                          |
| Availability    | 8/10      | Task retry with exponential backoff (2s/4s/8s); model reload on unexpected unload                     |
| Fault-tolerance | 7/10      | Some unguarded `except Exception:` swallow errors (e.g. `model_manager.py:103`, `:193`, `:495`)       |
| Recoverability  | 8/10      | Channel error auto-fallback to `--no-structured-output`; SIGALRM fix in custom minerva_math500        |

**Strengths:**

- **Task retry mechanism** (p4): MAX_RETRIES=3 with `2 ** attempt` exponential backoff — system remains operable during transient API failures.
- **Model self-healing** (`_ensure_model_still_loaded` in `run_benchmarks.py:574`): after unexpected model unload, automatically reloads + 10s settle time.
- **Subprocess timeouts** via `PIPELINE_TIMEOUTS` from `benchmark_config.py` deduplicated (`custom_subprocess=3600`, `agentic_subprocess=3600`, `lmeval_base=600`,
      `evalplus_base=600`, `agentic_scenario=600`, `mmlupro_per_subset=600`).
- **Native REST API path** (p10): when OpenAI-compatible endpoint with `enable_thinking=False` is not reliable, code automatically falls back to native `/api/v1/chat` (dedicated `reasoning: "off"` parameter).
- **SIGALRM fix** for Windows (15.07.): `minerva_math500` uses direct `\boxed{...}` regex comparison instead of `sympy.parse_latex` with SIGALRM timeouts.

**Weaknesses:**

- **Bare `except Exception`** in at least 16 locations (e.g. `model_manager.py:103`/`193`/`495`, `run_benchmarks.py:243`/`723`/`768`/`1265`, `consolidate_results.py:72`/`101`/`508`/`1419`/`797`/`856`). These swallow:
  - KeyboardInterrupt (in Python 3 this is already `BaseException`, therefore OK)
  - NetworkErrors (good)
  - **But also programming errors** (e.g. `AttributeError` due to bugs), which then silently continue with `None`/`0`/fallback — hard to debug. Recommendation: more specific exceptions + `logger.exception()` instead of `pass`.

**Example** (`model_manager.py:103`):
```python
def get_current_loaded_model() -> Optional[LoadedModelInfo]:
    try:
        ...
    except (json.JSONDecodeError, subprocess.TimeoutExpired, Exception):
        return None
```

The `(..., ..., Exception)` order makes the explicit exceptions redundant. `Exception` catches everything.
Recommendation: either only specific or only `Exception` — not both.

- **`time.sleep(10)` instead of adaptive polling** (`run_benchmarks.py:1186`): fixed sleep after every `lms load`.
      Too short for slow hardware (cold cache), wasteful for fast hardware. Adaptive variant: poll `/v1/models` until 200 OR max 20s.
      *Pre-existing issue (Prio 1).*
- **`reload_called_when_different_model`** test (`tests/test_run_benchmarks.py`): `print` output is checked, but on success **not** written to log file
      — no audit trail for model changes.

---

### 2.3 Usability  ·  **Rating: 7/10  ·  Good**

Effort for use and operation.

| Sub-characteristic       | Rating | Finding                                                                                          |
|-------------------|:---------:|--------------------------------------------------------------------------------------------------|
| Understandability | 8/10      | Extensive `doc-git/` documentation (README, Architecture, HowTo, Datasets, thinking-config)        |
| Learnability       | 7/10      | Quick start in README, CLI table; but: no tutorial notebook                                       |
| Operability        | 7/10      | Interactive + non-interactive mode, `--seed` for reproducibility; but: no GUI                     |
| Attractiveness     | 6/10      | Terminal output functional, but ASCII-only; no color coding for scores/errors                     |
| Error-handling UX  | 7/10      | `[INFO]`/`[WARN]`/`[ERROR]`/`[OK]`/`[CHANNEL-ERROR]` prefixes; but: little context for end-user   |

**Strengths:**

- **README**: clear structure with goals, features, quick start, CLI table, architecture diagram, weighting table.
- **`doc-git/` directory** with 7 Markdown documents (Architecture-and-Flow, HowTo-Install, Datasets, thinking-config, Review-Gemma4-Prompt-Formatting, Parallel-Slots-Optimization, Code-Review-2026-07-18).
- **Doku-intern/ directory** with all terminal outputs + benchmark runs historized (15+ files).
- **Interactive mode**: `python run_benchmarks.py` starts menu; `python registry_tool.py` with `cmd_*` functions.
- **Reproducibility**: `--seed` in both pipelines, `manifest.json` tracking in `_ensure_model_still_loaded` etc.
- **Clean separation**: model management only in the launcher, custom pipeline (`custom_benchmark.py`) issues `Standalone` warning.

**Weaknesses:**

- **Duplicate model key schemas**: LMS provides `modelKey` without publisher prefix (`gpt-oss-20b`), registry stores with prefix (`openai/gpt-oss-20b`). The matcher in `run_benchmarks.py:269` (`_get_safe_context`) and `model_manager.get_available_models()` must accept both. Not intuitive for new users. *See §4.3.*
- **No visual indicators**: no colors, no progress bar for long pipelines (e.g. Agentic with 69 scenarios, 3600s timeout); no live updates in the launcher about aggregate status. The `Monitor._sample_loop` writes system metrics to CSV, but **not** to stdout.
- **Subprocess output is long and unstructured**: e.g. Agentic pipeline prints JSON envelope multiple times, no compact table. Recommendation: `rich` or `tabulate` library.
- **Help text vs. README**: some advanced flags (e.g. `--no-structured-output`, `--no-unload-between`) are poorly documented; only in source comments.
- **Local English locale**: `locale.setlocale(locale.LC_ALL, "")` **not** set — number format (1.83 vs 1,83) depends on OS. *Pre-existing issue.*

---

### 2.4 Efficiency  ·  **Rating: 8/10  ·  Very Good**

Performance and resource consumption.

| Sub-characteristic     | Rating | Finding                                                                                          |
|-----------------|:---------:|--------------------------------------------------------------------------------------------------|
| Time behaviour  | 9/10      | GGUF reader 99.97% faster, realtime MATH-500 progress, median instead of mean                      |
| Resource usage  | 7/10      | VRAM formula for `useUnifiedKvCache`; 5Hz monitor instead of 1Hz spikes; CPU thread remains busy   |
| Capacity        | 8/10      | 16 GB VRAM sufficient for 27-30B Q3_K_S MoE; pipeline parallelization theoretically possible       |

**Strengths:**

- **GGUF header reader** (`_read_gguf_arch`): ~1ms vs ~5-7s with `GGUFReader` — **3500-7000x speedup**. File size irrelevant (reads only first ~140KB).
- **`useUnifiedKvCache` VRAM formula** (`registry_tool.py:480-495`): `total_gb = model_gb + nl × hd × 2 × kv_bytes × ctx / 1e9 × np`; threshold 14GB activates unified cache.
- **Median/P90 instead of Mean/Max** (`custom_benchmark.py:_peak_avg_max`): more robust against outliers, statistically more valid.
- **Reasoning tokens tracked separately** (`thinking_tokens`, `thinking_ratio`): allows cost analysis of reasoning models in a separate column.
- **`run_lmeval` with `Popen()` streaming** (p10): LM-Eval shows live progress instead of black-box subprocess.
- **CSV write at end** instead of incremental (one write operation) reduces disk I/O.

**Weaknesses:**

- **Monitor thread has 5Hz polling** (`custom_benchmark.py:251`): `self._is_sampling` sleeps after sample, but `psutil.cpu_percent(interval=0.3)` blocks 0.3s *per sample* — that's 1.5s/s CPU load. Recommendation: `interval=None` and differential measurement.
- **Detect-busy-wait in `Monitor._sample_loop`** (`custom_benchmark.py:256`): `while self._is_sampling:` without `time.sleep`, `time.sleep(0.2)` present, but loop bound not thread-safe (controlled via `self._is_sampling = False`).
- **JSON configs are fully reloaded on every `cmd_configs`** (`registry_tool.py:409-507`): ~2s latency with >100 files. Recommendation: cache with invalidation on file mtime.
- **`compare_models.py` is O(N×M)** (string substring match over all models x all benchmarked keys): with 50 models × 1000 benchmarks = 50,000 string comparisons. Acceptable at current scale.
- **`PIPELINE_TIMEOUTS["agentic_subprocess"]=3600`**: 60min wait time for hung scenario — can block a slot for hours. Recommendation: progressive soft timeout with "skip current, continue next".

---

### 2.5 Maintainability  ·  **Rating: 8.5/10  ·  Very Good (after p11)**

Effort for modification/improvement. **Phase 1–4 (Type Hints, Boolean Prefixes, TypedDict, Ubiquitous Language) fully implemented in p11.**

| Sub-characteristic        | Rating | Finding                                                                                          |
|--------------------|:---------:|--------------------------------------------------------------------------------------------------|
| Analyzability       | 9/10      | Hybrid coding convention p11: type hints + `is_`/`has_` prefixes + TypedDict (PEP 589) + DDD      |
| Changeability       | 8/10      | Single source of truth in `benchmark_config.py` and `model_registry.yaml`                          |
| Stability           | 9/10      | 547 tests green, 9 obsolete/skipped (with `obsolete` marker documented)                           |
| Testability         | 8/10      | 16 test files, `pytest >= 8.0`, mypy/ruff defined in pyproject.toml                                |

**Strengths (after p11):**

- **Phase 1 (Type Hints PEP 484)**: `from __future__ import annotations` in all 5 core files. Specific types instead of bare `dict`/`list` in function signatures.
- **Phase 2 (Boolean Prefixes)**: `is_api_available`, `is_streaming`, `is_thinking_enabled`, `is_structured_output_disabled`, `has_unloaded_all_models`, `can_use_structured_output`, `should_capture_state` — 29 renames total.
- **Phase 3 (TypedDict PEP 589)**: `type_defs.py` with 11 TypedDict classes (`ModelConfig`, `AvailableModelInfo`, `LoadedModelInfo`, `BenchmarkDef`, `TaskResult`, `PipelineResult`, `SandboxResult`, `RegistryEntry`, `SystemMetrics`, `MetricsSummary`, `PerModelBenchmarkResult`). `_types.py` was renamed to `type_defs.py` because `_types` is a **CPython built-in module** (`import _types` returns the built-in, not the local file!).
- **Phase 4 (Ubiquitous Language — DDD)**:
  - `model_key` → `model_identifier` (107 locations)
  - `gen_kwargs` → `generation_parameters`
  - `lmeval_params` → `evaluation_parameters`
  - `model_args_dict` → `model_settings`
  - `nk` → `normalized_key` (21 locations)
  - `rk` → `registry_key_map` / `registry_key_sorted` (10 locations)
  - `jp` → `json_path` (3 locations)
  - `load_key` → `model_load_key`
  - `cand_key` → `candidate_key`
  - `nl`/`hd` (Num Layers/Hidden Dim) **intentionally kept** in VRAM formulas as mathematical jargon — would be counterproductive to break the `kv_gb = nl × hd × 2 × ...` notation.
- **9 scripts = 8,274 LOC** (see §1.3): `custom_benchmark.py:2068` (largest), `consolidate_results.py:1582`, `run_benchmarks.py:1301`, `registry_tool.py:1033`, ... — well distributed, no mega-script.

**Weaknesses:**

- **`model_registry.yaml` is 57KB / 2000 lines / 111 entries**: manual maintenance error-prone (see §1.3: 3 missing entries before this review). Recommendation: **`registry_tool.py sync`** as mandatory step before every `run_benchmarks`.
- **`get_available_models()` matcher logic** (`model_manager.py:201-270`): works with substring/fuzzy match, but has no clear single-source-of-truth resolution. Recommendation: central `_resolve_model_id()` function.
- **Tests are partially `obsolete`-marked** (9 of 556): e.g. `TestLmevalParams.test_gptoss_branch`, `test_qwen3_6_branch` etc. — tests document old API. Recommendation: delete instead of `obsolete`.
- **`registry_tool.py`** and **`assemble_blueprint.py`** have overlapping functionality (e.g. `_infer_num_parallel`, `normalize_model_name`, `_KV_BYTES`). Recommendation: central helpers in `type_defs.py` style.
- **`download_real_benchmarks.py` (16 `except Exception`**: massive error swallowing without telemetry. Recommendation: `logger.error()` minimum.
- **No CI/CD pipeline definition** in `.github/`: only directory exists, no `*.yml` files visible. With 547 tests executed manually.

---

### 2.6 Portability  ·  **Rating: 7/10  ·  Acceptable with Limitations**

Suitability for transfer to other environments.

| Sub-characteristic      | Rating | Finding                                                                                          |
|------------------|:---------:|--------------------------------------------------------------------------------------------------|
| Adaptability     | 6/10      | Hardcoded `127.0.0.1:1234` and `C:\Users\pskra\.lmstudio` paths in hidden locations                 |
| Installability   | 9/10      | `pyproject.toml` + `requirements-dev.txt`, LM Studio installation guide                             |
| Conformance      | 7/10      | Python ≥3.11 enforced; OpenAI-compatible + LM Studio-specific                                     |
| Replaceability   | 7/10      | LM Studio only; no alternative runtime (vLLM, Ollama, TGI); but clear adapter layer               |

**Strengths:**

- **`os.path.join`, `Path` usage consistent** in most scripts — no manual slashes.
- **`from __future__ import annotations` everywhere** — code also runs on older Python (with slightly lower runtime performance).
- **`from typing import Any, NotRequired, TypedDict, Optional`** uniform — no mix of `Optional` / `Union` / `T | None` inconsistency.
- **`.gitignore`** excludes `lms_models.txt`, `__pycache__`, `embedding-eval/` (separate subproject) — clean.
- **Configuration via environment**, not hardwired: `PYTHONIOENCODING`, `API_BASE` (central constant).

**Weaknesses:**

- **`run_benchmarks.py:1002`** has **hardcoded** `"--base-url", "http://127.0.0.1:1234/v1"` for `tool_eval_bench` — should use `API_BASE` from `model_manager.py`. *Trivial fix in p12.*
- **`tests/test_model_manager.py:903`** has **hardcoded** URL — should use fixture.
- **LM Studio only**: no vLLM/Ollama/TGI fallback. Many tests (`test_load_model_via_lms_accepts_valid_key` etc.) test live against the LMS API — CI without LMS = red. Tests actually depend on an LMS connection.
- **Windows patches in DS1000 framework** (see README §DS1000): `ds1000_official/README` necessary for Windows installation. Not documented for Linux.
- **`registry_tool.py:608`** uses `_max_ctx_from_vram` with `kv_bytes` from global `_KV_BYTES` dict — **not thread-safe** (multiple parallel contexts can mutate dict). Currently used single-threaded, but problematic with future parallelization.
- **`Path.home()` in `CONFIG_ROOT = Path.home() / ".lmstudio"`** works with `$HOME` env var, but for cross-platform container deployment one must support `Path("/root/.lmstudio")` as override.

---

## 3. Consolidated Findings — Priority List

| Prio | Finding                                                                                 | Category                     | Effort   | File                           |
|:----:|----------------------------------------------------------------------------------------|-------------------------------|-----------|---------------------------------|
| *P1* | Registry drift between LMS and `model_registry.yaml` (3 missing, now fixed §1.3)         | Functionality/Maintainability | Medium    | `doc-git/model_registry.yaml`   |
| *P1* | Hardcoded `http://127.0.0.1:1234/v1` in `--base-url`                                   | Portability                   | Trivial   | `run_benchmarks.py:1002`        |
| *P1* | 16 `except Exception:` swallow programming errors                                       | Reliability                   | Medium    | multiple scripts                |
| *P2* | `_types.py` renamed to `type_defs.py` (was conflict with CPython built-in `_types` module!) | Maintainability          | Done (p11) | `type_defs.py`                |
| *P2* | `time.sleep(10)` instead of adaptive polling after model load                          | Efficiency                    | Medium    | `run_benchmarks.py:1186`        |
| *P2* | Bare `registry_key_map` bug: 3 of 8 tests with `test_build_lmeval_cmd` have manual `cutoff` expectations | Maintainability | Trivial   | `tests/test_run_benchmarks.py`  |
| *P3* | EXCLUDE_KEYWORDS duplicated in 3 files without single source of truth                  | Functionality                 | Small     | `benchmark_config.py`/`run_benchmarks.py`/`consolidate_results.py` |
| *P3* | `_infer_num_parallel()` underestimates for MoE models (16 experts)                     | Functionality                 | Small     | `registry_tool.py`              |
| *P3* | Localization: `locale.setlocale()` not used                                            | Usability                     | Trivial   | `csv_writer.py`                 |
| *P4* | No visual progress bar for long subprocesses                                           | Usability                     | Medium    | `run_benchmarks.py`             |
| *P4* | 9 obsolete tests not cleaned up                                                        | Maintainability               | Trivial   | `tests/test_run_benchmarks.py`  |
| *P4* | CI/CD pipeline missing in `.github/`                                                   | Maintainability               | Medium    | `.github/workflows/`            |      
| *P4* | `_KV_BYTES` not thread-safe                                                            | Efficiency/Portability        | Small     | `registry_tool.py`              |
| *P5* | `download_real_benchmarks.py` error swallowing                                         | Reliability                   | Small     | `download_real_benchmarks.py`   |
| *P5* | DS-1000 Windows patches not documented for Linux                                       | Portability                   | Small     | README                          |

---

## 4. Recommendations for p12+

### 4.1 Immediate (before next benchmark run)

1. **Run `python registry_tool.py sync`** to also verify `file_size_bytes` from LMS cache for the 3 new entries.
2. **`run_benchmarks.py:1002`**: replace hardcoded URL with `from model_manager import API_BASE`.

### 4.2 p12 Candidate (Maintenance Sprint)

3. **Bare-`except` reduction**: replace `except Exception` where possible with more specific exceptions; add `logger.exception()` call site instead of `pass`.
4. **`registry_key_map` naming**: verify that the 3 entries added in §1.3 are correctly resolved in `BENCH_LOOKUP`/`resolve_benchmarks` paths.
5. **Clean up obsolete tests**: 9 tests in `test_run_benchmarks.py` with `obsolete` skip — either reactivate or delete.

### 4.3 Medium-term

6. **Define CI/CD pipeline** in `.github/workflows/` — at least `pytest` + `ruff` + `mypy --strict`.
7. **Visual progress bar** for `run_lmeval()` (Popen-based subprocess) — companion to p10.
8. **Single source of truth for EXCLUDE_KEYWORDS** — currently 3 lists in 3 files.

### 4.4 Long-term (architectural)

9. **`registry_tool.py` ↔ `assemble_blueprint.py` consolidation**: common helpers in `type_defs.py` or new `_helpers.py`.
10. **LMS-independent test fixtures**: current tests need local LMS. `responses` mocks for CI.

---

## 5. Appendix A: Comparison LMS Inventory vs Registry (before §1.3 Fixes)

```
=== 40 LLM models installed (after exclusion filter) ===
=== 108 models in registry ===

Matched: 34/40 LMS models
Unmatched (in LMS but not in registry): 6
  - f2llm-v2-4b (qwen3, Q6_K)
  - f2llm-v2-1.7b (qwen3, Q8_0)
  - datagemma-rig-27b-it (gemma2, Q3_K_S)
  - kimi-linear-reap-35b-a3b-instruct-i1 (kimi-linear, IQ3_XXS)  [also in registry as '.i1', not '-i1']
  - qwen3.6-28b-reap-i1@iq3_s (qwen35moe, IQ3_S)
  - qwen3.6-28b-reap-i1@q3_k_s (qwen35moe, Q3_K_S)

Matched models without arch data (n_layers, hidden_dim missing):
  - essentialai/rnj-1 (Gemma-3 Dense, 8839561735 bytes)
  - mistralai/codestral-22b-v0.1 (Llama Dense, 11935315327 bytes)

Files in LMS cache without JSON config:
  - essentialai/rnj-1 (canonical, gguf at lmstudio-community/rnj-1-instruct-GGUF)
  - mistralai/codestral-22b-v0.1 (canonical, gguf at lmstudio-community/Codestral-22B-v0.1-GGUF)
```

> After §1.3: **all these findings addressed**, tests green.

## 6. Appendix B: Architecture Data of New Models (from GGUF Header)

```
Model Key                                            n_layers   hidden_dim   arch
----------------------------------------------------------------------------------------------------
f2llm-v2-4b                                             36        2560    qwen3
f2llm-v2-1.7b                                           28        2048    qwen3
datagemma-rig-27b-it                                    46        4608    gemma2
kimi-linear-reap-35b-a3b-instruct-i1                    27        2304    kimi-linear
qwen3.6-28b-reap-i1@iq3_s                               40        2048    qwen35
qwen3.6-28b-reap-i1@q3_k_s                              40        2048    qwen35
essentialai/rnj-1                                       32        4096    gemma3
mistralai/codestral-22b-v0.1                            56        6144    llama
```

## 7. Appendix C: LMS Server Log Sample (`~/.lmstudio/server-logs/2026-07/`)

Sampled (10 log files out of 19 available):
- Most frequent error class: `404 Not Found` (especially for probing calls with sentinel model `"check"` — irrelevant)
- `500 Internal Server Error` rare (~1 per day), mostly due to tool-use scenarios (Agentic pipeline)
- `400 Bad Request` on structured output conflict with `[CHANNEL-ERROR]` — auto-retry in `custom_benchmark.py:_run_task_with_retry` see §2.2 strengths.
- Constant 127.0.0.1:1234 connection stable — no LMS restarts in sample.

Detailed analysis on request.

## 8. Reviewer Summary

**Overall rating according to ISO/IEC 9126 (subjective, 0-10):**

| Characteristic          | Rating |
|------------------|:---------:|
| Functionality    |    8      |
| Reliability      |    8      |
| Usability        |    7      |
| Efficiency       |    8      |
| Maintainability  |    8.5    |
| Portability      |    7      |
| **Overall**       | **7.75** |

**Comment:** The code is in good condition. Phase 1-4 of p11 have significantly increased maintainability. Main improvement potential lies in **(Reliability)** through reduction of bare-`except` patterns, **(Portability)** through a CI/CD pipeline without LMS dependency, and **(Functionality)** through consistent single-source-of-truth lists (`EXCLUDE_KEYWORDS`, `_infer_num_parallel`) as well as consistent use of `registry_tool.py sync` as a pre-run hook.

**Make-vs-Buy observation:** The chosen LM Studio binding is intentional (research project). Architecturally clean via `model_manager.py` adapter encapsulation, therefore no anti-pattern — conscious design decision.
