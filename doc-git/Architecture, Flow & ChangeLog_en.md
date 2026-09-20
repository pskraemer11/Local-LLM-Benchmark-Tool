# Architecture and User Workflow

Status: 2026-09-19
Audience: first-time users, maintainers, and reviewers
Scope: model onboarding, Registry maintenance, prompt assembly, benchmark
execution, providers, and result data

This document explains how the repository works from the outside in. It is
organized around the two programs a user normally calls from PowerShell:

- src/registry_tool.py prepares the model and prompt metadata.
- src/run_benchmarks.py executes the benchmark run.

The README is the short operational guide. This document explains ownership
rules, data flow, and the reasons behind the workflow.

## 1. Mental model

The repository has two phases:

1. Preparation: discover models, establish a canonical identity, collect
   immutable GGUF facts, assign benchmark policy, and validate prompts.
2. Execution: read the prepared Registry, load the model through a provider,
   run tasks, and write reproducible result artifacts.

The central rule is:

> The Registry describes benchmark policy. LM Studio config JSONs describe
> backend-local runtime state. A normal sync or benchmark run must not
> silently overwrite the latter.

High-level flow:

~~~text
LM Studio inventory ─────┐
                         ├─ registry_tool.py ──> model_registry.yaml
GGUF headers/files ──────┘          │
                                    ├─> blueprint classification
blueprint_definitions.yaml ─────────┘
                                    │
                                    └─> prompt preview and validation

model_registry.yaml + provider ──> run_benchmarks.py
                                      │
                                      ├─> load / readiness / unload
                                      ├─> Custom, EvalPlus, LM-Eval, Agentic
                                      └─> CSV results ──> consolidation
~~~

## 2. Repository data structure

### 2.1 Authoritative and derived data

| Data                                           | Authority                                      | Used by                                        | Write policy                                   |
| ---------------------------------------------- | ---------------------------------------------- | ---------------------------------------------- | ---------------------------------------------- |
| doc-git/model_registry.yaml                    | Benchmark policy and provider-neutral metadata | Registry tool, launcher, model resolution      | Updated by registry maintenance                |
| GGUF header and filename                       | Model architecture and native limits           | Registry tool, resolver                        | Read-only source                               |
| doc-git/blueprint_definitions.yaml             | Prompt blueprint definitions                   | Assembly and validation                        | Maintained as project policy                   |
| doc-git/Jinja-Chat-Templates/                  | Explicit template files                        | Prompt assembly                                | Maintained as project assets                   |
| LM Studio config JSONs                         | LM Studio runtime state                        | Drift checks and explicit runtime repair       | Never written by ordinary sync/full            |
| simple_evals/                                  | Local custom benchmark tasks                   | Custom pipeline                                | Benchmark input; do not rewrite during runs    |
| EvalPlus/lm-eval/tool-eval-bench data          | External benchmark tasks                       | Their respective pipelines                     | Managed by the dependency/tool                 |
| ergebnisse/                                    | Run outputs                                    | Human review and consolidation                 | Runtime output, normally ignored               |

### 2.1.1 GGUF model root resolution

Local GGUF discovery uses one shared ordered-root contract. By default,
`D:\LLM-Modelle\models` is the primary root and
`C:\Users\<user>\.lmstudio\models` is the compatible fallback. This keeps
older LM Studio installations usable while making the dedicated model volume
the authoritative first lookup location.

`GGUF_MODEL_ROOT` can select one explicit root for an isolated or alternative
installation. The existing `UNSLOTH_MODEL_ROOT` and
`LMSTUDIO_MODELS_DIR` variables remain supported as compatibility overrides.
An explicit override scans only its selected directory. Resolved paths are
canonicalized so a Windows Junction does not produce duplicate candidates;
when both roots expose the same model identity, the primary-root candidate
wins. The registry tool, local resolver, benchmark runner, and Unsloth
provider all use this same order.

The important separation is between Registry policy and LM Studio runtime
artifacts. A GUI setting such as a system prompt, chat template, KV-cache
quantization, or parallel-session setting is not automatically a global
benchmark policy.

### 2.2 Canonical model identity

Every benchmarkable Registry entry uses:

~~~text
publisher/model@quant
~~~

All three components matter:

- publisher disambiguates Hub publishers with the same base name;
- model identifies the base model;
- quant identifies the GGUF variant.

The matching code normalizes spelling differences such as dots, underscores,
and quant suffix separators, but it does not intentionally erase publisher or
quantization identity. This prevents one publisher's config from being
assigned to another publisher's model with the same basename.

### 2.3 Registry entry shape

A typical Registry entry contains:

~~~yaml
publisher/model@q4_k_m:
  publisher: publisher
  hf_url: https://huggingface.co/...
  pub_url: https://...
  quants: Q4_K_M
  arch: dense
  sampling:
    coding:
      temperature: 0.2
      top_p: 1.0
    thinking:
      enabled: true
      temperature: 0.6
      top_p: 0.95
  reasoning: instruct
  capabilities: coding, text
  blueprint: coding_agent
  truncation: full
  context_length: 32768
  max_context_length: 131072
  offload: 1.0
  useUnifiedKvCache: false
  n_layers: 32
  hidden_dim: 4096
  file_size_bytes: 9000000000
~~~

The main field groups are:

- identity: Registry key, publisher, URLs, and quantization;
- benchmark policy: sampling, reasoning, capabilities, blueprint, truncation,
  and stop behavior;
- hardware/runtime derivation: context policy, offload, KV-cache policy,
  architecture, and file size;
- provenance: sampling status, source URLs, and evidence.

num_parallel is not a per-model Registry field. The launcher uses a fixed
benchmark policy based on sample size: four slots for sample sizes of at
least 10, otherwise one slot, subject to provider capabilities.

## 3. Model onboarding workflow

### 3.1 What happens after downloading a model

1. LM Studio makes the GGUF and its local inventory visible.
2. registry_tool.py reads the current LMS inventory.
3. Shared filters keep only models supported by local benchmark tests.
4. The model gets the canonical publisher/model@quant identity.
5. GGUF headers provide architecture and native context facts.
6. Sampling onboarding searches the Hugging Face card and bounded official
   documentation paths once.
7. Blueprint and reasoning classification assigns the prompt policy.
8. Validation reports missing fields, identity mismatches, and ownership drift.

OCR and embedding models are deliberately excluded. Their local benchmark
pipelines are not implemented in this repository, so adding them to the
Registry would create entries that the launcher cannot evaluate correctly.

MTP drafter companions, mmproj files, and iMatrix support files are also
filtered as auxiliary files rather than standalone benchmark models. A real
standalone model whose name contains mtp remains eligible when it is not a
small companion file.

### 3.2 The three pipeline modes

The commands share names but have different scopes.

#### pipeline status

~~~text
py -3.12 src\registry_tool.py pipeline status
~~~

status is a read-only comparison:

- query the benchmarkable LMS models;
- show the model count;
- compare Registry, LMS inventory, and config JSON identities.

No Registry or LM Studio config JSON is written.

#### sync

~~~text
py -3.12 src\registry_tool.py sync
~~~

sync calls the direct maintenance function. It:

- adds new eligible models;
- performs one-time sampling onboarding;
- fills quantization, size, architecture, reasoning, and context metadata;
- reconciles GGUF-owned fields;
- reads LM Studio config values in report mode;
- normalizes the Registry file.

It may write model_registry.yaml. It does not write LM Studio config JSONs.

#### pipeline sync

~~~text
py -3.12 src\registry_tool.py pipeline sync
~~~

pipeline sync is a wrapper with three stages:

1. LMS count and compare report;
2. the complete direct sync;
3. classify_registry().

The classification stage writes Registry fields such as reasoning,
capabilities, blueprint, truncation, and custom_template. Therefore
pipeline sync can change more Registry fields than direct sync.

It does not run prompt preview or validation and it does not apply the
blocking drift exit rule.

#### pipeline full

~~~text
py -3.12 src\registry_tool.py pipeline full
~~~

pipeline full performs pipeline sync and then:

1. reports non-installed Registry models in quarantine dry-run mode;
2. runs a read-only prompt assembly preview;
3. validates prompt and template completeness;
4. validates Registry drift and field ownership.

The assembly is explicitly preview-only. The GLM config patch is skipped and
LM Studio config JSONs remain unchanged. Open blocking ownership drift causes
exit code 1 unless --ignore-drift is passed. The flag changes the exit
behavior only; it is not an automatic repair.

### 3.3 Direct maintenance commands

The pipeline modes are the preferred user interface, but lower-level
commands remain useful for focused repairs:

| Command                                                   | Purpose                                                   | Writes config JSONs?                                      |
| --------------------------------------------------------- | --------------------------------------------------------- | --------------------------------------------------------- |
| compare                                                   | Report Registry/LMS/config differences                    | No                                                        |
| validate --ci                                             | Headless consistency validation                           | No                                                        |
| fill-quant                                                | Fill missing quantization from GGUF names                 | No                                                        |
| fill-arch                                                 | Read architecture values from GGUF headers                | No                                                        |
| fill-reasoning                                            | Detect reasoning from GGUF templates                      | No                                                        |
| sync-from-configs                                         | Report config-derived drift; --write is explicit          | No by default                                             |
| sync-templates                                            | Explicitly copy missing prompt templates into configs     | Yes                                                       |
| sync-template-from-gguf                                   | Explicitly copy an embedded GGUF template into one config | Yes                                                       |
| patch-reasoning-effort                                    | Explicit GLM runtime-config patch                         | Yes                                                       |

The explicit write commands are intentionally separate from normal sync and
full validation.

## 4. Sampling onboarding architecture

Sampling values are benchmark policy, not transient GUI state. The researcher
checks:

- the linked Hugging Face model card;
- base-model metadata where relevant;
- bounded official documentation paths;
- explicit generation examples and recommended defaults.

Accepted values pass plausibility checks and must form a coherent sampling
profile. The Registry records:

- category/profile values;
- sampling_research_status;
- timestamp;
- source URLs;
- field-level evidence and excerpts.

Typical statuses are confirmed, unresolved, conflict, and not_found.
Terminal statuses prevent repeated network searches on every sync. Use:

~~~text
py -3.12 src\registry_tool.py sync --refresh-sampling
~~~

for an explicit retry. The registry-sampling-review workflow is the manual
escalation path for unresolved or conflicting cases. Benchmark execution does
not use the network for sampling research.

At runtime the launcher resolves:

1. a confirmed Registry sampling cell for the model/category/profile;
2. thinking-specific Registry values when thinking mode is active;
3. category defaults from benchmark_config.py as fallback.

The old pattern of reading arbitrary GUI temperature values during a
benchmark is intentionally not used.

## 5. Prompt and blueprint architecture

blueprint_definitions.yaml is the source of truth for system-prompt
construction. It contains:

- blueprint descriptions and roles;
- reusable prompt modules;
- model-family template mappings;
- reasoning parsing and stop-string policy.

assemble_blueprint.py performs three logically separate operations:

1. classify a Registry entry;
2. assemble a prompt from the selected blueprint;
3. validate the expected template and prompt artifacts.

pipeline full uses preview mode. It computes what would be assembled but does
not write the LM Studio JSONs. Explicit commands are required for
runtime-artifact repair.

This separation prevents a routine Registry maintenance run from deleting or
replacing a GUI system prompt, chat template, or KV-cache setting.

## 6. run_benchmarks.py architecture

### 6.1 Responsibilities

run_benchmarks.py is the only normal entry point that initiates model loading
and unloading. It:

1. parses CLI flags and an optional run-spec YAML;
2. loads eligible Registry entries;
3. resolves model and benchmark selections;
4. checks Registry reasoning and prompt prerequisites;
5. selects a provider;
6. loads a model and waits for readiness;
7. dispatches each benchmark;
8. writes intermediate and final summaries;
9. unloads the model when supported.

The launcher passes one provider/model context into the benchmark pipelines.
Benchmark subprocesses do not manage the server lifecycle themselves.

### 6.2 Provider boundary

The provider facade handles model operations:

~~~text
run_benchmarks.py
    └─ model_manager.py
        └─ Provider
            ├─ lmstudio_provider.py
            ├─ tabbyapi_provider.py
            ├─ unsloth_server_provider.py
            └─ openai_compat_provider.py
~~~

Select one provider for a process:

~~~powershell
$env:LLM_PROVIDER = "lmstudio"
$env:LMSTUDIO_API_BASE = "http://127.0.0.1:1234/v1"
~~~

Other providers use their documented API-base variables. The exact model
identifier passed to the provider is retained separately from the canonical
Registry key so a loaded quantization can be checked for mismatches.

### 6.3 Pre-run checks

Before a model is loaded, the launcher checks:

- the Registry entry exists;
- reasoning metadata is available;
- required capabilities and blueprint data exist;
- the model is not filtered out;
- the provider can serve the selected path;
- the model identity and quantization are consistent.

Missing prerequisites normally produce a warning or skip instead of silently
benchmarking a different model.

### 6.4 Benchmark dispatch

For every selected benchmark:

| Selection                                        | Implementation                                   |
| ------------------------------------------------ | ------------------------------------------------ |
| DS1000 / CoderEval                               | custom_benchmark.py in a bounded subprocess      |
| HumanEval+ / MBPP+                               | EvalPlus generation and differential evaluation  |
| ARC / HellaSwag / TruthfulQA / IFEval / MATH-500 | lm-evaluation-harness                            |
| Agentic                                          | tool-eval-bench scenarios                        |

sample-size controls the number of tasks or scenarios where the pipeline
supports sampling. seed is passed to the deterministic selection paths.
Reasoning models can be forced into thinking mode with --thinking.

### 6.5 Runtime sampling and generation

model_registry.yaml supplies the selected temperature, top_p, and optional
other sampling values. The launcher builds the provider/request parameters
from this local policy. No sampling web search is performed here.

The fixed slot policy is:

- sample size at least 10: four parallel slots where supported;
- smaller sample: one slot.

The policy is deliberately not stored as a mutable per-model Registry field.

## 7. Result data flow

~~~text
benchmark task
   │
   ├─ model response
   ├─ score and detail
   ├─ latency and token counts
   └─ CPU/GPU/RAM/VRAM telemetry
          │
          ▼
     per-task CSV
          │
          ├─ per-model summary
          └─ consolidated overview
~~~

All pipelines use a common semicolon-separated UTF-8 result schema. Important
identity fields include:

- model;
- model_key (publisher/model@quant);
- benchmark;
- pipeline;
- category;
- seed;
- sample_size.

Runtime metrics are telemetry. They do not change the benchmark score.
Consolidation applies the documented category weights:

| Category  | Weight    |
| --------- | --------: |
| Coding    | 35%       |
| Math      | 25%       |
| Agentic   | 25%       |
| Knowledge | 15%       |

For comparisons, use the same model identity, quantization, task selection,
seed, sampling policy, provider, and hardware.

## 8. Configuration and run specifications

The launcher supports YAML run specifications:

~~~yaml
models:
  - qwen3-30b-a3b-instruct
benchmarks:
  - DS1000
  - CoderEval
sample_size: 20
seed: 42
thinking: false
~~~

Run:

~~~powershell
py -3.12 .\src\run_benchmarks.py --run-spec .\run.example.yaml
~~~

Explicit CLI flags override values from the YAML file. Local run*.yaml files
are operational examples and should not be confused with the Registry.

## 9. Project layout

~~~text
Benchmarks/
├── src/
│   ├── registry_tool.py
│   ├── run_benchmarks.py
│   ├── assemble_blueprint.py
│   ├── model_registry.py
│   ├── benchmark_config.py
│   ├── model_manager.py
│   ├── providers/
│   ├── custom_benchmark.py
│   ├── csv_writer.py
│   └── consolidate_results.py
├── tests/
├── doc-git/
│   ├── model_registry.yaml
│   ├── blueprint_definitions.yaml
│   ├── Jinja-Chat-Templates/
│   └── Architecture, Flow & ChangeLog_en.md
├── simple_evals/
├── lm_eval_tasks/
├── ergebnisse/
├── requirements-dev.txt
├── pyproject.toml
└── .githooks/
~~~

## 10. Operational checks

After Registry changes:

~~~powershell
py -3.12 .\src\registry_tool.py pipeline status
py -3.12 .\src\registry_tool.py validate --ci
py -3.12 -m pytest -q tests\test_registry_tool.py tests\test_registry_pipeline.py
~~~

After launcher/provider changes:

~~~powershell
py -3.12 -m ruff check src\run_benchmarks.py src\model_manager.py src\providers
py -3.12 -m pytest -q tests\test_run_benchmarks.py tests\test_provider_architecture.py
~~~

Before delivery:

~~~powershell
py -3.12 -m ruff check src
py -3.12 -m pytest -q
~~~

The full test suite and GitHub Actions are independent safety layers. A local
hook does not replace CI.

## 11. Known boundaries

- OCR and embedding models are outside the Registry until local benchmark
  tests exist for them.
- The benchmark suite is not a general model-serving platform.
- Process isolation around code benchmarks is a pragmatic Windows resource
  and failure boundary, not a complete security sandbox.
- --ignore-drift is not a repair mechanism.
- Benchmark results are not directly comparable across different hardware,
  providers, context policies, or sampling policies.

## 12. Short architecture change log

The current architecture consolidates Registry maintenance behind
registry_tool.py, separates benchmark policy from LM Studio runtime
artifacts, and makes sampling onboarding a one-time evidence-producing step.
run_benchmarks.py remains the single model-lifecycle owner and all four
benchmark pipelines share the provider and result boundaries described above.

Historical implementation details and code-review records remain in Git
history, doc-git/Reviews/, and the other focused documents under doc-git/.
