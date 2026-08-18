"""Stable contracts shared by benchmark inference providers.

The benchmark runner needs two different contracts: an OpenAI-compatible
inference surface and an optional model-lifecycle surface.  Keeping lifecycle
capabilities explicit prevents treating ``/v1/models`` as a portable unload
API when a server only exposes inference.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError


@dataclass(frozen=True)
class ProviderCapabilities:
    """Capabilities that may differ between local model servers."""

    can_list_models: bool = True
    can_load_models: bool = False
    can_unload_models: bool = False
    can_report_current_model: bool = False
    supports_chat_completions: bool = True
    supports_completions: bool = True


class ProviderError(RuntimeError):
    """Base error for provider boundary failures."""


class UnsupportedOperation(ProviderError):
    """Raised when a provider cannot implement a lifecycle operation."""


class InferenceClient(Protocol):
    """Inference and model-discovery contract used by benchmark pipelines."""

    base_url: str
    capabilities: ProviderCapabilities

    def list_models(
        self,
        exclude_keywords: list[str] | None = None,
        registry_only: bool = False,
    ) -> list[dict[str, Any]]: ...

    def chat_completions(self, payload: dict[str, Any], timeout: int = 120) -> Any | None: ...

    def completions(self, payload: dict[str, Any], timeout: int = 120) -> Any | None: ...

    def is_available(self, timeout: int = 5) -> bool: ...


class ModelManager(Protocol):
    """Optional model lifecycle contract used by the benchmark launcher."""

    def current_model(self) -> dict[str, Any] | None: ...

    def load_model(self, model_identifier: str, gpu_offload: float | None = None) -> tuple[bool, str | None]: ...

    def unload_all(self, timeout: int = 120) -> bool: ...

    def wait_ready(self, timeout: int = 120) -> bool: ...


class Provider(InferenceClient, ModelManager, Protocol):
    """Combined provider contract consumed by the model-manager facade."""


class HttpProvider:
    """Small Windows-compatible JSON-over-HTTP base for local providers."""

    def __init__(self, base_url: str, headers: dict[str, str] | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {"Accept": "application/json", **(headers or {})}

    def request_json(
        self,
        endpoint: str,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        timeout: int = 120,
        headers: dict[str, str] | None = None,
        read_body: bool = True,
    ) -> Any | None:
        """Make one request and return decoded JSON, or ``None`` on failure."""
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request_headers = {**self.headers, **(headers or {})}
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        request = urllib_request.Request(
            f"{self.base_url}/{endpoint.lstrip('/')}",
            data=body,
            headers=request_headers,
            method=method,
        )
        try:
            with urllib_request.urlopen(request, timeout=timeout) as response:
                status = getattr(response, "status", 200)
                if not 200 <= status < 300:
                    return None
                if not read_body:
                    response.read(1)
                    return {}
                raw = response.read().decode("utf-8")
        except (HTTPError, URLError, OSError, TimeoutError):
            return None
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            # TabbyAPI may answer a successful load request with an SSE body.
            return {}

    def chat_completions(self, payload: dict[str, Any], timeout: int = 120) -> Any | None:
        """Call the provider's OpenAI-compatible chat endpoint."""
        return self.request_json("/chat/completions", method="POST", payload=payload, timeout=timeout)

    def completions(self, payload: dict[str, Any], timeout: int = 120) -> Any | None:
        """Call the provider's OpenAI-compatible text-completion endpoint."""
        return self.request_json("/completions", method="POST", payload=payload, timeout=timeout)
