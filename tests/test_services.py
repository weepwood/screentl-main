import time
from pathlib import Path

from screentl.events import EventBus, EventKind
from screentl.models import CaptureConfig, RenderConfig, TaskState
from screentl.services import CaptureService, RenderService
from screentl.video import VideoCancelled


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not reached")


def test_capture_service_stops_and_emits_state(tmp_path):
    def fake_capture(**kwargs):
        kwargs["on_capture"](tmp_path / "screenshot_0.png")
        kwargs["stop_event"].wait(1)

    events = EventBus()
    service = CaptureService(events, capture_func=fake_capture)
    service.start(CaptureConfig(tmp_path, 1))
    wait_until(lambda: service.state is TaskState.RUNNING)

    service.stop()
    service.join(2)

    drained = events.drain(20)
    assert not service.is_running
    assert any(event.kind is EventKind.CAPTURED for event in drained)
    assert service.state is TaskState.COMPLETED


def test_render_service_cancels_cooperatively(tmp_path):
    def fake_render(**kwargs):
        cancel_event = kwargs["cancel_event"]
        if not cancel_event.wait(1):
            return Path(tmp_path / "video.mp4")
        raise VideoCancelled()

    events = EventBus()
    service = RenderService(events, render_func=fake_render)
    service.start(RenderConfig(tmp_path, 25))
    wait_until(lambda: service.state is TaskState.RUNNING)

    service.cancel()
    service.join(2)

    assert not service.is_running
    assert service.state is TaskState.CANCELLED
