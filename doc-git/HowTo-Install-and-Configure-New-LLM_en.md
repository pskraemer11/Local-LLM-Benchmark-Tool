# Installation Guide: Installing and Configuring a New LLM

This guide reflects the current provider-split architecture in the benchmark stack.

- GGUF headers are the technical source of truth for model architecture facts.
- `model_registry.yaml` is the source of truth for benchmark policy and provider-neutral runtime values.
- Provider artifacts such as LM Studio JSON configs, TabbyAPI config, or Unsloth server arguments are derived runtime data.

## 1. Resolution model

| Layer | Owns | Examples |
| --- | --- | --- |
| GGUF header | Immutable technical facts | `n_layers`, `hidden_dim`, max context, embedded chat template |
| `model_registry.yaml` | Benchmark policy and neutral runtime settings | reasoning, capabilities, blueprint, truncation, KV policy, template policy |
| Provider adapter | Provider-specific runtime behavior | LM Studio JSON, TabbyAPI, Unsloth `llama-server.exe` args |

Important:

- GGUF headers define the model architecture limits.
- `model_registry.yaml` defines the benchmark policy and the runtime decisions that are independent of a specific provider.
- LM Studio JSON configs are not a second source of truth. They are LM Studio-specific runtime artifacts and can be regenerated.
- The benchmark runner resolves models through `ModelRegistry` and the provider adapter, not by reading LM Studio metadata directly.

## 2. Recommended onboarding flow

1. Make sure the GGUF is available in a folder the chosen provider can see.
2. Add or update the registry entry in `doc-git\model_registry.yaml` if needed.
3. Run:

```powershell
python src\registry_tool.py pipeline full
```

This is the canonical one-shot maintenance command for a new or changed model. It:

- resolves the registry entry
- reads the GGUF header once for architecture facts
- classifies reasoning, capabilities, blueprint, and truncation
- derives runtime values such as context length, KV cache policy, and provider-specific settings
- writes the provider artifacts for the current stack
- validates the result

If the model is already known and only needs a partial refresh, the lower-level commands still exist, but `pipeline full` is the safest default.

## 3. What is derived from where

| Field or decision | Source | Notes |
| --- | --- | --- |
| `n_layers` | GGUF header | Read automatically from the model file |
| `hidden_dim` | GGUF header | Read automatically from the model file |
| `context_length` | GGUF + registry policy | Derived from architecture and runtime policy |
| `reasoning` / `thinking` | GGUF chat template | No more keyword fallback for the default path |
| `capabilities` | Registry classification | For example coding, text, vision, audio exclusions |
| `blueprint` | Registry classification | Derived from reasoning plus capability hints |
| `truncation` | Registry / context policy | Based on effective context length |
| `num_parallel` | Fixed policy | No longer a registry field; current policy is 4 for sample sizes >= 10, otherwise 1 |
| `k_cache` / `v_cache` | Registry policy | Used to derive the runtime settings |
| `useUnifiedKvCache` | VRAM formula | Derived from model size, KV settings, and available VRAM |

## 4. Provider-specific behavior

### LM Studio

- LM Studio JSON configs under `~\.lmstudio\.internal\user-concrete-model-default-config\` are the LM Studio runtime artifact.
- LM Studio Hub `model.yaml` and `.jinja` files under `~\.lmstudio\hub\models\...` are LM Studio-only overlays.
- They are useful for UI defaults and explicit chat-template overrides, but they do not replace `model_registry.yaml`.

### TabbyAPI

- TabbyAPI is used through the OpenAI-compatible surface.
- The runner consumes the same registry-resolved benchmark policy, but the server/runtime specifics come from the TabbyAPI side.

### Unsloth server

- Unsloth is treated as a separate local server provider.
- The benchmark runner starts `llama-server.exe` directly for this path.
- Runtime defaults favor short execution time and high GPU utilization, for example `--parallel 4` and maximal GPU layer offload.
- If VRAM is tight, the derived KV-quant, unified KV cache, or context-length policy is adjusted before launch.

## 5. Special cases

Some model families need an explicit template override or additional runtime hints. This includes, for example, GPT-OSS Harmony-style templates, Gemma 4 variants, and GLM variants with structured output behavior.

For a known Unsloth GGUF model, use:

```yaml
template_policy: explicit_file
template_variant: unsloth_harmony_fix
template: gpt-oss-20b-template_unsloth.jinja
```

That is the preferred way to pin the template for a model where the embedded GGUF template is not the one we want to benchmark.

Legacy registry `template:` entries should be treated as fallback only.

Blacklisted families such as embed, OCR, vision, audio, RAG, and other non-benchmark model groups are skipped by the registry pipeline.

## 6. Reinstall, remove, or quarantine

If a model was deleted and then reinstalled, rerun:

```powershell
python src\registry_tool.py pipeline full
```

To remove only the registry entry:

```powershell
python src\registry_tool.py rm <model-key>
```

To remove the registry entry and the associated files:

```powershell
python src\registry_tool.py rm <model-key> --delete-files --yes
```

To quarantine missing models instead of deleting them immediately:

```powershell
python src\registry_tool.py quarantine-missing --dry-run
```

## 7. Quick commands

```powershell
python src\registry_tool.py pipeline full
python src\registry_tool.py pipeline
python src\registry_tool.py compare
python src\registry_tool.py validate
python src\registry_tool.py fill-arch
python src\registry_tool.py fill-reasoning
python src\registry_tool.py rm <model-key> [--delete-files] [--yes]
```

For a model that is already registered and only needs a benchmark run, the benchmark launcher is:

```powershell
python src\run_benchmarks.py --help
```
