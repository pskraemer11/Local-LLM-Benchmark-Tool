"""Shared validation for a main GGUF and its local runtime companions."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from quantization import extract_quant_from_text, normalize_quant
from speculative import companion_role, normalize_speculative_profile

_QWEN_VERSION = re.compile(r"(?<![a-z0-9])qwen[-_ ]?(\d+(?:\.\d+)+)", re.IGNORECASE)
_PARAMETER_SIZE = re.compile(r"(?<![a-z0-9])(\d+(?:\.\d+)?)\s*b(?![a-z0-9])", re.IGNORECASE)


def _normalize_model_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def config_matches_gguf(
    config_path: str | Path,
    model_path: str | Path,
    *,
    scope: str = "gguf",
) -> bool:
    """Whether an LMS JSON names a concrete GGUF or an explicit model scope.

    File-specific ``*.gguf.json`` configs are the automatic/default form.
    A logical ``model.json`` is accepted only when the caller supplies the
    explicit ``scope="model"`` declaration from a machine-local Registry.
    """
    config = Path(config_path)
    model = Path(model_path)
    if config.suffix.casefold() != ".json" or model.suffix.casefold() != ".gguf":
        return False
    if scope == "model":
        folder_name = re.sub(r"[-_. ]gguf$", "", model.parent.name, flags=re.IGNORECASE)
        folder_name = re.sub(
            r"[-_. ](?:iq\d+[a-z0-9_]*|q\d+[a-z0-9_]*|mxfp4|nvfp4|fp16|f16)$",
            "",
            folder_name,
            flags=re.IGNORECASE,
        )
        return bool(folder_name) and _normalize_model_name(config.stem) == _normalize_model_name(folder_name)
    if scope != "gguf":
        return False
    if config.stem.casefold() != model.name.casefold():
        return False
    return tuple(part.casefold() for part in config.parent.parts[-2:]) == tuple(
        part.casefold() for part in model.parent.parts[-2:]
    )


def validate_config_gguf_pair(
    model_path: str | Path,
    config_path: str | Path,
    *,
    scope: str = "gguf",
) -> tuple[str, ...]:
    """Return errors when a declared GGUF/JSON pair is stale or mismatched."""
    model = Path(model_path)
    config = Path(config_path)
    errors: list[str] = []
    if not model.is_file():
        errors.append(f"main GGUF does not exist: {model}")
    elif model.suffix.casefold() != ".gguf":
        errors.append(f"main model is not a .gguf file: {model}")
    elif not _has_gguf_magic(model):
        errors.append(f"main file does not contain a GGUF header: {model}")
    if not config.is_file():
        errors.append(f"LM Studio config does not exist: {config}")
    elif not config_matches_gguf(config, model, scope=scope):
        errors.append(f"LM Studio config does not identify the same GGUF file/package: {config}")

    if model.is_file() and config.is_file():
        model_quant = extract_quant_from_text(model.name)
        config_quant = extract_quant_from_text(config.stem)
        if model_quant and config_quant and normalize_quant(model_quant) != normalize_quant(config_quant):
            errors.append(
                f"GGUF/config quantization mismatch: {normalize_quant(model_quant)} != "
                f"{normalize_quant(config_quant)}"
            )
    return tuple(errors)


def _name_signatures(path: Path) -> tuple[str | None, str | None]:
    value = " ".join(part for part in (path.parent.name, path.name) if part)
    version_match = _QWEN_VERSION.search(value)
    size_match = _PARAMETER_SIZE.search(value)
    version = version_match.group(1).casefold() if version_match else None
    size = size_match.group(1).casefold() if size_match else None
    return version, size


def _is_mtp_sidecar(path: Path) -> bool:
    parts = (path.name, *path.parent.parts)
    return any(
        part.casefold().startswith("mtp-")
        or part.casefold() == "mtp"
        or "-mtp-" in part.casefold()
        or part.casefold().endswith("-mtp")
        for part in parts
    )


def _draft_helper_kind(path: Path) -> str | None:
    name = " ".join((path.name, *path.parent.parts)).casefold()
    if "dspark" in name:
        return "dspark"
    if "dflash" in name:
        return "dflash"
    return None


def _has_gguf_magic(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(4) == b"GGUF"
    except OSError:
        return False


def validate_companion_binding(
    main_path: str | Path | None,
    companion_path: str | Path | None,
    profile: dict[str, Any],
) -> tuple[str, ...]:
    """Validate existence, role, and name-declared compatibility of a bundle.

    File size is deliberately not used to classify artifacts. Where both
    filenames expose a Qwen generation or parameter count, those declarations
    must agree; absent naming evidence is not fabricated into a match.
    """
    normalized = normalize_speculative_profile(profile)
    role = companion_role(normalized)
    if role is None:
        return ()  # integrated MTP and ordinary models have no sidecar
    errors: list[str] = []
    if not main_path:
        return ("main GGUF path is not configured for a companion bundle",)
    if not companion_path:
        return (f"required {role} companion path is not configured",)

    main = Path(main_path)
    companion = Path(companion_path)
    if not main.is_file():
        errors.append(f"main GGUF does not exist: {main}")
    elif main.suffix.casefold() != ".gguf":
        errors.append(f"main model is not a .gguf file: {main}")
    elif not _has_gguf_magic(main):
        errors.append(f"main file does not contain a GGUF header: {main}")
    if not companion.is_file():
        errors.append(f"required {role} companion does not exist: {companion}")
    elif companion.suffix.casefold() != ".gguf":
        errors.append(f"companion is not a .gguf file: {companion}")
    elif not _has_gguf_magic(companion):
        errors.append(f"companion does not contain a GGUF header: {companion}")
    if main.resolve(strict=False) == companion.resolve(strict=False):
        errors.append("main GGUF and companion resolve to the same file")

    if companion.is_file():
        if role == "mtp" and not _is_mtp_sidecar(companion):
            errors.append(f"MTP companion is not identified as a separate MTP sidecar: {companion}")
        if role == "draft":
            method = normalized.get("method")
            helper_kind = _draft_helper_kind(companion)
            if method in {"dflash", "dspark"} and helper_kind is None:
                errors.append(f"{method} profile points to a file not identified as DFlash/DSpark: {companion}")
            elif method == "simple" and helper_kind is not None:
                errors.append(f"simple draft profile points to a {helper_kind} support file: {companion}")
            elif method == "simple" and "draft" not in companion.name.casefold():
                errors.append(f"simple draft profile points to a filename not identified as a draft model: {companion}")

        if main.is_file():
            main_version, main_size = _name_signatures(main)
            helper_version, helper_size = _name_signatures(companion)
            if main_version and helper_version and main_version != helper_version:
                errors.append(
                    f"Qwen generation mismatch: main={main_version}, companion={helper_version}"
                )
            if main_size and helper_size and main_size != helper_size:
                errors.append(
                    f"parameter-size mismatch: main={main_size}B, companion={helper_size}B"
                )
    return tuple(errors)
