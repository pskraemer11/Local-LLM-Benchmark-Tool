"""Fail-closed privacy checks for staged content and outgoing Git commits."""

from __future__ import annotations

import base64
import binascii
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


_WINDOWS_PROFILE_PATH = re.compile(
    rb"(?i)(?:[A-Z]:[\\/]+Users[\\/]+|\\\\\?\\[A-Z]:\\Users\\|/(?:mnt/)?[A-Z]/Users/)([^\\/\s\"'<>:]+)"
)
_PROHIBITED_EMAIL_DOMAIN = re.compile(r"(?i)@(?:online|e-mail|posteo)\.de(?=$|[^a-z0-9.-])")
_VARIABLE_PROFILE_PREFIXES = (b"$", b"%", b"{")
_NON_PERSONAL_PROFILES = {b"public", b"default", b"default user", b"all users"}


class PrivacyGateError(RuntimeError):
    """A privacy check failed or could not be completed safely."""


def contains_private_profile_path(content: str | bytes) -> bool:
    """Return whether content contains a concrete Windows user-profile path."""
    raw_content = content.encode("utf-8", errors="replace") if isinstance(content, str) else content
    for match in _WINDOWS_PROFILE_PATH.finditer(raw_content):
        profile = match.group(1).strip().lower()
        if profile.startswith(_VARIABLE_PROFILE_PREFIXES):
            continue
        if profile in _NON_PERSONAL_PROFILES:
            continue
        return True
    return False


def contains_prohibited_email(identity: str | bytes) -> bool:
    """Return whether text contains an address from a prohibited email domain."""
    text = identity.decode("utf-8", errors="replace") if isinstance(identity, bytes) else identity
    return _PROHIBITED_EMAIL_DOMAIN.search(text) is not None


def _git(*arguments: str, input_bytes: bytes | None = None) -> bytes:
    try:
        result = subprocess.run(
            ["git", *arguments],
            check=False,
            capture_output=True,
            input=input_bytes,
        )
    except OSError as error:
        raise PrivacyGateError("Git could not be run; refusing the operation.") from error
    if result.returncode != 0:
        raise PrivacyGateError("A required Git privacy check failed; refusing the operation.")
    return result.stdout


def _check_added_lines(diff: bytes) -> None:
    for line in diff.splitlines():
        if line.startswith(b"+") and not line.startswith(b"+++"):
            if contains_private_profile_path(line[1:]):
                raise PrivacyGateError(
                    "Staged or outgoing content contains a concrete Windows user-profile path. "
                    "Use a portable home-directory variable instead."
                )
            if contains_prohibited_email(line[1:]):
                raise PrivacyGateError("Staged or outgoing added content contains a prohibited personal email domain.")


def _check_commit_identity(identity: bytes, *, context: str) -> None:
    if contains_prohibited_email(identity):
        raise PrivacyGateError(f"The {context} uses a prohibited personal email domain.")


def _check_commit_message(message: bytes) -> None:
    if contains_prohibited_email(message):
        raise PrivacyGateError("The commit message contains a prohibited personal email domain.")


def check_commit_message_file(message_path: str) -> None:
    """Check a Git commit-message file without including its contents in errors."""
    try:
        message = Path(message_path).read_bytes()
    except OSError as error:
        raise PrivacyGateError("The commit-message file could not be read; refusing the commit.") from error
    _check_commit_message(message)


def check_before_commit() -> None:
    """Check configured commit identities and newly staged text before commit."""
    for identity_kind in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
        identity = _git("var", identity_kind)
        _check_commit_identity(identity, context="commit author/committer identity")

    staged_diff = _git("diff", "--cached", "--no-ext-diff", "--no-color", "--unified=0", "--binary")
    _check_added_lines(staged_diff)


def _parse_push_updates(push_input: bytes) -> list[tuple[str, str]]:
    updates: list[tuple[str, str]] = []
    for line in push_input.splitlines():
        fields = line.split()
        if len(fields) != 4:
            raise PrivacyGateError("The pre-push ref update input was invalid; refusing the push.")
        local_sha = fields[1].decode("ascii", errors="strict")
        remote_sha = fields[3].decode("ascii", errors="strict")
        if not _is_git_sha(local_sha):
            raise PrivacyGateError("The pre-push local revision was invalid; refusing the push.")
        if not _is_git_sha(remote_sha):
            raise PrivacyGateError("The pre-push remote revision was invalid; refusing the push.")
        updates.append((local_sha, remote_sha))
    if not updates:
        raise PrivacyGateError("No pre-push ref updates were received; refusing the push.")
    return updates


def _is_git_sha(revision: str) -> bool:
    return re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", revision) is not None


def _outgoing_commits(updates: Sequence[tuple[str, str]]) -> list[str]:
    commits: set[str] = set()
    for local_sha, remote_sha in updates:
        if not local_sha.strip("0"):
            continue  # Deleting a ref publishes no new commit.
        revisions = [local_sha]
        if remote_sha.strip("0"):
            revisions.append(f"^{remote_sha}")
        output = _git("rev-list", *revisions)
        commits.update(line.decode("ascii") for line in output.splitlines() if line)
    return sorted(commits)


def _check_outgoing_identities_and_messages(commits: Sequence[str]) -> None:
    chunk_size = 200
    for start in range(0, len(commits), chunk_size):
        chunk = commits[start : start + chunk_size]
        metadata = _git("log", "--no-walk", "--format=%ae%x1f%ce", *chunk)
        for identity_line in metadata.splitlines():
            _check_commit_identity(identity_line, context="outgoing commit author/committer metadata")
        messages = _git("log", "--no-walk", "--format=%B", *chunk)
        _check_commit_message(messages)


def _check_outgoing_content(commits: Sequence[str]) -> None:
    for commit in commits:
        # -m includes merge-resolution changes relative to each parent. Only
        # added lines are inspected, so existing history does not block a clean
        # commit merely because it already contains previously published data.
        patch = _git(
            "show",
            "-m",
            "--format=",
            "--no-ext-diff",
            "--no-renames",
            "--unified=0",
            "--no-color",
            commit,
        )
        _check_added_lines(patch)


def check_before_push(push_input: bytes) -> None:
    """Check identities, commit messages, and added content for every pushed ref."""
    updates = _parse_push_updates(push_input)
    commits = _outgoing_commits(updates)
    _check_outgoing_identities_and_messages(commits)
    _check_outgoing_content(commits)


def check_commit_range(base_sha: str, head_sha: str) -> None:
    """Check identities, messages, and added content in a CI commit range."""
    if not _is_git_sha(base_sha) or not _is_git_sha(head_sha) or not head_sha.strip("0"):
        raise PrivacyGateError("The CI commit range was invalid; refusing the check.")
    commits = _outgoing_commits([(head_sha.lower(), base_sha.lower())])
    _check_outgoing_identities_and_messages(commits)
    _check_outgoing_content(commits)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selected Git-hook check and emit only non-sensitive diagnostics."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        print(
            "Usage: privacy_gate.py {pre-commit|pre-push [--input-base64 VALUE]|"
            "check-range BASE_SHA HEAD_SHA|check-message MESSAGE_FILE}",
            file=sys.stderr,
        )
        return 2

    try:
        if arguments[0] == "pre-commit" and len(arguments) == 1:
            check_before_commit()
        elif arguments[0] == "pre-push" and len(arguments) == 1:
            check_before_push(sys.stdin.buffer.read())
        elif arguments[0] == "pre-push" and len(arguments) == 3 and arguments[1] == "--input-base64":
            check_before_push(base64.b64decode(arguments[2], validate=True))
        elif arguments[0] == "check-range" and len(arguments) == 3:
            check_commit_range(arguments[1], arguments[2])
        elif arguments[0] == "check-message" and len(arguments) == 2:
            check_commit_message_file(arguments[1])
        else:
            print(
                "Usage: privacy_gate.py {pre-commit|pre-push [--input-base64 VALUE]|"
                "check-range BASE_SHA HEAD_SHA|check-message MESSAGE_FILE}",
                file=sys.stderr,
            )
            return 2
    except PrivacyGateError as error:
        # Error text is restricted to static reasons; never echo offending data.
        print(f"[PRIVACY GATE BLOCKED] {error}")
        return 1
    except (UnicodeDecodeError, binascii.Error):
        print("[PRIVACY GATE BLOCKED] Privacy checks failed; inspect the staged or outgoing changes.")
        return 1

    print("[PRIVACY GATE] No prohibited profile paths, email domains, or commit identities detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
