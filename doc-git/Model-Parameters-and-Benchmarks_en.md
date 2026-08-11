# Model Parameters & Benchmark Results

Hardware: AMD Ryzen 7 (8 cores) | NVIDIA RTX 5070 Ti (16 GB VRAM) | Windows 11

> **Single source of truth for model metadata:** `model_registry.yaml`
> (architecture, reasoning, capabilities, HF-URLs, quantization, KV-cache).
> This document covers **hardware constraints, benchmark results, and
> architectural details** that complement the registry.

## Legend

| Symbol         | Meaning                                                        |
|----------------|----------------------------------------------------------------|
| **Dense**      | All parameters active per token                                |
| **MoE**        | Mixture-of-Experts — only subset active; fits better in 16 GB  |
| **Reasoning**  | Explicit chain-of-thought before answer; needs more time/VRAM  |
| **Vision/OCR** | Image/document processing; excluded from benchmarks            |
| **Excluded**   | Excluded from benchmark selection (OCR/Vision/Embedding)       |
| **✅ OK**      | Suitable for local LLM benchmarks                             |
| **⚠️ OK**     | Conditionally suitable (e.g. only with specific quantization)  |

# Calculation of possible context length

The possible Context length depends on available VRAM (and CPU-RAM, but this is slow), model size, KV-Cache, KV quantisation, 
number of parallel slots in combination with Unified KV Cache =true/false and model architectural parameters. 

**theoretical KV-cache size formula (per slot!):**
`context_len × layers × KV_heads × head_dim × (bytes_per_K + bytes_per_V) / 1024²` (result in MB).
Here, cache quantisation factor (bytes_per_K + bytes_per_V) applies quantization of K- and V-cache (e.g. Q8/Q4 ≈ 1.5 bytes vs FP16 = 4 bytes).

But: correlation of formula with empirical proofed reality ist very weak! Better approax: rules of thumb, see downwards.

**Note:** `i1` in filenames = Importance Matrix quantization (not iMatrix-quant).

---

## Context Length Guidelines (16 GB VRAM, np=4)

> ⚠️ These are **approximate guidelines**. Actual limits depend on:
> - `np` (max concurrent predictions, or used number of parallel slots) in combination with UKV ("unified KV cache"): 
>          (only) if np=4 and UKV=false, reduce context length significant to 1/4 = 25% of table values
>   or enable `unifiedKVcache=true` (see `Parallel-Slots-Optimization_en.md`) to save memory
> - KV-cache quantization factor (Q8/Q4 or Q5_1/Q4_NL reduces VRAM significantly vs. FP16/FP16)
> - Model-specific VRAM (reserved GPU memory) overhead

| Model VRAM     | Approx. context length |
|----------------|-----------------------:|
| > 14 GB        |        16k             |
| 13–14 GB       |        32k             |
| 12–13 GB       |        49k             |
| 11–12 GB       |        64k             |
| 10–11 GB       |        98k             |
| 9–10 GB        |       131k             |
| < 9 GB         |       262k             |

**1st Rule of thumb**: use Model weights size less than (VRAM minus 2 GB) because of reserves for KV-cache + overhead.
**2nd Rule of thumb**: Model size >= 12 GB → `useUnifiedKvCache: true` (required for np=4).
                         Models < 12 GB → `useUnifiedKvCache: false` (if KV quantisation is supported).
**3rd Rule of thumb (exception)**: Some models CANNOT tolerate KV quantisation (architecture limitation).
                         These ALWAYS need `useUnifiedKvCache: true` regardless of size:
                         - **Gemma-4** (all variants: 26B, 19B, 12B)
                         - **Kimi-Linear** (REAP-35B-A3B)
                         - **GPT-OSS-20B**
                         Without UKV, these models leak into shared CPU RAM → 5-10x slower.
                         Implemented as `UKV_FORCE_TRUE_MODELS` in `src/benchmark_config.py` (return True unconditionally).
---

## Context Length Regression (log-log)

> **Goal:** Predict maximum usable context length from model metadata (VRAM, architecture).
> **New Use case:** `registry_tool.py configs` uses this formula to estimate np/UKV settings,
>        but does NOT overwrite context_length in JSON configs (manual GUI settings are authoritative).

### Method

**Formula:**
```
ctx = b0 × max_ctx^(b1) × vram_gb^(b2) × kv_gb^(b3)
```

Linear regression on logarithmic parameters:
- `log(ctx)` as dependent variable
- `log(max_ctx)`, `log(vram_gb)`, `log(kv_gb)` as predictors

(The original, theoretical formula for ctx consists of the multiplication and division of independent variables (parameters: num_layer, 
num_hidden, num_parallel slots, unifiedKvCache=true/false, K+V quantization). A direct linear regression using these variables is not effective. 
The linear regression is therefore performed on the logarithmic parameters, because on this scale the (logarithmic) terms behave 
additively or subtractively.) 

**Exclusion criterion:** Cases where `ctx = max_ctx` (native GGUF limit) are excluded, because here the architecture 
— not VRAM — is the limiting factor. 

### Results (05.08.2026)

| Metric/factor  | Value                            |
|----------------|----------------------------------|
| Data points    | 56 (excl. 5 where ctx = max_ctx) |
| R²             | **0.5227**                       |
| Intercept (b0) | 19.8329                          |
| max_ctx (b1)   | -0.0575                          |
| vram_gb (b2)   | -2.4782                          |
| kv_gb (b3)     |  0.3042                          |

**Formula:**
```
ctx = 410512948 × max_ctx^(-0.0575) × vram_gb^(-2.4782) × kv_gb^(0.3042)
```

### Interpretation

| Coefficient       | Meaning                                                 |
|-------------------|---------------------------------------------------------|
| `max_ctx^-0.0575` | Native ctx has minimal influence (exponent ≈ 0)         |
| `vram_gb^-2.4782` | More VRAM → significantly more ctx (negative = inverse) |
| `kv_gb^0.3042`    | Larger KV-cache → slightly more ctx (positive)          |

### Excluded Cases (ctx = max_ctx)

These models hit their native GGUF context limit, not VRAM:
- `mradermacher/deepseek-coder-33b-instruct`: ctx = max_ctx = 16384
- `qwen/qwen2.5-coder-14b-instruct@q5_k_m`: ctx = max_ctx = 131072
- `lmstudio-community/internlm2-math-plus-20b`: ctx = max_ctx = 8192

### Manual Corrections (05.08.2026)

**Some models** require manual overrides in `model_registry.yaml` (here are just a few examples):

| Model                             | np | UKV    | ctx   | Reason                                                    |
|-----------------------------------|----|--------|-------|-----------------------------------------------------------|
| Gemma-4-26B (all 3 variants)      |  4 | *True* | 32768 | no KV quantisation => too large without UKV               |
| DeepSeek-Coder-33B                |  4 |  True  | 16384 | before np=1 → after: np=4 with UKV                        |
| Codestral-22B                     |  4 |  True  | 32768 | UKV required for np=4                                     |
| DeepSeek-R1-Distill-14B           |  4 |  True  | 49152 | UKV required for np=4                                     |
| Qwen3.6-27B-MTP                   |  4 |  False | 32768 | ctx empirically reduced                                   |
| Qwen3.6-27B-I1                    |  4 |  False | 32768 | ctx empirically reduced                                   |
| Qwen3.6-27B (Q3_K_S)              |  4 |  True  | 32768 | 2GB larger than other local variants                      |
| GLM 4.7 Flash REAP 23B A3B@Q4_K_S |  4 | *True* | 32768 | UKV=False: VRAM excited, slow => UKV=True, VRAM fit, fast |

**General rules** see Rules of Thumbs above. 

---

## Benchmark Results: Top Candidates (16 GB VRAM)

**Source:** `ergebnisse/konsolidiert_20260810_073857.md` (consolidate_results.py)
**Period:** runs since 07.08.2026, SampleSize=30 (DS1000/CoderEval CSVs only), 31 models.
**Scoring:** Overall = Coding 35% | Math 25% | Agentic & Instruction 25% | Knowledge 15%.

> ⚠️ **PROVISIONAL (10.08.):** The Qwen models are missing from this run — the
> current consolidated table is **not final**. Only `Qwen Qwen3 14B@q6_k` (full
> pipeline, 09.08.) and `Qwen3 30B A3B Instruct 2507 128x1.8B@q2_k_s`
> (DS1000/CoderEval = 0, harness issue; EvalPlus/LM-Eval/Agentic from 04.08., old
> settings) are included. Missing: `qwen2.5-coder-14b` (q5_0/q5_k_m/q6_k — ran
> 09.08. with SS=30, but dropped by the installed-only filter of the 07:38
> consolidation; EvalPlus/LM-Eval only from 27.07.), `qwen3-30b-a3b-instruct-2507@Q3_K_S`,
> `qwen3-coder-30b-a3b`, `qwen3-coder-reap-25b(-i1)`, `qwen3.6-27b(-i1/-mtp)`,
> `qwen3.6-28b-reap-i1` — last runs 04.08. or older, different temperatures /
> partially without parallel slots. **Qwen re-run planned, then re-consolidate
> and update this table.** Ranks may change (old SS=100 table: Qwen3-Coder-30B
> 78%, Qwen3-Coder-REAP-25B 73% on top).

Only models with full pipeline run (DS1000 + CoderEval + EvalPlus + LMEval + MathQA + Agentic).

|Rank| Model (best quant.)                         | MoE | VRAM    | Overall | Effiz.   | Coding | Knowl. | Math  | Agentic | Strength                                                        |
|----|---------------------------------------------|-----|---------|---------|----------|--------|--------|-------|---------|-----------------------------------------------------------------|
|  1 | *Granite 4.1 8B@q6_k*                       | no  |  7.2 GB | *69%*   |  1.4 %p/h |  68%  |  64%   |  60%  |  83%    | Best overall (tied); best score/GB; strong Coding+Agentic       |
|  2 | Granite 4.1 30B@q3_k_s                      | no  | 12.6 GB | *69%*   |  3.6 %p/h | *69%* |  64%   |  60%  |  77%    | Best Coding (tied); ~3× faster runtime than 8B variant          |
|  3 | Devstral Small 2 24B Instruct 2512@q3_k_s   | no  | 12.2 GB |  67%    |  1.9 %p/h |  68%  |  58%   |  60%  | *90%*   | Top-3 overall; strong Coding + Agentic                          |
|  4 | Falcon3 10B Instruct@q8_0                   | no  | 11.0 GB |  65%    |  1.2 %p/h |  62%  |  63%   | *80%* |  28%    | Strong Math; weak Agentic; slow (31.7 min)                      |
|  5 | Mellum2 12B A2.5B Instruct@q4_k_m           | yes |  8.1 GB |  65%    |  6.4 %p/h |  59%  |  60%   |  70%  |  73%    | Strong Math+Agentic; compact, good efficiency                   |
|  6 | Gemma 4 26B A4B Instruct UD@iq3_s           | yes | 13.6 GB |  65%    |  1.3 %p/h |  53%  | [32%]  | *80%* |  75%    | High Math; Knowledge distorted [x]                              |
|  7 | Google Gemma 4 26B A4B Instruct@q3_k_s      | yes | 13.8 GB |  65%    |  1.1 %p/h |  52%  | [33%]  | *83%* |  75%    | Math winner (83%); Knowledge distorted [x]                      |
|  8 | Gemma 4 26B A4B Instruct I1@iq4_xs          | yes | 13.9 GB |  64%    |  1.3 %p/h |  54%  | [32%]  |  70%  |  83%    | Fast (18.5 tok/s); Knowledge distorted [x]                      |
|  9 | Mistralai Magistral Small 2509@q3_k_m       | no  | 11.5 GB |  64%    |  0.6 %p/h |  58%  |  49%   |  67%  | *92%*   | Very strong raw Agentic (92%); very slow (67.9 min)             |
| 10 | Google Gemma 4 12B It Qat@q4_0              | no  |    –    |  63%    |  0.9 %p/h |  52%  | [31%]  |  70%  |  82%    | Balanced; Knowledge distorted [x]; slow (41.7 min)               |
| 11 | Unsloth Phi 4@q5_k_m                        | no  |    –    |  61%    |  3.4 %p/h |  68%  |  32%   |  73%  |  60%    | Strong Coding + Math                                             |
| 12 | ERNIE 4.5 21B A3B PT@iq4_nl                 | yes | 12.5 GB |  60%    |  8.1 %p/h |  66%  |  68%   |  53%  |  37%    | New: good Coding+Knowledge, fast (4.4 min)                       |
| 13 | LFM2 24B A2B MXFP4 MoE                      | yes | 13.3 GB |  60%    | *20.1 %p/h* |  56% |  58%   |  53%  |  68%    | Efficiency winner; fastest runtime (1.8 min)                     |
| 14 | Qwen3 30B A3B Instruct 2507 128x1.8B@q2_k_s | yes | 10.7 GB |  58%    | 19.5 %p/h |  30%  |  64%   |  60%  | *100%*  | Raw Agentic winner (100%); weak Coding                          |
| 15 | ERNIE 4.5 21B A3B PT MXFP4 MoE              | yes | 12.4 GB |  57%    |  6.4 %p/h |  67%  |  63%   |  50%  |  32%    | MXFP4 sibling; weaker Math/Agentic than iq4_nl                   |
| 16 | JanusCoder 14B@q6_k                         | no  | 12.1 GB |  56%    |  2.8 %p/h |  58%  |  58%   |  53%  |  42%    | Solid all-round coder                                            |
| 17 | Ministral 3 14B Instruct 2512@q6_k          | no  | 12.0 GB |  56%    |  4.3 %p/h |  58%  |  57%   |  40%  |  77%    | Solid Coding + Agentic                                           |
| 18 | Nerdsking Python Coder 7B I@q8_0            | no  |  8.1 GB |  55%    |  4.2 %p/h | *69%* |  69%   |  37%  |  18%    | Top Coding (tied); weak Agentic                                  |
| 19 | Kimi Linear REAP 35B A3B Instruct I1@iq3_xxs | yes | 13.6 GB |  54%   | 14.2 %p/h |  57%  |  46%   |  67%  |  35%    | High efficiency; 1M context                                      |
| 20 | North Mini Code 1.0 UD@iq3_s                | yes | 12.8 GB |  54%    |  3.2 %p/h |  49%  |  66%   |  40%  |  83%    | Strong raw Agentic (83%); weak Coding                            |
| 21 | Qwen Qwen3 14B@q6_k                         | no  |    –    |  54%    |  1.0 %p/h |  40%  | [31%]  |  73%  |  53%    | Fast (16.1 tok/s); Knowledge distorted [x]                       |
| 22 | Gemma 4 19B A4B Instruct REAP I1@q4_k_m     | yes | 12.3 GB |  53%    |  9.5 %p/h |  45%  |  49%   |  60%  |  78%    | Efficient (9.5 %p/h); mid scores                                 |
| 23 | Internlm2 5 20B Chat@q4_k_m                 | no  | 12.0 GB |  52%    | 13.1 %p/h |  54%  |  68%   |  37%  |  30%    | Good Knowledge; very fast runtime (2.4 min)                      |
| 24 | Openai Gpt Oss 20B@mxfp4                    | yes |    –    |  49%    |  4.2 %p/h |  23%  | [31%]  |  77%  |  55%    | Fastest (21.9 tok/s); weak Coding; Knowledge distorted [x]       |
| 25 | Granite 4.0 H Tiny@q8_0                     | yes |  7.4 GB |  48%    | 13.2 %p/h |  46%  |  40%   |  37%  |  63%    | Compact (7.4 GB); high efficiency; weak Math                     |
| 26 | Mellum2 12B A2.5B Thinking MXFP4 MoE        | yes |  7.0 GB |  45%    |  0.3 %p/h |  27%  | [23%]  |  60%  |  65%    | Reasoning variant; very slow (96.6 min); Knowledge [x]           |
| 27 | Nemotron Cascade 14B Thinking@mxfp4         | no  | 10.4 GB |  40%    |  0.1 %p/h |  15%  | [22%]  |  60%  |  53%    | Slowest run (207 min!); weak Coding; Knowledge [x]               |
| 28 | Nemotron 3 Nano REAP 21B A3B@mxfp4          | yes | 12.1 GB |  36%    |  1.1 %p/h |  18%  | [17%]  |  47%  |  53%    | REAP; weak Coding; Knowledge [x]                                 |
| 29 | Internlm2 Math Plus 20B@q4_k_m              | no  | 12.0 GB |  35%    |  2.6 %p/h |  36%  |  20%   |  40%  |  38%    | Math-specialist; weak all-round; IFEval missing                  |
| 30 | GLM 4.7 Flash@q3_k_s                        | yes | 13.3 GB |  32%    |  1.0 %p/h |  11%  | [18%]  |  27%  |  68%    | Weak Coding; Knowledge [x]                                       |
| 31 | GLM 4.7 Flash REAP 23B A3B@q4_k_s           | yes | 13.3 GB |  13%    |  0.3 %p/h |   4%  | [14%]  |   0%  |  57%    | Worst overall; DS1000=0, HEval+/MBPP+ missing                    |

[x] = HellaSwag/TruthfulQA ≈ 0 (known HS/TQA issue) → Knowledge score distorted.
Affects 11 models: GLM-4.7-Flash (+REAP), Gemma-4-26B variants (I1/UD/Google-26B), Google Gemma 4 12B Qat, Mellum2-12B Thinking, Qwen3-14B, Gpt-Oss-20B, Nemotron-3-Nano-REAP, Nemotron-Cascade-14B-Thinking.
HS/TQA re-run planned (in progress since 04.08.).

Agentic column = raw Agentic score (as in the source table); Overall blends Agentic 50% + IFEval 50% for the Agentic & Instruction category.

**Efficiency** = Overall / runtime (h) (runtime = DS1000 + CoderEval latency), values from consolidation.
New models in this run (not in the 03.08. consolidation): ERNIE 4.5 21B A3B PT (iq4_nl + MXFP4), GLM 4.7 Flash (+REAP 23B), Nemotron 3 Nano REAP, Nemotron Cascade 14B Thinking, Qwen3-14B, Ministral-3-14B, JanusCoder, Nerdsking Python Coder, North Mini Code, Devstral Small 2, Falcon3, Magistral Small, Internlm2.5, Internlm2 Math+, Mellum2 Thinking, Kimi Linear REAP, LFM2, Phi 4.
GLM-4.7-Flash REAP and Nemotron-3-Nano-REAP score near 0 in DS1000/CoderEval (GLM-REAP: HEval+/MBPP+ missing) — harness issue suspected; retest planned.

---

## MoE Architecture Details

> ⚠️ MoE models should run with **np=4** (Max Concurrent Predictions in LMS).
> See `Parallel-Slots-Optimization_en.md` for measurements.
> **New (04.08.):** Parallel slots benchmark for Granite-4.0-h-tiny, Mellum2-12B, and
> LFM2-24B shows **2.9–3.3× speedup** for standard MoE models with np=4.
> Thinking models (e.g. Mellum2) show only ~1.2× speedup due to high token volume.

| Model                                | Total | Active | Ratio  | Experts                     | Top-k (active)          | Shared | Notes                                                                      |
|--------------------------------------|-------|--------|--------|-----------------------------|-------------------------|--------|----------------------------------------------------------------------------|
| DeepSeek-Coder-v2-Lite-Instruct      | 16B   | 2.4B   | 6.7:1  | 8                           | 2                       | No     | DeepSeekMoE; 27 layers; 65K ctx; **no KV-quantization!**                   |
| Granite-4.0-h-tiny                   | 7B    | 1B     | 7:1    | 64                          | 6 (4 routed + 2 shared) | 2      | Hybrid Mamba2+Attention (9:1); 4 of 40 layers with KV-cache                |
| LFM2.5-8b-a1b                        | 8.3B  | 1.5B   | 5.5:1  | 32                          | 4                       | No     | Hybrid Conv+GQA (3:1); Reasoning model; 6 Attention blocks                 |
| LFM2-24b-a2b-REAP-i1                 | 24B   | 2.3B   | 10.4:1 | 32 (pruned from 64)         | 4                       | No     | Hybrid Conv+GQA (3:1); 40 layers (10 Attention); REAP-compressed           |
| Ernie-4.5-21b-A3B-pt (MoE)           | 21B   | 3B     | 7:1    | 64 (Text) + 64 (Vision)     | 2×(6 + 1 shared) = 14   | 2      | Multimodal Heterogeneous MoE; 28 layers; Text+Vision experts separate      |
| Qwen3.6-28B-REAP (i1)                | 28B   | ~3B    | 9.3:1  | 205 (REAP-pruned from 256)  | 8 (+1 shared) = 9       | 1      | Hybrid Gated DeltaNet + Attention; 40 layers; original 256 experts/layer   |
| Qwen3-30B-A3B-Instruct               | 30.5B | 3.3B   | 9.2:1  | 128                         | 8                       | No     | Qwen3-MoE; 48 layers; general use; 262K context                            |
| Qwen3-Coder-30B-A3B-Instruct         | 30.5B | 3.3B   | 9.2:1  | 128                         | 8                       | No     | Qwen3-MoE; 48 layers; Python-specialized; 262K context                     |
| Qwen3-Coder-REAP-25B-A3B (i1)        | 25B   | ~3B    | 8.3:1  | 103 (REAP-pruned from 128)  | 8                       | No     | Qwen3 architecture; 48 layers; 262K context; REAP-pruned from 30B          |
| Gemma-4-19B-A4B-it-REAP-i1           | 19B   | ~4B    | 4.75:1 | 90 (REAP-pruned from 128)   | 8 (+1 shared) = 9       | 1      | Hybrid Sliding/Full Attention; 30 layers; originally 128 experts/layer     |
| Gemma-4-26B-A4B                      | 26B   | ~4B    | 4.75:1 | 128                         | 8 (+1 shared) = 9       | 1      | Hybrid Sliding/Full Attention; 30 layers                                   |
| GLM-4.7-Flash                        | 30B   | 3B     | 10:1   | 64                          | 4 (+ 1 shared) = 5      | 1      | Glm4MoeLite; 47 layers (1 dense + 46 MoE); KV-quant sensitive (K min Q8_0) |
| GLM-4.7-Flash-REAP-23B-A3B           | 23B   | 3B     | 7.7:1  | 48 (REAP-pruned)            | 4 (+ 1 shared) = 5      | 1      | Glm4MoeLite; REAP-compressed (30B→23B); KV-quant sensitive (K min Q8_0)    |
| GPT-OSS-20B                          | 20.9B | 3.6B   | 5.8:1  | 32                          | 4                       | No     | MXFP4-quant MoE weights; 24 layers; Alternating Dense+Banded Sparse Attn   |
|                                      |       |        |        |                             |                         |        | **No KV-quantization!** (won't load otherwise)                             |
| Kimi-Linear-REAP-35B-A3B-Instruct-i1 | 35B   | ~3B    | 11.7:1 | 180 (REAP-pruned)           | 8 (+1 shared) = 9       | 1      | Hybrid KDA+MLAS+SSM; 27 layers (26 MoE); 1M context; **no KV-quant!**      |
| Mellum2-12B-a2.5B-Instruct           | 12B   | 2.5B   | 4.8:1  | 64                          | 8                       | No     | 2 variants: Instruct SFT / Thinking SFT                                    |
| North-mini-code-1.0                  | 30B   | 3B     | 10:1   | 128                         | 8                       | No     | Cohere2MoE; 256K context; **no KV-cache quantization possible**            |
| MiroThinker-v1.5-30B                 | 30B   | –      | –      | –                           | –                       | –      | MoE reasoning model; 48 layers; 24K context (auto-configured)              |

---

## Reasoning Models

> Since 21.07.2026, reasoning detection is **registry-based** (`model_registry.yaml:reasoning` field).
> The list below is for reference — the registry is the authoritative source.
> See `thinking-config_en.md` for the full mechanism (classification, enable_thinking, API control).

Models with `reasoning: thinking` in the registry are automatically detected as reasoning models
at runtime (`_is_reasoning_model()` in `run_benchmarks.py`). Timeout is doubled for reasoning models.

Key reasoning families in the current setup:
- **Qwen3.6** (all variants): thinking (dual-mode, default thinking)
- **Gemma-4** (all variants): thinking (hard-wired `<|channel>thought` in template)
- **GPT-OSS-20B**: thinking (reasoning effort controllable via `GPTOSS_REASONING_EFFORT`)
- **Phi-4** (unsloth): thinking
- **RNJ-1**: thinking (THOUGHT:/RESPONSE: parsing format)
- **Magistral/Ministral/Nemotron-Cascade**: thinking
- **GLM-4.7** (all variants): thinking
- **MiroThinker-v1.5**: thinking
- **Bonsai-27B-MTP**: thinking

Models with `reasoning: instruct` are NOT treated as reasoning models:
- **Qwen3** (instruct variants, e.g. qwen3-30b-a3b-instruct)
- **Qwen2.5** (all variants)
- **DeepSeek-R1-Distill-Qwen-14B** (Qwen2.5 base, despite "r1" in name)
- **DeepSeek-Coder** (all variants)
- **Granite-4.x**, **ERNIE-4.5**, **Devstral**, **Codestral**, **Falcon3**, **LFM2**, **Mellum2-instruct**

For the full table see `model_registry.yaml` (field `reasoning: thinking|instruct`).

### Reasoning Parsing in LM Studio

**Disabled for all models** in the benchmark pipeline. The `reasoning.parsing` setting
 LM Studio default: `enabled=true`) with `<think>`/`</think>` tags forces chain-of-thought
generation even on non-reasoning models, adding 300–500 unnecessary tokens per generation.

Disable via: Chat Panel → "..." → Model Settings → Reasoning Parsing → Enabled off.

Thinking behavior is controlled exclusively via `enable_thinking` in the API call
(see `thinking-config_en.md`), not via the GUI setting.

---

## GPU Offloading

**Fixed (2026-07-07):** `model_manager.py:172` now passes `--gpu max` to `lms load`.
Without this flag, LM Studio loaded models to CPU only (despite `gpuOffloadLayers`
in config JSON — the KV-config stack did not forward this to llama.cpp).

All models now load with GPU acceleration. If a model doesn't fit in 16 GB VRAM,
`--gpu max` may fail — use `--gpu 0.8` or lower as fallback.

---

## References

| Topic                        | Document                                                    |
|------------------------------|-------------------------------------------------------------|
| Thinking/Reasoning config    | `thinking-config_en.md`                                     |
| Parallel slots (np)          | `Parallel-Slots-Optimization_en.md`                        |
| Model registry (metadata)    | `model_registry.yaml`                                       |
| Blueprint definitions        | `blueprint_definitions.yaml`                                |
| Architecture & flow          | `Architecture, Flow & ChangeLog_en.md`                      |
| How to add new models        | `HowTo-Install-and-Configure-New-LLM_en.md`                |
| A/B: GPT-OSS parallel slots | `A-B-Vergleich 1-2-4 Slots parallel_(GPT-OSS)_20260801_004539.md` |
| A/B: GLM-Flash thread pool  | `A-B-Vergleich Thread-Pool vs sequenziell_(GLM-4.7-Flash)_20260804_122724.md` |
| Benchmark datasets           | `Datasets-17-07-2026_en.md`                                |
| PandasEval vs CoderEval      | `PandasEval versus CoderEval - Evaluation Guidebook_en.md`  |
| MMLU-Plus subjects           | `MMLU-Plus-Subject-Classification_en.md`                    |
