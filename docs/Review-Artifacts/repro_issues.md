# Repro-Issues: model_registry.yaml vs. LM Studio Hub

Generated automatically: 2026-10-27 15:02:58

Source of truth for model facts are the GGUF files (immutable).
The `model_registry.yaml` is editable (python programs/manual) and is
checked here against the Hub `model.yaml` (`metadataOverrides`), which is
shipped by LM Studio and never touched anywhere in the process.

## Validate summary

- **Total issues (validate):** 4
- `template_missing_file`: 0
- `template_missing_config`: 0
- `missing_reasoning`: 0
- `missing_capabilities`: 0
- `missing_blueprint`: 0
- `sampling_invalid`: 0
- `sampling_research_status_invalid`: 0
- `quantization_status_invalid`: 0
- `identity_collision`: 0
- `publisherless_identity_ambiguity`: 4
- `registry_no_config`: 0
- `local_config_pair_invalid`: 0
- `local_binding_missing`: 0
- `local_companion_invalid`: 0
- `reasoning_arch_mismatch`: 0
- `config_context_drift`: 0
- `config_experts_drift`: 0
- `runtime_experts_missing`: 0
- `runtime_experts_exceed_max`: 0
- `config_np_ukv_drift`: 0
- `config_context_too_small`: 0
- `gguf_header_drift`: 0

## Hub deviations (Registry vs. model.yaml)

No deviations between registry and hub model.yaml.

## Hub notes (no model.yaml in local hub)

70 entries have no local hub model.yaml (no comparison possible, manual GGUF check required):

- **mradermacher/qwen3-coder-reap-25b-a3b-i1@q3_k_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/phi-4@q5_k_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **tiiuae/falcon3-10b-instruct@q8_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/januscoder-14b@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/f2llm-v2-4b@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/f2llm-v2-1.7b@q8_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/darwin-28b-coder-i1@q3_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **ibm-granite/granite-4.0-h-tiny@q8_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/glm-4.7-flash@q3_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **thebloke/em_german_13b_v01@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **bartowski/utter-project_eurollm-22b-instruct-2512@q4_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/granite-4.2-30b-i1@iq3_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **byteshape/qwen3.8-27b@iq4_xs**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **byteshape/qwen3.5-9b@q5_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **nerdsking/nerdsking-python-coder-7b-i@q8_0_i**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/gemma-4-31b-i1@iq3_xs**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **ibm-granite/granite-4.2-8b@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **bartowski/zai-org_glm-4.6v-flash@q6_k_l**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/gemma-4-26b-a4b-it@iq3_xxs**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **intel/qwen3.8-27b-q2ks-autoround@q2_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **byteshape/devstral-small-2-24b-instruct-2512@iq4_xs**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **gguf-org/muse-glimmer-30b@nvfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **prism-ml/ternary-bonsai-27b@q2_g64**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **vinpix/ternary-bonsai-27b-stock-mtp@q2_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **byteshape/qwen3.6-35b-a3b@iq3_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/industrialcoder-i1@iq3_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **lmstudio-community/codestral-22b-v0.1@iq4_xs**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **lmstudio-community/phi-4@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **bucoid/qwen3.8-27b-iq4-xs-mtp-16gb-vram@iq4_xs**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **jrell/qwen3.8-27b-i1-iq4_xs-gguf-smaller@iq4_xs**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **lmstudio-community/bonsai-27b@q1_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **lmstudio-community/qwen3-14b@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **lmstudio-community/rnj-1-instruct@q8_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/qwen3.8-27b@iq3_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **noctrex/ernie-4.5-21b-a3b-pt_moe@mxfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **jetbrains/mellum2-12b-a2.5b-instruct@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **noctrex/glm-4.7-flash-reap-23b-a3b_moe@mxfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **freedomaisvr/gpt-oss-20b@nvfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **freedomaisvr/ministral-3-14b-reasoning-2512@nvfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **freedomaisvr/mimo-v2.6-distill-qwen-9b@nvfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **zerodigest/qwen3.8-27b-ymq-mtp@?**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **jetbrains/mellum2-12b-a2.5b-thinking_moe@mxfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **noctrex/nemotron-cascade-14b-thinking@mxfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **empero-ai/qwen3.8-9b-distill@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **qwen/qwen2.5-coder-14b-instruct@q5_k_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **freedomaisvr/gemma-4-12b-it-qat@nvfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **quietimpostor/nemotron-3-nano-reap-21b-a3b@mxfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **noctrex/ernie-4.5-21b-a3b-thinking_moe@mxfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/north-mini-code-1.0@iq3_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/gemma-4-12b-it-qat@q4_k_xl**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **byteshape/qwen3.8-27b@iq3_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **jinaai/jina-reranker-v3.5@q8_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/gemma-4-e4b-it-qat@q4_k_xl**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/glm-4.7-flash-reap-19-i1@iq4_xs**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **freedomaisvr/qwythos-9b-claude-mythos-5-1m@nvfp4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **sleepyeldrazi/nemotron-3.5-lightning-30b-a3b-reap-20b-lora-iq4nl@iq4_nl**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **bucoid/qwen3.8-27b-xs-mtp-16gb-vram@iq4**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **jrell/qwen3.8-27b-i1-smaller@iq4_xs**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **bartowski/nvidia_nvidia-nemotron-nano-9b-v2@q8_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **ornith-ai/ornith-1.5-9b@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mradermacher/nemotron-cascade-14b-thinking-i1@q5_k_s**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/muse-glimmer-30b@iq2_m**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **google/gemma-4-26b-a4b-it-qat@q4_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/gemma-4-12b-it@q5_k_xl**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **bartowski/nvidia_nvidia-nemotron-nano-12b-v2@q6_k_l**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **gpustack/bge-reranker-v2-m3@q8_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **lmstudio-community/glm-4.6v-flash@q6_k**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **mistral/em_german_mistral_v01_gguf@q4_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **unsloth/qwen3.6-35b-a3b-mtp@iq4_xs**: quant variant without its own model.yaml (base model in hub carries the architecture info)
- **google/gemma-4-12b-it-qat@q4_0**: quant variant without its own model.yaml (base model in hub carries the architecture info)
