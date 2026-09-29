"""Pure KV-pair policy shared by persisted configs and executable adapters.

Only symmetric Q4_0 and Q8_0 pairs are emitted. Select the nearest combined
bit budget (8 or 16), with the tie at 12 going to Q4_0. Missing one side
mirrors the supplied side; missing both sides leaves the provider default.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_BITS = {
    "q4_0": 4.0, "iq4_nl": 4.0, "q4_1": 4.5,
    "q5_0": 5.0, "q5_1": 5.5, "q8_0": 8.0,
    "f16": 16.0, "bf16": 16.0, "f32": 32.0,
}
_ALIASES = {
    "q4_nl": "iq4_nl", "q8": "q8_0",
    "fp16": "f16", "float16": "f16",
    "fp32": "f32", "float32": "f32", "bfloat16": "bf16",
}


class KVCachePolicyError(ValueError):
    """An explicit KV value cannot establish the supported-pair contract."""


def kv_cache_type(value: Any) -> str | None:
    """Read a typed scalar/checkbox without inventing an effective cache type.

An unchecked LM Studio checkbox disables cache quantization, hence F16.
This parser also serves effective-load verification, which must compare the
actual type rather than normalize an unsafe loaded pair into a safe one.
"""
    if value is None:
        return None
    if isinstance(value, Mapping):
        checked = value.get("checked", True)
        if not isinstance(checked, bool):
            raise KVCachePolicyError("KV-cache checkbox checked must be boolean")
        if checked is False:
            return "f16"
        if "value" not in value:
            raise KVCachePolicyError("KV-cache checkbox requires a value")
        value = value["value"]
    if not isinstance(value, str) or not value.strip():
        raise KVCachePolicyError(f"invalid KV-cache type: {value!r}")
    cache_type = value.strip().casefold().replace("-", "_")
    cache_type = _ALIASES.get(cache_type, cache_type)
    if cache_type not in _BITS:
        raise KVCachePolicyError(f"unsupported KV-cache type: {value!r}")
    return cache_type


def normalize_kv_pair(k_cache: Any = None, v_cache: Any = None) -> tuple[str | None, str | None]:
    """Return the supported symmetric pair; reject malformed explicit values."""
    k_type, v_type = kv_cache_type(k_cache), kv_cache_type(v_cache)
    if k_type is None and v_type is None:
        return None, None
    k_type = k_type or v_type
    v_type = v_type or k_type
    assert k_type is not None and v_type is not None
    cache_type = "q4_0" if _BITS[k_type] + _BITS[v_type] <= 12 else "q8_0"
    return cache_type, cache_type


def runtime_kv_pair(k_cache: Any = None, v_cache: Any = None) -> tuple[str, str]:
    """Resolve an executable pair, explicitly defaulting missing policy to Q8."""
    pair = normalize_kv_pair(k_cache, v_cache)
    if pair == (None, None):
        return "q8_0", "q8_0"
    k_type, v_type = pair
    assert k_type is not None and v_type is not None
    return k_type, v_type
