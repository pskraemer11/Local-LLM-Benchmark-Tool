# Long-Term Planning & Open Items

Status: 2026-08-06. Legend: [ ] open, [~] in progress, [x] done/checked.

## Active Items

- [x] **1. Create Planung.md** — done 05.08., maintained continuously.
- [x] **2. Revise `Parallel-Slots-Optimization_en.md`** — done 05.08.: outdated Dense=np=1 table marked as historical, new rules (04.08.) incorporated, Recommendation section updated to priority algorithm.
- [x] **3. Fix CI failures on GitHub** — checked 05.08.: all 5 latest runs `success` (incl. `a73c15b2`); ruff with CI flags (`--select E,F`) green locally. No action needed.
- [x] **4. `fill-arch` should read `max_context_length` from GGUF** — already implemented: `cmd_fill_arch` in `src/registry_tool.py:1329-1438`, fills `max_context_length` from GGUF header when `None` (lines 1382-1396, via `_read_gguf_arch` 4-tuple `(block_count, embedding_length, is_reasoning, context_length)`). Done via fix from 05.08. 08:20.
- [x] **5. Fallback `max_context_length: None`** — no 8192 hardcode found anymore; `cmd_suggest`/`_compute_np_ukv` (`src/registry_tool.py:810-844`) use `entry.get("max_context_length") or 262144`, `MIN_CONTEXT_LENGTH = 32768` (`src/benchmark_config.py:563`). Fallback 256k is well above the required 16k lower bound.
- [x] **6. Update `thinking-config_en.md`** — done 05.08.: priority chain corrected to 05.08. state (LMS JSON config is the ONLY source, `MODEL_TEMP_OVERRIDES`/Knowledge-Floor removed), current-patterns table, `--thinking` table (keyword matching via REASONING_PATTERNS), configuration flow and history updated.
- [x] **7. Clarify native `max_token_length`** — registry values are correct and match the LMS GUI: `noctrex/lfm2-24b-a2b_moe` → max 128000 (**128k tokens**, not 128), `mradermacher/gemma-4-26b-a4b-it-i1` → max 262144 (**262k tokens**, not 262!). User's correction from 05.08. adopted.
- [x] **8. Real benchmarks run with 1 slot instead of 4** — **FIXED + VERIFIED (05.08.):** TWO pipeline bugs, not the load:
  1. **`run_evalplus()`** (run_benchmarks.py:1038): had no `num_parallel` parameter, evalplus `codegen()` submits strictly sequentially (ThreadPool max_workers=1). **Fix:** `num_parallel` passed through (call at line 1988) + own parallel codegen loop with `ThreadPoolExecutor(max_workers=num_parallel)`, identical JSONL format (sanitized+raw) per task under write lock.
  2. **`lmeval_proxy.py`**: used `HTTPServer` (synchronous, 1 request at a time) → lm_eval `num_concurrent>1` was serialized at the proxy. **Fix:** `ThreadingHTTPServer`.
  - **Test run verification (05.08., Rnj 1@Q8_0 + ERNIE-4.5-21B-A3B-PT, HumanEval+/HellaSwag/DS1000 SS=20 np=4):** evalplus ran with 4 parallel workers, DS1000-Custom still 4 workers. HellaSwag failed in the first run (lm_eval `NameError: TCPConnector` — aiohttp too old for Python 3.14, uses removed `cgi`).
  - **lm_eval TCPConnector fix (05.08.):** `pip install --upgrade aiohttp` → 3.14.3. **HellaSwag verification run successful:** 100 tasks in 149s, score 0.34 (Rnj 1). **Slot proof from server log 19:38-19:41: slots 0/1/2/3 active (12/12/8/6 events)** — before the fix: all 384 requests on slot 3. Thus ALL 3 pipeline types are parallelized and verified: evalplus (ThreadPool), lmeval (ThreadingHTTPServer + aiohttp), custom (was already ThreadPool).
  - **ERNIE case study (evidence for VRAM>np ranking):** ERNIE IQ4_NL ran 934s/20 tasks (ctx=131k + UKV=False → 15,5 GB VRAM + 7,3 GB shared RAM → PCIe paging). After GUI restart ctx=32k + UKV=True: 13,3 GB VRAM, 0 GB shared, **5-10× faster**. This **REFUTES** the old ERNIE-np=1 hypothesis (shared experts/CUDA kernels) — the cause was VRAM overflow, not architecture. MXFP4 variant separately slow (605s) — presumably MXFP4 slow path, not KV/ctx-related.
  - Verification: 717/717 tests green, py_compile OK. **Item 8 completed.**
- [x] **9. Quarantine folder** — 137 orphan configs in `~\.lmstudio\.internal\user-concrete-model-default-config\_quarantine_orphans_20260805\`; decision 05.08.: keep quarantine permanently as trash (no deletion). Completed by decision.

## 2026-08-06 – Registry Validation, README, Help Text

- [x] **10. Registry validation to 0 problems** — commits `0eca0867`, `d2cc53f7`, `1ec72067`: 48 registry `context_length` values cleared + sync-ctx, 8 configs raised to 32768, `gemma-4-12b-it-qat` UKV drift fixed, `unsloth/phi-4` + `mradermacher/deepseek-coder-33b-instruct` capped at native GGUF limit 16384, missing promptTemplate fields added. Validation logic in `src/registry_tool.py` corrected: only `cfg_ctx > max_ctx` and `cfg_ctx <= 0` remain — NO arithmetic minimums (8192/32768); user: "There is no such defined minimum!" Small max_ctx models (<16k) are only for Embedding/RAG/RIG/Math and belong on the blacklist.
- [x] **11. README.md updated** — commit `166b5cf7`, 7 points: (1) thinking support generally for all pipelines, (2) stratified subsampling broader (DS1000, CoderEval, others), (3) quickstart to `qwen3-30b-a3b-instruct --thinking` (Gemma-4 is always in thinking mode), (4) dev deps complete, (5) `--num-parallel` in CLI table, (6) registry tool section with real commands + principle (05.08.), (7) new section "Consolidate Results (src/consolidate_results.py)". The CLI table was cross-checked against the real `--help` output: `--bootstrap`, `--non-interactive`, `--output-dir` do **not** exist as flags (the quickstart call `consolidate_results.py --bootstrap` would have crashed), duplicate `--unload-between` line removed; bootstrap CIs run automatically, paired only via `--compare`.
- [x] **12. Thinking help text to "all pipelines"** — commit `7a8ac4d7`: 3 places in `src/run_benchmarks.py` (CLI help line 1756, comment line 753, summary print line 1838).
- [x] **13. Unjustified ResourceExhausted changes reverted** — `src/custom_benchmark.py` + `src/tools/lmeval_proxy.py` via `git checkout`; the 502/ResourceExhausted errors came from the NVIDIA provider (Nemotron 3 Ultra Free), not from the benchmark code.
- [x] **14. Cleaned up (Git dirtiness)** — 4 untracked `logs_3098*.zip` + `src/utils/modeling_gguf_pytorch_utils.py.lnk` deleted; `logs/` remains covered via `.gitignore`.
- [x] **15. Manual-corrections table + VRAM rule** — in `doc-git/Model-Parameters-and-Benchmarks_en.md` (05.08.): manual overrides (np/UKV/ctx) + general rule: ≥12 GB model size ⇒ UKV=true at np=4 (16 GB GPU). VRAM rule also in README.md (06.08., commit `888b22a0`).

## Open

- [ ] **16. Update top-candidates table** — after the running SS=30/np=4 run (since ~05.08., bugfixes: parallelization evalplus + lmeval, aiohttp 3.14.3): regenerate the table values in `doc-git/Model-Parameters-and-Benchmarks_en.md` from the new consolidation ODS (scores + efficiency change due to faster runtimes). Previously cleaned up (06.08.): outdated SS=4 note (12.07., not meaningful) removed, source reference `konsolidiert_15 Modelle, SampleSize 100, seit 20260711_20260803_172150.ods` verified — the table originates from the SS=100 run 11.07.–03.08. **Then commit** (incl. manual-corrections table 05.08. + SS=4 removal, currently uncommitted in `Model-Parameters-and-Benchmarks_en.md`).
- [ ] **17. Central alias map for model family names** — idea from reviewing transformers `modeling_gguf_pytorch_utils.py` (06.08.): a central table for name aliases (HF model_type ↔ GGUF arch ↔ registry arch, e.g. `gpt-oss-20b` → `gpt_oss`, `qwen2_moe` → `qwen2moe`, `minimax_m2` → `minimax-m2`) instead of scattered regexes (`-(ud|qat|imatrix)` suffixes, `@quant` strips, arch substring detection). Application sites: `normalize_model_name`/`_normalize_lms_model_name` + `_ARCH_REASONING_MAP` + `GGUF_TO_TRANSFORMERS_MAPPING` analogue. Purely structural improvement (robustness), no functional gain — deferrable.
- [x] **18. qwen3.5-9b: clarify reasoning classification vs. hub** — **COMPLETED (06.08.)** — registry `qwen/qwen3.5-9b` aligned to `reasoning: thinking` + `max_context_length: 262144` added (hub value); comment `assemble_blueprint.py:248-249` corrected (dual mode, default thinking — `enableThinking.defaultValue: true` per hub model.yaml/Qwen model card); enable_thinking handling checked: `get_model_config` forces `enable_thinking: True` in thinking runs (REASONING_PATTERNS contains qwen3.5/qwen3.6), `run_benchmarks` already had `_is_qwen3_6_model()`, `custom_benchmark._model_supports_reasoning()` now correctly reads `thinking` — no further code change needed. Verified: `validate --repro` = **0 hub deviations**, ruff 0, 741 tests green. Background remains documented:
  - **Applies to ALL Qwen 3.5/3.6 models** (user confirmation 06.08.): dual mode, thinking controllable via toggle, as stated on the Qwen model card.
  - **Registry is internally inconsistent**: all other Qwen3.5/3.6 entries (`Qwen/Qwen3.5-9B-GGUF@q6_k`, `unsloth/qwen3.6-27b`, `-mtp`, `mradermacher/qwen3.6-27b-i1`, `qwen3.6-28b-reap-i1@iq3_s/@q3_k_s`) have `reasoning: thinking` — only `qwen/qwen3.5-9b` has `instruct` (same file_size_bytes 8281142495 as the @q6_k variant).
  - `max_context_length` is missing from the entry (hub: 262144) — although `fill-arch` should have filled it in per planning item 4.
  - Code comment `assemble_blueprint.py:248-249` ("Qwen3.6 Default Non-Thinking, enable_thinking=False Default") contradicts the hub model.yaml (`defaultValue: true`).
  - Pipeline effect (`custom_benchmark.py:907-909`): with `is_thinking_enabled=False`, `enable_thinking: False` is explicitly sent → qwen3.5-9b benchmark results (if run) would be produced without thinking, although the model is thinking-capable.
  - All four subtasks (a)–(d) completed: (a) registry aligned to `thinking`, (b) `max_context_length: 262144` added, (c) comment corrected, (d) handling checked (no code change needed).

## Deliberately NOT included (decision 02.08., code review §5)

- P2 judge as second scoring instance.
- `temperatura`/`top_p` overrides in the run spec (stay at default).

## Final Registry Cleanup (05.08., committed `a73c15b2`)

- 3 orphan keys removed (no GGUF anymore): `intel/qwen3-8b-q4km-autoround-inc-v1`, `prism-ml/bonsai-27b`, `prism-ml/bonsai-27b@q1_0`.
- 9 entries: `context_length` capped to `max_context_length` (rnj-1, phi-4, falcon3-10b, mellum2 ×2, nerdsking-python-coder-7b, internlm2_5-20b, bonsai-8b, granite-4.1-8b).
- Registry: 70 entries, 0 inconsistencies, tests 717/717 green.
