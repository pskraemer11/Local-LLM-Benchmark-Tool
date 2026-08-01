# Thinking/Reasoning Configuration

Documents the control of Thinking mode in `custom_benchmark.py:MODEL_CONFIG`.

## Mechanism

The system controls Thinking on three levels:

1. **Registry** (`model_registry.yaml:reasoning` field): Determines if a model is classified as reasoning (thinking=True, instruct=False). 
                Populated automatically from GGUF `tokenizer.chat_template` via `registry_tool.py fill-reasoning` (part of `sync` pipeline).
2. **MODEL_CONFIG** (`custom_benchmark.py:140-230`): Per-model defaults
3. **`--thinking` CLI flag**: Overrides via `REASONING_PATTERNS` to `True`

### API Control: native REST-API versus OpenAI compatible API, model specific hints 

The system uses a **3-level strategy** for controlling thinking mode:

| Level | Model         | Parameter                                          | API                                      |
|-------|---------------|----------------------------------------------------|------------------------------------------|
|   1   | gpt-oss       | `reasoning: {"effort": "low"}`                     | Native REST `/api/v1/chat`               |
|   2   | Qwen3/Qwen3.5 | `chat_template_kwargs: {"enable_thinking": false}` | OpenAI-kompatibel `/v1/chat/completions` |
|   3   | Andere        | Keine Thinking-Steuerung                           |      -                                   |

> **⚠ `chat_template_kwargs` ist KEIN OpenAI-Standard-Parameter.**
> 
> Er wird nur von **Qwen-Modellen** (Qwen3, Qwen3.5) unterstuetzt. Die Quelle ist eine undokumentierte 
> LM-Studio-Extension, das auf HuggingFace transformers `chat_template_kwargs` basiert.
> 
> **Quelle:** https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1573
> 
> **Wichtig:** Fuer Gemma-4 funktioniert `chat_template_kwargs` NICHT - dort wird ein
>              System-Prompt-Override verwendet (siehe unten).

> **⚠ `extra_body` nesting (historical, fixed 19.07.):** The custom pipeline used to nest `chat_template_kwargs` under 
>  `extra_body` (`body["extra_body"]["chat_template_kwargs"] = {...}`). 
> This is WRONG for direct HTTP requests — `extra_body` is an OpenAI Python SDK concept that gets UNWRAPPED to the top level. 
>  In a manually-constructed JSON body, `extra_body` is just another unknown key that the server ignores. Fix: `body["chat_template_kwargs"] = kwargs`.
>
> The lm_eval path (`gen_kwargs["extra_body"]`) is correct because lm_eval passes gen_kwargs to the OpenAI SDK, which properly unwraps `extra_body` to the top level.
>
> **Bug symptom:** Qwen3.6-27B (thinking=ON by default in GGUF) always ran in thinking mode (6000+ tokens/task) because `enable_thinking=False` 
>                   never reached the Jinja template renderer.

### Reasoning-Effort Parameter for GPT-OSS models

Fuer *gpt-oss-Modelle* wird `reasoning.effort` verwendet (nicht `chat_template_kwargs`):

| Effekt     | Bedeutung                                        |
|------------|--------------------------------------------------|
| `"off"`    | Kein Reasoning (nicht unterstuetzt von gpt-oss)  |
| `"low"`    | Minimales Reasoning (schneller, aber schlechter) |
| `"medium"` | Mittleres Reasoning (langsamer, aber besser)     |
| `"hoch"`   | Maximales Reasoning (hohe Tokenzahl, je          |
|                           nach lokaler Hardware sehr langsam) |

**Quelle:** https://lmstudio.ai/docs/developer/rest/chat

### Gemma-4 Special Case

Gemma-4 models ignore `enable_thinking=False` via API because `<|channel>thought` is hard-wired in the GGUF-Jinja template. 

Additional system prompt override in `generate_answer()` (`custom_benchmark.py:659-663`):
```
"System: Do NOT use thinking or reasoning. Answer directly without <|channel>thought tags."
```

## Current Patterns (MODEL_TEMP_OVERRIDES)

Since v13, `max_tokens` is determined by the **benchmark category** (variant C+, p6):
- **coding**: 2048 | **math**: 4096 | **knowledge**: 2048 | **agentic**: 4096

The following overrides only override deviating category defaults:

| Pattern        |enable_thinking| max_tokens | Special Notes                                       |
|                                | (Override) |                                                     |
|----------------|---------------|------------|-----------------------------------------------------|
| default        |  *False*      |      –     | Default since 2026-07-11                            |
| qwen3.5        |   False       |      –     | temperature=0.2, top_p=0.9, no_system_msg           |
| qwen3.6 (alle) |  *False*      |      –     | GGUF-Default thinking=ON → explizit False seit 19.07.|
                                                      Catch-all für alle Qwen3.6-Derivate           |
| gemma          |   False       |      –     | + System prompt override                            |
| deepseek       |  *True*       |    2048    | Only default with Thinking=on                       |
| gpt-oss        |   False       |    4096    | stop: <\|return\|>, <\|call\|>, reasoning_effort=low |
| apriel         |   False       |    4096    |                                                     |
| nemotron       |   False       |    4096    |                                                     |
| falcon3        |   False       |      –     |                                                     |
| codestral      |   False       |      –     |                                                     |
| devstral       |   False       |      –     |                                                     |             
| ernie          |   False       |      –     |                                                     |
| rnj            |   False       |      –     | THOUGHT:/RESPONSE: Parsing format (hub model.yaml)  |
| python-coder   |   False       |      –     | Catches qwen3-python-coder and similar              |

> `–` in the max_tokens column = category default applies (no override).

## Stop-String Trap: `"\n```"` breaks Code-Block Opening (2026-08-01)

**Symptom:** deepseek-r1-distill-qwen-14b scored 0% on DS1000 and CoderEval (20/20 `No code generated`,
`tokens_out=0`, reasoning 237–1344 tokens) despite prompt hardening (`_THINKING_CODE_ONLY_SUFFIX`).

**Root cause:** `STOP_TOKENS_CODING` contained `"\n```"`. DeepSeek R1 Distill starts its final answer
(after thinking) with `\n```python` — i.e. the **opening** of a Markdown code block. LM Studio applies
stop strings eagerly, so the answer was cut off right after the block opened → nearly empty content.

Why only DeepSeek? Other models (Qwen3, LLaMA, ...) don't begin answers with `\n```; DeepSeek R1 Distill
does, because the final answer starts with a code block (suffix forces this).

**Live verification** (01.08.2026, direct API to localhost:1234, same prompt as benchmark run):

| Stop list                          | content_len | Result                                  |
|------------------------------------|-------------|-----------------------------------------|
| `["\n```", "\n# Task", ...]` (alt) | 1 (`"\n"`) | finish_reason=stop, code killed at open |
| no `\n``` ` stop                   | 338         | full code block                         |
| `["\n```\n", "\n# Task", ...]`     | 338         | full code block, stops at **close**     |

**Fix:** `custom_benchmark.py:192` — `"\n```"` → `"\n```\n"`. The trailing newline means the stop only
matches the **closing** fence (`\n```\n`, line end) and never the opening (`\n```python`).

**Result (verification run, seed 42, sample-size 20):** DS1000 **7/20 = 35%**, CoderEval **8/12 = 67%**
(previously 0/0). No more `No code generated`; remaining failures are real code-quality issues.
Consistent with older SS30 runs from 23./24.07. (40% / 58%) — the 0% runs were a regression, not model failure.

> **General rule:** stop strings with ` ``` ` must include the trailing `\n` (`\n```\n`) for any
> thinking/reasoning model whose final answer starts with a code block. The same applies to future
> stop-list additions for other code benchmarks.

## --thinking Flag Behavior (v13 Clarification)

The `--thinking` CLI flag has a limited effect since v13:

| Model group                | --thinking effect                         | Reason                                                                                  |
|----------------------------|-------------------------------------------|-----------------------------------------------------------------------------------------|
| **Reasoning models**       | ✅ Enables enable_thinking + Timeout ×2   | Native reasoning supported. Detection via `model_registry.yaml:reasoning` field         |
|  (registry `reasoning: thinking`)                                      |          (not keyword matching) 
| **Gemma 4**                | ✅ Enables enable_thinking for MATH-500   | Gemma-4 template sets `<|channel>thought`                                               |
| **Qwen3.6 (alle)**         | ❌ Ignored (enable_thinking=False forced) | qwen3.6-27b aus REASONING_PATTERNS entfernt. `--thinking` hat keinen Effekt auf Qwen3.6 |
| **GPT-OSS**                | ❌ Ignored (no thinking support)          | GPT-OSS architecture has no thinking                                                    |
| **Qwen3.5**                | ❌ Ignored (enable_thinking=False forced) | No thinking support                                                                     |
| **Default (other models)** | ❌ No effect                              | enable_thinking=None (no extra_body)                                                    |

**Practical consequence:** `--thinking` should only be used with Gemma 4 and explicit reasoning models. 
For all other models it is a no-op.

## Model Classification (registry-based since 21.07.)

Since 21.07., `_is_reasoning_model()` no longer uses keyword matching but reads the `reasoning` field
from `model_registry.yaml`. Detection flow:

1. **GGUF header** (`_read_gguf_arch()`): Reads `tokenizer.chat_template`, returns `is_reasoning=True/False/None`
2. **fill-reasoning** (`src/registry_tool.py`): Writes `reasoning: thinking|instruct` into registry for entries without it
3. **Runtime** (`run_benchmarks.py:_is_reasoning_model()`): Looks up `model_identifier` in registry,
   strips `@quant` suffix, returns `True` for `reasoning: thinking`, `False` otherwise

Fallback: If registry data is missing, prints a warning and returns `False`.

## MODEL_CONFIG in _get_lmeval_params (v13)

Since v13, the thinking parameters are no longer managed in MODEL_CONFIG (custom_benchmark.py), 
but centrally in `_get_lmeval_params()` in `src/run_benchmarks.py`. This avoids duplicate configuration 
between the custom pipeline and the lm_eval pipeline.

The model classification (_is_reasoning_model, _is_qwen3_6_model, _is_gptoss_model, _is_gemma_model, 
_is_qwen3_5_model) controls:
- enable_thinking (True/False/None)
- Category defaults: coding=2048, math=4096, knowledge=2048, agentic=4096
- temperature/top_p/min_p
- stop strings (until)
- no_system_msg

MODEL_CONFIG in custom_benchmark.py now only contains the custom pipeline parameters.

## History

### 2026-08-01
- **BUGFIX stop-string kills code-block opening:** `STOP_TOKENS_CODING` (`custom_benchmark.py:192`)
  `"\n```"` → `"\n```\n"`. Root cause: deepseek-r1-distill-qwen-14b begins its final answer with
  `\n```python` (opening fence); the old stop matched the opening and aborted the response after ~0 tokens
  (`No code generated`). Verified live (content_len 1 vs 338) and by re-run: DS1000 35%, CoderEval 67%
  (seed 42, SS20) instead of 0%/0%. See "Stop-String Trap" section above.
- **Prompt hardening verified:** `_THINKING_CODE_ONLY_SUFFIX` (`custom_benchmark.py:1541`) is effective —
  with it the model returns ONLY a ` ```python ` block. The 0% results were caused by the stop string,
  not by the suffix or thinking mode itself.

### 2026-07-31
- **Registry-driven enable_thinking (general solution):** `get_model_config()` now reads `reasoning: thinking`
  from `model_registry.yaml` and forces `enable_thinking=True` — no `--thinking` flag needed. Explicit
  `MODEL_TEMP_OVERRIDES` entries still win (kimi/qwen3.5/qwen3.6/gemma keep `enable_thinking=False` as
  experimental workarounds). Affects both pipelines (custom + lm_eval via `_get_evaluation_parameters`).
  Fixes deepseek-r1-distill-qwen-14b (registry `reasoning: thinking`, Qwen2 arch): quality over runtime.
- **Qwen template detection broadened:** `_uses_qwen_template()` replaces the qwen3/qwen-3 name checks in
  `generate_answer()` — covers Qwen-based distills (deepseek-r1-distill-qwen-14b) for
  `chat_template_kwargs.enable_thinking`.
- **Streaming reasoning deltas:** `_extract_reasoning_delta()` handles both formats:
  - `delta.reasoning_content` — DeepSeek R1, LM Studio 0.3.9+ (App Settings > Developer
    "Separate reasoning_content in Chat Completion responses"; blog/lmstudio-v0.3.9)
  - `delta.reasoning` — gpt-oss, LM Studio 0.3.23+ (o3-mini-conform; docs/developer/api-changelog
    "Reasoning content and tool-calling reliability")
  Non-streaming fallback already read both `message.reasoning` and `message.reasoning_content`.

### 2026-07-28
- **chat_template_kwargs nur fuer Qwen:** Parameter wird nur noch fuer Qwen3/Qwen3.5 Modelle verwendet. Quelle: https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1573
- **reasoning_effort angepasst:** gpt-oss reasoning_effort von "medium" auf "low" geaendert (schnellere Antworten, weniger Fehler)
- **MATH max_tokens reduziert:** 8192 → 4096 (reicht fuer die meisten MATH-Aufgaben, ca. 2x schneller)
- **Dokumentation ergaenzt:** Quellen und Einschraenkungen fuer chat_template_kwargs und reasoning_effort klar dokumentiert

### 2026-07-21
- **Reasoning detection via Registry:** `_is_reasoning_model()` now reads `model_registry.yaml:reasoning` field. No longer keyword-based. Registry populated automatically from GGUF `tokenizer.chat_template` via `registry_tool.py fill-reasoning`.
- **BUGFIX `_read_gguf_arch()`:** Returns `is_reasoning = False` (not `None`) when no chat template found, preventing models without templates from incorrectly triggering the reasoning path.
- **BUGFIX @quant suffix:** Both `src/run_benchmarks.py` and `src/custom_benchmark.py` now strip `@quant` suffix before registry lookup, so `model_identifier=model@q4_0` matches registry key `publisher/model`.

### 2026-07-20
- **Native REST API (Option 2):** `custom_benchmark.py:generate_answer()`: When `enable_thinking=False`, routes to `_generate_answer_native()` which uses LM Studio's native REST API (`/api/v1/chat`) with `reasoning: "off"` — a **dedicated, reliable** parameter that guarantees thinking is disabled. This is the fallback after `chat_template_kwargs` may be ignored by the OpenAI-compatible endpoint.
- **lm_eval double coverage:** `src/run_benchmarks.py`: Added `gen_kwargs["reasoning"] = "off"` alongside existing `chat_template_kwargs.enable_thinking`, plus `"reasoning"` in both `gen_kwargs_keys` sets. If LM Studio's OpenAI endpoint forwards `reasoning`, this provides a second path to disable thinking.
- **Reason for native API:** The OpenAI-compatible endpoint (`/v1/chat/completions`) does not list `chat_template_kwargs` or `reasoning` as supported parameters. The native REST API (`/api/v1/chat`) has `reasoning: "off"|"low"|"medium"|"high"|"on"` as a first-class parameter.

### 2026-07-19
- **Bugfix Custom Pipeline:** `extra_body` nesting removed in `custom_benchmark.py:generate_answer()` → `chat_template_kwargs` now at top level of HTTP body. Root cause: `extra_body` is an OpenAI SDK unwrap-mechanism, not a valid HTTP-level key — LM Studio ignored it silently. Betrifft DS1000, CoderEval.
- **Bugfix lm_eval Pipeline:** Selber Fix in `run_benchmarks.py:_get_lmeval_params()` und `gen_kwargs_keys` — `extra_body` → `chat_template_kwargs` top-level. lm_eval verwendet `requests.post()` direkt (nicht OpenAI SDK), daher gleicher Bug. Betrifft MATH-500, ARC, HellaSwag, TruthfulQA.
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
- **run_benchmarks.py**: lm_eval parameters passed via `--gen_kwargs` instead of `--model_args`
  - Generation parameters (max_tokens, temperature, top_p, min_p, extra_body, until)
    now land in the API payload instead of the (ignored) constructor
  - `--model_args` now only contains constructor parameters (base_url, model, num_concurrent, max_gen_toks)
  - `eos_string=<|endoftext|>` only for GPT-OSS (no longer for all models)
- **HellaSwag Limit**: `min_limit=100` per benchmark config, overrides `sample_size`
