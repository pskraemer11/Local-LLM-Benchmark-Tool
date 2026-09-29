"""Canonical quantization vocabulary shared by all model boundaries.

The Registry stores a normalized spelling in ``publisher/model@quant`` while
LM Studio, GGUF filenames, and Hugging Face repositories may use hyphens,
underscores, or a small number of aliases.  This module owns those aliases;
callers should retain the raw source value separately when reporting evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


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
    QuantizationSpec("q2_sym32k4"),
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
    # LM Studio / community GGUF filenames use Q6_K_L for a distinct larger
    # variant. Keep the trailing L: collapsing it to Q6_K creates identity
    # collisions and makes exact Registry-to-config joins fail closed.
    QuantizationSpec("q6_k_l"),
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
    alias.replace("-", "_").casefold(): spec.canonical for spec in _SPECS for alias in (spec.canonical, *spec.aliases)
}
_QUANT_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    + "|".join(re.escape(value).replace("_", r"[_-]") for value in sorted(_ALIASES, key=len, reverse=True))
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


def quant_from_gguf_evidence(
    filename: str,
    *,
    publisher: str | None,
    file_type: object,
    tensor_types: Mapping[str, int],
) -> str | None:
    """Resolve a filename or a publisher-scoped, independently backed format.

    ``publisher`` must come from the physical artifact source identity. Fork
    enum values are not globally unique. llmsforall's llama.h and ggml.h both
    define Q2_SYM32K4 as 56; require both the file-level declaration and an
    actual tensor using that type before identifying a filename without quant.
    """
    named_quant = extract_quant_from_text(filename)
    if named_quant is not None:
        return named_quant
    if (
        str(publisher or "").strip().casefold() == "llmsforall"
        and isinstance(file_type, int)
        and not isinstance(file_type, bool)
        and file_type == 56
        and any(
            isinstance(value, int) and not isinstance(value, bool) and value == 56 for value in tensor_types.values()
        )
    ):
        return "q2_sym32k4"
    return None
