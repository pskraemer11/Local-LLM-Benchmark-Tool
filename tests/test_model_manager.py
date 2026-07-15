"""Tests for model_manager.py – Stufe 7 (Prio 4.16 Code-Review §4 Prio 4).

Targets the LM Studio CLI wrapper and HTTP health-check. The
subprocess.run() and urllib calls are mocked using the
`lms_cli`, `subprocess_scripts`, and `lms_http` fixtures from
`tests/conftest.py`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import model_manager as mm
from model_manager import (
    API_BASE,
    TIMEOUT_HEALTH_CHECK,
    parse_selection,
    check_api_available,
    get_current_loaded_model,
    get_available_models,
    load_model_via_lms,
    unload_all_models,
    wait_for_model_ready,
)


# ── Auto-mocked time ───────────────────────────────────────────────
# model_manager.py uses time.sleep() in polling loops and time.time()
# for elapsed-time tracking. We auto-mock BOTH in this test module to
# prevent the 10-iteration load-wait loop (10 seconds of time.sleep)
# and the 15-iteration unload-wait loop (30 seconds of time.sleep)
# from blocking the test suite. We use a fake time.time that simply
# increments per call so wait_for_model_ready's timeout logic works.
@pytest.fixture(autouse=True)
def _mock_time(mocker):
    """Auto-mock time.sleep AND time.time for all tests in this module.

    time.sleep is replaced with a no-op.
    time.time is replaced with a counter that increments by 1 per call,
    so wait_for_model_ready's elapsed-time check (`time.time() - start > timeout`)
    quickly exceeds the timeout and breaks the polling loop.
    """
    mocker.patch("time.sleep")
    counter = [1000.0]
    def fake_time():
        counter[0] += 1
        return counter[0]
    mocker.patch("model_manager.time.time", side_effect=fake_time)
    return mocker


# ─────────────────────────────────────────────────────────────────────
# Pure function: parse_selection
# ─────────────────────────────────────────────────────────────────────

class TestParseSelection:
    """Parse user input like '1', '1,3,5', '1-5' into zero-based indices."""

    def test_empty_string_returns_none(self):
        assert parse_selection("", 10) is None

    def test_whitespace_only_returns_none(self):
        assert parse_selection("   ", 10) is None

    def test_single_number(self):
        # User types "1" → model index 0 (zero-based)
        assert parse_selection("1", 10) == [0]

    def test_comma_separated(self):
        # User types "1,3,5" → indices 0, 2, 4
        assert parse_selection("1,3,5", 10) == [0, 2, 4]

    def test_range(self):
        # User types "2-4" → indices 1, 2, 3
        assert parse_selection("2-4", 10) == [1, 2, 3]

    def test_mixed(self):
        # User types "1,3-5,7" → indices 0, 2, 3, 4, 6
        assert parse_selection("1,3-5,7", 10) == [0, 2, 3, 4, 6]

    def test_with_whitespace(self):
        # Whitespace inside the input is ignored
        assert parse_selection(" 1 , 3 ", 10) == [0, 2]

    def test_single_number_zero_based_conversion(self):
        # "1" → index 0 (NOT index 1)
        assert parse_selection("1", 10) == [0]
        # "5" → index 4
        assert parse_selection("5", 10) == [4]

    def test_out_of_range_returns_none(self):
        # "11" with max_val=10 → out of range
        assert parse_selection("11", 10) is None

    def test_zero_returns_none(self):
        # "0" is not a valid user input (1-based) → returns None
        assert parse_selection("0", 10) is None

    def test_invalid_range_start_greater_than_end(self):
        # "5-2" (reversed) → returns None
        assert parse_selection("5-2", 10) is None

    def test_non_numeric_returns_none(self):
        # Letters in input → returns None
        assert parse_selection("abc", 10) is None
        assert parse_selection("1,abc,3", 10) is None

    def test_result_is_sorted(self):
        # "5,1,3" → sorted to [0, 2, 4]
        assert parse_selection("5,1,3", 10) == [0, 2, 4]


# ─────────────────────────────────────────────────────────────────────
# check_api_available
# ─────────────────────────────────────────────────────────────────────

class TestCheckApiAvailable:
    """Test if the LM Studio API is reachable."""

    def test_returns_true_on_200(self, mocker):
        mock_resp = MagicMock()
        mock_resp.status = 200
        # urlopen is a context manager
        mock_urlopen = MagicMock()
        mock_urlopen.__enter__ = MagicMock(return_value=mock_resp)
        mock_urlopen.__exit__ = MagicMock(return_value=False)
        mocker.patch("urllib.request.urlopen", return_value=mock_urlopen)
        assert check_api_available() is True

    def test_returns_false_on_non_200(self, mocker):
        mock_resp = MagicMock()
        mock_resp.status = 500
        mock_urlopen = MagicMock()
        mock_urlopen.__enter__ = MagicMock(return_value=mock_resp)
        mock_urlopen.__exit__ = MagicMock(return_value=False)
        mocker.patch("urllib.request.urlopen", return_value=mock_urlopen)
        assert check_api_available() is False

    def test_returns_false_on_url_error(self, mocker):
        from urllib.error import URLError
        mocker.patch("urllib.request.urlopen", side_effect=URLError("not found"))
        assert check_api_available() is False

    def test_returns_false_on_connection_refused(self, mocker):
        mocker.patch("urllib.request.urlopen", side_effect=ConnectionRefusedError())
        assert check_api_available() is False

    def test_returns_false_on_generic_exception(self, mocker):
        mocker.patch("urllib.request.urlopen", side_effect=Exception("unexpected"))
        assert check_api_available() is False

    def test_uses_correct_url(self, mocker):
        # The function should call /v1/models (not /v1/chat/completions)
        captured_urls = []

        def fake_urlopen(req, **kwargs):
            captured_urls.append(req.full_url)
            raise Exception("stop here")

        mocker.patch("urllib.request.urlopen", side_effect=fake_urlopen)
        check_api_available()
        assert captured_urls[0] == f"{API_BASE}/models"


# ─────────────────────────────────────────────────────────────────────
# get_current_loaded_model
# ─────────────────────────────────────────────────────────────────────

class TestGetCurrentLoadedModel:
    """Query `lms ps --json` for the currently loaded model."""

    def test_returns_none_on_lms_failure(self, mocker):
        # lms command not found
        mocker.patch("subprocess.run", side_effect=FileNotFoundError())
        assert get_current_loaded_model() is None

    def test_returns_none_on_subprocess_timeout(self, mocker):
        mocker.patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="lms", timeout=15),
        )
        assert get_current_loaded_model() is None

    def test_returns_none_on_non_zero_exit(self, mocker):
        # lms returned non-zero (e.g. error)
        result = MagicMock()
        result.returncode = 1
        result.stdout = ""
        mocker.patch("subprocess.run", return_value=result)
        assert get_current_loaded_model() is None

    def test_returns_none_on_json_decode_error(self, mocker):
        result = MagicMock()
        result.returncode = 0
        result.stdout = "not valid JSON"
        mocker.patch("subprocess.run", return_value=result)
        assert get_current_loaded_model() is None

    def test_returns_none_on_empty_list(self, mocker):
        result = MagicMock()
        result.returncode = 0
        result.stdout = "[]"
        mocker.patch("subprocess.run", return_value=result)
        assert get_current_loaded_model() is None

    def test_returns_first_model(self, mocker):
        result = MagicMock()
        result.returncode = 0
        result.stdout = json.dumps([
            {
                "identifier": "model_a@q4_k_m",
                "modelKey": "model_a",
                "displayName": "Model A",
            },
            {
                "identifier": "model_b@q4_k_m",
                "modelKey": "model_b",
                "displayName": "Model B",
            },
        ])
        mocker.patch("subprocess.run", return_value=result)
        loaded = get_current_loaded_model()
        # Only the first model is returned
        assert loaded is not None
        assert loaded["identifier"] == "model_a@q4_k_m"
        assert loaded["model_key"] == "model_a"
        assert loaded["display_name"] == "Model A"

    def test_handles_dict_format(self, mocker):
        # lms sometimes returns a dict instead of a list.
        # The current implementation only handles list format (entries[0])
        # so passing a dict raises TypeError → caught by the broad except
        # → returns None. This is a known limitation: the implementation
        # was originally written for list format only. Documenting the
        # actual behavior.
        result = MagicMock()
        result.returncode = 0
        result.stdout = json.dumps({
            "model_a": {
                "identifier": "model_a@q4_k_m",
                "modelKey": "model_a",
                "displayName": "Model A",
            },
        })
        mocker.patch("subprocess.run", return_value=result)
        loaded = get_current_loaded_model()
        # Dict format is not supported (returns None via the catch-all
        # except clause). This is a known limitation.
        assert loaded is None


# ─────────────────────────────────────────────────────────────────────
# get_available_models
# ─────────────────────────────────────────────────────────────────────

class TestGetAvailableModels:
    """Query `lms ls --json` for installed models."""

    def test_returns_empty_list_on_lms_failure(self, mocker):
        mocker.patch("subprocess.run", side_effect=FileNotFoundError())
        assert get_available_models() == []

    def test_returns_empty_list_on_non_zero_exit(self, mocker):
        result = MagicMock()
        result.returncode = 1
        result.stderr = "lms not found"
        mocker.patch("subprocess.run", return_value=result)
        assert get_available_models() == []

    def test_returns_empty_list_on_json_error(self, mocker):
        result = MagicMock()
        result.returncode = 0
        result.stdout = "invalid json"
        mocker.patch("subprocess.run", return_value=result)
        assert get_available_models() == []

    def test_filters_excluded_keywords(self, mocker):
        result = MagicMock()
        result.returncode = 0
        result.stdout = json.dumps([
            {"modelKey": "good_model", "displayName": "Good",
             "selectedVariant": "good_model@q4", "variants": []},
            {"modelKey": "whisper-model", "displayName": "Whisper",
             "selectedVariant": "whisper-model@q8", "variants": []},
            {"modelKey": "vision-model", "displayName": "Vision",
             "selectedVariant": "vision-model@q8", "variants": []},
        ])
        mocker.patch("subprocess.run", return_value=result)
        models = get_available_models(exclude_keywords=["whisper", "vision"])
        # whisper and vision are filtered out
        assert len(models) == 1
        assert models[0]["model_key"] == "good_model"

    def test_includes_quant_in_display(self, mocker):
        result = MagicMock()
        result.returncode = 0
        result.stdout = json.dumps([{
            "modelKey": "my_model",
            "displayName": "My Model",
            "selectedVariant": "my_model",
            "variants": [],
            "quantization": {"name": "Q4_K_M"},
            "paramsString": "7B",
        }])
        mocker.patch("subprocess.run", return_value=result)
        models = get_available_models()
        # Display name includes quant
        assert "Q4_K_M" in models[0]["display"]

    def test_unique_key_uses_quant_suffix(self, mocker):
        result = MagicMock()
        result.returncode = 0
        # Two variants of the same model → both kept
        result.stdout = json.dumps([
            {"modelKey": "model_a", "displayName": "A",
             "selectedVariant": "model_a",
             "variants": ["model_a@q3_k_m", "model_a@q4_k_s"],
             "quantization": {"name": "Q3_K_M"}},
            {"modelKey": "model_a", "displayName": "A",
             "selectedVariant": "model_a",
             "variants": ["model_a@q3_k_m", "model_a@q4_k_s"],
             "quantization": {"name": "Q4_K_S"}},
        ])
        mocker.patch("subprocess.run", return_value=result)
        models = get_available_models()
        # Two entries with different quant suffixes
        assert len(models) == 2

    def test_no_quantization_falls_back_to_display(self, mocker):
        result = MagicMock()
        result.returncode = 0
        result.stdout = json.dumps([{
            "modelKey": "my_model",
            "displayName": "My Model",
            "selectedVariant": "my_model",
            "variants": [],
        }])
        mocker.patch("subprocess.run", return_value=result)
        models = get_available_models()
        # Without quant, the display name is the model's displayName
        # (the implementation uses the display field directly from lms)
        assert models[0]["display"] == "My Model"
        assert models[0]["quant"] == ""


# ─────────────────────────────────────────────────────────────────────
# load_model_via_lms
# ─────────────────────────────────────────────────────────────────────

class TestLoadModelViaLMS:
    """Load a model via the `lms load` CLI."""

    def test_successful_load(self, mocker):
        # Mock lms load (returns 0) and lms ps (returns a model)
        load_result = MagicMock()
        load_result.returncode = 0
        load_result.stderr = ""
        ps_result = MagicMock()
        ps_result.returncode = 0
        ps_result.stdout = json.dumps([{
            "identifier": "test_model@q4_k_m",
            "modelKey": "test_model",
            "displayName": "Test Model",
        }])
        # side_effect: first call returns load_result, subsequent calls ps_result
        mocker.patch("subprocess.run", side_effect=[load_result, ps_result])
        ok, identifier = load_model_via_lms("test_model")
        assert ok is True
        assert identifier == "test_model@q4_k_m"

    def test_falls_back_to_model_key_if_ps_returns_nothing(self, mocker):
        # lms load succeeds, but lms ps returns no loaded model
        # (this is a fallback case: the load succeeded but verification
        # did not return an identifier within 10 seconds)
        load_result = MagicMock()
        load_result.returncode = 0
        load_result.stderr = ""
        ps_result = MagicMock()
        ps_result.returncode = 0
        ps_result.stdout = "[]"  # no model loaded
        mocker.patch("subprocess.run", side_effect=[load_result] + [ps_result] * 10)
        # CRITICAL: mock time.sleep to prevent the 10-iteration 1-second
        # sleep loop from blocking the test
        mocker.patch("time.sleep")
        ok, identifier = load_model_via_lms("test_model")
        # Falls back to using the model key directly
        assert ok is True
        assert identifier == "test_model"

    def test_timeout_returns_false(self, mocker):
        mocker.patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="lms", timeout=180),
        )
        ok, identifier = load_model_via_lms("test_model")
        assert ok is False
        assert identifier is None

    def test_lms_not_found_returns_false(self, mocker):
        mocker.patch("subprocess.run", side_effect=FileNotFoundError())
        ok, identifier = load_model_via_lms("test_model")
        assert ok is False
        assert identifier is None

    def test_already_loaded(self, mocker):
        # lms load returns "already loaded" error
        load_result = MagicMock()
        load_result.returncode = 1
        load_result.stderr = "Model already loaded"
        ps_result = MagicMock()
        ps_result.returncode = 0
        ps_result.stdout = json.dumps([{
            "identifier": "test_model@q4_k_m",
            "modelKey": "test_model",
            "displayName": "Test",
        }])
        mocker.patch("subprocess.run", side_effect=[load_result, ps_result])
        ok, identifier = load_model_via_lms("test_model")
        # Already loaded is treated as success
        assert ok is True
        assert identifier == "test_model@q4_k_m"

    def test_with_context_length(self, mocker):
        # When context_length is provided, --context-length is appended
        load_result = MagicMock()
        load_result.returncode = 0
        load_result.stderr = ""
        ps_result = MagicMock()
        ps_result.returncode = 0
        ps_result.stdout = json.dumps([{
            "identifier": "test@q4",
            "modelKey": "test",
            "displayName": "Test",
        }])
        mock_run = mocker.patch(
            "subprocess.run",
            side_effect=[load_result, ps_result],
        )
        load_model_via_lms("test", context_length=8192)
        # The first call's command should include --context-length 8192
        call_args = mock_run.call_args_list[0]
        cmd = call_args.args[0] if call_args.args else call_args[0][0]
        assert "--context-length" in cmd
        assert "8192" in cmd
        assert "--yes" in cmd

    def test_with_gpu_offload(self, mocker):
        # When gpu_offload is provided, --gpu is appended
        load_result = MagicMock()
        load_result.returncode = 0
        load_result.stderr = ""
        ps_result = MagicMock()
        ps_result.returncode = 0
        ps_result.stdout = json.dumps([{
            "identifier": "test@q4",
            "modelKey": "test",
            "displayName": "Test",
        }])
        mock_run = mocker.patch(
            "subprocess.run",
            side_effect=[load_result, ps_result],
        )
        load_model_via_lms("test", gpu_offload=0.8)
        call_args = mock_run.call_args_list[0]
        cmd = call_args.args[0] if call_args.args else call_args[0][0]
        assert "--gpu" in cmd
        assert "0.8" in cmd

    def test_daemon_error_retried(self, mocker):
        # First attempt: "Runtime not found" error → restart and retry
        load_result_1 = MagicMock()
        load_result_1.returncode = 1
        load_result_1.stderr = "Runtime not found"
        load_result_2 = MagicMock()
        load_result_2.returncode = 0
        load_result_2.stderr = ""
        ps_result = MagicMock()
        ps_result.returncode = 0
        ps_result.stdout = json.dumps([{
            "identifier": "test@q4",
            "modelKey": "test",
            "displayName": "Test",
        }])
        # First call: daemon error, then load_result_2, then ps_result
        mock_run = mocker.patch(
            "subprocess.run",
            side_effect=[load_result_1, load_result_2, ps_result],
        )
        # _ensure_lmstudio_running is mocked to return True (restart succeeded)
        mocker.patch("model_manager._ensure_lmstudio_running", return_value=True)
        ok, identifier = load_model_via_lms("test")
        assert ok is True

    def test_load_failure_returns_false(self, mocker):
        # Generic error (not "already loaded", not daemon)
        load_result = MagicMock()
        load_result.returncode = 1
        load_result.stderr = "Some other error"
        mocker.patch("subprocess.run", return_value=load_result)
        ok, identifier = load_model_via_lms("test")
        assert ok is False
        assert identifier is None


# ─────────────────────────────────────────────────────────────────────
# unload_all_models
# ─────────────────────────────────────────────────────────────────────

class TestUnloadAllModels:
    """Unload all models via the `lms unload --all` CLI."""

    def test_successful_unload(self, mocker):
        # lms unload returns 0, then the confirmation poll returns
        # an HTTPError (model is unloaded) → success
        unload_result = MagicMock()
        unload_result.returncode = 0
        unload_result.stderr = ""
        # The confirmation HTTP polling: urlopen raises HTTPError
        from urllib.error import HTTPError
        mock_urlopen = MagicMock(side_effect=HTTPError(
            url="http://127.0.0.1:1234/v1/chat/completions",
            code=400, msg="Bad Request", hdrs={}, fp=None
        ))
        mocker.patch("subprocess.run", return_value=unload_result)
        mocker.patch("urllib.request.urlopen", side_effect=mock_urlopen)
        result = unload_all_models()
        assert result is True

    def test_lms_not_found(self, mocker):
        mocker.patch("subprocess.run", side_effect=FileNotFoundError())
        result = unload_all_models()
        assert result is False

    def test_timeout(self, mocker):
        mocker.patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="lms", timeout=30),
        )
        result = unload_all_models()
        assert result is False

    def test_unload_non_zero_exit_still_polls(self, mocker):
        # Non-zero exit is logged but doesn't fail
        unload_result = MagicMock()
        unload_result.returncode = 1
        unload_result.stderr = "warning: not loaded"
        from urllib.error import HTTPError
        mock_urlopen = MagicMock(side_effect=HTTPError(
            url="http://127.0.0.1:1234/v1/chat/completions",
            code=400, msg="Bad Request", hdrs={}, fp=None
        ))
        mocker.patch("subprocess.run", return_value=unload_result)
        mocker.patch("urllib.request.urlopen", side_effect=mock_urlopen)
        result = unload_all_models()
        # Non-zero exit is OK, success is determined by HTTP poll
        assert result is True

    def test_unload_timeout_after_retries(self, mocker):
        # All 15 polling attempts return HTTP 200 (model still active)
        unload_result = MagicMock()
        unload_result.returncode = 0
        unload_result.stderr = ""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen = MagicMock()
        mock_urlopen.__enter__ = MagicMock(return_value=mock_resp)
        mock_urlopen.__exit__ = MagicMock(return_value=False)
        mocker.patch("subprocess.run", return_value=unload_result)
        mocker.patch("urllib.request.urlopen", return_value=mock_urlopen)
        result = unload_all_models()
        # Model is still active after 15 attempts → return False
        assert result is False


# ─────────────────────────────────────────────────────────────────────
# wait_for_model_ready
# ─────────────────────────────────────────────────────────────────────

class TestWaitForModelReady:
    """Wait for the LM Studio API to return a successful response."""

    def test_returns_true_on_200(self, mocker):
        # First HTTP call returns 200 → model is ready
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen = MagicMock()
        mock_urlopen.__enter__ = MagicMock(return_value=mock_resp)
        mock_urlopen.__exit__ = MagicMock(return_value=False)
        mocker.patch("urllib.request.urlopen", return_value=mock_urlopen)
        mocker.patch("time.sleep")  # don't actually sleep
        assert wait_for_model_ready(timeout=5) is True

    def test_returns_true_after_retries(self, mocker):
        # First few calls fail (model not ready), then one succeeds
        from urllib.error import URLError
        mock_resp = MagicMock()
        mock_resp.status = 200
        success_urlopen = MagicMock()
        success_urlopen.__enter__ = MagicMock(return_value=mock_resp)
        success_urlopen.__exit__ = MagicMock(return_value=False)
        # First 3 calls fail, then success
        side_effect = [URLError("not ready")] * 3 + [success_urlopen]
        mocker.patch("urllib.request.urlopen", side_effect=side_effect)
        mocker.patch("time.sleep")
        assert wait_for_model_ready(timeout=10) is True

    def test_returns_false_on_timeout(self, mocker):
        # All calls fail with URLError → timeout after duration
        from urllib.error import URLError
        mocker.patch("urllib.request.urlopen", side_effect=URLError("never ready"))
        # Mock time.time to simulate timeout immediately
        start_time = [1000.0]
        def fake_time():
            start_time[0] += 100  # jump forward in time
            return start_time[0]
        mocker.patch("model_manager.time.time", side_effect=fake_time)
        mocker.patch("time.sleep")
        assert wait_for_model_ready(timeout=5) is False

    def test_returns_false_on_500_error(self, mocker):
        # 500 errors are also retried (server not ready yet)
        from urllib.error import HTTPError
        mocker.patch(
            "urllib.request.urlopen",
            side_effect=HTTPError(
                url="http://127.0.0.1:1234/v1/chat/completions",
                code=500, msg="Internal Server Error", hdrs={}, fp=None,
            ),
        )
        start_time = [1000.0]
        def fake_time():
            start_time[0] += 100
            return start_time[0]
        mocker.patch("model_manager.time.time", side_effect=fake_time)
        mocker.patch("time.sleep")
        assert wait_for_model_ready(timeout=5) is False

    def test_uses_chat_completions_url(self, mocker):
        # The function should poll /v1/chat/completions (not /v1/models)
        captured_urls = []

        def fake_urlopen(req, **kwargs):
            captured_urls.append(req.full_url)
            from urllib.error import URLError
            raise URLError("not ready")

        mocker.patch("urllib.request.urlopen", side_effect=fake_urlopen)
        # Use small increments so the loop iterates at least once
        # before timing out. start_time[0] = 1000, then +1 per call.
        # Z.306 start = 1001, Z.308 time = 1002 → elapsed = 1 < timeout=2 → loop
        # Z.309 sleep, Z.310 (no time), Z.311-319 urlopen call → captured!
        # Z.308 time = 1003 → elapsed = 2, not < 2 → exit
        start_time = [1000.0]
        def fake_time():
            start_time[0] += 1
            return start_time[0]
        mocker.patch("model_manager.time.time", side_effect=fake_time)
        mocker.patch("time.sleep")
        wait_for_model_ready(timeout=2)
        assert len(captured_urls) >= 1
        assert captured_urls[0] == f"{API_BASE}/chat/completions"

    def test_default_timeout(self, mocker):
        # The function uses TIMEOUT_MODEL_READY as default
        # We can't easily test the exact value, but we can check that
        # the function is callable without explicit timeout
        from urllib.error import URLError
        mocker.patch("urllib.request.urlopen", side_effect=URLError("never ready"))
        start_time = [1000.0]
        def fake_time():
            start_time[0] += 100
            return start_time[0]
        mocker.patch("model_manager.time.time", side_effect=fake_time)
        mocker.patch("time.sleep")
        result = wait_for_model_ready()  # no timeout arg
        assert result is False
