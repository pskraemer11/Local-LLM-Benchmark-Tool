# Repro-Issues: model_registry.yaml vs. LM Studio Hub

Generated automatically: 2026-09-19 11:08:51

Source of truth for model facts are the GGUF files (immutable).
The `model_registry.yaml` is editable (python programs/manual) and is
checked here against the Hub `model.yaml` (`metadataOverrides`), which is
shipped by LM Studio and never touched anywhere in the process.

## Validate summary

- **Total issues (validate):** 0
- `template_missing_file`: 0
- `template_missing_config`: 0
- `missing_reasoning`: 0
- `missing_capabilities`: 0
- `missing_blueprint`: 0
- `sampling_invalid`: 0
- `sampling_research_status_invalid`: 0
- `registry_no_config`: 0
- `reasoning_arch_mismatch`: 0
- `config_context_drift`: 0
- `config_np_ukv_drift`: 0
- `config_context_too_small`: 0
- `gguf_header_drift`: 0

## Hub deviations (Registry vs. model.yaml)

No deviations between registry and hub model.yaml.

## Hub notes (no model.yaml in local hub)

66 entries have no local hub model.yaml (no comparison possible, manual GGUF check required):

- **unsloth/ernie-4.5-21b-a3b-pt@iq4_nl**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/gemma-4-19b-a4b-it-reap-i1@q4_k_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/gemma-4-26b-a4b-it-i1@iq4_xs**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/gemma-4-26b-a4b-it@iq3_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/qwen3-30b-a3b-instruct-2507@q3_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **Qwen/Qwen3.5-9B-GGUF@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/qwen3.6-28b-reap-i1@iq3_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/qwen3.6-28b-reap-i1@q3_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **noctrex/ernie-4.5-21b-a3b-pt_moe@mxfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/kimi-linear-reap-35b-a3b-instruct-i1@iq3_xxs**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/qwen3-coder-reap-25b-a3b-i1@q3_k_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/phi-4@q5_k_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/devstral-small-2-24b-instruct-2512@q3_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **tiiuae/falcon3-10b-instruct@q8_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/januscoder-14b@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **jetbrains/mellum2-12b-a2.5b-instruct@q4_k_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **nerdsking/nerdsking-python-coder-7b-i@q8_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/qwen3-coder-30b-a3b-instruct@q3_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **bartowski/mistralai-magistral-small-2509@q3_k_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **lmstudio-community/internlm2-math-plus-20b@q4_k_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **quietimpostor/nemotron-3-nano-reap-21b-a3b@mxfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **intel/qwen3-30b-a3b-instruct-2507-q2ks-mixed-autoround@q2_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **crucible-labs/gemma4-26b-a4b-reap-25@mixed**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **essentialai/rnj-1@q8_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **openai/gpt-oss-20b@mxfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/gpt-oss-20b-GGUF@q8_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **qwen/qwen3.5-9b@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **qwen/qwen3-14b@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **zai-org/glm-4.6v-flash@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/f2llm-v2-4b@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/f2llm-v2-1.7b@q8_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/f2llm-v2-1.7b@q4_k_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **freedomaisvr/gpt-oss-20b-nvfp4@nvfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **jetbrains/mellum2-12b-a2.5b-instruct@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/gemma-4-12b-it@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mmnga/moonlight-16b-a3b-instruct@q5_k_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **peculiar-ragdoll/tiel-coder-35b-a3b@iq3_xxs**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **empero-ai/qwythos-9b-claude-mythos-5-1m@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/darwin-28b-coder-i1@q3_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/gemma-4-31b-i1@iq3_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **ibm-granite/granite-4.0-h-tiny@q8_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **ibm-granite/granite-4.1-30b@q3_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/north-mini-code-1.0@iq3_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **internlm/internlm2_5-20b-chat@q4_k_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **noctrex/lfm2-24b-a2b_moe@mxfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/glm-4.7-flash@q3_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **ibm-granite/granite-4.1-8b@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **thebloke/em_german_13b_v01@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **thebloke/em_german_leo_mistral@q4_k_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/llama-3.3-8b-instruct-128k@q8_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **lmstudio-community/starcoder2-15b-instruct-v0.1@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **prism-ml/bonsai-27b@q1_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **freedomaisvr/gemma-4-12b-it-qat-nvfp4@nvfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/glm-4.7-flash-reap-23b-a3b@q4_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **noctrex/glm-4.7-flash-reap-23b-a3b_moe@mxfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **bartowski/utter-project_eurollm-22b-instruct-2512@q4_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mistralai/ministral-3-14b-reasoning@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/granite-4.2-30b-i1@iq3_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **byteshape/qwen3.6-35b-a3b@iq3_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **byteshape/qwen3.8-27b@iq4_xs**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **empero-ai/qwen3.8-9b-distill@q8_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **qwen/qwen2.5-coder-14b-instruct@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **jrell/qwen3.8-27b-i1-smaller@iq4_xs**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/qwen3.6-27b-mtp@iq3_xxs**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **tooltd/qwen3.6-27b-mini-xs-mtp-16gb-vram@iq4_xs**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **bytkim/qwen3.6-27b-mtp-pi-tune@q3_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
