"""Read GGUF metadata and tensor descriptions without mapping tensor weights."""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from quantization import extract_quant_from_text, quant_from_gguf_evidence

if TYPE_CHECKING:
    from typing import BinaryIO

_FORMATS = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i", 6: "f", 7: "?", 10: "Q", 11: "q", 12: "d"}
_MAX_ITEMS = 1_000_000
_MAX_STRING = 16 * 1024 * 1024
_MAX_HEADER = 256 * 1024 * 1024


@dataclass(frozen=True)
class GgufArrayEvidence:
    """Content evidence for an array too large to retain in memory."""

    count: int
    sha256: str
    element_type: int


@dataclass(frozen=True)
class GgufEvidence:
    metadata: dict[str, Any]
    tensors: dict[str, tuple[int, ...]]
    header_sha256: str
    fingerprint: str
    tensor_types: dict[str, int] = field(default_factory=dict)


class _HeaderReader:
    def __init__(self, handle: BinaryIO) -> None:
        self.handle = handle
        self.digest = hashlib.sha256()
        self.bytes_read = 0

    def read(self, count: int) -> bytes:
        if count < 0 or self.bytes_read + count > _MAX_HEADER:
            raise ValueError("GGUF header exceeds supported bounds")
        raw = self.handle.read(count)
        if len(raw) != count:
            raise ValueError("truncated GGUF header")
        self.bytes_read += count
        self.digest.update(raw)
        return raw

    def number(self, format_code: str) -> Any:
        return struct.unpack("<" + format_code, self.read(struct.calcsize("<" + format_code)))[0]

    def string(self) -> str:
        count = self.number("Q")
        if count > _MAX_STRING:
            raise ValueError("GGUF string exceeds supported bounds")
        return self.read(count).decode("utf-8", errors="strict")

    def value(self, value_type: int, *, depth: int = 0) -> Any:
        if depth > 2:
            raise ValueError("nested GGUF arrays exceed supported bounds")
        if value_type == 8:
            return self.string()
        if value_type in _FORMATS:
            return self.number(_FORMATS[value_type])
        if value_type != 9:
            raise ValueError(f"unsupported GGUF metadata type: {value_type}")
        element_type, count = self.number("I"), self.number("Q")
        if count > _MAX_ITEMS:
            raise ValueError("GGUF array exceeds supported bounds")
        if count <= 4096:
            return tuple(self.value(element_type, depth=depth + 1) for _ in range(count))
        digest = hashlib.sha256(struct.pack("<IQ", element_type, count))
        for _ in range(count):
            if element_type == 8:
                size = self.number("Q")
                if size > _MAX_STRING:
                    raise ValueError("GGUF string exceeds supported bounds")
                digest.update(struct.pack("<Q", size))
                digest.update(self.read(size))
            elif element_type in _FORMATS:
                digest.update(self.read(struct.calcsize("<" + _FORMATS[element_type])))
            else:
                raise ValueError("unsupported large GGUF array type")
        return GgufArrayEvidence(count, digest.hexdigest(), element_type)


@lru_cache(maxsize=256)
def _read_cached(path: str, size: int, mtime_ns: int) -> GgufEvidence:
    with Path(path).open("rb") as handle:
        reader = _HeaderReader(handle)
        if reader.read(4) != b"GGUF":
            raise ValueError("file does not contain a GGUF header")
        version, tensor_count, metadata_count = reader.number("I"), reader.number("Q"), reader.number("Q")
        if version not in {2, 3}:
            raise ValueError(f"unsupported GGUF version: {version}")
        if tensor_count > _MAX_ITEMS or metadata_count > 100_000:
            raise ValueError("GGUF item count exceeds supported bounds")
        metadata: dict[str, Any] = {}
        for _ in range(metadata_count):
            key = reader.string()
            if key in metadata:
                raise ValueError(f"duplicate GGUF metadata key: {key}")
            metadata[key] = reader.value(reader.number("I"))
        tensors: dict[str, tuple[int, ...]] = {}
        tensor_types: dict[str, int] = {}
        for _ in range(tensor_count):
            name, dimensions = reader.string(), reader.number("I")
            if dimensions < 1 or dimensions > 8 or name in tensors:
                raise ValueError("invalid GGUF tensor description")
            tensors[name] = tuple(reader.number("Q") for _ in range(dimensions))
            tensor_types[name] = int(reader.number("I"))
            reader.number("Q")  # tensor offset; never read the weights
        header_sha256 = reader.digest.hexdigest()
        fingerprint = hashlib.sha256(f"{header_sha256}:{size}:{mtime_ns}".encode("ascii")).hexdigest()
        return GgufEvidence(metadata, tensors, header_sha256, fingerprint, tensor_types)


def read_gguf_evidence(path: str | Path) -> GgufEvidence:
    """Return bounded header evidence, invalidated when the local artifact changes."""
    resolved = Path(path).resolve(strict=True)
    stat = resolved.stat()
    evidence = _read_cached(str(resolved), stat.st_size, stat.st_mtime_ns)
    after = resolved.stat()
    if (after.st_size, after.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
        raise ValueError("GGUF artifact changed while its header was read")
    return GgufEvidence(
        dict(evidence.metadata),
        dict(evidence.tensors),
        evidence.header_sha256,
        evidence.fingerprint,
        dict(evidence.tensor_types),
    )


def resolve_artifact_quant(path: str | Path, *, publisher: str | None) -> str | None:
    """Resolve precise filename quant or bounded, publisher-scoped GGUF proof.

    Supply the publisher from path-derived artifact evidence, never from a
    requested Registry alias. Unreadable or unsupported naked files stay
    unresolved; a known filename quant never triggers a header override.
    """
    artifact = Path(path)
    named_quant = extract_quant_from_text(artifact.name)
    if isinstance(named_quant, str):
        return named_quant
    if str(publisher or "").strip().casefold() != "llmsforall":
        return None
    try:
        evidence = read_gguf_evidence(artifact)
    except (OSError, ValueError, struct.error):
        return None
    resolved_quant = quant_from_gguf_evidence(
        artifact.name,
        publisher=publisher,
        file_type=evidence.metadata.get("general.file_type"),
        tensor_types=evidence.tensor_types,
    )
    return resolved_quant if isinstance(resolved_quant, str) else None


def array_digest(value: Any) -> str | None:
    """Compare complete GGUF token arrays, including synthetic small fixtures."""
    if isinstance(value, GgufArrayEvidence) and value.element_type == 8:
        return value.sha256
    if isinstance(value, tuple) and value:
        if all(isinstance(item, str) for item in value):
            digest = hashlib.sha256(struct.pack("<IQ", 8, len(value)))
            for item in value:
                encoded = item.encode("utf-8")
                digest.update(struct.pack("<Q", len(encoded)))
                digest.update(encoded)
            return digest.hexdigest()
    return None
