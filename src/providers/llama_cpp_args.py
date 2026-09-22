"""Pure llama.cpp argument translation shared by provider and export tools."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

DEFAULT_SERVER_PARALLEL = 4
SUPPORTED_CACHE_TYPES = frozenset(
    {"f32", "f16", "bf16", "q8_0", "q4_0", "q4_1", "iq4_nl", "q5_0", "q5_1"}
)
CACHE_TYPE_ALIASES = {"fp16": "f16", "float16": "f16", "q4_nl": "iq4_nl"}
REASONING_FORMATS = frozenset({"auto", "none", "deepseek", "deepseek-legacy"})


def normalize_cache_type(value: Any) -> str | None:
    """Normalize and validate a llama.cpp KV-cache type."""
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold().replace("-", "_")
    normalized = CACHE_TYPE_ALIASES.get(normalized, normalized)
    return normalized if normalized in SUPPORTED_CACHE_TYPES else None


def _as_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"0", "false", "no", "off"}:
            return False
        if normalized in {"1", "true", "yes", "on"}:
            return True
    return default


def build_runtime_args(
    runtime: Mapping[str, Any],
    environment: Mapping[str, str] | None = None,
    warning: Callable[[str], None] | None = None,
) -> list[str]:
    """Translate validated Registry runtime data into server start arguments."""
    env = environment or os.environ
    notify = warning or (lambda _message: None)
    args: list[str] = []

    context_length = runtime.get("context_length")
    if isinstance(context_length, int) and context_length > 0:
        args.extend(["--ctx-size", str(context_length)])

    parallel = env.get("LLAMA_CPP_PARALLEL") or runtime.get("parallel") or env.get(
        "LLAMA_CPP_MAX_PARALLEL"
    )
    try:
        parallel_value = int(parallel or DEFAULT_SERVER_PARALLEL)
        if parallel_value < 1:
            raise ValueError
    except (TypeError, ValueError):
        notify(f"Invalid llama.cpp parallel value {parallel!r}; using {DEFAULT_SERVER_PARALLEL}.")
        parallel_value = DEFAULT_SERVER_PARALLEL
    args.extend(["--parallel", str(parallel_value)])

    for key, option in (("cache_type_k", "--cache-type-k"), ("cache_type_v", "--cache-type-v")):
        value = normalize_cache_type(runtime.get(key))
        if value is not None:
            args.extend([option, value])

    args.append("--kv-unified" if _as_bool(runtime.get("kv_unified"), default=True) else "--no-kv-unified")

    for key, option in (
        ("batch_size", "--batch-size"),
        ("ubatch_size", "--ubatch-size"),
        ("reasoning_budget", "--reasoning-budget"),
    ):
        value = runtime.get(key)
        if isinstance(value, (int, str)) and str(value).strip():
            try:
                args.extend([option, str(int(value))])
            except (TypeError, ValueError):
                notify(f"Invalid llama.cpp value {key}={value!r}; ignoring it.")

    for key, option in (
        ("gpu_layers", "--gpu-layers"),
        ("reasoning_effort", "--reasoning-effort"),
        ("chat_template_file", "--chat-template-file"),
    ):
        value = runtime.get(key)
        if isinstance(value, (int, str)) and str(value).strip():
            args.extend([option, str(value).strip()])

    # llama.cpp does not expose a dedicated --num-experts option. Its
    # supported metadata override changes the active expert count used by the
    # MoE graph, e.g. deepseek2.expert_used_count=int:24.
    num_experts = runtime.get("num_experts")
    expert_key = runtime.get("expert_override_key")
    if (
        isinstance(num_experts, int)
        and not isinstance(num_experts, bool)
        and num_experts > 0
        and isinstance(expert_key, str)
        and expert_key.strip()
    ):
        args.extend(["--override-kv", f"{expert_key.strip()}=int:{num_experts}"])
    elif isinstance(num_experts, int) and num_experts > 0:
        notify("Runtime num_experts has no architecture-specific llama.cpp override key; ignoring it.")

    reasoning_format = str(
        runtime.get("reasoning_format") or env.get("LLAMA_CPP_REASONING_FORMAT", "auto")
    ).strip().lower()
    if reasoning_format not in REASONING_FORMATS:
        notify(f"Invalid --reasoning-format {reasoning_format!r}; using 'auto'.")
        reasoning_format = "auto"
    args.extend(["--reasoning-format", reasoning_format])

    flash_attn = str(runtime.get("flash_attn") or env.get("LLAMA_CPP_FLASH_ATTN", "on")).strip()
    args.extend(["--flash-attn", flash_attn])
    args.append("--cont-batching" if _as_bool(runtime.get("cont_batching"), default=True) else "--no-cont-batching")
    args.append("--jinja" if _as_bool(runtime.get("jinja"), default=True) else "--no-jinja")
    return args


def build_server_command(
    executable: str | Path,
    model_path: str | Path,
    model_identifier: str,
    port: str | int,
    runtime: Mapping[str, Any],
    environment: Mapping[str, str] | None = None,
    warning: Callable[[str], None] | None = None,
) -> list[str]:
    """Build the complete deterministic llama-server command for one model."""
    return [
        str(executable),
        "--model",
        str(model_path),
        "--offline",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--alias",
        model_identifier,
        "--no-webui",
        *build_runtime_args(runtime, environment=environment, warning=warning),
    ]
