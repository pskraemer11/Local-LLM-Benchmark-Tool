"""Small real GGUF headers for companion-contract tests; no model weights."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any


def write_gguf(
    path: Path,
    *,
    architecture: str = "qwen35",
    hidden_dim: int = 5120,
    block_count: int = 64,
    source_repo: str = "Qwen/Qwen3.6-27B",
    helper: str | None = None,
    target_repo: str | None = None,
    tokens: tuple[str, ...] = ("a", "b", "c", "d"),
    target_dim: int | None = None,
    metadata: dict[str, Any] | None = None,
    tensors: dict[str, tuple[int, ...]] | None = None,
) -> None:
    target_dimension = target_dim if target_dim is not None else hidden_dim
    fields: dict[str, Any] = {
        "general.architecture": architecture,
        "general.repo_url": f"https://huggingface.co/{source_repo}",
        f"{architecture}.embedding_length": hidden_dim,
        f"{architecture}.block_count": block_count,
        "tokenizer.ggml.model": "gpt2",
        "tokenizer.ggml.tokens": tokens,
        "tokenizer.ggml.bos_token_id": 0,
        "tokenizer.ggml.eos_token_id": 1,
    }
    descriptions: dict[str, tuple[int, ...]] = {
        "token_embd.weight": (hidden_dim, len(tokens)),
        "blk.0.attn_q.weight": (hidden_dim, hidden_dim),
        "output.weight": (hidden_dim, len(tokens)),
    }
    if helper in {"dflash", "dspark"}:
        fields.update({"dflash.target_layers": (1, 3), "dflash.block_size": 8})
        descriptions = {"fc.weight": (target_dimension * 2, hidden_dim)}
        if helper == "dspark":
            descriptions.update({"markov_w1.weight": (32, len(tokens)), "markov_w2.weight": (32, len(tokens))})
    elif helper == "mtp":
        fields[f"{architecture}.embedding_length_out"] = target_dimension
        fields[f"{architecture}.nextn_predict_layers"] = 4
        descriptions = {
            "token_embd.weight": (hidden_dim, len(tokens)),
            "nextn.pre_projection.weight": (target_dimension * 2, hidden_dim),
            "nextn.post_projection.weight": (hidden_dim, target_dimension),
        }
    if target_repo:
        fields["speculative.target.repo_url"] = f"https://huggingface.co/{target_repo}"
    if metadata:
        fields.update(metadata)
    if tensors is not None:
        descriptions = tensors

    def string(value: str) -> bytes:
        raw = value.encode("utf-8")
        return struct.pack("<Q", len(raw)) + raw

    def value(item: Any) -> tuple[int, bytes]:
        if isinstance(item, str):
            return 8, string(item)
        if isinstance(item, bool):
            return 7, struct.pack("<?", item)
        if isinstance(item, int):
            return 4, struct.pack("<I", item)
        if isinstance(item, float):
            return 6, struct.pack("<f", item)
        if isinstance(item, (tuple, list)):
            values = [value(child) for child in item]
            element_type = values[0][0] if values else 4
            return 9, struct.pack("<IQ", element_type, len(values)) + b"".join(raw for _, raw in values)
        raise TypeError(item)

    result = bytearray(b"GGUF" + struct.pack("<IQQ", 3, len(descriptions), len(fields)))
    for key, item in fields.items():
        value_type, raw = value(item)
        result.extend(string(key) + struct.pack("<I", value_type) + raw)
    for name, shape in descriptions.items():
        result.extend(string(name) + struct.pack("<I", len(shape)))
        result.extend(struct.pack("<" + "Q" * len(shape), *shape))
        result.extend(struct.pack("<IQ", 0, 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(result)
