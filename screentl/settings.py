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


def normalize_capture_folder(value: Any, fallback: str) -> str:
    raw = str(value or fallback).strip()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = default_data_root() / path
    return str(path.resolve())


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
            folder=str((default_data_root() / today).resolve()),
            audio=str((Path.home() / "Music").resolve()),
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

        audio_value = raw.get("audio", defaults.audio)
        return cls(
            folder=normalize_capture_folder(raw.get("folder"), defaults.folder),
            interval=max(1, interval),
            fps=max(1, fps),
            audio=str(audio_value).strip() if audio_value is not None else "",
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
        normalized = AppSettings.from_dict(asdict(settings))
        atomic_write_json(self.path, asdict(normalized))
