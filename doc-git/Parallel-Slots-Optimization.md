# Parallel Slots Optimization (np) – LM Studio

## Problem

LM Studio sets `Max Concurrent Predictions` (np/parallel) to **4** by default.
For **sequential batch jobs** (e.g. benchmarks, one request after another), the optimal setting depends on the *LLM architecture* and the *type of requests*.

## Key Insight: Dense vs MoE

| Architecture                     | Optimal np | Reason                                                         |
|----------------------------------|------------|----------------------------------------------------------------|
| **Dense** (all parameters active)| **np=1**   | LCP cache reuse saves prompt tokens; GPU is already saturated  |
| **MoE** (only subset active)    | **np=4**   | LCP cache reuse not supported; batching fills GPU better        |

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

## useUnifiedKvCache – VRAM Formula

As of 17.07.2026, `useUnifiedKvCache` (JSON field `llm.load.useUnifiedKvCache`) is no longer set via a blanket `<9 GB` heuristic, but through an **architecture-aware VRAM estimate**:

```
model_gb     = file_size_bytes / 1_000_000_000
kv_bytes     = bytes_K(k_cache) + bytes_V(v_cache)    # Default: 1.0 + 0.5 = 1.5
kv_gb        = n_layers × hidden_dim × 2 × kv_bytes × context_length / 1e9
total_gb     = model_gb + kv_gb × num_parallel
```

| Condition                                   | useUnifiedKvCache | Reason                             |
|---------------------------------------------|:------------------:|------------------------------------|
| `total_gb < 14.5`                           | `false` (OFF)      | Enough VRAM for separate caches    |
| `total_gb ≥ 14.5`                           | `true` (ON)        | VRAM shortage, shared cache        |
| No architecture data + `model_gb ≥ 9.0`     | `true` (ON)        | Old heuristic (fallback)           |
| No architecture data + `model_gb < 9.0`     | `false` (OFF)      | Old heuristic (fallback)           |
| np = 1                                      | `false` (OFF)      | Only one slot, no shared cache needed |

**Source of architecture data:** `n_layers` and `hidden_dim` are automatically read from the GGUF header when adding new models (`registry_tool.py add`) using `block_count` and `embedding_length` respectively. The header reader takes ~1ms per file (unlike `GGUFReader` from the gguf package, which memory-maps the entire ~12GB file).

## Automatic Configuration

The JSON configs in `user-concrete-model-default-config` have been corrected by script:
MoE models have `numParallelSessions=4`, Dense models `=1`.

**Note:** The automatic configuration does not account for benchmark special cases.
Per model, `num_parallel` can be overridden in the registry (`model_registry.yaml`).

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
