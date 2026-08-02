"""Thread-safe application event channel."""

from __future__ import annotations

import queue
from dataclasses import dataclass
from enum import Enum
from typing import Any


class EventKind(str, Enum):
    LOG = "log"
    TASK_STATE = "task_state"
    CAPTURED = "captured"
    SESSION_CHANGED = "session_changed"
    RENDER_PROGRESS = "render_progress"
    RENDER_FINISHED = "render_finished"
    ERROR = "error"
    COMMAND = "command"


@dataclass(frozen=True)
class AppEvent:
    kind: EventKind
    source: str
    message: str = ""
    data: Any = None


class EventBus:
    """A bounded queue so long-running sessions cannot grow without limit."""

    def __init__(self, maxsize: int = 1000) -> None:
        self._queue: queue.Queue[AppEvent] = queue.Queue(maxsize=maxsize)

    def publish(self, event: AppEvent) -> None:
        try:
            self._queue.put_nowait(event)
            return
        except queue.Full:
            pass

        try:
            self._queue.get_nowait()
        except queue.Empty:
            return
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            pass

    def drain(self, limit: int = 100) -> list[AppEvent]:
        events: list[AppEvent] = []
        for _ in range(max(0, limit)):
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return events
