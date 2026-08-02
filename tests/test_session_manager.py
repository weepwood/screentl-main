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


def test_session_selection_keeps_only_one_active_session(tmp_path):
    repository = JournalRepository(tmp_path / "sessions.db")
    alpha = repository.create_session(tmp_path / "data", "Alpha")
    beta = repository.create_session(tmp_path / "data", "Beta")

    assert repository.get_session(alpha.id).status == "paused"
    assert repository.get_session(beta.id).status == "active"

    selected = repository.select_session(alpha.id, resume=True)
    assert selected is not None
    assert selected.status == "active"
    assert repository.get_session(beta.id).status == "paused"
    assert len(repository.list_session_overviews(status="active")) == 1

    viewed = repository.select_session(beta.id, resume=False)
    assert viewed is not None
    assert viewed.status == "paused"
    assert repository.list_session_overviews(status="active") == []


def test_archived_session_cannot_be_resumed(tmp_path):
    repository = JournalRepository(tmp_path / "sessions.db")
    session = repository.create_session(tmp_path / "data", "Archived")
    repository.set_session_status(session.id, "archived")

    with pytest.raises(ValueError, match="archived sessions cannot be resumed"):
        repository.select_session(session.id, resume=True)


def test_session_overviews_reject_unknown_status(tmp_path):
    repository = JournalRepository(tmp_path / "sessions.db")

    with pytest.raises(ValueError, match="unsupported session status"):
        repository.list_session_overviews(status="unknown")


def test_format_local_time_handles_empty_invalid_and_aware_values():
    assert format_local_time(None) == "—"
    assert format_local_time("not-a-date") == "not-a-date"

    result = format_local_time("2026-08-02T05:30:00+00:00")
    assert len(result) == 19
    assert result[:7] == "2026-08"
    assert result[8:10] in {"01", "02"}
    assert result[10] == " "
