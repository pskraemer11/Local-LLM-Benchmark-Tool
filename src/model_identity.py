"""Zentrale Modell-Identitaet: Normalisierung, Matching und Familien-Aliasse.

Konsolidiert die frueher verstreuten Normalisierungs- und Klassifikations-
Regeln (Fix 2026-08-09):
  - assemble_blueprint.normalize_model_name / normalize_for_config
  - benchmark_config._normalize_lms_model_name / _normalized_lms_key
  - registry_tool._normalize_variants / _ARCH_REASONING_MAP

Alle Normalisierer verhalten sich exakt wie vor der Konsolidierung -
die Stellen importieren nur noch von hier (eine Quelle der Wahrheit).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

# ── Normalisierung (exakt wie assemble_blueprint.normalize_model_name) ──


def normalize_model_name(name: str) -> str:
    """Normalize a model name for matching between registry and directory names.

    Behaelt @quant-Suffixe (z.B. @iq4_nl) bewusst bei - siehe
    normalize_for_config fuer eine breitere Variante.
    """
    s = name.lower()
    s = re.sub(r"\.gguf$", "", s)
    s = re.sub(r"-(gguf|mxfp4)$", "", s)
    # Strip -gguf-/-mxfp4- also from middle (Intel/JetBrains naming convention)
    s = re.sub(r"[-_](gguf|mxfp4)[-_]", r"-", s)
    # Strip publisher prefix (e.g., "mradermacher/", "unsloth/")
    s = re.sub(r"^[^/]+/", "", s)
    # Normalize separators: dots and underscores become hyphens
    s = s.replace(".", "-").replace("_", "-")
    # Collapse multiple hyphens
    while "--" in s:
        s = s.replace("--", "-")
    return s


_VARIANT_SUFFIXES = (
    "-ud",          # Unsloth distilled
    "-qat",         # Quantization-aware training variant: wird "qat" geschrieben, nicht "quat"!
    "-imatrix",     # Importance-matrix quant
)

_QUANT_DIR_SUFFIXES = (
    "-mxfp4", "-gguf", "-mxpr4", "-q4-0", "-q4-k", "-q5-0", "-q5-k", "-q6-k", "-q8-0",
    "-q2-k", "-q3-k", "-q1-0",
)


def normalize_for_config(name: str) -> str:
    """Broader normalization for config matching.

    Like normalize_model_name but also strips:
    - Quantization suffixes (@q4_0, @iq4_nl, etc.)
    - Variant suffixes (-ud, -quat, -imatrix)
    - Quant/format suffixes in directory names (-mxfp4, -gguf, -q4_0, -q8_0, etc.)
    """
    s = normalize_model_name(name)
    # Strip @quant suffix (e.g. @iq4_nl, @q4_k_s, @q5_0)
    idx = s.find("@")
    if idx > 0:
        s = s[:idx]
    # Strip variant suffixes
    for suffix in _VARIANT_SUFFIXES:
        if s.endswith(suffix):
            s = s[:-len(suffix)]
            break
    # Strip common quant/format suffixes in directory names
    for suffix in _QUANT_DIR_SUFFIXES:
        if s.endswith(suffix):
            s = s[:-len(suffix)]
            break
    # Strip -gguf-* patterns (e.g., -gguf-mxfp4-moe, -gguf-q4-k-m)
    if "-gguf" in s:
        idx = s.find("-gguf")
        s = s[:idx]
    # Strip -mxfp4-* patterns (e.g., -mxfp4-moe) -> preserve trailing hyphen
    if "-mxfp4-" in s:
        idx = s.find("-mxfp4-")
        s = s[:idx] + "-" + s[idx+len("-mxfp4-"):]
    return s


# ── LMS-Variante (exakt wie benchmark_config._normalize_lms_model_name) ──
# Unterschied zu normalize_model_name: entfernt zusaetzlich @quant-Suffixe
# bereits zu Beginn via Regex (Registry-Key-Form).

_LMS_QUANT_RE = re.compile(r"@[a-z0-9_?]+$")


def normalize_lms_model_name(name: str) -> str:
    """Normalize a model/config name for matching (LMS/Config-Key-Form).

    Wie normalize_model_name, aber strippt @quant-Suffixe (Registry-Key-Form).
    """
    s = str(name).lower()
    s = _LMS_QUANT_RE.sub("", s)  # @quant-Suffixe (Registry-Key) entfernen
    s = re.sub(r"\.gguf$", "", s)
    s = re.sub(r"-(gguf|mxfp4)$", "", s)
    s = re.sub(r"[-_](gguf|mxfp4)[-_]", "-", s)
    s = re.sub(r"^[^/]+/", "", s)  # Publisher-Prefix entfernen
    s = s.replace(".", "-").replace("_", "-")
    while "--" in s:
        s = s.replace("--", "-")
    return s


def normalized_lms_key(name: str) -> str:
    """Normalisierter Matching-Key eines Modellnamens (Registry-Key-Form).

    Wie normalize_lms_model_name, zusaetzlich Variant-Suffixe entfernt.
    """
    key = normalize_lms_model_name(name)
    return re.sub(r"-(ud|qat|imatrix)$", "", key)  # Variant-Suffixe (Registry-Key)


# ── Varianten (exakt wie registry_tool._normalize_variants) ──


def normalize_variants(key: str) -> set[str]:
    """All normalized spellings of a model key.

    Covers publisher prefixes (``unsloth/x`` vs ``x`` vs ``unsloth_x``),
    quant suffixes are stripped via the ``@`` split. Only used for
    **exact** comparisons, never for fuzzy word matching.
    """
    base = key.split("@", 1)[0]
    variants = {normalize_model_name(base)}
    if "/" in base:
        variants.add(normalize_model_name(base.split("/", 1)[1]))
    if "_" in base:
        variants.add(normalize_model_name(base.replace("_", "-")))
    return variants


# ── Familien-Aliasse ────────────────────────────────────────────────
# Ersetzt die Substring-Schleife in _ARCH_REASONING_MAP. Reihenfolge ist
# SIGNIFIKANT: "qwen3" ⊂ "qwen35" - qwen35/qwen35moe MUSS vor qwen3/qwen3moe
# geprueft werden (siehe ARCH_KEYS in Match-Reihenfolge).


@dataclass(frozen=True)
class ModelFamily:
    name: str                   # kanonischer Familienname (z.B. "qwen3.6")
    arch_keys: tuple[str, ...]  # Substring-Keys in Match-Reihenfolge
    reasoning: str              # Default-Reasoning-Typ
    qwen_special: bool = False  # Qwen-Sonderlogik (Name-basierte Unterscheidung)


MODEL_FAMILIES: tuple[ModelFamily, ...] = (
    ModelFamily("qwen3.6-moe", ("qwen35moe",), "thinking", qwen_special=True),
    ModelFamily("qwen3.6", ("qwen35",), "thinking", qwen_special=True),
    ModelFamily("qwen3-moe", ("qwen3moe",), "instruct", qwen_special=True),
    ModelFamily("qwen3", ("qwen3",), "instruct", qwen_special=True),
    ModelFamily("deepseek2", ("deepseek2",), "thinking"),
    ModelFamily("kimi-linear", ("kimi-linear",), "thinking"),
    ModelFamily("gpt-oss", ("gpt-oss",), "thinking"),
    ModelFamily("nomic-bert", ("nomic-bert",), "none"),
    ModelFamily("flux", ("flux",), "none"),
)


def _arch_reasoning_map() -> dict[str, str]:
    """Kompatibilitaets-Sicht: arch_key -> reasoning (wie bisherige Map)."""
    return {ak: fam.reasoning for fam in MODEL_FAMILIES for ak in fam.arch_keys}


def family_for_arch(arch: str) -> ModelFamily | None:
    """Familie zu einem Arch-Namen (Substring-Match, Reihenfolge der Map)."""
    arch_lower = arch.lower().replace(".", "")  # normalize: "Qwen3.5" → "qwen35"
    for fam in MODEL_FAMILIES:
        for ak in fam.arch_keys:
            if ak in arch_lower:
                return fam
    return None


def family_for_name(name: str) -> ModelFamily | None:
    """Familie zu einem Modellnamen (normalisierter Substring-Match)."""
    norm = normalize_model_name(name)
    for fam in MODEL_FAMILIES:
        for ak in fam.arch_keys:
            if ak in norm:
                return fam
    return None


def classify_reasoning_by_family(model_name: str, arch: str) -> str | None:
    """Reasoning-Klassifikation ueber die Familien-Map (Sonderlogik inklusive).

    Rueckgabe: reasoning-Typ oder None, wenn keine Familie matcht.
    """
    fam = family_for_arch(arch) if arch else family_for_name(model_name)
    if fam is None:
        return None
    name_lower = model_name.lower()
    if fam.qwen_special:
        if "thinking" in name_lower:
            return "thinking"
        if "instruct" in name_lower or "coder" in name_lower:
            return "instruct"
    return fam.reasoning


# ── Deterministisches Registry-Matching ─────────────────────────────
# Reihenfolge: Exact -> Publisher-stripped Exact -> Praefix/Suffix ->
# @quant-stripped Exact (broad). Kein Substring-Fuzzy.


def match_registry_key(name: str, keys: list[str]) -> str | None:
    """Deterministischer 1:1-Match eines Namens gegen Registry-Keys.

    Reihenfolge:
      1. Exact (normalized, inkl. @quant)
      2. Exact (normalize_for_config - @quant/varianten gestrippt)
      3. Praefix/Suffix-Exact (key ist Praefix/Suffix des Namens oder umgekehrt)
    Kein Substring-Fuzzy. Rueckgabe: Registry-Key oder None.
    """
    if not name or not keys:
        return None
    norm = normalize_model_name(name)
    broad = normalize_for_config(name)

    exact = {normalize_model_name(k) for k in keys}
    if norm in exact:
        return _first_key_with(norm, keys, normalize_model_name)

    broad_keys = {normalize_for_config(k) for k in keys}
    if broad in broad_keys:
        return _first_key_with(broad, keys, normalize_for_config)

    # Praefix/Suffix nur bei EINDEUTIGEM Treffer (sonst None - Aufrufer meldet).
    # Beispiel: "GLM-4.7-Flash-REAP-23B-A3B-Q4_K_S" darf nicht auf "glm-4.7-flash"
    # matchen, wenn es auch einen REAP-Key gibt.
    prefix_suffix: list[str] = []
    for k in keys:
        kn = normalize_model_name(k)
        if norm.startswith(kn + "-") or kn.startswith(norm + "-"):
            prefix_suffix.append(k)
        elif norm.endswith("-" + kn) or kn.endswith("-" + norm):
            prefix_suffix.append(k)
    if len(prefix_suffix) == 1:
        return prefix_suffix[0]
    return None


def _first_key_with(norm_key: str, keys: list[str], normalize: Callable[[str], str]) -> str | None:
    for k in keys:
        if normalize(k) == norm_key:
            return k
    return None
