# GPT-OSS-20b: Harmony-Jinja-Template-Injection in LM Studio Config JSONs

## Problem
GPT-OSS-20b **strictly requires** the Harmony-Jinja template (`llm.prediction.promptTemplate`) in the LM Studio config JSON. 
Without this template, LM Studio uses its default ChatML template (`<|im_start|>`, `<|im_end|>`). 
The model does not understand ChatML (expects Harmony format `<|start|>channel<|message|>...<|end|>`) and produces empty output.

## Root Cause
LM Studio overwrites the config JSONs during updates. The template injection from 09.07.2026
and 24.07.2026 was thereby overwritten several times.
**Most recently overwritten again by an unknown LM Studio update before 28.07.2026.**

## Fix (28.07.2026) — Alle bekannten Bugs behoben

### Bug 1: Missing Harmony template
Template `doc-git/Jinja-Chat-Templates/gpt-oss-20b_harmony.jinja` (17221 characters)
was injected into all configs:

| Config                                   | Vorher                     | Nachher                                |
|------------------------------------------|----------------------------|----------------------------------------|
| `openai/gpt-oss-20b.json` (Default-Load) | **fehlt** (3179 Bytes)     | Template + Prompt (20447 Bytes)        |
| `lmstudio-community/.../MXFP4.gguf.json` | vorhanden, falscher Prompt | Template korrekt + Prompt aktualisiert |
| `unsloth/.../Q6_K.gguf.json`             | vorhanden, falscher Prompt | Template korrekt + Prompt aktualisiert |
| `unsloth/.../Q8_0.gguf.json`             | vorhanden, falscher Prompt | Template korrekt + Prompt aktualisiert |

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

The fix was implemented in `assemble_blueprint.py`: new function `_harmonify_prompt()` converts 
XML-tag prompts to Harmony Markdown. **Only for the `gptoss_reasoning` blueprint.

### Bug 3: `chat_template_kwargs` was mistakenly sent to gpt-oss
`run_benchmarks.py:_get_evaluation_parameters()` sent `chat_template_kwargs`
with `enable_thinking: False` for all models with `enable_thinking` in the config.
This parameter is only valid for Qwen models. Fix: `chat_template_kwargs`
is now only set for non-gpt-oss models.

### Bug 4: `max_thinking_tokens` missing — reasoning token budget unlimited
**Most critical bug.** Without `max_thinking_tokens`, gpt-oss thinks up to `max_tokens`
(4096 for MATH-500) and produces `content=""`. The parameter had to be added in 3 files:

| File                                  | Change                                                  |
|---------------------------------------|---------------------------------------------------------|
| `benchmark_config.py` line 283        | `"max_thinking_tokens": 200` in gpt-oss override        |
| `run_benchmarks.py` lines 625, 996    | `"max_thinking_tokens"` in `generation_parameters_keys` |
| `custom_benchmark.py` lines 763, 779  | `body["max_thinking_tokens"] = 200` for gpt-oss         |

### Bug 5: `reasoning` instead of `reasoning_effort` in the API body
`squashed in earlier session (24.07.2026)`

## Effect of the fixes (test run 3, 28.07.2026)

| Benchmark | Before fixes (ChatML, no budget) | After fixes (Harmony + max_thinking_tokens=200) |
|-----------|----------------------------------|-------------------------------------------------|
| DS1000    | 0% (leerer Output)               | ~33% (sample-size 3, echter Code)               |
| MATH-500  | 0% (leerer Output)               | 20% (sample-size 5)                             |
| IFEVAL    | 40% / 62.5%                      | 40% / 62.5% (stabil)                            |

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

## Template scope

- `gpt-oss-20b_harmony.jinja`: upstream / LM Studio Harmony override for `openai/gpt-oss-20b`
- `gpt-oss-20b-template_unsloth.jinja`: explicit-file override for the verified Unsloth GGUF variant only
- In `model_registry.yaml`, use `template_policy: explicit_file`, `template_variant: unsloth_harmony_fix`,
  `template: gpt-oss-20b-template_unsloth.jinja` only for the matching Unsloth model. Do not generalize the
  Unsloth variant to the upstream model.

## Quellen
- https://developers.openai.com/cookbook/articles/openai-harmony
- https://developers.openai.com/cookbook/articles/gpt-oss/run-locally-lmstudio
- https://github.com/openai/gpt-oss/tree/main?tab=readme-ov-file#harmony-format--tools
- https://lmstudio.ai/blog/gpt-oss

- https://lmstudio.ai/blog/lmstudio-v0.3.23 
ebenda: 
**"Improve openai/gpt-oss in-chat tool calling reliability**
Tool names are now consistently formatted before being sent to the model. 
*Previously, tools with spaces in their names would confuse gpt-oss and lead to tool call failures. 
Tool names are now converted to `snake_case`. 
Additionally, we squashed a few parsing bugs that could have previously led to parsing errors in the chat. 
You might notice significant improvements in tool calling reliability."

**"Reasoning Content from gpt-oss using the Chat Completions endpoint
This is a change in behavior compared with version 0.3.22.
    message.content will no longer include reasoning content or <think> tags.
    Reasoning is now in choices.message.reasoning (non-streaming) and choices.delta.reasoning (streaming).
    This matches the behavior of o3-mini."

=========== Unlsoth ===========
https://unsloth.ai/blog/gpt-oss
ebenda:
  "Then use the encode_conversations_with_harmony function from Unsloth."
  ```from unsloth_zoo import encode_conversations_with_harmony
  def encode_conversations_with_harmony(
      messages,
      reasoning_effort = "medium",
      add_generation_prompt = True,
      tool_calls = None,
      developer_instructions = None,
      model_identity = "You are ChatGPT, a large language model trained by OpenAI.",
  )```

The harmony format includes multiple interesting things:
  -  reasoning_effort = "medium" You can select low, medium or high, and this changes gpt-oss's reasoning amount.
  -  developer_instructions is like a system prompt which you can add.
  -  model_identity is best left alone - you can edit it, but we're unsure if custom ones will function.

We find multiple issues with the current jinja chat template:
  -  Function and tool calls are rendered with `tojson`, which is fine it's a `dict`, but if it's a `string`, **speech marks and other symbols become backslashed.
  -  There are some extra new lines in the jinja template on some boundaries.
  -  Tool calling thoughts from the model should have the `analysis` tag and not `final` tag."
    
https://unsloth.ai/docs/models/gpt-oss-how-to-run-and-fine-tune

==============
(aus LM Studio model card im load Menü:)
## Inference examples

**Transformers

You can use gpt-oss-120b and gpt-oss-20b with Transformers. 
**If you use the Transformers chat template, it will automatically apply the harmony response format. 
If you use model.generate directly, you need to apply the harmony format manually using the chat template or use our openai-harmony package.

To get started, install the necessary dependencies to setup your environment:

`pip install -U transformers kernels torch`

Once, setup you can proceed to run the model by running the snippet below:
```
py
from transformers import pipeline
import torch

model_id = "openai/gpt-oss-20b"

pipe = pipeline(
    "text-generation",
    model=model_id,
    torch_dtype="auto",
    device_map="auto",
)

messages = [
    {"role": "user", "content": "Explain quantum mechanics clearly and concisely."},
]

outputs = pipe(
    messages,
    max_new_tokens=256,
)
print(outputs[0]["generated_text"][-1])
```

Alternatively, you can run the model via **Transformers Serve** to spin up a **OpenAI-compatible webserver**:

  transformers serve
  transformers chat localhost:8000 --model-name-or-path openai/gpt-oss-20b

Learn more about how to use gpt-oss with Transformers.
https://cookbook.openai.com/articles/gpt-oss/run-transformers

-----
** vLLM
vLLM recommends using uv for Python dependency management. 
You can use vLLM to spin up an OpenAI-compatible webserver. 
The following command will automatically download the model and start the server.

```
bash
uv pip install --pre vllm==0.10.1+gptoss \
    --extra-index-url https://wheels.vllm.ai/gpt-oss/ \
    --extra-index-url https://download.pytorch.org/whl/nightly/cu128 \
    --index-strategy unsafe-best-match

vllm serve openai/gpt-oss-20b
```
Learn more about how to use gpt-oss with vLLM.
https://cookbook.openai.com/articles/gpt-oss/run-vllm

----
**PyTorch / Triton
To learn about how to use this model with PyTorch and Triton, check out our reference implementations in the gpt-oss repository.
https://github.com/openai/gpt-oss?tab=readme-ov-file#reference-pytorch-implementation


