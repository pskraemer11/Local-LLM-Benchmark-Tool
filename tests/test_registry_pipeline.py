"""Regression tests for the registry maintenance pipeline."""

import sys
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import registry_tool as rt


def test_cmd_sync_repairs_missing_quant_before_arch_sync() -> None:
    calls: list[str] = []

    def record(name: str) -> Callable[..., None]:
        def callback(*_args: object, **_kwargs: object) -> None:
            calls.append(name)

        return callback

    with (
        patch.object(rt, "_run_lms_ls", return_value=[]),
        patch.object(rt, "load_registry", return_value={}),
        patch.object(
            rt,
            "_collect_registry_inventory",
            return_value=rt.RegistryInventory({}, [], [], [], [], True),
        ),
        patch.object(rt, "cmd_fill_quant", side_effect=record("fill-quant")),
        patch.object(rt, "cmd_fill_arch", side_effect=record("fill-arch")),
        patch.object(rt, "cmd_sync_from_gguf", side_effect=record("sync-from-gguf")),
        patch.object(rt, "cmd_fill_reasoning", side_effect=record("fill-reasoning")),
        patch.object(rt, "cmd_sync_from_configs", side_effect=record("sync-from-configs")),
        patch.object(rt, "cmd_fill_size", side_effect=record("fill-size")),
        patch.object(rt, "cmd_compare"),
        patch.object(rt, "_research_missing_sampling") as research,
        patch.object(rt, "cmd_fmt", side_effect=record("fmt")),
    ):
        rt.cmd_sync()

    assert calls == [
        "fill-quant",
        "fill-arch",
        "sync-from-gguf",
        "fill-reasoning",
        "fill-size",
        "sync-from-configs",
        "fmt",
    ]
    research.assert_not_called()
