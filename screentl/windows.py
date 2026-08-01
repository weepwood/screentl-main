"""Small platform helpers kept outside of the UI layer."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def set_startup(app_name: str, command: str, enabled: bool) -> None:
    if os.name != "nt":
        raise OSError("startup registration is only available on Windows")
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        key_path,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        if enabled:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass


def open_folder(path: Path) -> None:
    if os.name == "nt":
        os.startfile(str(path))
        return
    if os.name == "posix":
        command = (
            ["open", str(path)]
            if os.uname().sysname == "Darwin"
            else ["xdg-open", str(path)]
        )
        subprocess.Popen(command)
        return
    raise OSError("unsupported operating system")
