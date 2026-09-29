"""Shared Registry policies for context, templates and reasoning controls."""

from __future__ import annotations

import re
from typing import Any

from model_identity import classify_reasoning_by_family, family_for_name

REASONING_PATTERNS = {
    "acemath",
    "deepseek",
    "gemma",
    "phi-4-reasoning",
    "ministral",
    "nemotron",
    "apriel",
    "magistral",
    "gpt-oss",
    "reasoning",
    "think",
    "r1",
    "rnj",
    "qwq",
    "cascade",
    "cot",
    "phi-4",
    "kimi",
    "mirothinker",
    "thinking",
    "glm-4.7",
    "glm-4.6v",
    "qwen3.5",
    "qwen3.6",
    "qwen3.8",
    "qwen3-14b",
    "qwen3-coder-reap",
}


def _word_boundary_match(pattern: str, text: str) -> bool:
    """Substring match with word-boundary check to avoid false overlaps.

    Returns True if `pattern` is bounded by non-alphanumeric chars
    or string boundaries (start/end, '-', '_', '/', '.', '@').
    A digit counts as a boundary when adjacent to the pattern.
    """
    if pattern not in text:
        return False
    idx = text.find(pattern)
    while idx != -1:
        before = text[idx - 1] if idx > 0 else ""
        after = text[idx + len(pattern)] if idx + len(pattern) < len(text) else ""
        before_ok = not before or not before.isalnum() or before.isdigit()
        after_ok = not after or not after.isalnum() or after.isdigit()
        if before_ok and after_ok:
            return True
        idx = text.find(pattern, idx + 1)
    return False


def resolve_context_length(entry: dict[str, Any]) -> int | None:
    """Resolve a positive benchmark context within its technical GGUF limit."""

    def positive(value: Any) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None

    maximum = positive(entry.get("max_context_length"))
    requested = positive(entry.get("context_length")) or maximum
    return min(requested, maximum) if requested and maximum else requested


def resolve_template(entry: dict[str, Any], blueprint: dict[str, Any] | None, model_name: str = "") -> str | None:
    """Resolve explicit override, Blueprint map/file, then legacy fallback."""
    if entry.get("template_policy") == "explicit_file":
        value = entry.get("template")
        return str(value) if value else None
    bp = blueprint or {}
    mapping = bp.get("template_map")
    name = model_name.casefold()
    normalized = re.sub(r"[.\s]", "-", name)
    if isinstance(mapping, dict):
        for pattern, filename in mapping.items():
            pattern = str(pattern).casefold()
            canonical = re.sub(r"[.\s]", "-", pattern)
            if (pattern and pattern in name) or (canonical and canonical in normalized):
                return str(filename)
    value = bp.get("template") or entry.get("template")
    return str(value) if value else None


def resolve_reasoning(entry: dict[str, Any] | None, model_name: str) -> str | None:
    """An explicit Registry classification wins over a legacy family alias."""
    data = entry or {}
    declared = data.get("reasoning")
    if declared in {"thinking", "instruct"}:
        return str(declared)
    family_reasoning = classify_reasoning_by_family(model_name, str(data.get("architecture_family") or ""))
    if family_reasoning:
        return str(family_reasoning)
    if not data and any(_word_boundary_match(pattern, model_name.casefold()) for pattern in REASONING_PATTERNS):
        return "thinking"
    return None


def reasoning_template_controls(
    entry: dict[str, Any] | None, model_name: str, *, template_text: str | None = None
) -> frozenset[str]:
    """Use an actual template when known, otherwise a documented architecture."""
    if template_text is not None:
        return frozenset(key for key in ("enable_thinking", "reasoning_effort", "reasoning_strength") if key in template_text)
    data = entry or {}
    architecture = str(data.get("architecture_family") or "").casefold()
    if not architecture and not data:
        family = family_for_name(model_name)
        architecture = family.arch_keys[0].casefold() if family else ""
    if architecture in {"qwen3", "qwen3moe", "qwen35", "qwen35moe", "qwen3next", "gemma4"}:
        return frozenset({"enable_thinking"})
    return frozenset()


def reasoning_request_kwargs(config: dict[str, Any]) -> dict[str, Any]:
    """Emit only controls proven by the shared template capability resolver."""
    controls = config.get("_reasoning_template_controls", ())
    return {key: config[key] for key in controls if key in config and config[key] is not None}
