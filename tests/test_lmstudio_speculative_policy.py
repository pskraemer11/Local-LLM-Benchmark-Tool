"""Explicit speculative policies need effective, identity-bound load evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from model_registry import ModelRegistry
from providers.lmstudio_provider import LMStudioProvider
from speculative import lms_speculative_values

IDENTITY = "publisher/model@q6_k"
HELPER = "publisher/draft@q4_k_m"
FLAGS = ("draft_mtp", "draft_simple", "draft_dflash_sidecar", "draft_dspark_sidecar", "draft_mtp_sidecar")


def _disabled() -> dict[str, Any]:
    return {**dict.fromkeys(FLAGS, False), "draft_model_reference": ""}


def _provider(
    expected: dict[str, Any] | None,
    *,
    echo: dict[str, Any] | None = None,
    instance_config: dict[str, Any] | None = None,
    status: str = "loaded",
    identity: str = IDENTITY,
) -> tuple[LMStudioProvider, list[dict[str, Any]]]:
    payloads: list[dict[str, Any]] = []

    def request(endpoint: str, **kwargs: Any) -> dict[str, Any]:
        if endpoint.endswith("/load"):
            payloads.append(kwargs["data"])
            result: dict[str, Any] = {"status": status, "instance_id": "session-42"}
            if echo is not None:
                result["load_config"] = echo
            return result
        return {"models": [{"key": identity, "loaded_instances": [{"id": "session-42", "config": instance_config}]}]}

    runtime = {"_registry_key": IDENTITY}
    if expected is not None:
        runtime["_speculative_expected"] = expected
    return LMStudioProvider(
        "http://127.0.0.1:1234/v1", rest_request=request, runtime_loader=lambda _model: runtime
    ), payloads


@pytest.mark.parametrize("policy", ["disabled", "registry", "lmstudio"])
def test_registry_transports_policy_without_rest_fields(policy: str) -> None:
    entry = {
        "speculative_policy": policy,
        "local": {"llama_cpp": {"speculative": {"type": "draft", "method": "simple"}}, "companions": {"draft": HELPER}},
    }
    resolved = ModelRegistry(lambda: {IDENTITY: entry}).resolve(IDENTITY)
    assert resolved is not None
    runtime = resolved.provider_runtime("lmstudio")
    assert runtime.get("_speculative_expected") == lms_speculative_values(entry)
    assert not any(key in runtime for key in FLAGS)


@pytest.mark.parametrize("flag", FLAGS)
def test_disabled_rejects_each_active_algorithm(flag: str) -> None:
    provider, _ = _provider(_disabled(), echo={flag: True, "draft_model_reference": HELPER})
    assert provider.load_model(IDENTITY) == (False, None)


@pytest.mark.parametrize("echo", [None, {}, {"draft_simple": False}, {**_disabled(), "draft_simple": "false"}])
def test_disabled_rejects_missing_or_malformed_effective_evidence(echo: dict[str, Any] | None) -> None:
    provider, _ = _provider(_disabled(), echo=echo)
    assert provider.load_model(IDENTITY) == (False, None)


def test_disabled_accepts_complete_echo_without_sending_unsupported_fields() -> None:
    provider, payloads = _provider(_disabled(), echo=_disabled())
    assert provider.load_model(IDENTITY) == (True, "session-42")
    assert payloads == [{"model": IDENTITY, "echo_load_config": True}]


@pytest.mark.parametrize("status", ["loaded", "error"])
def test_loaded_instance_can_prove_policy_for_load_and_reuse(status: str) -> None:
    provider, _ = _provider(_disabled(), instance_config=_disabled(), status=status)
    assert provider.load_model(IDENTITY) == (True, "session-42")


@pytest.mark.parametrize("status", ["loaded", "error"])
def test_active_instance_is_never_overruled_by_saved_or_echoed_disabled_policy(status: str) -> None:
    provider, _ = _provider(
        _disabled(), echo=_disabled(), instance_config={"draft_simple": True, "draft_model_reference": HELPER}, status=status
    )
    assert provider.load_model(IDENTITY) == (False, None)


@pytest.mark.parametrize("observed", ["other/draft@q4_k_m", "publisher/draft@q6_k", "publisher/draft"])
def test_explicit_drafter_preserves_full_helper_identity(observed: str) -> None:
    expected = {**_disabled(), "draft_simple": True, "draft_model_reference": HELPER}
    provider, _ = _provider(expected, echo={**expected, "draft_model_reference": observed})
    assert provider.load_model(IDENTITY) == (False, None)


def test_explicit_drafter_checks_algorithm_and_helper_and_limits() -> None:
    expected = {**_disabled(), "draft_dspark_sidecar": True, "draft_model_reference": HELPER, "draft_n_max": 4}
    provider, _ = _provider(expected, echo=expected)
    assert provider.load_model(IDENTITY) == (True, "session-42")
    for changed in ({"draft_dspark_sidecar": False, "draft_simple": True}, {"draft_n_max": 8}):
        provider, _ = _provider(expected, echo={**expected, **changed})
        assert provider.load_model(IDENTITY) == (False, None)


def test_evidence_from_another_main_quantization_cannot_prove_policy() -> None:
    provider, _ = _provider(_disabled(), echo=_disabled(), instance_config=_disabled(), identity="publisher/model@q4_k_m")
    assert provider.load_model(IDENTITY) == (False, None)


@pytest.mark.parametrize("effective", [None, _disabled(), {"draft_simple": True, "draft_model_reference": HELPER}])
def test_default_lmstudio_policy_keeps_legacy_load_behavior(effective: dict[str, Any] | None) -> None:
    provider, _ = _provider(None, echo=effective)
    assert provider.load_model(IDENTITY) == (True, "session-42")


@pytest.mark.parametrize("effective", [None, _disabled(), {"draft_simple": True, "draft_model_reference": HELPER}])
def test_current_model_cannot_reuse_an_unverified_explicit_policy(effective: dict[str, Any] | None) -> None:
    provider, _ = _provider(_disabled(), instance_config=effective)
    current = provider.current_model()
    assert current is not None
    assert current["runtime_matches"] is (effective == _disabled())


def test_effective_native_key_names_are_verified_without_rest_overrides() -> None:
    aliases = ("draftMtp", "draftSimple", "draftDflashSidecar", "draftDsparkSidecar", "draftMtpSidecar")
    echo = {f"llm.load.llama.speculativeDecoding.{name}": False for name in aliases}
    echo["llm.load.llama.speculativeDecoding.draftModel"] = ""
    provider, _ = _provider(_disabled(), echo=echo)
    assert provider.load_model(IDENTITY) == (True, "session-42")


def test_contradictory_native_and_normalized_flags_are_not_collapsed() -> None:
    echo = {**_disabled(), "llm.load.llama.speculativeDecoding.draftSimple": True}
    provider, _ = _provider(_disabled(), echo=echo)
    assert provider.load_model(IDENTITY) == (False, None)


@pytest.mark.parametrize("enabled,numeric", [(False, 0), (True, 1)])
def test_numeric_alias_cannot_prove_a_boolean_flag(enabled: bool, numeric: int) -> None:
    expected = {**_disabled(), "draft_simple": enabled, "draft_model_reference": HELPER if enabled else ""}
    echo = {**expected, "llm.load.llama.speculativeDecoding.draftSimple": numeric}
    provider, _ = _provider(expected, echo=echo)
    assert provider.load_model(IDENTITY) == (False, None)


def test_complete_evidence_may_be_split_between_echo_and_bound_instance() -> None:
    provider, _ = _provider(_disabled(), echo={"draft_model_reference": ""}, instance_config=dict.fromkeys(FLAGS, False))
    assert provider.load_model(IDENTITY) == (True, "session-42")


def test_stale_helper_reference_is_not_disabled() -> None:
    provider, _ = _provider(_disabled(), echo={**_disabled(), "draft_model_reference": HELPER})
    assert provider.load_model(IDENTITY) == (False, None)


def test_physical_helper_path_requires_the_exact_artifact(tmp_path: Path) -> None:
    helper = str(tmp_path / "draft-Q4_K_M.gguf")
    expected = {**_disabled(), "draft_simple": True, "draft_model_reference": helper}
    provider, _ = _provider(expected, echo=expected)
    assert provider.load_model(IDENTITY) == (True, "session-42")
    for actual in (str(tmp_path / "other" / "draft-Q4_K_M.gguf"), "draft-Q4_K_M.gguf", HELPER):
        provider, _ = _provider(expected, echo={**expected, "draft_model_reference": actual})
        assert provider.load_model(IDENTITY) == (False, None)


def test_context_mismatch_remains_blocking_when_speculation_is_proven() -> None:
    provider, _ = _provider(_disabled(), instance_config={**_disabled(), "context_length": 1024})
    provider._runtime_loader = lambda _model: {"_registry_key": IDENTITY, "_speculative_expected": _disabled(), "context_length": 2048}
    current = provider.current_model()
    assert current is not None
    assert current["runtime_matches"] is False
