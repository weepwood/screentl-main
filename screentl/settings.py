"""Persistent application settings."""

from __future__ import annotations

import datetime
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .storage import atomic_write_json


def default_data_root() -> Path:
    return Path.home() / "Pictures" / "ScreenshotTimeLapse"


@dataclass
class AppSettings:
    folder: str
    interval: int = 30
    fps: int = 25
    audio: str = ""
    text: str = ""
    startup: bool = False
    minimize_to_tray: bool = True

    @classmethod
    def defaults(cls) -> AppSettings:
        today = datetime.date.today().strftime("%Y-%m-%d")
        return cls(
            folder=str(default_data_root() / today),
            audio=str(Path.home() / "Music"),
            text=today,
        )

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AppSettings:
        defaults = cls.defaults()
        try:
            interval = int(raw.get("interval", defaults.interval))
        except (TypeError, ValueError):
            interval = defaults.interval
        try:
            fps = int(raw.get("fps", defaults.fps))
        except (TypeError, ValueError):
            fps = defaults.fps
        return cls(
            folder=str(raw.get("folder") or defaults.folder),
            interval=max(1, interval),
            fps=max(1, fps),
            audio=str(raw.get("audio") or defaults.audio),
            text=str(raw.get("text", defaults.text)),
            startup=bool(raw.get("startup", defaults.startup)),
            minimize_to_tray=bool(
                raw.get("minimize_to_tray", defaults.minimize_to_tray)
            ),
        )


class SettingsRepository:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or self.default_path()

    @staticmethod
    def default_path() -> Path:
        app_data = Path(
            os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
        )
        return app_data / "ScreenshotTimeLapse" / "config.json"

    def load(self) -> AppSettings:
        try:
            with self.path.open("r", encoding="utf-8") as file:
                raw = json.load(file)
            if not isinstance(raw, dict):
                return AppSettings.defaults()
            return AppSettings.from_dict(raw)
        except (OSError, TypeError, ValueError):
            return AppSettings.defaults()

    def save(self, settings: AppSettings) -> None:
        atomic_write_json(self.path, asdict(settings))
