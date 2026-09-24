"""Single, fail-closed resolver for local GGUF artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from benchmark_config import guess_quant_from_filename, is_support_file
from model_identity import normalize_match_identity
from model_paths import configured_gguf_roots
from quantization import normalize_quant

ResolutionStatus = Literal["unique", "ambiguous", "not_found"]


@dataclass(frozen=True)
class ArtifactResolution:
    """Resolution result with all candidates retained for diagnostics."""

    requested: str
    status: ResolutionStatus
    path: Path | None = None
    candidates: tuple[Path, ...] = ()
    evidence: str = ""

    @property
    def is_unique(self) -> bool:
        """Return whether a runtime-safe single artifact was found."""
        return self.status == "unique" and self.path is not None


class ArtifactResolver:
    """Discover and resolve GGUF files using one deterministic rule set."""

    def __init__(self, models_root: str | Path | None = None) -> None:
        self.model_roots = configured_gguf_roots(models_root)

    @staticmethod
    def _canonical_path(path: Path) -> str:
        try:
            return str(path.resolve(strict=True)).casefold()
        except OSError:
            return str(path.absolute()).casefold()

    def files(self, *, include_support: bool = False) -> list[tuple[int, Path]]:
        """Return deduplicated GGUF files in configured root priority order."""
        seen: set[str] = set()
        result: list[tuple[int, Path]] = []
        for root_index, root in enumerate(self.model_roots):
            if not root.is_dir():
                continue
            try:
                paths = sorted(root.rglob("*.gguf"), key=lambda item: str(item).casefold())
            except OSError:
                continue
            for path in paths:
                if not path.is_file() or (not include_support and is_support_file(path)):
                    continue
                identity = self._canonical_path(path)
                if identity in seen:
                    continue
                seen.add(identity)
                result.append((root_index, path))
        return result

    @staticmethod
    def _quant(path: Path) -> str:
        return cast("str", normalize_quant(guess_quant_from_filename(path.name)))

    @staticmethod
    def _normalized_name(path: Path) -> str:
        return cast("str", normalize_match_identity(path.stem))

    @staticmethod
    def _requested_quant(requested: str) -> str | None:
        if "@" not in requested:
            return None
        quant = requested.rsplit("@", 1)[1].strip()
        return normalize_quant(quant) if quant and quant != "?" else None

    def _publisher_matches(self, root_index: int, path: Path, publisher: str) -> bool:
        """Match conventional and Hugging Face cache publisher directories."""
        if not publisher:
            return True
        try:
            parts = path.relative_to(self.model_roots[root_index]).parts
        except ValueError:
            return False
        lowered = [part.casefold() for part in parts]
        publisher = publisher.casefold()
        if lowered and lowered[0] == publisher:
            return True
        if lowered and lowered[0].startswith("models--"):
            return lowered[0].split("--", 2)[1:2] == [publisher]
        if len(lowered) > 1 and lowered[0] == "hub" and lowered[1].startswith("models--"):
            return lowered[1].split("--", 2)[1:2] == [publisher]
        return False

    def _select(self, requested: str, matches: list[tuple[int, Path]], evidence: str) -> ArtifactResolution:
        if not matches:
            return ArtifactResolution(requested, "not_found", evidence=evidence)
        highest_priority = min(root_index for root_index, _path in matches)
        candidates = tuple(path for root_index, path in matches if root_index == highest_priority)
        if len(candidates) == 1:
            return ArtifactResolution(requested, "unique", candidates[0], candidates, evidence)
        return ArtifactResolution(requested, "ambiguous", candidates=candidates, evidence=evidence)

    def resolve(
        self,
        requested: str,
        *,
        source_paths: tuple[tuple[str, ...], ...] = (),
    ) -> ArtifactResolution:
        """Resolve an identity; ambiguity is returned instead of first-wins."""
        if not requested:
            return ArtifactResolution(requested, "not_found", evidence="empty-request")
        files = self.files()
        if source_paths:
            scoped_files: list[tuple[int, Path]] = []
            for root_index, path in files:
                root = self.model_roots[root_index]
                if any(
                    path.is_relative_to(root.joinpath(*source))
                    for source in source_paths
                ):
                    scoped_files.append((root_index, path))
            files = scoped_files
        requested_quant = self._requested_quant(requested)
        requested_norm = normalize_match_identity(requested)
        requested_base = requested_norm.split("@", 1)[0]
        requested_publisher = ""
        if "/" in requested and not Path(requested).is_absolute():
            requested_publisher = requested.split("/", 1)[0].strip()
        match_files = files
        if requested_publisher and not source_paths:
            publisher_files = [
                item
                for item in files
                if self._publisher_matches(item[0], item[1], requested_publisher)
            ]
            # A known alias can legitimately live under another publisher's
            # local Hub directory.  Use that fallback only when the requested
            # publisher has no local directory at all; uniqueness still wins.
            if publisher_files:
                match_files = publisher_files

        explicit_matches: list[tuple[int, Path]] = []
        for root_index, root in enumerate(self.model_roots):
            candidate_roots = [root]
            for source in source_paths:
                candidate_roots.append(root.joinpath(*source))
            for candidate_root in candidate_roots:
                candidate = candidate_root / requested
                if candidate.is_file() and candidate.suffix.casefold() == ".gguf":
                    explicit_matches.append((root_index, candidate))
        selected = self._select(requested, explicit_matches, "explicit-path")
        if selected.status != "not_found":
            return selected

        exact_name: list[tuple[int, Path]] = []
        for root_index, path in match_files:
            path_norm = self._normalized_name(path)
            if path_norm != requested_norm and path_norm != requested_base:
                continue
            if requested_quant is not None and self._quant(path) != requested_quant:
                continue
            exact_name.append((root_index, path))
        selected = self._select(requested, exact_name, "normalized-name")
        if selected.status != "not_found":
            return selected

        # A filename may omit the publisher while retaining the model and
        # quant.  Accept this only when the normalized base/quant combination
        # remains unique in the configured root priority tier.
        suffix_matches: list[tuple[int, Path]] = []
        for root_index, path in match_files:
            path_norm = self._normalized_name(path)
            if requested_base and requested_base in path_norm:
                if requested_quant is None or self._quant(path) == requested_quant:
                    suffix_matches.append((root_index, path))
        return self._select(requested, suffix_matches, "unique-name-substring")


def resolve_artifact(
    requested: str,
    *,
    models_root: str | Path | None = None,
    source_paths: tuple[tuple[str, ...], ...] = (),
) -> ArtifactResolution:
    """Convenience boundary for callers that need one resolution."""
    return ArtifactResolver(models_root).resolve(requested, source_paths=source_paths)
