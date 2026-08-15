# LM Studio Developer Documentation — Reference Links

Reference collection for LM Studio API parameters relevant to the benchmark project.
Collected: 2026-08-11.

---

## REST API — Load Model

**URL:** https://lmstudio.ai/docs/developer/rest/load

**Endpoint:** `POST /api/v1/models/load`

### Request Body Parameters

| Parameter                 | Type               | Description                                      |
|---------------------------|--------------------|--------------------------------------------------|
| `model`                   | string             | Unique identifier for the model to load          |
| `context_length`          | number (optional)  | Maximum number of tokens the model will consider |
| `eval_batch_size`         | number (optional)  | Number of input tokens per evaluation batch      |
| `flash_attention`         | boolean (optional) | Optimize attention computation (reduces memory, faster) |
| `num_experts`             | number (optional)  | Number of experts for MoE models                 |
| `offload_kv_cache_to_gpu` | boolean (optional) | Whether KV cache is offloaded to GPU             |
| `echo_load_config`        | boolean (optional) | If true, returns applied config in `load_config` |

### Response Fields

- `type`: `"llm" | "embedding"`
- `instance_id`: Unique identifier for the loaded instance
- `load_time_seconds`: Time taken to load
- `status`: `"loaded"`
- `load_config`: Applied configuration (only if `echo_load_config: true`)

### Key Finding

**`load_config.parallel`** — The actual number of parallel slots used by LM Studio (e.g., 4). This is determined by the JSON config file's `numParallelSessions` value, NOT by the API payload.

---

## REST API — Chat Completions (OpenAI Compatible)

**URL:** https://lmstudio.ai/docs/developer/openai-compat/chat-completions

**Endpoint:** `POST /v1/chat/completions`

### Supported Payload Parameters

| Parameter           | Description                |
|---------------------|----------------------------|
| `model`             | Model identifier           |
| `messages`          | Chat history               |
| `temperature`       | Sampling temperature       |
| `top_p`             | Nucleus sampling           |
| `top_k`             | Top-K sampling             |
| `max_tokens`        | Maximum tokens to generate |
| `stream`            | Enable streaming           |
| `stop`              | Stop strings               |
| `presence_penalty`  | Presence penalty           |
| `frequency_penalty` | Frequency penalty          |
| `logit_bias`        | Logit bias                 |
| `repeat_penalty`    | Repeat penalty             |
| `seed`              | Random seed                |

---

## TypeScript SDK — LLMLoadModelConfig

**URL:** https://lmstudio.ai/docs/typescript/api-reference/llm-load-model-config

### Parameters

| Parameter                     | Type                           | Description                         |
|-------------------------------|--------------------------------|-------------------------------------|
| `gpu`                         | GPUSetting                     | GPU distribution                    |
| `contextLength`               | number                         | Context length in tokens            |
| `ropeFrequencyBase`           | number                         | Custom RoPE base frequency          |
| `ropeFrequencyScale`          | number                         | RoPE frequency scaling              |
| `evalBatchSize`               | number                         | Evaluation batch size               |
| `flashAttention`              | boolean                        | Enable Flash Attention              |
| `keepModelInMemory`           | boolean                        | Prevent swapping from system memory |
| `seed`                        | number                         | Random seed for reproducibility     |
| `useFp16ForKVCache`           | boolean                        | Store KV cache in FP16              |
| `tryMmap`                     | boolean                        | Use memory-mapped file access       |
| `numExperts`                  | number                         | Number of MoE experts               |
| `llamaKCacheQuantizationType` | LLMLlamaCacheQuantizationType \| false | Key cache quantization      |
| `llamaVCacheQuantizationType` | LLMLlamaCacheQuantizationType \| false | Value cache quantization    |

### Key Finding

**NO `numParallelSessions` and NO `useUnifiedKvCache`** — These parameters are NOT part of the LM Studio API. 
They are exclusively set via JSON config files in `~/.lmstudio/.internal/user-concrete-model-default-config/`.

---

## TypeScript SDK — LLMPredictionConfigInput

**URL:** https://lmstudio.ai/docs/typescript/api-reference/llm-prediction-config-input

### Fields

| Field                   | Type                     | Description                          |
|-------------------------|--------------------------|--------------------------------------|
| `maxTokens`             | number \| false          | Maximum tokens to predict            |
| `temperature`           | number                   | Sampling temperature                 |
| `stopStrings`           | string[]                 | Stop generation at these strings     |
| `toolCallStopStrings`   | string[]                 | Stop for tool calls                  |
| `contextOverflowPolicy` | LLMContextOverflowPolicy | Behavior when context exceeds window |
| `structured`            | ZodType \| LLMStructuredPredictionSetting | Structured JSON output |
| `topKSampling`          | number                   | Top-K sampling limit                 |
| `repeatPenalty`         | number \| false          | Repetition penalty                   |
| `minPSampling`          | number \| false          | Minimum probability threshold        |
| `topPSampling`          | number \| false          | Nucleus sampling threshold           |
| `xtcProbability`        | number \| false          | XTC sampling probability             |
| `xtcThreshold`          | number \| false          | XTC probability threshold            |
| `cpuThreads`            | number                   | CPU threads for inference            |
| `draftModel`            | string                   | Draft model for speculative decoding |

---

## Critical Architecture Notes

### Parameters NOT in API (JSON Config Only)

The following parameters are **exclusively** set via LM Studio JSON config files and CANNOT be overridden via the REST or TypeScript APIs:

- `llm.load.numParallelSessions` — Number of parallel slots (np)
- `llm.load.useUnifiedKvCache` — Unified KV cache (UKV)
- `llm.load.contextLength` — Can be set via API OR config
- `llm.load.llama.kCacheQuantizationType` — K cache quant (e.g., q8_0, q5_1)
- `llm.load.llama.vCacheQuantizationType` — V cache quant (e.g., iq4_nl)

### JSON Config Structure

```json
{
  "operation": {
    "fields": [
      {"key": "llm.prediction.systemPrompt", "value": "..."},
      {"key": "llm.prediction.temperature", "value": 0.7}
    ]
  },
  "load": {
    "fields": [
      {"key": "llm.load.numParallelSessions", "value": 4},
      {"key": "llm.load.useUnifiedKvCache", "value": true},
      {"key": "llm.load.contextLength", "value": 32768},
      {"key": "llm.load.llama.kCacheQuantizationType", "value": {"checked": true, "value": "q5_1"}},
      {"key": "llm.load.llama.vCacheQuantizationType", "value": {"checked": true, "value": "iq4_nl"}}
    ]
  }
}
```

### Implication for Benchmarks

Since `numParallelSessions` and `useUnifiedKvCache` cannot be set via API:
1. JSON config files MUST contain the correct values before model load
2. The benchmark must ensure models are unloaded/reloaded to pick up config changes
3. The `model_registry.yaml` serves as the Single Source of Truth for these values
