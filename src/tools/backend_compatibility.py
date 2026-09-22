"""Compare OpenAI-compatible local backends with identical requests.

This tool is deliberately report-oriented.  It does not load or unload a
model and it never starts a server.  Lifecycle ownership remains with the
selected provider.  A report therefore captures the API behaviour of two
already running endpoints without hiding provider-specific failures.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from collections.abc import Iterable


DEFAULT_PROMPT = "Reply with exactly COMPAT_OK and no other text."


@dataclass(frozen=True)
class RequestSpec:
    """Shared request parameters used for every backend measurement."""

    prompt: str
    max_tokens: int = 256
    temperature: float = 0.0
    top_p: float = 1.0
    seed: int = 42
    response_format: str = "text"


@dataclass
class Measurement:
    """One backend/mode result, including transport and model output facts."""

    backend: str
    base_url: str
    model: str
    mode: str
    ok: bool
    status_code: int | None = None
    elapsed_s: float | None = None
    first_event_s: float | None = None
    chunk_count: int = 0
    content: str = ""
    reasoning: str = ""
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    error_type: str | None = None
    error_detail: str | None = None


def normalize_base_url(base_url: str) -> str:
    """Return an OpenAI-compatible base URL ending in ``/v1``."""
    normalized = base_url.rstrip("/")
    return normalized if normalized.endswith("/v1") else f"{normalized}/v1"


def build_payload(model: str, spec: RequestSpec, *, stream: bool) -> dict[str, Any]:
    """Build the exact request payload used by both providers."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": spec.prompt}],
        "max_tokens": spec.max_tokens,
        "temperature": spec.temperature,
        "top_p": spec.top_p,
        "seed": spec.seed,
        "stream": stream,
    }
    if spec.response_format == "json":
        payload["response_format"] = {"type": "json_object"}
    return payload


def _as_dict(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _choice_text(choice: dict[str, Any], *, stream: bool) -> tuple[str, str, str | None]:
    value = choice.get("delta" if stream else "message", {})
    message = value if isinstance(value, dict) else {}
    content = message.get("content", "")
    reasoning = message.get("reasoning_content", message.get("reasoning", ""))
    return (
        content if isinstance(content, str) else "",
        reasoning if isinstance(reasoning, str) else "",
        choice.get("finish_reason") if isinstance(choice.get("finish_reason"), str) else None,
    )


def _usage_values(response: dict[str, Any]) -> tuple[int | None, int | None]:
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return None, None
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    return (
        prompt if isinstance(prompt, int) else None,
        completion if isinstance(completion, int) else None,
    )


def parse_sse_lines(lines: Iterable[bytes | str]) -> tuple[str, str, str | None, int]:
    """Parse OpenAI SSE data lines into content, reasoning, finish, count."""
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    finish_reason: str | None = None
    chunks = 0
    for raw_line in lines:
        line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else raw_line
        line = line.strip()
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            continue
        try:
            response = json.loads(data)
        except json.JSONDecodeError:
            continue
        if not isinstance(response, dict):
            continue
        choices = response.get("choices", [])
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            continue
        content, reasoning, chunk_finish = _choice_text(choices[0], stream=True)
        content_parts.append(content)
        reasoning_parts.append(reasoning)
        finish_reason = chunk_finish or finish_reason
        chunks += 1
    return "".join(content_parts), "".join(reasoning_parts), finish_reason, chunks


def _request_headers() -> dict[str, str]:
    return {"Accept": "application/json", "Content-Type": "application/json"}


def measure(base_url: str, backend: str, model: str, spec: RequestSpec, *, stream: bool, timeout: int) -> Measurement:
    """Send one request and return a failure-preserving measurement."""
    mode = "stream" if stream else "nonstream"
    result = Measurement(backend=backend, base_url=normalize_base_url(base_url), model=model, mode=mode, ok=False)
    request = Request(
        f"{result.base_url}/chat/completions",
        data=json.dumps(build_payload(model, spec, stream=stream)).encode("utf-8"),
        headers=_request_headers(),
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout) as response:
            result.status_code = int(getattr(response, "status", 200))
            if stream:
                first_event: float | None = None
                raw_lines: list[bytes] = []
                for raw_line in response:
                    if first_event is None and raw_line.strip().startswith(b"data:"):
                        first_event = time.perf_counter() - started
                    raw_lines.append(raw_line)
                result.content, result.reasoning, result.finish_reason, result.chunk_count = parse_sse_lines(raw_lines)
                result.first_event_s = first_event
            else:
                raw = response.read().decode("utf-8", errors="replace")
                decoded = _as_dict(json.loads(raw))
                if decoded is None:
                    raise ValueError("response JSON is not an object")
                choices = decoded.get("choices", [])
                if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                    raise ValueError("response contains no usable choice")
                result.content, result.reasoning, result.finish_reason = _choice_text(choices[0], stream=False)
                result.prompt_tokens, result.completion_tokens = _usage_values(decoded)
            result.elapsed_s = time.perf_counter() - started
            result.ok = 200 <= (result.status_code or 0) < 300
    except HTTPError as exc:
        result.status_code = int(exc.code)
        result.error_type = "http_error"
        result.error_detail = exc.read().decode("utf-8", errors="replace")[:2000]
    except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        result.error_type = type(exc).__name__
        result.error_detail = str(exc)[:2000]
    finally:
        if result.elapsed_s is None:
            result.elapsed_s = time.perf_counter() - started
    return result


def run_comparison(
    lmstudio_url: str,
    llama_url: str,
    lmstudio_model: str,
    llama_model: str,
    spec: RequestSpec,
    *,
    modes: tuple[str, ...] = ("nonstream", "stream"),
    timeout: int = 120,
) -> dict[str, Any]:
    """Run identical measurements against LM Studio and llama.cpp."""
    measurements = run_single_backend(lmstudio_url, "lmstudio", lmstudio_model, spec, modes=modes, timeout=timeout)
    measurements.extend(run_single_backend(llama_url, "llama_cpp", llama_model, spec, modes=modes, timeout=timeout))
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "request": asdict(spec),
        "measurements": [asdict(item) for item in measurements],
    }


def run_single_backend(
    base_url: str,
    backend: str,
    model: str,
    spec: RequestSpec,
    *,
    modes: tuple[str, ...] = ("nonstream", "stream"),
    timeout: int = 120,
) -> list[Measurement]:
    """Measure one already-running backend, preserving each failed mode."""
    measurements: list[Measurement] = []
    for mode in modes:
        if mode not in {"nonstream", "stream"}:
            raise ValueError(f"Unsupported mode: {mode}")
        measurements.append(measure(base_url, backend, model, spec, stream=mode == "stream", timeout=timeout))
    return measurements


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lmstudio-url", default="http://127.0.0.1:1234/v1")
    parser.add_argument("--llama-url", default="http://127.0.0.1:8080/v1")
    parser.add_argument("--lmstudio-model", default="lmstudio-model")
    parser.add_argument("--llama-model", default="llama-model")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--response-format", choices=("text", "json"), default="text")
    parser.add_argument("--mode", choices=("all", "nonstream", "stream"), default="all")
    parser.add_argument("--backend", choices=("all", "lmstudio", "llama_cpp"), default="all")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--output", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    modes = ("nonstream", "stream") if args.mode == "all" else (args.mode,)
    spec = RequestSpec(
        prompt=args.prompt,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
        seed=args.seed,
        response_format=args.response_format,
    )
    if args.backend == "all":
        report = run_comparison(
            args.lmstudio_url,
            args.llama_url,
            args.lmstudio_model,
            args.llama_model,
            spec,
            modes=modes,
            timeout=args.timeout,
        )
    else:
        base_url, model = (
            (args.lmstudio_url, args.lmstudio_model)
            if args.backend == "lmstudio"
            else (args.llama_url, args.llama_model)
        )
        measurements = run_single_backend(base_url, args.backend, model, spec, modes=modes, timeout=args.timeout)
        report = {
            "created_at": datetime.now(UTC).isoformat(),
            "request": asdict(spec),
            "measurements": [asdict(item) for item in measurements],
        }
    output = args.output or Path("ergebnisse") / f"backend-compatibility-{datetime.now():%Y%m%d-%H%M%S}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    return 0 if all(item["ok"] for item in report["measurements"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
