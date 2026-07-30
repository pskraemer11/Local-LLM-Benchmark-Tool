#!/usr/bin/env python3
"""Terminal output utilities: ANSI colors + progress bar."""

from __future__ import annotations

import os
import sys

_CAN_COLOR = (
    hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    and os.environ.get("TERM") != "dumb"
    and not os.environ.get("NO_COLOR")
)


def _c(code: str, text: str) -> str:
    return f"{code}{text}\033[0m" if _CAN_COLOR else text


def green(text: str) -> str:
    return _c("\033[92m", text)


def yellow(text: str) -> str:
    return _c("\033[93m", text)


def red(text: str) -> str:
    return _c("\033[91m", text)


def cyan(text: str) -> str:
    return _c("\033[96m", text)


def bold(text: str) -> str:
    return _c("\033[1m", text)


def ok(msg: str) -> None:
    print(f"  {green('[OK]')} {msg}")


def warn(msg: str) -> None:
    print(f"  {yellow('[WARN]')} {msg}", file=sys.stderr)


def error(msg: str) -> None:
    print(f"  {red('[ERROR]')} {msg}", file=sys.stderr)


def info(msg: str) -> None:
    print(f"  [INFO] {msg}")


def progress_bar(current: int, total: int, prefix: str = "") -> None:
    if total <= 0:
        return
    bar_w = min(total, 50)
    filled = int(bar_w * current / total)
    bar = green("#" * filled) + "." * (bar_w - filled)
    pad = " " * 10
    print(f"\r  {prefix} [{bar}] {current}/{total}{pad}", end="", flush=True)
    if current >= total:
        print()
