"""Benchmark sampling policy shared by the runtime and the llama.cpp adapter.

The policy is deliberately separate from the Registry ``sampling`` block. That
block keeps the per-model research history (values, provenance, sources) and
stays visible, but it no longer decides the runtime parameters. The runtime
reads the class values defined here.

Rationale (docs/Benchmark-Sampling-Policy_en.md): greedy decoding
(``temperature=0``) is not a valid default on the local 16 GB VRAM
workstation. Models beyond roughly 22-24B parameters have to be quantized to
about 3 bit or below there, and at that quantization level most models either
enter repetition loops or lose too much quality. Qwen3 explicitly warns
against greedy decoding ("performance degradation and endless repetitions"),
DeepSeek-R1 recommends 0.5-0.7 "to prevent endless repetitions or incoherent
outputs".

The values form a band of 0.5 to 0.7 across the benchmark classes rather than
one global value: Qwen3, DeepSeek-R1 and Llama 3 agree on 0.6 for reasoning
models, GLM-4.7 names 0.7 for coding and math, and Gemma 4 and IBM Granite
name 1.0 for their own use cases. 0.5 remains the conservative floor for
narrow instruct work.
"""

from __future__ import annotations

from typing import Any

BENCHMARK_CLASSES: tuple[str, ...] = ("coding", "math", "knowledge", "agentic")

#: Per-class sampling values. ``temperature`` is the primary control;
#: ``top_p``/``top_k``/``min_p`` follow the vendor recommendations that the
#: values were derived from (Qwen3, Qwen3.8, Llama 3, DeepSeek-R1).
BENCHMARK_SAMPLING_BY_CLASS: dict[str, dict[str, Any]] = {
    "coding": {
        "temperature": 0.6,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.0,
    },
    "math": {
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.0,
    },
    "knowledge": {
        "temperature": 0.6,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.0,
    },
    "agentic": {
        "temperature": 0.6,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.0,
    },
}

#: Sampling profile for a reasoning run. Kept at the vendor-recommended
#: reasoning temperature; the reasoning level itself is ``medium`` and the
#: response budget is 4096 tokens (see ``BENCHMARK_THINKING_DEFAULTS``).
BENCHMARK_THINKING_SAMPLING: dict[str, Any] = {
    "temperature": 0.6,
    "top_p": 0.95,
    "top_k": 20,
    "min_p": 0.0,
}

#: Narrow instruct work uses a lower floor; no vendor publishes a separate
#: prescription for it, so this stays a deliberate project compromise.
BENCHMARK_INSTRUCT_SAMPLING: dict[str, Any] = {
    "temperature": 0.5,
    "top_p": 0.95,
    "top_k": 20,
    "min_p": 0.0,
}

#: Reasoning level for benchmark runs. ``medium`` deliberately leaves some
#: model potential unused: the higher levels multiply the run time, and the
#: benchmark compares models against each other rather than maximising a
#: single score. The level is only sent when the selected template actually
#: understands the corresponding control.
BENCHMARK_REASONING_LEVEL = "medium"

#: Total completion budget for a reasoning run. It covers the reasoning trace
#: plus the final answer. The former value of 8192 doubled the runtime, and a
#: bounded budget ends the observed repetition loops under 4 bit and in REAP
#: variants earlier. It stays above the 1024 floor that the GLM-4.7
#: documentation warns against.
BENCHMARK_REASONING_MAX_TOKENS = 4096

#: Reasoning budget for the reasoning trace itself, where the backend keeps
#: the reasoning and the answer in separate channels. The completion budget
#: above is the total; this value caps the hidden part.
BENCHMARK_REASONING_THINKING_TOKENS = 2048

#: GPT-OSS reasoning levels for the interactive blueprint. The three levels used
#: to render the same text, so the selection had no effect at all. They now
#: differ: ``medium`` stays the benchmark default, ``full`` raises the level
#: for interactive use, and ``minimal`` lowers it. The blueprint writes the
#: level into the system prompt, exactly as the Harmony template expects.
GPTOSS_REASONING_LEVELS: dict[str, str] = {
    "full": "high",
    "medium": BENCHMARK_REASONING_LEVEL,
    "minimal": "low",
}


def sampling_for_class(category: str, *, thinking: bool = False) -> dict[str, Any]:
    """Return the sampling values for one benchmark class.

    A reasoning run uses the thinking profile; the class values are otherwise
    authoritative. Unknown categories fall back to ``coding`` so that an
    unexpected name never silently drops the sampling contract.
    """
    if thinking:
        return dict(BENCHMARK_THINKING_SAMPLING)
    key = category if category in BENCHMARK_SAMPLING_BY_CLASS else "coding"
    return dict(BENCHMARK_SAMPLING_BY_CLASS[key])
