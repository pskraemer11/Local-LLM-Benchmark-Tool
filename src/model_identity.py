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

from quantization import KNOWN_QUANTS

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True)
class UniqueMatch:
    """A unique Registry match and the matching strategy that produced it."""

    requested: str
    key: str
    stage: str


@dataclass(frozen=True)
class AmbiguousMatch:
    """A match that must not be resolved by iteration order."""

    requested: str
    candidates: tuple[str, ...]
    stage: str


@dataclass(frozen=True)
class Unmatched:
    """No Registry key matched the requested identity."""

    requested: str


type RegistryMatch = UniqueMatch | AmbiguousMatch | Unmatched

# ── Normalisierung (exakt wie assemble_blueprint.normalize_model_name) ──


def decompose_model_identity(key: str) -> tuple[str, str, str]:
    """Extract the canonical identity triple (publisher, model, quant) from a registry key.

    A valid registry key ALWAYS has the form ``publisher/modelname@quant``.
    The triple is the unique identity — no model is fully identified without all three parts.

    Returns:
        (publisher, model_name, quant) where quant is the @-suffix (without @) or "" if absent.
    """
    key = key.strip()
    if "@" in key:
        base, quant = key.split("@", 1)
    else:
        base, quant = key, ""
    if "/" in base:
        publisher, model = base.split("/", 1)
    else:
        publisher, model = "", base
    return publisher.lower(), model.lower(), quant.lower()


def build_model_identity(publisher: str, model_name: str, quant: str = "") -> str:
    """Build a canonical ``publisher/model@quant`` identity key.

    Publisher, model, and quantization are normalized to lowercase. The
    quantization suffix is optional for legacy base-key operations, although
    benchmark Registry identities should normally provide it.
    """
    normalized_publisher = str(publisher or "").strip().lower()
    normalized_model = str(model_name or "").strip().lower()
    normalized_quant = str(quant or "").strip().lstrip("@").lower()
    if not normalized_model:
        raise ValueError("model_name must not be empty")
    base = f"{normalized_publisher}/{normalized_model}" if normalized_publisher else normalized_model
    return f"{base}@{normalized_quant}" if normalized_quant else base


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


def _normalize_identity_component(value: str) -> str:
    """Normalize one publisher/model component without stripping its owner."""
    s = str(value or "").strip().lower()
    s = re.sub(r"\.gguf$", "", s)
    s = re.sub(r"-(gguf|mxfp4)$", "", s)
    s = re.sub(r"[-_](gguf|mxfp4)[-_]", "-", s)
    s = s.replace(".", "-").replace("_", "-")
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-")


def normalize_registry_identity(key: str, *, include_quant: bool = True) -> str:
    """Normalize a Registry identity while preserving the publisher prefix.

    ``normalize_model_name`` is intentionally publisher-agnostic for legacy
    filename matching.  Runtime identity matching must first use this
    publisher-aware form so two publishers cannot shadow each other.
    """
    publisher, model, quant = decompose_model_identity(key)
    normalized_model = (
        _normalize_identity_component(model)
        if include_quant
        else normalize_for_config(model)
    )
    normalized = build_model_identity(
        _normalize_identity_component(publisher),
        normalized_model,
        _normalize_identity_component(quant) if include_quant else "",
    )
    return normalized


def normalize_registry_base_identity(key: str) -> str:
    """Normalize a publisher-aware base while preserving model variants.

    This removes only the ``@quant`` component.  Variant markers such as
    ``-qat`` remain part of the base so a specific variant can beat a broader
    variant-stripped fallback without relying on registry iteration order.
    """
    publisher, model, _ = decompose_model_identity(key)
    return build_model_identity(
        _normalize_identity_component(publisher),
        _normalize_identity_component(model),
    )


def normalize_match_base_identity(key: str) -> str:
    """Normalize a publisherless base while preserving model variants."""
    return normalize_model_name(key).split("@", 1)[0]


def normalize_match_identity(key: str, *, include_quant: bool = True) -> str:
    """Normalize the historical publisher-stripped matching namespace."""
    normalized = normalize_model_name(key)
    if not include_quant:
        normalized = normalized.split("@", 1)[0]
    return normalized


def unique_normalized_index(keys: list[str], *, include_quant: bool = True) -> dict[str, str]:
    """Build a first-safe index containing only unique normalized identities."""
    grouped: dict[str, list[str]] = {}
    for key in keys:
        normalized = normalize_match_identity(key, include_quant=include_quant)
        grouped.setdefault(normalized, []).append(key)
    return {
        normalized: candidates[0]
        for normalized, candidates in grouped.items()
        if len(candidates) == 1
    }


def find_match_collisions(keys: list[str]) -> dict[str, tuple[str, ...]]:
    """Return publisher-stripped exact collisions used by legacy matchers.

    The publisher-aware resolver remains able to select an explicitly named
    publisher.  The collision is nevertheless a Registry data-quality error:
    publisherless LMS/path inputs cannot identify one of these keys safely.
    """
    grouped: dict[str, list[str]] = {}
    for key in keys:
        normalized = normalize_match_identity(key)
        grouped.setdefault(normalized, []).append(key)
    return {
        normalized: tuple(candidates)
        for normalized, candidates in grouped.items()
        if len(candidates) > 1
    }


_VARIANT_SUFFIXES = (
    "-ud",          # Unsloth distilled
    "-qat",         # Quantization-aware training variant: wird "qat" geschrieben, nicht "quat"!
    "-imatrix",     # Importance-matrix quant
)

_QUANT_DIR_SUFFIXES = tuple(
    sorted(
        {f"-{quant.replace('_', '-')}" for quant in KNOWN_QUANTS} | {"-gguf"},
        key=len,
        reverse=True,
    )
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
    # Strip variant and quant/format suffixes repeatedly. LM Studio paths
    # may combine them, e.g. ``...-QAT-NVFP4-GGUF``; a single pass leaves
    # ``-qat`` behind and makes registry/config matching asymmetric.
    while True:
        before = s
        for suffix in _VARIANT_SUFFIXES:
            if s.endswith(suffix):
                s = s[:-len(suffix)]
                break
        for suffix in _QUANT_DIR_SUFFIXES:
            if s.endswith(suffix):
                s = s[:-len(suffix)]
                break
        if s == before:
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
    ModelFamily("qwen3.8", ("qwen38",), "thinking", qwen_special=True),
    ModelFamily("qwen3.6-moe", ("qwen35moe",), "thinking", qwen_special=True),
    ModelFamily("qwen3.6", ("qwen35",), "thinking", qwen_special=True),
    ModelFamily("qwen3-moe", ("qwen3moe",), "instruct", qwen_special=True),
    ModelFamily("qwen3", ("qwen3",), "instruct", qwen_special=True),
    ModelFamily("qwen2", ("qwen2",), "instruct"),
    ModelFamily("deepseek2", ("deepseek2",), "thinking"),
    ModelFamily("ernie4.5-moe", ("ernie4_5-moe",), "instruct"),
    ModelFamily("gemma4", ("gemma4",), "thinking"),
    ModelFamily("gemma3", ("gemma3",), "instruct"),
    ModelFamily("gemma2", ("gemma2",), "instruct"),
    ModelFamily("glm4", ("glm4",), "thinking"),
    ModelFamily("kimi-linear", ("kimi-linear",), "thinking"),
    ModelFamily("gpt-oss", ("gpt-oss",), "thinking"),
    ModelFamily("granitehybrid", ("granitehybrid",), "instruct"),
    ModelFamily("granite", ("granite",), "instruct"),
    ModelFamily("internlm2", ("internlm2",), "instruct"),
    ModelFamily("lfm2moe", ("lfm2moe",), "instruct"),
    ModelFamily("lfm2", ("lfm2",), "instruct"),
    ModelFamily("llama", ("llama",), "instruct"),
    ModelFamily("mellum", ("mellum",), "instruct"),
    ModelFamily("mistral3", ("mistral3",), "instruct"),
    ModelFamily("muse-glimmer", ("muse-glimmer",), "instruct"),
    ModelFamily("starcoder2", ("starcoder2",), "instruct"),
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
# Reihenfolge: Publisher-aware Exact -> Publisherless Exact (nur eindeutig) ->
# Publisher-aware Base -> Publisherless Base (nur eindeutig) -> Prefix/Suffix.
# Kein Substring-Fuzzy und kein First-Wins.


def resolve_registry_match(name: str, keys: list[str]) -> RegistryMatch:
    """Deterministischer 1:1-Match eines Namens gegen Registry-Keys.

    Reihenfolge:
      1. Exact (normalized, inkl. @quant)
      2. Exact (normalize_for_config - @quant/varianten gestrippt)
      3. Praefix/Suffix-Exact (key ist Praefix/Suffix des Namens oder umgekehrt)
    Kein Substring-Fuzzy und kein First-Wins. Die Rueckgabe unterscheidet
    explizit zwischen eindeutigem, mehrdeutigem und nicht vorhandenem Treffer;
    ``match_registry_key`` bietet fuer alte Aufrufer weiterhin die schmalere
    ``key | None``-Sicht.
    """
    if not name or not keys:
        return Unmatched(name)

    def unique_stage(normalized: str, normalizer: Callable[[str], str], stage: str) -> RegistryMatch | None:
        candidates = tuple(key for key in keys if normalizer(key) == normalized)
        if len(candidates) == 1:
            return UniqueMatch(name, candidates[0], stage)
        if len(candidates) > 1:
            return AmbiguousMatch(name, candidates, stage)
        return None

    # Explicit publisher/model/quant identity is authoritative.
    normalized_identity = normalize_registry_identity(name)
    exact = unique_stage(normalized_identity, normalize_registry_identity, "publisher-aware-exact")
    if exact is not None:
        return exact

    # Publisherless exact matching remains supported only when it is unique.
    norm = normalize_match_identity(name)
    publisherless_exact = unique_stage(norm, normalize_match_identity, "publisherless-exact")
    if publisherless_exact is not None:
        return publisherless_exact

    # Remove only quantization first. This preserves discriminating markers
    # such as ``-qat`` and can safely resolve a unique repack/variant even if
    # the requested publisher is an alias not present in the Registry.
    variant_identity = normalize_registry_base_identity(name)
    variant_explicit = unique_stage(
        variant_identity,
        normalize_registry_base_identity,
        "publisher-aware-variant-base",
    )
    if variant_explicit is not None:
        return variant_explicit

    # Finally allow the historical broad base fallback, including known
    # ``-qat``/``-ud``/``-imatrix`` aliases, but only when it is unique.
    broad_identity = normalize_registry_identity(name, include_quant=False)
    broad_explicit = unique_stage(
        broad_identity,
        lambda key: normalize_registry_identity(key, include_quant=False),
        "publisher-aware-base",
    )
    if broad_explicit is not None:
        return broad_explicit

    # If the requested publisher is an alias, a specific variant can still be
    # safe when it is unique across publishers. This must come after the
    # publisher-aware broad stage so an explicit publisher always wins.
    variant = normalize_match_base_identity(name)
    variant_match = unique_stage(variant, normalize_match_base_identity, "publisherless-variant-base")
    if variant_match is not None:
        return variant_match

    broad = normalize_for_config(name)
    broad_match = unique_stage(broad, normalize_for_config, "publisherless-base")
    if broad_match is not None:
        return broad_match

    # Praefix/Suffix nur bei EINDEUTIGEM Treffer (sonst None - Aufrufer meldet).
    # Beispiel: "GLM-4.7-Flash-REAP-23B-A3B-Q4_K_S" darf nicht auf "glm-4.7-flash"
    # matchen, wenn es auch einen REAP-Key gibt.
    prefix_suffix: list[str] = []
    norm = normalize_model_name(name)
    for k in keys:
        kn = normalize_model_name(k)
        if norm.startswith(kn + "-") or kn.startswith(norm + "-"):
            prefix_suffix.append(k)
        elif norm.endswith("-" + kn) or kn.endswith("-" + norm):
            prefix_suffix.append(k)
    if len(prefix_suffix) == 1:
        return UniqueMatch(name, prefix_suffix[0], "prefix-suffix")
    if len(prefix_suffix) > 1:
        return AmbiguousMatch(name, tuple(prefix_suffix), "prefix-suffix")
    return Unmatched(name)


def match_registry_key(name: str, keys: list[str]) -> str | None:
    """Compatibility wrapper returning a key only for a unique match."""
    result = resolve_registry_match(name, keys)
    return result.key if isinstance(result, UniqueMatch) else None
