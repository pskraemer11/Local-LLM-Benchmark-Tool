# Gemma-4 – Consolidated Model Hints

> Status: 2026-07-29
> Sources: 8 documents from `doc-git/Model Specific Hints/`,
> `doc-git/Jinja-Chat-Templates/`, `doc-git/model_registry.yaml`, `doc-git/Architecture-and-Flow.md`

---
## Capabilities

- **Reasoning:** All models in the family are designed as highly capable reasoners, with configurable
                [thinking modes](https://ai.google.dev/gemma/docs/capabilities/thinking).
- **Extended Multimodalities:** Processes Text, [Image](https://ai.google.dev/gemma/docs/capabilities/vision/image) with variable aspect ratio and resolution support (all models),
                [Video](https://ai.google.dev/gemma/docs/capabilities/vision/video), and [Audio](https://ai.google.dev/gemma/docs/capabilities/audio) (featured natively on the E2B, E4B and 12B models).
- **Increased Context Window:** Small models feature a 128K context window, while the medium models support 256K.
- **Enhanced Coding \& Agentic Capabilities:** Achieves notable improvements in coding benchmarks alongside built-in
                [function-calling support](https://ai.google.dev/gemma/docs/capabilities/text/function-calling-gemma4), powering highly capable autonomous agents.
- **Native System Prompt Support:** Gemma 4 introduces built-in support for the system role, enabling more structured and controllable conversations.
- **[Multi-Token Prediction] (https://ai.google.dev/gemma/docs/mtp/overview)**


## 1. Model Variants in the Registry

| Variant                             | Publisher    | Quant(s)    | Architecture            | Special Feature                 |
|-------------------------------------|--------------|-------------|-------------------------|---------------------------------|
| `gemma-4-e4b`                       | google       |   –         | Gemma-4 MoE (PLE)       | Embedding model?                |
| `gemma-4-12b-qat@q4_0`              | google       | Q4_0        | Gemma-4 (12B) Unified   | QAT, Audio+Video native         |
| `gemma-4-19b-a4b-it-reap-i1@q4_k_s` | mradermacher | Q4_K_S      | Gemma-4 MoE             | REAP-compressed, 18 experts     |
| `gemma-4-26b-a4b-it-quat@q4_0`      | google       | Q4_0        | Gemma-4 MoE             | QAT-weighted                    |
| `google_gemma-4-26b-a4b-it@q3_k_s`  | bartowski    |Q3_K_S,IQ4_XS| Gemma-4 MoE             | lm_eval=0% problem              |
| `gemma-4-26b-a4b-it@iq4_xs`         | google       | IQ4_XS      | Gemma-4 MoE             | Original Google                 |
| `gemma-4-26b-a4b-it-ud@iq3_s`       | unsloth      | IQ3_S       | Gemma-4 MoE             | UD version                      |
| `gemma-4-26b-a4b-it-i1`             | mradermacher | IQ4_XS      | Gemma-4 MoE             | i1 quantization                 |
| `gemma-4-31b.i1`                    | mradermacher | IQ3_M       | Gemma-4 Dense           | 31B dense                       |

All Gemma-4 IT models have `reasoning: thinking` and use `blueprint: gemma_reasoning`.

---

## 2. KV-Cache: NO Quantization (f16 mandatory)

**Rule:** For all Gemma-4 models, the KV-Cache MUST be set to `f16` – both K and V.

- `k_cache: f16` (default would be `q8_0`)
- `v_cache: f16` (default would be `iq4_nl`)

**Reason:** Gemma-4 uses a special KV-Cache structure / attention mechanism that does not support quantized KV-Cache representation.
                If the KV-Cache is quantized (e.g., `q8_0`), the model **will not load** or will produce incorrect results.

**VRAM impact:** `f16` = 2 bytes/element (vs. `q8_0` = 1.0, `q4_0` = 0.5). The KV-Cache therefore theoretically uses two to four times as much VRAM as with quantized models.
                The MoE architecture mitigates this somewhat. The "unified KV-Cache" setting in LMS (llama.cpp) can also help counteract this.
                This is already taken into account in the rough calculation of `context_length` and `useUnifiedKvCache`.

All 9 Gemma-4 entries in `model_registry.yaml` correctly have `k_cache: f16` and `v_cache: f16` set.

---

## 3. System Prompt

### 3.1 Official Format (Google DeepMind)

Gemma-4 IT models use a structured token system (`<|turn|>`, `<|think|>`, etc.). The system prompt is processed in the chat template.

### 3.2 Custom Blueprint Tags – NOT in Chat Template

The file `Gemma-4 - System Prompt Example (ungeprüft).txt` contains custom XML tags:

```
<role>...</role>
<thinking>...</thinking>
<code>...</code>
<math>...</math>
<output>...</output>
```

**Assessment:** These tags are **not** part of the official Gemma-4 tokenizer vocabulary.
They are registered neither as `sot_token`, `eot_token` nor as any other control tokens.
The tags belong in the **Blueprint system** (`gemma_assistant`/`gemma_reasoning`) and are stored as **plain text in the LM Studio System Prompt Field**.

They **must not** be built into the Jinja chat template – the template exclusively processes the official tokens (`<|turn>`, `<|think|>`, `<|tool>`, `<|channel>`, etc.).

### 3.3 System Prompt Parameters (recommended)

| Parameter                                                | Value                              | Reason                            |
|----------------------------------------------------------|------------------------------------|-----------------------------------|
| `enable_thinking`                                        | `false` (Code), `true` (Reasoning) | Control via Blueprint/Benchmark   |
| No thinking tags in prompt when `enable_thinking=False`  |           –                        | Otherwise Gemma ignores the flag  |

---

## 4. Chat Template (Jinja)

### 4.1 Templates Used

| Model              | Template File                       |
|--------------------|-------------------------------------|
| 12B (QAT)          | `gemma4_12b_template_minijinja.jinja` |
| 19B (REAP)         | `gemma4-19b-template_minijinja.jinja` |
| 26B (all quantizations) | `gemma4-26b-template_minijinja.jinja` |
| 31B                | `gemma4-26b-template_minijinja.jinja` |

### 4.2 Token Reference (per Technical Report Appendix Table 11)

| Function          | Token                                                   |
|-----------------------------------|-------------------------------------------------------|
| Turn-Start (System/User/Model)    | `<|turn>role\n`                                       |
| Turn-End                          | `<turn|>`                                             |
| Thinking Signal (Prompt side)     | `<|think|>`                                           |
| Thinking Trace (Response side)    | `<|channel>thought\n...<channel|>`                    |
| Tool Declaration                  | `<|tool>declaration:name{...}<tool|>`                 |
| Tool Call                         | `<|tool_call>call:name{...}<tool_call|>`              |
| Tool Response                     | `<|tool_response>response:name{...}<tool_response|>`  |
| BOS                               | `bos_token` (per tokenizer)                           |

Compare "Technical Report Gemma-4" pdf by Google DeepMind, Appendix, page 17.

### 4.3 Template Divergence (CRITICAL – as of 07/13)

Three generations exist in parallel:

1. **GGUF-embedded** (Original in `tokenizer_config.json`) – 270-line macro version
2. **Hub Jinja override** (`~/.lmstudio/hub/models/google/*.jinja`) – **authoritative source**
3. **doc-git copies** – partially outdated (contain unconditional `<|think|>`, `<|channel>thought`)

**Recommended action:** Regularly synchronize doc-git copies with hub overrides.

### 4.4 `enable_thinking` Control in the Template

The template controls thinking via:

```jinja
{%- if enable_thinking is defined and enable_thinking -%}
    {{- '<|think|>\n' -}}
{%- endif -%}
```

- If `enable_thinking` is set to `false`, **no** `<|think|>` token appears in the prompt.
- When `enable_thinking=True`, `<|think|>` is inserted into the system turn.
- **Known issue (07/11):** Some Gemma Config instances ignore `enable_thinking=False` – Workaround: System prompt override "Do NOT use thinking or reasoning. Answer directly without `<|channel>thought` tags."

---

## 5. Thinking / Reasoning Effort

### 5.1 Control Mechanisms

| Method | Effect | Usage |
|---|---|---|
| `enable_thinking: bool` in JSON config (via `extra_body`) | `<|think|>` in prompt | Code benchmarks: `false`; Reasoning: `true` |
| LM Studio GUI: "Enable Thinking" | Same effect | Manual configuration |
| CLI `--no-think` (tool-eval-bench v2.0.7) | Sets `enable_thinking=false` | Agentic pipeline |
| System prompt override (if config ignored) | Textual prohibition | Emergency workaround |

### 5.2 Recommendation by Benchmark Type

| Benchmark Type    | `enable_thinking` | Reason |
|---|---|---|
| DS1000, CoderEval, Coding tasks | `false` | Thinking costs tokens + time, provides no benefit |
| MathQA, MMLU-Pro, GPQA | `true` | Reasoning improves accuracy |
| Agentic (BFCL) | `false` | Clear tool calls, no thinking needed |
| Generic chat tasks | `false` | Direct answers preferred |

### 5.3 Thinking Trace Extraction

Gemma-4 delivers thinking in the `content` field, not as `reasoning_content` (OpenAI format). The `strip_thinking_tokens()` function recognizes both formats:

- Gemma-4: `<|channel>thought\n...<channel|>`
- Legacy: `<think>...</think>`

After extraction, only the answer text (without thinking) is passed into benchmark evaluation.

---

## 6. LM Studio Reasoning Parsing MUST be disabled

**Important:** LM Studio has a global `reasoning.parsing` setting (default: `enabled=true`) that inserts `<think>`/`</think>` tags into the response – **even for models without native reasoning**. This interferes with API-driven control and generates unnecessary tokens.

**Recommendation:** Set to `false` for all models (including Gemma-4). Thinking control is handled exclusively via `enable_thinking` in the API call, not through the GUI.

**Configuration (per model):**
```json
// ~/.lmstudio/.internal/user-concrete-model-default-config/<pub>/<model>/<model>.gguf.json
"llm.prediction.reasoning.parsing": {
  "enabled": false,
  "startString": "<think>",
  "endString": "</think>"
}
```

**GUI:** Chat Panel → "..." → Model Settings → "Reasoning Parsing" → Disable.

---

## 7. Model Parameters (Temperature, etc.)

### 7.1 Recommended Defaults (Code Benchmarks)

| Parameter    | Value | Reason |
|---|---|---|
| `temperature` | 0.0 | Deterministic output for reproducible benchmarks |
| `top_p`       | 1.0 | No nucleus sampling |
| `max_tokens`  | 4096 | Sufficient for code responses |
| `until`       | `[]` | No stop token (template controls end) |

### 6.2 Reasoning Tasks

| Parameter    | Value | Reason |
|---|---|---|
| `temperature` | 0.0 – 0.3 | Minimal sampling for stable reasoning chains |
| `top_p`       | 0.95 | Light diversity across multiple solution paths |
| `max_tokens`  | 8192 | Longer reasoning chains possible |

### 6.3 lm_eval Parameters

```python
# In _get_lmeval_params():
{
    "max_tokens": 4096,
    "temperature": 0.0,
    "top_p": 1.0,
    "until": [],
    "apply_chat_template": True  # lm_eval uses HF tokenizer template
}
```

---

## 7. Other Special Features

### 7.1 Multi-Token Prediction (MTP)

All Gemma-4 models have dedicated draft models for Speculative Decoding:
- Naming: `<target-model-id>-assistant`
- Advantage: Significantly faster inference without quality loss
- **Limitation (26B MoE):** At batch size 1, MTP may deliver **smaller** speedups on hardware without good parallelization, since different experts must be loaded.

### 7.2 QAT Models

Quantization-Aware Training (QAT) minimizes quality loss during quantization:
- `-qat-q4_0-gguf` for LM Studio / llama.cpp (1 file)
- `-qat-w4a16-ct` for vLLM / SGLang
- `-qat-mobile-transformers` for Edge/Mobile

Official HF collections: `collections/google/gemma-4-qat-q4-0`, `collections/google/gemma-4-qat-mobile`

### 7.3 Reasoning Models: Timeout ×2

Gemma-4 19B and 26B are classified as reasoning models (Thinking mode). In the benchmark pipeline they therefore require a **timeout factor ×2**:

- `gemma-4-19b-A4B-it-REAP-i1` → Timeout ×2
- `gemma-4-26b-A4B-it` (all quantizations) → Timeout ×2
- `gemma-4-12b-qat` → Timeout ×2 (Thinking-mode capable)

The setting is located in `model_manager.py`/`run_benchmarks.py` in the `reasoning_models` list or is controlled via `reasoning: thinking` in the registry.

### 7.4 Architecture Details (MoE)

| Model    | Total | Active | Ratio | Experts | Active | Shared | Attention |
|---|---|---|---|---|---|---|---|
| 19B REAP | 19B | ~4B | 4.75:1 | 90 (pruned) | 8 | 1 | Hybrid Sliding/Full (30 layers) |
| 26B A4B  | 26B | ~4B | 4.75:1 | 128 | 8 | 1 | Hybrid Sliding/Full (30 layers) |

### 7.5 Memory Requirements (VRAM)

| Model    | BF16   | Q4_0   | f16 KV-Cache (per token) |
|---|---|---|---|
| 12B      | 26.7 GB | 6.7 GB | ~3.5 MB/token (12B) |
| 26B A4B  | 57.7 GB | 14.4 GB | ~2.3 MB/token (26B MoE) |
| 31B      | 69.9 GB | 17.5 GB | ~4.2 MB/token (31B) |

KV-Cache in `f16` is the dominant VRAM factor at long contexts.

### 7.4 Context Length

| Model Group  | Max. Context |
|---|---|
| E2B, E4B     | 128K tokens |
| 12B, 26B A4B, 31B | 256K tokens |

In LM Studio, `model_max_length` must be checked (not automatically read from GGUF). The effective context length in the registry is calculated via the VRAM formula (`context_length` in `model_registry.yaml`).

### 7.5 Template Timeline

```
02.07.   12B MiniJinja template created
04.07.   All 3 templates in doc-git/; 7 tag corrections (<|turn|>system → <|turn>system)
04.07.   Thinking parameterizable (CLI, extra_body)
05.07.   HTTP 500 due to duplicate GGUF instance; enableThinking=false set
08.07.   Hub templates updated via Google Docs (26B: gated <|think|>)
09.07.   12B template synchronized with hub; backup template-config-backups_20260709/
11.07.   Gemma ignores enable_thinking=False → System prompt override as workaround
13.07.   Blueprint system: gemma_assistant / gemma_reasoning
```

---

## 8. Benchmark Performance (as of 2026-07-10, SS=20)

Weighting: Coding 35% | Math 25% | Agentic 25% | Knowledge 15%

| Rank | Model | VRAM | Overall | Coding | Knowledge | Math | Agentic |
|---|---|---|---|---|---|---|---|
| 1 | Gemma 4 26B UD@IQ3_S | 13.6 GB | **66%** | 70% | 73% | **55%** | 28% |
| 2 | Gemma 4 19B REAP@Q4_K_S | 11.3 GB | **55%** | 68% | 75% | 24% | 22% |
| 7 | Gemma 4 19B REAP (earlier quantization) | 12.5 GB | 50% | 60% | 62% | 28% | 77% |

Note: Agentic score of the 26B UD (28%) is low – other models (Devstral, Ministral) are better suited for agentic tasks.

---

## 9. Error Sources (Review Findings)

1. **Divergence of Jinja templates** (GGUF vs. Hub vs. doc-git vs. JSON config) – all 4 generations can exist in parallel.
2. **`promptTemplate` in JSON configs** – embedded copy of the template at the time can overwrite hub override (LMS priority unclear).
3. **`enable_thinking=False` is ignored** (07/11) – Workaround via system prompt override.
4. **lm_eval 0% problem** with `bartowski/google_gemma-4-26b-a4b-it` – no HF entry for lm_eval (GGUF only).


## Links
permit responsible [commercial use](https://ai.google.dev/gemma/terms),
download Gemma 4 models from [Hugging Face](https://huggingface.co/collections/google/gemma-4).

For more technical details on Gemma 4, see the
[Model Card](https://ai.google.dev/gemma/docs/core/model_card_4)
and
=> [Technical Report](https://goo.gle/Gemma4Report).
