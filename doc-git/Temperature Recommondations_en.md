# Temperature Recommendations per Model and Task

**Status:** 2026-08-06 · **Method:** Official Hugging Face model cards, vendor docs/blogs (Mistral, Qwen, DeepSeek, Microsoft, IBM, OpenAI, Google, Zhipu, Moonshot, NVIDIA, Liquid AI, Baidu, JetBrains, Cohere).

## Starting Point

The benchmarks run so far use the `BENCHMARK_CATEGORY_DEFAULTS` (`src/benchmark_config.py:241`) for models without an LMS JSON config:

| Task      | temp | top_p | max_tokens | thinking |
|-----------|------|-------|------------|----------|
| coding    | 0.0  | 1.0   |   4096     | False    |
| math      | 0.7  | 0.95  |   4096     | False    |
| knowledge | 0.0  | 1.0   |   4096     | False    |
| agentic   | 0.3  | 0.95  |   4096     | False    |

**Finding:** temp=0.0 for coding/knowledge is only appropriate for a subset of models. 

The official recommendations range from **0.0** (Granite 4, Phi-4, DeepSeek-Coder, Ministral, LFM2) to **1.0** (GPT-OSS, Gemma-4, Qwen3.6, North-Mini-Code, MiroThinker, Nemotron-3). 
Many coding-specialized models officially recommend 0.15–0.7.

## New Recommendation:
** 1. Reasoning/thinking models: flat t=0.6 (top_p 0.95) for everything — do not take over the category values.** 

Rationale:
Official thinking values are 0.6/0.95 everywhere, not 0.2:**
- DeepSeek-R1-Distill: **0.6/0.95** ("0.6 is recommended", range 0.5–0.7)
- Qwen3-14B Thinking: **0.6/0.95** (card explicitly warns: *"DO NOT use greedy"*)
- Qwen3.6-27B Coding/WebDev in thinking mode: **0.6/0.95**
- Nemotron-Cascade: **0.6/0.95** · Kimi-K2: **0.6** · GLM-4.7 SWE-bench, Tool-Calling: **0.7/1.0** 

The coding value of 0.2 from the proposal applies to **instruct coders** (Qwen2.5-Coder, Codestral, Devstral) — vendors explicitly run thinking models at 0.6 for coding. 
Low temperature/greedy is even counterproductive for thinking models (repetition collapse in the reasoning path, hence the "DO NOT use greedy" warning).

**2. Why 0.6 instead of 0.7:** 0.6 is the mode of the official specs (R1, Qwen3, Cascade, Kimi, Qwen3.6-Coding). 
0.7 (Math) falls within the R1 range, but 0.6 covers all 4 categories. 
top_p 0.95 = official standard across all thinking cards.

**Proposal for the new defaults (fallback without JSON config):**

| Task      | instruct | thinking |
|-----------|----------|----------|
| coding    |   0.2    | **0.6**  |
| knowledge |   0.6    | **0.6**  |
| agentic   |   0.6    | **0.6**  |
| math      |   0.7    | **0.6**  |
| top_p     |   1.0    | **0.95** |

**Limitations:**
- Exceptions: GPT-OSS (1.0/1.0), Gemma-4 (1.0/0.95), MiroThinker (1.0/0.95), Qwen3.6-general (1.0/0.95), Nemotron-3-Reasoning (1.0/1.0) — officially higher. 
        0.6 remains a compromise, but clearly closer to the recommendations than 0.0.
- **Watch out for compatibility:** previous benchmark runs still use temp=0.0 (category default) — after changing the defaults, old scores would not be directly comparable with a new run. 

## Implementation & Design Decision (2026-08-06)

**Architecture:** Since 2026-08-05, the LMS JSON config supplies the generation parameters
(single source of truth; `MODEL_TEMP_OVERRIDES` were removed). **Since 2026-08-06, the
sampling design below applies** (exception table > defaults; JSON temp/top_p only for the GUI).

**Fundamental conflict:** The LMS JSON config can only hold **one**
temperature/top_p value per model (applies to ALL benchmark categories). The new defaults
however differentiate per category (coding 0.2, knowledge 0.6, agentic 0.6, math 0.7).
A per-category differentiation can therefore **not be expressed** via the JSON config.

**Solution (decision, option "table > defaults, JSON temp ignored"):**
1. **Registry `sampling:` field** (`doc-git/model_registry.yaml`, SSOT since 13.08.):
   per-category `temperature`/`top_p` block (Variante A, model × category). Migrated
   for 17 models with the researched values (previously: `MODEL_CATEGORY_SAMPLING` in
   `src/benchmark_config.py`). Missing categories fall back to the table.
2. **Precedence:** registry `sampling:` cell > `MODEL_CATEGORY_SAMPLING` cell >
   `BENCHMARK_THINKING_DEFAULTS` (0.6/0.95) or `BENCHMARK_CATEGORY_DEFAULTS`
   (0.2/0.6/0.6/0.7). Applies to instruct **and** thinking runs — this way the
   documented thinking exceptions (GPT-OSS 1.0/1.0, Gemma-4 1.0/0.95,
   Nemotron-3-Reasoning 1.0/1.0) also take effect as cells.
3. **JSON temp/top_p are ignored for benchmarks** (they only apply to
   GUI usage). The JSON configs continue to supply top_k, min_p,
   enable_thinking, reasoning_effort, max_tokens/ctx.
4. `_source` shows the origin: `registry-sampling` | `benchmark-table` | `thinking-default` | `category-default`.
5. **Deviation from the 05.08 principle** ("LMS JSON = single source"): justified because
   the JSON config cannot express per-category differentiation. The registry/table is
   documented data logic with sources (no obscure `MODEL_TEMP_OVERRIDES` reload);
   all non-temperature parameters remain JSON-fed.
6. **Compromises:** MiroThinker (1.0/0.95) and Qwen3.6-general (1.0/0.95) run in the
   thinking run at flat 0.6/0.95 (see limitations; a table value would also
   affect the instruct run, where 0.7/0.8 applies).

**Implementation details (2026-08-06, uncommitted):**
- `BENCHMARK_CATEGORY_DEFAULTS`: coding 0.0→0.2, knowledge 0.0→0.6, agentic 0.3→0.6; math 0.7 remains
- new `BENCHMARK_THINKING_DEFAULTS` (0.6/0.95, `enable_thinking: True`); selection in
  `get_model_config` via `is_thinking_enabled` + `REASONING_PATTERNS` (augmented with
   registry thinking models: qwen3.5/3.6, mirothinker, kimi, glm-4.7/4.6v, phi-4,
   qwen3-14b, qwen3-coder-reap, `thinking` name component)
- new `MODEL_CATEGORY_SAMPLING` (exception table, see above); matching via the
  normalized registry key (`_normalized_lms_key`); the first matching row wins
- `get_model_config`: table cell (instruct AND thinking) > thinking/category
  defaults; JSON merge only for non-temperature fields now
- 55 LMS JSON configs updated (temp + top_p, `{checked, value}` format preserved)
- Matching bugfixes in `benchmark_config.py`: `@quant` suffixes (e.g. `@q5_0`), variant
  suffixes (`-qat`/`-ud`/`-imatrix`), publisher fallback (repacks under a different publisher)
- **Known:** LM Studio keeps config values in memory; a one-off revert (GLM-4.7-Flash)
  observed → for a lasting effect, adopt the values in the LMS GUI or restart LMS.
  The running SS=30 benchmark becomes inconsistent (evals already run: old values).

## Processor Repacks → Base Model (Mapping)

Many registry entries are not vendor models but **quantizations/repacks** (unsloth, bartowski, mradermacher, lmstudio-community, noctrex, vinpix, gabriellarson, intel/AutoRound, quietimpostor) 
or **subsequent fine-tunes/REAPs**. These repacks usually have no model card of their own with sampling recommendations. 
The research was therefore **always done on the base model on the actual vendor page**; the values in the table apply to all quants of a base model.

| Registry entry (processor)                                            | Processor                 | Base model (vendor)                        | Note                               |
|-----------------------------------------------------------------------|---------------------------|--------------------------------------------|------------------------------------|
| `unsloth/qwen3-coder-30b-a3b-instruct`                                | Unsloth (GGUF)            | Qwen3-Coder-30B-A3B-Instruct               | official best practices 0.7/0.8    |
| `mradermacher/qwen3-coder-reap-25b-a3b(-i1)`                          | MRadermacher (GGUF)       | cerebras/Qwen3-Coder-REAP-25B-A3B          | inherits Qwen3-Coder values        |
| `qwen/qwen2.5-coder-14b-instruct@*`                                   | Qwen (official quants)    | Qwen2.5-Coder-14B-Instruct                 | family default 0.7/0.8             |
| `unsloth/qwen3-30b-a3b-instruct-2507`, `intel/qwen3-30b-…-autoround`  | Unsloth / Intel AutoRound | Qwen3-30B-A3B-Instruct-2507                | 0.7/0.8                            |
| `Qwen/Qwen3.5-9B-GGUF`, `qwen/qwen3.5-9b`                             | Qwen                      | Qwen3.5-9B                                 | Thinking 1.0/0.95, Coding 0.6/0.95 |
| `unsloth/qwen3.6-27b`, `-mtp`; `mradermacher/qwen3.6-27b-i1`,         | Unsloth / MRadermacher    | Qwen3.6-27B (REAP variants: cerebras)      | Thinking 1.0/0.95, Coding 0.6/0.95 |
|        `qwen3.6-28b-reap-i1@*`                                        |
| `intel/mirothinker-v1.5-30b-…`                                        | Intel AutoRound           | miromind-ai/MiroThinker-v1.5-30B           | 1.0/0.95                           |
| `unsloth/phi-4`                                                       | Unsloth (GGUF)            | microsoft/phi-4                            | 0.0                                |
| `unsloth/gemma-4-26b-a4b-it`, `bartowski/google_gemma-4-26b-a4b-it@*`,| Unsloth/Bartowski/...     |google/gemma-4-12B-it or -19B/-26B-A4B-it   | 1.0/0.95, top_k 64                 |
|    `mradermacher/gemma-4-26b-a4b-it-i1@*`, `gemma-4-19b-a4b-it-reap-i1@*`,| ...MRadermacher/Google|
|    `google/gemma-4-*-qat`                                             |
| `unsloth/ernie-4.5-21b-a3b-pt`, `noctrex/ernie-4.5-21b-a3b-pt_moe@*`  | Unsloth / Noctrex         | baidu/ERNIE-4.5-21B-A3B-PT                 | Qianfan 0.8/1.0                    |
| `unsloth/devstral-small-2-24b-instruct-2512`                          | Unsloth (GGUF)            | mistralai/Devstral-Small-2-24B-Instruct-2512 | 0.15                             |
| `bartowski/mistralai_magistral-small-2509`                            | Bartowski (GGUF)          | mistralai/Magistral-Small-2509             | 0.7/0.95                           |
| `lmstudio-community/ministral-3-14b-instruct-2512`                    | LM Studio                 | mistralai/Ministral-3-14B-Instruct-2512    | <0.1                               |
| `gabriellarson/mamba-codestral-7b-v0.1`                               | Gabriellarson (GGUF)      | mistralai/Mamba-Codestral-7B-v0.1          | no value, Mistral range            |
| `unsloth/januscoder-14b`                                              | Unsloth (GGUF)            | internlm/JanusCoder-14B (base Qwen3-14B)   | no value → Qwen3                   |
| `unsloth/north-mini-code-1.0`                                         | Unsloth (GGUF)            | CohereLabs/North-Mini-Code-1.0             | 1.0/0.95                           |
| `nerdsking/nerdsking-python-coder-7b-i`                               | Nerdsking (Fine-Tune)     | Nerdsking-Python-Coder-7B-i                | 0.1 (Eval)                         |
| `mradermacher/deepseek-coder-33b-instruct`                            | MRadermacher (GGUF)       | deepseek-ai/deepseek-coder-33b-instruct    | greedy                             |
| `lmstudio-community/deepseek-coder-v2-lite-instruct`                  | LM Studio                 | deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct | 0.3 (vLLM)                        |
| `lmstudio-community/deepseek-r1-distill-qwen-14b`                     | LM Studio                 | deepseek-ai/DeepSeek-R1-Distill-Qwen-14B   | 0.6/0.95                           |
| `lmstudio-community/internlm2-math-plus-20b`                          | LM Studio                 | internlm/internlm2-math-plus-20b           | greedy + CoT                       |
| `mradermacher/kimi-linear-reap-35b-a3b-instruct.i1`                   | MRadermacher (GGUF)       | moonshotai/Kimi-Linear (REAP: cerebras)    | Kimi-K2: 0.6                       |
| `mradermacher/nemotron-cascade-14b-thinking`                          | MRadermacher (GGUF)       | nvidia/Nemotron-Cascade-14B-Thinking       | 0.6/0.95                           |
| `quietimpostor/nemotron-3-nano-reap-21b-a3b`                          | QuietImpostor (REAP)      | nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16 | Reasoning 1.0/1.0, Tool 0.6/0.95   |
| `noctrex/lfm2-24b-a2b_moe`                                            | Noctrex (MXFP4)           | LiquidAI/LFM2-24B-A2B                      | 0.1                                |
| `unsloth/glm-4.7-flash`, `-reap-23b-a3b`                              | Unsloth                   | zai-org/glm-4.7-flash (REAP: cerebras)     | 1.0/0.95, SWE+Tool Calling 0.7/1.0 |
| `essentialai/essentialai/rnj-1`                                       | (registry name)           | EssentialAI/rnj-1                          | [0, 0.6]                           |

**Corrected registry links** (repo names deviate): `essentialai/essentialai/rnj-1` → `EssentialAI/rnj-1`; `google/gemma-4-12b-it-qat` (BF16) does not exist → only QAT-q4_0 repos; 
        `mradermacher/qwen3.6-27b-i1` does not exist as a repo (only i1 repacks of fine-tunes, base Qwen3.6-27B).

## Legend

- **Bold** = official specification from the vendor (card/docs/example code).
- `(BP)` = no official specification; derived best-practice value (based on family values or common practice: Coding 0.2–0.3, Agentic 0.2–0.6, Math 0.2–0.7, Knowledge 0.6–0.7).
- "–" = not suitable for this task / not recommended.

## Overview Table (Base Models, Quants Consolidated)

| Model (registry key)                                                               | Official recommendation (temp/top_p)                                       | Coding               | Knowledge      | Agentic           | Math                |
|-------------------------------------------------------------------------------------|--------------------------------------------------------------------------|----------------------|----------------|-------------------|---------------------|
| Qwen3-Coder-30B-A3B (`unsloth/qwen3-coder-30b-a3b-instruct`)                        | *0.7 / 0.8*, top_k 20, rep_pen 1.05                                      | *0.7/0.8*            | *0.7/0.8*      | *0.7/0.8*         | *0.7/0.8*           |
| Qwen3-Coder-REAP-25B (`mradermacher/qwen3-coder-reap-25b-a3b…`)                     | no own specification → inherits Qwen3-Coder                              |  0.7/0.8 (BP)        |  0.7/0.8 (BP)  | 0.7/0.8 (BP)      | 0.7/0.8 (BP)        |
| Qwen2.5-Coder-14B (`qwen/qwen2.5-coder-14b-instruct@*`)                             | family default *0.7 / 0.8* (Qwen2.5)                                     |  0.2–0.3 (BP)        | *0.7/0.8*      | 0.5–0.7 (BP)      | *0.7/0.8*           |         
| Qwen3-30B-A3B-Instruct-2507 (`unsloth/qwen3-30b-a3b-instruct-2507`, Intel-q2ks)     | *0.7 / 0.8*, top_k 20, min_p 0                                           |  0.7/0.8 (BP)        |  0.7/0.8 (BP)  | 0.7/0.8 (BP)      | 0.7/0.8 (BP)        |
| Qwen3-14B (`qwen/qwen3-14b`)                                                        | Thinking *0.6 / 0.95*; Non-Thinking *0.7 / 0.8*                          | *0.6/0.95*           | *0.6/0.95*     | 0.6/0.95 (BP)     | *0.6/0.95*          |
| Qwen3.5-9B (`qwen/qwen3.5-9b`, `Qwen/Qwen3.5-9B-GGUF`)                              | Thinking *1.0 / 0.95* (pres_pen 1.5); Coding/WebDev *0.6 / 0.95*;        | *0.6/0.95*           | *1.0/0.95*     | 1.0/0.95 (BP)     | *1.0/1.0*           |
                                                                                      |             / Instruct *0.7 / 0.8*; Instruct-Reasoning *1.0 / 1.0*       |                      |                |                   |                     |
| Qwen3.6-27B (`unsloth/qwen3.6-27b`, -mtp, `mradermacher/qwen3.6-27b-i1`, -28b-reap) | Thinking *1.0 / 0.95*; Coding/WebDev *0.6 / 0.95*; Instruct *0.7 / 0.8*  | *0.6/0.95*           | *1.0/0.95*     | *1.0/0.95*        | 0.6–1.0/0.95 (BP)   |
| MiroThinker-v1.5-30B (`intel/mirothinker-v1.5-30b-q2ks-mixed-autoround`)            | *1.0 / 0.95*, rep_pen 1.05, ctx 262144                                   |  1.0/0.95 (BP)       | *1.0/0.95*     | *1.0/0.95*        | 1.0/0.95 (BP)       |
| DeepSeek-R1-Distill-Qwen-14B (`lmstudio-community/deepseek-r1-distill-qwen-14b`)    | *0.5–0.7 (0.6 recommended) / 0.95*                                       | *0.6/0.95*           | *0.6/0.95*     | *0.6/0.95*        | *0.6/0.95*          |
| DeepSeek-Coder-33B-Instruct (`mradermacher/deepseek-coder-33b-instruct`)            | example *greedy* (do_sample=False, top_k 50, top_p 0.95)                 | *greedy* (0.0–0.3 BP)|  0.7 (BP)      | 0.2 (BP)          | 0.5 (BP)            |
| DeepSeek-Coder-V2-Lite (`lmstudio-community/deepseek-coder-v2-lite-instruct`)       | vLLM example *0.3*; transformers greedy                                  | *0.3*                |  0.7 (BP)      | 0.2–0.3 (BP)      | 0.3–0.5 (BP)        |
| GPT-OSS-20B (`openai/gpt-oss-20b`)                                                  | *1.0 / 1.0* ("recommended sampling parameters", GitHub-README)           | *1.0/1.0*            | *1.0/1.0*      | *1.0/1.0*         | *1.0/1.0*           |
| Phi-4 (`unsloth/phi-4`)                                                             | *0.0* (card metadata)                                                    | *0.0*                | *0.0*          | 0.0–0.3 (BP)      | *0.0*               |
| Gemma-4 12B/26B-A4B (+QAT, REAP) (`google/gemma-4-*`, `unsloth/gemma-4-*`,          | *1.0 / 0.95*, top_k 64 (standardized for all tasks)                      | *1.0/0.95*           | *1.0/0.95*     | *1.0/0.95*        | *1.0/0.95*          |
|      `mradermacher/gemma-4-*`, `bartowski/google_gemma-4-*`)                        |                                                                          |                      |                |                   |                     |
| rnj-1 (`essentialai/rnj-1`)                                                         | *range [0, 0.6]*; examples 0.2 / 0.95; tool-use model                    | *0.2/0.95*           |  0.2/0.95 (BP) |  *0.2/0.95*       | 0.2/0.95 (BP)       |
| Granite-4.0-H-Tiny (`ibm-granite/granite-4.0-h-tiny`)                               | *0.0 / 1.0*, top_k 0 (IBM docs: "work best with temperature 0")          | *0.0/1.0*            | *0.0/1.0*      | *0.0/1.0*         | *0.0/1.0*           |
| Granite-4.1 8B/30B (`ibm-granite/granite-4.1-8b`, `-30b`)                           | family rule *0.0 / 1.0*, top_k 0                                         | *0.0/1.0*            | *0.0/1.0*      | *0.0/1.0*         | *0.0/1.0*           |
| Codestral-22B (`mistralai/codestral-22b-v0.1`)                                      | examples *temp=0.0*; FIM docs: range 0.0–0.7                             | *0.0–0.3*            |  0.7 (BP)      | 0.2 (BP)          | 0.3 (BP)            |
| Mamba-Codestral-7B (`gabriellarson/mamba-codestral-7b-v0.1`)                        | no specification → Mistral range                                         |  0.0–0.3 (BP)        |  0.7 (BP)      | 0.2 (BP)          | 0.3 (BP)            |
| Devstral-Small-2-24B (`unsloth/devstral-small-2-24b-instruct-2512`)                 | examples *0.15*                                                          | *0.15*               |  0.4 (BP)      | *0.15* (SWE-Agent)| 0.3 (BP)            |
| Magistral-Small-2509 (`bartowski/mistralai_magistral-small-2509`)                   | *0.7 / 0.95* (explicitly)                                                | *0.7/0.95*           | *0.7/0.95*     | *0.7/0.95*        | *0.7/0.95*          |
| Ministral-3-14B (`lmstudio-community/ministral-3-14b-instruct-2512`)                | *temp < 0.1* ("daily driver"); examples 0.15                             | *<0.1–0.15*          | *<0.1–0.15*    | *<0.1–0.15*       | *<0.1–0.15*         |
| JanusCoder-14B (`unsloth/januscoder-14b`)                                           | no specification → Qwen3 family (0.7/0.8)                                |  0.2–0.3 (BP)        |  0.7/0.8 (BP)  | 0.2 (BP)          | 0.5 (BP)            |
| North-Mini-Code-1.0 (`unsloth/north-mini-code-1.0`)                                 | *1.0 / 0.95* (explicitly, also for benchmarks)                           | *1.0/0.95*           | *1.0/0.95*     | *1.0/0.95*        | *1.0/0.95*          |
| Nerdsking-Python-Coder-7B (`nerdsking/nerdsking-python-coder-7b-i`)                 | HumanEval config *0.1*, do_sample=False                                  | *0.1*                |  0.7 (BP)      | 0.2 (BP)          | 0.2–0.3 (BP)        |
| GLM-4.7-Flash (`unsloth/glm-4.7-flash`, -reap-23b)                                  | eval default *1.0 / 0.95*; SWE-bench *0.7 / 1.0*; τ²-Bench *0*           | *0.7/1.0* (SWE)      | *1.0/0.95*     | *0* (τ²)          | *1.0/0.95*          |
| GLM-4.6V-Flash (`zai-org/glm-4.6v-flash`)                                           | *0.8 / 0.6*, top_k 2, rep_pen 1.1                                        |  0.8/0.6 (visual)    | 0.8/0.6        | 0.8/0.6           | 0.8/0.6             |
| ERNIE-4.5-21B-A3B-PT (`unsloth/ernie-4.5-21b-a3b-pt*`,                              | card: n/a; hosted (Qianfan) *0.8 / 1.0*; Baidu tuning: 0.3 for focus     |  0.2–0.3 (BP)        | *0.8/1.0*      | 0.2–0.8, tool     | 0.2–0.3 (BP)        |
|               ... `noctrex/ernie-4.5-21b-a3b-pt_moe*`)                              |                                                                          |                      |                |   use low (BP)    |                     |
| Falcon3-10B-Instruct (`tiiuae/falcon3-10b-instruct`)                                | no specification (quickstart greedy)                                     |  0.2/0.95 (BP)       |0.6–0.7/0.9 (BP)| 0.2–0.3 (BP)      | 0.2/0.95 (BP)       |
| Falcon3-Mamba-7B (`tiiuae/falcon3-mamba-7b-instruct`)                               | no specification                                                         |  0.2/0.95 (BP)       |0.6–0.7/0.9 (BP)| 0.2–0.3 (BP)      | 0.2/0.95 (BP)       |
| Mellum2-12B (`jetbrains/mellum2-12b-a2.5b-instruct`, -thinking_moe)                 | quickstart *0.6 / 0.95*, top_k 20                                        | *0.6/0.95*           | *0.6/0.95*     | *0.6/0.95*        | *0.6/0.95*          |
| Kimi-Linear-REAP-35B (`mradermacher/kimi-linear-reap-35b-a3b-instruct.i1`)          | card: no specification; Kimi-K2: *0.6*                                   |  0.6 (BP, from K2)   |  0.6 (BP)      | 0.6 (BP)          | 0.6 (BP)            |
| Nemotron-Cascade-14B-Thinking (`mradermacher/nemotron-cascade-14b-thinking`)        | *0.6 / 0.95* (thinking-only)                                             | *0.6/0.95*           | *0.6/0.95*     | *0.6/0.95*        | *0.6/0.95*          |
| Nemotron-3-Nano-REAP-21B (`quietimpostor/nemotron-3-nano-reap-21b-a3b`)             | base 30B: Reasoning *1.0 / 1.0*; Tool-Calling *0.6 / 0.95*;              | *1.0/1.0*            | *1.0/1.0*      | *0.6/0.95*        | *1.0/1.0*           |
|                                                                                     |         ... thinking off: greedy                                         |                      |                |                   |                     |
| LFM2-24B-A2B (`noctrex/lfm2-24b-a2b_moe`)                                           | quickstart *0.1*, top_k 50, rep_pen 1.05; "not recommended for coding"   | –                    | *0.1*          | *0.1*             | 0.1 (BP)            |
| InternLM2.5-20B-Chat (`internlm/internlm2_5-20b-chat`)                              | no specification                                                         |  0.6/0.8 (BP)        |  0.6/0.8 (BP)  |  0.6/0.8 (BP)     | 0.6/0.8 (BP)        |
| InternLM2-Math-Plus-20B (`lmstudio-community/internlm2-math-plus-20b`)              | no specification; official eval: *greedy + CoT*                          | –                    |  0.7 (BP)      | –                 |*greedy* (0.2–0.6 BP)|

(Essential says about RNJ-1's knowledge segment: "not optimized for factual recovery")

## Key Takeaways

1. **temp=0.0 (the current coding/knowledge default) is only defensible for Granite 4.x, Phi-4, DeepSeek-Coder, Ministral, LFM2 and Codestral (example).** 
        All other vendors recommend higher values.
2. **Explicit 1.0 recommendations** (also for coding): GPT-OSS, Gemma-4, Qwen3.5/3.6 (Thinking), North-Mini-Code, MiroThinker, Nemotron-3 (Reasoning). 
        For these models, temp=0.0 reduces diversity and can lead to repetitive/empty responses — potentially explaining poorer scores.
3. **Reasoning/thinking models:** DeepSeek-R1 (0.6/0.95), Nemotron-Cascade (0.6/0.95), Qwen3-Thinking (0.6/0.95) — temp=0.7 (the current math default) fits well here.
4. **Agentic/tool use:** ranges from 0 (GLM-4.7 τ²-Bench, Granite) via 0.2 (rnj-1, Devstral) to 1.0 (Qwen3.6, GPT-OSS). Kimi-K2: 0.6.
5. **Consequence for the pipeline (superseded by the design above):** The clean solution would be
        to set `temperature` per model in the JSON configs (via the LMS GUI) or to raise the defaults;
        instead, the sampling design of 2026-08-06 was implemented (`MODEL_CATEGORY_SAMPLING` > defaults,
        JSON temp GUI-only).

## Sources

**Mistral:** [Codestral card](https://huggingface.co/mistralai/codestral-22b-v0.1) · [FIM API docs](https://docs.mistral.ai/api/endpoint/fim) · [Codestral blog](https://mistral.ai/news/codestral) · [Mamba-Codestral card](https://huggingface.co/mistralai/Mamba-Codestral-7B-v0.1) · [Mamba blog](https://mistral.ai/news/codestral-mamba) · [Devstral card](https://huggingface.co/mistralai/Devstral-Small-2-24B-Instruct-2512) · [Magistral card](https://huggingface.co/mistralai/Magistral-Small-2509) · [Ministral-3 card](https://huggingface.co/mistralai/Ministral-3-14B-Instruct-2512)

**Qwen:** [Qwen2.5-Coder](https://huggingface.co/Qwen/Qwen2.5-Coder-14B-Instruct) · [Qwen2.5 family](https://huggingface.co/Qwen/Qwen2.5-14B-Instruct-1M) · [Qwen2.5-Coder blog](https://qwenlm.github.io/blog/qwen2.5-coder/) · [Qwen3-Coder](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct) · [Qwen3-Coder blog](https://qwenlm.github.io/blog/qwen3-coder/) · [Qwen3-Coder-REAP](https://huggingface.co/cerebras/Qwen3-Coder-REAP-25B-A3B) · [Qwen3-30B-A3B-2507](https://huggingface.co/Qwen/Qwen3-30B-A3B-Instruct-2507) · [Qwen3-14B](https://huggingface.co/Qwen/Qwen3-14B) · [Qwen3 quickstart](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html) · [Qwen3 paper](https://arxiv.org/abs/2505.09388) · [Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B) · [Qwen3.5 blog](https://qwen.ai/blog?id=qwen3.5) · [Qwen3.6-27B](https://huggingface.co/Qwen/Qwen3.6-27B) · [Qwen3.6 blog](https://qwen.ai/blog?id=qwen3.6-27b) · [Alibaba Cloud blog](https://www.alibabacloud.com/blog/qwen3-6-27b-flagship-level-coding-in-a-27b-dense-model_603063) · [Qwen3.6-MTP repack](https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF) · [Intel AutoRound repacks](https://huggingface.co/Intel/Qwen3-30B-A3B-Instruct-2507-gguf-q2ks-mixed-AutoRound)

**DeepSeek:** [DeepSeek-Coder-33B](https://huggingface.co/deepseek-ai/deepseek-coder-33b-instruct) · [DeepSeek-Coder GitHub](https://github.com/deepseek-ai/DeepSeek-Coder) · [DeepSeek-Coder-V2](https://huggingface.co/deepseek-ai/deepseek-coder-v2-lite-instruct) · [DeepSeek-Coder-V2 GitHub](https://github.com/deepseek-ai/DeepSeek-Coder-V2) · [R1-Distill-Qwen-14B](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-14B) · [R1 paper](https://arxiv.org/abs/2501.12948) · [DeepSeek API](https://api-docs.deepseek.com/api/create-chat-completion)

**Microsoft/OpenAI:** [Phi-4](https://huggingface.co/microsoft/phi-4) · [Phi-4 paper](https://arxiv.org/pdf/2412.08905) · [GPT-OSS](https://github.com/openai/gpt-oss) · [GPT-OSS card](https://huggingface.co/openai/gpt-oss-20b) · [GPT-OSS sampling discussion](https://huggingface.co/openai/gpt-oss-120b/discussions/21)

**IBM:** [Granite docs](https://www.ibm.com/granite/docs/models/granite) · [Granite-4.1 docs](https://www.ibm.com/granite/docs/models/granite4-1) · [Granite-4.0-H-Tiny](https://huggingface.co/ibm-granite/granite-4.0-h-tiny) · [Granite-4.1-8B](https://huggingface.co/ibm-granite/granite-4.1-8b) · [Granite-4.1-30B](https://huggingface.co/ibm-granite/granite-4.1-30b) · [Granite-4.1 GitHub](https://github.com/ibm-granite/granite-4.1-language-models) · [Granite Kitchen](https://github.com/ibm-granite-community/granite-kitchen) · [Unsloth Granite-4.0](https://unsloth.ai/docs/models/tutorials/ibm-granite-4.0) · [Unsloth Granite-4.1](https://unsloth.ai/docs/models/ibm-granite-4.1) · [Granite-Code paper](https://arxiv.org/html/2405.04324v1)

**Google:** [Gemma-4-12B-it](https://huggingface.co/google/gemma-4-12B-it) · [Gemma-4-26B-A4B-it](https://huggingface.co/google/gemma-4-26B-A4B-it) · [Gemma-4-QAT-GGUF](https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-gguf) · [Gemma model card 4](https://ai.google.dev/gemma/docs/core/model_card_4) · [Unsloth Gemma-4](https://unsloth.ai/docs/models/gemma-4)

**EssentialAI:** [rnj-1](https://huggingface.co/EssentialAI/rnj-1) · [rnj-1-instruct](https://huggingface.co/EssentialAI/rnj-1-instruct)

**Zhipu (z.ai):** [GLM-4.7-Flash](https://huggingface.co/zai-org/glm-4.7-flash) · [GLM-4.7 docs](https://docs.z.ai/guides/llm/glm-4.7) · [GLM-4.7-REAP](https://huggingface.co/cerebras/GLM-4.7-Flash-REAP-23B-A3B) · [GLM-4.6V-Flash](https://huggingface.co/zai-org/glm-4.6v-flash)

**Baidu:** [ERNIE-4.5 card](https://huggingface.co/baidu/ERNIE-4.5-21B-A3B-PT) · [Qianfan API](https://cloud.baidu.com/doc/qianfan/s/6mh4stoyf) · [ERNIE-4.5 blog](https://ernie.baidu.com/blog/zh/posts/ernie4.5/) · [Baidu tuning guide](https://cloud.baidu.com/article/3547357)

**TII:** [Falcon3-10B](https://huggingface.co/tiiuae/falcon3-10b-instruct) · [Falcon3-Mamba-7B](https://huggingface.co/tiiuae/falcon3-mamba-7b-instruct) · [Falcon3 blog](https://huggingface.co/blog/falcon3)

**JetBrains:** [Mellum2-Instruct](https://huggingface.co/JetBrains/Mellum2-12B-A2.5B-Instruct) · [Mellum2-Thinking](https://huggingface.co/JetBrains/Mellum2-12B-A2.5B-Thinking)

**Moonshot:** [Kimi-K2-Instruct](https://huggingface.co/moonshotai/Kimi-K2-Instruct) · [Kimi-Linear-48B](https://huggingface.co/moonshotai/Kimi-Linear-48B-A3B-Instruct) · [Kimi-Linear-REAP-35B](https://huggingface.co/cerebras/Kimi-Linear-REAP-35B-A3B-Instruct) · [Kimi-Linear paper](https://huggingface.co/papers/2510.26692)

**NVIDIA:** [Nemotron-Cascade-14B-Thinking](https://huggingface.co/nvidia/Nemotron-Cascade-14B-Thinking) · [Nemotron-3-Nano-30B-BF16](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16) · [Nemotron-3 paper](https://arxiv.org/abs/2512.20848) · [Nemotron-3-Nano-REAP-21B-GGUF](https://huggingface.co/QuietImpostor/Nemotron-3-Nano-REAP-21B-A3B-MXFP4-GGUF)

**Liquid AI:** [LFM2-24B-A2B](https://huggingface.co/LiquidAI/LFM2-24B-A2B) · [Liquid docs](https://docs.liquid.ai/lfm) · [noctrex repack](https://huggingface.co/noctrex/LFM2-24B-A2B-MXFP4_MOE-GGUF)

**InternLM:** [InternLM2.5-20B-Chat](https://huggingface.co/internlm/internlm2_5-20b-chat) · [InternLM2-Math-Plus-20B](https://huggingface.co/internlm/internlm2-math-plus-20b) · [InternLM-Math GitHub](https://github.com/InternLM/InternLM-Math) · [InternLM-Math paper](https://arxiv.org/abs/2402.06332)

**Miscellaneous:** [MiroThinker-v1.5-30B](https://huggingface.co/miromind-ai/MiroThinker-v1.5-30B) · [MiroThinker paper](https://arxiv.org/abs/2511.11793) · [North-Mini-Code-1.0](https://huggingface.co/CohereLabs/North-Mini-Code-1.0) · [JanusCoder](https://huggingface.co/internlm/JanusCoder-14B) · [Nerdsking-Python-Coder-7B](https://huggingface.co/Nerdsking/Nerdsking-python-coder-7B-i) · [REAP paper](https://arxiv.org/abs/2510.13999) · [Ternary-Bonsai-27B](https://huggingface.co/prism-ml/Ternary-Bonsai-27B-gguf) · [Bonsai-8B](https://huggingface.co/prism-ml/Ternary-Bonsai-8B-gguf) · [vinpix Bonsai repacks](https://huggingface.co/vinpix/Ternary-Bonsai-27B-Stock-MTP-GGUF)

