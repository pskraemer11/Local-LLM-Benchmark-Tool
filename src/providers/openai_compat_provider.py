"""Provider for servers exposing only the OpenAI-compatible API."""

from __future__ import annotations

import os
import time
from typing import Any

from .base import HttpProvider, ProviderCapabilities


class OpenAICompatProvider(HttpProvider):
    """OpenAI-compatible inference with an optional Unsloth lifecycle extension."""

    capabilities = ProviderCapabilities(
        can_list_models=True,
        can_load_models=False,
        can_unload_models=False,
        can_report_current_model=False,
    )

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        lifecycle: bool = False,
        lifecycle_timeout: int | None = None,
    ) -> None:
        key = (
            api_key
            or os.environ.get("UNSLOTH_API_KEY")
            or os.environ.get("OPENAI_COMPAT_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("LLM_API_KEY")
        )
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        super().__init__(base_url, headers)
        self._lifecycle = lifecycle
        self._lifecycle_timeout = lifecycle_timeout or int(os.environ.get("UNSLOTH_LOAD_TIMEOUT", "300"))
        self.capabilities = ProviderCapabilities(
            can_list_models=True,
            can_load_models=lifecycle,
            can_unload_models=lifecycle,
            can_report_current_model=lifecycle,
        )

    def list_models(
        self,
        exclude_keywords: list[str] | None = None,
        registry_only: bool = False,
    ) -> list[dict[str, Any]]:
        del registry_only
        payload = self.request_json("/models", timeout=10)
        if not isinstance(payload, dict):
            return []
        raw_models = payload.get("data", payload.get("models", []))
        if not isinstance(raw_models, list):
            return []
        models: list[dict[str, Any]] = []
        for item in raw_models:
            if isinstance(item, str):
                model_id = item
            elif isinstance(item, dict):
                model_id = item.get("id") or item.get("model") or item.get("name")
            else:
                model_id = None
            if not model_id:
                continue
            model = {
                "key": model_id,
                "model_identifier": model_id,
                "display": model_id,
                "variant": model_id,
                "quant": "",
                "variants": [],
                "identifier": model_id,
                "params": "",
                "publisher": model_id.split("/", 1)[0] if "/" in model_id else "",
                "modelKey": model_id,
            }
            if isinstance(item, dict):
                if item.get("display_name"):
                    model["display"] = item["display_name"]
                for field in ("created", "owned_by", "quant", "loaded", "context_length",
                              "max_context_length", "native_context_length"):
                    if field in item:
                        model[field] = item[field]
            models.append(model)
        if exclude_keywords:
            models = [
                model
                for model in models
                if not any(
                    keyword in f"{model['key']} {model['display']}".lower()
                    for keyword in exclude_keywords
                )
            ]
        return models

    def is_available(self, timeout: int = 5) -> bool:
        try:
            payload = self.request_json("/models", timeout=timeout)
        except Exception:
            return False
        return payload is not None

    def current_model(self) -> dict[str, Any] | None:
        """Use an explicit nonstandard ``loaded`` field when a server provides one."""
        loaded = [model for model in self.list_models() if model.get("loaded") is True]
        if len(loaded) != 1:
            return None
        model = loaded[0]
        model_id = model["model_identifier"]
        return {
            "identifier": model_id,
            "model_identifier": model_id,
            "display_name": model["display"],
            "status": "loaded",
            "context_length": model.get("context_length"),
        }

    def load_model(self, model_identifier: str, gpu_offload: float | None = None) -> tuple[bool, str | None]:
        del gpu_offload
        matches = [
            model for model in self.list_models()
            if model["model_identifier"] == model_identifier
        ]
        if not matches:
            return False, None
        if self._lifecycle:
            if any(model.get("loaded") is True for model in matches):
                return True, model_identifier
            response = self.request_json(
                "/load",
                method="POST",
                payload={"model_path": model_identifier},
                timeout=self._lifecycle_timeout,
            )
            if response is None:
                return False, None
            if self._wait_until_loaded(model_identifier):
                return True, model_identifier
            return False, None
        explicit_loaded_state = any("loaded" in model for model in matches)
        if explicit_loaded_state and not any(model.get("loaded") is True for model in matches):
            return False, None
        return True, model_identifier

    def _wait_until_loaded(self, model_identifier: str) -> bool:
        deadline = time.monotonic() + self._lifecycle_timeout
        while True:
            loaded = [
                model for model in self.list_models()
                if model["model_identifier"] == model_identifier and model.get("loaded") is True
            ]
            if loaded:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(1)

    def unload_all(self, timeout: int = 120) -> bool:
        if not self._lifecycle:
            del timeout
            return False
        loaded = [model for model in self.list_models() if model.get("loaded") is True]
        if not loaded:
            return True
        for model in loaded:
            response = self.request_json(
                "/unload",
                method="POST",
                payload={"model_path": model["model_identifier"]},
                timeout=timeout,
            )
            if response is None:
                return False
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not any(model.get("loaded") is True for model in self.list_models()):
                return True
            time.sleep(1)
        return False

    def wait_ready(self, timeout: int = 120) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.is_available(timeout=min(5, max(1, int(deadline - time.monotonic())))):
                return True
            time.sleep(1)
        return False
