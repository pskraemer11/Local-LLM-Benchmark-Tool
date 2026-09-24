"""Shared per-run inventory contracts for Registry synchronization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class IdentityLink:
    """Evidence linking one canonical identity to boundary observations."""

    registry_key: str
    lms_model_keys: tuple[str, ...] = ()
    config_paths: tuple[Path, ...] = ()
    artifact_paths: tuple[Path, ...] = ()
    hf_urls: tuple[str, ...] = ()


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
