"""TabbyAPI provider for ExLlama-based local inference."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from .base import HttpProvider, ProviderCapabilities

RuntimeLoader = Callable[[str], Mapping[str, Any] | None]
ConfigLoader = Callable[[], dict[str, Any]]

_LOAD_FIELDS = {
    "backend",
    "max_seq_len",
    "cache_size",
    "cache_mode",
    "tensor_parallel",
    "tensor_parallel_backend",
    "gpu_split_auto",
    "autosplit_reserve",
    "gpu_split",
    "rope_scale",
    "rope_alpha",
    "chunk_size",
    "output_chunking",
    "prompt_template",
    "vision",
}


class TabbyAPIProvider(HttpProvider):
    """TabbyAPI inference plus its provider-specific model lifecycle API."""

    capabilities = ProviderCapabilities(
        can_list_models=True,
        can_load_models=True,
        can_unload_models=True,
        can_report_current_model=True,
    )

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        admin_key: str | None = None,
        runtime_loader: RuntimeLoader | None = None,
        config_loader: ConfigLoader | None = None,
        model_dir: str | Path | None = None,
    ) -> None:
        inference_key = api_key or os.environ.get("TABBYAPI_API_KEY") or os.environ.get("LLM_API_KEY")
        management_key = admin_key or os.environ.get("TABBYAPI_ADMIN_KEY")
        inference_headers = {"Authorization": f"Bearer {inference_key}"} if inference_key else {}
        self._admin_headers = {"Authorization": f"Bearer {management_key}"} if management_key else {}
        super().__init__(base_url, inference_headers)
        self._runtime_loader = runtime_loader
        self._config_loader = config_loader
        self._model_dir = Path(model_dir) if model_dir else None

    def _model_payload(self) -> dict[str, Any] | None:
        payload = self.request_json("/model", headers=self._admin_headers, timeout=10)
        return payload if isinstance(payload, dict) else None

    def current_model(self) -> dict[str, Any] | None:
        payload = self._model_payload()
        if not payload:
            return None
        model_id = payload.get("id") or payload.get("model_name") or payload.get("name")
        if not model_id:
            return None
        parameters = payload.get("parameters") if isinstance(payload.get("parameters"), dict) else {}
        return {
            "identifier": model_id,
            "model_identifier": model_id,
            "display_name": model_id,
            "status": "loaded",
            "context_length": parameters.get("max_seq_len", 0),
            "api_model_id": model_id,
            "model_name": model_id,
            "model_path": str(self._model_dir / model_id) if self._model_dir else None,
            "parameters": parameters,
        }

    def list_models(
        self,
        exclude_keywords: list[str] | None = None,
        registry_only: bool = False,
    ) -> list[dict[str, Any]]:
        del registry_only
        payload = self.request_json("/models", timeout=10)
        raw_models = payload.get("data", payload.get("models", [])) if isinstance(payload, dict) else []
        if not isinstance(raw_models, list):
            raw_models = []
        models: list[dict[str, Any]] = []
        for item in raw_models:
            model_id = item.get("id") if isinstance(item, dict) else item if isinstance(item, str) else None
            if model_id:
                models.append(self._model_info(str(model_id)))
        if models:
            return self._filter_models(models, exclude_keywords)
        current = self.current_model()
        models = [self._model_info(current["model_identifier"])] if current else []
        return self._filter_models(models, exclude_keywords)

    @staticmethod
    def _filter_models(
        models: list[dict[str, Any]],
        exclude_keywords: list[str] | None,
    ) -> list[dict[str, Any]]:
        if not exclude_keywords:
            return models
        return [
            model
            for model in models
            if not any(
                keyword in f"{model['key']} {model['display']}".lower()
                for keyword in exclude_keywords
            )
        ]

    def _model_info(self, model_id: str) -> dict[str, Any]:
        model_path = str(self._model_dir / model_id) if self._model_dir else None
        return {
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
            "api_model_id": model_id,
            "model_name": model_id,
            "model_path": model_path,
        }

    def is_available(self, timeout: int = 5) -> bool:
        return self.request_json("/models", timeout=timeout) is not None

    def _config_args(self) -> dict[str, Any]:
        """Read TabbyAPI model defaults as a provider-local fallback."""
        if self._config_loader is not None:
            return dict(self._config_loader())

        paths = []
        configured = os.environ.get("TABBYAPI_CONFIG")
        if configured:
            paths.append(Path(configured))
        paths.append(Path(__file__).resolve().parents[2] / "tabbyAPI" / "config.yml")
        for path in paths:
            if not path.is_file():
                continue
            try:
                with path.open(encoding="utf-8") as config_file:
                    data = YAML(typ="safe").load(config_file) or {}
            except (OSError, TypeError, ValueError):
                continue
            model_config = data.get("model", {}) if isinstance(data, dict) else {}
            if not isinstance(model_config, dict):
                continue
            return {
                key: value
                for key, value in model_config.items()
                if key in _LOAD_FIELDS and value is not None
            }
        return {"cache_size": 8192, "max_seq_len": 16384}

    def _load_args(self, model_identifier: str) -> dict[str, Any]:
        """Merge config fallback with provider-neutral registry runtime values."""
        args = self._config_args()
        if self._runtime_loader is not None:
            runtime = self._runtime_loader(model_identifier)
            if runtime:
                args.update({key: value for key, value in runtime.items() if key in _LOAD_FIELDS and value is not None})
        return args

    def load_model(
        self,
        model_identifier: str,
        gpu_offload: float | None = None,
        timeout: int | None = None,
    ) -> tuple[bool, str | None]:
        del gpu_offload
        current = self.current_model()
        if current and current["model_identifier"] == model_identifier:
            return True, model_identifier
        payload = {"model_name": model_identifier, **self._load_args(model_identifier)}
        response = self.request_json(
            "/model/load",
            method="POST",
            payload=payload,
            timeout=10,
            headers=self._admin_headers,
            read_body=False,
        )
        if response is None:
            return False, None
        load_timeout = int(os.environ.get("TABBYAPI_LOAD_TIMEOUT", "180")) if timeout is None else timeout
        deadline = time.monotonic() + load_timeout
        while time.monotonic() < deadline:
            current = self.current_model()
            if current and current["model_identifier"] == model_identifier:
                return True, model_identifier
            time.sleep(2)
        return False, None

    def unload_all(self, timeout: int = 120) -> bool:
        current = self.current_model()
        if current is None:
            return self.is_available(timeout=10)
        # TabbyAPI returns HTTP 200 with JSON ``null`` and no useful body.
        response = self.request_json(
            "/model/unload",
            method="POST",
            payload={},
            headers=self._admin_headers,
            read_body=False,
        )
        if response is None:
            return False
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.current_model() is None:
                return True
            time.sleep(2)
        return False

    def wait_ready(self, timeout: int = 120) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.current_model() is not None:
                return True
            time.sleep(2)
        return False
