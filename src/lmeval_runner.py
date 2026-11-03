"""CLI wrapper that registers the project backend before lm-eval starts.

lm-eval resolves the model backend through its own registry. The project uses
a local chat-completions backend that must not send the ineffective task
fields ``do_sample`` and ``max_gen_toks`` to the server (see
``lmeval_backend``). Registering it here keeps the cleanup inside the project
instead of patching the installed package.

Usage mirrors the lm-eval module entry point:

    py -3.12 src/lmeval_runner.py --model benchmarks-chat-completions --tasks ...
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# The backend module is addressed by its import path, so the project source
# directory has to be importable in the child process.
_SRC_DIR = Path(__file__).resolve().parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def main(argv: list[str] | None = None) -> int:
    """Register the project backend and run the lm-eval CLI."""
    arguments = list(sys.argv[1:] if argv is None else argv)

    from lmeval_backend import register

    register()

    from lm_eval.__main__ import cli_evaluate

    sys.argv = [sys.argv[0], *arguments]
    cli_evaluate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
