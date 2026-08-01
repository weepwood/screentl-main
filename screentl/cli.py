"""Command-line adapters built on the same application services as the GUI."""

from __future__ import annotations

import time
from pathlib import Path

from .events import AppEvent, EventBus, EventKind
from .models import CaptureConfig, RenderConfig, TaskState
from .services import CaptureService, RenderService


def _print_event(event: AppEvent) -> Path | None:
    if event.kind in {EventKind.LOG, EventKind.ERROR} and event.message:
        print(event.message)
    elif event.kind is EventKind.CAPTURED:
        print(f"Captured: {event.data}")
    elif event.kind is EventKind.RENDER_PROGRESS:
        print(f"Render progress: {int(float(event.data) * 100)}%")
    elif event.kind is EventKind.RENDER_FINISHED:
        output = Path(event.data)
        print(f"Video written to {output}")
        return output
    return None


def _drain_events(events: EventBus) -> Path | None:
    output = None
    for event in events.drain(500):
        event_output = _print_event(event)
        if event_output is not None:
            output = event_output
    return output


def run_capture(config: CaptureConfig) -> int:
    """Run capture until Ctrl+C and return a process-style exit code."""
    config.validate()
    events = EventBus()
    service = CaptureService(events)
    service.start(config)

    try:
        while service.is_running:
            service.join(0.2)
            _drain_events(events)
    except KeyboardInterrupt:
        print("Stopping capture...")
        service.stop()
    finally:
        service.join()
        _drain_events(events)

    return 1 if service.state is TaskState.FAILED else 0


def run_render(config: RenderConfig) -> tuple[int, Path | None]:
    """Run one render job and return an exit code plus output path."""
    config.validate()
    events = EventBus()
    service = RenderService(events)
    service.start(config)
    output = None

    try:
        while service.is_running:
            service.join(0.2)
            output = _drain_events(events) or output
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("Cancelling video render...")
        service.cancel()
    finally:
        service.join()
        output = _drain_events(events) or output

    failed = service.state in {TaskState.FAILED, TaskState.CANCELLED}
    return (1 if failed else 0), output
