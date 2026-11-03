"""Materialize GGUF chat templates for the native llama.cpp path.

The GGUF file is the authoritative source of a model's chat template. A
versioned copy under ``docs/Jinja-Chat-Templates/`` is a second, manually
maintained representation that drifts silently: the upstream template changes
with every model revision and nobody updates the copy.

The native llama.cpp server only injects a tool schema into the prompt when
it receives ``--chat-template-file``. Without that flag the model never sees
the tools, which looks like a missing model capability. The file has to be a
real Jinja file, so the template is extracted from the GGUF metadata into a
machine-local cache directory and referenced from there.

The cache is derived data. It is never a source of truth and never part of
the Registry.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Mapping
from pathlib import Path

#: Machine-local cache for extracted templates. It sits next to the local
#: Registry so that both stay outside the versioned source tree.
DEFAULT_CACHE_ROOT = Path(
    os.environ.get("BENCHMARKS_TEMPLATE_CACHE")
    or (Path(__file__).resolve().parents[1] / "data" / "chat_templates")
)

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def cache_root() -> Path:
    """Return the template cache directory, creating it on demand."""
    root = DEFAULT_CACHE_ROOT
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        return root
    return root


def _cache_name(model_key: str, template: str) -> str:
    digest = hashlib.sha256(template.encode("utf-8")).hexdigest()[:16]
    stem = _SAFE_NAME.sub("_", model_key).strip("_") or "model"
    return f"{stem}.{digest}.jinja"


def materialize_template(model_key: str, template: str, root: Path | None = None) -> Path:
    """Write the template into the cache and return its path.

    The file name carries a content hash, so a changed upstream template
    produces a new file instead of silently reusing a stale one.
    """
    directory = cache_root() if root is None else root
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    target = directory / _cache_name(model_key, template)
    try:
        if not target.is_file() or target.read_text(encoding="utf-8") != template:
            target.write_text(template, encoding="utf-8")
    except OSError:
        return target
    return target


def template_from_registry_entry(
    entry: Mapping[str, object] | None,
    model_key: str,
    read_gguf_template: object = None,
) -> Path | None:
    """Return the cached template path for a Registry entry.

    ``read_gguf_template`` is a callable that maps a GGUF path to its
    template text. It is injected to keep this module free of the heavier
    GGUF reader import.
    """
    if not isinstance(entry, Mapping):
        return None
    local = entry.get("local")
    if not isinstance(local, Mapping):
        return None
    model_path = local.get("model_path")
    if not isinstance(model_path, str) or not model_path.strip():
        return None
    reader = read_gguf_template
    if not callable(reader):
        return None
    try:
        template = reader(model_path)  # type: ignore[operator]
    except Exception:
        return None
    if not isinstance(template, str) or not template.strip():
        return None
    return materialize_template(model_key, template)
