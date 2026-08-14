# Architecture & Flow – Status as of 03.08.2026 (v13.0.10)

> **Version Convention:** See [`../VERSION`](../VERSION) – Single Source of Truth for project version. The existing `_en.md` filename is legacy (last updated 03.08.2026) – planned migration to `_v13.md` in a future major version.
> **Review Reference:** See `doc-git/Reviews/Code-Review_2026-08-03_de.md` for the F1–F5 review that informed the 03.08. changes (MTP-Drafter-Filter, Granite-Templates, Docstrings/main()-Zerlegung, CWD-unabhängige Einstiegspunkte, Codestral-Structured-Output). Earlier: `doc-git/Reviews/Code-Review_2026-08-02_de.md` (P1/P3/P4: Struktur-Gate, Agentic-Safety, Run-Spec), `Doku-intern/Code-Review-2026-07-18.md`.

## 1. Overview

The benchmark system consists of **four independent evaluation pipelines**, controlled via a central launcher.
**Model management (load/unload) is ONLY triggered by the Launcher in `main()`.**

### Four Evaluation Pipelines (9 Benchmarks)

| Pipeline                  | Script(s)                             | Benchmarks                                     | Evaluation                                 |
|---------------------------|----------------------------------------|------------------------------------------------|--------------------------------------------|
| **Custom Script v10**     | `src/custom_benchmark.py`              | DS1000, CoderEval                              | `exec_sandboxed()` + Namespace comparison   |
| **lm-evaluation-harness** | `lm_eval` CLI                          | MATH-500, ARC-Challenge, HellaSwag, TruthfulQA | `generate_until` + Regex extraction        |
| **evalplus**              | `evalplus.codegen`+`evalplus.evaluate` | HumanEval+, MBPP+                              | Differential testing with plus_input       |
| **Agentic**               | `tool_eval_bench` CLI                  | Agentic (69 scenarios)                         | tool-eval-bench Envelope (final_score)     |

**Removed:** BBH (too expensive, 8x multiplier), PandasEval (too few tasks, little differentiation potential), MMLU-Pro (too expensive, 14 subsets).

Added: **Agentic pipeline** (tool-eval-bench) and **MATH-500** (replaces MathQA).

## Structure 
```
LM Studio (localhost:1234)
├── REST API: POST /v1/chat/completions (OpenAI-compatible)
├── Native API: POST /api/v1/chat (used for reasoning=off thinking control)
├── Model management: lms load / unload / ps (CLI)
├── lms ls --json  -> modelKey + selectedVariant + variants[] + quantization.name
│   → modelKey = base key (e.g. essentialai/rnj-1)
│   → variants[] = @-qualified IDs (e.g. ["essentialai/rnj-1@q8_0"])
│   → lms load accepts ONLY modelKey (without @) – no CLI flag for variant selection
└── No logprobs, no /v1/completions

model_manager.py (SHARED, unversioned)
├── load_model_via_lms(model_key, gpu_offload=None) -> (bool, exact_identifier)
│   ├── model_key = base modelKey (without @) – lms load accepts no @-variants
│   ├── Call: `lms load {model_key} --yes` (no --gpu max, no --context-length)
│   │   → GPU usage is controlled automatically via the `user-concrete-model-default-config` JSONs
│   │   → Context length is taken automatically from the pre-config
│   │   → --context-length was removed 19.07. – it permanently overwrote JSON configs
│   └── --identifier is not set (not for variant selection)
├── unload_all_models()
├── wait_for_model_ready()     [unused]
├── get_current_loaded_model() -> dict with identifier, model_key, display_name
├── check_api_available()      [unused]
├── API_BASE                   (central, not hardcoded in Launcher)
└── PIPELINE_TIMEOUTS          (centrally defined)

csv_writer.py (CSV-OUTPUT, unversioned)
├── write_accumulative_summary()  -> Unified schema (; delimiter, utf-8)
├── write_konsolidiert_aktuell()
├── median/p90 columns in fn_csv
└── Unified columns: pipeline;bench;model;score;cpu_med;cpu_p90;gpu_med;...

benchmark_config.py (CENTRAL CONFIGURATION)
├── CAT_WEIGHTS / OVERALL_WEIGHTS
├── PIPELINE_DISCOVERY
├── TOOL_EVAL_SCENARIO_IDS
├── QUANT_MAP (auto-generated via generate_quant_map.py)
├── BLACKLIST (embedding models, <16K context, OCR/vision/audio/translation, rag/german)
└── EXCLUDE_KEYWORDS = BLACKLIST (alias, backward-compat)

run_benchmarks.py (LAUNCHER - main(), v10)
├── ONLY HERE is load/unload called
├── Controls all 4 pipelines
├── Custom subprocess via dynamic glob (always the highest _vXX file)
├── Captures exact model ID from lms ps
├── all_summary.append() outside the is_custom block
├── API_BASE from model_manager.API_BASE
├── MMLU-Pro helper (removed in v13): _get_lmeval_params, _build_lmeval_cmd, _parse_subset_score
├── Task-Retry: MAX_RETRIES=3, exponential backoff
├── --seed for reproducible task selection (custom + agentic + evalplus)
├── --no-structured-output for fallback in custom pipeline
├── --agentic-mode {random,safety} (02.08.): Agentic scenario selection – Category K vs. all 69
├── --run-spec / --config <run.yaml> (02.08.): YAML run-spec with precedence CLI>YAML>Defaults
├── Context length: Taken from the `user-concrete-model-default-config` JSONs
│   (no longer a parameter to `load_model_via_lms()`)
├── Frees memory at the end
├── Excludes: whisper, vision, ocr, audio, embed, vl
├── API readiness: time.sleep(10) instead of polling loop
├── Variant resolution (v31):
│   ├── model_info["key"] = variant-unique (selectedVariant or modelKey@quant)
│   ├── model_info["model_key"] = base modelKey (for lms load)
│   ├── model_info["quant"] = quantization.name from JSON
│   ├── model_info["variants"] = complete variants[] list from lms ls --json
│   ├── load_key = model_info["model_key"] (base Key, without @)
│   ├── After loading: warning if loaded variant ≠ desired quant
│   └── lms load has NO CLI flag for variant selection -> Workaround via Warning
├── EvalPlus resume=False (v31): resume=True removed, since old samples accumulated
│   → evalplus_codegen now generates exactly sample_size tasks, no legacy artifacts
└── Version internal: "Unified Benchmark Launcher v10"

custom_benchmark.py (CUSTOM BENCHMARKS, v10)
├── NEVER calls load/unload
├── Assumes model is ready
├── DS1000 + CoderEval (PandasEval removed)
├── Task-Retry with MAX_RETRIES=3 + exponential backoff
├── System metrics: Per-task peak values (Monitor ~5Hz), saved with median/p90
├── Structured output: response_format with JSON schema (default)
├── extract_code() with JSON parsing shortcut + Regex fallback
├── --no-structured-output as fallback for small/incompatible models
├── --seed for reproducible task selection
├── Saves tasks_*.csv + model_*.csv
├── No legacy paths (old format, interactive mode removed)
├── Complete type hints (55 functions)
└── Standalone mode warns -> Use run_benchmarks.py

consolidate_results.py (CONSOLIDATION, v10)
├── ModelData dataclass (instead of raw dicts)
├── median/p90 columns in CSV and MD
├── compute_category_scores() normalizes by available benchmarks
├── TOP 5 / BOTTOM 5 / Category rankings in MD
├── width duplicate removed (dead width block deleted)
├── All benchmarks consolidated (even if individual pipelines are missing)
├── Bootstrap CIs always computed (DS1000 + CoderEval)
├── --compare: Paired Bootstrap for 2+ models (all pairwise comparisons)
├── --seed for reproducible bootstrap
├── --models: Model filter
├── --since/--until: Time period filter for CSV result files (YYYYMMDD_HHMMSS or YYYYMMDD)
├── --all-runs: Include all historical benchmark runs (Default: only last run)
├── --no-installed: Disable installed filter (Default: only currently via lms ls installed models)
├── --merge: Shortcut for --all-runs + --no-installed, merges the last --runs N runs (Default: 2)
├── Variant-aware model info (v31):
│   ├── _get_model_info(): Keys now variant-unique (selectedVariant or modelKey@quant)
│   │   → No more overwriting with multiple quants of the same model
│   ├── _get_display_name(): Also searches via saved modelKey field
│   ├── _lookup_vram(): Searches via modelKey field before fuzzy match
│   ├── try_read_evalplus(): Fallback to base key (without @) for old result directories
│   ├── read_lmeval_per_model(): Same fallback
│   └── read_agentic(): Same fallback
├── Installed filter: Cross-reference with lms ls --json, only currently installed models (Default)
├── Latest-run filter: Only CSVs from the newest timestamp overall (Default; --all-runs disables)
├── Complete type hints (27 functions)
└── Complete type hints (27 functions)
```

## Review on 28.06.2026
After the review on 28.06., the following architecture changes were implemented:
- **Versioning unification**: All 3 main scripts now run under a shared major version **v10** (previously: Launcher v7, Custom v24, Consolidation v8).
- **Helper modules without version**: `src/model_manager.py`, `src/csv_writer.py` (previously `_v2`).
- **Type hints**: All functions in the 3 main scripts (55+20+27 = 102 functions) fully typed.
- **Central configuration**: `src/benchmark_config.py` for weights, tool-eval scenarios.
- **Task-Retry**: `MAX_RETRIES=3` with exponential backoff on API errors.
- **MMLU-Pro helper extracted**: `_get_lmeval_params()`, `_build_lmeval_cmd()`, `_parse_subset_score()` as testable individual functions.
- **ModelData dataclass**: In `src/consolidate_results.py` – typed CSV rows instead of raw dicts.
- **System metrics**: Median + P90 instead of Mean + Max (more robust against outliers).
- **CSV schema**: `fn_csv` extended with CPU_med/CPU_p90/GPU_med/GPU_p90/RAM_med/RAM_p90/GPU_Temp_p90.
- **API_BASE**: No longer hardcoded, but sourced from `model_manager.API_BASE`.
- **all_summary bug fixed**: `all_summary.append()` was incorrectly inside the `if is_custom:` block – all 4 pipelines now end up in the summary.
- **Pytest tests**: 15 tests for compute_category_scores, read_custom_csv, Percentile, CSV parsing.
- **Granite 4.0 H Tiny**: Experts=64 causes `ggml_new_object: not enough space` at 1M Context; only viable with Experts=16.
- **Thinking mode via CLI**: `--thinking` flag forces `enable_thinking=True` for MATH-500 on all reasoning models (controlled via `REASONING_PATTERNS` in `src/benchmark_config.py`).
- **Structured output (v30)**: Custom pipeline uses `response_format` with JSON schema (`{"code": "..."}`) via LM Studio API. Guarantees valid JSON, eliminates ~12% parsing errors (empty responses, markdown extraction). Fallback via `--no-structured-output`.
- **Paired bootstrap comparison (v30)**: `consolidate_results.py --compare "key1,key2,key3"` compares all pairs with paired bootstrap CI. `--seed` ensures identical task subsets.
- **--seed for reproducibility (v30)**: `run_benchmarks.py --seed 42` and `custom_benchmark.py --seed 42` enable reproducible task selection.
- **--bootstrap removed (v30)**: CIs are always computed when per-item data exists. No flag needed.
- **Context length (v32)**: Taken from the `user-concrete-model-default-config` JSONs (no longer a CLI parameter). Typically 8192-16384 – sufficient for all benchmarks (DS1000~1.2K, MATH-500~1K, Agentic~9K), massively reduces VRAM pressure on 128K models.
- **Variant C+ (p6)**: Sampling parameters are no longer model-specific but benchmark-category-dependent. Four category defaults (`coding`, `math`, `knowledge`, `agentic`) in `BENCHMARK_CATEGORY_DEFAULTS` + optional model overrides in `MODEL_TEMP_OVERRIDES`. Unified `get_model_config()` function replaces the separate `_get_model_config()` and `_get_lmeval_params()` (see §2.10).

---

## 2. Main Flow (run_benchmarks.py)

### 2.1 main() Function – Central Model Management

All pipelines use the exact model ID from `model_info["_api_model"]` (e.g. `microsoft/phi-4@q6_k`). No more `variant`/`key` mismatches:

```
main()
├── stdout.reconfigure(encoding='utf-8')
├── os.environ["PYTHONIOENCODING"] = "utf-8"     # Global for subprocesses
├── Parse arguments (--model, --benchmarks, --sample-size)
├── get_available_models()                        # lms ls --json -> deduplicated by model_family; filters MTP drafter/mmproj support files (03.08., F1)
├── resolve_models()                              # exact match before substring
├── resolve_benchmarks()
│
├── for MODEL in models:
│   │
│   ├── [Registry checks BEFORE loading]          # NEW 24.07., see §2.6a
│   │   ├── 1. Model in registry?                 → otherwise skip
│   │   ├── 2. reasoning field set?               → otherwise skip
│   │   ├── 3. capabilities field set?            → otherwise skip
│   │   ├── 4. blueprint field set?               → otherwise skip
│   │   ├── 5. truncation field valid?            → WARN + default
│   │   ├── 6. systemPrompt in Config JSON?       → WARN if empty
│   │   └── 7. Template file exists?              → WARN if missing
│   │
│   ├── Reasoning-/MoE detection (Timeout x2 / display)
│   ├── get_current_loaded_model()                # lms ps --json
│   ├── if same model loaded:
│   │   └── api_model = loaded["identifier"]
│   │   └── (unload + reload)                     # for different model
│   │       ├── unload_all_models()
│   │       ├── ok, api_model = load_model_via_lms(model_key)  # -> exact ID (Config from JSON)
│   │       └── time.sleep(10)                    # Wait for API initialization
│   │
│   ├── model_info["_api_model"] = api_model      # GLOBAL for all pipelines
│   │
│   ├── for BENCHMARK in benchmarks:
│   │   ├── if agentic:
│   │   │   └── run_agentic(mode=args.agentic_mode, seed=args.seed)  # tool-eval-bench
│   │   ├── if evalplus (HumanEval+/MBPP+):
│   │   │   ├── evalplus.codegen --id-range [0,N) # exclusive end
│   │   │   └── evalplus.evaluate
│   │   ├── if lmeval (MATH-500, ARC, HellaSwag, TruthfulQA):
│   │   │   └── lm_eval --model local-chat-completions
│   │   └── if custom (DS1000/CoderEval):
│   │       └── custom_benchmark.py --subprocess
│   │           (Script resolved via dynamic glob: CUSTOM_BENCHMARK_SCRIPT)
│   │
│   └── all_summary.append(result)                # all 4 pipelines (Bugfix 28.06.)
│   └── csv_writer.write_accumulative_summary()   # Intermediate summary
│
├── unload_all_models()                            # Free memory
└── csv_writer.write_konsolidiert_aktuell()        # Overall overview (for >1 model)
```

### 2.1a Pre-Run Registry Checks (NEW 24.07.)

Before loading a model, `src/run_benchmarks.py` checks 7 conditions. Every failed check leads to **skip with error message** (ERROR) or **WARN**:

| # | Check | Failure mode | Recommended fix |
|---|---------|-------------|-----------------|
| 1 | Registry entry exists | ERROR + skip | `python src/registry_tool.py sync` |
| 2 | `reasoning` field set | ERROR + skip | `python src/registry_tool.py sync` |
| 3 | `capabilities` field set | ERROR + skip | `python src/assemble_blueprint.py classify` (or `sync`) |
| 4 | `blueprint` field set (`!= none`) | ERROR + skip | `python src/assemble_blueprint.py classify` (or `sync`) |
| 5 | `truncation` valid (`full/medium/minimal`) | WARN + default | `python src/assemble_blueprint.py classify` (or `sync`) |
| 6 | `systemPrompt` in Config JSON not empty | WARN | `python src/assemble_blueprint.py assemble` (or `sync`) |
| 7 | Template Jinja file exists (if `template:` set) | WARN | Create template file in `doc-git/Jinja-Chat-Templates/` |

### 2.2 Model Management Architecture

**OLD (before v20):** Three independent loading sources -> double loading.

**NEW (v20+):**
- `src/model_manager.py` contains ALL model functions
- `src/run_benchmarks.py` imports from `model_manager` - only caller of load/unload
- `src/custom_benchmark.py` imports from `model_manager`, **never** calls `load/unload`
- `_api_model` (exact ID from `lms ps`) is used consistently in **all** pipelines
- `API_BASE` is sourced from `model_manager.API_BASE` (not hardcoded in the Launcher)
- **Context length:** Taken from the `user-concrete-model-default-config` JSONs (no longer a parameter to `load_model_via_lms()`). Typically 8192–16384 – sufficient for all pipelines (DS1000~1.2K, MATH-500~1K, Agentic~9K) and massively reduces VRAM pressure on models with native 128K+ context.

### 2.3 Model Readiness (simplified in v9)

**OLD (before v9):** `wait_for_model_ready()` polled POST `/v1/chat/completions` with `"model": "check"` (previously POST `inference` endpoint). Often failed because `"model": "check"` is not a valid LM Studio model name.

**OLD (v9 initial):** `check_api_available()` polled GET `/v1/models` every 2s (max 90s). Failed because the REST server needs additional time for model initialization after `lms load`.

**NEW (v9 fix):** After `load_model_via_lms()`, the model is confirmed via `lms ps --json`. Then simple `time.sleep(10)` - no more polling loop:

```python
# run_benchmarks.py:
ok, api_model = load_model_via_lms(model_key)  # lms load + lms ps polling
print("  [INFO] Waiting 10s for API initialization...")
time.sleep(10)
model_info["_api_model"] = api_model
```

After reload (when custom benchmark unexpectedly unloaded the model): also `time.sleep(10)`.

### 2.4 Dynamic Subprocess Resolution (NEW in v7/v24, retained in v10)

**Problem:** With `Copy-Item custom_benchmark_v23.py custom_benchmark_v24.py` the launcher had to be manually updated, otherwise it would call the old version.

**Fix:** The launcher determines the highest existing `custom_benchmark_v*.py` via glob:

```python
_custom_scripts = glob.glob(os.path.join(BASE_DIR, "custom_benchmark_v*.py"))
_versions = [(int(re.search(r'_v(\d+)\.py$', s).group(1)), s) for s in _custom_scripts]
CUSTOM_BENCHMARK_SCRIPT = max(_versions, key=lambda x: x[0])[1]
```

Advantage: After `Copy-Item`, the new version is used immediately without manual intervention.
Disadvantage: Both versions (old + new) must exist during the run, since resolution happens only at startup.

### 2.5 id_range Correction

**Bug:** EvalPlus uses `[low, high)` (exclusive end). `id_range = "[0,sample_size-1]"` with SampleSize=8 produced the range `[0,7]` -> only 7 tasks.

**Fix:** `id_range = f"[0,{args.sample_size}]"` -> SampleSize=20 -> `[0,20]` = 20 tasks.

### 2.6 Model Classification

Reasoning detection uses a **hybrid approach** with 4-tier priority chain:

```
classify_reasoning(model_name, notes, arch, existing_reasoning)
  ├── 1. existing_reasoning      GGUF-Header / user override (highest priority)
  ├── 2. _ARCH_REASONING_MAP     Known architecture (qwen3→thinking, gpt-oss→instruct, …)
  ├── 3. NON_REASONING_MODELS    Keyword blacklist (whisper, flux, …)
  ├── 4. REASONING_KEYWORDS      Keyword whitelist (r1, qwq, thinking, …)
  └── 5. Default: "instruct"     Fallback
```

**Sources of classification (in order of reliability):**

| Source | Method | Set by |
|--------|---------|-------------|
| **GGUF chat_template** | `_detect_reasoning_from_template()` via Regex: `<\s*(think|thinking|thought)>`, `enable_thinking`, `reasoning_effort` | `cmd_fill_reasoning()` → Registry `reasoning` field |
| **Architecture map** | `_ARCH_REASONING_MAP` in `src/assemble_blueprint.py`: qwen3/qwen35/deepseek2/kimi-linear → `thinking`, gpt-oss/nomic-bert/flux → `instruct/none` | `classify_reasoning()` Priority 2 |
| **Keyword heuristic** | `REASONING_KEYWORDS` (`r1`, `qwq`, `thinking`, …) + `NON_REASONING_MODELS` | Fallback without GGUF data |

**Used by:**

| Function | Location | Purpose |
|----------|-----|-------|
| `_is_reasoning_model()` | `src/run_benchmarks.py` | Timeout ×2 for reasoning models |
| `_check_reasoning_registry()` | `src/run_benchmarks.py` | Tri-State: True/False/None |
| `is_reasoning_model` | `run_benchmarks.py:1301` | Pre-run check before model loading |
| `get_model_config()` | `src/benchmark_config.py` | `--thinking` flag control |
| `classify_registry()` | `src/assemble_blueprint.py` | Bulk classification during `sync` |

**`_ARCH_REASONING_MAP` (statische Architektur→Reasoning-Zuordnung):**

```python
_ARCH_REASONING_MAP = {
    "qwen3": "thinking",    "qwen35": "thinking",
    "qwen35moe": "thinking", "qwen3moe": "thinking",
    "deepseek2": "thinking", "kimi-linear": "thinking",
    "gpt-oss": "thinking",  # 27.07.: Harmony-Template (analysis/commentary/final-Kanaele)
    "nomic-bert": "none",    "flux": "none",
}
```

> **Qwen3 family (01.08.):** `classify_reasoning()` checks the **model name** for `qwen*` architectures:
> `-instruct` variants → `instruct`, `-thinking` variants → `thinking` (HF card
> Qwen3-30B-A3B-Instruct-2507; Qwen3.6 dual-mode).

**Further detections:**

```
_is_moe_model()            → only display "(detected)"
_is_qwen3_5_model()        → system-less prompt embedding (no_system_msg)
_is_gptoss_model()         → stop tokens for evalplus/lmeval
_is_reasoning_model()      → reads registry reasoning field (Timeouts x2)
```

The registry `reasoning` field is automatically populated from GGUF chat_templates via `registry_tool.py fill-reasoning` (part of the `sync` pipeline). `_load_registry_for_context()` loads the entire registry (no longer filtered by `context_length`).

> **Registry-driven enable_thinking (31.07.):** `get_model_config()` (`benchmark_config.py`) has
> since 31.07. a **new priority level**: if the model's registry `reasoning` field is
> `thinking`, `enable_thinking=True` is set — without the `--thinking` flag. Explicit
> `MODEL_TEMP_OVERRIDES` entries win (kimi/qwen3.5/qwen3.6/gemma remain `False`).
> Lookup via `_registry_reasoning()` (publisher prefix and `@quant` suffix are stripped; no
> cross-publisher fallback). This makes deepseek-r1-distill-qwen-14b think by default.
> Details: `doc-git/thinking-config_en.md`.

**Sampling parameters** are no longer assigned per model class since Variant C+, but via the category system (see §2.10).

### 2.7 Task-Retry Mechanism (NEW in v10, after review)

```python
MAX_RETRIES = 3
for attempt in range(1, MAX_RETRIES + 1):
    try:
        result = benchmark_task(...)
        if result is not None:
            return result
    except Exception as e:
        if attempt < MAX_RETRIES:
            wait = 2 ** attempt  # exponential backoff: 2s, 4s, 8s
            print(f"[RETRY] Attempt {attempt} failed: {e}. Waiting {wait}s...")
            time.sleep(wait)
        else:
            print(f"[FAIL] All {MAX_RETRIES} attempts failed.")
            return 0.0, f"Max retries exceeded: {e}"
```

### 2.8 Split: `--model_args` vs `--gen_kwargs` (Bugfix 11.07.)

**Problem (until 10.07.):** `_get_lmeval_params()` placed all parameters (`max_tokens`, `temperature`, `top_p`, `min_p`, `until`, `extra_body`) in `--model_args`. These ended up in the constructor `LocalChatCompletion.__init__(**kwargs)` and were **silently ignored** there (openai_completions.py:158 `**kwargs`). The API payload instead used the `generation_kwargs` from the task YAML (`max_gen_toks: 20` → only 20 tokens → 0% score).

**Fix:** Split into two CLI parameters:

| Parameter | Receiver | Contains |
|-----------|----------|----------|
| `--model_args` | `LocalChatCompletion.__init__()` | `base_url`, `model`, `num_concurrent`, `max_gen_toks` (fallback), `eos_string` |
| `--gen_kwargs` | Evaluator merges into YAML `generation_kwargs` → API payload (via `**gen_kwargs` in `_create_payload()`) | `max_tokens`, `temperature`, `top_p`, `top_k`, `min_p`, `until`, `extra_body` |

**Effect:** `extra_body.chat_template_kwargs.enable_thinking` now flows into the LM Studio request for the first time. `max_tokens` overrides YAML's `max_gen_toks`. `temperature`/`top_p`/`min_p` are set correctly.

**Reference:** `run_benchmarks.py:709-754`, `openai_completions.py:189-206` (LocalChatCompletion._create_payload)

### 2.9 Sampling Parameters: Variant C+ (p6, 15.07.2026)

**Problem:** Previously, sampling parameters (`temperature`, `top_p`, `max_tokens`) were assigned either model-specifically in `THINKING_CONFIG` (43 entries) or via if-else cascade in `_get_lmeval_params()` (7+ branches). This was maintenance-intensive and scientifically questionable: Coding benchmarks run deterministically (`temp=0.0`), while reasoning benchmarks need sampling (`temp=0.6–1.0`).

**Solution (Variant C+):** The temperature is now determined by the **benchmark category**, not by the model:

```
BENCHMARK_CATEGORY_DEFAULTS  (global, 4 entries)
  ├── "coding":    temp=0.0,  top_p=1.0,   max_tokens=2048, enable_thinking=False
  ├── "math":      temp=0.7,  top_p=0.95,  max_tokens=8192, enable_thinking=True
  ├── "knowledge": temp=0.0,  top_p=1.0,   max_tokens=2048, enable_thinking=False
  └── "agentic":   temp=0.3,  top_p=0.95,  max_tokens=4096, enable_thinking=False
                          │
                 MODEL_TEMP_OVERRIDES  (additive merge)
                          │
              (e.g. phi-4-reasoning: temp=0.8, top_k=50)
                          │
               --thinking flag  (forces enable_thinking)
```

**Category Mapping:**

| Pipeline | Benchmarks | Category |
|----------|------------|----------|
| Custom | DS1000, CoderEval | `coding` |
| EvalPlus | HumanEval+, MBPP+ | `coding` |
| LM-Eval | ARC-Challenge, HellaSwag, TruthfulQA | `knowledge` |
| LM-Eval | MATH-500 | `math` |
| LM-Eval | IFEval | `agentic` |
| Agentic | tool-eval-bench | `agentic` |

**Model overrides** (only when manufacturer recommendation differs from category default):

| Pattern | Overrides | Reason |
|---------|----------|--------|
| `phi-4-reasoning` | temp=0.8, top_k=50 | Model Card: "do_sample=True for all tasks" |
| `gpt-oss` | temp=1.0, top_k=0, stop/Harmony | Harmony format requires sampling |
| `magistral` | temp=0.7 | Mistral recommendation |
| `ministral` | temp=0.7 | Mistral recommendation |
| `nemotron` | temp=0.7 | [THINK]-token-based reasoning |
| `apriel` | temp=0.6 | [BEGIN FINAL RESPONSE] format |
| `deepseek` | temp=0.6, min_p=0.02 | Reasoning needs moderate temp |
| `qwen3.6` | enable_thinking=False | Thinking tokens block token budget |
| `qwen3.5` | temp=0.2, no_system_msg | System-less prompt embedding |
| `gemma` | enable_thinking=False | Thinking disrupts coding benchmarks |

**Merge order** (higher wins):
1. `BENCHMARK_CATEGORY_DEFAULTS[category]` – global default
2. `MODEL_TEMP_OVERRIDES[pattern]` – model override (additive, via substring match)
3. `--thinking` CLI flag – forces `enable_thinking=True` for reasoning models

**Implementation:**
- `src/benchmark_config.py`: `get_model_config(model_key, category, thinking)` – single merge function
- `src/custom_benchmark.py`: `_get_model_config()` delegates to `get_model_config()`; benchmark_category is determined in `benchmark_model()` via `get_benchmark_category(benchmark_name)`
- `src/run_benchmarks.py`: `_get_lmeval_params()` derives category from `bench_name` and calls `get_model_config()` – the old if-else cascade is eliminated

### 2.10 Error Handling

| Error                   | Handling                              |
|-------------------------|----------------------------------------|
| API timeout (120s)      | Score=0, Detail="Timeout/API error"    |
| SyntaxError in code     | Score=0, Detail="Code error: ..."      |
| API error (e.g. 503)    | Retry up to 3x with exponential backoff |
| Model cannot be loaded  | Skip model                             |
| Model unloaded after custom bench | Automatic reload + 10s pause |
| UnicodeEncodeError      | PYTHONIOENCODING=utf-8 set globally   |
| Granite Tiny Experts=64 | `ggml_new_object: not enough space` at 1M Context; workaround: set Experts=16 |

### 2.11 YAML Run-Spec (NEW 02.08., P3 / v13.0.10)

Reproducible runs via a YAML file instead of long CLI invocations:

```bash
python run_benchmarks.py --run-spec run.example.yaml     # --config is an alias
```

**Precedence: `CLI flags > YAML > script defaults`.** The detection of which CLI flags
were explicitly set is done **exactly** via a SUPPRESS probe parser in `_parse_args`
– not via default-comparison heuristics. A `--seed 99` on the CLI therefore always wins
against a `seed:` value in the YAML.

**Mechanics in `src/run_benchmarks.py`:**
- `RUN_SPEC_DEST_MAP`: YAML key → CLI dest (snake_case + kebab-case aliases).
- `_load_run_spec(path)`: PyYAML `safe_load` (lazy import, fatal on missing file /
  broken YAML / non-mapping). Unknown top-level keys → `[WARN]`, lists
  (models/benchmarks/exclude_benchmarks) → comma string, bool/int validation.
- `_validate_run_spec_selections()`: warning on unknown benchmark/model names
  (against `ALL_BENCH_NAMES` resp. `lms ls --json`; `all`/numbers/ranges → skip).
- `_apply_run_spec(...)`: applies values only if the dest was **not** explicitly set via CLI
  (SUPPRESS probe parse namespace).
- `_LAUNCHER_ARG_SPECS`: shared argument definitions for main & probe parser.

**Supported keys** (example see `run.example.yaml`): `models`, `benchmarks`,
`sample_size`, `seed`, `agentic_mode` (`random`/`safety`), `exclude_benchmarks`,
`thinking`, `no_structured_output`, `unload_between`, `keep_response`.
`temperature/top_p` overrides are deliberately **not** in the spec – they come from
`MODEL_TEMP_OVERRIDES` (category + model, §2.9).

### 2.12 Seed Propagation (P3)

The `--seed` value is passed **consistently** to all reproducible paths:
- Custom pipeline (`custom_benchmark.py --seed`) → task selection
- Agentic (`run_agentic(..., seed=args.seed)`) → `random.Random(seed)` scenario selection
- EvalPlus (`run_evalplus(..., seed=args.seed)`)
- `tools/parallel_ab.py --seed` (default `RANDOM_SEED=42`) → reproducible prompt selection in `build_prompts()`

---

## 3. Task Distribution (v13 - 9 Benchmarks)

| Benchmark       | Custom (v13) | lm-eval | evalplus | Agentic |
|-----------------|:------------:|:-------:|:--------:|:-------:|
| DS1000          | **Yes**      | No      | No       | No      |
| CoderEval       | **Yes**      | No      | No       | No      |
| HumanEval+      | No           | No      | **Yes**  | No      |
| MBPP+           | No           | No      | **Yes**  | No      |
| MATH-500        | No           | **Yes** | No       | No      |
| ARC-Challenge   | No           | **Yes** | No       | No      |
| HellaSwag       | No           | **Yes** | No       | No      |
| TruthfulQA      | No           | **Yes** | No       | No      |
| Agentic         | No           | No      | No       | **Yes** |

**Removed:** PandasEval (too few/insufficiently informative tasks), BBH (too expensive, 8x multiplier), MMLU-Pro (too expensive, 14 subsets).

---

## 4. MATH-500 (replaces MathQA)

MATH-500 is a standardized math benchmark (500 tasks from the MATH dataset).
It replaces MathQA (604 multiple-choice tasks), as MATH-500 offers better coverage of mathematical
concepts and is more widely adopted.

**Pipeline:** `lm_eval --model local-chat-completions --tasks minerva_math500 --gen_kwargs ...` 
(generation, no multiple choice). Extraction of the final answer via `\boxed{}` regex.

**Windows SIGALRM bug (fixed 15.07.):** The original `minerva_math500` task from lm-eval uses 
`signal.SIGALRM` for timeouts in `is_equiv()` – does **not exist on Windows**. This caused EVERY 
answer to be scored as incorrect (0.0% for all models). **Fix:** Custom task in 
`lm_eval_tasks/minerva_math500/` with SIGALRM-free `process_results()`: Extracts `\boxed{...}`
content via regex, normalizes and compares as string. No `math_verify`, no `sympy.parse_latex` 
with signal timeout.

**MathQA (removed):** Previously used (604 multiple-choice A-E). Replaced by MATH-500 (open generation).

---

## 5. Agentic Pipeline

`run_agentic(model_info, limit, mode="random", seed=None)` in `src/run_benchmarks.py`:

```
tool_eval_bench CLI (v2.0.7+)
├── --base-url http://127.0.0.1:1234/v1
├── --scenarios TC-XX ... (mode="random": from TOOL_EVAL_SCENARIO_IDS = TC-01..TC-69
│                           mode="safety": from AGENTIC_SAFETY_SCENARIO_IDS = 13 Category-K)
├── --json-file <agentic_<model>_<ts>.json>
├── --timeout 600 (per scenario, from PIPELINE_TIMEOUTS["agentic_scenario"])
├── --no-live (no interactive UI)
└── Result: final_score (0-100) from JSON envelope, normalized to 0-1
```

The scenario selection is **deterministic**: `random.Random(seed).sample(all_ids, limit)` –
not global `random`. `seed=args.seed` comes from the launcher (resp. the run-spec, §2.12).

Timeout per scenario: `PIPELINE_TIMEOUTS["agentic_scenario"]` = 600s (10 minutes)
Total runtime per model: `PIPELINE_TIMEOUTS["agentic_subprocess"]` = 3600s (60 minutes)

The 600s per scenario prevent the previous problem where `tool_eval_bench` aborted the HTTP request after 120s while the model was still generating a tool call. For very large multi-turn contexts (>5000 tokens), the timeout can be increased further if needed.

### tool-eval-bench v2.0.7 — CLI changes (2026-07-29)

Since the tool-eval-bench upgrade to v2.0.7 the CLI has changed:

| Old (before v2.0.7) | New (v2.0.7+) | Note |
|------------------|----------------|-----------|
| `--model` (auto-detection via `lms ps`) | `--model` explicit | Auto-detection removed, must be added manually if needed |
| `reasoning=off` in payload | `--no-think` | Dedicated flag, no `backend-kwargs` needed anymore |
| `max_tokens` patch in `orchestrator.py:379` (4096→512) | **Removed** | v2.0.7 has no hardcoded `max_tokens` override anymore. Control via `--backend-kwargs '{"max_tokens": 512}'` if necessary |
| `--timeout 120` | `--timeout 600` | Controlled by `PIPELINE_TIMEOUTS["agentic_scenario"]` |
| `reasoning` API parameter | `--no-think` | Direct replacement |

The former source patch in `tool_eval_bench\runner\orchestrator.py:379` (`max_tokens=4096→512`) is **no longer needed**, since v2.0.7 respects the backend behavior (LM Studio controls `max_tokens` via Config).

**Fallback for too-long answers:** append `--backend-kwargs '{"max_tokens": 512}'` to the command.

### AGENTIC_SAFETY_SCENARIO_IDS – Adversarial Safety Mode (NEW 02.08.)

`benchmark_config.py` defines 13 "Category-K" scenarios (Safety & Boundaries) from
tool_eval_bench v2.0.7 (source: `evals/scenarios.py` + `evals/scenarios_adversarial.py`):

```python
AGENTIC_SAFETY_SCENARIO_IDS = [
    "TC-31", "TC-32", "TC-33", "TC-34", "TC-35", "TC-36",   # Prompt-injection related
    "TC-41", "TC-42", "TC-43",                               # Safety / Boundaries
    "TC-57", "TC-58", "TC-59", "TC-60",                      # further Category-K
]
```

**Selection via `--agentic-mode`** (CLI or run-spec):
| Mode | Scenarios | Purpose |
|------|-----------|-------|
| `random` (default) | all 69 (`TOOL_EVAL_SCENARIO_IDS`) | Regression / normal benchmark |
| `safety` | only the 13 Category-K | Adversarial-safety selection (C≥K) |

Call signature: `run_agentic(model_info, limit, mode="random", seed=None)` – `mode` and
`seed` are passed from the launcher (§2.1), `random.Random(seed)` makes the selection
reproducible. Unknown modes → WARN + fallback to `random`.

### --no-unload-between (NEW in v13)

The `--no-unload-between` flag prevents unloading/reloading between benchmarks of the same model.
By default, the model is unloaded after each benchmark (to save VRAM). With `--no-unload-between`
the model stays loaded – useful for many small benchmarks, but risky for models just above 16 GB VRAM.

### registry_tool.py (NEW 14.07., extended 24.07.)

**`src/registry_tool.py`** consolidates three previously separate code locations for registry and JSON config maintenance:

| Command | Origin | Function |
|---------|--------|----------|
| `compare` | Previously embedded Python in `sync_model_configs.ps1` | Compare Registry vs LMS vs JSON configs |
| `add` | Previously embedded Python in `sync_model_configs.ps1` | Add new LMS models to registry (canonical Key = `publisher/model-name`), **reads n_layers/hidden_dim automatically from GGUF header**. **24.07.:** interactive prompt question when GGUF is missing (`[i]nstruct/[t]hinking/[n]one`). **03.08. (F1):** `_is_support_file()` check centralized in `benchmark_config.py` – MTP drafter (`mtp-*` files, `MTP/` folder, `-assistant` architecture) and `mmproj*` are skipped (also in `_resolve_model_path_multi`) |
| `configs` | Previously embedded Python in `sync_model_configs.ps1` | Write `load.fields` (offloadRatio, numParallelSessions, useUnifiedKvCache) to JSON configs. **useUnifiedKvCache decision via VRAM formula** (see below) |
| `fix-np` | **NEW 17.07.** | **DEPRECATED seit 13.08.:** np ist feste Policy (SS≥10→4, sonst 1), kein Registry-Feld – Stub zeigt nur Info, schreibt nichts |
| `fix-ctx` | **NEW 17.07.** | Re-calculate `context_length` for ALL entries based on np policy (=4)/KV-quant values |
| `sync-ctx` | `sync_context_length.py` | Adopt `context_length` from JSON configs into Registry |
| `sync-from-configs` | **NEW 17.07.** | Melde-Modus: offload, useUnifiedKvCache **aus JSON configs** reporten (skips context_length to preserve native model limit; schreibt nichts) |
| `fill-ctx` | `fmt_registry.py` | Fill missing `context_length` in the registry (size-based formula) |
| `fill-size` | **NEW 15.07.** | Fill `file_size_bytes` from LMS cache for registry entries without size |
| `fill-arch` | **NEW 17.07.** | Write `n_layers`/`hidden_dim` from **local GGUF files** (header reader, ~1ms/file) into registry |
| `fill-reasoning` | **NEW 21.07., extended 24.07.** | Fill missing `reasoning` field in registry from GGUF chat_template (`_detect_reasoning_from_template()` with Regex instead of substring) |
| `migrate-keys` | **NEW 15.07.** | Migrate entries without publisher prefix to `publisher/model-name` (119 keys migrated) |
| `fmt` | `fmt_registry.py` | Normalize blank lines (none within, one between entries) |
| **`validate`** | **NEW 24.07.** | **7 Checks:** template file exists, Config JSON promptTemplate set, override_overlap, missing_reasoning/capabilities/blueprint, registry_no_config, orphan_override, reasoning_arch_mismatch |
| `sync` | All of the above | **24.07.:** add → fill-arch → fill-reasoning → configs → sync-from-configs → sync-ctx → fill-ctx → fmt → **classify** → **assemble** → **validate** |

**The one command for everything** (after a new model or changes):
```bash
python src/registry_tool.py sync
```
**03.08. (F4):** All entry points are now CWD-independent – alternatively from the project root also
`python -m src.registry_tool sync` (sys.path bootstrap in `run_benchmarks.py`, `custom_benchmark.py`,
`consolidate_results.py`, `registry_tool.py`).
This command automatically invokes:
1. `add` – new models from LMS
2. `fill-arch` – n_layers/hidden_dim/reasoning from GGUF
3. `fill-reasoning` – reasoning from GGUF chat_template
4. `configs` – load.fields into JSON configs
5. `sync-from-configs` – JSON→Registry
6. `sync-ctx` – context_length from JSON
7. `fill-ctx` – default context_length
8. `fmt` – blank lines
9. **`classify_registry()`** – set reasoning, capabilities, blueprint, truncation
10. **`assemble_prompts()`** – write prompt into JSON configs
11. **`validate_prompts()`** – syntax check

**Further invocations:**
```bash
python src/registry_tool.py validate      # 7 checks (see above)
python src/registry_tool.py compare       # Report only
python src/registry_tool.py add <file>    # New models from JSON file
python src/registry_tool.py configs       # Write load.fields only
python src/registry_tool.py sync-ctx      # Sync context_length only
```

**`sync_model_configs.ps1`** was converted to `src/registry_tool.py` (no more embedded Python). The old scripts `sync_context_length.py` and `fmt_registry.py` are thin wrappers that delegate to `src/registry_tool.py`. **`fmt_registry.py` was removed** (function duplicated in `registry_tool._format_blank_lines()`).

### model_registry.yaml – Fields

| Field | Type | Default | Set By | Description |
|-------|------|---------|--------|-------------|
| `offload` | int (0-1) | 1 | `add` / registry manual | GPU offload ratio (1 = full GPU offload) |
| `k_cache` | str | `q8_0` | registry manual | KV cache quantization (K) – Gemma-4/GPT-OSS: `f16` |
| `v_cache` | str | `iq4_nl` | registry manual | KV cache quantization (V) – Gemma-4/GPT-OSS: `f16` |
| `file_size_bytes` | int | – | `add` / `fill-size` | GGUF file size (for context_length formula + useUnifiedKvCache formula) |
| `context_length` | int | Formula-based | `fill-ctx` / `sync-ctx` | Calculated from `file_size_bytes`, np policy (=4), KV quant (default 16384 when size missing) |
| `useUnifiedKvCache` | bool | VRAM formula | `configs` | Written to JSON config via `configs` (not permanently in Registry) |
| `n_layers` | int | – | `add` / `fill-arch` | Number of transformer layers (from GGUF header `block_count`) |
| `hidden_dim` | int | – | `add` / `fill-arch` | Embedding dimension (from GGUF header `embedding_length`) |
| `reasoning` | str | – | `add` / `fill-reasoning` | `thinking` (model has reasoning/thinking capability) or `instruct` (no reasoning). Read from GGUF `tokenizer.chat_template` via `_detect_reasoning_from_template()` (Regex) |
| `capabilities` | str | – | `classify_registry()` | Comma-separated: `text`, `coding`, `vision`, `audio`, `agentic`. Auto-detected via name + arch + notes |
| `blueprint` | str | – | `classify_registry()` | Prompt blueprint name (e.g. `default_chat`, `coding_agent`, `reasoning_assistant`). From `reasoning` + `capabilities` |
| `truncation` | str | – | `classify_registry()` | `full` / `medium` / `minimal` (depending on context_length) |
| `custom_template` | bool | – | `classify_registry()` | `True` if YAML `template:` is set (Jinja override active) |

> **`num_parallel` ist seit 13.08. KEIN Registry-Feld mehr** – feste Benchmark-Policy:
> `_resolve_num_parallel(SS)` = 4 bei SS≥10, sonst 1 (run_benchmarks.py). Kein CLI-Override,
> kein Registry-Lookup. Das `fix-np`-Kommando ist deprecated (zeigt nur noch Info).
> Vom verfügbaren Speicher, der Kontextlänge und der KV-Quantisierung hängt nur noch
> `useUnifiedKvCache` ab – nicht np.

**Architecture data (n_layers, hidden_dim):** Are automatically read from the GGUF header when adding new models (`add`). Can be retroactively filled for existing models via `fill-arch`. The lightweight header reader takes ~1ms per file (no memory-mapping of the entire ~12GB model). Models without GGUF files (uninstalled) receive no architecture data.

### useUnifiedKvCache – VRAM Formula (17.07.)

The decision for `useUnifiedKvCache` (ON/OFF) is made in `cmd_configs` via a VRAM estimation:

```
model_gb     = file_size_bytes / 1_000_000_000         # Model size in GB
kv_bytes     = bytes_K(cache) + bytes_V(cache)         # e.g. q8_0(1.0) + iq4_nl(0.5) = 1.5
kv_gb        = n_layers × hidden_dim × 2 × kv_bytes × context_length / 1_000_000_000
total_gb     = model_gb + kv_gb × num_parallel
useUnifiedKvCache = total_gb ≥ 14.0                    # ON at VRAM scarcity
```

**Rationale:** With np>1, multiple parallel KV caches are allocated. When total VRAM requirement (model + np × KV cache) ≥ 14.0 GB of a 16 GB GPU (15.2 GB usable due to overhead), `useUnifiedKvCache` activates the shared cache (saves VRAM, costs some performance). With sufficient VRAM (<14.0 GB), the cache stays separate (faster).

**Fallback** (without n_layers/hidden_dim): `useUnifiedKvCache = model_gb ≥ 9.0` (old heuristic).

**KV bytes per element:**

| Quant | Bytes/Element |
|-------|:-------------:|
| `q8_0` / `q8_1` | 1.0 / 2.0 |
| `q5_1` / `q5_l` | 0.625 |
| `iq4_nl` / `q4_0` | 0.5 |
| `q4_1` | 0.625 |
| `f16` | 2.0 |

### context_length – Calculation (Default)

From `_default_ctx_from_size()` in `src/registry_tool.py`:

```
based on file_size_bytes (GB):
  >14 GB → 16384 | >13 GB → 32768 | >12 GB → 49152
  >11 GB → 65536 | >10 GB → 98304 | >9 GB  → 131072
  else  → 262144

at np > 1: kv_ref = 1.5 (q8_0 + iq4_nl)
            kv_actual = bytes_K + bytes_V
            scale = (kv_ref / kv_actual) / np
            return max(2048, int(base_ctx × scale))
```

### GGUF Header Reader

`_read_gguf_arch()` in `src/registry_tool.py` parses the GGUF binary header directly (not the slow `GGUFReader` from the gguf package, which memory-maps the entire file). The format is:
- Magic `GGUF` (4 bytes)
- Version (uint32), TensorCount (uint64), MetadataKVCount (uint64)
- Metadata KV pairs: Key (String), Value (typed: UINT32/STRING/ARRAY/...)
- Looks for `{arch}.block_count` (n_layers), `{arch}.embedding_length` (hidden_dim), and `tokenizer.chat_template` (is_reasoning)
- Returns `(n_layers, hidden_dim, is_reasoning)` where `is_reasoning` is `True` (thinking template), `False` (instruct template), or `None` (no chat template found)
- **Runtime:** ~1ms per file (vs. 5-7s with GGUFReader)

**Blank line formatting:** No blank lines within an entry, exactly one between entries. Automatically ensured by `registry_tool.py fmt` or `save_registry()` in `src/registry_tool.py`.

### Reasoning Parsing in LM Studio (2026-07-07)

**Problem (trigger):** Granite-4.1-30B generated 300-500 tokens per response because LM Studio's `reasoning.parsing` with `<think>`/`</think>` tags was active (default for many models). The model writes a long thought chain before each tool call before producing the actual answer.

**Fix:** `reasoning.parsing.enabled` set to `false`, global stop strings added, context length adjusted per pipeline.

| Aspect | Detail |
|--------|--------|
| File | `...\.lmstudio\.internal\user-concrete-model-default-config\<publisher>\<model>\<model>.gguf.json` |
| Key | `llm.prediction.reasoning.parsing.enabled` |
| Old value | `true` (default) |
| New value | `false` |
| Effect | No more `<think>` blocks → ~50-70% fewer tokens per generation |
| Stop strings | `["<|end_of_text|>", "<|endoftext|>"]` – stops generation at EOS token |
| Context length | Reduced from 49152 to 16384 (matching pipeline specification) |

**Affects ALL models in LM Studio:** The `reasoning.parsing` default is often `true`. For models without native reasoning (that don't have `<think>` tags in training), this produces unnecessarily long responses. It is recommended to set `reasoning.parsing.enabled` to `false` for all models used in the benchmark pipeline.

**LM Studio GUI path:** Chat Panel → Top right "..." → "Model Settings" → "Reasoning Parsing" → Disabled.

---

## 6. System Metrics

Values from **per-task peak values of the monitor thread** (~5Hz sampling during active inference):

```python
def _peak_avg_max(key, min_val=0):
    vals = [r.get(key) for r in results if r.get(key) and r[key] > min_val]
    return sum(vals)/len(vals), max(vals)

_cpu_avg, _cpu_max = _peak_avg_max("cpu_during")
_gpu_avg, _gpu_max = _peak_avg_max("gpu_during")
_ram_avg_pct = avg(ram_during) / total_ram * 100
_vram_avg, _vram_max = _peak_avg_max("vram_during")
```

| Value | Source | Unit |
|-------|--------|------|
| CPU  | `psutil.cpu_percent(interval=0.3)` | % (integer) |
| RAM  | `psutil.virtual_memory()` | % (integer) |
| GPU  | `nvidia_smi` via subprocess | % (integer) |
| VRAM | `lms ps --json` `gpuMemUsage` | GB (1 decimal) |
| GPU Temp | `nvidia_smi` | °C (integer) |

**Storage in CSV (v10, after review):** CPU_avg, CPU_med, CPU_p90, GPU_avg, GPU_med, GPU_p90, RAM_avg, RAM_med, RAM_p90, VRAM_GB, GPU_Temp_max, GPU_Temp_p90.

Median and P90 replace Mean/Max as more robust metrics against outliers.

---

## 7. DS1000 Evaluation

`evaluate_code()` in `src/custom_benchmark.py` goes through 4 evaluation modes:

1. **DS1000 Harness** – if `test_execution` in `code_context` present
2. **Namespace comparison** – if `reference_code` + `setup_code` present
3. **Reference as tests** – if `reference_code` without tests
4. **Direct tests** – if `tests` array present

**Important fixes:**
- `extract_code()`: JSON parsing shortcut for structured output, then regex fallback with `_is_bare_statement` fallback, line-by-line heuristic with break
- `_repair_indentation()`: iterative heuristic for missing indentations + `pass` insertion
- `_unwrap_solution_for_insert()`: removes `def` header for `[insert]` in function body
- Regex: `except(?: |:)` instead of `except ` (bare `except:` not detected)
- **Structured output (v30):** `response_format` with JSON schema guarantees valid JSON. `extract_code()` first parses JSON, then regex. Eliminates ~12% parsing errors (empty responses, markdown extraction).
- **Structured output exclusions (03.08., F5):** `_can_use_structured_output()` (custom_benchmark.py) disables `response_format` for Mamba models (no grammar support), reasoning/thinking modes (structure collision with `<think>` streaming) and **Codestral-22B** (grammar-channel errors in the server log 03.08.). Fallback: regex extraction.

**Harness fail:** The DS1000 harness actually executes the generated code in a Python sandbox. A "harness error" means the code crashed with a runtime error (SyntaxError, NameError etc.). Small models (Granite Tiny, Nerdsking) often have syntax problems with insertion tasks.

**Task-Retry (v10):** On API errors (e.g. LM Studio 503, channel error), the task is retried up to 3x with exponential backoff (2s, 4s, 8s).

---

## 8. exec Sandbox

```
exec_sandboxed(code, timeout=30)
├── template = _build_sandbox_script(code, tests)
├── subprocess.run([sys.executable, "-c", template], timeout=30)
├── if returncode == 0 -> ok
└── else -> error from stderr
```

**Blocked builtins:** eval, exec, open, input, compile, globals, locals, vars
**Blocked modules:** os, subprocess, shutil, socket, http, urllib, ctypes, multiprocessing, threading

---

## 9. lm-eval Integration

| Task | Description |
|------|-------------|
| math500_gen | MATH-500 (generation) |
| arc_challenge_chat | ARC-Challenge (multiple choice) |
| hellaswag_gen | HellaSwag (multiple choice) |
| truthfulqa_gen | TruthfulQA (generation) |

**Model ID:** `model = model_info.get("_api_model") or model_key` - exact ID from `lms ps`.

**Parameters via `--gen_kwargs` (v13, Variant C+ p6):**
Since p6, sampling parameters are assigned **benchmark-category-based**. The category defaults
from `BENCHMARK_CATEGORY_DEFAULTS` are supplemented by `MODEL_TEMP_OVERRIDES` (model-specific).
See §2.9 for details.

| Category | temperature | top_p | max_tokens | enable_thinking |
|----------|-------------|-------|------------|-----------------|
| **coding** | 0.0 | 1.0 | 2048 | False |
| **math** | 0.7 | 0.95 | 8192 | True |
| **knowledge** | 0.0 | 1.0 | 2048 | False |
| **agentic** | 0.3 | 0.95 | 4096 | False |

Model overrides (from `MODEL_TEMP_OVERRIDES`) overwrite individual fields, e.g.:
`deepseek` → temp=0.6, min_p=0.02 | `gpt-oss` → temp=1.0, top_k=0 | `qwen3.6` → enable_thinking=False

**Important (v13):** `--thinking` ONLY has effect with:
- **Gemma 4** (for MATH-500) – activates `<|channel>thought` tags
- **Reasoning models** (detected via name: reasoning/think/r1) – increases timeout ×2
- **All other models** (Qwen3.6, GPT-OSS, Qwen3.5) – `--thinking` is ignored, since `enable_thinking=False` is forced

---

## 10. evalplus Integration

**Patched file: `openai_request.py`**

| Change               | Before       | After      | Reason                                  |
|----------------------|--------------|------------|-----------------------------------------|
| `max_tokens` default | 512          | **4096**   | Reasoning models need more tokens       |
| API parameter        | `max_completion_tokens` | **`max_tokens`** | LM Studio understands `max_tokens` |

**id_range:** `evalplus.codegen --id-range [0,sample_size]` (exclusive end).

---

## 11. CSV Output (csv_writer.py)

Unified schema for ALL pipelines:

```
pipeline;bench;model;score;thinking;cpu_avg;cpu_med;cpu_p90;gpu_avg;gpu_med;gpu_p90;ram_avg;ram_med;ram_p90;vram_gb;gpu_temp_max;gpu_temp_p90
custom;DS1000;Phi-4;0.45;0;35;33;40;42;40;46;32;30;35;12.3;67;65
evalplus;HumanEval+;Phi-4;0.82;0;28;26;32;38;36;42;30;28;33;11.8;62;60
lmeval;MATH-500;Phi-4;0.67;1;31;29;36;40;38;44;31;29;34;12.0;64;62
agentic;Agentic;Phi-4;0.55;0;33;31;38;39;37;43;30;28;32;11.9;63;61
```

**Delimiter:** `;` (semicolon, comma-compatible for German Excel)
**Encoding:** utf-8
**Intermediate summary:** `csv_writer.write_accumulative_summary()` after each model
**Consolidation:** `csv_writer.write_konsolidiert_aktuell()` at the end (only for >1 model)

### Structure-Gate columns (NEW 02.08., P1)

`tasks_*.csv` (per-task raw, `TASK_FIELDS` in `csv_writer.py`) was extended by diagnostic columns
(pure telemetry, **no** score/pipeline change):

| Column | Meaning | Values |
|--------|-----------|-------|
| `output_status` | `classify_output()`: how the raw answer was translated into runnable code | `empty`, `json_ok`, `json_missing_code`, `json_invalid`, `fenced`, `bare` |
| `entry_point_found` | entry-point triage (only if `entry_point` param set) | `true`/`false`/`""` |
| `extracted_code` | extracted code (possibly 200-char truncation) | Text |
| `response` | raw answer (200-char truncation, full text only with `--keep-response`) | Text |

Classification (structured output expects JSON): `json_ok` = valid JSON with `code` field,
`json_missing_code` = JSON without `code`, `json_invalid` = unparsable JSON. Unstructured:
`fenced` (markdown code block detected) vs. `bare` (code directly). Empty → `empty`. The
entry-point triage checks via regex `^def <entry_point>(` only in the **direct-tests path**
(`tests and entry_point`); DS1000 harness/bare remain unchanged (→ `entry_point_found` empty).
`classify_output()` in `custom_benchmark.py:849`.

> The DS1000 re-run measurement with it: Ternary-Bonsai 0.10 (9×`empty`, 1×`fenced`), gpt-oss 0.20
> (10×`fenced`), Bonsai 27B@Q1_0 0.30 (6×`empty`, 4×`fenced`), Bonsai 8B 0.60 (10×`bare`).
> 8B difference to the morning run (0.0→0.6) via `bare` path; details in section 7 of the evaluation file.

### Filename Schema:

| File | Pattern | Example |
|------|---------|---------|
| Per-task raw data | `tasks_{ts}_{bench}_{model}.csv` | `tasks_20260628_093326_DS1000_Granite 4.0 H Tiny.csv` |
| Model summary | `model_{ts}_{model}.csv` | `model_20260628_093326_Granite 4.0 H Tiny.csv` |
| Consolidated (CSV) | `konsolidiert_{ts}.csv` | `konsolidiert_20260628_094051.csv` |
| Consolidated (MD) | `konsolidiert_{ts}.md` | `konsolidiert_20260628_094051.md` |
| **Current consolidated** | `konsolidiert_aktuell.csv` | Always the newest overall overview (overwritten by `write_konsolidiert_aktuell()`) |

**CSV filename rule (v10):** The complete `model_key` (including quant variant) is used as filename, max. 50 characters. In case of name collisions, a suffix `_1`, `_2` etc. is appended.

---

## 12. Consolidation (consolidate_results.py)

```
consolidate_results.py
├── main() – slim (03.08., F3): only calls the named sub-functions
│   ├── _parse_args()            # CLI parsing
│   ├── _read_all_data()         # run/model filter, read/bootstrap calls
│   ├── _write_csv()             # consolidated CSV
│   └── _write_markdown()        # consolidated MD + comparison tables (~190 lines)
├── find_latest_csv(pattern)
├── read_evalplus(model_key)
├── read_lmeval_per_model(model_key)
├── ModelData dataclass (typed rows instead of raw dicts)
├── compute_category_scores(bench_scores)
│   ├── Coding  (35%): HumanEval+, MBPP+, DS1000, CoderEval
│   ├── Math    (25%): MATH-500
│   ├── Agentic (25%): Agentic
│   └── Knowledge (15%): ARC, HellaSwag, TruthfulQA
├── Overall = Coding + Math + Agentic + Knowledge (normalized to 100%)
├── System metrics: median/p90 instead of mean/max
├── _threshold_filtered() for TOP Coding (>=60%)
├── _b5_named() for BOTTOM 5
├── _fmt_pct() with {:.0f}% (whole numbers)
├── fn_csv with median/p90 columns (CPU_med, CPU_p90, GPU_med, GPU_p90, ...)
├── thinking column (0/1) in all pipeline returns, CSVs and consolidation
├── bootstrap_ci(scores, n_resamples=10000) – Bootstrap 95% CI for DS1000/CoderEval from per-item data (always active)
│   ├── ds1000_ci_lo / ds1000_ci_hi / codereval_ci_lo / codereval_ci_hi in CSV
│   └── Format in MD: "XX% [lo–hi]"
├── paired_bootstrap_ci() – Paired bootstrap comparison for 2+ models
│   ├── compare_two_quants() computes difference, CI, p-value
│   └── All pairwise comparisons via itertools.combinations
├── read_paired_scores() – Matches tasks by task_index (same items)
├── write_quant_comparison() in csv_writer.py – CSV + MD output
├── --compare "key1,key2,key3" – Automatic pairwise comparisons
├── --seed – Reproducible bootstrap
├── --models – Model filter
├── --compare-benchmark DS1000|CoderEval|all
├── width duplication removed (only one widths block)
├── _extract_csv_sizes() – per-file sample_size from filename/content; find_latest_csvs()
│   returns 3rd return value custom_sizes {benchmark: {model_key: sample_size}}
├── _collect_pipeline_sample_sizes() – EvalPlus len(eval), LM-Eval sample_len, Agentic total_scenarios
├── _describe_sample_sizes() – MD header "SampleSize=5,20 (DS1000), …" instead of fixed "mixed" (01.08.)
├── _render_complete_table() – content-driven column widths, `|` escaping, decimal-point alignment
│   (longest model name determines column width; numbers right-aligned on the point)
├── _align_decimal_cells() – in-place alignment of numeric cells
├── _write_tbl() – TOP5/BOTTOM5 tables: rank centered, model left, numbers right (01.08.)
└── Generate CSV + MD (alphabetically sorted)
```

### Weights (v10)

| Category | Share | Benchmarks |
|----------|-------|------------|
| Coding   | 35%   | HumanEval+ (25%), MBPP+ (25%), DS1000 (25%), CoderEval (25%) |
| Math     | 25%   | MATH-500 (100%) |
| Agentic  | 25%   | Agentic (100%) |
| Knowledge | 15%  | ARC (33.3%), HellaSwag (33.3%), TruthfulQA (33.3%) |
| **Overall** | **100%** | Sum of all four categories |

### ModelData Dataclass (NEW in v10, after review)

```python
@dataclass
class ModelData:
    model_name: str
    scores: dict[str, float]
    system_metrics: dict[str, float]
    laufzeit_h: float
    eff: float
    toks: float
    vram: float
    quant: str
    cpu_med: float
    cpu_p90: float
    gpu_med: float
    gpu_p90: float
    ram_med: float
    ram_p90: float
    gpu_temp_p90: float
    gpu_temp_max: float
    cpu_avg: float
    gpu_avg: float
    cpu_max: float
    gpu_max: float

    def to_csv_dict(self) -> dict[str, str]:
        ...
```

---

## 13. Benchmark Sources

| Dataset           | Source github                | Tasks                   | Reference            |
|-------------------|-------------------------------|------------------------|---------------------|
| **DS1000**        | `xlangai/DS-1000` (HF)        | 5 Libraries (N Tasks)  | Lai et al. 2023     |
| **CoderEval**     | Manually curated (self_contained+slib_runnable) | ~138 Tasks | CoderEval 2023 |
| **HumanEval+**    | evalplus                      | 164 functions          | Liu et al. 2023     |
| **MBPP+**         | evalplus                      | 378 algorithms         | Liu et al. 2023     |
| **MATH-500**      | openai/gsm8k (HF)             | 500 tasks              | Hendrycks et al. 2021 |
| **ARC-Challenge** | lm-eval built-in              | 259 tasks              | Clark et al. 2018   |
| **HellaSwag**     | lm-eval built-in              | 10042 tasks            | Zellers et al. 2019 |
| **TruthfulQA**    | lm-eval built-in              | 817 tasks              | Lin et al. 2021     |
| **Agentic**       | tool-eval-bench (HF: `aisafety-ai/tool_eval_bench`) | 69 scenarios | -- |

---

## 14. File Structure (Project)

```
Benchmarks/
├── benchmark_config.py              # Central configuration (weights, subsets, scenarios)
├── model_manager.py                 # Model management (unversioned)
├── csv_writer.py                    # CSV schema (unversioned) + write_quant_comparison()
├── custom_benchmark.py          # Current custom pipeline (DS1000 + CoderEval, structured output)
├── run_benchmarks.py            # Current launcher (v13), dynamic script resolution, --seed
├── consolidate_results.py       # Current consolidation (--compare, --models, always-CI)
├── registry_tool.py                 # Registry + JSON config maintenance (consolidated)
├── assemble_blueprint.py            # Prompt-Blueprint-System (classify + assemble + validate)
├── type_defs.py                     # Shared TypedDict definitions
├── generate_quant_map.py            # QUANT_MAP generator (auto-generated)
├── check_agentic.py                 # Agentic diagnostics
├── download_real_benchmarks.py      # Dataset download
├── download_codereval.py            # CoderEval download
├── tests/
│   ├── __init__.py
│   ├── test_scores.py               # 10 tests: compute_category_scores, Percentile
│   ├── test_csv.py                  # 5 tests: read_custom_csv, auto_delimiter
│   └── fixtures/
│       └── test_tasks.csv           # Test data
│
├── simple_evals/                    # JSONL datasets (DS1000, CoderEval)
├── lm_eval_tasks/                   # Custom YAML tasks
│   ├── hellaswag_gen.yaml           # HellaSwag with chat prompt + regex extraction
│   ├── mathqa_gen/                  # MathQA (multi-choice) – Custom YAML + utils.py
│   └── minerva_math500/             # MATH-500 – SIGALRM-free Windows version (15.07.)
├── Doku+Install/                    # Documentation
├── ergebnisse/                      # Results + consolidation
├── ds1000_official/                 # DS-1000 framework (Windows patches)
├── Archiv/alte_py_skripte/          # Archived scripts (old wrappers, one-offs)
└── doc-git/                         # Documentation
```

**Migration path when copying a new version:**
It suffices to `Copy-Item custom_benchmark.py custom_benchmark_v14.py`. The launcher dynamically detects the highest version. No manual launcher update required.

---

## 15. Important Constants

### From model_manager.py

| Constant                   | Value   | Purpose                             |
|----------------------------|---------|-------------------------------------|
| `API_BASE`                 | `http://127.0.0.1:1234/v1` | LM Studio API      |
| `TIMEOUT_HTTP`             | 120 s   | HTTP request timeout                |
| `TIMEOUT_CLI`              | 30 s    | CLI subprocess timeout              |
| `TIMEOUT_LOAD_MODEL`       | 180 s   | Model loading timeout               |

### PIPELINE_TIMEOUTS (in model_manager.py)

| Key                     | Default | Usage                                                       |
|-------------------------|---------|-------------------------------------------------------------|
| `custom_subprocess`     | 3600    | Subprocess timeout DS1000/CoderEval (run_custom_benchmark)  |
| `evalplus_base`         | 600     | Base timeout codegen+evaluate (×2 for reasoning)            |
| `lmeval_base`           | 600     | Base timeout lm_eval (×2 for reasoning)                     |
| `agentic_subprocess`    | 3600    | Total runtime timeout tool_eval_bench                       |
| `agentic_scenario`      | 600     | Timeout per scenario (--timeout to tool_eval_bench)         |

All pipelines import their timeouts centrally from `PIPELINE_TIMEOUTS`.
Changes need ONLY be made in `src/model_manager.py` – no more searching for hardcoded values.

### From benchmark_config.py (NEW in v10, after review)

| Constant                 | Value                       | Purpose                          |
|--------------------------|-----------------------------|----------------------------------|
| `CAT_WEIGHTS`            | `{"Coding": 0.35, "Math": 0.25, "Agentic": 0.25, "Knowledge": 0.15}` | Category weighting |
| `OVERALL_WEIGHTS`        | `{"Coding": {"HumanEval+": 0.25, "MBPP+": 0.25, "DS1000": 0.25, "CoderEval": 0.25}, ...}` | Benchmark weighting per category |
| `TOOL_EVAL_SCENARIO_IDS` | TC-01..TC-69               | Agentic scenarios                |
| `AGENTIC_SAFETY_SCENARIO_IDS` | 13 Category-K TCs (TC-31..36, 41..43, 57..60) | **NEW 02.08. (P4):** adversarial-safety selection at `--agentic-mode safety` |
| `GPTOSS_REASONING_EFFORT` | `medium` | **NEW 02.08.:** central source for gpt-oss reasoning level – controls `patch_reasoning_effort.py` (engine config) AND the system prompt of the `gptoss_reasoning` blueprint synchronously |
| `GPTOSS_REASONING_BUDGET` | `4096` | **NEW 02.08.:** thinking-token budget for gpt-oss (central source, also overridable per `--effort/--budget`) |
| `EXCLUDE_KEYWORDS`       | whisper, vision, ocr, transcription, translat, audit, audio, embed, vl, flux, **german, rag** | Excluded modalities |
| `REASONING_KEYWORDS`     | ["r1", "thinking", "qwq", "cot", "reasoning", "phi-4-reasoning", …] | Keyword whitelist for reasoning detection (lowest priority in the hybrid classification, see §2.6) |
| `_ARCH_REASONING_MAP`   | `{"qwen3":"thinking", "deepseek2":"thinking", "gpt-oss":"instruct", …}` | **NEW 24.07.:** architecture→reasoning mapping in `src/assemble_blueprint.py`. Overrides keyword heuristic. See §2.6 |
| `QUANT_MAP`              | Dict model_key -> Quant label (static, ~45 entries) | Quant mapping for CSV and display. Source priority: QUANT_MAP > `lms ls --json` > Config files > GGUF cache. Auto-generatable via `generate_quant_map.py`. **NEW 18.07.:** `get_quant()` 4-step look-up priority: QUANT_MAP exact → suffix → base → **registry fallback** (`model_registry.yaml:quants` first entry) |
| `PIPELINE_DISCOVERY`     | Glob pattern + version regex | Dynamic script detection        |
| `CUSTOM_BENCHMARK_SCRIPT` | dynamic via `glob()`       | Highest `custom_benchmark_v*.py` |
| `USABLE_VRAM_GB`          | **15.3**                    | **NEW 18.07.:** RTX 5070 Ti 16 GB minus driver/overhead. Single source of truth |
| `USE_UNIFIED_KV_CACHE_THRESHOLD_GB` | **14.0**       | **NEW 18.07.:** When `total_gb >= this`, UKV cache activates |
| `LEGACY_MODEL_GB_THRESHOLD_GB` | **9.0**             | **NEW 18.07.:** Fallback for entries without `n_layers`/`hidden_dim` |
| `KV_QUANT_REFERENCE_BYTES` | **1.5**                    | **NEW 18.07.:** Reference (q8_0 + iq4_nl) for ctx scaling in `_default_ctx_from_size` |

**Removed in v29:** `DISPLAY_NAMES` + `WHITELIST` – replaced by dynamic auto-discovery:
- **Model selection** (`src/consolidate_results.py`): Automatically iterates over all model keys from the result CSVs. Optional filter via `--models key1,key2`.
- **Display names**: Are queried live from `lms ls --json` (field `displayName`), fallback = readable key transformation.
- **QUANT_MAP generator** (`generate_quant_map.py`): Fetches all keys dynamically from `lms ls --json` + result CSVs, no more static import from `src/benchmark_config.py`.
- Background: Whitelist was redundant (selection also possible interactively/CLI), DISPLAY_NAMES replaceable by dynamic sources.

**Removed in p8 (18.07.):** `MMLU_PRO_ENABLED = False` – was imported by `src/run_benchmarks.py` and `src/consolidate_results.py` but never read.

### From custom_benchmark.py (stop strings)

| Constant | Value | Purpose |
|----------|-------|---------|
| `STOP_TOKENS_CODING` | `["\n```\n", "\n# Task", "\n// ", "<|endoftext|>"]` | Coding stops. **01.08.:** `"\n```\n"` instead of `"\n```"` – the old stop matched the code-block **opening** (`\n```python`), which made DeepSeek-R1-Distill abort the answer after ~0 tokens ("No code generated", 0% DS1000/CoderEval). With trailing `\n` the stop only matches the **closing**. Details + live experiment: `doc-git/thinking-config_en.md` §"Stop-String Trap" |
| `STOP_TOKENS_DEFAULT` | `["<|endoftext|>"]` | Default stop without override |

### Single-Instance-Lock (run_benchmarks.py, 01.08.)

`RESULTS_DIR/.benchmark.lock` (JSON `{pid, started}`): prevents **parallel launcher instances** — observed 31.07.: 3 parallel runs loaded/unloaded models against each other (VRAM, then system RAM exhausted, system hang). Stale locks (dead PID, corrupt) are overwritten. `psutil.pid_exists()` as PID check.

---

## 16. Type Hints (NEW in v10, after review)

All 3 main scripts have complete type hints:

| Script | Functions | Imports |
|--------|-----------|---------|
| `src/custom_benchmark.py` | 55 functions | `from collections.abc import Generator` |
| `src/run_benchmarks.py` | 20 functions | `from collections.abc import Iterator` |
| `src/consolidate_results.py` | 27 functions | `from dataclasses import dataclass`, `from collections.abc import Callable` |

**Examples:**

```python
# custom_benchmark.py
def evaluate_generated_code(
    generated_code: str,
    entry_point: str,
    tests_field: Any,
    reference_code: str = "",
    setup_code: str = ""
) -> tuple[float, str]:
    ...

# run_benchmarks.py
def run_benchmarks(
    models: list[str],
    benchmarks: list[str],
    sample_size: int
) -> list[dict[str, Any]]:
    ...

# consolidate_results.py
@dataclass
class ModelData:
    model_name: str
    scores: dict[str, float]
    ...
    def to_csv_dict(self) -> dict[str, str]:
        ...
```

---

## 17. Tests (NEW in v10, after review)

**Status 03.08.2026 (v13.0.10):** **713 passing, 0 failing** (704 → 713, +9 from review 03.08.: 2× MTP drafter/mmproj filter in `test_model_manager.py`, 7× `TestCanUseStructuredOutput` in `test_prio2.py`). 9 skipped tests are obsolete `_get_lmeval_params` if-else-cascade tests (replaced by Variant C+ in v13).

Test files in `tests/`:

| File | Tests | Tested functions |
|------|-------:|------------------|
| `test_scores.py` | 9 | `compute_category_scores()`, `_percentile()`, `_threshold_filtered()`, `_b5_named()` |
| `test_csv.py` | 6 | `read_custom_csv()`, `auto_delimiter_detection()`, CSV parsing with fixtures |
| `test_csv_writer.py` | 55 | `src/csv_writer.py` unified schema (incl. Struktur-Gate-Spalten, `--keep-response`) |
| `test_consolidate.py` | 99 | `src/consolidate_results.py` (percentiles, bootstrap CI, paired bootstrap, quant mapping) |
| `test_consolidate_results.py` | 59 | `src/consolidate_results.py` extended (incl. `TestGetQuant`, `TestTryFloat`, `TestFindNewestByMtime`) |
| `test_custom_benchmark.py` | 86 | `src/custom_benchmark.py` (evaluate_code, extract_code, `_can_use_structured_output`, structure gate) |
| `test_custom_benchmark_io.py` | 28 | `exec_sandboxed` I/O, `_extract_reasoning_delta`, code-only prompts |
| `test_dependencies.py` | 7 | Required Python packages |
| `test_model_manager.py` | 78 | `parse_selection`, `check_api_available`, `get_current_loaded_model`, `get_available_models` (incl. **MTP-Drafter/mmproj-Filter, 03.08. F1**), `load_model_via_lms`, **`unload_all_models` (Bug 1 fix, 18.07.)**, **`_ensure_lmstudio_running` (Bug 2 fix, 18.07.)**, `wait_for_model_ready`, **`_validate_model_key` (18.07.)** |
| `test_parallel_ab.py` | 14 | **NEW 02.08.:** `build_prompts(seed=...)` reproduzierbar, ABBA-Sequenz, Body-Bau, Lock, Report |
| `test_patch_reasoning_effort.py` | 9 | **NEW 31.07.:** `tools/patch_reasoning_effort.py` (defaults from `GPTOSS_REASONING_EFFORT_BUDGET`) |
| `test_prio2.py` | 42 | Prio 2 (Variant C+ category defaults, `_can_use_structured_output`; **+7 `TestCanUseStructuredOutput` 03.08. F5:** normal/disabled/thinking/reasoning/mamba/codestral/none) |
| `test_prio2_terminal.py` | 25 | Prio 0/2/3 terminal findings (incl. **Bug 6.4 fix, 18.07.**: `_unwrap_solution_for_insert` synthetic def for Granite) |
| `test_run_benchmarks.py` | 83 | Launcher & resolve functions. **NEW 02.08.:** `TestRunSpec` (12 Fälle: Laden, Listen→CSV, Unbekannt-Warn, Bool/Int, Fatal-Fehler, `_apply_run_spec` Precedence) + `test_parse_args_cli_flags_win_over_run_spec` |
| `test_registry_tool.py` | 64 | VRAM formula (`_max_ctx_from_vram`), KV-bytes table, match cascade in `cmd_configs`, `_infer_num_parallel` rules, `_is_support_file` (mtp-*/mmproj/MTP-Ordner, F1) |
| `test_assemble_blueprint.py` | 51 | `normalize_model_name`, `classify_capabilities`, `extract_params`, format helpers, `read_lms_configs` cache (5s TTL) |

**Execution:**
```
pytest tests/ -v
```

**Test framework:** pytest with `pytest-mock` and `pytest-timeout`. Shared fixtures in `tests/conftest.py` (`lms_cli`, `lms_http`, `subprocess_scripts`, `fake_lmeval_results`, `tmp_results_dir`).

---

## 18. Known Limitations

1. **Variant selection via CLI:** `lms load` has NO flag to load a specific quantization. `--yes` always loads the first/preferred variant. With 2+ quants of the same model, a warning is displayed; the variant must be chosen via LM Studio GUI or by uninstalling the unwanted variant.
1. **DS1000 score conservative:** ~50% of tasks are not standalone executable (harness fail).
2. **evalplus without Docker:** Same security risk as own sandbox.
3. **No logprobs:** LM Studio does not provide access to token probabilities.
4. **Thinking token extraction:** `<think>...</think>` is stripped.
5. **lm-eval regex:** `mmlu_pro_*` only extracts letters `[A-E]`. Since 11.07.: `mathqa_gen` + `hellaswag_gen` also support lowercase letters `[a-e]`, `[a-d]`.
6. **Windows cp1252 encoding:** `PYTHONIOENCODING=utf-8` set globally.
7. **`lms unload --all` unreliable:** Node processes sometimes remain active. **FIXED 18.07. (Bug 1):** `model_manager.unload_all_models()` no longer uses the racy HTTP-ping with `model:"check"`; it polls `lms ps --json` (canonical LMS state) until the loaded-models list is empty.
8. **MMLU-Pro modified (removed in v13):** Was replaced by MATH-500. MMLU-Pro was too expensive (14 subsets) and provided little differentiation.
9. **API readiness:** `time.sleep(10)` is a hack; for very large models (>30B), initialization can take longer.
10. **GLM 4.7 Flash:** Not runnable on 16 GB VRAM (GPU thrashing).
11. **Gemma 4 19B:** Requires disabled KV quant to load.
12. **llmster.exe hardcoded path (removed 18.07., Bug 2):** The legacy `_ensure_lmstudio_running()` used a hardcoded `.lmstudio/llmster/0.0.12-1/llmster.exe` path that broke on every LMS version update. The fixed implementation tries `lms server start` first (preferred – modern LMS manages the daemon internally), then falls back to discovering the newest `llmster.exe` under `.lmstudio/llmster/*/` via `iterdir()` sorted by version descending.
12. **Granite 4.0 H Tiny:** Experts=64 causes `ggml_new_object: not enough space` at 1M Context. Workaround: set Experts=16. The `num_experts` parameter can only be set via LM Studio Python SDK/REST API, not in the GUI.
13. **numExperts (MoE models):** In `model_registry.yaml` distinguish: `experts:` = LMS setting (reduced due to VRAM), `notes:` contains the architecture value (from specs). The `user-concrete-model-default-config` JSONs store the LMS value as `llm.load.numExperts`.
14. **THINKING_ENABLED global (18.07.):** Module-level global set once in `main()`. Safe in current single-threaded launcher (sequential model iteration), but needs `threading.Lock` if parallel benchmarking is added.
14. **Dynamic script resolution:** The launcher resolves the custom benchmark path only at startup. If the file is replaced during the run, the old version runs until completion.
20. **Windows SIGALRM (minerva_math500):** The original lm-eval task `minerva_math500` uses `signal.SIGALRM` for timeouts in `is_equiv()`. On Windows, this causes every answer to be scored as incorrect (0.0%). Workaround: Custom override in `lm_eval_tasks/minerva_math500/` with SIGALRM-free `process_results()`.
15. **Agentic scenario timeout:** `PIPELINE_TIMEOUTS["agentic_scenario"]` (600s) prevents timeout aborts for long contexts (previously: 120s hardcoded -> abort during tool call generation).
16. **model.yaml conflict:** A virtual model via `hub/models/<publisher>/<model>/model.yaml` collides with an already loaded physical instance of the same GGUF file → llama.cpp crashes with HTTP 500. Workaround: model.yaml only for models without physical instance (e.g. mradermacher/qwen3-coder-reap).
17. **MATH-500 instead of MathQA:** MathQA was replaced by MATH-500 (better coverage, more standardized). MMLU-Pro removed (too expensive, 14 subsets).
18. **`--no-unload-between`:** Off by default. Useful for many small benchmarks, saves loading time.
19. **`--exclude-benchmarks`:** Allows exclusion of individual benchmarks (e.g. `--exclude-benchmarks agentic,custom`).
20. **Consolidate bugfixes (15.07.):** `find_latest_csvs` now pairs DS1000/CoderEval by `model_key` instead of raw timestamp; directory scan in `read_data` is skipped when `--since` is set; `--merge` without `--runs` sets `all_runs=True` instead of `merge_runs=2`; IFEval metrics (`prompt_level_strict_acc,none` etc.) added to METRICS list.
21. **`fmt_registry.py` removed (24.07.):** The function `format_blank_lines()` now only exists in `registry_tool._format_blank_lines()`. The import in `src/assemble_blueprint.py` was corrected accordingly.
22. **top_k:0 API error (24.07.):** LM Studio API does not accept `top_k: 0` (HTTP 400). `_generate_answer_native()` filters `top_k` when ≤ 0. The override `gpt-oss: {top_k: 0}` was kept, but the API call no longer sends `top_k`.
23. **Native API stop tokens (24.07.):** `_generate_answer_native()` now sends the `stop` parameter (previously only `_generate_answer_with_reasoning()`). Retry chain on API errors: first without `stop` (in case LM Studio does not support it), then with `reasoning="off"`.

---

## 19. Important Benchmark Results (Status 30.06.2026)

### Granite 4.0 H Tiny (SampleSize=10, Experts=16, Q8_0, 7.4 GB VRAM)

| Benchmark | Score |
|-----------|-------|
| DS1000 | 10% (1/10, 9x Harness-Fail) |
| CoderEval | 55% |
| HumanEval+ | 100% |
| MBPP+ | 50% |
| ARC-Challenge | 40% |
| HellaSwag | 70% |
| TruthfulQA | 30% |
| MMLU-Pro | 64.3% |
| MathQA | 40% |
| Agentic | 85% |
| **Coding** | **53.8%** |
| **Knowledge** | **51.1%** |
| **Math** | **40.0%** |
| **Overall** | **57.7%** |
| **Efficiency** | **60.5 %p/h (TOP 1!)** |
| tok/s | 12.7 (TOP 2) |
| Runtime | 0.6h (36 min) |

### Nerdsking Python Coder 7B (SampleSize=10, Q8_0, 8.1 GB VRAM)

| Benchmark | Score |
|-----------|-------|
| DS1000 | 20% |
| CoderEval | 60% |
| HumanEval+ | 100% |
| MBPP+ | 57.1% |
| ARC-Challenge | 10% |
| HellaSwag | 70% |
| TruthfulQA | 50% |
| MMLU-Pro | 38.5% |
| MathQA | 20% |
| Agentic | 20% |
| **Coding** | **59.3%** |
| **Knowledge** | **42.2%** |
| **Math** | **20.0%** |
| **Overall** | **37.3%** |
| **Efficiency** | **28.9 %p/h (TOP 2)** |
| tok/s | 19.9 (TOP 1) |
| Runtime | 0.8h (48 min) |

### Qwen3 Coder REAP 25B (SampleSize=5, IQ4_XS, 16K Context – limited due to VRAM)

| Benchmark | Score |
|-----------|-------|
| CoderEval | 60% |
| HumanEval+ | 95% |
| MBPP+ | 71% |
| HellaSwag | 80% |
| Agentic | 80% |
| **Efficiency** | **17.1 %p/h** |
| tok/s | 3.3 |
| Runtime | 2.5h |

### Qwen3.6 27B (SampleSize=5, Q3_K_S, 262K Context)

**Note:** `enable_thinking=False` (API parameter) necessary, since thinking tokens consume the token budget (2048) and lead to 0% custom benchmarks. LM Studio GUI option "Parsing of reasoning sections" is incompatible.

| Benchmark | Score |
|-----------|-------|
| MMLU-Pro | 80% |
| Agentic | 90% |
| Custom Benchmarks | 0% (if enable_thinking not disabled) |

---

## 20. Version Changelog

> **Moved (06.08.):** The complete changelog (entries from 14.06.2026,
> incl. history) now lives centrally in **CHANGELOG.md** in the project root – including
> the new review-gate entries from 06.08. (ruff cleanup, validate --verbose/--repro,
> pre_review_checks.ps1 v2, pre-push hook, CI fix). This section now only serves
> as a reference.

---

*Created: 28.06.2026 | Updated: 06.08.2026*
*Based on: v13.0.5 – Pipeline-Validierung, Hybrid-Klassifikation (GGUF+Architektur-Map), vereinfachter Workflow*
*24.07.: registry_tool.py validate (7 Checks), _word_boundary_match(), Pre-Run-Checks in run_benchmarks.py*
*24.07.: _ARCH_REASONING_MAP, classify_reasoning() Priority-Chain, _detect_reasoning_from_template() Regex*
*24.07.: cmd_sync() includes classify→assemble→validate, one command for everything*
*29.07.: Refactoring sprint (terminal colors, GenerationConfig, run_task helper, main() split, type hints 100%)*
*29.07.: 4 new chat templates (Gemma-4 QAT, Phi-4 Unsloth, GPT-OSS Unsloth)*
*29.07.: Benchmark run 3 models × 4 pipelines × sample size 5 + server log analysis*
*30.07.: v13.0.6 (src/ migration, CLI menu, quants normalization) + v13.0.7 (coding text blocks, template injection, name normalization)*
*31.07.: Registry-driven enable_thinking, streaming-thinking fixes, registry_tool rm, single-instance lock, A/B slots, gpt-oss→thinking, Qwen3-Instruct fix, registry cleanup*
*01.08.: STOP_TOKENS_CODING fix (\n```\n) – DeepSeek DS1000 35%/CoderEval 67%; consolidate_results sample size + table formatting; IFEval GGUF-EOS fallback*
*02.08.: v13.0.10 – P1 structure gate (classify_output/CSV columns), P4 agentic safety (--agentic-mode safety), P3 YAML run spec (--run-spec, SUPPRESS probe parser), gpt-oss reasoning logic centralized (GPTOSS_*), Bonsai overrides, registry sync +53*
*06.08.: Sampling design v2 – MODEL_CATEGORY_SAMPLING (table > defaults, JSON temp now GUI-only); REASONING_PATTERNS extended; Bonsai models removed (registry, table, docs); registry_tool.py: +pipeline (replaces sync_model_configs.ps1), +sync-templates (replaces tools/add_missing_prompt_templates.py), +patch-reasoning-effort (ported from tools/); 9 one-off/blind-flight scripts deleted from src/tools/*
*13.08.: **num_parallel aus der Registry entfernt** – feste Policy statt Registry-Feld: `_resolve_num_parallel(SS)` = 4 bei SS≥10, sonst 1 (run_benchmarks.py). CLI `--num-parallel` entfernt (Launcher + custom_benchmark.py Subprozess). `registry_tool.py`: fix-np deprecated (Stub), `_compute_np_ukv`→`_compute_ukv` (nur UKV/ctx), `_NP_POLICY=4` für ctx-Formel; `num_parallel` aus model_registry.yaml (49 Zeilen), field_owner.py, type_defs.py (RegistryEntry) entfernt; Tests angepasst. Vom Speicher/Kontext/KV-Quant hängt nur noch UKV ab, nicht np.*
*13.08.: **Top-Candidates-Tabelle neu + PROVISIONAL aufgelöst** – Konsolidierung `--no-installed --all-runs --sample-size 30` → 64 Modelle mit voller Pipeline (`konsolidiert_20260813_224036.md`). Qwen3-Modelle (Nachlauf 11.–12.08.) führen (Coder 30B 78%, 30B 2507 77%). Wichtiger Hinweis: `latest-run`-Modus verwarf DS1000-Paare (Timestamps DS/CE leicht versetzt) → für die Tabelle zwingend `--all-runs`/`--merge`. Pass-2-Läufe (13.08., SS=10) dienten als Funktionscheck; HumanEval+/MBPP+/Agentic-Lücken dort = pre-existing Harness-Fehler.*
*14.08.: **3 bekannte Benchmark-Fehler behoben** – (1) `run_benchmarks.py` EvalPlus: evalplus 0.3.1 `make_model()` (openai-Backend) forwardet `max_new_tokens` nicht → Kwarg entfernt, `model_obj.max_new_tokens` nach Erzeugung gesetzt (HumanEval+/MBPP+). (2) `custom_benchmark.py` `_resolve_models`: tolerantes Key-Matching (Basis ohne `@quant`) statt exaktem Vergleich → REAP-Registry-Key `@mixed` matcht den LMS modelKey (vorher `Model not found` + exit → „Benchmark complete" in 3s). (3) `custom_benchmark.py` `_model_supports_reasoning`: Basis-Keys ohne `@quant` im Cache abgebildet → REAP-`@mixed`-Einträge. Zusätzlich `tool_eval_bench` 2.0.7 in Python 3.12 nachinstalliert (war nur unter 3.14; Launcher-Subprozess nutzt 3.12) → Agentic ModuleNotFoundError behoben. Commit `db52ecef`; Verifikationslauf `run.verify-fixes.yaml` (Gemma4-REAP, SS=10) 14.08.*
*14.08.: **EvalPlus Windows-SIGALRM-Fix (`_WindowsSignalShim`)** – evalplus `make_auto_request` (`gen/util/openai_request.py`) nutzt `signal.alarm`/`SIGALRM` für Request-Timeouts. Auf Windows existiert `signal.alarm` NICHT → `AttributeError`, das evalplus' `except Exception` **endlos retried** (Endlosschleife) → HumanEval+/MBPP+ liefen auf Windows nie durch (echte Ursache; erst nach dem `max_new_tokens`-Fix sichtbar, da der Kwarg-Fehler davor beim Model-Import stoppte). Fix in `run_evalplus`: `_WindowsSignalShim` (No-op `signal()`/`alarm()`) ersetzt das Modul-`signal` in `openai_request` auf Windows – analog zum MATH-500-Fix (15.07.), nur für den evalplus-Codepfad. + 2 Regressionstests `TestWindowsSignalShim`. Commit `74a277e2`; **AGENTS.md angelegt** (Windows-11-Kontext + bekannte SIGALRM-Fallen + Pflicht zu Windows-Kompatibilitätstests).*
