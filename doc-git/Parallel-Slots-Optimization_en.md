# Parallel Slots Optimization (np) – LM Studio

## Problem

LM Studio sets `Max Concurrent Predictions` (np/parallel) to **4** by default.
For **sequential batch jobs** (e.g. benchmarks, one request after another), the optimal setting depends on the *LLM architecture* and the *type of requests*.

## Key Insight: Dense vs MoE

| Architecture                     | Optimal np | Reason                                                         |
|----------------------------------|------------|----------------------------------------------------------------|
| **Dense** (all parameters active)| **np=1**   | LCP cache reuse saves prompt tokens; GPU is already saturated  |
| **MoE** (only subset active)     | **np=4**   | LCP cache reuse not supported; batching fills GPU better        |

### Measurement Dense: Qwen2.5 Coder 14B, two quantization variants (08./09.07.2026)

| Feature                      | Q5_0 (np=4)    | Q6_K (np=1)                |
|------------------------------|----------------|----------------------------|
| Eval Speed                   | **~8–9.6 t/s** | **~12.8–13.4 t/s**         |
| `cache size limit reached`   | Yes (frequent) | None                       |
| LCP cache hits (f_keep)      | Varying by slot| **0.52–0.94**              |
| VRAM usage                   | Higher         | Lower (~3-4 GB less)       |

> **Note:** Q6_K is more compute-intensive than Q5_0 – the measured speed increase is **solely due to np=1**.

### Measurement MoE: google_gemma-4-26b-a4b-it Q3_K_S (04./09.07.2026)

| Feature         | np=4 (04.07.)           | np=1 (09.07.)                              |
|-----------------|-------------------------|--------------------------------------------|
| Eval Speed      | **~5.3 t/s**            | **~2.1 t/s**                               |
| Prompt Eval     | 21.8 t/s                | 98 t/s (LCP helps prompt, but not eval)    |
| KV-Cache Reuse  | Not supported (MoE)     | Not supported (MoE)                        |

np=4 is **2.5× faster** on MoE because batching 4 tokens utilizes the GPU better.
LCP cache reuse is irrelevant for MoE anyway.

### Measurement MoE: Granite / Mellum2 / LFM2 – np=1 vs np=4 (04.08.2026)

Three MoE models benchmarked with DS1000, SampleSize=20:

| Model                                  | Type       | np=1     | np=4     | Speedup | Score Δ       |
|----------------------------------------|------------|----------|----------|---------|---------------|
| Granite-4.0-h-tiny@Q8_0               | Dense-like | 90s      | 27s      | **3.33×** | 20% → 65%   |
| Mellum2-12B-a2.5B-thinking_moe@Q4_K_M | Thinking   | 1530s    | 1301s    | **1.18×** | 30% → 35%   |
| LFM2-24B-a2b_moe                      | Standard   | 80s      | 27s      | **2.96×** | 15% → 25%   |

**Key findings:**
- Granite and LFM2 show **2.9–3.3× speedup** with np=4 — significant throughput gain
- Mellum2 (Thinking model) shows only **1.18× speedup** — generates ~99% thinking tokens,
  so each request produces far more tokens, limiting parallel throughput
- All three models also show **score improvement** with np=4 — batching may improve
  inference quality through better GPU utilization
- Server logs confirm `n_slots=4` and all slots active simultaneously

## Mechanism

### KV-Cache & Slots

LM Studio uses llama.cpp with **Slot-based KV-Cache**. Each slot has its own KV-Cache region.
With np=N, N slots are allocated, even if only one is active at a time.

**KV-Cache VRAM (per slot):**
```
context_length × layers × KV_heads × head_dim × (bytes_K + bytes_V) / 1024³   (result in GB)
```

**Total VRAM for KV-Cache = np × VRAM per slot**

Example (24B Llama-Dense, ~64 layers, 8 KV-heads, head_dim=128, k_cache=q8_0=1B, v_cache=iq4_nl=0.5B):
- Per token: 64 × 8 × 128 × (1 + 0.5) = 98.304 bytes ≈ **96 KB**
- Per slot at 49K context: 49.000 × 96 KB ≈ **4.7 GB**
- **np=4 → 18.8 GB** KV-Cache (vs. np=1 → 4.7 GB)

### Slot Selection

On each request, the server selects a slot:
- **LCP-Similarity** (Longest Common Prefix): The prompt of the previous request is compared with the current one.
  On a match, the KV-Cache of the prefix is reused (`f_keep` = fraction served from cache).
  **Works only with Dense models** – MoE does not support cache reuse.
- **LRU** (Least Recently Used): If no matching prefix is found, the least recently used slot is chosen → cache lost.

### np=1 vs np=4 – Dense

| Aspect        | np=4                            | np=1                          |
|---------------|---------------------------------|-------------------------------|
| Slot count    | 4 slots                         | 1 slot                        |
| LCP hits      | Random (depends on LRU rotation)| **Always** (no alternative)   |
| f_keep        | Highly variable                 | 0.80–0.95 (stable)            |
| KV-Cache VRAM | 4× base                         | 1× base                       |

### np=1 vs np=4 – MoE

| Aspect         | np=4                         | np=1              |
|----------------|------------------------------|-------------------|
| GPU utilization| **High** (4 tokens parallel) | Low (1 token)     |
| Cache Reuse    | N/A (MoE)                    | N/A (MoE)         |
| Eval Speed     | **~2-3× higher**             | Lower             |

## Special Case: Benchmarks (lm_eval, EvalPlus) – LCP=0

### Problem

lm_eval benchmarks (ARC-Challenge, HellaSwag, TruthfulQA, MATH-500, IFEval) use **Few-Shot Prompts**:

```
Question: What is 2+2?
Answer: 4

Question: What is 3+5?
Answer: 8

Question: <current question>
Answer:
```

Each question has **different few-shot examples** (randomly drawn from the training set or rotated). The prompt therefore differs **from the very first character**.

**Consequence:**
- LCP between request N and request N+1 = **0** (no common prefix)
- **No slot match** possible
- For **every single question**, the LRU slot is evicted and the entire prompt is recomputed from scratch (prefill)
- All N slots are rotated through but never reused

**np=4 vs np=1 under benchmark load:**

| Aspect                | np=4                                   | np=1                     |
|-----------------------|----------------------------------------|--------------------------|
| LCP hits              | **0** (never)                          | **0** (never)            |
| Effective usage       | 1 slot active, 3 slots unused          | 1 slot active            |
| KV-Cache VRAM         | **4× base** (3× waste)                 | 1× base                  |
| Progressive slowdown  | **Yes** – VRAM pressure grows over time | No (minimal cache)       |
| Result                | Same speed as np=1, but higher VRAM consumption | Same speed, minimal VRAM |

### Progressive Slowdown

With np=4 and benchmarks, a significant **progressive slowdown** was observed:
- Model `bartowski/mistralai_magistral-small-2509` (24B Dense): Start **15 tok/s → End 5 tok/s**

**Cause:**
1. Initially: KV-Cache nearly empty, ~11.5 GB VRAM for compute buffers → 15 tok/s
2. With each question, the page-table-based KV-Cache grows across the 4 slots
3. Once free VRAM is exhausted, **paging over PCIe** to system RAM begins (36× slower than GPU RAM)
4. Simultaneously: Less VRAM for compute buffers → smaller batches → lower throughput
5. Result: **Drastic drop** in token rate over the course of a benchmark

**np=2 mitigates** the effect (halves KV-Cache), but does not eliminate it on long benchmarks.

## Recommendation

### General

1. **Dense models**: **np=1** – LCP cache reuse reduces prompt overhead (except for benchmarks, see below), GPU already saturated
2. **MoE models**: **np=4** – Batching utilizes GPU better, no cache reuse to lose
3. **Exception ERNIE** (`ernie4_5-moe`): **np=1** – Shared expert architecture + heterogeneous text/vision experts cause inefficient CUDA kernels at np=4
4. **Interactive chat / parallel users:** keep np=4 (default)

### For Benchmark Load (sequential, diverse prompts)

1. **Dense models**: **np=1** – no LCP benefit on benchmarks, but minimal KV-Cache VRAM
2. **MoE models**: **np=2–4**, depending on available VRAM – batching advantage remains, but watch VRAM limits
3. **SampleSize ≥ 20**: All models forced to **np=4** automatically (see Automatic Configuration above)

### Context Length vs np

KV-Cache VRAM scales linearly with np:
```
VRAM_KV = np × context_length × (cost per token)
```

Therefore, context length must be **reduced** at higher np. Rule of thumb:
```
safe_context_length = np=1_context_length / np
```

Example for a 16 GB VRAM GPU (approximate values, depends on model size and KV quantization):

| np  | Maximum Context Length (approximate) |
|-----|--------------------------------------|
| 1   | as per existing table (16k–262k)     |
| 2   | ~50 % of np=1 values                 |
| 4   | ~25 % of np=1 values                 |

## useUnifiedKvCache & num_parallel – Priority-Based Algorithm (05.08.2026)

As of 05.08.2026, `num_parallel` and `useUnifiedKvCache` are computed by `_compute_np_ukv()`
in `registry_tool.py` using a priority-based algorithm:

### Priority Order

| Priority | num_parallel | useUnifiedKvCache | Reason |
|----------|-------------|-------------------|--------|
| 1 | 4 | False | Max GPU parallelism, separate KV caches |
| 2 | 4 | True | Save VRAM (unified KV, np does not scale) |
| 3 | 2 | True | Reduce KV overhead further |
| 4 | 1 | True | Minimum parallelism |
| 5 | 1 | False | Last resort (reduce ctx) |

### VRAM Budget

- **Usable VRAM:** 15.3 GB (16 GB - 0.7 GB reserve)
- **Min context length:** 32768 tokens

### Architecture Data

- **Source:** GGUF header (read by `_read_gguf_arch()`)
- **Fields:** `n_layers` (block_count), `hidden_dim` (embedding_length), `max_context_length`
- **Fallback:** If no GGUF data, model size heuristic is used

### Key Changes from Previous Version

1. **All models (MoE AND Dense) get np=4** when possible — VRAM is the limit, not architecture
2. **Context length is NOT overwritten** in JSON configs — manual GUI settings are authoritative
3. **GGUF header is source of truth** for `max_context_length` (not registry fallbacks)
4. **Priority-based** instead of threshold-based (always tries np=4 first)

## Automatic Configuration

### Model loading (JSON configs)

The JSON configs in `user-concrete-model-default-config` are updated by `registry_tool.py configs`:
- **np and UKV** are computed from VRAM budget and architecture (priority-based algorithm)
- **Context length** is NOT modified — manual GUI settings are preserved

### Benchmark sending (`run_benchmarks.py`)

`num_parallel` is auto-resolved per model at runtime (`_resolve_num_parallel()`):

| Priority | Condition | num_parallel |
|----------|-----------|-------------|
| 1 | Explicit `--num-parallel N` | N (user override) |
| 2 | SampleSize ≥ 20 | **4 for all models** |
| 3 | Registry value | 4 (all models, MoE and Dense) |
| 4 | Fallback | 1 |

**Rationale for SS ≥ 20 override:** At larger sample sizes, the threading overhead
amortizes and batching provides measurable speedup (1.85× for GLM-4.7-Flash, see
A/B doc). At SS < 5, overhead dominates — use registry default.

**CLI override always wins:** `--num-parallel 1` on SS=100 forces sequential;
`--num-parallel 4` on SS=5 forces parallel for any model.

## Reproducible Prompt Selection (parallel_ab, since 02.08.)

`tools/parallel_ab.py` wacht anfangs an Handler: `build_prompts(sample_size, benchmark,
seed=None)` zieht die Prompts deterministisch. Ohne `seed` greift `RANDOM_SEED = 42`; ein
explizites `--seed` (CLI) macht die Prompt-Auswahl reproduzierbar gegenüber älteren Läufen.

```
python src/tools/parallel_ab.py --model <key> --benchmark ds1000 --sample-size 20 --slots 1,2,4 --seed 42
```

## Appendix: Fix for PowerShell Logging

The batch script `run_missing_benchmarks.ps1` showed barely any log output,
because Python uses block buffering (4K/8K) when stdout is piped.

**Fix:** Invoke Python with `-u` (unbuffered):

```powershell
& $Python -u run_benchmarks_v12.py `
    --sample-size 100 `
    --seed 42 `
    --model $ModelArg `
    --benchmarks $BenchArg `
    2>&1 | Tee-Object -FilePath $LogFile -Append
```

Alternatively: set `$env:PYTHONUNBUFFERED=1` before starting the script.
