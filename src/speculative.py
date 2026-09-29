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


def registry_speculative_policy(entry: Mapping[str, Any]) -> str:
    """Choose explicit Registry ownership or the legacy LMS-derived profile."""
    policy = entry.get("speculative_policy", "lmstudio")
    if not isinstance(policy, str) or policy not in {"lmstudio", "registry", "disabled"}:
        raise ValueError(f"unsupported Registry speculative_policy: {policy!r}")
    return str(policy)


def _reference(profile: Mapping[str, Any]) -> str:
    for field in ("draft_model_reference", "draft_gguf"):
        value = profile.get(field)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _draft_method_from_reference(reference: str) -> str:
    """Infer the explicit helper algorithm when legacy data stores only its path."""
    normalized = reference.casefold()
    if "dspark" in normalized:
        return "dspark"
    if "dflash" in normalized:
        return "dflash"
    return "simple"


def normalize_speculative_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize legacy and current speculative profiles.

    ``type: mtp`` describes MTP capability of the main model.  ``mode`` says
    whether the MTP layers are integrated in that GGUF or supplied by a
    non-standalone companion. ``type: draft`` describes a separate proposal
    artifact: ``simple`` is an independently runnable LLM; DFlash and DSpark
    are helpers trained for a particular target. It is never an MTP type.
    """
    raw_type = str(profile.get("type") or "").strip().casefold()
    reference = _reference(profile)
    mode = str(profile.get("mode") or "").strip().casefold()
    method = str(profile.get("method") or "").strip().casefold()

    if raw_type in {"mtp", "draft-mtp"}:
        normalized: dict[str, Any] = {
            "type": "mtp",
            "mode": mode
            if mode and mode not in {"integrated", "separate"}
            else ("separate" if mode == "separate" or reference else "integrated"),
        }
    elif raw_type in {"draft", "draft-dflash", "draft-dspark", "draft-simple"}:
        if not method and raw_type.startswith("draft-"):
            method = raw_type.removeprefix("draft-")
        if method in {"drafter", "draft", "standard"}:
            method = "simple"
        if not method:
            method = _draft_method_from_reference(reference)
        normalized = {"type": "draft", "method": method}
    else:
        return {}

    if reference:
        normalized["draft_model_reference"] = reference
    pairing = profile.get("pairing")
    if isinstance(pairing, dict):
        normalized["pairing"] = dict(pairing)
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
            "method": _draft_method_from_reference(reference),
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


def lms_speculative_values(entry: Mapping[str, Any]) -> dict[str, Any] | None:
    """Derive saved LMS load fields for an explicitly Registry-owned policy.

    These are concrete JSON-config values, not unsupported REST load inputs.
    Callers must validate specialized companion evidence before enabling them.
    """
    policy = registry_speculative_policy(entry)
    if policy == "lmstudio":
        return None
    values: dict[str, Any] = dict.fromkeys((
        "draft_mtp", "draft_simple", "draft_dflash_sidecar",
        "draft_dspark_sidecar", "draft_mtp_sidecar",
    ), False)
    values["draft_model_reference"] = ""
    if policy == "disabled":
        return values
    local = entry.get("local")
    local_llama = local.get("llama_cpp") if isinstance(local, dict) else None
    raw_profile = local_llama.get("speculative") if isinstance(local_llama, dict) else None
    profile = normalize_speculative_profile(raw_profile) if isinstance(raw_profile, dict) else {}
    if not profile:
        raise ValueError("Registry-owned speculative policy requires a valid profile")
    if profile["type"] == "mtp":
        field = "draft_mtp_sidecar" if profile["mode"] == "separate" else "draft_mtp"
    else:
        method = profile["method"]
        if method not in {"simple", "dspark", "dflash"}:
            raise ValueError(f"unsupported Registry draft method: {method!r}")
        field = "draft_simple" if method == "simple" else f"draft_{method}_sidecar"
    values[field] = True
    role = companion_role(profile)
    if role:
        companions = local.get("companions") if isinstance(local, dict) else None
        helper = companions.get(role) if isinstance(companions, dict) else None
        if role == "draft" and not helper and isinstance(companions, dict):
            helper = companions.get("drafter")
        if not isinstance(helper, str) or not helper.strip():
            raise ValueError(f"Registry-owned speculative profile requires {role} companion")
        values["draft_model_reference"] = helper
    if isinstance(raw_profile, dict):
        for field in ("draft_n_max", "draft_n_min", "draft_p_min"):
            if field in raw_profile:
                values[field] = raw_profile[field]
    return values


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
