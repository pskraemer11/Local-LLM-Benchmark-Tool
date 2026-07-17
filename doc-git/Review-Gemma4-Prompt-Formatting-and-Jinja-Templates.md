## Review Report: Gemma-4 Prompt Formatting & Jinja Templates ##

Both templates are now fixed. Here is the detailed summary:

---

### 1. Official Format (from `tokenizer_config.json` of `google/gemma-4-12b-it`)

| Structure   | Official                                                                  | Token                   |
|-------------|---------------------------------------------------------------------------|-------------------------|
| Turn Start  | `<|turn>role\n`                                                           | `sot_token`             |
| Turn End    | `<turn|>`                                                                 | `eot_token`             |
| Tool Call   | `<|tool_call>call:name{args}<tool_call|>`                                 | `stc_token`/`etc_token` |
| Tool Decl.  | `<|tool>declaration:name{...}<tool|>`                                     | `std_token`/`etd_token` |
| Tool Resp.  | `<|tool_response>response:name{value:<|"|>...<|"|>}<tool_response|>`     | `str_token`/`etr_token` |
| Thinking    | `<|channel>thought\n...<channel|>` (Response)                             | `soc_token`/`eoc_token` |
| Think Signal| `<|think|>` (Prompt)                                                      | `think_token`           |

---

### 2. Found and Fixed Errors

#### **26B Template – 7 Tag Fixes:**

|Line(s)| Before                               | After                            |
|-------|--------------------------------------|----------------------------------|
|   3   | `<|turn|>system`                     | `<|turn>system`                  |
|  14   | `<|tool|>`                           | `<|tool>`                        |
|  21   | `<|tool|>`                           | `<tool|>`                        |
|  47   | `<|tool_response|>`                  | `<|tool_response>`               |
|  49   | `<|tool_response|>`                  | `<tool_response|>`               |
|  58   | `<|turn|>user`                       | `<|turn>user`                    |
| 72,89 | `<|turn|>model`                      | `<|turn>model`                   |
|  76   | `<|tool_call|>...<|tool_call|>`      | `<|tool_call>...<tool_call|>`    |

#### **12B Template – Completely Rewritten:**

- **BOS token** added (line 1)
- **Thinking mode** implemented (`enable_thinking` parameter, `<|think|>` signal)
- **Tool declarations** added (`<|tool>...<tool|>`)
- **tool_call_id matching** implemented (instead of `message.get('name')`)
- **Turn separator logic** adopted from 26B template (prev_was_model check)
- **Content type handling** (string vs. multipart `content[]`)

### 3. Python Code Changes

#### **custom_benchmark_v11.py:**

**a) Gemma config added to MODEL_CONFIG** (after line 136):
```python
"gemma": {
    "temperature": 0.0,
    "top_p": 1.0,
    "max_tokens": 4096,
    "enable_thinking": False,
},
```

**b) `strip_thinking_tokens` extended** – now recognizes both formats:
- Gemma 4: `<|channel>thought\n...<channel|>`
- Legacy: `<think>...</think>`

#### **run_benchmarks_v11.py:**

**a) `_is_gemma_model()`** added (analogous to `_is_gptoss_model`)

**b) `_get_lmeval_params()`** extended with Gemma branch:
```python
if _is_gemma_model(model_key):
    return {"max_tokens": 4096, "temperature": 0.0, "top_p": 1.0, "until": []}
```

### 4. Unchanged / Open Items

| Item                               | Status      | Reason                                                                                                                                      |
|------------------------------------|-------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| `enable_thinking=False`            | Intentional | For code benchmarks (DS1000, CoderEval) thinking is counterproductive. For reasoning tasks (MathQA, MMLU-Pro) it can be set to `True`.      |
| No `reasoning_content` streaming   | Accepted    | Gemma 4 delivers thinking in `<|channel>thought\n...<channel|>` inside the `content` field – correctly extracted by `strip_thinking_tokens`. |
| lm_eval `--apply_chat_template`    | Accepted    | lm_eval uses HuggingFace's own template (in the tokenizer), which matches the official format.                                              |
|                                    |             | The MiniJinja template is only used in the custom pipeline.                                                                                 |
| No `_is_gemma_model` in `main()`   | Accepted    | Gemma is not classified as a reasoning model (timeout ×2). If needed, `enable_thinking=True` can be set in the config –                     |
|                                    |             | then `reasoning=True` should also be set in the pipeline.                                                                                   |

### 5. Recommendations for Future Improvements

1. **Gemma-4-19B Template**: Check whether a Jinja template is also needed for the 19B variant
2. **Make thinking parameterizable**: Via CLI flag (`--thinking`) or benchmark configuration so that MathQA/MMLU-Pro can run with `enable_thinking=True`
3. **Tool-use pipeline**: The agentic pipeline (`tool_eval_bench`) uses its own chat templates – check consistency with the Gemma templates
4. **Context length**: Gemma 4 supports 1M tokens – check whether `model_max_length` is correctly configured in LM Studio

---
## Gemma-4-19B Template
The 19B model (gemma-4-19b-a4b-it-reap-i1) uses gemma4 architecture (same as 26B). The template file gemma4-26b-template_minijinja.jinja is the correct template format for all Gemma 4 models. 
I'll copy it as a reference for 19B.
