"""Non-interactive startup diagnostics for packaged application smoke tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import imageio_ffmpeg

from .settings import SettingsRepository
from .version import __version__


def collect_diagnostics() -> dict[str, str | bool]:
    ffmpeg_path = Path(imageio_ffmpeg.get_ffmpeg_exe())
    settings_path = SettingsRepository.default_path()
    return {
        "application": "ScreenshotTimeLapse",
        "version": __version__,
        "python": sys.version.split()[0],
        "frozen": bool(getattr(sys, "frozen", False)),
        "ffmpeg": str(ffmpeg_path),
        "ffmpeg_exists": ffmpeg_path.is_file(),
        "settings_path": str(settings_path),
    }


def run_diagnostics() -> int:
    result = collect_diagnostics()
    if sys.stdout is not None:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ffmpeg_exists"] else 1
