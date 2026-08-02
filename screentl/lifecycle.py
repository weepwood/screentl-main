"""Session-bound capture, render and timeline helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .capture_engine import SessionCaptureEngine
from .sessions import RecordingSession
from .timeline import TimelineGroup, TimelinePage, TimelineService, frame_hour


@dataclass
class SessionTaskBindings:
    """Track immutable session ownership for asynchronous tasks."""

    capture_session_id: str | None = None
    pending_complete_session_id: str | None = None
    render_session_id: str | None = None

    def bind_capture(self, session_id: str) -> None:
        self.capture_session_id = session_id
        self.pending_complete_session_id = None

    def request_completion(self, session_id: str) -> bool:
        if self.capture_session_id != session_id:
            return False
        self.pending_complete_session_id = session_id
        return True

    def rollover_capture(self, session_id: str) -> None:
        completion_requested = self.pending_complete_session_id is not None
        self.capture_session_id = session_id
        self.pending_complete_session_id = session_id if completion_requested else None

    def finish_capture(self) -> tuple[str | None, str | None]:
        session_id = self.capture_session_id
        if session_id is None:
            return None, None
        status = (
            "completed"
            if self.pending_complete_session_id == session_id
            else "paused"
        )
        self.capture_session_id = None
        self.pending_complete_session_id = None
        return session_id, status

    def bind_render(self, session_id: str) -> None:
        self.render_session_id = session_id

    def finish_render(self) -> None:
        self.render_session_id = None


class LifecycleCaptureEngine(SessionCaptureEngine):
    """Notify the desktop coordinator when daily rollover changes sessions."""

    def __init__(
        self,
        *args,
        on_session_change: Callable[[RecordingSession], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.on_session_change = on_session_change

    def _rollover_if_needed(self) -> None:
        previous_id = self.session.id
        super()._rollover_if_needed()
        if self.session.id != previous_id and self.on_session_change is not None:
            self.on_session_change(self.session)


class AccurateTimelineService(TimelineService):
    """Keep pagination totals aligned with excluded-frame filtering."""

    def page(
        self,
        session_id: str,
        offset: int = 0,
        limit: int = 200,
        include_excluded: bool = True,
    ) -> TimelinePage:
        counter = getattr(self.repository, "count_frames", None)
        total = (
            int(counter(session_id, include_excluded))
            if callable(counter)
            else int(self.repository.session_summary(session_id)["frames"])
        )
        frames = self.repository.list_frames(
            session_id,
            offset=offset,
            limit=limit,
            include_excluded=include_excluded,
        )
        grouped: list[TimelineGroup] = []
        current_hour = ""
        bucket = []
        for frame in frames:
            hour = frame_hour(frame)
            if bucket and hour != current_hour:
                grouped.append(TimelineGroup(current_hour, tuple(bucket)))
                bucket = []
            current_hour = hour
            bucket.append(frame)
        if bucket:
            grouped.append(TimelineGroup(current_hour, tuple(bucket)))
        return TimelinePage(offset, limit, total, tuple(grouped))
