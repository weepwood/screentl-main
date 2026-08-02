import datetime as dt
from pathlib import Path

import pytest
from PIL import Image

from screentl.journal_repository import JournalRepository
from screentl.session_manager import format_local_time


def create_image(path: Path, color: str) -> Path:
    Image.new("RGB", (80, 45), color).save(path)
    return path


def test_session_overviews_aggregate_kept_excluded_and_deleted_frames(tmp_path):
    repository = JournalRepository(tmp_path / "sessions.db")
    alpha = repository.create_session(tmp_path / "data", "Alpha Project")
    beta = repository.create_session(tmp_path / "data", "Beta Review")

    kept = repository.add_frame(
        alpha.id,
        create_image(alpha.frames_path / "kept.png", "red"),
    )
    excluded = repository.add_frame(
        alpha.id,
        create_image(alpha.frames_path / "excluded.png", "blue"),
    )
    deleted = repository.add_frame(
        alpha.id,
        create_image(alpha.frames_path / "deleted.png", "green"),
    )
    repository.set_frame_duration(kept.id, 2.5)
    repository.set_frame_duration(excluded.id, 7.5)
    repository.set_frame_duration(deleted.id, 20.0)
    repository.set_frames_excluded([excluded.id], True)
    repository.delete_frames([deleted.id], delete_files=False)
    repository.set_session_status(beta.id, "completed")

    overviews = repository.list_session_overviews()
    alpha_overview = next(item for item in overviews if item.id == alpha.id)
    beta_overview = next(item for item in overviews if item.id == beta.id)

    assert alpha_overview.frames == 2
    assert alpha_overview.kept_frames == 1
    assert alpha_overview.excluded_frames == 1
    assert alpha_overview.estimated_video_seconds == 2.5
    assert beta_overview.status == "completed"
    assert beta_overview.frames == 0


def test_session_overviews_support_name_search_and_status_filter(tmp_path):
    repository = JournalRepository(tmp_path / "sessions.db")
    alpha = repository.create_session(tmp_path / "data", "Alpha Project")
    beta = repository.create_session(tmp_path / "data", "Beta Project")
    repository.set_session_status(alpha.id, "paused")
    repository.set_session_status(beta.id, "archived")

    search_results = repository.list_session_overviews(query="alpha")
    archived_results = repository.list_session_overviews(status="archived")

    assert [item.id for item in search_results] == [alpha.id]
    assert [item.id for item in archived_results] == [beta.id]


def test_session_overviews_reject_unknown_status(tmp_path):
    repository = JournalRepository(tmp_path / "sessions.db")

    with pytest.raises(ValueError, match="unsupported session status"):
        repository.list_session_overviews(status="unknown")


def test_format_local_time_handles_empty_invalid_and_aware_values():
    assert format_local_time(None) == "—"
    assert format_local_time("not-a-date") == "not-a-date"

    value = "2026-08-02T05:30:00+00:00"
    result = format_local_time(value)
    parsed = dt.datetime.strptime(result, "%Y-%m-%d %H:%M:%S")
    assert parsed.year == 2026
    assert parsed.month == 8
    assert parsed.day in {1, 2}
