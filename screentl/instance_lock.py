"""Cross-platform application instance locking with Windows window activation."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Any

ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9


class _WindowsApi:
    """Small ctypes wrapper kept behind an injectable interface for tests."""

    def __init__(self) -> None:
        self.kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)

        self.kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel32.CreateMutexW.restype = wintypes.HANDLE
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL

        self.user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        self.user32.FindWindowW.restype = wintypes.HWND
        self.user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.ShowWindow.restype = wintypes.BOOL
        self.user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        self.user32.SetForegroundWindow.restype = wintypes.BOOL

    def create_mutex(self, name: str) -> tuple[Any, int]:
        ctypes.set_last_error(0)
        handle = self.kernel32.CreateMutexW(None, False, name)
        return handle, ctypes.get_last_error()

    def close_handle(self, handle: Any) -> None:
        self.kernel32.CloseHandle(handle)

    def activate_window(self, title: str) -> bool:
        window = self.user32.FindWindowW(None, title)
        if not window:
            return False
        self.user32.ShowWindow(window, SW_RESTORE)
        self.user32.SetForegroundWindow(window)
        return True


class SingleInstance:
    """Own a named OS mutex for the lifetime of one application process."""

    def __init__(self, name: str, api: Any | None = None) -> None:
        self.name = name
        self._api = api if api is not None else (_WindowsApi() if os.name == 'nt' else None)
        self._handle: Any | None = None
        self._acquired = False

    def acquire(self) -> bool:
        if self._acquired:
            return True
        if self._api is None:
            self._acquired = True
            return True

        handle, last_error = self._api.create_mutex(self.name)
        if not handle:
            raise OSError(last_error, f'failed to create application mutex: {self.name}')
        if last_error == ERROR_ALREADY_EXISTS:
            self._api.close_handle(handle)
            return False

        self._handle = handle
        self._acquired = True
        return True

    def release(self) -> None:
        if self._handle is not None and self._api is not None:
            self._api.close_handle(self._handle)
        self._handle = None
        self._acquired = False

    def __enter__(self) -> 'SingleInstance':
        if not self.acquire():
            raise RuntimeError('another application instance is already running')
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.release()


def activate_existing_window(title: str, api: Any | None = None) -> bool:
    """Restore and focus a window with the exact application title on Windows."""
    platform_api = api if api is not None else (_WindowsApi() if os.name == 'nt' else None)
    if platform_api is None:
        return False
    return bool(platform_api.activate_window(title))
