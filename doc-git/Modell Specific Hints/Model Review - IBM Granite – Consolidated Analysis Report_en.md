# Granite Models – Consolidated Analysis Report, as of 2026-07-13

**Task/Prompt:
Repeat this research (previously on Gemma-4) on system prompts, chat templates, config and yaml files using the chat history from
"C:\Users\pskra\Python-Projekte\Benchmarks\Doku-intern\Konsolidierte_Compaction-Chronik_20260615-20260713.md" for the Granite models.
Cross-reference the data from the three ~\.lmstudio folders for .\models, .\hub and .internal\user-concrete-model-default-config as well as
the files in the doc-git folder with the entries in model_registry.yaml.

Analyze the relationships and create a consolidated summary report.
Also use the model cards from HuggingFace to help clarify open points.

## 1. Registry Entry Overview (7 entries)

| Registry Name                 | Publisher                 | Arch        | Template                            | Blueprint      | Capabilities (Actual) | Capabilities (HF Target) |
|-------------------------------|---------------------------|-------------|-------------------------------------|----------------|----------------------|--------------------------|
| `granite-4.0-h-tiny`          | ibm-granite               | Granite-4.0 | `granite-4.0-h-tiny_template.jinja` | `default_chat` | text                 | **coding** missing       |
| `granite-4.0-h-tiny-UD`       | unsloth                   | Granite-4.0 | `granite-4.0-h-tiny_template.jinja` | `default_chat` | text                 | **coding** missing       |
| `granite-4.1-8b`              |ibm-granite,lms-co.,unsloth| Granite-4.1 | `granite-4.1-30b_template.jinja`    | `default_chat` | text                 | **coding** missing       |
| `granite-4.1-8b-UD`           | unsloth                   | Granite-4.1 | `granite-4.1-30b_template.jinja`    | `default_chat` | text                 | **coding** missing       |
| `granite-4.1-30b`             | ibm-granite, mradermacher | Granite-4.1 | `granite-4.1-30b_template.jinja`    | `default_chat` | text                 | **coding** missing       |
| `granite-4.1-30b-i1`          | ibm-granite, mradermacher | Granite-4.1 | `granite-4.1-30b_template.jinja`    | `default_chat` | text                 | **coding** missing       |

---

## 2. Cross-Reference with HuggingFace Model Cards

### Granite-4.1-30b / Granite-4.1-8b
- **Per HF**: Decoder-only dense Transformer, GQA/RoPE/SwiGLU. 30B (64 layers) / 8B (40 layers). 131K Context. **Tool Calling, Coding, Instruction Following, RAG, FIM, JSON Output, multilingual (12 languages)**. Chat Template: `<|start_of_role|>` / `<|end_of_role|>` / `<|end_of_text|>`.
- **In Registry**: `arch: Granite-4.1` ✅; `capabilities: [text]` ⚠️ **coding missing**; `blueprint: default_chat` ⚠️ should rather be coding_agent or a granite-specific blueprint.

### Granite-4.0-h-tiny
- **Per HF**: MoE Hybrid Mamba-2/Transformer (9:1). **64 total experts, 6 active, 1 shared**. 7B total / 1B active. 128K Context. NoPE. **Tool Calling, Coding, Instruction Following, RAG, FIM, JSON, multilingual**. Chat Template identical.
- **In Registry**: `arch: Granite-4.0` ✅; `experts: 24` ❌ **should be 64**; `capabilities: [text]` ⚠️ **coding missing**; `notes:` says "24 Experts" ❌

---

## 3. System Prompt Quality (3 bugs found)

### Bug A: Wrong model name in JSON configs
Several configs have the **wrong model name** in the system prompt – a matching issue in the assemble script (Publisher-overwrite / normalize_match):

| Config file under                                     | System prompt says (wrong)                                                    | Should be                                |
|-------------------------------------------------------|-------------------------------------------------------------------------------|------------------------------------------|
| `ibm-granite/...granite-4.0-h-tiny-Q8_0.gguf.json`    | `You are **granite-4.0-h-tiny-UD** ... by **unsloth**`                        | `granite-4.0-h-tiny` by `ibm-granite`    |
| `ibm-granite/...granite-4.1-30b-Q3_K_S.gguf.json`     | `You are **granite-4.1-30b-i1** ... by **ibm-granite/mradermacher**`          | `granite-4.1-30b` by `ibm-granite`       |
| `ibm-granite/...granite-4.1-8b-Q8_0.gguf.json`        | `You are **granite-4.1-8b-UD** ... by **unsloth**`                            | `granite-4.1-8b` by `ibm-granite`        |
| `lmstudio-community/...granite-4.1-8b-Q8_0.gguf.json` | `You are **granite-4.1-8b-UD** ... by **unsloth**`                            | `granite-4.1-8b` by `lmstudio-community` |

**Root cause**: The `normalize_model_name()` match is too broad – "granite-4.0-h-tiny" also matches "granite-4.0-h-tiny-UD", and the first match wins.

### Bug B: No system prompt in `lmstudio-community/granite-4.1-8b-Q6_K.gguf.json`
This config has an empty `operation.fields` array – no system prompt was written at all.

---

## 4. Chat Template Situation

### Jinja templates in `doc-git/Jinja-Chat-Templates/`:
- `granite-4.1-30b_template.jinja` (71 lines) ✅ – correct
- `granite-4.0-h-tiny_template.jinja` (72 lines) ✅ – correct (minimal difference: comment + different condition on line 45)

### promptTemplate in JSON configs:
| Publisher    | Config                   | promptTemplate                         | Status                  |
|--------------|--------------------------|----------------------------------------|-------------------------|
| ibm-granite  | 4.0-h-tiny Q8_0          | ✅ embedded (3037 chars, correct)      | **Not yet removed**     |
| ibm-granite  | 4.1-30b Q3_K_S           | ✅ embedded (2925 chars, correct)      | **Not yet removed**     |
| ibm-granite  | 4.1-8b Q8_0              | ✅ embedded (2925 chars, correct)      | **Not yet removed**     |
| mradermacher | 4.1-30b-i1 Q3_K_S        | ✅ embedded (2925 chars, correct)      | **Not yet removed**     |
| unsloth      | 4.0-h-tiny-UD Q8_K_XL    | ❌ none                                | ✅                     |
| unsloth      | 4.1-8b(-UD) Q8/Q6        | ❌ none                                | ✅                     |
| lmstudio-community | 4.1-8b Q6/Q8       | ❌ none                                | ✅                     |

### Hub Jinja overrides (`hub/models/`):
**No Granite Jinja files found** in `hub/models/`. Unlike Gemma-4, no hub overrides exist. When `promptTemplate` is missing, LMS falls back directly to the GGUF-embedded template.

---

## 5. Blueprint Appropriateness

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

## 6. Other Anomalies

### Context length
- `granite-4.0-h-tiny Q8_0`: **1,048,576** (1M!) in JSON config → far above HF spec (128K). Likely LMS default, never set.
- `granite-4.1-30b Q3_K_S`: Not in the listed config fields – no contextLength set?
- HF specifies 128K (4.0) or 131K (4.1).

### `granite-20b-code-instruct` is deprecated
Per HF: "⚠️ **DEPRECATED** – not recommended for new projects." Should be marked with a note in the registry or removed.

---

## 7. Recommended Actions

| # | Action | Priority |
|---|---|---|
| 1 | Add `arch: Granite-20b-Code` to `granite-20b-code-instruct` in registry                              | 🔴 High   |
| 2 | Add `coding` to `capabilities` of all Granite-4.x models (via `classify_capabilities()` or manually) | 🔴 High   |
| 3 | Bugfix: Correct `normalize_model_name()` so that "granite-4.0-h-tiny" does not match                 | 🔴 High   |
|             "granite-4.0-h-tiny-UD" (exact match or suffix comparison)                                   |           |
| 4 | Correct `experts: 64` for `granite-4.0-h-tiny` (HF: 64 total / 6 active)                             | 🟡 Medium |
| 5 | Remove `promptTemplate` from the 4 remaining ibm-granite/mradermacher configs                        | 🟡 Medium |
|             (or replace with hub override)
| 6 | Create dedicated `granite_chat` blueprint + `granite_capabilities` module                            | 🟡 Medium |
| 7 | Mark `granite-20b-code-instruct` with `deprecated: true`                                             | 🟢 Low    |
| 8 | Set context lengths in configs to HF values (128K / 131K)                                            | 🟢 Low    |
| 9 | Re-assemble `lmstudio-community/granite-4.1-8b-Q6_K.gguf.json` without system prompt                 | 🟢 Low    |

Shall I execute the actions?
