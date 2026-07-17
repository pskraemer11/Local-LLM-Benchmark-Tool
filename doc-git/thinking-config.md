# Thinking/Reasoning Configuration

Documents the control of Thinking mode in `custom_benchmark_v13.py:MODEL_CONFIG`.

## Mechanism

The system controls Thinking on two levels:

1. **MODEL_CONFIG** (`custom_benchmark_v13.py:140-230`): Per-model defaults
2. **`--thinking` CLI flag**: Overrides via `REASONING_PATTERNS` to `True`

### API Control

The `enable_thinking` parameter is sent to LM Studio as `extra_body.chat_template_kwargs.enable_thinking`.

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
| qwen3.6 | False | 8192 | Thinking consumes budget → 0% Score |
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
| **Reasoning models** (name contains "reasoning"/"think"/"r1"/"rnj") | ✅ Enables enable_thinking + Timeout ×2 | Native reasoning supported |
| **Gemma 4** | ✅ Enables enable_thinking for MATH-500 | Gemma-4 template sets `<|channel>thought` |
| **Qwen3.6** | ❌ Ignored (enable_thinking=False forced) | Thinking tokens block token budget → 0% Score |
| **GPT-OSS** | ❌ Ignored (no thinking support) | GPT-OSS architecture has no thinking |
| **Qwen3.5** | ❌ Ignored (enable_thinking=False forced) | No thinking support |
| **Default (other models)** | ❌ No effect | enable_thinking=None (no extra_body) |

**Practical consequence:** `--thinking` should only be used with Gemma 4 and explicit reasoning models. 
For all other models it is a no-op.

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
