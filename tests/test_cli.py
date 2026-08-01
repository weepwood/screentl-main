from pathlib import Path

from screentl import cli
from screentl.events import AppEvent, EventKind
from screentl.models import CaptureConfig, RenderConfig, TaskState


class FakeCaptureService:
    def __init__(self, events):
        self.events = events
        self.state = TaskState.IDLE
        self.is_running = False
        self.started = None

    def start(self, config):
        self.started = config
        self.state = TaskState.RUNNING
        self.is_running = True
        self.events.publish(
            AppEvent(EventKind.CAPTURED, "capture", data=config.folder / "frame.png")
        )

    def join(self, _timeout=None):
        self.is_running = False
        self.state = TaskState.COMPLETED

    def stop(self):
        self.is_running = False
        self.state = TaskState.COMPLETED


class FakeRenderService:
    def __init__(self, events):
        self.events = events
        self.state = TaskState.IDLE
        self.is_running = False
        self.started = None

    def start(self, config):
        self.started = config
        self.state = TaskState.RUNNING
        self.is_running = True
        self.events.publish(AppEvent(EventKind.RENDER_PROGRESS, "render", data=0.5))
        self.events.publish(
            AppEvent(EventKind.RENDER_FINISHED, "render", data=config.folder / "video.mp4")
        )

    def join(self, _timeout=None):
        self.is_running = False
        self.state = TaskState.COMPLETED

    def cancel(self):
        self.is_running = False
        self.state = TaskState.CANCELLED


def test_run_capture_uses_shared_service(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "CaptureService", FakeCaptureService)

    result = cli.run_capture(CaptureConfig(tmp_path, 5))

    assert result == 0
    assert "Captured:" in capsys.readouterr().out


def test_run_render_returns_output(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "RenderService", FakeRenderService)

    exit_code, output = cli.run_render(RenderConfig(tmp_path, 25))

    assert exit_code == 0
    assert output == Path(tmp_path / "video.mp4")
    text = capsys.readouterr().out
    assert "Render progress: 50%" in text
    assert "Video written to" in text


def test_print_event_reports_log_and_error(capsys):
    assert cli._print_event(AppEvent(EventKind.LOG, "test", "hello")) is None
    assert cli._print_event(AppEvent(EventKind.ERROR, "test", "failed")) is None

    assert capsys.readouterr().out.splitlines() == ["hello", "failed"]
