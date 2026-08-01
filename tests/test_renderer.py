from pathlib import Path
from threading import Event

import pytest
from PIL import Image

from screentl.journal_repository import JournalRepository
from screentl.renderer import FFmpegSessionRenderer, RenderCancelled, RenderOptions


def make_session(repo, root):
    session = repo.create_session(root, "Render")
    for index, color in enumerate(("red", "blue")):
        path = session.frames_path / f"frame-{index}.png"
        Image.new("RGB", (101, 61), color).save(path)
        frame = repo.add_frame(session.id, path, captured_at=f"2026-08-02T0{index}:00:00+00:00")
        repo.set_frame_duration(frame.id, 0.5)
    return session


def test_renderer_commits_versioned_output_and_updates_job(tmp_path, monkeypatch):
    repo = JournalRepository(tmp_path / "sessions.db")
    session = make_session(repo, tmp_path / "data")
    renderer = FFmpegSessionRenderer(repo, executable="ffmpeg")

    def fake_run(command, _duration, _job_id, _cancel, on_progress):
        Path(command[-1]).write_bytes(b"video")
        on_progress(0.5)

    monkeypatch.setattr(renderer, "_run_process", fake_run)
    outputs = renderer.render(session.id, RenderOptions())

    assert len(outputs) == 1
    assert outputs[0].suffix == ".mp4"
    assert outputs[0].read_bytes() == b"video"
    assert not list(session.output_path.glob("*.part.mp4"))


def test_renderer_split_by_hour_creates_multiple_outputs(tmp_path, monkeypatch):
    repo = JournalRepository(tmp_path / "sessions.db")
    session = make_session(repo, tmp_path / "data")
    renderer = FFmpegSessionRenderer(repo, executable="ffmpeg")

    monkeypatch.setattr(
        renderer,
        "_run_process",
        lambda command, *_args: Path(command[-1]).write_bytes(b"video"),
    )
    outputs = renderer.render(session.id, RenderOptions(split_by_hour=True))

    assert len(outputs) == 2
    assert len({path.name for path in outputs}) == 2


def test_renderer_command_supports_gif_and_loop_audio(tmp_path):
    repo = JournalRepository(tmp_path / "sessions.db")
    renderer = FFmpegSessionRenderer(repo, executable="ffmpeg")
    concat = tmp_path / "frames.ffconcat"
    concat.touch()
    audio = tmp_path / "music.mp3"
    audio.touch()

    gif = renderer._build_command(
        concat,
        tmp_path / "out.gif",
        2.0,
        RenderOptions(output_format="gif"),
        tmp_path,
    )
    assert "-filter_complex" in gif
    assert "palettegen" in gif[gif.index("-filter_complex") + 1]

    loop = renderer._build_command(
        concat,
        tmp_path / "out.mp4",
        2.0,
        RenderOptions(audio_mode="loop", audio_path=audio),
        tmp_path,
    )
    assert loop[loop.index("-stream_loop") + 1] == "-1"
    assert "-filter:a" in loop


def test_renderer_cancel_preserves_no_partial_output(tmp_path, monkeypatch):
    repo = JournalRepository(tmp_path / "sessions.db")
    session = make_session(repo, tmp_path / "data")
    renderer = FFmpegSessionRenderer(repo, executable="ffmpeg")
    cancel = Event()

    def cancelled(command, _duration, _job_id, cancel_event, _progress):
        Path(command[-1]).write_bytes(b"partial")
        cancel_event.set()
        raise RenderCancelled("cancelled")

    monkeypatch.setattr(renderer, "_run_process", cancelled)
    with pytest.raises(RenderCancelled):
        renderer.render(session.id, RenderOptions(), cancel_event=cancel)

    assert not list(session.output_path.glob("*.part.mp4"))
    assert not list(session.output_path.glob("*.mp4"))
