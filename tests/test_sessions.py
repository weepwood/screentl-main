import json
from pathlib import Path

from PIL import Image

from screentl.journal_repository import JournalRepository
from screentl.sessions import SessionRepository
from screentl.timeline import TimelineService


def create_image(path: Path, color="red", size=(160, 90)) -> Path:
    Image.new("RGB", size, color).save(path)
    return path


def test_session_frames_duplicate_detection_and_summary(tmp_path):
    repo = SessionRepository(tmp_path / "sessions.db")
    session = repo.create_session(tmp_path / "data", "Demo")
    first = create_image(session.frames_path / "first.png")
    second = create_image(session.frames_path / "second.png")

    frame1 = repo.add_frame(session.id, first, app_name="Editor")
    frame2 = repo.add_frame(session.id, second, app_name="Editor")

    assert frame1.sequence == 0
    assert frame2.sequence == 1
    assert frame2.duplicate_of == frame1.id
    summary = repo.session_summary(session.id)
    assert summary["frames"] == 2
    assert summary["duplicates"] == 1
    assert summary["top_apps"] == [("Editor", 2)]


def test_timeline_mutations_contact_sheet_and_preview(tmp_path):
    repo = SessionRepository(tmp_path / "sessions.db")
    session = repo.create_session(tmp_path / "data", "Timeline")
    first = repo.add_frame(session.id, create_image(session.frames_path / "one.png", "blue"))
    second = repo.add_frame(session.id, create_image(session.frames_path / "two.png", "green"))
    repo.set_frames_excluded([second.id], True)
    repo.set_frame_duration(first.id, 2.5)
    repo.set_frame_masks(first.id, [(10, 10, 20, 20)])
    repo.add_chapter(session.id, first.id, "Start")

    timeline = TimelineService(repo)
    page = timeline.page(session.id, limit=10)
    assert page.total == 2
    assert sum(len(group.frames) for group in page.groups) == 2
    assert timeline.estimate_seconds(session.id) == 2.5

    sheet = timeline.build_contact_sheet(session.id, tmp_path / "sheet.jpg")
    preview = timeline.build_html_preview(session.id, tmp_path / "preview" / "timeline.html")
    assert sheet.is_file()
    assert preview.is_file()
    assert "Timeline" in preview.read_text(encoding="utf-8")
    assert list(session.thumbnails_path.glob("*.jpg"))


def test_manifest_archive_cleanup_and_render_recovery(tmp_path):
    repo = JournalRepository(tmp_path / "sessions.db")
    session = repo.create_session(tmp_path / "data", "Archive")
    repo.add_frame(session.id, create_image(session.frames_path / "frame.png"))
    job = repo.create_render_job(session.id, "mp4", {"codec": "h264"})

    assert repo.recover_render_jobs() == 1
    manifest = repo.export_session_manifest(session.id, tmp_path / "manifest.json")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["session"]["id"] == session.id
    assert payload["frames"][0]["path"].endswith("frame.png")

    archive = repo.archive_session(session.id, tmp_path / "archives")
    assert archive.is_file()
    assert job
    removed = repo.cleanup(retention_days=0)
    assert session.root_path in removed
    assert repo.get_session(session.id) is None


def test_soft_delete_and_keep_original_file_option(tmp_path):
    repo = SessionRepository(tmp_path / "sessions.db")
    session = repo.create_session(tmp_path / "data", "Delete")
    image = create_image(session.frames_path / "frame.png")
    frame = repo.add_frame(session.id, image)

    assert repo.delete_frames([frame.id], delete_files=False) == 1
    assert image.exists()
    assert repo.get_frame(frame.id) is None
