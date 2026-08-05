# Thinking/Reasoning Configuration

Documents how Thinking mode is controlled across the benchmark pipelines:
`benchmark_config.py:get_model_config()` (runtime config), `assemble_blueprint.py:classify_reasoning()`
(blueprint classification) and `model_registry.yaml` (single source of truth).

## Mechanism

Thinking is controlled on three levels:

1. **Registry** (`model_registry.yaml:reasoning` field): Determines whether a model is a reasoning model (`thinking`) or not (`instruct`). 
    Populated automatically from GGUF `tokenizer.chat_template` (Source of Truth for architecture) via `registry_tool.py fill-reasoning` (part of the `sync` pipeline).
    Existing values are **never overwritten** (`skipped_has`) — manual corrections persist.
    
2. **`get_model_config()`** (`benchmark_config.py:495`): Since 05.08. the **LMS JSON-Config is the ONLY source**
    (reads `operation.fields` from `user-concrete-model-default-config` — matches the GUI). `BENCHMARK_CATEGORY_DEFAULTS`
    serve only as fallback when no JSON-Config exists. `MODEL_TEMP_OVERRIDES` and the Knowledge-Floor were **removed**
    (no Python override anymore). Used by both pipelines (custom via `custom_benchmark.py`, lm_eval via `run_benchmarks.py:_get_evaluation_parameters`).
    
3. **`--thinking` CLI flag**: Forces `enable_thinking=True` for models matching `REASONING_PATTERNS`.

### Priority chain in `get_model_config()` (verified 05.08. against code)

```
1. LM Studio JSON-Config (operation.fields)   (enableThinking / budgetTokens / parsing.enabled)
2. BENCHMARK_CATEGORY_DEFAULTS[category]      (fallback ONLY if no JSON-Config exists; enable_thinking=False)
3. --thinking flag + REASONING_PATTERNS       (force enable_thinking=True)
Result contains _source ("lms-json" | "category-default") for display.
```

Thinking detection from JSON-Config (`benchmark_config.py:448-462`):
`enableThinking` > `budgetTokens` (checked + value>0) > `parsing.enabled`.

### Classification in `assemble_blueprint.py:classify_reasoning()`

```
1. existing_reasoning (registry field / user override)     → returned as-is
2. arch → _ARCH_REASONING_MAP                              → thinking|instruct|none
3. NON_REASONING_MODELS keyword blacklist                  → none
4. REASONING_KEYWORDS keyword whitelist                    → thinking
5. default                                                 → instruct
```

`_ARCH_REASONING_MAP` (order matters — `qwen35*` must be checked before `qwen3*`):

| Arch key      | Default         | Notes                                                   |
|---------------|-----------------|---------------------------------------------------------|
| `qwen35moe`   | `thinking`      | Qwen3.6 MoE — dual-mode, default thinking               |
| `qwen35`      | `thinking`      | Qwen3.6 — dual-mode, default thinking                   |
| `qwen3moe`    | `instruct`      | Qwen3 MoE (Coder/Instruct) — except "thinking" in name  |
| `qwen3`       | `instruct`      | Qwen3 — except "thinking" in name                       |
| `deepseek2`   | `thinking`      |                                                         |
| `kimi-linear` | `thinking`      |                                                         |
| `gpt-oss`     | `thinking`      |                                                         |
| `nomic-bert`  | `none`          |                                                         |
| `flux`        | `none`          |                                                         |

Qwen name exceptions (checked before the arch default, applies to Qwen3 AND Qwen3.6):
- `thinking` in name → `thinking`
- `instruct` or `coder` in name → `instruct`
- otherwise → arch default (`qwen35*`: thinking, `qwen3*`: instruct)

**Blueprint classification is registry-driven.** `classify_registry()` always passes the
registry value as `existing_reasoning` (priority 1), so manual/GGUF-derived values win over
keyword heuristics. `registry_tool.py validate` Check 7 cross-checks `reasoning` against the
arch map (currently 0 mismatches).

## API Control: native REST-API versus OpenAI compatible API

The system uses a **3-level strategy** for controlling thinking mode:

| Level | Model         | Parameter                                          | API                                      |
|-------|---------------|----------------------------------------------------|------------------------------------------|
|   1   | gpt-oss       | `reasoning: {"effort": "low"}`                     | Native REST `/api/v1/chat`               |
|   2   | Qwen3/3.5/3.6 | `chat_template_kwargs: {"enable_thinking": false}` | OpenAI-compatible `/v1/chat/completions` |
|   3   | Others        | No thinking control (registry decides)             |      -                                   |

**Note:** Level 1/2 parameter hints are model-specific; since 2026-07-31 the **registry**
(`reasoning: thinking`) is the primary switch — `get_model_config()` sets
`enable_thinking=True` for registry-thinking models without any flag. The level tables above
describe the transport mechanism per family.

**⚠ `chat_template_kwargs` is NOT an OpenAI-standard parameter.**
It is only supported by **Qwen models** (Qwen3, Qwen3.5, Qwen3.6). 
The source is an *undocumented LM Studio extension* based on HuggingFace transformers `chat_template_kwargs`.
**Source:** https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1573

*For Qwen3 models (but NOT Qwen2.5):
"To Switch Between Thinking and Non-Thinking: If you are using llama.cpp, Ollama,Open WebUI etc., you can add /think and /no_think 
to user prompts or system messages to switch the model's thinking mode from turn to turn. The model will follow the most recent
instruction in multi-turn conversations." (Source: Unsloth, model card in LMS)

**Important:** For **Gemma-4** `chat_template_kwargs` does NOT work — thinking is hard-wired into the GGUF-Jinja template 
                via `<|channel>thought` (see Gemma-4 section below).

**⚠`extra_body` nesting (historical, fixed 19.07.):** The custom pipeline used to nest `chat_template_kwargs` under 
            `extra_body` (`body["extra_body"]["chat_template_kwargs"] = {...}`). 
            This is WRONG for direct HTTP requests — `extra_body` is an OpenAI Python SDK concept that gets
            UNWRAPPED to the top level. In a manually-constructed JSON body, `extra_body` is just another
            unknown key that the server ignores.

**Fix**: `body["chat_template_kwargs"] = kwargs`.

The `lm_eval` path (`gen_kwargs["extra_body"]`) is correct because lm_eval passes gen_kwargs to the OpenAI SDK, 
which properly unwraps `extra_body` to the top level.

**Bug symptom:** Qwen3.6-27B (thinking=ON by default in GGUF) always ran in thinking mode (6000+ tokens/task) 
when `enable_thinking=False` never reached the Jinja template renderer.
Fixed since 19.07. by top-level placement; since 04.08. Qwen3.6 intentionally runs with `enable_thinking=True` (registry default, see below).


## Reasoning-Effort Parameter for GPT-OSS models

**SINCE 02.08. (v13.0.10):** Central source in `benchmark_config.py`: `GPTOSS_REASONING_EFFORT = "medium"`, `GPTOSS_REASONING_BUDGET = 4096`.

They control **both** levels synchronously: 
(1) LM Studio engine config (`patch_reasoning_effort.py` writes `reasoningEffort`/`budgetTokens`, overridable via `--effort/--budget`) and 
(2) the system prompt of the `gptoss_reasoning` blueprint (`assemble_blueprint.py`, "Reasoning: "). 

Source reference below remains valid.

For **gpt-oss models**, `reasoning.effort` is used (not `chat_template_kwargs`):

| Effort     | Meaning                                       |
|------------|-----------------------------------------------|
| `"off"`    | No reasoning (not supported by gpt-oss)       |
| `"low"`    | Minimal reasoning (faster, but worse)         |
| `"medium"` | Medium reasoning (slower, but better)         |
| `"high"`   | Maximum reasoning (high token usage, very slow on local hardware) |

**Source:** https://lmstudio.ai/docs/developer/rest/chat


## Gemma-4 Special Case

- **Registry:** ALL Gemma-4 variants (19B-REAP-I1, 26B I1/REAP, google/unsloth 26B, 12B-QAT)
  are `reasoning: thinking` — Gemma-4 is a natively reasoning model.
- Gemma-4 models ignore `enable_thinking=False` via API because `<|channel>thought` is
  hard-wired in the GGUF-Jinja template.
- `strip_thinking_tokens()` (`custom_benchmark.py:748-785`) strips the
  `<|channel>thought\n...<channel|>` sections from the final answer.
- **No system-prompt override anymore** (the former `"Do NOT use thinking..."` prompt in
  `generate_answer()` was removed; thinking is handled purely via registry config +
  post-processing).


## Current Patterns — effective `enable_thinking` (JSON-Config / registry, since 05.08.)

Since v13, `max_tokens` is determined by the **benchmark category** (variant C+, p6):
**coding**: 2048 | **math**: 4096 | **knowledge**: 2048 | **agentic**: 4096

The table below documents the **effective** values (source: LMS JSON-Config
`operation.fields` → `get_model_config()`, plus registry `reasoning` for the
family default). `MODEL_TEMP_OVERRIDES` no longer exists (removed 05.08.);
all per-model values now come from the JSON-Config (matches the GUI).

| Pattern             | enable_thinking | max_tokens | Special Notes                                       |
|---------------------|-----------------|------------|-----------------------------------------------------|
| default (category)  |  *False*        |      –     | Category defaults since 2026-07-11                  |
| qwen3.5             |   False         |      –     | temp=0.2, top_p=0.9, no_system_msg; installed qwen3.5-9b is `instruct` in registry (GGUF variant would be thinking) |
| qwen3.6 (all)       |  *True* (reg.)  |      –     | Registry `thinking` wins — no override anymore      |
| gemma (all)         |  *True* (reg.)  |      –     | Registry `thinking` wins — no override anymore      |
| gpt-oss             |  *True* (reg.)  |    4096    | stop: <\|return\|>, <\|call\|>, reasoning_effort central (GPTOSS_REASONING_EFFORT, default medium) |
| phi-4               |  *True* (reg.)  |      –     | unsloth/phi-4 is `thinking` in registry; JSON-Config only sets temp=0.8/top_k=50 |
| deepseek-r1-distill |   False         |      –     | Registry `instruct` (Qwen2.5 base, manually set 04.08.); JSON-Config only temp=0.0 |
| deepseek-coder      |   False         |      –     | temp=0.6, min_p=0.02; registry `instruct`           |
| kimi                |   False         |      –     | enable_thinking=True → "Content-only format" error |
| rnj                 |  *True* (reg.)  |      –     | THOUGHT:/RESPONSE: parsing format (hub model.yaml)  |
| bonsai-27b / 8b     |   (reg.)        |      –     | temp/top_k per manufacturer card (thinking-mode)    |
| magistral/ministral/nemotron |  (reg.)  |      –     | temp=0.7, top_p=0.95                                 |

> `–` in the max_tokens column = category default applies (no override).
> `(reg.)` = no `enable_thinking` in the JSON-Config; the registry value decides
> (`thinking` → True, `instruct` → False).


### Effective `enable_thinking` per installed model family (verified 04.08.)

| Family                                    | registry | enable_thinking |
|-------------------------------------------|----------|-----------------|
| qwen3.6-27b / -mtp / -i1 / 28b-reap-i1    | thinking | **True**        |
| gemma-4-12b-it-qat / 19b-reap-i1 / 26b (all) | thinking | **True**   |
| gpt-oss-20b                               | thinking | **True**        |
| unsloth/phi-4                             | thinking | **True**        |
| qwen3-coder-reap-25b-a3b-i1               | thinking | **True**        |
| rnj-1 / magistral / ministral-3-14b / nemotron-cascade / mirothinker / bonsai-27b-mtp / glm-4.7 (all) / zai-org/glm-4.6v | thinking | **True** |
| qwen3-30b-a3b-instruct / qwen3-coder-30b-a3b-instruct | instruct | False  |
| qwen2.5-coder-14b-instruct (all quants)   | instruct | False          |
| deepseek-r1-distill-qwen-14b              | instruct | False          |
| deepseek-coder-33b-instruct / v2-lite     | instruct | False          |
| ernie-4.5 / granite-4.x / devstral / codestral / falcon3 / lfm2 / mellum2-instruct / internlm2_5 / bonsai-8b | instruct | False |
| kimi-linear-reap-35b                      | (none)   | False (override)|


## Stop-String Trap: `"\n```"` breaks Code-Block Opening (2026-08-01)

**Symptom:** deepseek-r1-distill-qwen-14b scored 0% on DS1000 and CoderEval (20/20
`No code generated`, `tokens_out=0`, reasoning 237–1344 tokens) despite prompt hardening
(`_THINKING_CODE_ONLY_SUFFIX`).

**Root cause:** `STOP_TOKENS_CODING` contained `"\n```"`. DeepSeek R1 Distill starts its
final answer (after thinking) with `\n```python` — i.e. the **opening** of a Markdown code
block. LM Studio applies stop strings eagerly, so the answer was cut off right after the
block opened → nearly empty content.

Why only DeepSeek? Other models (Qwen3, LLaMA, ...) don't begin answers with `\n```;
DeepSeek R1 Distill does, because the final answer starts with a code block (suffix forces this).

**Live verification** (01.08.2026, direct API to localhost:1234, same prompt as benchmark run):

| Stop list                          | content_len | Result                                  |
|------------------------------------|-------------|-----------------------------------------|
| `["\n```", "\n# Task", ...]` (old) | 1 (`"\n"`) | finish_reason=stop, code killed at open |
| no `\n``` ` stop                   | 338         | full code block                         |
| `["\n```\n", "\n# Task", ...]`     | 338         | full code block, stops at **close**     |

**Fix:** `custom_benchmark.py:192` — `"\n```"` → `"\n```\n"`.                                                                        #  ```
The trailing newline means the stop only matches the **closing** fence (`\n```\n`, line end) and never the opening (`\n```python`).  # ```

**Result (verification run, seed 42, sample-size 20):** DS1000 **7/20 = 35%**, CoderEval **8/12 = 67%** (previously 0/0). 
No more `No code generated`; remaining failures are real code-quality issues. 
Consistent with older SS30 runs from 23./24.07. (40% / 58%) — the 0% runs were a regression, not model failure.

> **General rule:** stop strings with ` ``` ` must include the trailing `\n` (`\n```\n`)                   # ```
>  for any thinking/reasoning model whose final answer starts with a code block. 
> The same applies to future stop-list additions for other code benchmarks.

## --thinking Flag Behavior (v13, updated 05.08.)

| Model group              | --thinking effect                         | Reason                                                                          |
|--------------------------|-------------------------------------------|---------------------------------------------------------------------------------|
| Reasoning models         | ✅ enable_thinking=True (+ timeout ×2)    | Detection via `REASONING_PATTERNS` keyword match (`benchmark_config.py:514`, word-boundary) |
| (registry `thinking`)    |                                           |                                                                                 |
| Gemma-4                  | ✅ registry already sets True             | Registry `thinking` wins; no override anymore                                   |
| Qwen3.6 (all)            | ✅ registry already sets True             | Registry `thinking` wins; no override anymore (formerly forced False)           |
| GPT-OSS                  | ✅ enable_thinking=True possible          | `gpt-oss` in REASONING_PATTERNS; registry already `thinking`                    |
| Qwen3.5                  | ❌ no effect                              | Installed qwen3.5-9b is `instruct` (registry); JSON-Config False stays          |
| Default (instruct models)| ❌ no effect                              | enable_thinking stays False (JSON-Config / category default)                    |

**Practical consequence:** `--thinking` is now mostly redundant for reasoning models —
the registry already enables thinking. It remains useful as an explicit force for
`REASONING_PATTERNS` models not (yet) marked `thinking` in the registry.


## Model Classification (registry-based since 21.07.)

Since 21.07., model classification no longer uses keyword matching but reads the `reasoning`
field from `model_registry.yaml`. Detection flow:

1. **GGUF header** (`_read_gguf_arch()`): Reads `tokenizer.chat_template`, returns `is_reasoning=True/False/None`
   
2. **fill-reasoning** (`src/registry_tool.py`): Writes `reasoning: thinking|instruct` into
   registry for entries without it (existing values are kept)
   
3. **Runtime** (`run_benchmarks.py:_is_reasoning_model()`, `custom_benchmark.py: _model_supports_reasoning()`): 
   Look up `model_identifier` in registry, strip `@quant` suffix, return `True` for `reasoning: thinking`, `False` otherwise

Fallback: If registry data is missing, prints a warning and returns `False`.


## Configuration flow (v13)

Since v13, the thinking parameters are managed centrally in `get_model_config()` (`benchmark_config.py:495`), used by:
- `custom_benchmark.py:_get_model_config()` (custom pipeline)
- `run_benchmarks.py:_get_evaluation_parameters()` (lm_eval pipeline)

This avoids duplicate configuration between the custom pipeline and the lm_eval pipeline.
Since 05.08. the **LMS JSON-Config is the only source** for generation parameters;
`MODEL_CONFIG`/`THINKING_CONFIG` in `custom_benchmark.py` is now only a backward-compatible alias for `BENCHMARK_CATEGORY_DEFAULTS`.

The registry lookup (`reasoning: thinking`) is reflected in the JSON-Config's
`enableThinking` (via `configs` command); `--thinking` force-overrides it
(see --thinking section above).


## History

### 2026-08-05
- **LMS JSON-Config as the ONLY source** (`benchmark_config.py:495`): `MODEL_TEMP_OVERRIDES`
  and the Knowledge-Floor were removed — no Python override anymore. Generation parameters
  (incl. thinking) come exclusively from `operation.fields` of the
  `user-concrete-model-default-config` JSONs; `BENCHMARK_CATEGORY_DEFAULTS` only as fallback
  without JSON-Config. Result carries `_source` ("lms-json" | "category-default").
- **Thinking detection from JSON-Config** (`benchmark_config.py:448-462`): `enableThinking` >
  `budgetTokens` (checked + value>0) > `parsing.enabled`.
- **Docs updated:** Priority chain, current patterns, `--thinking` table, configuration flow.

### 2026-08-04
- **Registry wins for thinking families:** Removed the `enable_thinking=False` workarounds
  for `qwen3.6` and `gemma` from `MODEL_TEMP_OVERRIDES` — these models are natively
  reasoning and now run with `enable_thinking=True` (registry `reasoning: thinking`).
- **deepseek-r1-distill-qwen-14b → instruct:** Manually set to `instruct` in the registry
  (Qwen2.5 base = instruct model, name contains "r1" but it is a distilled instruct model).
  `fill-reasoning` does not overwrite existing values.
- **Effective-config verification:** Live check of all installed models — registry
  classification matches `classify_reasoning()` (arch map + name exceptions), Check 7
  (reasoning ↔ arch map) passes with 0 mismatches.
- **Docs fully translated to English** and aligned with the registry-first mechanism.

### 2026-08-01
- **BUGFIX stop-string kills code-block opening:** `STOP_TOKENS_CODING`
  (`custom_benchmark.py:192`) `"\n```"` → `"\n```\n"`. Root cause: deepseek-r1-distill-qwen-14b
  begins its final answer with `\n```python` (opening fence); the old stop matched the opening
  and aborted the response after ~0 tokens (`No code generated`). Verified live (content_len
  1 vs 338) and by re-run: DS1000 35%, CoderEval 67% (seed 42, SS20) instead of 0%/0%.
  See "Stop-String Trap" section above.
- **Prompt hardening verified:** `_THINKING_CODE_ONLY_SUFFIX` (`custom_benchmark.py:1541`) is
  effective — with it the model returns ONLY a ` ```python ` block. The 0% results were caused
  by the stop string, not by the suffix or thinking mode itself.

### 2026-07-31
- **Registry-driven enable_thinking (general solution):** `get_model_config()` now reads
  `reasoning: thinking` from `model_registry.yaml` and forces `enable_thinking=True` — no
  `--thinking` flag needed. Explicit `MODEL_TEMP_OVERRIDES` entries still win
  (kimi/qwen3.5/qwen3.6/gemma kept `enable_thinking=False` as experimental workarounds —
  removed again on 04.08.). Affects both pipelines (custom + lm_eval via
  `_get_evaluation_parameters`). Fixed deepseek-r1-distill-qwen-14b (registry
  `reasoning: thinking`, Qwen2 arch): quality over runtime.
- **Qwen template detection broadened:** `_uses_qwen_template()` replaces the
  qwen3/qwen-3 name checks in `generate_answer()` — covers Qwen-based distills
  (deepseek-r1-distill-qwen-14b) for `chat_template_kwargs.enable_thinking`.
- **Streaming reasoning deltas:** `_extract_reasoning_delta()` handles both formats:
  - `delta.reasoning_content` — DeepSeek R1, LM Studio 0.3.9+ (App Settings > Developer
    "Separate reasoning_content in Chat Completion responses"; blog/lmstudio-v0.3.9)
  - `delta.reasoning` — gpt-oss, LM Studio 0.3.23+ (o3-mini-conform;
    docs/developer/api-changelog "Reasoning content and tool-calling reliability")
  Non-streaming fallback already read both `message.reasoning` and `message.reasoning_content`.

### 2026-07-28
- **chat_template_kwargs only for Qwen:** Parameter is only used for Qwen3/Qwen3.5/Qwen3.6
  models. Source: https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1573
- **reasoning_effort adjusted:** gpt-oss reasoning_effort from "medium" to "low" (faster
  answers, fewer errors)
- **MATH max_tokens reduced:** 8192 → 4096 (sufficient for most MATH tasks, ~2x faster)
- **Documentation extended:** Sources and constraints for chat_template_kwargs and
  reasoning_effort documented

### 2026-07-21
- **Reasoning detection via Registry:** `_is_reasoning_model()` now reads
  `model_registry.yaml:reasoning` field. No longer keyword-based. Registry populated
  automatically from GGUF `tokenizer.chat_template` via `registry_tool.py fill-reasoning`.
- **BUGFIX `_read_gguf_arch()`:** Returns `is_reasoning = False` (not `None`) when no chat
  template found, preventing models without templates from incorrectly triggering the
  reasoning path.
- **BUGFIX @quant suffix:** Both `src/run_benchmarks.py` and `src/custom_benchmark.py` now
  strip `@quant` suffix before registry lookup, so `model_identifier=model@q4_0` matches
  registry key `publisher/model`.

### 2026-07-20
- **Native REST API (Option 2):** `custom_benchmark.py:generate_answer()`: When
  `enable_thinking=False`, routes to `_generate_answer_native()` which uses LM Studio's
  native REST API (`/api/v1/chat`) with `reasoning: "off"` — a dedicated, reliable parameter
  that guarantees thinking is disabled. This is the fallback after `chat_template_kwargs` may
  be ignored by the OpenAI-compatible endpoint.
- **lm_eval double coverage:** `src/run_benchmarks.py`: Added `gen_kwargs["reasoning"] = "off"`
  alongside existing `chat_template_kwargs.enable_thinking`, plus `"reasoning"` in both
  `gen_kwargs_keys` sets. If LM Studio's OpenAI endpoint forwards `reasoning`, this provides
  a second path to disable thinking.
- **Reason for native API:** The OpenAI-compatible endpoint (`/v1/chat/completions`) does not
  list `chat_template_kwargs` or `reasoning` as supported parameters. The native REST API
  (`/api/v1/chat`) has `reasoning: "off"|"low"|"medium"|"high"|"on"` as a first-class parameter.

### 2026-07-19
- **Bugfix Custom Pipeline:** `extra_body` nesting removed in
  `custom_benchmark.py:generate_answer()` → `chat_template_kwargs` now at top level of HTTP
  body. Root cause: `extra_body` is an OpenAI SDK unwrap-mechanism, not a valid HTTP-level
  key — LM Studio ignored it silently. Affects DS1000, CoderEval.
- **Bugfix lm_eval Pipeline:** Same fix in `run_benchmarks.py:_get_lmeval_params()` and
  `gen_kwargs_keys` — `extra_body` → `chat_template_kwargs` top-level. lm_eval uses
  `requests.post()` directly (not OpenAI SDK), therefore the same bug. Affects MATH-500, ARC,
  HellaSwag, TruthfulQA.
- **Qwen3.6 Catch-All:** `MODEL_TEMP_OVERRIDES`: `"qwen3.6"` → `enable_thinking=False` for
  all Qwen3.6 models and derivatives (removed again on 04.08.).
- **REASONING_PATTERNS:** `qwen3.6-27b` removed — `--thinking` had no effect on Qwen3.6
  (now redundant because the registry sets True anyway).

### 2026-07-11
- Default `enable_thinking`: None → **False** (previously: no extra_body sent)
- 8 new patterns added (apriel, nemotron, falcon3, codestral, devstral, ernie, rnj,
  python-coder)
- gpt-oss `enable_thinking`: None → False
- Gemma system prompt override implemented (removed again on 04.08.)
- Diagnostic warning in `strip_thinking_tokens()` on complete thinking consume

### 2026-07-11 (Bugfixes HellaSwag/MathQA)
- **YAML max_gen_toks**: MathQA `20→512`, HellaSwag `20→100`
- **YAML Regex**: `[ABCDE]` → `[A-Ea-e]` (lowercase also matchable), same for HellaSwag
- **HellaSwag YAML**: `>-` (folded) → `|` (literal) for newlines in prompt
- **utils.py**: `process_docs()` regex more robust against comma values in choices
- **run_benchmarks.py**: lm_eval parameters passed via `--gen_kwargs` instead of
  `--model_args`
  - Generation parameters (max_tokens, temperature, top_p, min_p, extra_body, until)
    now land in the API payload instead of the (ignored) constructor
  - `--model_args` now only contains constructor parameters (base_url, model,
    num_concurrent, max_gen_toks)
  - `eos_string=<|endoftext|>` only for GPT-OSS (no longer for all models)
- **HellaSwag Limit**: `min_limit=100` per benchmark config, overrides `sample_size`
