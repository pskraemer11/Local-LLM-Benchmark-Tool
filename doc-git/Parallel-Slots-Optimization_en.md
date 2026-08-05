# Parallel Slots Optimization (np) – LM Studio

## TL;DR / Recommendation (05.08.2026)

1. **np=4 is the standard for benchmarks** — from SampleSize=20 onward (already measurable at SS=5, see GLM-4.7-Flash). Applies to MoE **and** Dense models. The pipeline must actually send requests in parallel (ThreadPool), otherwise np is wasted (see "Pipeline fixes" below).
2. **VRAM is the limit, not architecture.** If the model does not fit into VRAM with 4 slots, apply, in this order:
   1. **`useUnifiedKvCache=True`** — unified KV cache scales with context, not with np (biggest lever),
   2. then **reduce `contextLength`** (ctx=32k is the documented minimum, works well),
   3. np reduction only if the above is still not enough.
3. **Fastest operation:** model weights + KV-cache fit **below ~15.5 GB VRAM** with no spill into shared system RAM. Any spill (shared RAM, PCIe paging) costs 5–10× performance.

---

## Measured Facts (all dates verified)

### A/B tests on real pipeline (DS1000 / CoderEval, `--num-parallel`)

| Date    | Model                  | Arch   | SS | np=1      | np=2      | np=4      | Speedup |
|---------|------------------------|--------|----|-----------|-----------|-----------|---------|
| 01.08.  | GPT-OSS-20b            | Dense  | 20 | 692.8s    | 666.3s    | 517.6s    | **1.34×** |
| 04.08.  | GLM-4.7-Flash          | MoE    |  5 | 164.7s    | –         | 89.2s     | **1.85×** |
| 04.08.  | Granite-4.0-h-tiny@Q8_0| MoE*   | 20 | 90s       | –         | 27s       | **3.33×** |
| 04.08.  | LFM2-24B-a2b_moe       | MoE    | 20 | 80s       | –         | 27s       | **2.96×** |
| 04.08.  | Mellum2-12B (Thinking) | MoE    | 20 | 1530s     | –         | 1301s     | **1.18×** |

*Granite-4.0-h-tiny: small MoE-like arch, behaves like Dense for VRAM purposes.

**Conclusions:**
- np=4 wins in every single measured case. Benefit is largest for small models (3.3×) and shrinks for Thinking models (~99% thinking tokens per request → 1.18×).
- Already at SS=5 (GLM) the speedup is measurable — **np=4 from SS=20 upward is a safe standard; even lower sample sizes benefit.**
- GPT-OSS (Dense, np=1 vs np=4): 1.34× — Dense models benefit too, just less than MoE.

### 05.08. test run (real pipeline, HumanEval+ SS=20, np=4)

| Model                  | Wall time | Note                                        |
|------------------------|-----------|---------------------------------------------|
| Rnj 1@Q8_0             | 146s      | fast – baseline                            |
| ERNIE-4.5-21B-A3B-PT MXFP4 MoE | 605s | MXFP4 slow path on this GPU (see case study) |
| ERNIE-4.5-21B-A3B-PT@IQ4_NL | 934s | **misconfigured** (ctx=131k, UKV=False) – fixed case study below |

The ERNIE result is the most important single data point: **configuration, not model size, caused a 6× slowdown.**

---

## Case Study: ERNIE-4.5-21B-A3B-PT@IQ4_NL (05.08.2026)

Old hypothesis (pre-05.08.): "ERNIE is slow at np=4 because of shared experts / heterogeneous CUDA kernels" — **REFUTED.** The real cause was a VRAM overflow:

| Setting                    | VRAM (GPU) | Shared system RAM | Speed       |
|----------------------------|-----------:|------------------:|-------------|
| ctx=131k, UKV=False (old)  | 15.5 GB    | 7.3 GB            | very slow (934s / 20 tasks) |
| ctx=32k, UKV=True (new)    | 13.3 GB    | 0 GB              | **5–10× faster** |

**Mechanism:** with UKV=False, each of the 4 slots gets its own KV cache (4 × ctx). ctx=131k × 4 slots exceeded the 16 GB GPU → KV spilled into shared system RAM → PCIe paging → massive slowdown. UKV=True shares one unified KV pool (scales with ctx, not np), ctx=32k keeps the total small → everything fits in VRAM → 5–10× faster.

**This confirms the priority order: UKV=True first, then ctx reduction.**

**MXFP4 note (05.08.):** ERNIE MXFP4 also ran slow (605s). This variant is a separate observation — likely MXFP4's slow-path/quantization handling on this GPU. Registry config for it should be checked separately; it is not a KV/ctx issue.

---

## Mechanism

### KV-Cache & Slots

LM Studio uses llama.cpp **slot-based KV cache**. With np=N, N slots are allocated.

**KV-cache VRAM per slot:**
```
context_length × layers × KV_heads × head_dim × (bytes_K + bytes_V) / 1024³   (GB)
```
**Total with separate caches = np × per-slot VRAM.**

`useUnifiedKvCache=True` changes this: one unified KV pool sized by context length, **independent of np** — this is why it is the #1 lever when VRAM is tight.

### Slot Selection

- **LCP similarity:** prefix of the previous prompt is reused (f_keep). Works with Dense models; MoE does not reuse.
- **LRU:** no prefix match → least recently used slot.

For benchmarks, prompts are diverse → LCP≈0 → cache reuse is irrelevant. The np=4 benefit for benchmarks comes purely from **GPU batch utilization** (server logs show 2–4 slots active simultaneously; GLM run: 10 windows with 2–3 active slots).

### np=1 vs np=4 summary

| Aspect           | np=1                          | np=4                              |
|------------------|-------------------------------|-----------------------------------|
| GPU utilization  | Low (1 token stream)          | High (2–4 parallel)              |
| LCP reuse (Dense, chat-like load) | Always (stable f_keep) | Random / reduced                 |
| KV-cache VRAM    | 1× base                       | up to 4× base (unless UKV=True)  |
| Benchmark speed  | baseline                      | **1.18–3.33× faster** (measured) |

## VRAM budget & context

- **Usable VRAM:** ~15.5 GB (16 GB minus reserve). Staying below this with weights + KV = fastest operation.
- **Minimum context:** 32k (documented; ERNIE case proves 32k + UKV=True is the sweet spot for 21B MoE).

Practical sizing for a 16 GB GPU:
1. np=4 + UKV=True if model fits (KV scales with ctx, not np)
2. If still too big: reduce ctx (32k target)
3. np=2 / np=1+UKV only as last resort

## Retired Hypotheses (kept for reference, NOT valid)

| Old claim | Status | Correct fact |
|-----------|--------|--------------|
| Dense → np=1 is optimal | **Retired 04.08.** | np=4 wins on benchmarks even for Dense (GPT-OSS 1.34×, Granite 3.33×) |
| "np=4 → 3 slots unused" | **Retired 04.08.** | server logs: 2–4 slots active |
| LCP=0 → np=4 useless | **Retired 04.08.** | batching effect dominates |
| ERNIE slow due to shared experts / CUDA kernels | **Retired 05.08.** | VRAM overflow (ctx=131k, UKV=False) – fixed via UKV=True + ctx=32k |
| "safe context = np=1 ctx / np" rule | **Retired 05.08.** | obsolete with UKV=True (KV no longer scales with np) |

## Pipeline fixes (05.08.2026) – np=4 only works if requests are sent in parallel

Even with np=4 configured, a sequential pipeline uses 1 slot. Proven via server log (05.08.: all 384 requests on slot 3):

1. **EvalPlus:** `run_evalplus()` called evalplus' `codegen()` which iterates tasks sequentially. Fixed: `num_parallel` passed through, codegen runs in `ThreadPoolExecutor(max_workers=num_parallel)`.
2. **lm_eval:** `lmeval_proxy.py` used synchronous `HTTPServer` (one request at a time), serializing lm_eval's `num_concurrent`. Fixed: `ThreadingHTTPServer`. Additionally, lm_eval's `num_concurrent` path requires a current `aiohttp` (the installed version was too old for Python 3.14 — crashed with `NameError: TCPConnector`).
3. **Custom (DS1000/CoderEval):** already parallel via ThreadPool — verified 04.08. (slots 0-3 active).

**Verification (05.08., HellaSwag 100 tasks, np=4, Rnj 1):** 149s, all slots active —
server log 19:38-19:41: slot 0=12, slot 1=12, slot 2=8, slot 3=6 print_timing events.

## Automatic Configuration (05.08.2026)

`_compute_np_ukv()` in `registry_tool.py` (priority-based, VRAM budget 15.3 GB):

| Prio | num_parallel | useUnifiedKvCache | Reason |
|------|--------------|-------------------|--------|
| 1    | 4            | False             | max parallelism, separate KV caches |
| 2    | 4            | True              | save VRAM (KV scales with ctx, not np) |
| 3    | 2            | True              | reduce KV overhead further |
| 4    | 1            | True              | minimum parallelism |
| 5    | 1            | False             | last resort |

Context length is **not** overwritten by the algorithm — manual GUI settings are authoritative. GGUF header is the source of truth for `max_context_length`.

### Runtime resolution (`_resolve_num_parallel()`)

| Prio | Condition | num_parallel |
|------|-----------|--------------|
| 1 | explicit `--num-parallel N` | N (user override) |
| 2 | SampleSize ≥ 20 | **4 for all models** |
| 3 | registry value | 4 (all models, MoE and Dense) |
| 4 | fallback | 1 |

CLI always wins: `--num-parallel 1` forces sequential, `--num-parallel 4` forces parallel even at SS=5.

## Reproducible Prompt Selection (parallel_ab)

```
python src/tools/parallel_ab.py --model <key> --benchmark ds1000 --sample-size 20 --slots 1,2,4 --seed 42
```

`build_prompts()` draws deterministically; `RANDOM_SEED=42` default, explicit `--seed` makes it reproducible.

## Appendix: PowerShell Logging Fix

`run_missing_benchmarks.ps1` showed no output because Python block-buffers piped stdout. Invoke with `-u`:

```powershell
& $Python -u run_benchmarks.py --sample-size 100 --seed 42 --model $ModelArg --benchmarks $BenchArg 2>&1 | Tee-Object -FilePath $LogFile -Append
```
