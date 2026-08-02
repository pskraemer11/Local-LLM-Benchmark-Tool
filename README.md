[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/pskraemer11/Local-LLM-Benchmark-Tool)

# LLM Benchmark Suite

> **Version:** v13.0.5 – Pipeline-Validierung, Hybrid-Klassifikation  
> **Release date:** 2026-07-29  
> **Last doc update:** 2026-07-29  
> - ISO/IEC 9126 Review (28.07.): alle 9 Skripte auf 100% Typ-Hints, Terminal-Farben, `GenerationConfig`-Dataclass  
> - `run_task()` in 4 Helfer refactored, `run_agentic()` mit Live-Fortschritt, `main()` gesplittet  
> - Chat-Templates: 4 neue Jinja-Overrides (Gemma-4 QAT, Phi-4 Unsloth, GPT-OSS Unsloth)  
> - 8 Code-Reviews in `doc-git/Reviews/`, 14 Modell-Dokumente in `doc-git/Modell Specific Hints/`  
> **Status:** see [`doc-git/Reviews/Code-Review_2026-07-28.md`](./doc-git/Reviews/Code-Review_2026-07-28.md) for the latest ISO/IEC 9126 quality review.

Local benchmark framework for LLMs via LM Studio REST API (OpenAI-compatible). Tests coding, reasoning, knowledge, and agentic capabilities across **4 pipelines** with **9 benchmarks** (MMLU-Pro is archived).

**Goal:**
While many benchmark results are available online, they typically run on large servers with abundant memory and powerful CPU/GPU resources. 
This project focuses on obtaining realistic values for local execution under real-world constraints where resources — especially VRAM — are limited. 
This means either smaller (generally weaker) models with fewer parameters, or medium-sized models with heavy quantization (which also impacts quality). 
The same applies to KV-cache: either heavily quantized and/or limited context length to fit in VRAM, otherwise token/s plummets and runtime skyrockets.

This test suite makes it possible to find the best models and quantizations for a given piece of hardware.

Over 50 LLM models were tested on an HP Omen gaming PC with an NVIDIA RTX 5070 Ti (see a sample of results below).

## Features

- **4 independent pipelines**: Custom (DS1000, CoderEval), EvalPlus (HumanEval+, MBPP+), LM-Eval (ARC, HellaSwag, TruthfulQA, MATH-500), Agentic (tool-eval-bench)
- **Reasoning support**: Thinking mode (`--thinking`) for MATH-500 on reasoning models
- **Stratified subsampling**: Random but category-balanced task selection for DS1000
- **System metrics**: CPU/GPU/RAM/VRAM/temperature per task (median + P90)
- **Thinking token analysis**: `<think>`/`<|channel|>` extraction, percentage thinking ratio
- **Task retry**: 3 attempts with exponential backoff on API errors
- **Consolidation**: Weighted leaderboard (Coding 35%, Math 25%, Agentic 25%, Knowledge 15%)
- **Bootstrap confidence intervals**: 95% CI from per-item data (DS1000/CoderEval) via `--bootstrap`
- **Terminal colors**: ANSI-coded output with progress bars (`utils/terminal.py`)
- **GenerationConfig**: 16 parameters → single dataclass (`type_defs.py`)
- **Registry tool**: `src/registry_tool.py` for model registry management, JSON config sync, architecture data extraction from GGUF headers

## Prerequisites

- **Hardware**: NVIDIA GPU with >=16 GB VRAM (tested: RTX 5070 Ti)
                (less works, but not with all models tested here)
- **Software**: LM Studio (>=1.4.1), based on llama.cpp Backends with REST / OpenAI compatible API on `localhost:1234`
- **Python**: 3.13+
- **Installed models**: GGUF quantizations in LM Studio

## Installation

```bash
# Clone repository
git clone https://github.com/pskraemer11/Local-LLM-Benchmark-Tool/llm-benchmark-suite.git
cd llm-benchmark-suite

# Python dependencies
pip install lm-eval[api] evalplus nvidia-ml-py3 psutil

# lm-eval task dependencies (REQUIRED for IFEval and MATH-500)
# Without these, IFEval and MATH-500 will fail with ModuleNotFoundError
# (see Terminalausgabe Benchmark Run 12.07.2026 for details).
#   - langdetect: required by lm_eval/tasks/ifeval/instructions.py
#   - immutabledict: required by lm_eval/tasks/ifeval/instructions_util.py
#   - sympy, math_verify, antlr4-python3-runtime==4.11: required by lm_eval/tasks/minerva_math/
#   - nltk: required by lm_eval for TruthfulQA tokenization
pip install langdetect immutabledict "antlr4-python3-runtime==4.11" lm-eval[math] nltk
python -c "import nltk; nltk.download('punkt', quiet=True); nltk.download('punkt_tab', quiet=True)"

# If no NVIDIA GPU, CPU/GPU utilization must be obtained differently

# DS1000 official framework (optional)
git clone https://github.com/xlangai/DS-1000.git ds1000_official
# Apply Windows patches (see ds1000_official/README)
```

## Quick Start

```bash
# Registry maintenance (add new models, sync configs, extract GGUF arch data)
python src/registry_tool.py sync

# Interactive mode (select model + benchmarks)
python src/run_benchmarks.py

# Direct run (model + all benchmarks)
python src/run_benchmarks.py --model "qwen2.5-coder-14b-instruct" --sample-size 20

# With thinking mode for reasoning models (MATH-500)
python src/run_benchmarks.py --model "gemma-4-26b-a4b-it" --sample-size 20 --thinking

# Specific benchmarks
python src/run_benchmarks.py --model "qwen2.5-coder-14b-instruct" --benchmarks DS1000,CoderEval --sample-size 10

# Consolidate results (with bootstrap CI)
python src/consolidate_results.py --bootstrap
```

## CLI Options (run_benchmarks)

| Flag                | Description                                                                                                  |
|---------------------|--------------------------------------------------------------------------------------------------------------|
| `--model`           | Model key (from `lms ls --json`)                                                                             |
| `--benchmarks`      | Comma-separated: DS1000, CoderEval, HumanEval+, MBPP+, ARC, HellaSwag, TruthfulQA, MATH-500, Agentic         |
| `--sample-size`     | Tasks per benchmark (default: 10)                                                                            |
| `--thinking`        | Enable thinking mode for reasoning models                                                                    |
| `--bootstrap`       | Enable Bootstrap 95% CI for DS1000/CoderEval (consolidation only)                                            |
| `--non-interactive` | No user prompts                                                                                              |
| `--output-dir`      | Results directory (default: `ergebnisse/`)                                                                   |
| `--unload-between`  | Unload model between benchmarks (default: on)                                                                |

## Registry Tool (src/registry_tool.py)

| Command            | Description                                                                 |
|--------------------|-----------------------------------------------------------------------------|
| `sync`             | Full pipeline: add → fill-arch → configs → sync-from-configs → sync-ctx → fill-ctx → fmt |
| `add`              | Add new models from LMS to registry (auto-reads GGUF arch data)             |
| `fill-arch`        | Extract n_layers/hidden_dim from all local GGUF headers (~1ms/file)         |
| `configs`          | Write load.fields (offload, np, useUnifiedKvCache) into JSON configs        |
| `sync-from-configs`| Overwrite registry values from JSON configs                                 |
| `fix-np` / `fix-ctx` | Recompute num_parallel or context_length for all entries                  |
| `compare`          | Registry vs LMS vs JSON configs comparison report                           |

## Architecture

```
LM Studio REST API (localhost:1234)
|
src/registry_tool.py            (Model registry + JSON config management)
├── add / fill-arch         (GGUF header reader for n_layers/hidden_dim)
├── configs / sync-from-configs  (Bidirectional JSON ↔ Registry sync)
└── sync                    (Full maintenance pipeline)
|
src/run_benchmarks.py       (Launcher – load/unload HERE ONLY)
├── src/custom_benchmark.py   (DS1000, CoderEval)
├── lm_eval                   (ARC, HellaSwag, TruthfulQA, MATH-500)
├── evalplus                  (HumanEval+, MBPP+)
└── tool_eval_bench           (Agentic)
|
src/consolidate_results.py   (Weighted leaderboard + bootstrap CI)
    → ergebnisse/konsolidiert_*.csv + *.md
```

see also: https://deepwiki.com/pskraemer11/Local-LLM-Benchmark-Tool

### Benchmarks

| Pipeline  | Benchmarks                                    | Evaluation                                |
|-----------|-----------------------------------------------|-------------------------------------------|
| Custom    | DS1000, CoderEval                             | `exec_sandboxed()` + namespace comparison |
| lm-eval   | ARC, HellaSwag, TruthfulQA, MATH-500          | `generate_until` + regex extraction       |
| evalplus  | HumanEval+, MBPP+                             | Differential testing with plus_input      |
| Agentic   | Agentic (69 scenarios)                        | tool-eval-bench final_score               |

### Weighting (Overall Score)

| Category  | Weight | Benchmarks                                                   |
|-----------|--------|--------------------------------------------------------------|
| Coding    |   35%  | DS1000 (25%), CoderEval (25%), HumanEval+ (25%), MBPP+ (25%) |
| Math      |   25%  | MATH-500 (100%)                                              |
| Agentic   |   25%  | Agentic (100%)                                               |
| Knowledge |   15%  | ARC (33%), HellaSwag (33%), TruthfulQA (33%)                 |

## Thinking Mode

Activates `--thinking` for reasoning models on supported benchmarks:

```bash
python src/run_benchmarks.py --model "gemma-4-26b-a4b-it" --thinking
```

Implementation is in `src/run_benchmarks.py` and `src/custom_benchmark.py`.
Reasoning model detection uses model-name keywords (r1, thinking, qwq, reasoning, cot).

## Project Structure

```
Benchmarks/
├── src/run_benchmarks.py           # Launcher
├── src/custom_benchmark.py         # Custom pipeline (DS1000, CoderEval)
├── src/consolidate_results.py      # Consolidation + bootstrap CI
├── src/registry_tool.py                # Model registry + JSON config management
├── src/assemble_blueprint.py           # Blueprint/classify/validate assembly
├── src/benchmark_config.py             # Weights, Tool-Eval-Scenarios
├── src/model_manager.py                # LM Studio load/unload
├── src/csv_writer.py                   # CSV output
├── tools/lmeval_proxy.py            # Native API proxy for lm_eval
├── tools/correlation_export.py      # Results correlation export
├── utils/terminal.py                # ANSI terminal colors + progress bars
├── type_defs.py                     # Shared TypedDict + GenerationConfig
├── simple_evals/                    # JSONL datasets
├── lm_eval_tasks/                   # Custom YAML tasks (minerva_math500, etc.)
├── ergebnisse/                      # Results + consolidation
├── doc-git/                         # Documentation (German)
│   ├── Architecture-and-Flow.md    # Full architecture + flow description
│   ├── HowTo-Install-and-Configure-New-LLM.md # Model installation guide
│   ├── Parallel-Slots-Optimization.md # numParallel & KV-Cache optimization
│   ├── thinking-config.md          # Thinking mode configuration
│   ├── model_registry.yaml         # YAML model registry (source of truth)
│   ├── blueprint_definitions.yaml  # Blueprint definitions for prompt assembly
│   ├── Datasets-17-07-2026.md      # Dataset descriptions
│   ├── Jinja-Chat-Templates/       # Chat template overrides (Gemma-4, Phi-4, GPT-OSS)
│   ├── Reviews/                    # ISO/IEC 9126 Code Reviews (8 Reports)
│   ├── Modell Specific Hints/      # Model-specific documentation (14 files)
│   └── PandasEval vs CoderEval - Evaluation Guidebook.md
└── tests/                          # Pytest tests (520+, 14 files)
```

## Sample Results

From the latest run (30 models, SampleSize=20). Scores in %

|Rank| Model                        | Overall | Coding |Knowledge| Math |
|----|------------------------------|---------|--------|---------|------|
|  1 | Devstral 24B Q3_K_S          |  *67%*  |   71%  |   65%   |  40% |
|  2 | Granite 4.1 30B              |   66%   |   65%  |   62%   | *55%*|
|  3 | Qwen3 Coder REAP 25B Q4_K_S  |   65%   |   67%  |   54%   |  50% |
|  4 | Qwen2.5 Coder 14B            |   64%   |  *72%* |   66%   |  40% |
|  5 | Qwen3 Coder REAP 25B IQ4_XS  |   63%   |   63%  |   53%   |  45% |

## License

GNU General Public License v3.0 (see LICENSE). The benchmark datasets are subject to their own licenses (Apache-2.0, CC-BY-NC-4.0, etc.).

## Related Projects

- [LM Studio](https://lmstudio.ai) – Local LLM server
- [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness) – Standardized LLM evaluation
- [evalplus](https://github.com/evalplus/evalplus) – Extended coding benchmarks
- [tool-eval-bench](https://huggingface.co/datasets/aisafety-ai/tool_eval_bench) – Tool-use evaluation
