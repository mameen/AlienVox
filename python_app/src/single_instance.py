"""Single-instance enforcement via a named Windows mutex.

One AlienVox instance total, regardless of --cpu/--gpu — switching device
mode requires closing the running instance first (a CPU instance and a GPU
instance both hold the same audio devices / hotkey registration, so running
both at once is never actually useful, just confusing).
"""
from __future__ import annotations

import sys

_MUTEX_NAME = "Global\\AlienVox_SingleInstance"


class SingleInstanceGuard:
    """Holds an OS-level mutex for the lifetime of the process.

    `acquired` is True if this process is the only instance; False if
    another instance already holds the mutex. The mutex handle is released
    automatically when the process exits (or explicitly via release()).
    """

    def __init__(self) -> None:
        self.acquired = True
        self._handle = None

        if sys.platform != "win32":
            return  # single-instance enforcement is Windows-only for now

        try:
            import win32api
            import win32event
            import winerror

            self._handle = win32event.CreateMutex(None, False, _MUTEX_NAME)
            self.acquired = win32api.GetLastError() != winerror.ERROR_ALREADY_EXISTS
        except Exception:
            # If pywin32 isn't available or mutex creation fails for any
            # reason, fail open (allow the instance to start) rather than
            # blocking the app over a non-critical guard.
            self.acquired = True

    def release(self) -> None:
        if self._handle is not None:
            try:
                import win32api
                win32api.CloseHandle(self._handle)
            except Exception:
                pass
            self._handle = None
