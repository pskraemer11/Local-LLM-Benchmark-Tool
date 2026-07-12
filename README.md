# LLM Benchmark Suite

> **Version:** see [`VERSION`](./VERSION) (currently 13.0.0-p3).  
> **Release date:** 2026-07-12  
> **Status:** see [`Doku-intern/Reviews/Code-Review_2026-07-12.md`](./Doku-intern/Reviews/Code-Review_2026-07-12.md) for the most recent code-review and fix history.

Local benchmark framework for LLMs via LM Studio REST API (OpenAI-compatible). Tests coding, reasoning, knowledge, and agentic capabilities across **4 pipelines** with **9 benchmarks** (MMLU-Pro is archived).

**Goal:**
While many benchmark results are available online, they typically run on large servers with abundant memory and powerful CPU/GPU resources. 
This project focuses on obtaining realistic values for local execution under real-world constraints where resources — especially VRAM — are limited. 
This means either smaller (generally weaker) models with fewer parameters, or medium-sized models with heavy quantization (which also impacts quality). 
The same applies to KV-cache: either heavily quantized and/or limited context length to fit in VRAM, otherwise token/s plummets and runtime skyrockets.

This test suite makes it possible to find the best models and quantizations for a given piece of hardware.

Over 50 LLM models were tested on an HP Omen gaming PC with an NVIDIA RTX 5070 Ti (see a sample of results below).

## Features

- **4 independent pipelines**: Custom (DS1000, CoderEval), EvalPlus (HumanEval+, MBPP+), LM-Eval (ARC, HellaSwag, TruthfulQA, MathQA, MMLU-Pro), Agentic (tool-eval-bench)
- **Reasoning support**: Thinking mode (`--thinking`) for MathQA/MMLU-Pro on AceMath, DeepSeek, Gemma 4
- **Stratified subsampling**: Random but category-balanced task selection for DS1000, MathQA, MMLU-Pro
- **System metrics**: CPU/GPU/RAM/VRAM/temperature per task (median + P90)
- **Thinking token analysis**: `<think>`/`<|channel|>` extraction, percentage thinking ratio
- **Task retry**: 3 attempts with exponential backoff on API errors
- **Consolidation**: Weighted leaderboard (Coding 35%, Math 25%, Agentic 25%, Knowledge 15%)
- **Bootstrap confidence intervals**: 95% CI from per-item data (DS1000/CoderEval) via `--bootstrap`

## Prerequisites

- **Hardware**: NVIDIA GPU with >=16 GB VRAM (tested: RTX 5070 Ti)
                (less works, but not with all models tested here)
- **Software**: LM Studio (>=1.4.1) with REST API on `localhost:1234`
- **Python**: 3.13+
- **Installed models**: GGUF quantizations in LM Studio

## Installation

```bash
# Clone repository
git clone https://github.com/pskraer11/llm-benchmark-suite.git
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
# Interactive mode (select model + benchmarks)
python run_benchmarks_v12.py

# Direct run (model + all benchmarks)
python run_benchmarks_v12.py --model "qwen2.5-coder-14b-instruct" --sample-size 20

# With thinking mode for reasoning models (MathQA/MMLU-Pro)
python run_benchmarks_v12.py --model "gemma-4-26b-a4b-it" --sample-size 20 --thinking

# Specific benchmarks
python run_benchmarks_v12.py --model "qwen2.5-coder-14b-instruct" --benchmarks DS1000,CoderEval --sample-size 10

# Consolidate results (with bootstrap CI)
python consolidate_results_v12.py --bootstrap
```

## CLI Options

| Flag                | Description                                                                                                  |
|---------------------|--------------------------------------------------------------------------------------------------------------|
| `--model`           | Model key (from `lms ls --json`)                                                                             |
| `--benchmarks`      | Comma-separated: DS1000, CoderEval, HumanEval+, MBPP+, ARC, HellaSwag, TruthfulQA, MathQA, MMLU-Pro, Agentic |
| `--sample-size`     | Tasks per benchmark (default: 10)                                                                            |
| `--thinking`        | Enable thinking mode for MathQA/MMLU-Pro (reasoning models)                                                  |
| `--bootstrap`       | Enable Bootstrap 95% CI for DS1000/CoderEval (consolidation only)                                            |
| `--non-interactive` | No user prompts                                                                                              |
| `--output-dir`      | Results directory (default: `ergebnisse/`)                                                                   |

## Architecture

```
LM Studio REST API (localhost:1234)
|
run_benchmarks_v12.py  (Launcher – load/unload HERE ONLY)
├── custom_benchmark_v12.py   (DS1000, CoderEval)
├── lm_eval                   (ARC, HellaSwag, TruthfulQA, MathQA, MMLU-Pro)
├── evalplus                  (HumanEval+, MBPP+)
└── tool_eval_bench           (Agentic)
|
consolidate_results_v12.py    (Weighted leaderboard + bootstrap CI)
    → ergebnisse/konsolidiert_*.csv + *.md
```

### Benchmarks

| Pipeline  | Benchmarks                                    | Evaluation                                |
|-----------|-----------------------------------------------|-------------------------------------------|
| Custom    | DS1000, CoderEval                             | `exec_sandboxed()` + namespace comparison |
| lm-eval   | ARC, HellaSwag, TruthfulQA, MathQA, MMLU-Pro  | `generate_until` + regex extraction       |
| evalplus  | HumanEval+, MBPP+                             | Differential testing with plus_input      |
| Agentic   | Agentic (69 scenarios)                        | tool-eval-bench final_score               |

### Weighting (Overall Score)

| Category  | Weight | Benchmarks                                                   |
|-----------|--------|--------------------------------------------------------------|
| Coding    |   35%  | DS1000 (25%), CoderEval (25%), HumanEval+ (25%), MBPP+ (25%) |
| Math      |   25%  | MathQA (100%)                                                |
| Agentic   |   25%  | Agentic (100%)                                               |
| Knowledge |   15%  | ARC (25%), HellaSwag (25%), TruthfulQA (25%), MMLU-Pro (25%) |

## Thinking Mode

Activates `enable_thinking=True` for AceMath, DeepSeek, and Gemma 4 on MathQA + MMLU-Pro:

```bash
python run_benchmarks_v12.py --model "acemath-7b-instruct" --thinking
```

Implementation:
- `custom_benchmark_v12.py`: `REASONING_PATTERNS = {"acemath", "deepseek", "gemma"}` in `_get_model_config()`
- `run_benchmarks_v12.py`: `_is_reasoning_model()` + `_is_gemma_model()` in `_get_lmeval_params()`
- Qwen3.6/Qwen3.5 are excluded (`enable_thinking=False` enforced)

## Project Structure

```
Benchmarks/
├── run_benchmarks_v12.py           # Launcher
├── custom_benchmark_v12.py         # Custom pipeline (DS1000, CoderEval)
├── consolidate_results_v12.py      # Consolidation + bootstrap CI
├── benchmark_config.py             # Weights, MMLU-Pro-Subsets, Tool-Eval-Scenarios
├── model_manager.py                # LM Studio load/unload
├── csv_writer.py                   # CSV output
├── simple_evals/                   # JSONL datasets
├── lm_eval_tasks/                  # Custom YAML tasks
├── ergebnisse/                     # Results + consolidation
├── doc-git/                        # Documentation
│   ├── Architektur+Flow_*.md        # Full architecture description (German)
│   └── Modell_Steckbriefe*.md      # Model reference (40+ entries, German)
└── tests/                          # Pytest tests
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
