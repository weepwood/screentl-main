"""Reliable filesystem helpers for screenshots and small state files."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

SCREENSHOT_PATTERN = re.compile(
    r"^screenshot_(?P<sequence>\d+)(?:_(?P<timestamp>\d{8}_\d{6}))?\.png$",
    re.IGNORECASE,
)


def parse_screenshot_name(path: str | Path) -> tuple[int, str, str] | None:
    """Return a deterministic sort key for a supported screenshot filename."""
    name = Path(path).name
    match = SCREENSHOT_PATTERN.match(name)
    if match is None:
        return None
    return (
        int(match.group("sequence")),
        match.group("timestamp") or "",
        name.casefold(),
    )


def list_screenshots(folder: str | Path) -> list[Path]:
    """List supported screenshot files in deterministic render order."""
    folder_path = Path(folder)
    if not folder_path.is_dir():
        return []

    screenshots: list[tuple[tuple[int, str, str], Path]] = []
    for child in folder_path.iterdir():
        sort_key = parse_screenshot_name(child)
        if sort_key is not None and child.is_file():
            screenshots.append((sort_key, child))
    screenshots.sort(key=lambda item: item[0])
    return [path for _, path in screenshots]


def _read_counter(counter_path: Path) -> int:
    try:
        with counter_path.open("r", encoding="utf-8") as file:
            value = int(json.load(file)["num"])
        return max(0, value)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return 0


def next_screenshot_number(folder: str | Path) -> int:
    """Return a safe next sequence using both disk contents and counter state."""
    folder_path = Path(folder)
    folder_path.mkdir(parents=True, exist_ok=True)

    highest_existing = -1
    for screenshot_path in list_screenshots(folder_path):
        parsed = parse_screenshot_name(screenshot_path)
        if parsed is not None:
            highest_existing = max(highest_existing, parsed[0])

    return max(highest_existing + 1, _read_counter(folder_path / "num.json"))


def atomic_write_json(path: str | Path, payload: Any) -> None:
    """Write JSON through a same-directory temporary file and atomic replace."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    temporary_path = Path(temporary_name)

    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, destination)
    except Exception:
        try:
            os.close(file_descriptor)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise
