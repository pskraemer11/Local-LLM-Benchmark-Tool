# IBM Granite Models – Consolidated Model Review, updated 2026-09-20

**Task/Prompt:
Repeat this research (previously on Gemma-4) on system prompts, chat templates, config and yaml files using the chat history from
"C:\Users\pskra\Python-Projekte\Benchmarks\Doku-intern\Konsolidierte_Compaction-Chronik_20260615-20260713.md" for the Granite models.
Cross-reference the data from the three ~\.lmstudio folders for .\models, .\hub and .internal\user-concrete-model-default-config as well as
the files in the doc-git folder with the entries in model_registry.yaml.

This update adds a fresh review of the locally available Granite 4.2 model and preserves the earlier Granite 4.0/4.1 findings as historical context.

Analyze the relationships and create a consolidated summary report.
Also use the model cards from HuggingFace to help clarify open points.

## 1. Registry Entry Overview (7 entries)

| Registry Name           | Publisher                   | Arch        | Template                            | Blueprint              | Capabilities (Actual)  | Capabilities (HF Target) |
| ----------------------- | --------------------------- | ----------- | ----------------------------------- | ---------------------- | ---------------------- | ------------------------ |
| `granite-4.0-h-tiny`    | ibm-granite                 | Granite-4.0 | `granite-4.0-h-tiny_template.jinja` | `default_chat`         | text                   | **coding** missing       |
| `granite-4.0-h-tiny-UD` | unsloth                     | Granite-4.0 | `granite-4.0-h-tiny_template.jinja` | `default_chat`         | text                   | **coding** missing       |
| `granite-4.1-8b`        | ibm-granite,lms-co.,unsloth | Granite-4.1 | `granite-4.1-30b_template.jinja`    | `default_chat`         | text                   | **coding** missing       |
| `granite-4.1-8b-UD`     | unsloth                     | Granite-4.1 | `granite-4.1-30b_template.jinja`    | `default_chat`         | text                   | **coding** missing       |
| `granite-4.1-30b`       | ibm-granite, mradermacher   | Granite-4.1 | `granite-4.1-30b_template.jinja`    | `default_chat`         | text                   | **coding** missing       |
| `granite-4.1-30b-i1`    | ibm-granite, mradermacher   | Granite-4.1 | `granite-4.1-30b_template.jinja`    | `default_chat`         | text                   | **coding** missing       |
| `granite-4.2-30b-i1`    | mradermacher                | Granite-4.2 | `granite-4.1-30b_template.jinja`    | `granite_coding_agent` | coding, text, thinking | reviewed 2026-09-20      |

The reviewed local model is `mradermacher/granite-4.2-30b-i1@iq3_m` at `D:\LLM-Modelle\models\mradermacher\granite-4.2-30b-i1-GGUF\granite-4.2-30b.i1-IQ3_M.gguf`. It is a GGUF `IQ3_M` file with 13,066,761,632 bytes (about 13.1 GB decimal).

## Granite 4.2 Review

### Architecture, lineage and capabilities

Granite 4.2 is a decoder-only dense Transformer family in 3B, 8B and 30B sizes. The 30B model has 64 layers, GQA with 32 attention heads and 8 KV heads, RoPE, SwiGLU, RMSNorm and a native context length of 131,072 tokens. IBM describes the generation as post-trained from Granite 4.1 base models.

The local `IQ3_M` file is a quantized interleaved-imatrix variant of the 30B model. Quantization changes memory use and numerical fidelity, but not the model family, chat-template contract or upstream sampling recommendation.

The Registry classification is appropriate: `architecture_family: granite`, `reasoning: thinking`, `capabilities: coding, text`, `max_context_length: 131072`, and `blueprint: granite_coding_agent`. IBM additionally documents reasoning, math, tool calling, agentic workflows and multilingual dialogue. The model card mentions a 512K long-context extension, but it is not enabled in the local LM Studio configuration and is not used as the benchmark limit.

### Thinking modes and chat-template contract

IBM documents three modes selected through chat-template parameters:

| Mode         | Template setting                        | Expected behavior                        | Registry interpretation    |
| ------------ | --------------------------------------- | ---------------------------------------- | -------------------------- |
| Thinking     | `enable_thinking=True`                  | Full reasoning in `<think>...</think>`   | `reasoning: thinking`      |
| Non-thinking | `enable_thinking=False`                 | Direct answer without reasoning overhead | direct-answer runtime mode |
| Low effort   | `enable_thinking=True, low_effort=True` | Brief reasoning for simpler tasks        | optional runtime mode      |

The upstream examples end thinking output with a final answer and `<|im_end|>`. Tool calls use `<tool_call>...</tool_call>` and carry a function name plus parameter payload.

The repository's `granite-4.1-30b_template.jinja` correctly represents Granite role delimiters (`<|start_of_role|>`, `<|end_of_role|>`, `<|end_of_text|>`) and handles tools and tool responses. It does not visibly implement the Granite 4.2 `enable_thinking` and `low_effort` switches. The GGUF-embedded or LM Studio model-specific template therefore remains authoritative for Granite 4.2 until a dedicated 4.2 template is added and tested. No unverified 4.2 template was added in this review.

### Sampling recommendations

IBM explicitly recommends `temperature=1.0` and `top_p=0.95` across general chat, reasoning and tool-calling tasks and across serving backends. The current Registry entry contains these values for all six categories:

| Registry category | Temperature | Top-p | Evidence status                                     |
| ----------------- | ----------: | ----: | --------------------------------------------------- |
| normal            | 1.0         | 0.95  | direct IBM/Hugging Face example                     |
| coding            | 1.0         | 0.95  | derived from the documented all-task recommendation |
| knowledge         | 1.0         | 0.95  | derived from the documented all-task recommendation |
| agentic           | 1.0         | 0.95  | derived from thinking/tool-calling guidance         |
| math              | 1.0         | 0.95  | derived from the documented all-task recommendation |
| thinking          | 1.0         | 0.95  | direct IBM thinking example                         |

This same-value result is justified by an explicit manufacturer statement; it is not an undifferentiated fallback. The evidence remains category-labelled so a future profile-specific recommendation can replace only the affected category.

### Local LM Studio configuration

The associated configuration is `C:\Users\pskra\.lmstudio\.internal\user-concrete-model-default-config\mradermacher\granite-4.2-30b-i1-GGUF\granite-4.2-30b.i1-IQ3_M.gguf.json`.

| Setting           | Local value                     | Review assessment                                   |
| ----------------- | ------------------------------- | --------------------------------------------------- |
| Temperature       | `1.0`                           | matches IBM                                         |
| Top-p             | not explicitly present          | Registry/API should supply `0.95`                   |
| Top-k             | `20`                            | local runtime override, not an IBM recommendation   |
| Reasoning budget  | checked, `8192` tokens          | can truncate reasoning-heavy replies                |
| Context length    | `24576` (24K tokens)            | deliberate VRAM/performance limit below the Registry maximum |
| K-cache / V-cache | `q5_1` / `iq4_nl`               | local memory/performance choices                    |
| Offload ratio     | `1`                             | full GPU offload requested                          |
| System prompt     | generated Granite coding prompt | project runtime policy, not upstream model identity |

LM Studio settings must therefore be distinguished from Registry policy. `topK=20`, the 8,192-token reasoning budget and the 24K context limit are local runtime choices, while `temperature` and `top_p` are benchmark-policy values. The context was reduced because the full model context exceeded the 16 GB VRAM budget and made inference unacceptably slow.

### Local behavior smoke review

The model was queried through LM Studio's OpenAI-compatible endpoint at `http://127.0.0.1:1234/v1` with model id `granite-4.2-30b-i1`, `temperature=1.0`, `top_p=0.95` and deliberately small output limits. A direct-answer probe returned `READY` plus a separate `reasoning_content` field, confirming that native thinking is active in the serving path.

With an artificially small `max_tokens` budget, the model spent the output budget on reasoning and returned empty final `content` with `finish_reason: length`. This is an operational finding, not a model-quality score: benchmark runs must budget reasoning tokens or use a verified non-thinking template mode for direct-answer tasks. Math and coding probes likewise produced reasoning before their final answer, but were intentionally stopped by the small smoke-test budget and are not scored as benchmark results.

### Review result

Granite 4.2 is correctly onboarded for the reviewed local variant. No Registry correction is required from this review. The main implementation risk is template/runtime handling of `enable_thinking` and the distinction between reasoning budget and final-answer budget. A dedicated 4.2 template should only be introduced together with template rendering tests and a non-thinking/thinking API smoke test.

---

## 3. Historical Granite 4.0/4.1 Findings

### Granite-4.1-30b / Granite-4.1-8b
- **Per HF**: Decoder-only dense Transformer, GQA/RoPE/SwiGLU. 30B (64 layers) / 8B (40 layers). 131K Context. **Tool Calling, Coding, Instruction Following, RAG, FIM, JSON Output, multilingual (12 languages)**. Chat Template: `<|start_of_role|>` / `<|end_of_role|>` / `<|end_of_text|>`.
- **In Registry**: `arch: Granite-4.1` ✅; `capabilities: [text]` ⚠️ **coding missing**; `blueprint: default_chat` ⚠️ should rather be coding_agent or a granite-specific blueprint.

### Granite-4.0-h-tiny
- **Per HF**: MoE Hybrid Mamba-2/Transformer (9:1). **64 total experts, 6 active, 1 shared**. 7B total / 1B active. 128K Context. NoPE. **Tool Calling, Coding, Instruction Following, RAG, FIM, JSON, multilingual**. Chat Template identical.
- **In Registry**: `arch: Granite-4.0` ✅; `experts: 24` ❌ **should be 64**; `capabilities: [text]` ⚠️ **coding missing**; `notes:` says "24 Experts" ❌

---

## 4. Historical System Prompt Quality (3 bugs found)

### Bug A: Wrong model name in JSON configs
Several configs have the **wrong model name** in the system prompt – a matching issue in the assemble script (Publisher-overwrite / normalize_match):

| Config file under                                     | System prompt says (wrong)                                           | Should be                                |
| ----------------------------------------------------- | -------------------------------------------------------------------- | ---------------------------------------- |
| `ibm-granite/...granite-4.0-h-tiny-Q8_0.gguf.json`    | `You are **granite-4.0-h-tiny-UD** ... by **unsloth**`               | `granite-4.0-h-tiny` by `ibm-granite`    |
| `ibm-granite/...granite-4.1-30b-Q3_K_S.gguf.json`     | `You are **granite-4.1-30b-i1** ... by **ibm-granite/mradermacher**` | `granite-4.1-30b` by `ibm-granite`       |
| `ibm-granite/...granite-4.1-8b-Q8_0.gguf.json`        | `You are **granite-4.1-8b-UD** ... by **unsloth**`                   | `granite-4.1-8b` by `ibm-granite`        |
| `lmstudio-community/...granite-4.1-8b-Q8_0.gguf.json` | `You are **granite-4.1-8b-UD** ... by **unsloth**`                   | `granite-4.1-8b` by `lmstudio-community` |

**Root cause**: The `normalize_model_name()` match is too broad – "granite-4.0-h-tiny" also matches "granite-4.0-h-tiny-UD", and the first match wins.

### Bug B: No system prompt in `lmstudio-community/granite-4.1-8b-Q6_K.gguf.json`
This config has an empty `operation.fields` array – no system prompt was written at all.

---

## 5. Historical Chat Template Situation

### Jinja templates in `doc-git/Jinja-Chat-Templates/`:
- `granite-4.1-30b_template.jinja` (71 lines) ✅ – correct
- `granite-4.0-h-tiny_template.jinja` (72 lines) ✅ – correct (minimal difference: comment + different condition on line 45)

### promptTemplate in JSON configs:
| Publisher          | Config                | promptTemplate                   | Status              |
| ------------------ | --------------------- | -------------------------------- | ------------------- |
| ibm-granite        | 4.0-h-tiny Q8_0       | ✅ embedded (3037 chars, correct) | **Not yet removed** |
| ibm-granite        | 4.1-30b Q3_K_S        | ✅ embedded (2925 chars, correct) | **Not yet removed** |
| ibm-granite        | 4.1-8b Q8_0           | ✅ embedded (2925 chars, correct) | **Not yet removed** |
| mradermacher       | 4.1-30b-i1 Q3_K_S     | ✅ embedded (2925 chars, correct) | **Not yet removed** |
| unsloth            | 4.0-h-tiny-UD Q8_K_XL | ❌ none                           | ✅                   |
| unsloth            | 4.1-8b(-UD) Q8/Q6     | ❌ none                           | ✅                   |
| lmstudio-community | 4.1-8b Q6/Q8          | ❌ none                           | ✅                   |

### Hub Jinja overrides (`hub/models/`):
**No Granite Jinja files found** in `hub/models/`. Unlike Gemma-4, no hub overrides exist. When `promptTemplate` is missing, LMS falls back directly to the GGUF-embedded template.

---

## 6. Historical Blueprint Appropriateness

All Granite-4.x models use `default_chat` (3 text modules: safety + output_style). However, the HF cards demonstrate **significantly more capabilities**:
- Tool Calling (Function Calling)
- Coding (Code generation, completion, debugging)
- RAG / long contexts (128K-131K)
- Instruction Following
- Multilingual (12 languages)
- JSON Output / Structured Output

The `default_chat` blueprint does not cover these specialized capabilities. **Recommendation**: Create a dedicated `granite_chat` blueprint (analogous to `gemma_assistant`) with:
- `coding` in capabilities (all Granite models)
- A `granite_capabilities` module (Function Calling, Coding, RAG, long context, multilingual)

---

## 7. Historical Other Anomalies

### Context length
- `granite-4.0-h-tiny Q8_0`: **1,048,576** (1M!) in JSON config → far above HF spec (128K). Likely LMS default, never set.
- `granite-4.1-30b Q3_K_S`: Not in the listed config fields – no contextLength set?
- HF specifies 128K (4.0) or 131K (4.1).

### `granite-20b-code-instruct` is deprecated
Per HF: "⚠️ **DEPRECATED** – not recommended for new projects." Should be marked with a note in the registry or removed.

---

## 8. Historical Recommended Actions

| #                                                          | Action                                                                                               | Priority |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | -------- |
| 1                                                          | Add `arch: Granite-20b-Code` to `granite-20b-code-instruct` in registry                              | 🔴 High   |
| 2                                                          | Add `coding` to `capabilities` of all Granite-4.x models (via `classify_capabilities()` or manually) | 🔴 High   |
| 3                                                          | Bugfix: Correct `normalize_model_name()` so that "granite-4.0-h-tiny" does not match                 | 🔴 High   |
| "granite-4.0-h-tiny-UD" (exact match or suffix comparison) |                                                                                                      |          |
| 4                                                          | Correct `experts: 64` for `granite-4.0-h-tiny` (HF: 64 total / 6 active)                             | 🟡 Medium |
| 5                                                          | Remove `promptTemplate` from the 4 remaining ibm-granite/mradermacher configs                        | 🟡 Medium |
| (or replace with hub override)                             |                                                                                                      |          |
| 6                                                          | Create dedicated `granite_chat` blueprint + `granite_capabilities` module                            | 🟡 Medium |
| 7                                                          | Mark `granite-20b-code-instruct` with `deprecated: true`                                             | 🟢 Low    |
| 8                                                          | Set context lengths in configs to HF values (128K / 131K)                                            | 🟢 Low    |
| 9                                                          | Re-assemble `lmstudio-community/granite-4.1-8b-Q6_K.gguf.json` without system prompt                 | 🟢 Low    |

These actions belong to the earlier Granite 4.0/4.1 review and are retained as historical follow-up items. They are not claims that the current Granite 4.2 review changed those files.

## 9. Sources for the Granite 4.2 Update

- [IBM Granite 4.2 documentation](https://www.ibm.com/granite/docs/models/granite4-2) – architecture, thinking modes, tool calling, and the `temperature=1.0` / `top_p=0.95` recommendation.
- [IBM Granite 4.2 language-model repository](https://github.com/ibm-granite/granite-4.2-language-models) – official model family, model sizes, lineage and inference examples.
- [IBM Granite 4.2 30B model card](https://huggingface.co/ibm-granite/granite-4.2-30b) – model design, context length, capabilities and serving guidance.
- [IBM Granite 4.2 GGUF repository](https://huggingface.co/ibm-granite/granite-4.2-30b-GGUF) – official quantization size comparison and GGUF family reference.
