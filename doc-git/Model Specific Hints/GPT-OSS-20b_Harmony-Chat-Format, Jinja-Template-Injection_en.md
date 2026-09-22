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
| ---------------------------------------- | -------------------------- | -------------------------------------- |
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

| File                                 | Change                                                  |
| ------------------------------------ | ------------------------------------------------------- |
| `benchmark_config.py` line 283       | `"max_thinking_tokens": 200` in gpt-oss override        |
| `run_benchmarks.py` lines 625, 996   | `"max_thinking_tokens"` in `generation_parameters_keys` |
| `custom_benchmark.py` lines 763, 779 | `body["max_thinking_tokens"] = 200` for gpt-oss         |

### Bug 5: `reasoning` instead of `reasoning_effort` in the API body
`squashed in earlier session (24.07.2026)`

## Effect of the fixes (test run 3, 28.07.2026)

| Benchmark | Before fixes (ChatML, no budget) | After fixes (Harmony + max_thinking_tokens=200) |
| --------- | -------------------------------- | ----------------------------------------------- |
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

## Current project integration review (2026-09-21)

`assemble_blueprint.py` now keeps the Harmony template and `<|return|>` stop
string in both the YAML blueprint and its embedded fallback definition. It
also converts the generic blueprint section wrappers (`<role>`, `<coding>`,
`<safety>`, and `<output>`) to Markdown headings for GPT-OSS, because those
XML wrappers are not part of the Harmony instruction format.

The benchmark runtime profile keeps structured output disabled for GPT-OSS,
uses the Harmony stop string, and sends a bounded `max_thinking_tokens`
budget of 4096. This budget is sent only for GPT-OSS requests; it is not
copied to unrelated models and is separate from LM Studio's GUI profile.

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

## LM Studio smoke test and current integration (2026-09-22)

LM Studio 0.3.23 documents two relevant GPT-OSS compatibility changes in its
[release notes](https://lmstudio.ai/blog/lmstudio-v0.3.23): tool names are
normalized to `snake_case` before they reach GPT-OSS, and reasoning is removed
from the final `content` field. For non-streaming Chat Completions, reasoning
is exposed as `choices.message.reasoning`; for streaming, it is exposed as
`choices.delta.reasoning`. The project parser accepts these fields and retains
the older `reasoning_content` names used by DeepSeek-style responses.

The agentic wrapper also removes `response_format` when a request contains
tools, because LM Studio/llama.cpp cannot combine that structured-output
constraint with tool-calling grammar. Tool-name normalization itself remains
an LM Studio compatibility responsibility; the benchmark must use the names
returned by the tool-calling adapter rather than trying to reverse-map them.

The locally downloaded model was tested through the real LM Studio
OpenAI-compatible endpoint after the Harmony configuration review:

* model: `ggml-org/gpt-oss-20b-MXFP4-GGUF/gpt-oss-20b-MXFP4.gguf`, API ID
  `gpt-oss-20b`;
* context length 32768, one parallel slot, full GPU offload;
* Harmony prompt template enabled, structured output absent, and
  `max_thinking_tokens: 4096` in the active LM Studio profile;
* non-streaming returned `GPTOSS_OK` with `finish_reason: stop` and separate
  reasoning content;
* streaming reconstructed `GPTOSS_STREAM_OK`, also with separate reasoning
  content.

The active LM Studio prompt template is byte-for-byte identical to
`doc-git/Jinja-Chat-Templates/gpt-oss-20b_harmony.jinja` after normalizing
Windows line endings. The two project template files currently have identical
content as well; their separate names are retained for explicit policy
selection, not because their current text differs. The active config also has
the expected GPT-OSS reasoning-effort and parsing fields and no GUI Structured
Output field.

One diagnostic request deliberately included the top-level API field
`reasoning_effort: "medium"`. LM Studio logged:

```text
No valid custom reasoning fields found ... Reasoning setting 'medium' cannot be converted to any custom KVs.
```

The request nevertheless completed, but the warning shows that this field is
not portable across LM Studio GGUF/config identities. A second request without
`reasoning_effort` completed without that warning. The project therefore keeps
GPT-OSS out of `chat_template_kwargs` and does not send `reasoning_effort` as an
API generation parameter. The Harmony system prompt and the bounded
`max_thinking_tokens` value are the portable controls for this LM Studio path.

The benchmark-side bug found during this review was different: the blueprint
already defined `max_thinking_tokens: 4096`, and `custom_benchmark.py` forwarded
it, but the LM-Eval command path did not. `run_benchmarks.py` now forwards that
field in `--gen_kwargs` for GPT-OSS and explicitly keeps
`reasoning_effort` out. Without this separation, a reasoning trace can consume
the entire ordinary `max_tokens` budget and leave an empty final channel.

The downloaded `ggml-org` variant was also missing from
`doc-git/model_registry.yaml`, even though the code and tests already had a
GPT-OSS policy. It is now registered as
`ggml-org/gpt-oss-20b@mxfp4` with the local GGUF facts, the
`gptoss_reasoning` blueprint, Harmony policy, and a 32768-token benchmark
context. This is required for `registry_only=True` model discovery and for
selection by `run_benchmarks.py`; it does not modify LM Studio's external JSON
configuration.

The same LM Studio server log contains a GPT-OSS-specific load warning about
`<|return|>`, `<|call|>`, `<|calls|>`, and `<|flush|>` being present in the EOG
set and `<|end|>` being removed. This is consistent with Harmony's explicit
return marker and is not the GLM `special_eot_id`/`special_eom_id` warning. The
benchmark continues to use `<|return|>` as the explicit stop string.

## Direct llama.cpp: reasoning effort versus reasoning budget

The standalone CUDA `llama-server.exe` exposes a native load-time option:

```text
--reasoning-effort LEVEL
```

This is the preferred control for the direct llama.cpp backend. It is passed to
the model's chat template when the server starts and accepts `default`,
`minimal`, `low`, `medium`, `high`, `xhigh`, or `max`. It belongs in the
provider-specific `llama_cpp` runtime section of the Registry, not in a generic
system prompt and not in an OpenAI-compatible request body. The current
`src/providers/llama_cpp_args.py` and `src/model_registry.py` already translate
that field into `--reasoning-effort`.

The following controls must remain separate:

| Control | Meaning | Recommended owner |
| --- | --- | --- |
| `llama_cpp.reasoning_effort` | qualitative Harmony reasoning level | Registry provider override, translated to `llama-server.exe` |
| `max_thinking_tokens` / `reasoning_budget` | numerical cap on reasoning tokens | benchmark runtime or llama.cpp runtime, depending on backend |
| `Reasoning: ...` in the Harmony system prompt | legacy/template-level fallback, mainly for LM Studio compatibility | assembled LM Studio prompt only when required |
| LM Studio `reasoningEffort` GUI field | LM Studio-local model setting | external LM Studio JSON configuration, not Registry SSOT |

The LM Studio path should not receive `reasoning_effort` as a generic
OpenAI-compatible request parameter: the real local smoke test accepted the
request but logged that the value could not be converted to custom KVs. For the
direct llama.cpp path, the server argument is explicit and reproducible.

For benchmark policy, `medium` should remain the initial baseline until a
dedicated quality/runtime comparison is recorded. `high` may improve GPT-OSS
accuracy, but it also changes the amount of reasoning and runtime; it is
therefore a separate benchmark profile, not a silent replacement of the
baseline. A comparison is only interpretable when the selected effort, token
budget, model file, context, and sampling values are recorded together.


