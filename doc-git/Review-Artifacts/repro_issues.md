# Repro-Issues: model_registry.yaml vs. LM Studio Hub

Generated automatically: 2026-08-06 23:28:05

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
- `registry_no_config`: 0
- `reasoning_arch_mismatch`: 0
- `config_context_drift`: 0
- `config_np_ukv_drift`: 0
- `config_context_too_small`: 0

## Hub deviations (Registry vs. model.yaml)

No deviations between registry and hub model.yaml.

## Hub notes (no model.yaml in local hub)

57 entries have no local hub model.yaml (no comparison possible, manual GGUF check required):

- **mistralai/codestral-22b-v0.1**: no hub model.yaml found (registry has GGUF size)
- **unsloth/phi-4**: no hub model.yaml found (registry has GGUF size)
- **mradermacher/deepseek-coder-33b-instruct**: no hub model.yaml found (registry has GGUF size)
- **unsloth/devstral-small-2-24b-instruct-2512**: no hub model.yaml found (registry has GGUF size)
- **unsloth/ernie-4.5-21b-a3b-pt@iq4_nl**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **tiiuae/falcon3-10b-instruct**: no hub model.yaml found (registry has GGUF size)
- **mradermacher/gemma-4-19b-a4b-it-reap-i1@q4_k_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/gemma-4-26b-a4b-it-i1@iq4_xs**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/gemma-4-26b-a4b-it@iq3_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **ibm-granite/granite-4.0-h-tiny**: no hub model.yaml found (registry has GGUF size)
- **ibm-granite/granite-4.1-30b**: no hub model.yaml found (registry has GGUF size)
- **unsloth/januscoder-14b**: no hub model.yaml found (registry has GGUF size)
- **jetbrains/mellum2-12b-a2.5b-instruct**: no hub model.yaml found (registry has GGUF size)
- **lmstudio-community/ministral-3-14b-instruct-2512**: no hub model.yaml found (registry has GGUF size)
- **mradermacher/kimi-linear-reap-35b-a3b-instruct.i1**: no hub model.yaml found (registry has GGUF size)
- **mradermacher/nemotron-cascade-14b-thinking**: no hub model.yaml found (registry has GGUF size)
- **nerdsking/nerdsking-python-coder-7b-i**: no hub model.yaml found (registry has GGUF size)
- **unsloth/qwen3-30b-a3b-instruct-2507**: no hub model.yaml found (registry has GGUF size)
- **unsloth/qwen3-coder-30b-a3b-instruct**: no hub model.yaml found (registry has GGUF size)
- **mradermacher/qwen3-coder-reap-25b-a3b-i1**: no hub model.yaml found (registry has GGUF size)
- **mradermacher/qwen3-coder-reap-25b-a3b**: no hub model.yaml found (registry has GGUF size)
- **unsloth/north-mini-code-1.0**: no hub model.yaml found (registry has GGUF size)
- **qwen/qwen2.5-coder-14b-instruct@q5_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **qwen/qwen2.5-coder-14b-instruct@q5_k_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **qwen/qwen2.5-coder-14b-instruct@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **Qwen/Qwen3.5-9B-GGUF@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/qwen3.6-27b**: no hub model.yaml found (registry has GGUF size)
- **unsloth/qwen3.6-27b-mtp**: no hub model.yaml found (registry has GGUF size)
- **mradermacher/qwen3.6-27b-i1**: no hub model.yaml found (registry has GGUF size)
- **mradermacher/qwen3.6-28b-reap-i1@iq3_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/qwen3.6-28b-reap-i1@q3_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **bartowski/mistralai_magistral-small-2509**: no hub model.yaml found (registry has GGUF size)
- **lmstudio-community/deepseek-r1-distill-qwen-14b**: no hub model.yaml found (registry has GGUF size)
- **gabriellarson/mamba-codestral-7b-v0.1**: no hub model.yaml found (registry has GGUF size)
- **tiiuae/falcon3-mamba-7b-instruct**: no hub model.yaml found (registry has GGUF size)
- **internlm/internlm2_5-20b-chat**: no hub model.yaml found (registry has GGUF size)
- **lmstudio-community/deepseek-coder-v2-lite-instruct**: no hub model.yaml found (registry has GGUF size)
- **lmstudio-community/internlm2-math-plus-20b**: no hub model.yaml found (registry has GGUF size)
- **google/gemma-4-12b-it-qat**: no hub model.yaml found (registry has GGUF size)
- **quietimpostor/nemotron-3-nano-reap-21b-a3b**: no hub model.yaml found (registry has GGUF size)
- **intel/qwen3-30b-a3b-instruct-2507-q2ks-mixed-autoround**: no hub model.yaml found (registry has GGUF size)
- **intel/qwen3-30b-a3b-thinking-2507-q2ks-mixed-autoround**: no hub model.yaml found (registry has GGUF size)
- **intel/qwen3-coder-30b-a3b-instruct-q2ks-mixed-autoround**: no hub model.yaml found (registry has GGUF size)
- **intel/mirothinker-v1.5-30b-q2ks-mixed-autoround**: no hub model.yaml found (registry has GGUF size)
- **noctrex/ernie-4.5-21b-a3b-pt_moe@mxfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **jetbrains/mellum2-12b-a2.5b-thinking_moe**: no hub model.yaml found (registry has GGUF size)
- **noctrex/lfm2-24b-a2b_moe**: no hub model.yaml found (registry has GGUF size)
- **unsloth/glm-4.7-flash**: no hub model.yaml found (registry has GGUF size)
- **unsloth/glm-4.7-flash-reap-23b-a3b**: no hub model.yaml found (registry has GGUF size)
- **noctrex/ernie-4.5-21b-a3b-pt_moe**: no hub model.yaml found (registry has GGUF size)
- **mradermacher/gemma-4-19b-a4b-it-reap-i1**: no hub model.yaml found (registry has GGUF size)
- **ibm-granite/granite-4.1-8b**: no hub model.yaml found (registry has GGUF size)
- **mradermacher/gemma-4-26b-a4b-it-i1**: no hub model.yaml found (registry has GGUF size)
- **bartowski/google_gemma-4-26b-a4b-it**: no hub model.yaml found (registry has GGUF size)
- **unsloth/gemma-4-26b-a4b-it**: no hub model.yaml found (registry has GGUF size)
- **unsloth/ernie-4.5-21b-a3b-pt**: no hub model.yaml found (registry has GGUF size)
- **unsloth/gemma-4-12b-it-qat@q4_k_xl**: quant variant without its own model.yaml (base model in hub carries the architecture info)
