"""Small Windows Job Object wrapper for benchmark worker processes."""

from __future__ import annotations

import ctypes
import os
import subprocess
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence


class WindowsJobObjectError(RuntimeError):
    """Raised when the worker cannot be placed under a Windows Job Object."""


if os.name == "nt":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _HANDLE = ctypes.c_void_p
    _DWORD = ctypes.c_uint32
    _SIZE_T = ctypes.c_size_t
    _LARGE_INTEGER = ctypes.c_int64

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class _BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", _LARGE_INTEGER),
            ("PerJobUserTimeLimit", _LARGE_INTEGER),
            ("LimitFlags", _DWORD),
            ("MinimumWorkingSetSize", _SIZE_T),
            ("MaximumWorkingSetSize", _SIZE_T),
            ("ActiveProcessLimit", _DWORD),
            ("Affinity", _SIZE_T),
            ("PriorityClass", _DWORD),
            ("SchedulingClass", _DWORD),
        ]

    class _ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimitInformation),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", _SIZE_T),
            ("JobMemoryLimit", _SIZE_T),
            ("PeakProcessMemoryUsed", _SIZE_T),
            ("PeakJobMemoryUsed", _SIZE_T),
        ]

    class _ThreadEntry32(ctypes.Structure):
        _fields_ = [
            ("dwSize", _DWORD),
            ("cntUsage", _DWORD),
            ("th32ThreadID", _DWORD),
            ("th32OwnerProcessID", _DWORD),
            ("tpBasePri", ctypes.c_long),
            ("tpDeltaPri", ctypes.c_long),
            ("dwFlags", _DWORD),
        ]

    _kernel32.CreateJobObjectW.argtypes = [_HANDLE, ctypes.c_wchar_p]
    _kernel32.CreateJobObjectW.restype = _HANDLE
    _kernel32.SetInformationJobObject.argtypes = [_HANDLE, _DWORD, ctypes.c_void_p, _DWORD]
    _kernel32.SetInformationJobObject.restype = ctypes.c_int
    _kernel32.AssignProcessToJobObject.argtypes = [_HANDLE, _HANDLE]
    _kernel32.AssignProcessToJobObject.restype = ctypes.c_int
    _kernel32.TerminateJobObject.argtypes = [_HANDLE, _DWORD]
    _kernel32.TerminateJobObject.restype = ctypes.c_int
    _kernel32.CloseHandle.argtypes = [_HANDLE]
    _kernel32.CloseHandle.restype = ctypes.c_int
    _kernel32.ResumeThread.argtypes = [_HANDLE]
    _kernel32.ResumeThread.restype = _DWORD
    _kernel32.CreateToolhelp32Snapshot.argtypes = [_DWORD, _DWORD]
    _kernel32.CreateToolhelp32Snapshot.restype = _HANDLE
    _kernel32.Thread32First.argtypes = [_HANDLE, ctypes.POINTER(_ThreadEntry32)]
    _kernel32.Thread32First.restype = ctypes.c_int
    _kernel32.Thread32Next.argtypes = [_HANDLE, ctypes.POINTER(_ThreadEntry32)]
    _kernel32.Thread32Next.restype = ctypes.c_int
    _kernel32.OpenThread.argtypes = [_DWORD, ctypes.c_int, _DWORD]
    _kernel32.OpenThread.restype = _HANDLE


class WindowsJobObject:
    """Limit and own one worker process tree.

    Non-Windows callers get a no-op adapter so unit tests and development tools
    can still exercise the worker protocol. The production Windows path fails
    closed when a Job Object cannot be created or assigned.
    """

    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    _JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
    _JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
    _JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

    def __init__(self, memory_limit_bytes: int, max_processes: int = 4) -> None:
        if memory_limit_bytes <= 0:
            raise ValueError("memory_limit_bytes must be positive")
        if max_processes <= 0:
            raise ValueError("max_processes must be positive")
        self._handle: Any = None
        self._enabled = os.name == "nt"
        if not self._enabled:
            return

        self._handle = _kernel32.CreateJobObjectW(None, None)
        if not self._handle:
            raise WindowsJobObjectError(self._last_error("CreateJobObjectW"))

        info = _ExtendedLimitInformation()
        info.BasicLimitInformation.LimitFlags = (
            self._JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            | self._JOB_OBJECT_LIMIT_PROCESS_MEMORY
            | self._JOB_OBJECT_LIMIT_JOB_MEMORY
            | self._JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        info.BasicLimitInformation.ActiveProcessLimit = max_processes
        info.ProcessMemoryLimit = memory_limit_bytes
        info.JobMemoryLimit = memory_limit_bytes
        ok = _kernel32.SetInformationJobObject(
            self._handle,
            self._JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            message = self._last_error("SetInformationJobObject")
            self.close()
            raise WindowsJobObjectError(message)

    def assign(self, process: subprocess.Popen[bytes]) -> None:
        """Assign a suspended Popen child before it can execute worker code."""
        if not self._enabled:
            return
        if not _kernel32.AssignProcessToJobObject(self._handle, process._handle):
            raise WindowsJobObjectError(self._last_error("AssignProcessToJobObject"))

    def resume(self, process: subprocess.Popen[bytes]) -> None:
        """Resume the primary thread after Job Object assignment."""
        if not self._enabled:
            return
        thread_handle = self._find_suspended_thread(process.pid)
        try:
            if _kernel32.ResumeThread(thread_handle) == 0xFFFFFFFF:
                raise WindowsJobObjectError(self._last_error("ResumeThread"))
        finally:
            _kernel32.CloseHandle(thread_handle)

    def terminate(self, exit_code: int = 1) -> None:
        if self._enabled and self._handle:
            _kernel32.TerminateJobObject(self._handle, exit_code)

    def close(self) -> None:
        if self._enabled and self._handle:
            _kernel32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self) -> WindowsJobObject:
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    @staticmethod
    def _last_error(operation: str) -> str:
        return f"{operation} failed: {ctypes.WinError(ctypes.get_last_error())}"

    @staticmethod
    def _find_suspended_thread(pid: int) -> Any:
        snapshot = _kernel32.CreateToolhelp32Snapshot(0x00000004, 0)
        if not snapshot or snapshot == ctypes.c_void_p(-1).value:
            raise WindowsJobObjectError(WindowsJobObject._last_error("CreateToolhelp32Snapshot"))
        entry = _ThreadEntry32()
        entry.dwSize = ctypes.sizeof(entry)
        try:
            found = _kernel32.Thread32First(snapshot, ctypes.byref(entry))
            while found:
                if entry.th32OwnerProcessID == pid:
                    thread_handle = _kernel32.OpenThread(0x0002, 0, entry.th32ThreadID)
                    if not thread_handle:
                        raise WindowsJobObjectError(WindowsJobObject._last_error("OpenThread"))
                    return thread_handle
                found = _kernel32.Thread32Next(snapshot, ctypes.byref(entry))
        finally:
            _kernel32.CloseHandle(snapshot)
        raise WindowsJobObjectError(f"No suspended primary thread found for process {pid}")


def run_bounded_subprocess(
    command: Sequence[str],
    *,
    timeout: float | None,
    memory_limit_bytes: int,
    max_processes: int,
    **popen_kwargs: Any,
) -> subprocess.CompletedProcess[Any]:
    """Run a child process with Windows process-tree resource enforcement.

    Windows has no portable ``resource.setrlimit`` equivalent.  Starting the
    child suspended, assigning it to a Job Object, and resuming it makes the
    memory/process limits apply before evaluator code can run.  Descendants
    created by EvalPlus inherit the same job.  Non-Windows callers retain the
    normal subprocess semantics so the module remains importable in tooling.
    """
    job: WindowsJobObject | None = None
    creationflags = int(popen_kwargs.pop("creationflags", 0) or 0)
    if popen_kwargs.pop("capture_output", False):
        popen_kwargs.setdefault("stdout", subprocess.PIPE)
        popen_kwargs.setdefault("stderr", subprocess.PIPE)
    if os.name == "nt":
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        creationflags |= getattr(subprocess, "CREATE_SUSPENDED", 0x00000004)
        job = WindowsJobObject(memory_limit_bytes, max_processes=max_processes)

    try:
        process = subprocess.Popen(command, creationflags=creationflags, **popen_kwargs)
        try:
            if job is not None:
                try:
                    job.assign(process)
                    job.resume(process)
                except BaseException:
                    job.terminate()
                    process.kill()
                    process.wait(timeout=5)
                    raise
            stdout, stderr = process.communicate(timeout=timeout)
            return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            if job is not None:
                job.terminate()
            else:
                process.kill()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
            raise
    finally:
        if job is not None:
            job.close()
