# Thinking/Reasoning Configuration

Documents the control of Thinking mode in `custom_benchmark_v13.py:MODEL_CONFIG`.

## Mechanism

The system controls Thinking on three levels:

1. **Registry** (`model_registry.yaml:reasoning` field): Determines if a model is classified as reasoning (thinking=True, instruct=False). Populated automatically from GGUF `tokenizer.chat_template` via `registry_tool.py fill-reasoning` (part of `sync` pipeline).
2. **MODEL_CONFIG** (`custom_benchmark_v13.py:140-230`): Per-model defaults
3. **`--thinking` CLI flag**: Overrides via `REASONING_PATTERNS` to `True`

### API Control

The `enable_thinking` parameter is sent to LM Studio as `chat_template_kwargs.enable_thinking` at the top level of the JSON body.

> **⚠ `extra_body` nesting (historical, fixed 19.07.):** The custom pipeline used to nest `chat_template_kwargs` under `extra_body` (`body["extra_body"]["chat_template_kwargs"] = {...}`). This is WRONG for direct HTTP requests — `extra_body` is an OpenAI Python SDK concept that gets UNWRAPPED to the top level. In a manually-constructed JSON body, `extra_body` is just another unknown key that the server ignores. Fix: `body["chat_template_kwargs"] = kwargs`.
>
> The lm_eval path (`gen_kwargs["extra_body"]`) is correct because lm_eval passes gen_kwargs to the OpenAI SDK, which properly unwraps `extra_body` to the top level.
>
> **Bug symptom:** Qwen3.6-27B (thinking=ON by default in GGUF) always ran in thinking mode (6000+ tokens/task) because `enable_thinking=False` never reached the Jinja template renderer.

### Gemma 4 Special Case

Gemma 4 models ignore `enable_thinking=False` via API because `<|channel>thought` is hard-wired in the GGUF-Jinja template. Additional system prompt override in `generate_answer()` (`custom_benchmark_v13.py:659-663`):
```
"System: Do NOT use thinking or reasoning. Answer directly without <|channel>thought tags."
```

## Current Patterns (MODEL_TEMP_OVERRIDES)

Since v13, `max_tokens` is determined by the **benchmark category** (variant C+, p6):
- **coding**: 2048 | **math**: 8192 | **knowledge**: 2048 | **agentic**: 4096

The following overrides only override deviating category defaults:

| Pattern | enable_thinking | max_tokens (Override) | Special Notes |
|---------|----------------|----------------------|-------------|
| default | **False** | – | Default since 2026-07-11 |
| qwen3.5 | False | – | temperature=0.2, top_p=0.9, no_system_msg |
| qwen3.6 (alle) | **False** | – | GGUF-Default thinking=ON → explizit False seit 19.07. Catch-all für alle Qwen3.6-Derivate |
| gemma | False | – | + System prompt override |
| deepseek | **True** | 2048 | Only default with Thinking=on |
| gpt-oss | False | 4096 | stop: <\|return\|>, <\|call\|> |
| apriel | False | 4096 | |
| nemotron | False | 4096 | |
| falcon3 | False | – | |
| codestral | False | – | |
| devstral | False | – | |
| ernie | False | – | |
| rnj | False | – | THOUGHT:/RESPONSE: Parsing format (hub model.yaml) |
| python-coder | False | – | Catches qwen3-*-python-coder and similar |

> `–` in the max_tokens column = category default applies (no override).

## --thinking Flag Behavior (v13 Clarification)

The `--thinking` CLI flag has a limited effect since v13:

| Model group | --thinking effect | Reason |
|-------------|-------------------|------------|
| **Reasoning models** (registry `reasoning: thinking`) | ✅ Enables enable_thinking + Timeout ×2 | Native reasoning supported. Detection via `model_registry.yaml:reasoning` field (not keyword matching) |
| **Gemma 4** | ✅ Enables enable_thinking for MATH-500 | Gemma-4 template sets `<|channel>thought` |
| **Qwen3.6 (alle)** | ❌ Ignored (enable_thinking=False forced) | qwen3.6-27b aus REASONING_PATTERNS entfernt. `--thinking` hat keinen Effekt auf Qwen3.6 |
| **GPT-OSS** | ❌ Ignored (no thinking support) | GPT-OSS architecture has no thinking |
| **Qwen3.5** | ❌ Ignored (enable_thinking=False forced) | No thinking support |
| **Default (other models)** | ❌ No effect | enable_thinking=None (no extra_body) |

**Practical consequence:** `--thinking` should only be used with Gemma 4 and explicit reasoning models. 
For all other models it is a no-op.

## Model Classification (registry-based since 21.07.)

Since 21.07., `_is_reasoning_model()` no longer uses keyword matching but reads the `reasoning` field
from `model_registry.yaml`. Detection flow:

1. **GGUF header** (`_read_gguf_arch()`): Reads `tokenizer.chat_template`, returns `is_reasoning=True/False/None`
2. **fill-reasoning** (`registry_tool.py`): Writes `reasoning: thinking|instruct` into registry for entries without it
3. **Runtime** (`run_benchmarks_v13.py:_is_reasoning_model()`): Looks up `model_identifier` in registry,
   strips `@quant` suffix, returns `True` for `reasoning: thinking`, `False` otherwise

Fallback: If registry data is missing, prints a warning and returns `False`.

## MODEL_CONFIG in _get_lmeval_params (v13)

Since v13, the thinking parameters are no longer managed in MODEL_CONFIG (custom_benchmark_v13.py), 
but centrally in `_get_lmeval_params()` in `run_benchmarks_v13.py`. This avoids duplicate configuration 
between the custom pipeline and the lm_eval pipeline.

The model classification (_is_reasoning_model, _is_qwen3_6_model, _is_gptoss_model, _is_gemma_model, 
_is_qwen3_5_model) controls:
- enable_thinking (True/False/None)
- Category defaults: coding=2048, math=8192, knowledge=2048, agentic=4096
- temperature/top_p/min_p
- stop strings (until)
- no_system_msg

MODEL_CONFIG in custom_benchmark_v13.py now only contains the custom pipeline parameters.

## History

### 2026-07-21
- **Reasoning detection via Registry:** `_is_reasoning_model()` now reads `model_registry.yaml:reasoning` field. No longer keyword-based. Registry populated automatically from GGUF `tokenizer.chat_template` via `registry_tool.py fill-reasoning`.
- **BUGFIX `_read_gguf_arch()`:** Returns `is_reasoning = False` (not `None`) when no chat template found, preventing models without templates from incorrectly triggering the reasoning path.
- **BUGFIX @quant suffix:** Both `run_benchmarks_v13.py` and `custom_benchmark_v13.py` now strip `@quant` suffix before registry lookup, so `model_identifier=model@q4_0` matches registry key `publisher/model`.

### 2026-07-20
- **Native REST API (Option 2):** `custom_benchmark_v13.py:generate_answer()`: When `enable_thinking=False`, routes to `_generate_answer_native()` which uses LM Studio's native REST API (`/api/v1/chat`) with `reasoning: "off"` — a **dedicated, reliable** parameter that guarantees thinking is disabled. This is the fallback after `chat_template_kwargs` may be ignored by the OpenAI-compatible endpoint.
- **lm_eval double coverage:** `run_benchmarks_v13.py`: Added `gen_kwargs["reasoning"] = "off"` alongside existing `chat_template_kwargs.enable_thinking`, plus `"reasoning"` in both `gen_kwargs_keys` sets. If LM Studio's OpenAI endpoint forwards `reasoning`, this provides a second path to disable thinking.
- **Reason for native API:** The OpenAI-compatible endpoint (`/v1/chat/completions`) does not list `chat_template_kwargs` or `reasoning` as supported parameters. The native REST API (`/api/v1/chat`) has `reasoning: "off"|"low"|"medium"|"high"|"on"` as a first-class parameter.

### 2026-07-19
- **Bugfix Custom Pipeline:** `extra_body` nesting removed in `custom_benchmark_v13.py:generate_answer()` → `chat_template_kwargs` now at top level of HTTP body. Root cause: `extra_body` is an OpenAI SDK unwrap-mechanism, not a valid HTTP-level key — LM Studio ignored it silently. Betrifft DS1000, CoderEval.
- **Bugfix lm_eval Pipeline:** Selber Fix in `run_benchmarks_v13.py:_get_lmeval_params()` und `gen_kwargs_keys` — `extra_body` → `chat_template_kwargs` top-level. lm_eval verwendet `requests.post()` direkt (nicht OpenAI SDK), daher gleicher Bug. Betrifft MATH-500, ARC, HellaSwag, TruthfulQA.
- **Qwen3.6 Catch-All:** `MODEL_TEMP_OVERRIDES`: `"qwen3.6"` → `enable_thinking=False` für alle Qwen3.6-Modelle und Derivate.
- **REASONING_PATTERNS:** `qwen3.6-27b` entfernt — `--thinking` hat keinen Effekt auf Qwen3.6.

### 2026-07-11
- Default `enable_thinking`: None → **False** (previously: no extra_body sent)
- 8 new patterns added (apriel, nemotron, falcon3, codestral, devstral, ernie, rnj, python-coder)
- gpt-oss `enable_thinking`: None → False
- Gemma system prompt override implemented
- Diagnostic warning in `strip_thinking_tokens()` on complete thinking consume

### 2026-07-11 (Bugfixes HellaSwag/MathQA)
- **YAML max_gen_toks**: MathQA `20→512`, HellaSwag `20→100`
- **YAML Regex**: `[ABCDE]` → `[A-Ea-e]` (lowercase also matchable), same for HellaSwag
- **HellaSwag YAML**: `>-` (folded) → `|` (literal) for newlines in prompt
- **utils.py**: `process_docs()` regex more robust against comma values in choices
- **run_benchmarks_v13.py**: lm_eval parameters passed via `--gen_kwargs` instead of `--model_args`
  - Generation parameters (max_tokens, temperature, top_p, min_p, extra_body, until)
    now land in the API payload instead of the (ignored) constructor
  - `--model_args` now only contains constructor parameters (base_url, model, num_concurrent, max_gen_toks)
  - `eos_string=<|endoftext|>` only for GPT-OSS (no longer for all models)
- **HellaSwag Limit**: `min_limit=100` per benchmark config, overrides `sample_size`
