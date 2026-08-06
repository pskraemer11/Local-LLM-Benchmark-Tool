# Qwen3.6 / REAP: Native-API-Fix (Stop-Tokens + Reasoning)

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
