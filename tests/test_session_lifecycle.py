from pathlib import Path

from PIL import Image

from screentl.capture_engine import SessionCaptureEngine
from screentl.journal_repository import JournalRepository
from screentl.lifecycle import (
    AccurateTimelineService,
    LifecycleCaptureEngine,
    SessionTaskBindings,
)
from screentl.sessions import RecordingSession


def create_image(path: Path, color: str) -> Path:
    Image.new("RGB", (80, 45), color).save(path)
    return path


def test_task_bindings_complete_only_the_bound_capture_session():
    bindings = SessionTaskBindings()
    bindings.bind_capture("session-a")

    assert bindings.request_completion("session-b") is False
    assert bindings.request_completion("session-a") is True
    assert bindings.finish_capture() == ("session-a", "completed")
    assert bindings.capture_session_id is None
    assert bindings.pending_complete_session_id is None


def test_task_bindings_transfer_completion_intent_across_rollover():
    bindings = SessionTaskBindings()
    bindings.bind_capture("day-one")
    bindings.request_completion("day-one")
    bindings.rollover_capture("day-two")
    bindings.bind_render("render-session")

    assert bindings.finish_capture() == ("day-two", "completed")
    assert bindings.render_session_id == "render-session"
    bindings.finish_render()
    assert bindings.render_session_id is None


def test_repository_reactivation_clears_end_time_and_normalizes_name(tmp_path):
    repository = JournalRepository(tmp_path / "sessions.db")
    session = repository.create_session(tmp_path / "data", "   ")

    assert session.name == "Untitled session"
    repository.set_session_status(session.id, "completed")
    completed = repository.get_session(session.id)
    assert completed is not None
    assert completed.ended_at is not None

    repository.set_session_status(session.id, "active")
    active = repository.get_session(session.id)
    assert active is not None
    assert active.status == "active"
    assert active.ended_at is None


def test_summary_and_filtered_pagination_ignore_excluded_duration(tmp_path):
    repository = JournalRepository(tmp_path / "sessions.db")
    session = repository.create_session(tmp_path / "data", "Summary")
    kept = repository.add_frame(
        session.id,
        create_image(session.frames_path / "kept.png", "red"),
    )
    excluded = repository.add_frame(
        session.id,
        create_image(session.frames_path / "excluded.png", "blue"),
    )
    repository.set_frame_duration(kept.id, 2.5)
    repository.set_frame_duration(excluded.id, 7.5)
    repository.set_frames_excluded([excluded.id], True)

    summary = repository.session_summary(session.id)
    page = AccurateTimelineService(repository).page(
        session.id,
        include_excluded=False,
    )

    assert summary["frames"] == 2
    assert summary["excluded"] == 1
    assert summary["estimated_video_seconds"] == 2.5
    assert repository.count_frames(session.id, include_excluded=False) == 1
    assert page.total == 1
    assert sum(len(group.frames) for group in page.groups) == 1


def test_rollover_notifies_coordinator(monkeypatch, tmp_path):
    previous = RecordingSession(
        "old",
        "Old",
        tmp_path / "old",
        "daily",
        "active",
        "2026-08-01T00:00:00+00:00",
    )
    current = RecordingSession(
        "new",
        "New",
        tmp_path / "new",
        "daily",
        "active",
        "2026-08-02T00:00:00+00:00",
    )
    engine = LifecycleCaptureEngine.__new__(LifecycleCaptureEngine)
    engine.session = previous
    notifications = []
    engine.on_session_change = notifications.append

    monkeypatch.setattr(
        SessionCaptureEngine,
        "_rollover_if_needed",
        lambda instance: setattr(instance, "session", current),
    )

    engine._rollover_if_needed()

    assert engine.session == current
    assert notifications == [current]
