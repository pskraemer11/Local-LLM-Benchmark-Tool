"""Worker process for bounded execution of generated benchmark code.

The worker is intentionally a defense-in-depth control, not a hard sandbox.
The parent process supplies one JSON request over stdin and receives one JSON
result marker over stdout. The parent owns the stronger Windows process limits.
"""

from __future__ import annotations

import ast
import builtins
import io
import json
import sys
from typing import Any

SANDBOX_MAX_REQUEST_BYTES = 8 * 1024 * 1024
SANDBOX_MAX_ERROR_CHARS = 500
SANDBOX_MAX_OUTPUT_BYTES = 512 * 1024

SANDBOX_SAFE_BUILTINS = frozenset({
    "abs", "all", "any", "bin", "bool", "bytearray", "bytes", "chr",
    "complex", "dict", "divmod", "enumerate", "filter", "float", "format",
    "frozenset", "hash", "hex", "id", "int", "isinstance", "issubclass",
    "iter", "len", "list", "map", "max", "min", "next", "oct", "ord",
    "pow", "print", "property", "range", "repr", "reversed", "round", "set",
    "slice", "sorted", "str", "sum", "super", "tuple", "zip", "True", "False",
    "None", "staticmethod", "classmethod", "memoryview", "ascii", "__build_class__",
})

# These libraries are needed by DS1000 setup/reference code. They are an
# explicit compatibility allowlist, not a claim that third-party modules are
# safe to expose to hostile model output.
SANDBOX_ALLOWED_MODULES = frozenset({
    "collections", "decimal", "fractions", "functools", "itertools", "math",
    "matplotlib", "numpy", "pandas", "PIL", "random", "scipy", "seaborn",
    "sklearn", "statistics",
})

SANDBOX_BLOCKED_MODULES = frozenset({
    "asyncio", "antigravity", "code", "codeop", "ctypes", "distutils", "ftplib",
    "http", "inspect", "importlib", "multiprocessing", "os", "pathlib", "pdb",
    "pickle", "platform", "shutil", "signal", "smtplib", "socket", "subprocess",
    "sys", "sysconfig", "telnetlib", "threading", "tkinter", "traceback", "urllib",
    "warnings", "webbrowser",
})


class _BoundedTextWriter(io.TextIOBase):
    """Absorb untrusted print output without allowing unbounded pipe growth."""

    def __init__(self, limit: int) -> None:
        super().__init__()
        self._limit = limit
        self._data = bytearray()

    def writable(self) -> bool:
        return True

    def write(self, value: str) -> int:
        encoded = value.encode("utf-8", errors="replace")
        remaining = max(0, self._limit - len(self._data))
        if remaining:
            self._data.extend(encoded[:remaining])
        return len(value)

    def flush(self) -> None:
        return None


def _validate_source(code: str) -> None:
    """Reject obvious interpreter-recovery syntax before execution."""
    tree = ast.parse(code, mode="exec")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Name, ast.Attribute)):
            identifier = node.id if isinstance(node, ast.Name) else node.attr
            if identifier.startswith("__") or identifier.endswith("__"):
                raise ValueError("dunder access is not allowed in sandbox code")


def _make_builtins() -> dict[str, Any]:
    real_import = builtins.__import__

    def safe_import(name: str, globals_dict: dict[str, Any] | None = None,
                    locals_dict: dict[str, Any] | None = None,
                    fromlist: tuple[str, ...] = (), level: int = 0) -> Any:
        if level != 0:
            raise ImportError("relative imports are not allowed")
        top_level = name.split(".", 1)[0]
        if top_level not in SANDBOX_ALLOWED_MODULES:
            raise ImportError(f"Module {name!r} is not on the sandbox allowlist")
        return real_import(name, globals_dict, locals_dict, fromlist, level)

    safe = {
        name: getattr(builtins, name)
        for name in SANDBOX_SAFE_BUILTINS
        if hasattr(builtins, name)
    }
    safe["__import__"] = safe_import
    return safe


def _execute(request: dict[str, Any]) -> dict[str, Any]:
    code = request.get("code")
    tests = request.get("tests")
    if not isinstance(code, str) or not isinstance(tests, (list, type(None))):
        raise ValueError("invalid sandbox request")
    if tests is not None and not all(isinstance(test, str) for test in tests):
        raise ValueError("sandbox tests must be strings")

    _validate_source(code)
    namespace: dict[str, Any] = {"__builtins__": _make_builtins(), "__name__": "__sandbox__"}
    result: dict[str, Any] = {
        "ok": True,
        "error": None,
        "state": None,
        "passed": 0,
        "total": 0,
        "details": [],
    }
    exec(code, namespace, namespace)  # noqa: S102 - intentional worker boundary

    if request.get("capture_state"):
        state: dict[str, str] = {}
        for key, value in namespace.items():
            if key.startswith("_"):
                continue
            try:
                state[key] = repr(value)[:SANDBOX_MAX_ERROR_CHARS]
            except Exception:
                state[key] = str(type(value))
        result["state"] = state

    if tests is not None:
        details: list[dict[str, Any]] = []
        for index, test in enumerate(tests):
            try:
                _validate_source(test)
                exec(test, namespace, namespace)  # noqa: S102 - intentional worker boundary
                details.append({"index": index, "passed": True})
            except BaseException as exc:
                details.append({
                    "index": index,
                    "passed": False,
                    "error": str(exc)[:SANDBOX_MAX_ERROR_CHARS],
                })
        result["passed"] = sum(1 for item in details if item["passed"])
        result["total"] = len(details)
        result["details"] = details
    return result


def _error_result(exc: BaseException) -> dict[str, Any]:
    return {
        "ok": False,
        "error": f"{type(exc).__name__}: {str(exc)[:SANDBOX_MAX_ERROR_CHARS]}",
        "state": None,
        "passed": 0,
        "total": 0,
        "details": [],
    }


def main() -> int:
    raw_request = sys.stdin.buffer.read(SANDBOX_MAX_REQUEST_BYTES + 1)
    if len(raw_request) > SANDBOX_MAX_REQUEST_BYTES:
        result = _error_result(ValueError("sandbox request exceeds size limit"))
    else:
        try:
            request = json.loads(raw_request.decode("utf-8"))
            if not isinstance(request, dict):
                raise ValueError("sandbox request must be an object")
            result = _execute(request)
        except BaseException as exc:
            result = _error_result(exc)

    # Generated code gets a bounded stdout/stderr sink; only this final marker
    # is written to the parent process's real stdout.
    sys.__stdout__.write("__SANDBOX__" + json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    sys.__stdout__.flush()
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    _stdout, _stderr = sys.stdout, sys.stderr
    _limited_output = _BoundedTextWriter(SANDBOX_MAX_OUTPUT_BYTES)
    sys.stdout = _limited_output
    sys.stderr = _limited_output
    try:
        raise SystemExit(main())
    finally:
        sys.stdout, sys.stderr = _stdout, _stderr
