# Architecture and User Workflow

Status: 2026-09-24
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

> The Registry describes benchmark policy. LM Studio JSONs and llama.cpp
> config/preset files describe backend-local runtime state. A normal sync or
> benchmark run must not silently overwrite those backend artifacts.

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

| Data                                  | Authority                                      | Used by                                   | Write policy                                      |
| ------------------------------------- | ---------------------------------------------- | ----------------------------------------- | ------------------------------------------------- |
| doc-git/model_registry.yaml           | Benchmark policy and provider-neutral metadata | Registry tool, launcher, model resolution | Updated by registry maintenance                   |
| GGUF header and filename              | Model architecture and native limits           | Registry tool, resolver                   | Read-only source                                  |
| doc-git/blueprint_definitions.yaml    | Prompt blueprint definitions                   | Assembly and validation                   | Maintained as project policy                      |
| doc-git/Jinja-Chat-Templates/         | Explicit template files                        | Prompt assembly                           | Maintained as project assets                      |
| LM Studio config JSONs                | LM Studio runtime state                        | Drift checks and explicit Registry import | Read as evidence; full may add only missing promptTemplate fields |
| llama.cpp `config.ini`                | Hardware-wide llama.cpp defaults               | Direct CLI/server processes               | User/system runtime configuration                 |
| llama.cpp `preset.ini`                | Derived model router catalog                   | Direct server provider                    | Generated from Registry; preserve custom sections |
| simple_evals/                         | Local custom benchmark tasks                   | Custom pipeline                           | Benchmark input; do not rewrite during runs       |
| EvalPlus/lm-eval/tool-eval-bench data | External benchmark tasks                       | Their respective pipelines                | Managed by the dependency/tool                    |
| ergebnisse/                           | Run outputs                                    | Human review and consolidation            | Runtime output, normally ignored                  |

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

The important separation is between Registry policy and backend runtime
artifacts. A GUI setting such as a system prompt, chat template, KV-cache
quantization, or parallel-session setting is not automatically a global
benchmark policy.

### 2.1.2 llama.cpp configuration layers

The direct llama.cpp backend uses the CUDA installation at
`C:\Program Files\llama.cpp\llama-server.exe`. The WindowsApps `llama.exe`
wrapper and the desktop llama GUI are separate installations and are not the
production benchmark executable. The provider resolves a concrete GGUF file
and starts `llama-server.exe`; the GUI catalog is not the source of model
eligibility.

llama.cpp automatically reads the user configuration from
`%APPDATA%\llama.cpp\config.ini` (on the current machine this is
`C:\Users\<user>\AppData\Roaming\llama.cpp\config.ini`) and may also read
the system configuration from `%PROGRAMDATA%\llama.cpp\config.ini`. These
files are suitable for hardware-wide defaults. They are deliberately not a
second model registry.

The model router preset is an explicit derived artifact at
`C:\Users\<user>\.config\llama.cpp\preset.ini`. It is selected with
`--models-preset` or `LLAMA_ARG_MODELS_PRESET`. Its `[*]` section contains
shared preset defaults; named sections contain model-specific server options.

The SSOT-Registry remains the authoritative source for model identity, benchmark
policy, context/KV settings, templates, reasoning behavior, and sampling
evidence. The public `registry_tool.py preset` command translates that policy
into the preset; it does not make the preset authoritative. The older
`export-llama-preset` spelling remains as a compatibility alias.

For direct per-model execution, `registry_tool.py export-llama-args` produces
a report-only JSON manifest with the resolved GGUF path, concrete start
arguments, request defaults, Registry SHA-256, and detected server version.
This manifest is an audit artifact, not a second source of truth.

The effective precedence is two related sequences:

~~~text
standalone llama.cpp:
  built-in defaults -> config.ini -> LLAMA_ARG_* -> explicit CLI

router/preset mode:
  built-in defaults -> config.ini -> LLAMA_ARG_* -> preset [*]
  -> preset [model] -> explicit outer CLI -> request-level API options
~~~

Within a preset, a named model section overrides `[*]`, and explicit outer
CLI options have the highest priority. Sampling, structured output, seed,
stop conditions, and reasoning format are request or model-policy decisions;
they do not belong in a generic hardware baseline. The separate LM Studio
JSON configuration remains an LM Studio-only runtime artifact.

### 2.1.3 Hugging Face and GGUF metadata interoperability

The authoritative reference for metadata naming between Hugging Face model
cards and GGUF files is the official llama.cpp note
[HuggingFace Model Card Metadata Interoperability Consideration](https://github.com/ggml-org/llama.cpp/wiki/HuggingFace-Model-Card-Metadata-Interoperability-Consideration).
It describes correspondences such as `model_name` to `general.name`,
`base_model`/`base_model_sources` to `general.base_model.*`, and model-card
`tags`/`language` to the corresponding GGUF general metadata.

This reference is a metadata interoperability contract, not a complete runtime
parameter mapping. LM Studio JSON fields, Registry policy fields, and
llama.cpp command-line flags remain separate adapter contracts. The Registry
therefore stores the canonical `publisher/model@quant` identity and benchmark
policy, while adapters preserve source-specific names and report missing or
ambiguous evidence rather than guessing.

The current build accepts the relevant settings as CLI options but rejects
`mmap` when it appears in a models preset. The generated preset therefore
does not put `mmap` in `[*]` until the installed preset parser supports it.

### 2.1.4 Field authority during synchronization

The Registry is not a copy of every local file. It stores reviewed benchmark
policy and the selected runtime values consumed by providers. Synchronization
reads several sources, but each field has one defined authority:

| Field or data                  | Authoritative source                           | Synchronization rule                                                                |
| ------------------------------ | ---------------------------------------------- | ----------------------------------------------------------------------------------- |
| Model identity and eligibility | Registry key plus exact local identity         | Match publisher/model/quant; report ambiguity instead of guessing.                  |
| Main GGUF path and byte size   | Resolved main GGUF file on disk                | Use the main file stat; exclude `mmproj` and LMS aggregate size.                    |
| Technical facts and limits     | GGUF header and filename                       | Read-only: architecture, quant, native context, `max_experts`.                      |
| Tested runtime settings        | Active LMS config after a real test            | Propose context, offload, K/V cache, unified KV, experts; import explicitly.        |
| MoE expert counts              | GGUF maximum plus tested LMS value             | Keep fixed `max_experts`; store selected runtime value as `experts`.                |
| Sampling values                | Official model card or documentation           | Import sourced categories only; leave missing or conflicting values unresolved.     |
| Benchmark and prompt policy    | Registry plus blueprint/template files         | Registry holds policy; blueprint and Jinja files hold prompt content.               |
| LMS prompt fields              | Project blueprint and templates                | Fill only missing `promptTemplate`; never import GUI prompt text.                   |
| Parallel benchmark slots       | Runner rule plus provider capability           | Use Sample Size rule and provider cap; ignore GUI parallel-session settings.        |
| llama.cpp model sections       | Registry, resolved GGUF, and test evidence     | Export model sections; preserve user-owned `config.ini` and preset `[*]`.           |

LM Studio settings are evidence of a user's tested choice, not the ongoing
source for benchmark execution. After an explicit import, `model_registry.yaml`
is the value used by the runner and exported presets. A disagreement must be
shown as a proposed field-level change with its source; a missing or ambiguous
source must not silently produce a guessed value. The main model GGUF size is
distinct from LM Studio's aggregate size when the model also has a projector.

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

The canonical identity is constructed by `build_model_identity()` and split
by its counterpart `decompose_model_identity()`. Both helpers operate on the
same three components—publisher, model base name, and quantization—so callers
do not maintain separate parsing or formatting rules for the
`publisher/model@quant` Registry key.

Resolution is fail-closed. `resolve_registry_match()` returns a typed
`UniqueMatch`, `AmbiguousMatch`, or `Unmatched` result; the compatibility helper
`match_registry_key()` returns a key only for the unique state. The shared
`ArtifactResolver` applies the same rule to local GGUF files and retains all
candidate paths for diagnostics. `quantization.py`, `inventory.py`, and
`parameter_bindings.py` are the reusable boundary contracts for quantization
spelling, per-run source snapshots, and Registry-to-backend parameter names.

### 2.2.1 Identity evidence and LMS runtime linkage

The canonical identity is intentionally smaller than the evidence needed to
operate one local benchmark run. The required semantic identity is exactly:

~~~text
publisher + complete model name + quantization
~~~

The complete model name may contain slashes. The installed Qwen pair makes
the distinction concrete: `byteshape/qwen3.5-9b@q5_k_s` is the Q5_K_S file
from Byteshape, while `lmstudio-community/qwen/qwen3.5-9b@q6_k` is the Q6_K
file stored below the LM Studio Community model root. In the latter identity,
the first `qwen/` is part of the model name, not a second publisher.

For a local GGUF artifact, the evidence table retains only the additional data
needed to prove and resolve that identity. The distinction between required
identity data and transient join data is intentional:

| Evidence | Required for a unique local identity? | Role and persistence |
| -------- | ------------------------------------ | ------------------- |
| Registry key: publisher + complete model name + quant | yes | Semantic identity and benchmark selection; persisted as the Registry key |
| Absolute GGUF path | yes for local execution | Strong physical reference to the exact file passed to `llama-server.exe`; persisted in the machine-local `local.model_path` |
| Full path components and GGUF filename | yes as physical evidence | Derive/check publisher, namespaced model name, variant markers, and filename quant; retained in the per-run evidence record, not copied into the semantic key |
| GGUF header facts | yes for technical validation | Immutable architecture and limit evidence such as context and expert bounds; never replaced by an LMS display value |
| LMS publisher/modelKey/selectedVariant | no for the final llama.cpp binding | Transient join and cross-check evidence only; do not persist as a second identity because LMS publisher metadata is not the physical file owner |
| Unique LMS JSON config path | only when LMS runtime values are imported | Identifies the source of tested sampling, context, UKV, cache, offload, parallel-session, expert, and speculative settings; persisted as `local.config_path` only after a unique join |

LM Studio data is join evidence, not a second semantic identity. Its
`publisher`, `modelKey`, `selectedVariant`, and logical path are used only to
locate the matching JSON config and to cross-check the physical artifact. They
are not copied into the runtime binding because llama.cpp does not need them.
The JSON config path and its runtime values remain necessary for importing
tested values such as sampling parameters, context length, UKV, K/V cache
types, offload, experts, parallel sessions, and speculative decoding.
`RuntimeBinding` stores those values only after one LMS row, one exact GGUF,
and one exact JSON config have been joined. A reported LMS artifact path, when
present, must name that exact local GGUF; it is not allowed to select a
different similarly named file. If LMS exposes only a logical Hub key, the
physical GGUF evidence remains the stronger source and the LMS row may complete
the join only when the resulting model and quantization are still unique.

#### 2.2.1.1 The per-run data contract

`registry_tool.py` reads one `InventorySnapshot` for a synchronization run.
The snapshot is an in-memory join table, not another user-maintained Registry:

~~~text
InventorySnapshot
├─ registry: semantic Registry entries
├─ raw_lms_models / lms_models: one LMS inventory snapshot
├─ configs: parsed LMS JSON configs with their absolute json_path
├─ gguf_candidates: physical GGUF candidates, loaded lazily
└─ identity_links[registry_key]
   ├─ artifact_evidence[]
   │  ├─ absolute path
   │  ├─ path-derived source_reference
   │  └─ publisher / complete model_name / quant
   └─ runtime_bindings[]
      ├─ unique config_path, or None when the join is not proven
      ├─ sampling, context_length, use_unified_kv, num_parallel
      ├─ offload, K/V cache, and num_experts
      └─ normalized speculative settings
~~~

`ArtifactIdentityEvidence` is the physical proof for one concrete GGUF.
`RuntimeBinding` is the runtime projection of one uniquely matched JSON
config. `IdentityLink` keeps both projections under the Registry key and is
the only object allowed to feed local materialization. This prevents an LMS
row, config, or basename from being reused across two publisher/quantization
identities merely because it appeared first in an iteration.

The persisted machine-local projection is deliberately smaller than the
snapshot and contains only values needed for offline execution or audit:

~~~yaml
publisher/model@quant:
  local:
    model_path: D:/LLM-Modelle/models/publisher/model-GGUF/model-Q6_K.gguf
    config_path: C:/Users/<user>/.lmstudio/.internal/user-concrete-model-default-config/...
    companions:
      mtp: D:/LLM-Modelle/models/publisher/model-GGUF/mtp-model-Q8_0.gguf
      draft: D:/LLM-Modelle/models/publisher/model-GGUF/dflash-q4_0.gguf
    llama_cpp:
      speculative:
        type: mtp
        mode: separate
        companion_role: mtp
        draft_n_max: 4
        draft_n_min: 0
        draft_p_min: 0.0
~~~

The LMS publisher, model key, selected variant, aggregate size, and logical
display path are deliberately absent from this persisted projection. They are
useful inputs to the join, but they are neither needed by `llama-server.exe`
nor authoritative over the exact local GGUF and its header.

#### 2.2.1.2 Deterministic reconciliation sequence

Every discovery, `sync`, `full`, preset export, and direct llama.cpp launch
must use the following sequence. The sequence is designed so that a different
directory layout or a second publisher cannot change the selected result by
iteration order:

~~~text
read Registry + LMS inventory + JSON configs once
                 │
                 ▼
discover GGUFs under LLAMA_ARG_MODELS_DIR first, then configured fallbacks
                 │
                 ▼
derive full-path/filename evidence and read immutable GGUF header facts
                 │
                 ▼
match exact publisher + complete model name + quantization
                 │
       ┌─────────┴─────────┐
       │ exactly one       │ zero or multiple
       ▼                   ▼
cross-check concrete LMS  emit diagnostic; do not choose a first match
path, if available         and do not import runtime values
       │
       ▼
find exactly one JSON config for that LMS row and claim it exclusively
       │
       ▼
materialize local.model_path, local.config_path, companions, and runtime
       │
       ▼
provider adapter translates the internal profile to llama.cpp CLI flags
~~~

Support files are excluded from the main-model scan. They are admitted only
after an explicit, uniquely joined bundle reference: a separate MTP file is a
`companions.mtp` artifact, while a DFlash draft LLM is a `companions.draft`
artifact. Integrated MTP remains a property of the single main GGUF and has
no companion path. Internal types (`mtp` and `draft`) are translated to the
current llama.cpp option labels only at the provider boundary.

#### 2.2.1.3 Fail-closed reconciliation outcomes

The synchronization report must preserve the reason for a rejected join:

| Outcome | Meaning | Allowed action |
| ------- | ------- | -------------- |
| `not_found` | No physical GGUF or no matching config exists | Report; leave the local binding unchanged |
| `ambiguous` | Several GGUFs/configs match the same request | Report all candidates; never select the first |
| `identity_collision` | Publisherless or normalized identity maps to multiple Registry keys | Require publisher and quant evidence; do not import |
| `stale_path` | Persisted or LMS concrete path no longer names the candidate | Fail resolution; do not fall back silently |
| `config_reused` | One JSON config would be assigned to multiple identities | Keep it diagnostic-only until a unique ownership exists |
| `companion_missing` | Speculative mode requires an explicit sidecar that cannot be uniquely resolved | Keep the main model usable, but omit broken speculative CLI arguments |

Only the unique path continues to runtime materialization. A warning may be
non-blocking for a report-only command, but it must never become an implicit
selection rule for benchmark execution.

`registry_tool.py` creates or refreshes these local bindings from the current
environment. A configured local path is authoritative: if it becomes stale,
runtime resolution fails closed instead of selecting another file. CI and
portable Registry review ignore the `local` section. `LLAMA_ARG_MODELS_DIR`
is the highest-priority shared GGUF root and therefore participates in the
same resolver used for discovery, config joins, companion resolution, and
llama.cpp execution; it is not a second path-resolution implementation.

### 2.2.2 Model bundles and speculative decoding

The Registry contains one default benchmark identity for the main GGUF. A
separate MTP file, mmproj, and iMatrix file are non-standalone bundle
artifacts. A DFlash draft GGUF is different: it is a complete LLM that can run
independently, but when discovered under its standard sidecar name it is
attached as `companions.draft` and excluded from default main-model
enumeration. An explicit companion reference from the uniquely joined LMS
config may resolve any of these bundle artifacts with support-file scanning
enabled.

The three supported local shapes are:

| Local shape | Registry representation | llama.cpp launch data |
| ----------- | ----------------------- | ---------------------- |
| Integrated MTP in the main GGUF | main `model_path`; speculative `type: mtp`, `mode: integrated`; no companion path | `--spec-type draft-mtp` plus the MTP runtime limits |
| Main GGUF plus separate MTP GGUF | main identity only; `companions.mtp` contains the exact non-standalone path; speculative `type: mtp`, `mode: separate`, `companion_role: mtp` | `--spec-type draft-mtp`, `--spec-draft-model`, and MTP limits |
| Main GGUF plus separate DFlash draft LLM | main identity only; `companions.draft` contains the exact path; speculative `type: draft`, `method: dflash`, `companion_role: draft` | `--spec-type draft-dflash`, `--spec-draft-model`, and draft limits |

The adapter translates this normalized local profile to current llama.cpp
server options (`--spec-type`, `--spec-draft-model`,
`--spec-draft-n-max`, `--spec-draft-n-min`, and `--spec-draft-p-min`). The
authoritative option semantics are maintained in the official
[llama.cpp speculative decoding documentation](https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md)
and [server option reference](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).
The Hugging Face/llama.cpp metadata naming differences remain a source-level
mapping concern and are documented by the official
[metadata interoperability consideration](https://github.com/ggml-org/llama.cpp/wiki/HuggingFace-Model-Card-Metadata-Interoperability-Consideration).

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

Separate MTP companions, DFlash draft files, mmproj files, and iMatrix support
files are also filtered as auxiliary rather than standalone benchmark models.
Integrated MTP main GGUFs and real standalone MTP models remain eligible. A
DFlash file is a full LLM in its own right, but a standard `dflash-*` sidecar
is treated as a bundle dependency during default inventory. The LMS `lms ls --json` snapshot is useful
for logical model and variant metadata, but it does not replace the physical
GGUF inventory: in particular, it does not expose every companion file.

LM Studio also relies on a naming convention for vision projectors: the
projector filename should start with `mmproj-` (for example,
`mmproj-Millie-35B-A3B.gguf`). Otherwise LM Studio can expose it as a separate
model instead of associating it with the main language-model GGUF. The
benchmark-side inventory filter checks all available identity fields, so a
projector remains auxiliary even when an inventory record omits its path.

### 3.2 Public registry command surface

The routine interface is intentionally limited to a small set of
workflow-level commands:

~~~text
py -3.12 src\registry_tool.py status
py -3.12 src\registry_tool.py sync
py -3.12 src\registry_tool.py sync --import-lms-settings
py -3.12 src\registry_tool.py full
py -3.12 src\registry_tool.py validate
py -3.12 src\registry_tool.py preset "C:\Users\<user>\.config\llama.cpp\preset.ini" --merge-existing
py -3.12 src\registry_tool.py quarantine-missing
py -3.12 src\registry_tool.py preset
~~~

`status` is read-only. `sync` uses a shared model/config inventory and prints
field-level LM Studio proposals while updating deterministic Registry-owned
facts. `--import-lms-settings` is an explicit write opt-in for valid,
unambiguous local values; conflicting Configs and values exceeding GGUF-owned
context/expert limits are never applied. `full` adds missing prompt-template
maintenance, prompt preview, and validation. It does not write assembled
system prompts. `preset` derives local model sections from the Registry while
preserving the target INI's global and manually maintained sections.
`quarantine-missing` is preview-only unless `--apply` is supplied. Specialist
maintenance commands remain available through `registry_tool.py advanced
<command>`; old command names continue to work as compatibility aliases.

### 3.3 The three pipeline modes (compatibility aliases)

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

Validation and active config matching ignore `_quarantine_*` directories below
the LM Studio config root. Quarantined JSON files are historical runtime
artifacts and do not represent installed model configurations.

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

#### sync-from-configs

~~~text
py -3.12 src\registry_tool.py sync-from-configs
~~~

`sync-from-configs` is report-only by default. The explicit narrow mode

~~~text
py -3.12 src\registry_tool.py sync-from-configs --write-context
~~~

imports only `llm.load.contextLength` into the Registry field
`context_length`. It does not write LM Studio JSONs and does not change
offload, `useUnifiedKvCache`, `k_cache`, or `v_cache`. It also considers
matching retained Config JSONs that are absent from the current LMS inventory,
because validation still checks their Registry identities. The broader
`--write` mode imports all supported config-derived fields and must therefore
be selected deliberately.

For MoE runtime tuning, use the focused import:

~~~text
py -3.12 src\registry_tool.py sync-from-configs --write-experts
~~~

This imports the live-tested LM Studio load field llm.load.numExperts into
Registry.experts. It is distinct from max_experts, the immutable GGUF
architectural maximum. LM Studio receives the runtime value as num_experts;
direct llama.cpp receives the architecture-specific
--override-kv <architecture>.expert_used_count=int:<N> override.

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

#### full (legacy spelling: pipeline full)

~~~text
py -3.12 src\registry_tool.py full
~~~

`full` is the concise public spelling for the same operation as the older
`pipeline full` command. Both spellings route to the same workflow and accept
the same flags. The full workflow performs synchronization and then:

1. reports non-installed Registry models in quarantine dry-run mode;
2. classifies Registry entries and fills missing LM Studio `promptTemplate` fields;
3. runs a read-only system-prompt assembly preview;
4. validates prompt and template completeness;
5. validates Registry drift and field ownership.

System-prompt assembly is explicitly preview-only. The GLM config patch is
skipped. Open blocking Registry/runtime issues cause exit code 1 unless
--ignore-drift is passed. The flag changes the exit behavior only; it is not
an automatic repair.

Validation treats LM Studio context values as local runtime observations.
Registry `context_length` is the benchmark source of truth, so a different
`contextLength` in an LM Studio JSON is reported but does not block `validate`
or the direct llama.cpp path. Missing LM Studio config files and missing
`promptTemplate` values are reported the same way. A missing or invalid
Registry-owned runtime value, such as MoE `experts`, remains blocking.

`pipeline full` runs `sync-templates` before prompt preview. It fills only
missing or empty `promptTemplate` fields in matching LM Studio config JSONs
and preserves populated values. System-prompt assembly remains preview-only;
the separate GLM config patch is not run.

These steps are intentionally previews or report-only unless explicitly
applied. To move the proposed stale configs and Registry entries into
quarantine, review the report and run:

~~~text
py -3.12 src\registry_tool.py quarantine-missing --apply
~~~

To write assembled system prompts instead of previewing them, run:

~~~text
py -3.12 src\assemble_blueprint.py assemble
~~~

LM Studio runtime settings are imported only when requested, for example:

~~~text
py -3.12 src\registry_tool.py sync --import-lms-settings
~~~

### 3.3 Direct maintenance commands

The pipeline modes are the preferred user interface, but lower-level
commands remain useful for focused repairs:

| Command                 | Purpose                                                                                  | Writes config JSONs? |
| ----------------------- | ---------------------------------------------------------------------------------------- | -------------------- |
| compare                 | Report Registry/LMS/config differences                                                   | No                   |
| validate --ci           | Headless consistency validation                                                          | No                   |
| fill-quant              | Fill missing quantization from GGUF names                                                | No                   |
| fill-arch               | Read architecture values from GGUF headers                                               | No                   |
| fill-reasoning          | Detect reasoning from GGUF templates                                                     | No                   |
| sync-from-configs       | Report drift; --write-context imports only context; --write-experts imports tested MoE runtime experts; --write imports all supported fields | No by default        |
| sync-templates          | Copy missing prompt templates into configs; also run by pipeline full                   | Yes                  |
| sync-template-from-gguf | Explicitly copy an embedded GGUF template into one config                                | Yes                  |
| patch-reasoning-effort  | Explicit GLM runtime-config patch                                                        | Yes                  |

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

- the four benchmark category values (`coding`, `knowledge`, `agentic`, and
  `math`) plus an optional `thinking` runtime profile;
- `evidence_kind` and optional `derived_from` inside each category cell;
- `sampling_research_status`, the timestamp, and deduplicated source URLs
  inside the same `sampling` block.

The old `normal` profile is an internal research fallback only. It is mapped
to the explicit coding anchor and is not persisted as a Registry category.
There is no parallel `sampling_evidence` list; source URLs are stored once in
`sampling.sampling_sources`.

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
            ├─ llama_cpp_provider.py
            ├─ tabbyapi_provider.py
            ├─ unsloth_server_provider.py
            └─ openai_compat_provider.py
~~~

Select one provider for a process:

~~~powershell
$env:LLM_PROVIDER = "lmstudio"
$env:LMSTUDIO_API_BASE = "http://127.0.0.1:1234/v1"
~~~

For the production llama.cpp path, the launcher starts the CUDA server binary
directly and resolves a local GGUF through `LocalModelResolver`; it does not
call `lms.exe` or the WindowsApps `llama.exe` wrapper:

~~~powershell
py -3.12 src/run_benchmarks.py --provider llama_cpp --api-base http://127.0.0.1:8080/v1 --model all --benchmarks all
~~~

The direct provider uses `C:\Program Files\llama.cpp\llama-server.exe` by
default. `LLAMA_CPP_SERVER_EXE`, `LLAMA_CPP_API_BASE`,
`LLAMA_CPP_MODEL_ROOT`, and `LLAMA_CPP_LOG_DIR` override the executable,
endpoint, local GGUF root, and server-log directory. The provider owns only
the process it started; a foreign server already using the configured port is
reported as a conflict and is never terminated.

The provider-level runtime policy is assembled from the Registry and the
resolved GGUF. A router deployment may additionally use the generated
`%USERPROFILE%\.config\llama.cpp\preset.ini`, but direct model execution can
pass the concrete GGUF path to `llama-server.exe` without using the router
catalog. This keeps the benchmark model identity tied to the resolved file,
not to a GUI or cache entry.

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

| Selection                                        | Implementation                                  |
| ------------------------------------------------ | ----------------------------------------------- |
| DS1000 / CoderEval                               | custom_benchmark.py in a bounded subprocess     |
| HumanEval+ / MBPP+                               | EvalPlus generation and differential evaluation |
| ARC / HellaSwag / TruthfulQA / IFEval / MATH-500 | lm-evaluation-harness                           |
| Agentic                                          | tool-eval-bench scenarios                       |

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

| Category  | Weight |
| --------- | -----: |
| Coding    | 35%    |
| Math      | 25%    |
| Agentic   | 25%    |
| Knowledge | 15%    |

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
registry_tool.py, separates benchmark policy from LM Studio and llama.cpp
runtime artifacts, and makes sampling onboarding a one-time evidence-
producing step. The direct llama.cpp provider uses a CUDA server and a
Registry-derived preset while leaving global `config.ini` available for
hardware defaults. run_benchmarks.py remains the single model-lifecycle owner
and all four benchmark pipelines share the provider and result boundaries
described above.

Historical implementation details and code-review records remain in Git
history, doc-git/Reviews/, and the other focused documents under doc-git/.
