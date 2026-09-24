"""Canonical quantization vocabulary shared by all model boundaries.

The Registry stores a normalized spelling in ``publisher/model@quant`` while
LM Studio, GGUF filenames, and Hugging Face repositories may use hyphens,
underscores, or a small number of aliases.  This module owns those aliases;
callers should retain the raw source value separately when reporting evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class QuantizationSpec:
    """One canonical quantization marker and its accepted spellings."""

    canonical: str
    aliases: tuple[str, ...] = ()


_SPECS = (
    QuantizationSpec("q1_0"),
    QuantizationSpec("q2_k"),
    QuantizationSpec("q2_k_s"),
    QuantizationSpec("q2_k_m"),
    QuantizationSpec("q2_k_l"),
    QuantizationSpec("q2_g64"),
    QuantizationSpec("q3_k_xs"),
    QuantizationSpec("q3_k_s"),
    QuantizationSpec("q3_k_m"),
    QuantizationSpec("q3_k_l"),
    QuantizationSpec("q4_0"),
    QuantizationSpec("q4_1"),
    QuantizationSpec("q4_k_s"),
    QuantizationSpec("q4_k_m"),
    QuantizationSpec("q4_k_xl"),
    QuantizationSpec("q5_0"),
    QuantizationSpec("q5_1"),
    QuantizationSpec("q5_k_s"),
    QuantizationSpec("q5_k_m"),
    QuantizationSpec("q6_k"),
    QuantizationSpec("q8_0_i"),
    QuantizationSpec("q8_0"),
    QuantizationSpec("q8_1"),
    QuantizationSpec("iq1_s"),
    QuantizationSpec("iq1_m"),
    QuantizationSpec("iq2_xxs"),
    QuantizationSpec("iq2_xs"),
    QuantizationSpec("iq2_s"),
    QuantizationSpec("iq2_m"),
    QuantizationSpec("iq3_xxs"),
    QuantizationSpec("iq3_xs"),
    QuantizationSpec("iq3_s"),
    QuantizationSpec("iq3_m"),
    QuantizationSpec("iq3_nl"),
    QuantizationSpec("iq4_xs"),
    QuantizationSpec("iq4_nl"),
    QuantizationSpec("iq5_0"),
    QuantizationSpec("iq5_1"),
    QuantizationSpec("iq5_2"),
    QuantizationSpec("mxfp4"),
    QuantizationSpec("mxpr4"),
    QuantizationSpec("nvfp4"),
    QuantizationSpec("mini"),
    QuantizationSpec("fp16"),
    QuantizationSpec("f16", ("float16",)),
    QuantizationSpec("bf16"),
)

QUANTIZATION_SPECS: tuple[QuantizationSpec, ...] = _SPECS
KNOWN_QUANTS: tuple[str, ...] = tuple(spec.canonical for spec in _SPECS)
_ALIASES = {
    alias.replace("-", "_").casefold(): spec.canonical
    for spec in _SPECS
    for alias in (spec.canonical, *spec.aliases)
}
_QUANT_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    + "|".join(
        re.escape(value).replace("_", r"[_-]")
        for value in sorted(_ALIASES, key=len, reverse=True)
    )
    + r")(?![a-z0-9])",
    re.IGNORECASE,
)


def normalize_quant(value: str) -> str:
    """Return the canonical spelling or the normalized unknown value."""
    normalized = str(value or "").strip().lstrip("@").casefold().replace("-", "_")
    return _ALIASES.get(normalized, normalized)


def extract_quant_from_text(value: str) -> str | None:
    """Extract the last known quant marker from a filename or directory name."""
    matches = _QUANT_RE.findall(str(value or ""))
    return normalize_quant(matches[-1]) if matches else None


def is_known_quant(value: str) -> bool:
    """Return whether a value belongs to the shared quantization vocabulary."""
    return normalize_quant(value) in KNOWN_QUANTS
