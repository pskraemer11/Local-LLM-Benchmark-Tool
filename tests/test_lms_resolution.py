"""Regression tests for the lms.exe resolution and the empty pre-push input."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import registry_tool as rt

REPO_ROOT = Path(__file__).resolve().parents[1]
PRIVACY_GATE = REPO_ROOT / "src" / "privacy_gate.py"


def _make_binary(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path


def test_lms_executables_prefers_the_application_binary(tmp_path: Path, monkeypatch: object) -> None:
    """The daemon bundle on the PATH hangs; the application binary answers."""
    home = tmp_path / "home"
    app_cli = _make_binary(
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Programs"
        / "LM Studio"
        / "resources"
        / "app"
        / ".webpack"
        / "lms.exe"
    )
    bin_cli = _make_binary(home / ".lmstudio" / "bin" / "lms.exe")
    daemon_cli = _make_binary(home / ".lmstudio" / "llmster" / "0.0.25-1" / ".bundle" / "lms.exe")
    staging_cli = _make_binary(home / ".lmstudio" / "llmster" / "bootstrap-staging" / "payload" / ".bundle" / "lms.exe")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))  # type: ignore[arg-type]
    monkeypatch.setattr(rt.shutil, "which", lambda name: None)  # type: ignore[arg-type]

    resolved = rt._lms_executables()

    assert resolved[0] == app_cli
    assert bin_cli in resolved
    assert daemon_cli in resolved
    assert staging_cli not in resolved


def test_lms_executables_deduplicates_the_path_copy(tmp_path: Path, monkeypatch: object) -> None:
    home = tmp_path / "home"
    daemon_cli = _make_binary(home / ".lmstudio" / "llmster" / "0.0.25-1" / ".bundle" / "lms.exe")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))  # type: ignore[arg-type]
    monkeypatch.setattr(rt.shutil, "which", lambda name: str(daemon_cli))  # type: ignore[arg-type]

    resolved = rt._lms_executables()

    assert resolved.count(daemon_cli) == 1


def test_pre_push_without_ref_updates_does_not_block(tmp_path: Path) -> None:
    """Git runs the hook even when nothing has to be pushed; stdin is then empty."""
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True, capture_output=True)

    result = subprocess.run(
        [sys.executable, str(PRIVACY_GATE), "pre-push"],
        cwd=tmp_path,
        input="",
        env={**os.environ, "PYTHONUTF8": "1"},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Nothing to push" in result.stdout
