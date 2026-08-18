"""Resolve local GGUF files to benchmark model identities.

The resolver deliberately owns only local discovery.  Benchmark eligibility
continues to come from ``benchmark_config`` and canonical model matching from
``model_identity``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from benchmark_config import BLACKLIST, guess_quant_from_filename, is_mtp_drafter, is_support_file
from model_identity import match_registry_key, normalize_for_config

RegistryLoader = Callable[[], dict[str, Any]]


class ModelResolutionError(RuntimeError):
    """Raised when a requested local model cannot be resolved unambiguously."""


@dataclass(frozen=True)
class LocalModelCandidate:
    """One eligible local GGUF model file."""

    model_identifier: str
    path: Path
    quant: str
    registry_key: str | None
    display: str


class LocalModelResolver:
    """Discover and resolve benchmarkable GGUF files below one model root."""

    def __init__(
        self,
        models_root: str | Path | None = None,
        registry_loader: RegistryLoader | None = None,
    ) -> None:
        configured_root = models_root or Path.home() / ".lmstudio" / "models"
        self.models_root = Path(configured_root).expanduser()
        self._registry_loader = registry_loader

    def _registry(self) -> dict[str, Any]:
        if self._registry_loader is None:
            return {}
        data = self._registry_loader()
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _canonical_path(path: Path) -> str:
        try:
            return str(path.resolve(strict=True)).casefold()
        except OSError:
            return str(path.absolute()).casefold()

    @staticmethod
    def _blacklisted(model_name: str) -> bool:
        lowered = model_name.lower()
        return any(keyword in lowered for keyword in BLACKLIST)

    def _model_base_id(self, path: Path) -> str:
        try:
            relative = path.relative_to(self.models_root)
        except ValueError:
            relative = path
        parts = relative.parts
        # Unsloth's local HF cache lives below models/hub, not below the
        # separate LM Studio config tree at .lmstudio/hub.
        if len(parts) >= 4 and parts[0].casefold() == "hub" and parts[1].startswith("models--"):
            repository = parts[1][len("models--") :]
            if "--" in repository and parts[2].casefold() == "snapshots":
                publisher, model_name = repository.split("--", 1)
                return f"{publisher}/{model_name}"
        parents = relative.parts[:-1]
        if parents:
            return "/".join(parents)
        return path.stem

    @staticmethod
    def _match_registry(base_id: str, quant: str, registry: dict[str, Any]) -> str | None:
        keys = list(registry)
        if quant:
            normalized_base = normalize_for_config(base_id)
            normalized_quant = LocalModelResolver._normalize_quant(quant)
            same_base = [
                key for key in keys if normalize_for_config(key) == normalized_base
            ]
            exact_quant = [
                key
                for key in same_base
                if LocalModelResolver._registry_quant(key) == normalized_quant
            ]
            if exact_quant:
                return exact_quant[0]
            mixed = [
                key for key in same_base if LocalModelResolver._registry_quant(key) == "mixed"
            ]
            if mixed:
                return mixed[0]

            # Preserve the established publisher/variant aliases, but never
            # let a flexible base match silently change the local quant.
            probe = f"{base_id}@{quant.lower()}"
            matched = match_registry_key(probe, keys)
            if matched is not None and LocalModelResolver._registry_quant(matched) in {
                normalized_quant,
                "mixed",
            }:
                return matched
            return None
        matched = match_registry_key(base_id, keys)
        if matched is not None:
            return matched
        return None

    @staticmethod
    def _normalize_quant(quant: str) -> str:
        return quant.strip().casefold().replace("-", "_")

    @staticmethod
    def _registry_quant(key: str) -> str:
        if "@" not in key:
            return ""
        return LocalModelResolver._normalize_quant(key.rsplit("@", 1)[1])

    @staticmethod
    def _display_name(model_identifier: str, quant: str, registry_entry: Any) -> str:
        display = registry_entry.get("display_name") if isinstance(registry_entry, dict) else None
        label = str(display or model_identifier)
        if quant and "@" not in label:
            label = f"{label}@{quant.lower()}"
        return label

    def candidates(self, registry_only: bool = False) -> list[LocalModelCandidate]:
        """Return eligible, path-deduplicated local GGUF candidates."""
        if not self.models_root.is_dir():
            return []

        registry = self._registry()
        by_path: dict[str, LocalModelCandidate] = {}
        try:
            paths = sorted(self.models_root.rglob("*.gguf"), key=lambda item: str(item).casefold())
        except OSError:
            return []

        for path in paths:
            if not path.is_file():
                continue
            try:
                size_bytes = path.stat().st_size
            except OSError:
                continue
            model_base_id = self._model_base_id(path)
            if self._blacklisted(model_base_id) or self._blacklisted(path.name):
                continue
            if is_support_file(path):
                continue
            if is_mtp_drafter(path.name, size_bytes):
                continue

            quant = guess_quant_from_filename(path.name)
            registry_key = self._match_registry(model_base_id, quant, registry)
            if registry_only and registry_key is None:
                continue
            model_identifier = registry_key or (
                f"{model_base_id}@{quant.lower()}" if quant else model_base_id
            )
            entry = registry.get(registry_key) if registry_key else None
            candidate = LocalModelCandidate(
                model_identifier=model_identifier,
                path=path,
                quant=quant,
                registry_key=registry_key,
                display=self._display_name(model_identifier, quant, entry),
            )
            canonical_path = self._canonical_path(path)
            existing = by_path.get(canonical_path)
            if existing is None or (existing.registry_key is None and registry_key is not None):
                by_path[canonical_path] = candidate

        return sorted(by_path.values(), key=lambda item: item.display.casefold())

    def resolve(self, model_identifier: str) -> LocalModelCandidate:
        """Resolve one model identifier or raise instead of downloading remotely."""
        matches = [
            candidate
            for candidate in self.candidates(registry_only=False)
            if candidate.model_identifier.casefold() == model_identifier.casefold()
        ]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise ModelResolutionError(
                f"Lokales GGUF nicht gefunden: {model_identifier}. "
                f"Remote-Downloads sind für den Unsloth-Benchmark-Provider deaktiviert."
            )
        paths = ", ".join(str(candidate.path) for candidate in matches)
        raise ModelResolutionError(f"Modell nicht eindeutig: {model_identifier} ({paths})")

    @staticmethod
    def as_model_info(candidate: LocalModelCandidate, loaded: bool = False) -> dict[str, Any]:
        """Convert a local candidate to the provider-neutral model shape."""
        return {
            "key": candidate.model_identifier,
            "model_identifier": candidate.model_identifier,
            "display": candidate.display,
            "variant": candidate.model_identifier,
            "quant": candidate.quant,
            "variants": [],
            "identifier": candidate.model_identifier,
            "params": "",
            "publisher": candidate.model_identifier.split("/", 1)[0]
            if "/" in candidate.model_identifier
            else "",
            "registry_key": candidate.registry_key,
            "model_path": str(candidate.path),
            "loaded": loaded,
        }
