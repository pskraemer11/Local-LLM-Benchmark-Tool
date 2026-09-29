"""Transport-neutral evidence checks for bounded model generation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping


TERMINAL_GENERATION_ERRORS = frozenset(
    {
        "timeout",
        "output_budget_exceeded",
        "reasoning_budget_exceeded",
        "repetition_loop",
    }
)


@dataclass(frozen=True)
class GenerationViolation:
    """A proven usage overrun or a deterministic repeated-output pattern."""

    error_type: str
    detail: str


class GenerationLimitError(RuntimeError):
    """Propagate a terminal violation across a non-streaming transport seam."""

    def __init__(self, violation: GenerationViolation, usage: object = None) -> None:
        super().__init__(violation.detail)
        self.violation = violation
        self.usage: dict[str, Any] = dict(usage) if isinstance(usage, dict) else {}


def _positive_limit(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def reported_reasoning_tokens(usage: object) -> int | None:
    """Read reported reasoning usage, never infer it from generated text."""
    details = usage.get("completion_tokens_details") if isinstance(usage, dict) else None
    value = details.get("reasoning_tokens") if isinstance(details, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def generation_usage_violation(
    payload: Mapping[str, Any],
    usage: object,
    *,
    reasoning_budget: object = None,
) -> GenerationViolation | None:
    """Check exact reported counts; completion already includes reasoning."""
    if not isinstance(usage, dict):
        return None
    output_limits = [
        limit
        for key in ("max_tokens", "max_completion_tokens")
        if (limit := _positive_limit(payload.get(key))) is not None
    ]
    output = usage.get("completion_tokens")
    if output_limits and isinstance(output, int) and not isinstance(output, bool) and output > min(output_limits):
        return GenerationViolation(
            "output_budget_exceeded",
            f"Server exceeded max_tokens: reported {output}, requested {min(output_limits)}",
        )
    reasoning_limits = [
        limit
        for value in (
            reasoning_budget,
            payload.get("max_thinking_tokens"),
            payload.get("reasoning_budget"),
        )
        if (limit := _positive_limit(value)) is not None
    ]
    reasoning = reported_reasoning_tokens(usage)
    if reasoning_limits and reasoning is not None and reasoning > min(reasoning_limits):
        return GenerationViolation(
            "reasoning_budget_exceeded",
            f"Server exceeded reasoning budget: reported {reasoning}, requested {min(reasoning_limits)}",
        )
    return None


class RepetitionGuard:
    """Detect four consecutive substantial blocks across arbitrary deltas.

    Whitespace is normalized incrementally. Each channel retains at most
    32768 characters, checking every 64 new characters and on completion. At
    most 64 matching anchors are considered per check. Ordinary content needs
    a 256-character block with varied words; explicit infinite-loop syntax in
    Python/JavaScript code fences may use shorter blocks. This is a repeated-
    output guard, not a tokenizer.
    """

    def __init__(self) -> None:
        self._tail = ""
        self._pending_chars = 0
        self._trailing_space = False

    def feed(self, fragment: str) -> bool:
        """Return true once a repeated-block suffix has been established."""
        if not fragment:
            return False
        normalized = re.sub(r"\s+", " ", fragment)
        if self._trailing_space and normalized.startswith(" "):
            normalized = normalized[1:]
        self._trailing_space = fragment[-1].isspace()
        offset = 0
        while offset < len(normalized):
            width = min(64 - self._pending_chars, len(normalized) - offset)
            self._tail = (self._tail + normalized[offset : offset + width])[-32768:]
            self._pending_chars += width
            offset += width
            if self._pending_chars == 64:
                self._pending_chars = 0
                if self._repeated_suffix():
                    return True
        return False

    def finish(self) -> bool:
        """Check a final partial interval without waiting for another delta."""
        return self._repeated_suffix()

    def _repeated_suffix(self) -> bool:
        text = self._tail
        if len(text) < 1024:
            return False
        anchor_start = len(text) - 64
        anchor = text[-64:]
        search_end = anchor_start
        for _ in range(64):
            previous = text.rfind(anchor, max(0, anchor_start - 8192), search_end)
            if previous < 0:
                return False
            search_end = previous
            period = anchor_start - previous
            if period < 32 or len(text) < period * 4:
                continue
            block = text[-period:]
            if all(text[-period * (index + 1) : len(text) - period * index] == block for index in range(1, 4)):
                is_code_loop = _contains_explicit_infinite_loop(block)
                if is_code_loop:
                    return True
                # Do not interpret repetitions of short filler phrases as a
                # larger period simply because the search finds a multiple.
                if period < 256:
                    return False
                words = re.findall(r"\w+", block)
                if len(words) >= 24 and len(set(words)) >= 12:
                    return True
        return False


def _contains_explicit_infinite_loop(block: str) -> bool:
    """Identify explicit, repeated infinite loops inside Python/JS code fences."""
    if not re.search(r"```\s*(?:python|py|javascript|js|typescript|ts)\b", block, re.IGNORECASE):
        return False
    return bool(
        re.search(r"\bwhile\s*\(?\s*(?:true|1)\s*\)?\s*[:{]", block, re.IGNORECASE)
        or re.search(r"\bfor\s*\(\s*;\s*;\s*\)", block, re.IGNORECASE)
    )
