# GPT-OSS-20b: Harmony-Jinja-Template-Injection in LM Studio Config JSONs

## Problem
GPT-OSS-20b **strictly requires** the Harmony-Jinja template (`llm.prediction.promptTemplate`)
in the LM Studio config JSON. Without this template, LM Studio uses its default ChatML template
(`<|im_start|>`, `<|im_end|>`). The model does not understand ChatML (expects Harmony format
`<|start|>channel<|message|>...<|end|>`) and produces empty output.

## Root Cause
LM Studio overwrites the config JSONs during updates. The template injection from 09.07.2026
and 24.07.2026 was thereby overwritten several times.
**Most recently overwritten again by an unknown LM Studio update before 28.07.2026.**

## Fix (28.07.2026) — Alle bekannten Bugs behoben

### Bug 1: Missing Harmony template
Template `doc-git/Jinja-Chat-Templates/gpt-oss-20b_harmony.jinja` (17221 characters)
was injected into all configs:

| Config | Vorher | Nachher |
|---|---|---|
| `openai/gpt-oss-20b.json` (Default-Load) | **fehlt** (3179 Bytes) | Template + Prompt (20447 Bytes) |
| `lmstudio-community/.../MXFP4.gguf.json` | vorhanden, falscher Prompt | Template korrekt + Prompt aktualisiert |
| `unsloth/.../Q6_K.gguf.json` | vorhanden, falscher Prompt | Template korrekt + Prompt aktualisiert |
| `unsloth/.../Q8_0.gguf.json` | vorhanden, falscher Prompt | Template korrekt + Prompt aktualisiert |

### Bug 2: Wrong system prompt (XML tags instead of Markdown)
The `systemPrompt` contained `<role>`, `<reasoning>`, `<coding>`, `<output>` XML tags.
These are **not** Harmony-compatible. The prompt was switched to Markdown headings:

**Before:**
```
<role>
You are GPT-OSS, an AI software engineering assistant.
</role>

<reasoning>
- Analyze the problem step by step...
</reasoning>
```

**After:**
```
You are gpt-oss-20b, a GPT-OSS MoE model with 20B parameters...

## Reasoning
- Analyze the problem step by step...

## Safety
...
```

The fix was implemented in `assemble_blueprint.py`: new function `_harmonify_prompt()`
converts XML-tag prompts to Harmony Markdown. Only for the `gptoss_reasoning` blueprint.

### Bug 3: `chat_template_kwargs` was mistakenly sent to gpt-oss
`run_benchmarks.py:_get_evaluation_parameters()` sent `chat_template_kwargs`
with `enable_thinking: False` for all models with `enable_thinking` in the config.
This parameter is only valid for Qwen models. Fix: `chat_template_kwargs`
is now only set for non-gpt-oss models.

### Bug 4: `max_thinking_tokens` missing — reasoning token budget unlimited
**Most critical bug.** Without `max_thinking_tokens`, gpt-oss thinks up to `max_tokens`
(4096 for MATH-500) and produces `content=""`. The parameter had to be added in 3 files:

| File | Change |
|---|---|
| `benchmark_config.py` line 283 | `"max_thinking_tokens": 200` in gpt-oss override |
| `run_benchmarks.py` lines 625, 996 | `"max_thinking_tokens"` in `generation_parameters_keys` |
| `custom_benchmark.py` lines 763, 779 | `body["max_thinking_tokens"] = 200` for gpt-oss |

### Bug 5: `reasoning` instead of `reasoning_effort` in the API body
`squashed in earlier session (24.07.2026)`

## Effect of the fixes (test run 3, 28.07.2026)

| Benchmark | Before fixes (ChatML, no budget) | After fixes (Harmony + max_thinking_tokens=200) |
|---|---|---|
| DS1000 | 0% (leerer Output) | ~33% (sample-size 3, echter Code) |
| MATH-500 | 0% (leerer Output) | 20% (sample-size 5) |
| IFEVAL | 40%/62.5% | 40%/62.5% (stabil) |

## Verification
```bash
# Check config JSON for template and prompt
python -c "import json; d=json.load(open(r'C:\Users\pskra\.lmstudio\.internal\user-concrete-model-default-config\openai\gpt-oss-20b.json')); fields={f['key']: f['value'] for f in d['operation']['fields']}; print('Has template:', 'promptTemplate' in str(list(fields.keys()))); print('Prompt starts:', repr(fields['llm.prediction.systemPrompt'][:80]))"

# Template-Validierung (registry_tool.py)
echo "14" | python registry_tool.py | grep template
# Erwartet: template_missing_config: 0

# Blueprint-Assembly + Validierung
python assemble_blueprint.py assemble
python assemble_blueprint.py validate
```

## Stability
The template is overwritten by LM Studio updates. After every update:
1. `python assemble_blueprint.py assemble` (restores prompt + template)
2. Reload the model: `lms unload --all && lms load openai/gpt-oss-20b`

## Template-Quelle
`doc-git/Jinja-Chat-Templates/gpt-oss-20b_harmony.jinja`
(identical to `gpt-oss-20b-template_unsloth.jinja`, SHA256 confirmed)

## Quellen
- https://developers.openai.com/cookbook/articles/openai-harmony
- https://developers.openai.com/cookbook/articles/gpt-oss/run-locally-lmstudio
- https://github.com/openai/gpt-oss/tree/main?tab=readme-ov-file#harmony-format--tools
- https://lmstudio.ai/blog/gpt-oss
