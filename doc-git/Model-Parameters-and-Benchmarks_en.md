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

**Conservative KV-cache formula (per slot):**
`context_len × layers × KV_heads × head_dim × (bytes_per_K + bytes_per_V) / 1024²` (result in MB).
LM Studio shows lower values because it applies auto KV-quantization (Q8/Q4 ≈ 1.5 bytes
vs FP16 = 4 bytes), especially for VRAM-critical models.

**Note:** `i1` in filenames = Importance Matrix quantization (not iMatrix-quant).

---

## Context Length Guidelines (16 GB VRAM, np=1)

> ⚠️ These are **approximate guidelines**. Actual limits depend on:
> - `np` (max concurrent predictions): at np=4, reduce context to ~25% of table values
>   or enable `unifiedKVcache=true` (see `Parallel-Slots-Optimization_en.md`)
> - KV-cache quantization (Q8/Q4 reduces VRAM significantly)
> - Model-specific VRAM overhead

| Model VRAM     | Approx. context length |
|----------------|-----------------------:|
| > 14 GB        |        16k             |
| 13–14 GB       |        32k             |
| 12–13 GB       |        49k             |
| 11–12 GB       |        64k             |
| 10–11 GB       |        98k             |
| 9–10 GB        |       131k             |
| < 9 GB         |       262k             |

**1st Rule of thumb:** Model weights size should be less then VRAM (reserved GPU memory) minus 2 GB (reserve for KV-cache + overhead).
**2nd Rule of thumb:** Models greater 12GB need Unified KV Cache = true (activated) to use 4 parallel slots (normally faster)
**3rd Rule of thumb:** some models can't use KV quantisation (e.g. Gemma-4, Kimi Linear). They need Unified KV Cache = true and allow less context length to fit into VRAM. 
                        Otherwise their perfomance slow down dramatically (use of shared CPU memory).
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

**General rule for VRAM (GPU) = 16 GB** (minus 0.5–0.7 GB overhead): 
All models with a model size (weights) of 12 GB or larger require the unified KV cache (UKV=true) when using 4 parallel slots (np=4).
Otherwise they slow down dramatically.

---

## Benchmark Results: Top Candidates (16 GB VRAM)

**Source:** `ergebnisse/konsolidiert_SampleSize 100, seit 20260711_20260803_172150.ods`
**Period:** 11.07.–03.08.2026, SampleSize=100 (DS1000/CoderEval), 15 models.
**Scoring:** Overall = Coding 35% | Math 25% | Agentic 25% | Knowledge 15%.

Only models with full pipeline run (DS1000 + CoderEval + EvalPlus + LMEval + MathQA + Agentic).

|Rank| Model (best quant.)                    | MoE | VRAM    | Overall | Effiz.   | Coding | Knowl. | Math  | Agentic | Strength                                              |
|----|----------------------------------------|-----|---------|---------|----------|--------|--------|-------|---------|-------------------------------------------------------|
|  1 | *Qwen3 Coder 30B A3B Instruct@q3_k_s*  | yes | 13.3 GB | *78%*   | 10.3 %p/h | *80%* |  65%   | *80%* |  60%    | Best overall; top Coding + Math                       |
|  2 | *Qwen3 Coder REAP 25B A3B I1@q3_k_m*   | yes | 12.0 GB | *73%*   | 11.0 %p/h | *76%* |  58%   | *80%* |  65%    | REAP variant near-original quality, better efficiency |
|  3 | *Granite 4.1 8B@q6_k*                  | no  |  7.2 GB | *71%*   |  8.5 %p/h |  63%  |  68%   |  60%  | *90%*   | Best score/GB, strong Agentic, compact                |
|  4 | Granite 4.1 30B@q3_k_s                 | no  | 12.6 GB |  65%    |  3.4 %p/h |  52%  |  72%   |  60%  | *90%*   | Strong Agentic + Knowledge, solid all-round           |
|  5 | Gemma 4 26B A4B Instruct UD@iq3_s      | yes | 13.6 GB |  64%    | 20.4 %p/h |  67%  | [27%]  |  60%  | *90%*   | Very high efficiency, strong Coding ] Agentic         |
|  6 | Gemma 4 26B A4B Instruct I1@iq4_xs     | yes | 13.9 GB |  62%    | 20.8 %p/h | *71%* | [27%]  |  60%  | *90%*   | Highest efficiency among Gemma-4-26B variants         |
|  7 | Qwen3.6 27B I1@q3_k_s                  | no  | 12.1 GB |  59%    |  6.6 %p/h |  33%  | [33%]  | *91%* |  77%    | Math winner (91%), strong Agentic, weak Coding        |
|  8 | Google Gemma 4 26B A4B Instruct@q3_k_s | yes | 13.8 GB |  58%    |  4.6 %p/h |  52%  | [33%]  |  60%  |  80%    | Solid all-round, cheapest Gemma quant                 |
|  9 | Qwen3.6 27B MTP@iq3_xxs                | no  | 12.2 GB |  49%    | 24.0 %p/h |  28%  | [32%]  |  50%  | *88%*   | MTP draft variant; DS1000 missing (NaN)               |
| 10 | Granite 4.0 H Tiny@q8_0                | yes |  7.4 GB |  47%    | 21.9 %p/h |  61%  |  43%   |  20%  |  50%    | Compact (7.4 GB), high efficiency, weak Math          |
| 11 | DeepSeek R1 Distill Qwen 14B@q6_k      | no  | 12.1 GB |  46%    |  0.3 %p/h |  35%  | [27%]  |  60%  |  40%    | Reasoning model; very slow, weak Coding/Agentic       |
| 12 | Mistralai Codestral 22B V0.1@iq4_xs    | no  |    –    |  44%    |     –     |  40%  |  68%   |  40%  |  55%    | Coding scores invalid (DS1000/CoderEval=0%, aborted)  |
| 13 | Bonsai 27B@q1_0                        | no  |  4.7 GB |  43%    |  0.3 %p/h |  16%  | [27%]  |  60%  | *90%*   | Extremely compact, but very slow; weak Coding         |
| 14 | Openai Gpt Oss 20B@mxfp4               | yes |    –    |  39%    |  1.5 %p/h |  34%  |  72%   |  20%  |  55%    | MXFP4 quant; weak Coding/Math, VRAM not captured      |
| 15 | Deepseek Coder 33B Instruct@q3_k_s     | no  | 14.4 GB |  37%    |  2.0 %p/h |  62%  |  20%   |  20%  |  60%    | Older coder; very slow (2.3 tok/s), weak Math/Knowl.  |

[x] = HellaSwag/TruthfulQA = 0 (known HS/TQA issue) → Knowledge score distorted.
Affects 7 models: all Gemma-4-26B variants, Qwen3.6-27B I1 + MTP, DeepSeek R1 Distill 14B, Bonsai 27B. 
HS/TQA re-run planned (in progress since 04.08.).

**Efficiency** = Overall / runtime (h) (runtime = DS1000 + CoderEval latency).
Granite-4.0-H-Tiny has valid Coding scores in SS=100 run (DS1000 42% / CoderEval 62.5%) — the earlier 0% finding has been resolved. 
ERNIE 4.5 is not included in the consolidated results (double-quant bug, new release pending).

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
| Ernie-4.5-21b-A3B-pt (MoE)          | 21B   | 3B     | 7:1    | 64 (Text) + 64 (Vision)     | 2×(6 + 1 shared) = 14  | 2      | Multimodal Heterogeneous MoE; 28 layers; Text+Vision experts separate      |
| Qwen3.6-28B-REAP (i1)               | 28B   | ~3B    | 9.3:1  | 205 (REAP-pruned from 256)  | 8 (+1 shared) = 9      | 1      | Hybrid Gated DeltaNet + Attention; 40 layers; original 256 experts/layer   |
| Qwen3-30B-A3B-Instruct              | 30.5B | 3.3B   | 9.2:1  | 128                         | 8                       | No     | Qwen3-MoE; 48 layers; general use; 262K context                           |
| Qwen3-Coder-30B-A3B-Instruct        | 30.5B | 3.3B   | 9.2:1  | 128                         | 8                       | No     | Qwen3-MoE; 48 layers; Python-specialized; 262K context                    |
| Qwen3-Coder-REAP-25B-A3B (i1)       | 25B   | ~3B    | 8.3:1  | 103 (REAP-pruned from 128)  | 8                       | No     | Qwen3 architecture; 48 layers; 262K context; REAP-pruned from 30B         |
| Gemma-4-19B-A4B-it-REAP-i1          | 19B   | ~4B    | 4.75:1 | 90 (REAP-pruned from 128)   | 8 (+1 shared) = 9      | 1      | Hybrid Sliding/Full Attention; 30 layers; originally 128 experts/layer     |
| Gemma-4-26B-A4B                     | 26B   | ~4B    | 4.75:1 | 128                         | 8 (+1 shared) = 9      | 1      | Hybrid Sliding/Full Attention; 30 layers                                   |
| GLM-4.7-Flash                       | 30B   | 3B     | 10:1   | 64                          | 4 (+ 1 shared) = 5     | 1      | Glm4MoeLite; 47 layers (1 dense + 46 MoE); KV-quant sensitive (K min Q8_0)|
| GLM-4.7-Flash-REAP-23B-A3B          | 23B   | 3B     | 7.7:1  | 48 (REAP-pruned)            | 4 (+ 1 shared) = 5     | 1      | Glm4MoeLite; REAP-compressed (30B→23B); KV-quant sensitive (K min Q8_0)   |
| GPT-OSS-20B                         | 20.9B | 3.6B   | 5.8:1  | 32                          | 4                       | No     | MXFP4-quant MoE weights; 24 layers; Alternating Dense+Banded Sparse Attn  |
|                                      |       |        |        |                             |                         |        | **No KV-quantization!** (won't load otherwise)                             |
| Kimi-Linear-REAP-35B-A3B-Instruct-i1| 35B   | ~3B    | 11.7:1 | 180 (REAP-pruned)           | 8 (+1 shared) = 9      | 1      | Hybrid KDA+MLAS+SSM; 27 layers (26 MoE); 1M context; **no KV-quant!**     |
| Mellum2-12B-a2.5B-Instruct          | 12B   | 2.5B   | 4.8:1  | 64                          | 8                       | No     | 2 variants: Instruct SFT / Thinking SFT                                   |
| North-mini-code-1.0                 | 30B   | 3B     | 10:1   | 128                         | 8                       | No     | Cohere2MoE; 256K context; **no KV-cache quantization possible**            |
| MiroThinker-v1.5-30B                | 30B   | –      | –      | –                           | –                       | –      | MoE reasoning model; 48 layers; 24K context (auto-configured)              |

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
