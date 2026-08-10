"""Feld-Ownership-Tabelle: Wer ist fuer welches Modell-Feld zustaendig?

SSOT-Design (Fix 2026-08-09): Jedes Feld hat genau eine kanonische Quelle
und eine Sync-Richtung. Die Tabelle liegt im Code (bewusst keine externe
YAML, damit Aenderungen an Regeln immer mit Code-Tests einhergehen).

Quellen:
  - "gguf":     GGUF-Header (unveraenderlich, architektur-bedingt)
  - "config":   LM-Studio-Config-JSON (GUI ist die Quelle)
  - "hub":      LM-Studio-Hub model.yaml (metadataOverrides)
  - "lms":      lms ls --json (Dateigroessen)
  - "registry": model_registry.yaml (menschliche Entscheidung)

auto_fix=True nur bei unveraenderlichen Quellen (gguf/lms): Abweichungen
werden automatisch aus der Quelle in die Registry geschrieben. Alle anderen
Abweichungen werden gemeldet und zur Entscheidung vorgelegt (Nutzer-Fix
2026-08-09: "Aus Config: melden und zur Entscheidung vorlegen").
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldRule:
    source: str                       # gguf | config | hub | lms | registry
    target: str                       # registry | config
    auto_fix: bool = False            # nur gguf/lms erlaubt (unveraenderlich)
    checks: tuple[str, ...] = ()      # zusaetzliche Querverweise
    description: str = ""

    def __post_init__(self) -> None:
        if self.auto_fix and self.source not in ("gguf", "lms"):
            raise ValueError(f"auto_fix nur fuer gguf/lms-Quellen, nicht {self.source}")


FIELD_OWNERSHIP: dict[str, FieldRule] = {
    # ── GGUF-Header (unveraenderlich) → Registry, Auto-Fix ─────────
    "n_layers": FieldRule(
        "gguf", "registry", True, description="block_count aus GGUF-Header"
    ),
    "hidden_dim": FieldRule(
        "gguf", "registry", True, description="embedding_length aus GGUF-Header"
    ),
    "max_context_length": FieldRule(
        "gguf", "registry", True, checks=("hub_crosscheck",),
        description="context_length aus GGUF-Header, Hub-Kreuzcheck",
    ),
    "arch": FieldRule(
        "gguf", "registry", True, description="moe/mtp/dense aus GGUF expert_count",
    ),
    # ── lms ls --json (unveraenderlich) → Registry, Auto-Fix ────────
    "file_size_bytes": FieldRule(
        "lms", "registry", True, description="Dateigroesse aus lms ls"
    ),
    # ── GGUF-Header, aber Interpretationsspielraum → nur melden ────
    "reasoning": FieldRule(
        "gguf", "registry", False, checks=("arch_map", "hub"),
        description="aus GGUF chat_template + Familien-Map; Dual-Mode-Interpretation (nicht rein architektur-bedingt)",
    ),
    # ── Config-JSON (GUI-Quelle) → Registry, nur melden ─────────────
    "num_parallel": FieldRule(
        "config", "registry", False, description="Config ist die Quelle (GUI)"
    ),
    "useUnifiedKvCache": FieldRule(
        "config", "registry", False, description="Config ist die Quelle (GUI)"
    ),
    "offload": FieldRule(
        "config", "registry", False, description="Config ist die Quelle (GUI)"
    ),
    "context_length": FieldRule(
        "config", "registry", False, checks=("gguf_max",),
        description="Config-Wert; darf nativer GGUF-Grenze nicht uebersteigen",
    ),
    # ── Registry (menschliche Entscheidung) → Config, nur Pruefung ─
    "blueprint": FieldRule(
        "registry", "config", False, description="Blueprint-Auswahl (menschlich)"
    ),
    "template": FieldRule(
        "registry", "config", False, checks=("template_file",),
        description="Jinja-Vorlage-Referenz (menschlich)"
    ),
    "truncation": FieldRule(
        "registry", "config", False, description="Truncation-Verhalten (menschlich)"
    ),
    # ── Registry (menschliche Entscheidung), nur Pflichtfeld-Pruefung
    "capabilities": FieldRule("registry", "registry", False),
    "publisher": FieldRule("registry", "registry", False),
    "k_cache": FieldRule("registry", "registry", False),
    "v_cache": FieldRule("registry", "registry", False),
    "quants": FieldRule("registry", "registry", False),
    "hf_url": FieldRule("registry", "registry", False),
    "pub_url": FieldRule("registry", "registry", False),
    "notes": FieldRule("registry", "registry", False),
    "display_name": FieldRule("registry", "registry", False),
    "experts": FieldRule("registry", "registry", False),
    "custom_template": FieldRule("registry", "registry", False),
}


def resolve(field: str) -> FieldRule | None:
    """Regel zu einem Feldnamen (None fuer unbekannte Felder)."""
    return FIELD_OWNERSHIP.get(field)


def auto_fix_fields() -> tuple[str, ...]:
    """Alle Felder mit auto_fix=True (aus gguf/lms, unveraenderlich)."""
    return tuple(f for f, r in FIELD_OWNERSHIP.items() if r.auto_fix)


def report_only_fields() -> tuple[str, ...]:
    """Alle Felder, deren Abweichungen gemeldet werden (kein Auto-Fix)."""
    return tuple(f for f, r in FIELD_OWNERSHIP.items() if not r.auto_fix)


def field_sources() -> dict[str, set[str]]:
    """Quellen-Lookup fuer Reports: quelle -> felder."""
    out: dict[str, set[str]] = {}
    for f, r in FIELD_OWNERSHIP.items():
        out.setdefault(r.source, set()).add(f)
    return out


@dataclass
class Drift:
    """Eine erkannte Abweichung zwischen Quelle und Registry."""

    field: str
    registry_value: object
    source_value: object
    rule: FieldRule
    context: str = ""

    @property
    def auto_fixable(self) -> bool:
        return self.rule.auto_fix

    def report_line(self) -> str:
        action = "AUTO-FIX" if self.auto_fixable else "MELDEN"
        return (
            f"  [{action}] {self.field}: Registry={self.registry_value!r} "
            f"vs Quelle({self.rule.source})={self.source_value!r}"
            + (f" ({self.context})" if self.context else "")
        )
