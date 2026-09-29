"""All final validation blockers must reach the pipeline exit status."""
from contextlib import ExitStack
from unittest.mock import patch

import pytest
import registry_tool as rt


BLOCKERS = (
    "local_companion_invalid", "local_config_pair_invalid", "template_missing_file",
    "identity_collision", "runtime_experts_missing", "runtime_experts_exceed_max",
    "config_experts_drift", "gguf_header_drift", "unknown_future_blocker",
)


def run_full(errors, ignore_drift=False):
    with ExitStack() as stack:
        stack.enter_context(patch.object(rt, "_collect_registry_inventory", return_value=rt.RegistryInventory({}, [], [], [], [])))
        for name in ("_ensure_gguf_inventory", "cmd_compare", "cmd_quarantine_missing", "cmd_sync", "classify_registry",
                     "cmd_sync_templates", "assemble_prompts", "validate_prompts"):
            stack.enter_context(patch.object(rt, name))
        stack.enter_context(patch.object(rt, "cmd_validate", return_value=errors))
        rt.cmd_pipeline("full", ignore_drift=ignore_drift)


@pytest.mark.parametrize("category", BLOCKERS)
@pytest.mark.parametrize("ignore_drift", [False, True])
def test_full_exits_on_every_open_blocker(category, ignore_drift):
    if ignore_drift and category in rt._DRIFT_CHECKS:
        run_full({category: ["violation"]}, ignore_drift=True)
    else:
        with pytest.raises(SystemExit) as error:
            run_full({category: ["violation"]}, ignore_drift=ignore_drift)
        assert error.value.code == 1


def test_advisories_do_not_block_full():
    run_full({key: ["advisory"] for key in rt._VALIDATION_ADVISORY_CHECKS})
