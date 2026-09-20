# Local LLM Benchmark Suite

This repository measures how language models behave on a local Windows
machine. It is designed for realistic constraints such as limited VRAM,
quantized GGUF files, a local LM Studio server, and several
OpenAI-compatible providers.

The project has two user-facing entry points:

1. src/registry_tool.py prepares and validates the model registry.
2. src/run_benchmarks.py loads models and runs the benchmarks.

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
- LM Studio for the native local provider
- downloaded GGUF models in LM Studio
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

1. Download or update a model in LM Studio.
2. Let registry_tool.py discover and classify it.
3. Review the registry and prompt validation output.
4. Run the selected benchmarks with run_benchmarks.py.
5. Inspect per-task CSVs and consolidated summaries under ergebnisse\.

Start with a read-only status report:

~~~powershell
py -3.12 .\src\registry_tool.py pipeline status
~~~

If new benchmarkable models are installed, run the registry sync:

~~~powershell
py -3.12 .\src\registry_tool.py sync
~~~

For the complete maintenance and validation workflow:

~~~powershell
py -3.12 .\src\registry_tool.py pipeline full
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
- LM Studio config JSONs as read-only runtime evidence
- blueprint definitions and Jinja templates
- bounded web research for one-time sampling onboarding

### GGUF model root configuration

Local GGUF discovery uses the following order by default:

1. `D:\LLM-Modelle\models` as the primary model root;
2. `C:\Users\<user>\.lmstudio\models` as a compatibility fallback.

The fallback also covers installations that still expose the old location or
use a Windows Junction.  The resolver canonicalizes paths and keeps the
primary copy when the same model identity is visible through both locations.

For an isolated or different installation, set `GGUF_MODEL_ROOT` to one
directory.  The existing `UNSLOTH_MODEL_ROOT` and `LMSTUDIO_MODELS_DIR`
variables remain supported as lower-priority compatibility overrides.  An
explicit override scans only that directory; it does not silently add the
default fallback.  The same resolution order is used by the registry tool,
the local resolver, the benchmark runner, and the Unsloth provider.

### The important pipeline variants

These commands are related but not interchangeable.

#### pipeline status

~~~powershell
py -3.12 .\src\registry_tool.py pipeline status
~~~

Read-only report:

- counts benchmarkable models reported by LM Studio;
- compares Registry keys, LMS inventory, and local config JSONs;
- reports missing or stale identities.

It does not write model_registry.yaml and does not write LM Studio
configuration JSONs.

pipeline without a mode uses this status mode.

#### sync

~~~powershell
py -3.12 .\src\registry_tool.py sync
~~~

Direct registry maintenance:

- adds new benchmarkable models;
- performs one-time sampling onboarding for new models;
- fills quantization, GGUF architecture, reasoning, and context metadata;
- reports LM Studio config drift;
- normalizes the registry file.

It may write doc-git\model_registry.yaml. It does not write LM Studio
config JSONs.

#### pipeline sync

~~~powershell
py -3.12 .\src\registry_tool.py pipeline sync
~~~

This is an orchestration wrapper around sync:

1. prints the LMS model count and a Registry/LMS/config comparison;
2. runs the complete sync operation;
3. classifies every registry entry by reasoning, capabilities, and blueprint.

The classification step can write additional fields such as reasoning,
capabilities, blueprint, truncation, and custom_template to
model_registry.yaml. It still does not write LM Studio config JSONs.

Unlike pipeline full, it does not run prompt preview, prompt validation,
or the blocking drift exit check.

#### pipeline full

~~~powershell
py -3.12 .\src\registry_tool.py pipeline full
~~~

This runs pipeline sync and then adds:

- a dry-run report for non-installed registry models;
- blueprint and reasoning classification;
- read-only prompt assembly preview;
- prompt validation;
- Registry field-ownership and GGUF drift validation.

It may update model_registry.yaml through the sync and classification
stages, but it does not write LM Studio config JSONs. It returns exit code 1
when blocking ownership drift remains.

Use this only to keep the report/exit status while continuing after a known
drift:

~~~powershell
py -3.12 .\src\registry_tool.py pipeline full --ignore-drift
~~~

ignore-drift does not repair anything. It only prevents the open drift
from turning the full pipeline into exit code 1.

### Sampling onboarding

Sampling research is performed when a new model is added, not during every
benchmark run. The tool checks Hugging Face model cards and bounded official
documentation paths for values such as temperature, top_p, top_k, and
min_p. Values are accepted only after plausibility and consistency checks.

The result is stored in the Registry with status and evidence. Later syncs
skip terminal research statuses unless an explicit retry is requested:

~~~powershell
py -3.12 .\src\registry_tool.py sync --refresh-sampling
~~~

Unresolved or conflicting cases are reviewed with the
registry-sampling-review workflow. Benchmark execution itself performs no
web search and reads only local Registry values.

### Model filters

Only models supported by the implemented benchmark pipelines belong in the
Registry. Shared filters exclude, among others:

- embedding models;
- OCR, vision, audio, and transcription models;
- RAG-only or feature-extraction models;
- MTP drafter companion files and iMatrix support files.

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
- tabbyapi
- unsloth_server
- an OpenAI-compatible provider

Common local API variables:

~~~powershell
$env:LLM_PROVIDER = "lmstudio"
$env:LMSTUDIO_API_BASE = "http://127.0.0.1:1234/v1"
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
│   ├── providers/                LM Studio and OpenAI-compatible providers
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
