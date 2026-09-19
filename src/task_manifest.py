"""Create one-time integrity and prompt-injection manifests for benchmark inputs."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

_TEXT_FIELDS = (
    "prompt",
    "instruction",
    "question",
    "description",
    "input",
    "context",
    "messages",
    "conversation",
)

_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?previous\s+(instructions?|rules?)", re.IGNORECASE),
    re.compile(r"ignore\s+(the\s+)?benchmark\s+(rules?|instructions?)", re.IGNORECASE),
    re.compile(
        r"(read|open|send|upload|print)\b.{0,80}\b(secret|password|token|credential|api[ -]?key)", re.IGNORECASE
    ),
    re.compile(r"(reveal| disclose|leak)\b.{0,80}\b(system prompt|secret|password|token|credential)", re.IGNORECASE),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_text_values(item))
        return result
    if isinstance(value, dict):
        result = []
        for item in value.values():
            result.extend(_text_values(item))
        return result
    return []


def find_prompt_injection_warnings(task: dict[str, Any]) -> list[str]:
    """Return warnings for deliberately narrow, obvious injection indicators."""
    text = "\n".join(text_value for field in _TEXT_FIELDS for text_value in _text_values(task.get(field)))
    return [pattern.pattern for pattern in _INJECTION_PATTERNS if pattern.search(text)]


def build_manifest(benchmark: str, source: Path) -> dict[str, Any]:
    """Read a JSONL dataset and return a compact, human-readable manifest."""
    tasks: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    with source.open(encoding="utf-8") as handle:
        for ordinal, line in enumerate(handle):
            if not line.strip():
                continue
            task = json.loads(line)
            if not isinstance(task, dict):
                raise ValueError(f"{source}: line {ordinal + 1} is not a JSON object")
            task_id = next(
                (task.get(key) for key in ("task_id", "id", "question_id", "problem_id") if task.get(key) is not None),
                ordinal,
            )
            task_entry = {"ordinal": ordinal, "id": str(task_id)}
            tasks.append(task_entry)
            for pattern in find_prompt_injection_warnings(task):
                warnings.append({"ordinal": ordinal, "id": str(task_id), "pattern": pattern})

    return {
        "format": "benchmark-task-manifest-v1",
        "benchmark": benchmark,
        "source": str(source.resolve()),
        "source_sha256": sha256_file(source),
        "task_count": len(tasks),
        "tasks": tasks,
        "prompt_injection_warnings": warnings,
    }
