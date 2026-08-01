from pathlib import Path
from threading import Event

import pytest

from screentl.video import VideoCancelled, _write_video_atomically


class FakeClip:
    def __init__(self, payload=b"new", error=None):
        self.payload = payload
        self.error = error
        self.duration = None

    def set_duration(self, duration):
        self.duration = duration
        return self

    def write_videofile(self, filename, **_kwargs):
        Path(filename).write_bytes(self.payload)
        if self.error is not None:
            raise self.error


def test_atomic_video_output_replaces_existing_file_only_after_success(tmp_path):
    output = tmp_path / "video.mp4"
    output.write_bytes(b"old")

    result = _write_video_atomically(FakeClip(), 2.0, output)

    assert result == output
    assert output.read_bytes() == b"new"
    assert list(tmp_path.glob(".*.part.mp4")) == []


def test_failed_video_render_preserves_existing_output(tmp_path):
    output = tmp_path / "video.mp4"
    output.write_bytes(b"old")

    with pytest.raises(RuntimeError, match="encode failed"):
        _write_video_atomically(
            FakeClip(error=RuntimeError("encode failed")),
            2.0,
            output,
        )

    assert output.read_bytes() == b"old"
    assert list(tmp_path.glob(".*.part.mp4")) == []


def test_cancelled_video_render_does_not_touch_existing_output(tmp_path):
    output = tmp_path / "video.mp4"
    output.write_bytes(b"old")
    cancel_event = Event()
    cancel_event.set()

    with pytest.raises(VideoCancelled):
        _write_video_atomically(
            FakeClip(),
            2.0,
            output,
            cancel_event=cancel_event,
        )

    assert output.read_bytes() == b"old"
