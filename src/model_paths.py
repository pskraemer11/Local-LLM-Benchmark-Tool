"""Resolve the ordered local roots used for GGUF model discovery.

The project keeps the model files outside the repository.  The default
location is the current dedicated model volume, while the former LM Studio
location remains a compatibility fallback.  Callers may provide one explicit
root when an isolated scan is required (for example in tests).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: Candidate roots in discovery priority order.  The model volume holds
#: several sibling directories; ``Llama-GGUF`` is the llama.cpp layout and
#: carries the current local collection.  A root that does not exist is
#: skipped, so the list tolerates a renamed or reorganised volume instead of
#: silently finding nothing.
PRIMARY_GGUF_ROOT = Path(r"D:\LLM-Modelle\Llama-GGUF")
#: The former dedicated-model-volume layout.  Kept as a fallback because a
#: reinstall may use either spelling.
ALTERNATE_GGUF_ROOT = Path(r"D:\LLM-Modelle\models")
LEGACY_GGUF_ROOT = Path.home() / ".lmstudio" / "models"

# GGUF_MODEL_ROOT is provider-neutral.  The other two names predate this
# module and remain supported for existing Unsloth/LM Studio setups.
#: Set once so a stale environment override is reported once per process.
_WARNED_STALE_ROOT = False

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
    single-root configuration.  Without an override, the llama.cpp model
    directory is primary, the alternate volume spelling is the first
    fallback, and the former LM Studio directory is the last one.
    Junctions and equivalent spellings are removed after path resolution.

    An override that points at a missing directory is reported and ignored
    instead of hiding the local collection.
    """
    configured: list[tuple[str, Path]] = []
    if explicit_root is not None:
        return _deduplicate_roots((Path(explicit_root),))

    # An environment override is a deliberate single-root configuration, but
    # it must not hide the local collection when it points at a directory
    # that no longer exists.  A stale override would otherwise make the
    # Registry scan find nothing at all, which reads like "no models
    # installed" instead of "the configured path is wrong".
    for variable in _ROOT_ENV_VARS:
        value = os.environ.get(variable, "").strip()
        if not value:
            continue
        override = Path(value).expanduser()
        if override.is_dir():
            return _deduplicate_roots((override,))
        configured.append((variable, override))

    roots = [PRIMARY_GGUF_ROOT, ALTERNATE_GGUF_ROOT, LEGACY_GGUF_ROOT]
    global _WARNED_STALE_ROOT
    if configured and not _WARNED_STALE_ROOT:
        # Keep the broken override visible in the report instead of silently
        # using a different collection. The warning is emitted once per
        # process; the root resolution runs for every inventory refresh.
        _WARNED_STALE_ROOT = True
        stale = ", ".join(f"{name}={path}" for name, path in configured)
        print(
            f"[WARN] GGUF-Root aus Umgebung nicht erreichbar ({stale}); "
            f"verwende {', '.join(str(root) for root in roots)}",
            file=sys.stderr,
        )
    return _deduplicate_roots(tuple(roots))
