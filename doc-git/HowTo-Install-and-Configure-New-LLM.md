## Installation Guide: Installing and Configuring a New LLM

### Phase A – LM Studio handles automatically

| Step                                                   | What happens                                                  | Where                                                                               |
|--------------------------------------------------------|---------------------------------------------------------------|-------------------------------------------------------------------------------------|
| ① Import GGUF / `lms get`                              | File lands in `~/.lmstudio/models/{publisher}/{name}/`        |
| ② First load of the model                              | LMS generates JSON config                                     | `~/.lmstudio/.internal/user-concrete-model-default-config/{publisher}/{dir}/*.json` |
| ③ If `hub/models/{pub}/{model}/model.yaml` exists       | Its `config.operation.fields` are merged into the JSON        |
| ④ If `hub/models/{pub}/{model}/*.jinja` exists          | Its chat template overrides the embedded GGUF template        |

### Phase B – Manual check & our pipeline

```bash
# 1. Check: Is the model in the registry?
grep -l "model-name" doc-git/model_registry.yaml
```

**Case 1: Model is already in the registry**
→ `sync_model_configs.ps1 -FullSync` or manually:
```
python assemble_blueprint.py classify   # Update classification
python assemble_blueprint.py assemble   # Write prompt to JSON
python assemble_blueprint.py validate   # Syntax check
```

**Case 2: New model – create entry in registry**

Easiest way: `sync_model_configs.ps1 -AutoAdd` detects the model via `lms ls` and registers it automatically. Manual:

`doc-git/model_registry.yaml` – insert entry (alphabetical position):
```yaml
My-New-Model-8B:
  publisher: "publisher"
  hf_url: "https://huggingface.co/publisher/My-New-Model-8B"
  quants: [Q4_K_M, Q6_K]
  arch: "Llama Dense"
  k_cache: "q8_0"
  v_cache: "iq4_nl"
  offload: 1
  num_parallel: 1
  # notes, reasoning, capabilities, blueprint, truncation, context_length
  # are set automatically by classify + registry_tool.py
```

Then:
```
python registry_tool.py sync           # Full maintenance: add → fill-arch → configs → sync-from-configs → sync-ctx → fill-ctx → fmt
                                       #   add:        new models from LMS into registry (incl. GGUF architecture data)
                                       #   fill-arch:  n_layers/hidden_dim from GGUF headers for existing entries
                                       #   configs:    load.fields (offload, np, useUnifiedKvCache) into JSON configs
                                       #   sync-from-configs:  JSON→Registry (overwrite)
                                       #   sync-ctx:   context_length from JSON configs (missing only)
                                       #   fill-ctx:   remaining context_length via formula
                                       #   fmt:        normalize blank lines
python assemble_blueprint.py classify   # → reasoning, blueprint, truncation, capabilities set
python assemble_blueprint.py assemble   # → Prompt written
```

**All info that classify + registry_tool.py determine automatically:**

| Field              | Source                                                      | Example                                      |
|--------------------|-------------------------------------------------------------|----------------------------------------------|
| `reasoning`        | Model name (keywords: r1, thinking, qwq, reasoning, cot)   | `Ministral-...-Reasoning` → `thinking`       |
| `capabilities`     | Model name (vl/vision/ocr, coder/code)                     | `qwen2.5-coder-14b` → `[coding, text]`       |
| `blueprint`        | From reasoning + capabilities                               | `thinking` → `reasoning_assistant`           |
| `truncation`       | contextLength from JSON config                              | `16384` (≥8192) → `medium`                   |
| `offload`          | Default 1 (full GPU offload) at `add` / `fill-ctx`          | `1`                                           |
| `num_parallel`     | MoE=4 (except ERNIE→1), Dense=1, GPT-OSS=4                  | `4` (MoE) / `1` (Dense) / `1` (ERNIE)        |
| `k_cache`          | `q8_0` (default), Gemma-4/GPT-OSS = `f16`                  | `q8_0`, `f16`                                |
| `v_cache`          | `iq4_nl` (default), Gemma-4/GPT-OSS = `f16`                | `iq4_nl`, `q5_1`, `f16`                      |
| `n_layers`         | **Automatically from GGUF header** via `add`/`fill-arch`    | `49` (North Mini Code), `64` (Qwen3.6-27B)   |
| `hidden_dim`       | **Automatically from GGUF header** via `add`/`fill-arch`    | `2048` / `5120`                               |
| `context_length`   | Formula from `file_size_bytes`, `num_parallel`, KV quant    | `16384` (default when size is missing)        |
| `useUnifiedKvCache`| **VRAM formula** (see below) – written to JSON via `configs`| `false` / `true`                              |

**VRAM formula for useUnifiedKvCache (since 17.07.):**
```
model_gb     = file_size / 1_000_000_000
kv_gb        = n_layers × hidden_dim × 2 × kv_bytes × context_length / 1_000_000_000
total_gb     = model_gb + kv_gb × num_parallel
useUnifiedKvCache = total_gb ≥ 14.5   # ON when VRAM is tight (≥14.5 GB)
```
With np=1 or missing architecture data: `useUnifiedKvCache = model_gb ≥ 9.0` (old heuristic).

### Phase C – Special cases only

**When do I need a Jinja template override?**

Only if the model has special chat template tokens not embedded in the GGUF. The only case so far: **Gemma-4** with `<|think|>` token.

```bash
# Create Jinja override (if necessary)
mkdir -p ~/.lmstudio/hub/models/{publisher}/{model-name}/
# File: {model-name}-template_minijinja.jinja
```

**When do I need a model.yaml?**

| Use Case                                                | Codebase Example                                                                  |
|---------------------------------------------------------|-----------------------------------------------------------------------------------|
| `customFields` (UI dropdown, e.g. Reasoning-Effort)     | `openai/gpt-oss-20b/model.yaml` → `reasoningEffort`                               |
| `config.operation.fields` (default temperature, parsing)| `essentialai/rnj-1/model.yaml` → `reasoning.parsing` with `THOUGHT:/RESPONSE:`    |
| `base` keys (multiple quants → one base model)          | `mistralai/codestral-22b-v0.1/model.yaml` → lmstudio-community-GGUF               |

⚠️ **Caution (from the chronicle, line 2159):** `model.yaml` creates a **virtual model instance** in LMS. If the same GGUF is already loaded as a physical instance → **HTTP-500 conflict** (two instances on the same file). Solution: use `model.yaml` only for models without a physical GGUF, or use alternative base keys.

### Phase D – After GGUF reinstallation (deleted + reloaded)

```
1. Delete GGUF            # Config is preserved
2. Re-import GGUF          # Old config is recognized again
3. python registry_tool.py sync           # Sync configs + registry
4. python assemble_blueprint.py classify  # Update classification
5. python assemble_blueprint.py assemble  # Rewrite prompt
```
→ Done. The old `model.yaml` (if present) is updated on `lms clone`/`lms get`, not on manual import.

### Cheat Sheet

```bash
# Full maintenance (registry + configs)
python registry_tool.py sync

# Fill in architecture data from GGUF headers (n_layers, hidden_dim)
python registry_tool.py fill-arch

# np correction for all entries (after architecture changes)
python registry_tool.py fix-np

# Recalculate context_length (e.g. after np change)
python registry_tool.py fix-ctx

# Write useUnifiedKvCache, offload, np from registry into JSON configs
python registry_tool.py configs

# Write JSON configs back to registry (overwrite)
python registry_tool.py sync-from-configs

# Compare registry vs LMS vs configs
python registry_tool.py compare

# Standard case (model known)
python assemble_blueprint.py classify && assemble && validate

# New model – automatically via sync_model_configs.ps1
.\sync_model_configs.ps1 -AutoAdd
# or manually:
# → edit registry.yaml (enter publisher, arch, k/v_cache, offload, num_parallel)
python registry_tool.py sync          # incl. fill-arch + configs in pipeline
python assemble_blueprint.py classify  # fills reasoning, capabilities, blueprint, truncation
python assemble_blueprint.py assemble

# Full sync incl. prompt assembly
.\sync_model_configs.ps1 -FullSync

# Preview only (without writing)
python assemble_blueprint.py preview

# Validation after changes
python assemble_blueprint.py validate
```
