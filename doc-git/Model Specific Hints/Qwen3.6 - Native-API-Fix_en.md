# Qwen3.6 / REAP: Native-API-Fix (Stop-Tokens + Reasoning)

## Current Registry and Blueprint Review (2026-09-20)

The earlier API-fix description remains relevant, but it is no longer the complete Qwen3.6 model-family documentation. Qwen3.6 models are classified in the Registry as the `qwen35` or `qwen35moe` architecture families, depending on whether the downloaded variant is dense/MTP or MoE/REAP. They use the `reasoning_coding` blueprint and are treated as dual-mode reasoning models rather than as permanently non-thinking instruct models.

| Model group         | Architecture family | Registry reasoning | Blueprint          | Local/runtime implication                                               |
| ------------------- | ------------------- | ------------------ | ------------------ | ----------------------------------------------------------------------- |
| Qwen3.6 dense / MTP | `qwen35`            | `thinking`         | `reasoning_coding` | thinking can be enabled or disabled by the request/template             |
| Qwen3.6 MoE / REAP  | `qwen35moe`         | `thinking`         | `reasoning_coding` | same dual-mode contract; quantization does not change the family policy |

The central correction is that `enable_thinking=False` is a task- or request-level choice for direct coding/instruct execution. It must not be documented as an intrinsic property of all Qwen3.6 models. When the benchmark deliberately selects the LM Studio Native API for non-thinking generation, the fixes below ensure that the API route receives both the reasoning-off instruction and the model stop token.

## Current Sampling Policy

The current `model_registry.yaml` differentiates the benchmark categories instead of copying one value into every profile. The active Qwen3.6 entries use the following family-level policy:

| Category  | Temperature | Top-p | Top-k | Min-p | Evidence/status                                                                                         |
| --------- | ----------: | ----: | ----: | ----: | ------------------------------------------------------------------------------------------------------- |
| coding    | 0.7         | 0.80  | 20    | 0.0   | Registry value derived from Qwen instruct/coding guidance                                               |
| knowledge | 0.7         | 0.80  | 20    | 0.0   | Registry value derived from the non-thinking/instruct profile                                           |
| agentic   | 0.6         | 0.95  | 20    | 0.0   | Registry value derived from precise/agentic guidance                                                    |
| math      | 0.7         | 0.80  | 20    | 0.0   | deliberately aligned with the precise coding/instruct path where no separate math profile is documented |
| thinking  | 0.6         | 0.95  | 20    | 0.0   | direct thinking profile where available                                                                 |

The source material distinguishes precise coding/thinking from ordinary instruct mode. The repository's sampling research records whether a category is direct or derived in `sampling_category_status`; this is the reason the YAML contains differentiated categories even when several values happen to be close. `presence_penalty` and `repetition_penalty` remain source/runtime-specific fields and are not silently invented for Registry profiles that do not define them.

## Blueprint and API Contract

`reasoning_coding` supplies coding principles, safety handling and technical output style without injecting a generic chain-of-thought scaffold. Reasoning is controlled by the model's native/template/API mechanism. The Qwen3.6 family has no separate repository Jinja template in `doc-git/Jinja-Chat-Templates`; the GGUF-embedded or LM Studio-provided Qwen template remains authoritative.

For the non-thinking Native API path, the implementation must preserve:

- `reasoning: "off"` on the request, with a compatibility retry when the endpoint rejects it;
- `<|im_end|>` as a stop token for direct answers and coding output;
- a retry path that can remove unsupported `stop` and/or `reasoning` fields without losing the request;
- a clear distinction between Native API `/api/v1/chat` and OpenAI-compatible `/v1/chat/completions` behavior.

The current Registry/blueprint classification and the Native-API fixes therefore address different layers: the Registry chooses the model policy and blueprint, while `custom_benchmark.py` adapts the request to the selected LM Studio API route.

Sources: [Qwen3.6 model card](https://huggingface.co/Qwen/Qwen3.6-27B), [Qwen3.6 README](https://huggingface.co/Qwen/Qwen3.6-27B/raw/main/README.md), and the project sources `doc-git/model_registry.yaml`, `doc-git/blueprint_definitions.yaml`, `src/assemble_blueprint.py` and `src/custom_benchmark.py`.

## Problem
Qwen3.6 27B and Qwen3.6 28B REAP performed worse in v13 than before.

## Root Cause
All Qwen3.6 models have the override `enable_thinking: False` in `benchmark_config.py`. Since v13 this routes through **`_generate_answer_native()`** (LM Studio Native API `/api/v1/chat`) instead of the OpenAI-compatible API (`/v1/chat/completions`). The Native API had three deficiencies:

### 1. No stop tokens ❌
`_generate_answer_native()` did not accept/send a `stop` parameter. Qwen models need `<|im_end|>` as stop token, otherwise they generate far beyond the code boundaries → wasted token budget, low scores.

**Fix (24.07.2026):**
- `_generate_answer_native()` extended with `stop: Optional[list[str]]`
- Body builds the `stop` field when `stop` is set
- Fallback: If the Native API does not support `stop` → retry without `stop`

### 2. `reasoning: "off"` only for thinking models ❌
`reasoning: "off"` was only set when `_model_supports_reasoning()` → True (i.e. `reasoning: thinking` in the registry). REAP models have `reasoning: instruct` → no `reasoning: "off"` → thinking stayed enabled → token budget exhausted.

**Fix:** `reasoning: "off"` is now **always** set, because the Native API route is only taken when `enable_thinking=False`. The existing fallback (retry without reasoning) catches models that do not support the parameter.

### 3. No fallback for stop-token errors ❌
The Native API retry logic only handled `reasoning` errors, not `stop` errors.

**Fix:** New helper function `_retry_native()` extracted. Retry chain: stop → reasoning.

## Changed file
`custom_benchmark.py`:
- `_retry_native()` – new helper function (line 760)
- `_generate_answer_native()` – `stop` parameter + `reasoning: "off"` always (line 789)
- `generate_answer()` – `stop=stop` passed to Native API (line 720)

See also: `GPT-OSS-20b_Harmony-Template-Injection.md` (top_k=0 fix) – similar API issue.
