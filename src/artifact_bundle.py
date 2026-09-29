"""Shared validation for a main GGUF and its local runtime companions."""

from __future__ import annotations

import hashlib
import json
import re
import struct
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from gguf_evidence import GgufEvidence, array_digest, read_gguf_evidence
from quantization import extract_quant_from_text, normalize_quant
from speculative import companion_role, normalize_speculative_profile


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
                f"GGUF/config quantization mismatch: {normalize_quant(model_quant)} != {normalize_quant(config_quant)}"
            )
    return tuple(errors)


def _helper_kind(evidence: GgufEvidence) -> str | None:
    architecture = str(evidence.metadata.get("general.architecture") or "").casefold()
    markov = {"markov_w1.weight", "markov_w2.weight"}.intersection(evidence.tensors)
    if architecture == "dflash":
        return "dspark" if len(markov) == 2 else "invalid-dspark" if markov else "dflash"
    nextn = any("nextn" in name for name in evidence.tensors)
    nextn_layers = evidence.metadata.get(f"{architecture}.nextn_predict_layers")
    block_count = evidence.metadata.get(f"{architecture}.block_count")
    if nextn and (
        architecture.endswith("-assistant")
        or str(evidence.metadata.get("general.type") or "").casefold() == "mtp"
        or (isinstance(nextn_layers, int) and nextn_layers > 0 and nextn_layers == block_count)
    ):
        return "mtp"
    return None


def _tokenizer_errors(main: GgufEvidence, helper: GgufEvidence, *, ordinary_draft: bool) -> list[str]:
    errors: list[str] = []
    main_tokens = array_digest(main.metadata.get("tokenizer.ggml.tokens"))
    helper_tokens = array_digest(helper.metadata.get("tokenizer.ggml.tokens"))
    if not main_tokens or not helper_tokens:
        errors.append("tokenizer compatibility evidence is missing: complete token tables are required")
    elif main_tokens != helper_tokens:
        errors.append("tokenizer token-table mismatch between main model and companion")
    # Target-bound helpers consume target token IDs and hidden states directly.
    # Their own BOS/EOS/padding defaults do not tokenize the benchmark prompt.
    fields: tuple[str, ...] = ("model",)
    if ordinary_draft:
        fields += ("pre", "bos_token_id", "eos_token_id", "add_bos_token", "add_eos_token")
    for field in fields:
        key = f"tokenizer.ggml.{field}"
        left, right = main.metadata.get(key), helper.metadata.get(key)
        if field == "model" and (left is None or right is None):
            errors.append("tokenizer model evidence is missing")
        elif left != right:
            errors.append(f"tokenizer {field} mismatch: main={left}, companion={right}")
    return errors


def _repo_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    parts = parsed.path.strip("/").split("/")
    if parsed.scheme == "https" and parsed.hostname == "huggingface.co" and len(parts) == 2:
        return "/".join(parts).casefold()
    return None


def _header_target_matches(main: GgufEvidence, helper: GgufEvidence) -> bool:
    """Use declared source identity; sharing an ancestor is insufficient for a finetune."""
    main_repositories = {_repo_id(main.metadata.get("general.repo_url"))}
    if not main.metadata.get("general.finetune") and main.metadata.get("general.base_model.0.relation") == "quantized":
        main_repositories.add(_repo_id(main.metadata.get("general.base_model.0.repo_url")))
    main_repositories.discard(None)
    explicit_target = _repo_id(helper.metadata.get("speculative.target.repo_url"))
    declared_target = explicit_target or _repo_id(helper.metadata.get("general.base_model.0.repo_url"))
    return declared_target is not None and declared_target in main_repositories


def _pairing_evidence_matches(
    profile: dict[str, Any],
    main: Path,
    helper: Path,
    main_evidence: GgufEvidence,
    helper_evidence: GgufEvidence,
    method: str,
) -> bool:
    """Verify a recorded successful pairing tied to the current exact artifacts."""
    pairing = profile.get("pairing")
    if not isinstance(pairing, dict):
        return False
    evidence_path, expected_hash = pairing.get("evidence_path"), pairing.get("evidence_sha256")
    if not isinstance(evidence_path, str) or not isinstance(expected_hash, str):
        return False
    if not re.fullmatch(r"[a-fA-F0-9]{64}", expected_hash):
        return False
    try:
        source = Path(evidence_path)
        if source.stat().st_size > 1024 * 1024:
            return False
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_hash.casefold():
            return False
        record = json.loads(raw)
        if not isinstance(record, dict):
            return False
        validation = record.get("validation")
        if not isinstance(validation, dict) or not (
            validation.get("status") == "passed"
            and validation.get("check") == "speculative_pairing"
            and validation.get("provider") in {"llama_cpp", "lmstudio"}
            and isinstance(validation.get("source"), str)
            and validation["source"].strip()
        ):
            return False
        return (
            record.get("method") == method
            and Path(record["main_path"]).resolve(strict=True) == main.resolve(strict=True)
            and Path(record["companion_path"]).resolve(strict=True) == helper.resolve(strict=True)
            and record.get("main_fingerprint") == main_evidence.fingerprint
            and record.get("companion_fingerprint") == helper_evidence.fingerprint
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _target_shape_errors(main: GgufEvidence, helper: GgufEvidence, method: str) -> list[str]:
    architecture = str(main.metadata.get("general.architecture") or "")
    hidden_dim = main.metadata.get(f"{architecture}.embedding_length")
    if not isinstance(hidden_dim, int) or hidden_dim <= 0:
        return ["main model target embedding dimensions are missing"]
    if method in {"dflash", "dspark"}:
        layers = helper.metadata.get("dflash.target_layers")
        main_layers = main.metadata.get(f"{architecture}.block_count")
        if (
            not isinstance(layers, tuple)
            or not layers
            or not isinstance(main_layers, int)
            or isinstance(main_layers, bool)
            or main_layers <= 0
        ):
            return ["DFlash/DSpark target-layer evidence is missing"]
        # GGUF block_count includes integrated NextN prediction blocks. A
        # target-bound helper captures ordinary decoder states only.
        nextn_layers = main.metadata.get(f"{architecture}.nextn_predict_layers", 0)
        if not isinstance(nextn_layers, int) or isinstance(nextn_layers, bool) or not 0 <= nextn_layers < main_layers:
            return ["DFlash/DSpark main decoder-layer count evidence is invalid"]
        decoder_layers = main_layers - nextn_layers
        if any(
            not isinstance(layer, int) or isinstance(layer, bool) or layer < 0 or layer >= decoder_layers
            for layer in layers
        ):
            return ["DFlash/DSpark target layers exceed the main model architecture"]
        projection = helper.tensors.get("fc.weight")
        if not projection or projection[0] != hidden_dim * len(layers):
            return ["DFlash/DSpark target feature projection dimensions mismatch"]
    elif method == "mtp":
        helper_arch = str(helper.metadata.get("general.architecture") or "")
        target_dim = helper.metadata.get(f"{helper_arch}.embedding_length_out")
        if target_dim is None:
            target_dim = helper.metadata.get(f"{helper_arch}.embedding_length")
        if target_dim != hidden_dim:
            return ["MTP target projection dimensions mismatch"]
        if helper_arch.endswith("-assistant"):
            pre = helper.tensors.get("nextn.pre_projection.weight")
            post = helper.tensors.get("nextn.post_projection.weight")
            if (
                not pre
                or not post
                or len(pre) != 2
                or len(post) != 2
                or pre[0] != hidden_dim * 2
                or post[1] != hidden_dim
            ):
                return ["MTP target projection tensor dimensions mismatch"]
        elif not any(
            name.endswith(".nextn.eh_proj.weight") and len(shape) == 2 and shape[0] == hidden_dim * 2
            for name, shape in helper.tensors.items()
        ):
            return ["MTP target feature projection tensor evidence is missing"]
        if helper_arch.endswith("-assistant") and helper_arch.removesuffix("-assistant") != architecture:
            return ["MTP companion target architecture mismatch"]
    return []


def _has_gguf_magic(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(4) == b"GGUF"
    except OSError:
        return False


def _integrated_mtp_errors(main_path: str | Path | None) -> tuple[str, ...]:
    """Prove MTP layers in a runnable main GGUF before enabling draft-mtp."""
    if not main_path:
        return ("main GGUF path is not configured for an integrated MTP profile",)
    main = Path(main_path)
    if not main.is_file():
        return (f"integrated MTP main GGUF does not exist: {main}",)
    if main.suffix.casefold() != ".gguf" or not _has_gguf_magic(main):
        return (f"integrated MTP main file is not a GGUF: {main}",)
    try:
        evidence = read_gguf_evidence(main)
    except (OSError, ValueError, struct.error) as exc:
        return (f"integrated MTP GGUF header evidence could not be read: {exc}",)
    architecture = str(evidence.metadata.get("general.architecture") or "")
    if (
        _helper_kind(evidence) is not None
        or "token_embd.weight" not in evidence.tensors
        or not any(name.startswith("blk.") and ".nextn." not in name for name in evidence.tensors)
    ):
        return ("integrated MTP requires an independently runnable main model, not a sidecar",)
    layer_count = evidence.metadata.get(f"{architecture}.nextn_predict_layers")
    block_count = evidence.metadata.get(f"{architecture}.block_count")
    if (
        not isinstance(layer_count, int)
        or isinstance(layer_count, bool)
        or not isinstance(block_count, int)
        or isinstance(block_count, bool)
        or not 0 < layer_count < block_count
    ):
        return ("integrated MTP nextn layer metadata is missing or invalid",)
    hidden_dim = evidence.metadata.get(f"{architecture}.embedding_length")
    if not isinstance(hidden_dim, int) or isinstance(hidden_dim, bool) or hidden_dim <= 0:
        return ("integrated MTP main embedding dimensions are missing or invalid",)
    for layer in range(block_count - layer_count, block_count):
        prefix = f"blk.{layer}.nextn."
        if evidence.tensors.get(prefix + "eh_proj.weight") != (hidden_dim * 2, hidden_dim):
            return (f"integrated MTP projection tensor evidence is missing or incompatible at layer {layer}",)
        for name in ("enorm.weight", "hnorm.weight"):
            if evidence.tensors.get(prefix + name) != (hidden_dim,):
                return (f"integrated MTP normalization tensor evidence is missing or incompatible at layer {layer}",)
    return ()


def validate_companion_binding(
    main_path: str | Path | None,
    companion_path: str | Path | None,
    profile: dict[str, Any],
) -> tuple[str, ...]:
    """Validate ordinary drafts and target-bound helpers using actual GGUF evidence.

    Ordinary drafts may have different sizes and architectures. Specialized
    helpers require their algorithm, tokenizer, target dimensions and target
    identity to be proven by headers or an artifact-bound successful pairing.
    """
    normalized = normalize_speculative_profile(profile)
    if profile and not normalized:
        return (
            "unsupported speculative profile type" if profile.get("type") else "speculative profile type is missing",
        )
    if normalized.get("type") == "mtp" and normalized.get("mode") not in {"integrated", "separate"}:
        return ("unsupported MTP mode",)
    role = companion_role(normalized)
    if role is None:
        return _integrated_mtp_errors(main_path) if normalized.get("type") == "mtp" else ()
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

    if errors:
        return tuple(errors)
    method = "mtp" if role == "mtp" else str(normalized.get("method") or "")
    if method not in {"mtp", "simple", "dflash", "dspark"}:
        return (f"unsupported speculative method: {method}",)
    try:
        main_evidence, helper_evidence = read_gguf_evidence(main), read_gguf_evidence(companion)
    except (OSError, ValueError, struct.error) as exc:
        return (f"GGUF companion header evidence could not be read: {exc}",)
    errors.extend(_tokenizer_errors(main_evidence, helper_evidence, ordinary_draft=method == "simple"))
    helper_kind = _helper_kind(helper_evidence)
    if method == "simple":
        if helper_kind is not None or not (
            "token_embd.weight" in helper_evidence.tensors
            and any(name.startswith("blk.") for name in helper_evidence.tensors)
        ):
            errors.append("simple draft profile requires an independently runnable draft model")
    else:
        if helper_kind != method:
            errors.append(f"{method} profile conflicts with companion header kind: {helper_kind or 'ordinary model'}")
        errors.extend(_target_shape_errors(main_evidence, helper_evidence, method))
        if not _header_target_matches(main_evidence, helper_evidence) and not _pairing_evidence_matches(
            normalized,
            main,
            companion,
            main_evidence,
            helper_evidence,
            method,
        ):
            errors.append(
                "specialized companion target identity is unproven; matching headers or valid pairing evidence required"
            )
    return tuple(errors)
