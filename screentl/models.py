"""Application data models shared by GUI, CLI and background services."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class TaskState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class CaptureConfig:
    folder: Path
    interval: int

    def validate(self) -> None:
        if self.interval <= 0:
            raise ValueError("capture interval must be greater than zero")
        if not str(self.folder).strip():
            raise ValueError("capture folder is required")


@dataclass(frozen=True)
class RenderConfig:
    folder: Path
    fps: int
    audio_folder: Path | None = None
    title: str = ""
    output_name: str = "video.mp4"

    def validate(self) -> None:
        if self.fps <= 0:
            raise ValueError("video fps must be greater than zero")
        if not str(self.folder).strip():
            raise ValueError("screenshot folder is required")
        if not self.output_name.lower().endswith(".mp4"):
            raise ValueError("output filename must use the .mp4 extension")
