# Local LLM Benchmark Suite

This repository measures how large language models (LLMs) perform on a local Windows machine with limited resources.
It is designed to calculate realistic benchmark scores using genuinely limited local resources, such as limited VRAM,
heavily quantized GGUF files, and a quantized KV cache.
The default benchmark backend is the local CUDA build of `llama-server.exe`,
started directly by the runner. LM Studio remains the local model inventory
and parameter-tuning environment; its tested settings can be reviewed and
explicitly imported into the Registry before deriving llama.cpp presets.
Other providers remain available for compatibility checks.

The project has two user-facing entry points:

1. src/registry_tool.py prepares and validates model registration with all required runtime parameters.
2. src/run_benchmarks.py selects models and benchmarks interactively or via the CLI, then loads the models and executes the benchmark runs.

Translated with DeepL.com (free version)

Everything else supports one of these two workflows: model discovery,
prompt assembly, provider access, result writing, or result consolidation.

## Central data flow

The repository separates preparation from execution. Registry maintenance
establishes the model and prompt policy; benchmark execution consumes that
policy through a provider and writes reproducible result artifacts.

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
                                      ├─> llama.cpp config/preset + GGUF
                                      ├─> load / readiness / unload
                                      ├─> Custom, EvalPlus, LM-Eval, Agentic
                                      └─> CSV results ──> consolidation
~~~

## What the project measures

The launcher currently supports four benchmark pipelines:

| Pipeline | Benchmarks                                   | What it measures                                |
| -------- | -------------------------------------------- | ----------------------------------------------- |
| Custom   | DS1000, CoderEval                            | Data-science and code-generation tasks          |
| EvalPlus | HumanEval+, MBPP+                            | Code generation with differential tests         |
| LM-Eval  | ARC, HellaSwag, TruthfulQA, IFEval, MATH-500 | Knowledge, reasoning, and instruction following |
| Agentic  | tool-eval-bench                              | Tool-use scenarios                              |

The result files contain per-task scores and runtime telemetry such as
latency, tokens per second, CPU, GPU, RAM, VRAM, and temperature. The
consolidation tool can build weighted summaries and paired comparisons.

The benchmark is local and hardware-dependent. Results are meaningful only
when the model, quantization, context policy, sampling parameters, seed,
sample size, provider, and hardware are recorded together.

## First-time setup

The documented environment is Windows PowerShell with Python 3.12.
Use the Python launcher explicitly so that the same interpreter is used for
the registry tool, benchmark launcher, tests, and hooks.

Prerequisites:

- Windows 11 or a compatible Windows Python environment
- Python 3.12
- LM Studio for the native local provider and parameter-tuning workflow
- downloaded GGUF models in a configured local model root
- the CUDA build of llama.cpp for the direct local provider (optional when
  using LM Studio only)
- an NVIDIA GPU is recommended; the current reference machine has 16 GB VRAM
- the dependencies required by the selected providers and benchmark suites

Install the development and test dependencies:

~~~powershell
py -3.12 -m pip install -r requirements-dev.txt
~~~

Install the runtime dependencies used by the benchmark pipelines as needed:

~~~powershell
py -3.12 -m pip install lm-eval[api] evalplus psutil ruamel.yaml nvidia-ml-py3
~~~

For MATH-500 and related lm-eval tasks, the project pins the ANTLR runtime
in requirements-dev.txt:

~~~powershell
py -3.12 -m pip install "antlr4-python3-runtime==4.11"
~~~

Verify the environment:

~~~powershell
py -3.12 -m pip check
py -3.12 -m pytest -q
~~~

## The normal user workflow

The repository is easiest to use in five steps:

1. Download or update a model in LM Studio or another supported local model
   store.
2. Let registry_tool.py discover and classify it.
3. Review the registry and prompt validation output.
4. Run the selected benchmarks with run_benchmarks.py.
5. Inspect per-task CSVs and consolidated summaries under ergebnisse\.

Start with a read-only status report:

~~~powershell
py -3.12 .\src\registry_tool.py status
~~~

If new benchmarkable models are installed, run the registry sync:

~~~powershell
py -3.12 .\src\registry_tool.py sync
~~~

LM Studio configuration changes are shown as field-level proposals. After
reviewing them, explicitly import valid and unambiguous tested values with:

~~~powershell
py -3.12 .\src\registry_tool.py sync --import-lms-settings
~~~

For the complete maintenance and validation workflow:

~~~powershell
py -3.12 .\src\registry_tool.py full
~~~

After explicitly importing tested LM Studio settings, update the local
llama.cpp router preset while preserving its global defaults and manual
sections:

~~~powershell
py -3.12 .\src\registry_tool.py preset "C:\Users\<user>\.config\llama.cpp\preset.ini" --merge-existing
~~~

Then inspect the available benchmark options:

~~~powershell
py -3.12 .\src\run_benchmarks.py --help
~~~

Example benchmark run:

~~~powershell
py -3.12 .\src\run_benchmarks.py --model "qwen3-30b-a3b-instruct" --benchmarks "DS1000,CoderEval" --sample-size 20 --seed 42
~~~

## registry_tool.py: prepare the registry

Invoke it from the repository root:

~~~powershell
py -3.12 .\src\registry_tool.py --help
~~~

The registry tool operates on:

- doc-git\model_registry.yaml
- local GGUF headers
- the LM Studio model inventory
- LM Studio config JSONs as read-only runtime evidence; the explicit
  `sync --import-lms-settings` option imports valid, field-listed settings
  into the Registry after showing their proposals
- blueprint definitions and Jinja templates
- bounded web research for one-time sampling onboarding

The authoritative source for each field and the permitted direction of data
transfer are defined in the [field ownership and synchronization rules](<doc-git/Architecture, Flow & ChangeLog_en.md#213-field-authority-during-synchronization>). In particular, GGUF facts come from the main file on disk, LM Studio settings are evidence of tested runtime choices, and benchmark policy remains in the Registry. LM Studio's displayed model size can include support files such as `mmproj`; it is not the main GGUF file size.

### GGUF model root configuration

Local GGUF discovery uses the following order by default:

1. `D:\LLM-Modelle\models` as the primary model root;
2. `C:\Users\<user>\.lmstudio\models` as a compatibility fallback.

The fallback also covers installations that still expose the old location or
use a Windows Junction.  The resolver canonicalizes paths and keeps the
primary copy when the same model identity is visible through both locations.

The direct llama.cpp provider does not use the llama GUI or router catalog to
discover benchmark models.  It recursively resolves concrete local `*.gguf`
files, so both of these layouts are supported:

~~~text
<root>\<publisher>\<model-folder>\<file>.gguf
<root>\models--<publisher>--<model>\snapshots\<revision>\<file>.gguf
<root>\hub\models--<publisher>--<model>\snapshots\<revision>\<file>.gguf
~~~

The llama.cpp GUI may display only models from its own catalog/cache and may
therefore omit otherwise valid publisher directories.  That display is not a
benchmark eligibility check.  The benchmark provider passes the resolved
GGUF file directly to `llama-server.exe --model`; the file path, GGUF header,
and registry match are authoritative.  For example, a file below
`models--ggml-org--gpt-oss-20b-GGUF\snapshots\<revision>` is discovered even
when the GUI does not list the surrounding directory.

For an isolated or different installation, set `GGUF_MODEL_ROOT` to one
directory.  The existing `UNSLOTH_MODEL_ROOT` and `LMSTUDIO_MODELS_DIR`
variables remain supported as lower-priority compatibility overrides.  An
explicit override scans only that directory; it does not silently add the
default fallback.  The same resolution order is used by the registry tool,
the local resolver, the benchmark runner, and the Unsloth provider.

### llama.cpp configuration, presets, and Registry

The direct production backend is the CUDA build at
`C:\Program Files\llama.cpp\llama-server.exe`. The WindowsApps
`llama.exe` wrapper and the llama desktop GUI are separate installations and
are not the benchmark backend. The direct provider resolves a concrete GGUF
file and starts `llama-server.exe`; it does not depend on the GUI model list.

llama.cpp has two different configuration layers. The automatically loaded
user configuration is:

~~~text
%APPDATA%\llama.cpp\config.ini
C:\Users\<user>\AppData\Roaming\llama.cpp\config.ini
~~~

The system-wide counterpart is `%PROGRAMDATA%\llama.cpp\config.ini`. These
`config.ini` files are appropriate for hardware-wide defaults, such as a GPU
offload policy, context baseline, or conservative server defaults. They are
not the project's model registry and should not contain benchmark scores or
model identity metadata.

The project-specific router preset is kept separately at:

~~~text
C:\Users\<user>\.config\llama.cpp\preset.ini
~~~

It is selected explicitly with `--models-preset` or
`LLAMA_ARG_MODELS_PRESET`. The current generated file contains a global
`[*]` section and model sections. The global section supplies defaults shared
by the model sections; a named section supplies model-specific server
options. The preset is a derived runtime catalog, not a replacement for
`doc-git\model_registry.yaml`.

For a normal standalone llama.cpp command, the effective order is:

~~~text
built-in defaults -> config.ini -> LLAMA_ARG_* environment variables -> CLI
~~~

For the router/preset path, the model-specific layers are added between the
environment defaults and the outer command-line overrides:

~~~text
built-in defaults
  -> config.ini
  -> LLAMA_ARG_* environment variables
  -> preset [*]
  -> preset [model]
  -> explicit outer CLI options
  -> request-level API options
~~~

The exact preset precedence is handled by llama.cpp: named model options
override `[*]`, and explicit outer CLI options have the highest priority.
Sampling, structured output, seed, stop conditions, and reasoning format are
request or model-policy decisions; they must not be inferred from a generic
hardware `config.ini` default.

The Registry remains the single source of truth for benchmark identity,
context/KV policy, templates, reasoning behavior, and category-specific
sampling evidence. The public `preset` command derives the llama.cpp preset
from that source:

~~~powershell
py -3.12 .\src\registry_tool.py preset "C:\Users\<user>\.config\llama.cpp\preset.ini" --merge-existing
~~~

The export preserves existing non-Registry sections and updates the derived
Registry sections. Review the generated diff rather than editing those
sections as the primary maintenance path. The current llama.cpp build rejects
`mmap` in a models preset even though the corresponding CLI capability exists;
that option is therefore kept out of the generated `[*]` section until the
preset parser supports it.

For an auditable direct-server run, export the concrete per-model argument
manifest separately:

~~~powershell
py -3.12 .\src\registry_tool.py export-llama-args "ergebnisse\llama-cpp-generated\args-manifest.json"
~~~

The JSON records the resolved GGUF path, start arguments, request defaults,
Registry SHA-256, and the detected `llama-server.exe` version. It is a
report-only artifact; `model_registry.yaml` remains authoritative.

The separate GUI log directory
`C:\Users\<user>\AppData\Local\Llama\logs` is not the automatic llama.cpp
`config.ini` location. Server logs used for benchmark diagnostics are
controlled by the direct provider's `LLAMA_CPP_LOG_DIR` setting.

### Registry maintenance commands

The routine interface is `status`, `sync`, `full`, `validate`, `preset`, and
`quarantine-missing`; `sync` and `full` orchestrate lower-level operations
from one shared inventory. Use `registry_tool.py advanced --help` for
specialist commands. The old `export-llama-preset` command remains as a
compatibility alias.

#### status

~~~powershell
py -3.12 .\src\registry_tool.py status
~~~

Read-only report:

- counts benchmarkable models reported by LM Studio;
- compares Registry keys, LMS inventory, and local config JSONs;
- reports missing or stale identities.

It does not write model_registry.yaml and does not write LM Studio
configuration JSONs.

Validation and active config matching ignore the existing `_quarantine_*`
directories below the LM Studio config root. Those files are historical
artifacts and are not treated as installed model configurations.

The old `pipeline status` spelling remains available for existing scripts.

#### sync

~~~powershell
py -3.12 .\src\registry_tool.py sync
~~~

Direct registry maintenance:

- adds new benchmarkable models;
- reads LM Studio models and configs once into a shared inventory;
- prints field-level change proposals with their source config;
- fills quantization, GGUF architecture, reasoning, and main-GGUF file size;
- normalizes the registry file.

It may write `doc-git\model_registry.yaml`. It does not write LM Studio
config JSONs or search the web unless `--refresh-sampling` is supplied.

#### Import LM Studio runtime settings

~~~powershell
py -3.12 .\src\registry_tool.py sync
~~~

The command compares active LM Studio config JSONs with the Registry and is
report-only by default. Each difference is shown with the old value, proposed
value, and source file. Conflicting values or ambiguous model matches are
reported and never imported. Values beyond GGUF context/expert limits are also
rejected. After review, apply the supported values deliberately:

~~~powershell
py -3.12 .\src\registry_tool.py sync --import-lms-settings
~~~

For a context-only import, the narrow write mode remains available:

~~~powershell
py -3.12 .\src\registry_tool.py advanced sync-from-configs --write-context
~~~

`--write-context` writes only `llm.load.contextLength` to the Registry field
`context_length`. It leaves offload, `useUnifiedKvCache`, `k_cache`, and
`v_cache` unchanged. The narrow mode also considers matching retained Config
JSONs that are not in the current LMS inventory, because validation still
checks their Registry identities. The broader `--write` mode remains
available when all supported config-derived fields should be imported
intentionally.

For MoE models, the tested LM Studio runtime expert count is imported
separately and deliberately:

~~~powershell
py -3.12 .\src\registry_tool.py advanced sync-from-configs --write-experts
~~~

This copies the LM Studio load field llm.load.numExperts to the Registry
field experts. experts is the selected runtime value used for benchmark
loading; max_experts is the immutable architectural maximum read from GGUF.
The latter is never used as an automatic VRAM fallback. LM Studio receives
experts as num_experts through its native load API. The direct llama.cpp
provider translates it to the architecture-specific
--override-kv <architecture>.expert_used_count=int:<N> argument.

#### Full maintenance modes

~~~powershell
py -3.12 .\src\registry_tool.py sync
~~~

The short `sync` command is the recommended orchestration wrapper:

1. prints the LMS model count and a Registry/LMS/config comparison;
2. runs the complete sync operation;
3. classifies every registry entry by reasoning, capabilities, and blueprint.

The classification step can write additional fields such as reasoning,
capabilities, blueprint, truncation, and custom_template to
model_registry.yaml. It still does not write LM Studio config JSONs.

Unlike `full`, it does not run prompt preview, prompt validation,
or the blocking drift exit check.

Validation distinguishes Registry/backend blockers from LM Studio-local
observations. The Registry owns benchmark `context_length`; a different LM
Studio `contextLength` is reported as an advisory and does not change the
benchmark value or block direct llama.cpp runs. Missing LM Studio configs and
missing `promptTemplate` values are also advisories because they affect LM
Studio compatibility rather than Registry readiness. Registry-owned runtime
requirements, including a selected MoE `experts` value, remain blocking when
missing or invalid.

#### Full validation and prompt maintenance

~~~powershell
py -3.12 .\src\registry_tool.py full
~~~

This runs synchronization and then adds:

- a dry-run report for non-installed registry models;
- blueprint and reasoning classification;
- read-only prompt assembly preview;
- prompt validation;
- Registry field-ownership and GGUF drift validation.

It may update model_registry.yaml through the sync and classification
stages. It also fills only missing or empty LM Studio `promptTemplate` fields.
It returns exit code 1 when blocking Registry/runtime ownership issues remain.

`full` runs template synchronization before prompt preview. This step fills
only missing or empty `promptTemplate` fields in matching LM Studio configs;
existing template values are preserved. System-prompt assembly remains
preview-only, and the separate GLM config patch is not run.

`full` is the short public command for the same workflow as the older
`pipeline full` spelling; both accept the same options. The quarantine report
and prompt assembly are previews. To apply those actions explicitly, run
`py -3.12 .\src\registry_tool.py quarantine-missing --apply` after reviewing
the proposed removals, or run `py -3.12 .\src\assemble_blueprint.py assemble`
to write assembled system prompts. LM Studio settings remain report-only
unless imported with `py -3.12 .\src\registry_tool.py sync --import-lms-settings`
(or `full --import-lms-settings`).

Use this only to keep the report/exit status while continuing after a known
drift:

~~~powershell
py -3.12 .\src\registry_tool.py full --ignore-drift
~~~

ignore-drift does not repair anything. It only prevents the open drift
from turning the full pipeline into exit code 1.

#### quarantine-missing

This command is report-only by default. It lists Registry models with no
matching LM Studio entry or local GGUF and shows which configs would be moved.
Only the explicit `--apply` option moves matching config files to a quarantine
folder and removes the Registry entries; an on-disk GGUF is never quarantined.

### Legacy command spelling

`py -3.12 .\src\registry_tool.py pipeline full` remains supported for existing
scripts. It invokes the same workflow and options as the shorter recommended
command `py -3.12 .\src\registry_tool.py full`.

### Sampling onboarding

Sampling research is performed when a new model is added, not during every
benchmark run. The tool checks Hugging Face model cards and bounded official
documentation paths for values such as temperature, top_p, top_k, and
min_p. Values are accepted only after plausibility and consistency checks.

The result is stored in the Registry with status and evidence. Synchronization
does not start a web search on its own. To research missing values, retry
terminal results, or refresh every benchmarkable candidate, request it
explicitly:

~~~powershell
py -3.12 .\src\registry_tool.py sync --refresh-sampling
~~~

This uses a web search and may take several minutes. Unresolved or conflicting cases are reviewed with the
registry-sampling-review workflow. Benchmark execution itself performs no
web search and reads only local Registry values.

### Model filters

Only models supported by the implemented benchmark pipelines belong in the
Registry. Shared filters exclude, among others:

- embedding models;
- OCR, vision, audio, and transcription models;
- RAG-only or feature-extraction models;
- MTP drafter companion files, DFlash decoder/draft files, and iMatrix
  support files.

For LM Studio vision models, the projector companion should follow LM
Studio's filename convention and start with `mmproj-` (for example
`mmproj-Millie-35B-A3B.gguf`). Without that prefix LM Studio may list the
projector as a separate model instead of associating it with the main GGUF.
The benchmark filters treat every `mmproj` file as auxiliary; only the main
language-model GGUF is a benchmark target.

OCR and embedding models are intentionally excluded because this repository
does not yet contain local benchmark tests for them.

## run_benchmarks.py: run the benchmarks

Invoke it from the repository root:

~~~powershell
py -3.12 .\src\run_benchmarks.py --help
~~~

The launcher:

1. reads the Registry and discovers eligible models;
2. selects the requested model(s) and benchmark(s);
3. loads one model through the selected provider;
4. runs each selected benchmark;
5. writes per-task and summary CSV files;
6. unloads the model when the provider supports it.

Only the launcher owns model load/unload lifecycle. Individual benchmark
pipelines do not independently load models.

### Common options

| Option                 | Meaning                                                      |
| ---------------------- | ------------------------------------------------------------ |
| --model, -m            | Model name, number, range, comma-separated selection, or all |
| --benchmarks, -b       | Benchmark name(s), number(s), or all                         |
| --sample-size, -s      | Number of tasks/scenarios per benchmark; default 20          |
| --seed                 | Reproducible task selection for supported pipelines          |
| --thinking             | Force thinking mode for reasoning models                     |
| --agentic-mode random  | Select random agentic scenarios                              |
| --agentic-mode safety  | Select the safety-focused agentic scenarios                  |
| --exclude-benchmarks   | Comma-separated exclusions                                   |
| --no-structured-output | Use the regex fallback in custom benchmarks                  |
| --unload-between       | Reload the model between benchmarks                          |
| --keep-response        | Store full responses instead of truncated response text      |
| --run-spec, --config   | Read models, benchmarks, seed, and options from YAML         |

CLI options override values from a run-spec YAML file.

Examples:

~~~powershell
# One model, all configured benchmarks, small smoke run
py -3.12 .\src\run_benchmarks.py --model "qwen3-30b-a3b-instruct" --sample-size 1

# Coding-only run
py -3.12 .\src\run_benchmarks.py --model "qwen3-30b-a3b-instruct" --benchmarks "DS1000,CoderEval" --sample-size 20 --seed 42

# Reasoning run with an explicit provider selected in the environment
$env:LLM_PROVIDER = "lmstudio"
py -3.12 .\src\run_benchmarks.py --model "qwen3-30b-a3b-instruct" --thinking

# Reproducible YAML run
py -3.12 .\src\run_benchmarks.py --run-spec .\run.example.yaml
~~~

## Data and source-of-truth rules

The project deliberately separates benchmark policy from backend-local
runtime artifacts.

| Data                   | Location                                                       | Role                                                 |
| ---------------------- | -------------------------------------------------------------- | ---------------------------------------------------- |
| Model registry         | doc-git\model_registry.yaml                                    | Benchmark policy and provider-neutral model metadata |
| Blueprint definitions  | doc-git\blueprint_definitions.yaml                             | System-prompt assembly rules                         |
| Jinja templates        | doc-git\Jinja-Chat-Templates\                                  | Explicit chat-template overrides                     |
| GGUF files             | `D:\LLM-Modelle\models` (legacy `~\.lmstudio\models` fallback) | Immutable model/header facts                         |
| LM Studio config JSONs | LM Studio internal config directory                            | Backend-local runtime artifacts and drift evidence   |
| Benchmark datasets     | simple_evals\, lm-eval, EvalPlus, tool-eval-bench              | Tasks and scenarios                                  |
| Run specifications     | local run*.yaml files                                          | Reproducible run selections                          |
| Results                | ergebnisse\                                                    | Per-task CSVs, summaries, logs, and reports          |

The canonical model identity is:

~~~text
publisher/model@quant
~~~

The publisher and quantization are part of the identity. Two files with the
same base model name but different publishers or quantizations are different
models for Registry matching.

The shared helpers `build_model_identity()` and
`decompose_model_identity()` keep construction and parsing of this
`publisher/model@quant` triplet in one place. The publisher, model base name,
and quantization are therefore handled consistently across registry matching,
benchmark result consolidation, and blacklist filtering.

Sampling values and provenance are stored together in each entry's `sampling`
block. The four benchmark categories are `coding`, `knowledge`, `agentic`, and
`math`; instruction following is covered by `agentic`. Category provenance
uses `evidence_kind` and, for derived values, `derived_from`. The research
status, timestamp, and deduplicated source URLs are stored once in that same
block; there is no separate `normal` category or parallel evidence list.

### Registry entry example

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
  reasoning: instruct
  capabilities: coding, text
  blueprint: default_chat
  context_length: 32768
  max_context_length: 131072
  offload: 1.0
  useUnifiedKvCache: false
~~~

Do not manually edit the Registry for routine model onboarding. Use
registry_tool.py, inspect its diff, and then run validation.

## Providers and environment

Select one provider per benchmark process with LLM_PROVIDER:

- lmstudio
- llama_cpp
- tabbyapi
- unsloth_server
- an OpenAI-compatible provider

Common local API variables:

~~~powershell
$env:LLM_PROVIDER = "lmstudio"
$env:LMSTUDIO_API_BASE = "http://127.0.0.1:1234/v1"
~~~

For direct llama.cpp execution:

~~~powershell
$env:LLM_PROVIDER = "llama_cpp"
$env:LLAMA_CPP_SERVER_EXE = "C:\Program Files\llama.cpp\llama-server.exe"
$env:LLAMA_CPP_API_BASE = "http://127.0.0.1:8080/v1"
~~~

The provider layer keeps model selection, load/unload, readiness checks, and
API execution separate. The benchmark launcher remains provider-aware but the
benchmark implementations use a common result contract.

## Results and consolidation

All pipelines write UTF-8 semicolon-separated CSV files below ergebnisse\.
The result schema includes model identity, benchmark, category, score, seed,
sample size, latency, token counts, and system telemetry.

Build a weighted overview with:

~~~powershell
py -3.12 .\src\consolidate_results.py --help
py -3.12 .\src\consolidate_results.py
~~~

The default category weights are:

| Category  | Weight |
| --------- | -----: |
| Coding    | 35%    |
| Math      | 25%    |
| Agentic   | 25%    |
| Knowledge | 15%    |

For statistically paired comparisons, use the consolidation tool's compare
options with a fixed seed and comparable task selection.

## Repository map

~~~text
Benchmarks/
├── src/
│   ├── registry_tool.py          Registry onboarding and validation entry point
│   ├── run_benchmarks.py        Benchmark launcher and model lifecycle
│   ├── assemble_blueprint.py    Blueprint classification, assembly, validation
│   ├── model_registry.py        Registry resolution and runtime derivation
│   ├── benchmark_config.py      Filters, defaults, benchmark definitions
│   ├── model_manager.py         Provider facade for model operations
│   ├── providers/                LM Studio, llama.cpp, and API providers
│   ├── custom_benchmark.py      DS1000 and CoderEval implementation
│   ├── csv_writer.py            Uniform result output
│   └── consolidate_results.py   Weighted summaries and comparisons
├── tests/                       Pytest suite
├── doc-git/
│   ├── model_registry.yaml      Registry source of truth
│   ├── blueprint_definitions.yaml
│   ├── Jinja-Chat-Templates/
│   └── Architecture, Flow & ChangeLog_en.md
├── simple_evals/                Local JSONL benchmark data
├── ergebnisse/                  Runtime results and reports
├── requirements-dev.txt
└── pyproject.toml
~~~

## Validation and development

Run focused checks after changing Registry or launcher code:

~~~powershell
py -3.12 -m ruff check src\registry_tool.py src\run_benchmarks.py
py -3.12 -m pytest -q tests\test_registry_tool.py tests\test_registry_pipeline.py
~~~

Run the complete local suite:

~~~powershell
py -3.12 -m pytest -q
~~~

If Git hooks are configured, use the repository hooks for commit and push.
Do not use --no-verify unless the skipped checks are documented and run
manually afterwards.

## Further documentation

- Review-Gate für Review, Commit und Push: REVIEW-GATE.md
- Architecture, Flow & ChangeLog: doc-git\Architecture, Flow & ChangeLog_en.md
- How to install and configure a new LLM:
  doc-git\HowTo-Install-and-Configure-New-LLM_en.md
- LM Studio API references: doc-git\Developer-Docs\LM-Studio-API-References.md
- Registry sampling review workflow:
  .codex\skills\registry-sampling-review\SKILL.md
- Project planning: PLANUNG.md

## License

See the repository license files and the licenses of the individual benchmark
datasets and external tools before redistribution.
