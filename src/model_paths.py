"""Resolve the ordered local roots used for GGUF model discovery.

The project keeps the model files outside the repository.  The default
location is the current dedicated model volume, while the former LM Studio
location remains a compatibility fallback.  Callers may provide one explicit
root when an isolated scan is required (for example in tests).
"""

from __future__ import annotations

import os
from pathlib import Path

PRIMARY_GGUF_ROOT = Path(r"D:\LLM-Modelle\models")
LEGACY_GGUF_ROOT = Path.home() / ".lmstudio" / "models"

# GGUF_MODEL_ROOT is provider-neutral.  The other two names predate this
# module and remain supported for existing Unsloth/LM Studio setups.
_ROOT_ENV_VARS = (
    "LLAMA_ARG_MODELS_DIR",
    "GGUF_MODEL_ROOT",
    "UNSLOTH_MODEL_ROOT",
    "LMSTUDIO_MODELS_DIR",
)


def _deduplicate_roots(roots: tuple[Path, ...]) -> tuple[Path, ...]:
    """Keep the first spelling of each physical/root path."""
    result: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        expanded = root.expanduser()
        try:
            identity = str(expanded.resolve(strict=False)).casefold()
        except OSError:
            identity = str(expanded.absolute()).casefold()
        if identity in seen:
            continue
        seen.add(identity)
        result.append(expanded)
    return tuple(result)


def configured_gguf_roots(explicit_root: str | Path | None = None) -> tuple[Path, ...]:
    """Return GGUF roots in discovery priority order.

    An explicit constructor argument or environment override is a deliberate
    single-root configuration.  Without an override, the dedicated model
    volume is primary and the former LM Studio directory is the fallback.
    Junctions and equivalent spellings are removed after path resolution.
    """
    if explicit_root is not None:
        return _deduplicate_roots((Path(explicit_root),))

    for variable in _ROOT_ENV_VARS:
        value = os.environ.get(variable, "").strip()
        if value:
            return _deduplicate_roots((Path(value),))

    return _deduplicate_roots((PRIMARY_GGUF_ROOT, LEGACY_GGUF_ROOT))
