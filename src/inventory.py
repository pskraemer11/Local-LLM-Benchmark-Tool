"""Shared per-run inventory contracts for Registry synchronization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from model_identity import ArtifactIdentityEvidence


@dataclass(frozen=True)
class RuntimeBinding:
    """Runtime data joined to one exact local model artifact.

    Publisher/model keys and LMS-reported paths are join evidence used while
    building the inventory. They are deliberately not repeated here: the
    Registry identity and the concrete artifact evidence already carry the
    authoritative identity and GGUF path.
    """

    config_path: Path | None = None
    sampling: tuple[tuple[str, Any], ...] = ()
    context_length: int | float | None = None
    use_unified_kv: bool | None = None
    num_parallel: int | None = None
    offload: float | None = None
    k_cache: str | None = None
    v_cache: str | None = None
    num_experts: int | None = None
    speculative: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True)
class IdentityLink:
    """Evidence linking one identity to its local and LMS boundary records.

    Absolute paths are retained here as the verified join result.  The local
    Registry may materialize the same paths under ``local`` because this
    Registry is an effective machine-local catalog; the link table remains
    the pre-persistence proof that the binding was unique.
    """

    registry_key: str
    runtime_bindings: tuple[RuntimeBinding, ...] = ()
    artifact_evidence: tuple[ArtifactIdentityEvidence, ...] = ()
    hf_urls: tuple[str, ...] = ()

    @property
    def config_paths(self) -> tuple[Path, ...]:
        """Return only config paths that are uniquely joined to the artifact."""
        return tuple(
            record.config_path
            for record in self.runtime_bindings
            if record.config_path is not None
        )

    @property
    def artifact_paths(self) -> tuple[Path, ...]:
        """Compatibility projection of the immutable artifact evidence."""
        return tuple(evidence.path for evidence in self.artifact_evidence)


@dataclass
class InventorySnapshot:
    """One consistent read-only snapshot shared by a synchronization run."""

    registry: dict[str, Any]
    raw_lms_models: list[dict[str, Any]]
    lms_models: list[dict[str, Any]]
    configs: list[dict[str, Any]]
    gguf_candidates: list[Any]
    gguf_candidates_loaded: bool = False
    gguf_header_cache: dict[
        tuple[str, int, int],
        tuple[tuple[int | None, int | None, bool | None, int | None, int | None], str | None],
    ] = field(default_factory=dict)
    identity_links: dict[str, IdentityLink] = field(default_factory=dict)

    def with_identity_link(self, link: IdentityLink) -> None:
        """Record a link without mutating any source artifact."""
        self.identity_links[link.registry_key] = link
