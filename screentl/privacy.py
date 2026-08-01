"""Local privacy rules and Windows activity signals."""

from __future__ import annotations

import ctypes
import os
import threading
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ActiveWindowInfo:
    title: str = ""
    process_name: str = ""
    rect: tuple[int, int, int, int] | None = None


@dataclass
class PrivacyRules:
    excluded_apps: list[str] = field(default_factory=list)
    excluded_title_keywords: list[str] = field(default_factory=list)
    idle_pause_seconds: int = 0
    pause_when_locked: bool = True
    pause_on_battery: bool = False
    collect_window_metadata: bool = False
    ocr_enabled: bool = False
    cloud_enabled: bool = False

    def normalized_apps(self) -> set[str]:
        return {Path(value).name.casefold() for value in self.excluded_apps if value.strip()}

    def normalized_titles(self) -> tuple[str, ...]:
        return tuple(value.casefold() for value in self.excluded_title_keywords if value.strip())


class _LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


class _SystemPowerStatus(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte),
        ("BatteryFlag", ctypes.c_ubyte),
        ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte),
        ("BatteryLifeTime", ctypes.c_uint),
        ("BatteryFullLifeTime", ctypes.c_uint),
    ]


def get_active_window_info() -> ActiveWindowInfo:
    if os.name != "nt":
        return ActiveWindowInfo()
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ActiveWindowInfo()

    length = user32.GetWindowTextLengthW(hwnd)
    title_buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, title_buffer, length + 1)

    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    process_name = ""
    process = kernel32.OpenProcess(0x1000, False, process_id.value)
    if process:
        try:
            size = wintypes.DWORD(32768)
            path_buffer = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(
                process,
                0,
                path_buffer,
                ctypes.byref(size),
            ):
                process_name = Path(path_buffer.value).name
        finally:
            kernel32.CloseHandle(process)

    rect_value = wintypes.RECT()
    rect = None
    if user32.GetWindowRect(hwnd, ctypes.byref(rect_value)):
        rect = (
            rect_value.left,
            rect_value.top,
            max(0, rect_value.right - rect_value.left),
            max(0, rect_value.bottom - rect_value.top),
        )
    return ActiveWindowInfo(title_buffer.value, process_name, rect)


def get_idle_seconds() -> float:
    if os.name != "nt":
        return 0.0
    info = _LastInputInfo()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    elapsed_ms = ctypes.windll.kernel32.GetTickCount64() - info.dwTime
    return max(0.0, elapsed_ms / 1000.0)


def is_workstation_locked() -> bool:
    if os.name != "nt":
        return False
    user32 = ctypes.windll.user32
    desktop = user32.OpenInputDesktop(0, False, 0x0100)
    if not desktop:
        return True
    try:
        return not bool(user32.SwitchDesktop(desktop))
    finally:
        user32.CloseDesktop(desktop)


def is_on_battery() -> bool:
    if os.name != "nt":
        return False
    status = _SystemPowerStatus()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        return False
    return status.ACLineStatus == 0


class PrivacyGuard:
    def __init__(self, rules: PrivacyRules | None = None) -> None:
        self.rules = rules or PrivacyRules()
        self.manual_pause = threading.Event()

    def toggle_manual_pause(self) -> bool:
        if self.manual_pause.is_set():
            self.manual_pause.clear()
            return False
        self.manual_pause.set()
        return True

    def should_capture(self) -> tuple[bool, str, ActiveWindowInfo]:
        window = get_active_window_info()
        if self.manual_pause.is_set():
            return False, "manual privacy pause", window
        if self.rules.pause_when_locked and is_workstation_locked():
            return False, "workstation locked", window
        if self.rules.pause_on_battery and is_on_battery():
            return False, "running on battery", window
        if self.rules.idle_pause_seconds > 0 and get_idle_seconds() >= self.rules.idle_pause_seconds:
            return False, "user idle", window
        if window.process_name.casefold() in self.rules.normalized_apps():
            return False, "excluded application", window
        title = window.title.casefold()
        if any(keyword in title for keyword in self.rules.normalized_titles()):
            return False, "excluded window title", window
        return True, "", window


class GlobalPrivacyHotkey:
    """Register Ctrl+Alt+P on Windows and invoke a callback on a daemon thread."""

    HOTKEY_ID = 0x5343
    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012
    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    VK_P = 0x50

    def __init__(self, callback: Callable[[], None]) -> None:
        self.callback = callback
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._ready = threading.Event()
        self.registered = False

    def start(self) -> bool:
        if os.name != "nt" or self._thread is not None:
            return False
        self._thread = threading.Thread(
            target=self._run,
            name="screentl-privacy-hotkey",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait(2)
        return self.registered

    def _run(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = int(kernel32.GetCurrentThreadId())
        self.registered = bool(
            user32.RegisterHotKey(
                None,
                self.HOTKEY_ID,
                self.MOD_ALT | self.MOD_CONTROL,
                self.VK_P,
            )
        )
        self._ready.set()
        if not self.registered:
            return
        message = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == self.WM_HOTKEY and message.wParam == self.HOTKEY_ID:
                    self.callback()
        finally:
            user32.UnregisterHotKey(None, self.HOTKEY_ID)
            self.registered = False

    def stop(self) -> None:
        if os.name == "nt" and self._thread_id is not None:
            ctypes.windll.user32.PostThreadMessageW(
                self._thread_id,
                self.WM_QUIT,
                0,
                0,
            )
        if self._thread is not None:
            self._thread.join(2)
        self._thread = None
        self._thread_id = None
