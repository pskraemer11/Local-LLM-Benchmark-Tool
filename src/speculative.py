"""Shared classification for MTP and standalone draft-model bundles.

The Registry uses provider-neutral terms.  llama.cpp has its own speculative
decoding labels (for example ``draft-mtp`` and ``draft-dflash``); those labels
are emitted only at the llama.cpp adapter boundary and must not become model
or artifact types in the Registry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping


def _enabled(value: Any) -> bool:
    """Interpret an LM Studio boolean-like field without treating ``"false"`` as true."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() not in {"", "0", "false", "no", "off"}
    return value not in (None, 0, "")


def _reference(profile: Mapping[str, Any]) -> str:
    for field in ("draft_model_reference", "draft_gguf"):
        value = profile.get(field)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def normalize_speculative_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize legacy and current speculative profiles.

    ``type: mtp`` describes MTP capability of the main model.  ``mode`` says
    whether the MTP layers are integrated in that GGUF or supplied by a
    non-standalone companion.  ``type: draft`` describes a separate,
    independently runnable draft LLM and is never an MTP classification.
    """
    raw_type = str(profile.get("type") or "").strip().casefold()
    reference = _reference(profile)
    mode = str(profile.get("mode") or "").strip().casefold()
    method = str(profile.get("method") or "").strip().casefold()

    if raw_type in {"mtp", "draft-mtp"}:
        normalized: dict[str, Any] = {
            "type": "mtp",
            "mode": "separate" if mode == "separate" or reference else "integrated",
        }
    elif raw_type in {"draft", "draft-dflash", "draft-dspark", "draft-simple"}:
        if not method and raw_type.startswith("draft-"):
            method = raw_type.removeprefix("draft-")
        if method not in {"dflash", "dspark", "simple"}:
            method = "dflash" if "dflash" in reference.casefold() else "simple"
        normalized = {"type": "draft", "method": method}
    else:
        return {}

    if reference:
        normalized["draft_model_reference"] = reference
    return normalized


def classify_lms_speculative_values(values: Mapping[str, Any]) -> dict[str, Any]:
    """Translate LM Studio speculative flags into the Registry vocabulary."""
    if _enabled(values.get("draft_mtp_sidecar")):
        profile: dict[str, Any] = {"type": "mtp", "mode": "separate"}
    elif _enabled(values.get("draft_mtp")):
        profile = {"type": "mtp", "mode": "integrated"}
    elif _enabled(values.get("draft_dflash_sidecar")):
        profile = {"type": "draft", "method": "dflash"}
    elif _enabled(values.get("draft_dspark_sidecar")):
        profile = {"type": "draft", "method": "dspark"}
    elif _enabled(values.get("draft_simple")):
        profile = {"type": "draft", "method": "simple"}
    elif values.get("draft_model_reference") not in (None, ""):
        reference = str(values["draft_model_reference"]).casefold()
        profile = {
            "type": "draft",
            "method": "dflash" if "dflash" in reference else "simple",
        }
    else:
        profile = {}

    for field in (
        "draft_model_reference",
        "draft_n_max",
        "draft_n_min",
        "draft_p_min",
    ):
        if field in values and values[field] not in (None, ""):
            profile[field] = values[field]
    return profile


def companion_role(profile: Mapping[str, Any]) -> str | None:
    """Return the non-main artifact role, if this profile requires one."""
    normalized = normalize_speculative_profile(profile)
    if normalized.get("type") == "mtp" and normalized.get("mode") == "separate":
        return "mtp"
    if normalized.get("type") == "draft":
        return "draft"
    return None


def llama_cpp_spec_type(profile: Mapping[str, Any]) -> str | None:
    """Map the normalized profile to llama.cpp's current CLI vocabulary."""
    normalized = normalize_speculative_profile(profile)
    if normalized.get("type") == "mtp":
        return "draft-mtp"
    if normalized.get("type") == "draft":
        method = normalized.get("method")
        if method in {"dflash", "dspark", "simple"}:
            return f"draft-{method}"
    return None
