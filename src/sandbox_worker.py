"""Worker process for bounded execution of generated benchmark code.

The worker is intentionally a defense-in-depth control, not a hard sandbox.
The parent process supplies one JSON request over stdin and receives one JSON
result marker over stdout. The parent owns the stronger Windows process limits.
"""

from __future__ import annotations

import builtins
import hashlib
import io
import json
import sys
from datetime import date, datetime, time, timedelta
from types import BuiltinFunctionType, FunctionType, MethodType, ModuleType
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

# Kept as documentation for the benchmark dependencies. The normal worker no
# longer uses an import allowlist; the process boundary and Job Object provide
# the practical protection without blocking valid benchmark code.
SANDBOX_ALLOWED_MODULES = frozenset({
    "collections", "decimal", "fractions", "functools", "itertools", "math",
    "matplotlib", "numpy", "pandas", "PIL", "random", "scipy", "seaborn",
    "sklearn", "statistics",
})

# Deprecated compatibility metadata for callers that imported these names.
# They are informational only; imports are no longer blocked in this worker.
SANDBOX_BLOCKED_MODULES = frozenset({
    "asyncio", "code", "ctypes", "ftplib", "http", "inspect", "importlib",
    "multiprocessing", "os", "pathlib", "pickle", "shutil", "socket",
    "subprocess", "sys", "threading", "urllib", "warnings",
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


def _make_builtins() -> dict[str, Any]:
    # The worker is intentionally compatibility-first. It is not the security
    # boundary; the parent process owns the timeout and Windows Job Object.
    return dict(vars(builtins))


def _combine_value_hashes(kind: str, parts: list[str | None]) -> str | None:
    """Combine typed child digests without ambiguous concatenation."""
    digest = hashlib.sha256(kind.encode("utf-8") + b"\0")
    for part in parts:
        if part is None:
            return None
        digest.update(part.encode("ascii"))
    return digest.hexdigest()


def _value_hash(value: Any, active: set[int] | None = None) -> str | None:
    """Hash complete supported values; unsupported or cyclic objects fail closed.

    Library display representations deliberately omit middle rows/elements.
    Those representations are previews and never serve as equality evidence.
    """
    value_type = type(value)
    if value_type in {type(None), bool, int, float, complex, str, bytes, bytearray, range}:
        representation = bytes(value) if value_type in {bytes, bytearray} else repr(value).encode("utf-8", errors="surrogatepass")
        return hashlib.sha256(value_type.__name__.encode("ascii") + b"\0" + representation).hexdigest()
    if isinstance(value, (datetime, date, time)):
        parts = [_value_hash(value.isoformat()), _value_hash(getattr(value, "fold", 0)), _value_hash(getattr(value, "nanosecond", 0))]
        return _combine_value_hashes(value_type.__qualname__, parts)
    if isinstance(value, timedelta):
        return _combine_value_hashes(value_type.__qualname__, [_value_hash((value.days, value.seconds, value.microseconds)), _value_hash(getattr(value, "value", None))])

    active = set() if active is None else active
    object_id = id(value)
    if object_id in active:
        return None
    active.add(object_id)
    try:
        if value_type in {list, tuple, set, frozenset}:
            children = [_value_hash(item, active) for item in value]
            if value_type in {set, frozenset}:
                if any(child is None for child in children):
                    return None
                children.sort(key=lambda child: child or "")
            return _combine_value_hashes(value_type.__name__, children)
        if value_type is dict:
            children = [
                _combine_value_hashes("item", [_value_hash(key, active), _value_hash(item, active)])
                for key, item in value.items()
            ]
            return _combine_value_hashes("dict", sorted(children, key=lambda child: child or ""))

        np = sys.modules.get("numpy")
        if np is not None and isinstance(value, np.ndarray):
            if value_type is not np.ndarray:
                # Subclasses can carry additional value semantics (e.g. a
                # MaskedArray mask). Dropping those would create false passes.
                return None
            array = np.asarray(value)
            metadata = _value_hash((array.dtype.descr, array.shape, dict(array.dtype.metadata or {})), active)
            if array.dtype.hasobject:
                content = _value_hash(array.tolist(), active)
            else:
                content = hashlib.sha256(array.tobytes(order="C")).hexdigest()
            return _combine_value_hashes("numpy.ndarray", [metadata, content])
        if np is not None and isinstance(value, np.generic):
            content = _value_hash(value.item(), active) if value.dtype.hasobject else hashlib.sha256(value.tobytes()).hexdigest()
            return _combine_value_hashes("numpy.scalar", [_value_hash(value.dtype.descr), content])

        pd = sys.modules.get("pandas")
        if pd is not None:
            if value is pd.NA:
                return hashlib.sha256(b"pandas.NA").hexdigest()
            if value is pd.NaT:
                return hashlib.sha256(b"pandas.NaT").hexdigest()
            if isinstance(value, pd.DataFrame):
                dtypes = [_pandas_dtype_hash(dtype, active) for dtype in value.dtypes]
                return _combine_value_hashes("pandas.DataFrame", [
                    _value_hash(value.shape), _value_hash(value.index, active),
                    _value_hash(value.columns, active), _combine_value_hashes("dtypes", dtypes),
                    _value_hash(value.to_numpy(dtype=object).tolist(), active),
                ])
            if isinstance(value, pd.Series):
                return _combine_value_hashes("pandas.Series", [
                    _value_hash(value.shape), _value_hash(value.name, active),
                    _value_hash(value.index, active), _pandas_dtype_hash(value.dtype, active),
                    _value_hash(value.to_numpy(dtype=object).tolist(), active),
                ])
            if isinstance(value, pd.Index):
                structure = None
                if isinstance(value, pd.MultiIndex):
                    structure = (list(value.levels), list(value.codes), value.sortorder)
                return _combine_value_hashes("pandas.Index", [
                    _value_hash(value.shape), _value_hash(list(value.names), active),
                    _pandas_dtype_hash(value.dtype, active), _value_hash(value.tolist(), active),
                    _value_hash(structure, active),
                ])
        return None
    finally:
        active.remove(object_id)


def _pandas_dtype_hash(dtype: Any, active: set[int]) -> str | None:
    """Preserve extension dtype details including categorical ordering."""
    parts = [_value_hash(str(dtype)), _value_hash(type(dtype).__qualname__)]
    categories = getattr(dtype, "categories", None)
    if categories is not None:
        parts.extend([_value_hash(categories, active), _value_hash(bool(dtype.ordered))])
    return _combine_value_hashes("pandas.dtype", parts)


def _capture_namespace(namespace: dict[str, Any]) -> tuple[dict[str, str], dict[str, str], list[str]]:
    """Capture bounded previews and complete typed hashes for comparable values."""
    state: dict[str, str] = {}
    hashes: dict[str, str] = {}
    value_keys: list[str] = []
    for key, value in namespace.items():
        if key.startswith("_"):
            continue
        try:
            representation = repr(value)
            state[key] = representation[:SANDBOX_MAX_ERROR_CHARS]
            if isinstance(value, (FunctionType, BuiltinFunctionType, MethodType, ModuleType, type)):
                # Callables/modules are execution context, not comparable
                # outputs. Their identity is stable across the setup snapshot
                # and reference execution in this same worker.
                hashes[key] = hashlib.sha256(f"context:{id(value)}".encode("ascii")).hexdigest()
                continue
            digest = _value_hash(value)
            if digest is not None:
                hashes[key] = digest
                value_keys.append(key)
        except Exception:
            state[key] = str(type(value))
    return state, hashes, value_keys


def _execute(request: dict[str, Any]) -> dict[str, Any]:
    code = request.get("code")
    tests = request.get("tests")
    setup_code = request.get("setup_code")
    if not isinstance(code, str) or not isinstance(tests, (list, type(None))):
        raise ValueError("invalid sandbox request")
    if not isinstance(setup_code, (str, type(None))):
        raise ValueError("sandbox setup_code must be a string")
    if tests is not None and not all(isinstance(test, str) for test in tests):
        raise ValueError("sandbox tests must be strings")

    namespace: dict[str, Any] = {"__builtins__": _make_builtins(), "__name__": "__sandbox__"}
    result: dict[str, Any] = {
        "ok": True,
        "error": None,
        "state": None,
        "passed": 0,
        "total": 0,
        "details": [],
    }
    if setup_code is not None:
        try:
            exec(setup_code, namespace, namespace)  # noqa: S102 - intentional worker boundary
        except BaseException as exc:
            failure = _error_result(exc)
            failure["error_phase"] = "setup"
            return failure
        if request.get("capture_state"):
            result["setup_state"], result["setup_state_hashes"], _ = _capture_namespace(namespace)
    exec(code, namespace, namespace)  # noqa: S102 - intentional worker boundary

    if request.get("capture_state"):
        result["state"], result["state_hashes"], result["state_value_keys"] = _capture_namespace(namespace)

    if tests is not None:
        details: list[dict[str, Any]] = []
        for index, test in enumerate(tests):
            try:
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
    real_stdout = sys.__stdout__
    if real_stdout is None:
        return 1
    real_stdout.write("__SANDBOX__" + json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    real_stdout.flush()
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
