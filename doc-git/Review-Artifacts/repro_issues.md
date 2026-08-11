# Repro-Issues: model_registry.yaml vs. LM Studio Hub

Generated automatically: 2026-08-11 23:08:10

Source of truth for model facts are the GGUF files (immutable).
The `model_registry.yaml` is editable (python programs/manual) and is
checked here against the Hub `model.yaml` (`metadataOverrides`), which is
shipped by LM Studio and never touched anywhere in the process.

## Validate summary

- **Total issues (validate):** 6
- `template_missing_file`: 0
- `template_missing_config`: 0
- `missing_reasoning`: 0
- `missing_capabilities`: 0
- `missing_blueprint`: 0
- `registry_no_config`: 2
- `reasoning_arch_mismatch`: 0
- `config_context_drift`: 1
- `config_np_ukv_drift`: 0
- `config_context_too_small`: 0
- `gguf_header_drift`: 1
- `missing_quant`: 2

## Hub deviations (Registry vs. model.yaml)

No deviations between registry and hub model.yaml.

## Hub notes (no model.yaml in local hub)

48 entries have no local hub model.yaml (no comparison possible, manual GGUF check required):

- **unsloth/ernie-4.5-21b-a3b-pt@iq4_nl**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/gemma-4-19b-a4b-it-reap-i1@q4_k_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/gemma-4-26b-a4b-it-i1@iq4_xs**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/gemma-4-26b-a4b-it@iq3_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/qwen3-30b-a3b-instruct-2507**: no hub model.yaml found (registry has GGUF size)
- **qwen/qwen2.5-coder-14b-instruct@q5_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **qwen/qwen2.5-coder-14b-instruct@q5_k_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **qwen/qwen2.5-coder-14b-instruct@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **Qwen/Qwen3.5-9B-GGUF@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/qwen3.6-28b-reap-i1@iq3_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/qwen3.6-28b-reap-i1@q3_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **noctrex/ernie-4.5-21b-a3b-pt_moe@mxfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/gemma-4-12b-it-qat@q4_k_xl**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **originalgeek/qwen3.6-27b-unsloth-mtp-head-only**: no hub model.yaml found (registry has GGUF size)
- **mradermacher/kimi-linear-reap-35b-a3b-instruct-i1@iq3_xxs**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/qwen3.6-27b-i1@q3_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/qwen3-coder-reap-25b-a3b-i1@q3_k_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/gemma-4-26b-a4b-it-heretic-i1@iq3_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/phi-4@q5_k_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/devstral-small-2-24b-instruct-2512@q3_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **tiiuae/falcon3-10b-instruct@q8_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **ibm-granite/granite-4-0-h-tiny@q8_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **ibm-granite/granite-4-1-30b@q3_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/januscoder-14b@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **jetbrains/mellum2-12b-a2-5b-instruct@q4_k_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **lmstudio-community/ministral-3-14b-instruct-2512@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **nerdsking/nerdsking-python-coder-7b-i@q8_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/qwen3-coder-30b-a3b-instruct@q3_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/north-mini-code-1-0@iq3_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/qwen3-6-27b@q3_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/qwen3-6-27b-mtp@q8_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **bartowski/mistralai-magistral-small-2509@q3_k_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **internlm/internlm2-5-20b-chat@q4_k_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **lmstudio-community/internlm2-math-plus-20b@q4_k_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **quietimpostor/nemotron-3-nano-reap-21b-a3b@mxfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **intel/qwen3-30b-a3b-instruct-2507-q2ks-mixed-autoround@q2_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **intel/qwen3-30b-a3b-thinking-2507-q2ks-mixed-autoround@q2_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **jetbrains/mellum2-12b-a2-5b-thinking-moe@mxfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **noctrex/lfm2-24b-a2b-moe@mxfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/glm-4-7-flash@q3_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **ibm-granite/granite-4-1-8b@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **crucible-labs/gemma4-26b-a4b-reap-25@mixed**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **essentialai/rnj-1@q8_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **openai/gpt-oss-20b@mxfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **qwen/qwen3.5-9b@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **qwen/qwen3-14b@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **zai-org/glm-4.6v-flash@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/qwen3-coder-reap-25b-a3b@q3_k_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
