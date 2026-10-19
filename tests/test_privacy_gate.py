"""Regression tests for the commit/push privacy gate."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from src.privacy_gate import contains_private_profile_path, contains_prohibited_email

REPO_ROOT = Path(__file__).resolve().parents[1]
PRIVACY_GATE = REPO_ROOT / "src" / "privacy_gate.py"


def test_detects_concrete_windows_profile_paths_without_echoing_them() -> None:
    private_path = "C:" + "\\Users\\" + "SyntheticUser" + "\\Documents\\notes.txt"

    assert contains_private_profile_path(f"Example path: {private_path}")
    assert contains_private_profile_path(private_path.replace("\\", "/"))
    portable_style_path = "/" + "mnt/c/" + "Users/" + "SyntheticUser" + "/Documents/notes.txt"
    assert contains_private_profile_path(portable_style_path)


def test_allows_portable_or_placeholder_paths() -> None:
    assert not contains_private_profile_path("$HOME\\Documents\\notes.txt")
    assert not contains_private_profile_path("C:\\Users\\<username>\\Documents")
    assert not contains_private_profile_path("C:\\Users\\Public\\Documents")


@pytest.mark.parametrize("domain", ["online.de", "e-mail.de", "posteo.de"])
def test_detects_prohibited_commit_email_domain_case_insensitively(domain: str) -> None:
    prohibited = "synthetic-identity@" + domain
    assert contains_prohibited_email(prohibited)
    assert contains_prohibited_email(prohibited.upper())
    assert not contains_prohibited_email("dev" + "@example.org")
    assert not contains_prohibited_email("synthetic" + "@example.com")


@pytest.mark.parametrize("domain", ["e-mail.de", "posteo.de"])
def test_commit_message_cli_blocks_prohibited_domain_without_echoing_it(tmp_path: Path, domain: str) -> None:
    message_file = tmp_path / "COMMIT_EDITMSG"
    message_file.write_text("docs: update policy\nContact: " + "synthetic-identity@" + domain, encoding="utf-8")

    result = _run_gate(tmp_path, "check-message", args=(str(message_file),))

    assert result.returncode != 0
    assert "commit message" in result.stdout
    assert "synthetic-identity" not in result.stdout + result.stderr


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> None:
    process_env = os.environ.copy()
    if env is not None:
        process_env.update(env)
    subprocess.run(
        ["git", *args],
        cwd=repo,
        env=process_env,
        check=True,
        capture_output=True,
        text=True,
    )


def _run_gate(
    repo: Path,
    mode: str,
    *,
    args: tuple[str, ...] = (),
    stdin: str = "",
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, str(PRIVACY_GATE), mode, *args],
        cwd=repo,
        input=stdin,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_pre_commit_blocks_staged_profile_path_without_printing_it(tmp_path: Path) -> None:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.name", "Synthetic Contributor")
    _git(tmp_path, "config", "user.email", "clean" + "@example.org")
    private_path = "C:" + "\\Users\\" + "SyntheticUser" + "\\private.txt"
    staged_file = tmp_path / "example.md"
    staged_file.write_text(f"Do not publish: {private_path}\n", encoding="utf-8")
    _git(tmp_path, "add", "example.md")

    result = _run_gate(tmp_path, "pre-commit")

    assert result.returncode != 0
    assert "Windows user-profile path" in result.stdout
    assert "SyntheticUser" not in result.stdout + result.stderr


@pytest.mark.parametrize("domain", ["online.de", "e-mail.de", "posteo.de"])
def test_pre_commit_blocks_author_identity_with_prohibited_domain(tmp_path: Path, domain: str) -> None:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.name", "Synthetic Contributor")
    _git(tmp_path, "config", "user.email", "synthetic-identity@" + domain)

    result = _run_gate(tmp_path, "pre-commit")

    assert result.returncode != 0
    assert "commit author/committer identity" in result.stdout
    assert "synthetic-identity" not in result.stdout + result.stderr


def test_pre_commit_blocks_committer_environment_override(tmp_path: Path) -> None:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.name", "Synthetic Contributor")
    _git(tmp_path, "config", "user.email", "clean" + "@example.org")
    env = os.environ.copy()
    env["GIT_COMMITTER_EMAIL"] = "synthetic-identity@" + "online.de"

    result = subprocess.run(
        [sys.executable, str(PRIVACY_GATE), "pre-commit"],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "commit author/committer identity" in result.stdout
    assert "synthetic-identity" not in result.stdout + result.stderr


@pytest.mark.parametrize("domain", ["e-mail.de", "posteo.de"])
def test_pre_commit_blocks_prohibited_email_in_added_text(tmp_path: Path, domain: str) -> None:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.name", "Synthetic Contributor")
    _git(tmp_path, "config", "user.email", "clean" + "@example.org")
    (tmp_path / "notes.md").write_text("Contact: synthetic-identity@" + domain + "\n", encoding="utf-8")
    _git(tmp_path, "add", "notes.md")

    result = _run_gate(tmp_path, "pre-commit")

    assert result.returncode != 0
    assert "added content" in result.stdout
    assert "synthetic-identity" not in result.stdout + result.stderr


@pytest.mark.parametrize("domain", ["online.de", "e-mail.de", "posteo.de"])
def test_pre_push_blocks_prohibited_identity_in_outgoing_commit(tmp_path: Path, domain: str) -> None:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.name", "Synthetic Contributor")
    _git(tmp_path, "config", "user.email", "clean" + "@example.org")
    (tmp_path / "file.txt").write_text("safe\n", encoding="utf-8")
    _git(tmp_path, "add", "file.txt")
    commit_env = os.environ.copy()
    commit_env["GIT_AUTHOR_EMAIL"] = "clean" + "@example.org"
    commit_env["GIT_COMMITTER_EMAIL"] = "synthetic-identity@" + domain
    _git(tmp_path, "commit", "--quiet", "-m", "docs: synthetic test commit", env=commit_env)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    zero_sha = "0" * len(commit)
    pre_push_input = f"refs/heads/main {commit} refs/heads/main {zero_sha}\n"

    result = _run_gate(tmp_path, "pre-push", stdin=pre_push_input)

    assert result.returncode != 0
    assert "outgoing commit author/committer metadata" in result.stdout
    assert "synthetic-identity" not in result.stdout + result.stderr


def test_pre_push_blocks_profile_path_added_in_outgoing_commit(tmp_path: Path) -> None:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.name", "Synthetic Contributor")
    _git(tmp_path, "config", "user.email", "clean" + "@example.org")
    private_path = "C:" + "\\Users\\" + "SyntheticUser" + "\\private.txt"
    (tmp_path / "file.txt").write_text(f"Do not publish: {private_path}\n", encoding="utf-8")
    _git(tmp_path, "add", "file.txt")
    _git(tmp_path, "commit", "--quiet", "-m", "docs: synthetic test commit")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    zero_sha = "0" * len(commit)
    pre_push_input = f"refs/heads/main {commit} refs/heads/main {zero_sha}\n"

    result = _run_gate(tmp_path, "pre-push", stdin=pre_push_input)

    assert result.returncode != 0
    assert "Windows user-profile path" in result.stdout
    assert "SyntheticUser" not in result.stdout + result.stderr


def test_ci_commit_range_blocks_prohibited_email_in_added_text(tmp_path: Path) -> None:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.name", "Synthetic Contributor")
    _git(tmp_path, "config", "user.email", "clean" + "@example.org")
    (tmp_path / "notes.md").write_text("Safe text\n", encoding="utf-8")
    _git(tmp_path, "add", "notes.md")
    _git(tmp_path, "commit", "--quiet", "-m", "docs: synthetic base")
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()

    (tmp_path / "notes.md").write_text("Contact: " + "synthetic-identity@" + "posteo.de\n", encoding="utf-8")
    _git(tmp_path, "add", "notes.md")
    _git(tmp_path, "commit", "--quiet", "-m", "docs: synthetic follow-up")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()

    result = _run_gate(tmp_path, "check-range", args=(base, head))

    assert result.returncode != 0
    assert "added content" in result.stdout
    assert "synthetic-identity" not in result.stdout + result.stderr


def test_ci_commit_range_blocks_prohibited_email_in_commit_message(tmp_path: Path) -> None:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.name", "Synthetic Contributor")
    _git(tmp_path, "config", "user.email", "clean" + "@example.org")
    (tmp_path / "file.txt").write_text("safe\n", encoding="utf-8")
    _git(tmp_path, "add", "file.txt")
    _git(tmp_path, "commit", "--quiet", "-m", "docs: synthetic base")
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()

    (tmp_path / "file.txt").write_text("safe follow-up\n", encoding="utf-8")
    _git(tmp_path, "add", "file.txt")
    message = "docs: follow-up " + "synthetic-identity@" + "posteo.de"
    _git(tmp_path, "commit", "--quiet", "-m", message)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()

    result = _run_gate(tmp_path, "check-range", args=(base, head))

    assert result.returncode != 0
    assert "commit message" in result.stdout
    assert "synthetic-identity" not in result.stdout + result.stderr


def test_pre_push_blocks_prohibited_email_in_outgoing_content(tmp_path: Path) -> None:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.name", "Synthetic Contributor")
    _git(tmp_path, "config", "user.email", "clean" + "@example.org")
    (tmp_path / "notes.md").write_text("Contact: " + "synthetic-identity@" + "e-mail.de\n", encoding="utf-8")
    _git(tmp_path, "add", "notes.md")
    _git(tmp_path, "commit", "--quiet", "-m", "docs: synthetic privacy test")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    zero_sha = "0" * len(commit)

    result = _run_gate(
        tmp_path,
        "pre-push",
        stdin=f"refs/heads/main {commit} refs/heads/main {zero_sha}\n",
    )

    assert result.returncode != 0
    assert "added content" in result.stdout
    assert "synthetic-identity" not in result.stdout + result.stderr


@pytest.mark.parametrize("workflow", ["ci.yml", "review.yml"])
def test_github_workflows_run_history_aware_privacy_gate(workflow: str) -> None:
    workflow_text = (REPO_ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")

    assert "fetch-depth: 0" in workflow_text
    assert "check-range" in workflow_text
    assert "github.event.pull_request.base.sha" in workflow_text
    assert "github.event.pull_request.head.sha" in workflow_text


def test_pre_push_checks_only_commits_not_already_on_remote(tmp_path: Path) -> None:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.name", "Synthetic Contributor")
    _git(tmp_path, "config", "user.email", "synthetic-identity@" + "online.de")
    (tmp_path / "file.txt").write_text("legacy commit\n", encoding="utf-8")
    _git(tmp_path, "add", "file.txt")
    _git(tmp_path, "commit", "--quiet", "-m", "docs: synthetic legacy commit")
    legacy_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()

    _git(tmp_path, "config", "user.email", "clean" + "@example.org")
    (tmp_path / "file.txt").write_text("new clean commit\n", encoding="utf-8")
    _git(tmp_path, "add", "file.txt")
    _git(tmp_path, "commit", "--quiet", "-m", "docs: clean follow-up")
    local_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    pre_push_input = f"refs/heads/main {local_commit} refs/heads/main {legacy_commit}\n"

    result = _run_gate(tmp_path, "pre-push", stdin=pre_push_input)

    assert result.returncode == 0


def _copy_hook_runtime(destination: Path, hook_name: str) -> Path:
    hook_directory = destination / ".githooks"
    source_directory = destination / "src"
    hook_directory.mkdir()
    source_directory.mkdir()
    shutil.copy2(REPO_ROOT / ".githooks" / hook_name, hook_directory / hook_name)
    shutil.copy2(REPO_ROOT / "src" / "privacy_gate.py", source_directory / "privacy_gate.py")
    return hook_directory / hook_name


def _run_powershell_hook(
    script: Path,
    *,
    args: tuple[str, ...] = (),
    stdin: str = "",
) -> subprocess.CompletedProcess[str] | None:
    powershell = shutil.which("pwsh")
    if powershell is None:
        return None
    return subprocess.run(
        [
            powershell,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            *args,
        ],
        cwd=script.parents[1],
        input=stdin,
        check=False,
        capture_output=True,
        text=True,
    )


def test_powershell_pre_commit_hook_runs_privacy_gate_first(tmp_path: Path) -> None:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.name", "Synthetic Contributor")
    _git(tmp_path, "config", "user.email", "synthetic-identity@" + "online.de")
    hook = _copy_hook_runtime(tmp_path, "pre_commit.ps1")

    result = _run_powershell_hook(hook)

    if result is None:
        import pytest

        pytest.skip("PowerShell 7 is unavailable")
    assert result.returncode != 0
    assert "commit author/committer identity" in result.stdout
    assert "synthetic-identity" not in result.stdout + result.stderr


def test_powershell_commit_msg_hook_blocks_prohibited_domain(tmp_path: Path) -> None:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.name", "Synthetic Contributor")
    _git(tmp_path, "config", "user.email", "clean" + "@example.org")
    hook_directory = tmp_path / ".githooks"
    source_directory = tmp_path / "src"
    hook_directory.mkdir()
    source_directory.mkdir()
    shutil.copy2(REPO_ROOT / ".githooks" / "commit_msg.ps1", hook_directory / "commit_msg.ps1")
    shutil.copy2(REPO_ROOT / "src" / "privacy_gate.py", source_directory / "privacy_gate.py")
    message_file = tmp_path / ".git" / "COMMIT_EDITMSG"
    message_file.write_text("docs: update policy\nContact: " + "synthetic-identity@" + "e-mail.de\n", encoding="utf-8")

    result = _run_powershell_hook(hook_directory / "commit_msg.ps1", args=(str(message_file),))

    if result is None:
        pytest.skip("PowerShell 7 is unavailable")
    assert result.returncode != 0
    assert "prohibited personal email domain" in result.stdout
    assert "synthetic-identity" not in result.stdout + result.stderr


def test_powershell_pre_push_hook_forwards_git_ref_input(tmp_path: Path) -> None:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.name", "Synthetic Contributor")
    _git(tmp_path, "config", "user.email", "synthetic-identity@" + "online.de")
    (tmp_path / "file.txt").write_text("safe\n", encoding="utf-8")
    _git(tmp_path, "add", "file.txt")
    _git(tmp_path, "commit", "--quiet", "-m", "docs: synthetic test commit")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    hook = _copy_hook_runtime(tmp_path, "pre_push.ps1")
    zero_sha = "0" * len(commit)
    pre_push_input = f"refs/heads/main {commit} refs/heads/main {zero_sha}\n"

    result = _run_powershell_hook(hook, stdin=pre_push_input)

    if result is None:
        import pytest

        pytest.skip("PowerShell 7 is unavailable")
    assert result.returncode != 0
    assert "outgoing commit author/committer metadata" in result.stdout
    assert "synthetic-identity" not in result.stdout + result.stderr
