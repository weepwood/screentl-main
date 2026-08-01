"""Background capture and render services."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .events import AppEvent, EventBus, EventKind
from .models import CaptureConfig, RenderConfig, TaskState
from .utils import screenshot
from .video import VideoCancelled, make_video


class CaptureService:
    def __init__(
        self,
        events: EventBus,
        capture_func: Callable[..., Any] = screenshot,
    ) -> None:
        self.events = events
        self.capture_func = capture_func
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()
        self._thread: threading.Thread | None = None
        self._state = TaskState.IDLE
        self._lock = threading.Lock()

    @property
    def state(self) -> TaskState:
        with self._lock:
            return self._state

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _set_state(self, state: TaskState) -> None:
        with self._lock:
            self._state = state
        self.events.publish(
            AppEvent(EventKind.TASK_STATE, "capture", data=state.value)
        )

    def start(self, config: CaptureConfig) -> None:
        config.validate()
        if self.is_running:
            return
        self.stop_event.clear()
        self.pause_event.set()
        self._thread = threading.Thread(
            target=self._run,
            args=(config,),
            name="screentl-capture",
            daemon=False,
        )
        self._thread.start()

    def _run(self, config: CaptureConfig) -> None:
        self._set_state(TaskState.RUNNING)
        self.events.publish(
            AppEvent(
                EventKind.LOG,
                "capture",
                f"开始截屏：{config.folder}，间隔 {config.interval} 秒",
            )
        )
        try:
            self.capture_func(
                folder=str(config.folder),
                interval=config.interval,
                stop_event=self.stop_event,
                pause_event=self.pause_event,
                on_capture=self._on_capture,
            )
        except Exception as exc:
            self._set_state(TaskState.FAILED)
            self.events.publish(
                AppEvent(EventKind.ERROR, "capture", f"截屏失败：{exc}", exc)
            )
        else:
            self._set_state(TaskState.COMPLETED)
            self.events.publish(AppEvent(EventKind.LOG, "capture", "截屏已停止"))

    def _on_capture(self, path: Path) -> None:
        self.events.publish(AppEvent(EventKind.CAPTURED, "capture", data=path))

    def pause(self) -> None:
        if not self.is_running or self.state is not TaskState.RUNNING:
            return
        self.pause_event.clear()
        self._set_state(TaskState.PAUSED)

    def resume(self) -> None:
        if not self.is_running or self.state is not TaskState.PAUSED:
            return
        self.pause_event.set()
        self._set_state(TaskState.RUNNING)

    def stop(self) -> None:
        if not self.is_running:
            return
        self._set_state(TaskState.STOPPING)
        self.stop_event.set()
        self.pause_event.set()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)


class RenderService:
    def __init__(
        self,
        events: EventBus,
        render_func: Callable[..., Path] = make_video,
    ) -> None:
        self.events = events
        self.render_func = render_func
        self.cancel_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._state = TaskState.IDLE
        self._lock = threading.Lock()

    @property
    def state(self) -> TaskState:
        with self._lock:
            return self._state

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _set_state(self, state: TaskState) -> None:
        with self._lock:
            self._state = state
        self.events.publish(
            AppEvent(EventKind.TASK_STATE, "render", data=state.value)
        )

    def start(self, config: RenderConfig) -> None:
        config.validate()
        if self.is_running:
            return
        self.cancel_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(config,),
            name="screentl-render",
            daemon=False,
        )
        self._thread.start()

    def _run(self, config: RenderConfig) -> None:
        self._set_state(TaskState.RUNNING)
        self.events.publish(
            AppEvent(EventKind.LOG, "render", f"开始生成视频：{config.folder}")
        )
        try:
            output = self.render_func(
                folder=str(config.folder),
                fps=config.fps,
                audio_loc=str(config.audio_folder or ""),
                text=config.title,
                output_name=config.output_name,
                cancel_event=self.cancel_event,
                on_progress=self._on_progress,
            )
        except VideoCancelled:
            self._set_state(TaskState.CANCELLED)
            self.events.publish(AppEvent(EventKind.LOG, "render", "视频生成已取消"))
        except Exception as exc:
            self._set_state(TaskState.FAILED)
            self.events.publish(
                AppEvent(EventKind.ERROR, "render", f"视频生成失败：{exc}", exc)
            )
        else:
            self._set_state(TaskState.COMPLETED)
            self.events.publish(
                AppEvent(EventKind.RENDER_FINISHED, "render", data=output)
            )

    def _on_progress(self, progress: float) -> None:
        self.events.publish(
            AppEvent(
                EventKind.RENDER_PROGRESS,
                "render",
                data=max(0.0, min(1.0, progress)),
            )
        )

    def cancel(self) -> None:
        if not self.is_running:
            return
        self._set_state(TaskState.STOPPING)
        self.cancel_event.set()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)
