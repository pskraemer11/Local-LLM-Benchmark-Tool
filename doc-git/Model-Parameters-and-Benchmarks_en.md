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

**Source:** `ergebnisse/konsolidiert_20260813_224036.md` (consolidate_results.py, `--no-installed --all-runs --sample-size 30`)
**Period:** runs since 07.08.2026 incl. Qwen re-run (11.–12.08.) and Pass-2 (13.08.); SampleSize=30 (DS1000/CoderEval CSVs only), 64 models with full pipeline.
**Scoring:** Overall = Coding 35% | Math 25% | Agentic & Instruction 25% | Knowledge 15%.

> ✅ **Final (13.08.):** Qwen re-run and Pass-2 completed — the PROVISIONAL
> flag is resolved. The Qwen3 models (re-run 11.–12.08. with current settings)
> now top the table: `Qwen3 Coder 30B A3B Instruct@q3_k_s` (78%) and
> `Qwen3 30B A3B Instruct 2507@q3_k_s` (77%). The table below shows the top 35
> of 64 models with full pipeline.

Only models with full pipeline run (DS1000 + CoderEval + EvalPlus + LMEval + MathQA + Agentic).

|Rank| Model (best quant.)                         | MoE | VRAM    | Overall | Effiz.   | Coding | Knowl. | Math  | Agentic | Strength                                                        |
|----|---------------------------------------------|-----|---------|---------|----------|--------|--------|-------|---------|-----------------------------------------------------------------|
|  1 | Qwen3 Coder 30B A3B Instruct@q3_k_s   | yes |  13.3 | *78%* | 10.3 %p/h | 70% | 73% | *80%* | 80% | NEW overall winner; top Coding/Knowledge/Math; fast (4.5 min) |
|  2 | Qwen3 30B A3B Instruct 2507 128x1.8B@q3_k_s | yes |  13.3 | *77%* | 11.8 %p/h | 68% | 78% | *80%* | 70% | Top-2; strongest Knowledge (78%); IFEval/HEval+ winners |
|  3 | Gemma 4 19B A4B Instruct REAP@q4_k_s  | yes |  12.3 | 70% | *50.2 %p/h* | 63% | 72% | *80%* | 63% | Efficiency winner (50.2 %p/h); best runtime (0.8 min) |
|  4 | Qwen3 Coder REAP 25B A3B I1@q3_k_m    | yes |  12.0 | 70% | 10.5 %p/h | *76%* | 64% | 53% | 65% | Top Coding (76%); fast (4.0 min) |
|  5 | Qwen3 30B A3B 2507 q2ks Mixed AR@q2_k_s | yes |  10.7 | 70% | 5.9 %p/h | 64% | 67% | 60% | *100%* | Raw Agentic winner (100%); 131K ctx |
|  6 | Granite 4.1 8B@q8_0                   | no |   7.2 | 70% | 11.8 %p/h | 68% | 64% | 60% | 83% | Best compact (7.2 GB); strong Coding+Agentic |
|  7 | Granite 4.1 8B@q6_k                   | no |   7.2 | 70% | 1.4 %p/h | 68% | 64% | 60% | 83% | Twin of q8_0; very slow runtime (30.8 min) |
|  8 | Qwen3 Coder REAP 25B A3B@q3_k_m       | yes |  12.0 | 69% | 10.0 %p/h | 72% | 54% | 69% | *90%* | Top-3 Coding; raw Agentic 90% |
|  9 | Granite 4.1 30B@q3_k_s                | no |  12.6 | 69% | 3.6 %p/h | 69% | 64% | 60% | 77% | Balanced; slower than 8B |
| 10 | Devstral Small 2 24B Instruct 2512@q3_k_s | no |  12.2 | 68% | 1.9 %p/h | 68% | 58% | 60% | *90%* | Strong Coding+Agentic; slow (20.9 min) |
| 11 | GPT-OSS 20B@q8_0                      | yes |  12.1 | 67% | 8.6 %p/h | 57% | 70% | 77% | 68% | Strong Math+Knowledge; fast (83.3 tok/s) |
| 12 | Gemma 4 26B A4B Instruct UD@iq3_s     | yes |  13.6 | 65% | 1.3 %p/h | 53% | [32%] | *80%* | 75% | High Math; Knowledge distorted [x] |
| 13 | Mellum2 12B A2.5B Instruct@q4_k_m     | yes |   8.1 | 65% | 6.4 %p/h | 59% | 60% | 70% | 73% | Compact MoE; good efficiency |
| 14 | Falcon3 10B Instruct@q8_0             | no |  11.0 | 65% | 1.2 %p/h | 62% | 63% | *80%* | 28% | Strong Math; weak Agentic; slow (31.7 min) |
| 15 | Qwen2.5 Coder 14B Instruct@q5_k_m     | no |  10.5 | 64% | 4.6 %p/h | *81%* | 64% | 60% | 22% | Top Coding (81%); weak Agentic |
| 16 | Magistral Small 2509@q3_k_m           | no |  11.5 | 64% | 0.6 %p/h | 58% | 49% | 67% | *92%* | Very strong raw Agentic (92%); very slow (67.9 min) |
| 17 | Qwen2.5 Coder 14B Instruct@q6_k       | no |  12.1 | 64% | 4.8 %p/h | *80%* | 64% | 60% | 22% | Top Coding (80%); weak Agentic |
| 18 | RNJ-1@q8_0                            | no |   8.8 | 64% | *29.2 %p/h* | 74% | 54% | 60% | 70% | High efficiency (29.2 %p/h); strong Coding+Math |
| 19 | Gemma 4 26B A4B Instruct I1@iq4_xs    | yes |  13.9 | 64% | 1.3 %p/h | 54% | [32%] | 70% | 83% | Fast (18.5 tok/s); Knowledge distorted [x] |
| 20 | Qwen2.5 Coder 14B Instruct@q5_0       | no |  10.3 | 64% | 5.0 %p/h | *79%* | 64% | 60% | 22% | Top Coding (79%); weak Agentic |
| 21 | Google Gemma 4 12B It Qat@q4_0        | no |     – | 63% | 0.9 %p/h | 52% | [31%] | 70% | 82% | Balanced; Knowledge distorted [x]; slow (41.7 min) |
| 22 | Qwen3 Coder 30B A3B q2ks Mixed AR@q2_k_s | yes |  10.7 | 62% | 7.8 %p/h | 43% | 64% | 60% | 80% | IFEval/Agentic strong; weaker Coding |
| 23 | Unsloth Gemma 4 12B It Qat@q4_0       | no |   6.9 | 62% | 13.6 %p/h | 58% | [21%] | 70% | 72% | Compact (6.9 GB); fast; Knowledge distorted [x] |
| 24 | Unsloth Gemma 4 12B It Qat@q4_k_xl    | no |   6.7 | 62% | 1.0 %p/h | 57% | [21%] | 70% | 72% | Compact (6.7 GB); slow runtime; Knowledge [x] |
| 25 | Bonsai 8B Requantized@q2_k            | no |     – | 61% | 8.6 %p/h | 53% | 59% | 60% | 74% | Solid all-round; balanced |
| 26 | LFM2 24B A2B MXFP4 MoE                | yes |  13.3 | 60% | *20.1 %p/h* | 56% | 58% | 53% | 68% | High efficiency; fast runtime (1.8 min) |
| 27 | ERNIE 4.5 21B A3B PT@iq4_nl           | yes |  12.5 | 60% | 8.1 %p/h | 66% | 68% | 53% | 37% | Good Coding+Knowledge; fast (4.4 min) |
| 28 | Google Gemma 4 26B A4B Instruct@q3_k_s | yes |  13.8 | 60% | 1.0 %p/h | 52% | [0%] | *83%* | 75% | Math winner (83%); Knowledge distorted [x] |
| 29 | Qwen3.6 27B MTP@iq3_xxs               | yes |  12.2 | 58% | 14.1 %p/h | 36% | [33%] | 60% | *100%* | Raw Agentic winner (100%); weak Coding |
| 30 | Unsloth Phi 4@q5_k_m                  | no |  10.4 | 57% | 3.2 %p/h | 68% | 31% | *80%* | 60% | Strong Coding+Math; weak IFEval |
| 31 | ERNIE 4.5 21B A3B PT MXFP4 MoE        | yes |  12.4 | 57% | 6.4 %p/h | 67% | 63% | 50% | 32% | MXFP4 sibling; weaker Math/Agentic |
| 32 | JanusCoder 14B@q6_k                   | no |  12.1 | 56% | 2.8 %p/h | 58% | 58% | 53% | 42% | Solid all-round coder |
| 33 | Ministral 3 14B Instruct 2512@q6_k    | no |  12.0 | 56% | 4.3 %p/h | 58% | 57% | 40% | 77% | Solid Coding + Agentic |
| 34 | Nerdsking Python Coder 7B I@q8_0      | no |   8.1 | 55% | 4.2 %p/h | 69% | 69% | 37% | 18% | Good Coding+Knowledge; weak Agentic |
| 35 | Qwen3.5 9B@q6_k                       | no |   8.3 | 55% | 4.0 %p/h | 32% | [32%] | 73% | 80% | Strong Math+Agentic; Knowledge distorted [x] |

[x] = HellaSwag/TruthfulQA ≈ 0 (known HS/TQA issue) → Knowledge score distorted.
Affects 8 models in this table: Gemma-4-26B variants (UD@iq3_s, I1@iq4_xs), Google Gemma 4 26B@q3_k_s, Google Gemma 4 12B Qat@q4_0, Unsloth Gemma 4 12B Qat (q4_0 + q4_k_xl), Qwen3.6 27B MTP@iq3_xxs, Qwen3.5 9B@q6_k.
HS/TQA re-run planned (in progress since 04.08.).

Agentic column = raw Agentic score (as in the source table); Overall blends Agentic 50% + IFEval 50% for the Agentic & Instruction category.

**Efficiency** = Overall / runtime (h) (runtime = DS1000 + CoderEval latency), values from consolidation.
Changes vs. 10.08. table: Qwen3 models now on top (Qwen re-run 11.–12.08.); Granite 4.1 8B@q8_0 (69.6%) overtakes the q6_k variant; Gemma 4 19B REAP@q4_k_s (70.4%) is the efficiency leader; GPT-OSS 20B@q8_0 (67.1%) jumps in ahead of the mxfp4 variant; RNJ-1@q8_0 (63.9%) and Qwen3.5 9B (55%) are new entries from Pass-2.
GLM-4.7-Flash REAP and Nemotron-3-Nano-REAP score near 0 in DS1000/CoderEval (GLM-REAP: HEval+/MBPP+ missing) — harness issue suspected; retest planned. HumanEval+/MBPP+/Agentic gaps for the Pass-2 models (13.08.) stem from pre-existing harness issues (EvalPlus `make_model` kwarg, missing `tool_eval_bench`); DS1000/CoderEval for those models use the 09.08./12.08. SS=30 runs.

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
