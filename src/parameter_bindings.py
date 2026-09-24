"""Declarative cross-boundary parameter bindings.

The Registry field is the provider-neutral contract.  Backend adapters use
this table to name their local representation; policy and source ownership
remain separate in :mod:`field_owner`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParameterBinding:
    """One canonical field and its backend-specific spellings."""

    registry_field: str
    lmstudio_field: str | None = None
    llama_cpp_flag: str | None = None
    value_kind: str = "passthrough"
    owner: str = "registry"


PARAMETER_BINDINGS: tuple[ParameterBinding, ...] = (
    ParameterBinding("context_length", "context_length", "--ctx-size", "positive_int"),
    ParameterBinding("offload", "offload", None, "ratio"),
    ParameterBinding("useUnifiedKvCache", "use_unified_kv", "--kv-unified", "bool"),
    ParameterBinding("k_cache", "k_cache", "--cache-type-k", "cache_type"),
    ParameterBinding("v_cache", "v_cache", "--cache-type-v", "cache_type"),
    ParameterBinding("experts", "num_experts", "--override-kv", "positive_int"),
    ParameterBinding("batch_size", None, "--batch-size", "positive_int"),
    ParameterBinding("ubatch_size", None, "--ubatch-size", "positive_int"),
    ParameterBinding("reasoning_budget", None, "--reasoning-budget", "positive_int"),
    ParameterBinding("gpu_layers", None, "--gpu-layers", "integer"),
    ParameterBinding("reasoning_effort", None, "--reasoning-effort", "string"),
    ParameterBinding("chat_template_file", None, "--chat-template-file", "string"),
    ParameterBinding("reasoning_format", None, "--reasoning-format", "enum"),
    ParameterBinding("flash_attn", None, "--flash-attn", "enum"),
    ParameterBinding("cont_batching", None, "--cont-batching", "bool_flag"),
    ParameterBinding("jinja", None, "--jinja", "bool_flag"),
)

_BY_REGISTRY_FIELD = {binding.registry_field: binding for binding in PARAMETER_BINDINGS}


def parameter_binding(field: str) -> ParameterBinding | None:
    """Return the binding for a canonical Registry field."""
    return _BY_REGISTRY_FIELD.get(field)


def config_sync_fields(*, context_only: bool = False, experts_only: bool = False) -> tuple[tuple[str, str], ...]:
    """Return the LM Studio fields eligible for the corresponding sync mode."""
    fields: tuple[str, ...]
    if context_only:
        fields = ("context_length",)
    elif experts_only:
        fields = ("experts",)
    else:
        fields = ("offload", "useUnifiedKvCache", "context_length", "k_cache", "v_cache", "experts")
    result: list[tuple[str, str]] = []
    for field in fields:
        lmstudio_field = _BY_REGISTRY_FIELD[field].lmstudio_field
        if lmstudio_field is not None:
            result.append((field, lmstudio_field))
    return tuple(result)


def llama_cpp_value_bindings() -> tuple[ParameterBinding, ...]:
    """Return bindings represented by direct llama.cpp value flags."""
    return tuple(
        binding
        for binding in PARAMETER_BINDINGS
        if binding.llama_cpp_flag is not None
        and binding.value_kind in {"positive_int", "integer", "string"}
        and binding.registry_field not in {"context_length", "experts"}
    )
