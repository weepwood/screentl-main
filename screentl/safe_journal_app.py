"""Race-safe desktop coordination for recording sessions."""

from __future__ import annotations

from pathlib import Path
from tkinter import messagebox

from .application import DesktopApplication
from .events import AppEvent, EventKind
from .journal_app import JournalApplication
from .lifecycle import AccurateTimelineService, LifecycleCaptureEngine
from .models import TaskState
from .renderer import RenderCancelled, RenderOptions
from .services import CaptureService
from .sessions import RecordingSession
from .video import VideoCancelled


class SafeJournalApplication(JournalApplication):
    """Bind every background task to the session that started it."""

    def __init__(self) -> None:
        self._capture_session_id: str | None = None
        self._pending_complete_session_id: str | None = None
        self._render_session_id: str | None = None
        super().__init__()
        self.timeline_service = AccurateTimelineService(self.repository)

    def _session_change_blocked(self, action: str) -> bool:
        active_tasks = []
        if self.capture_service.is_running:
            active_tasks.append("截图")
        if self.render_service.is_running:
            active_tasks.append("视频输出")
        if not active_tasks:
            return False
        messagebox.showinfo(
            "任务仍在运行",
            f"当前{'和'.join(active_tasks)}任务尚未结束，无法{action}。请先停止或取消任务。",
            parent=self,
        )
        return True

    def new_session(self, default_name: str = "") -> None:
        if self._session_change_blocked("新建会话"):
            return
        super().new_session(default_name)

    def continue_latest_session(self) -> None:
        if self._session_change_blocked("切换会话"):
            return
        super().continue_latest_session()
        self._refresh_current_session()

    def archive_session(self) -> None:
        if self._session_change_blocked("归档会话"):
            return
        super().archive_session()
        self._refresh_current_session()

    def complete_session(self) -> None:
        if self.current_session is None:
            return
        session_id = self.current_session.id
        if self.capture_service.is_running:
            self._pending_complete_session_id = session_id
            self.status_var.set("正在结束当前会话…")
            self._log("正在停止截图，线程结束后将会话标记为已完成")
            self.capture_service.stop()
            return
        self.repository.set_session_status(session_id, "completed")
        self._refresh_current_session()
        self._sync_session_ui()
        self._log("当前会话已结束")

    def _refresh_current_session(self) -> None:
        if self.current_session is None:
            return
        refreshed = self.repository.get_session(self.current_session.id)
        if refreshed is not None:
            self.current_session = refreshed

    def _sync_session_ui(self) -> None:
        self._refresh_current_session()
        super()._sync_session_ui()

    def _publish_session_change(self, session: RecordingSession) -> None:
        self.event_bus.publish(
            AppEvent(
                EventKind.SESSION_CHANGED,
                "capture",
                message=f"已跨日切换到会话：{session.name}",
                data=session,
            )
        )

    def _handle_event(self, event: AppEvent) -> None:
        if event.kind is EventKind.SESSION_CHANGED:
            session = event.data
            if isinstance(session, RecordingSession):
                self.current_session = session
                self._capture_session_id = session.id
                self.folder_var.set(str(session.frames_path))
                self._sync_session_ui()
                self._log(event.message)
            return
        super()._handle_event(event)

    def start_capture(self) -> None:
        if self.capture_service.is_running:
            return
        try:
            self._ensure_session()
        except RuntimeError as exc:
            messagebox.showerror("无法开始", str(exc), parent=self)
            return
        if self.current_session is None:
            return

        session = self.current_session
        self.repository.set_session_status(session.id, "active")
        self.current_session = self.repository.get_session(session.id) or session
        self._capture_session_id = session.id
        self._pending_complete_session_id = None
        engine = LifecycleCaptureEngine(
            repository=self.repository,
            session=self.current_session,
            options=self.capture_options,
            privacy=self.privacy_guard,
            on_skip=self._capture_skip,
            on_session_change=self._publish_session_change,
        )
        self.capture_service = CaptureService(
            self.event_bus,
            capture_func=engine,
        )
        self.folder_var.set(str(self.current_session.frames_path))
        DesktopApplication.start_capture(self)
        if not self.capture_service.is_running and self.capture_service.state is TaskState.IDLE:
            self._capture_session_id = None

    def start_video(self) -> None:
        if self.render_service.is_running:
            return
        if self.current_session is not None:
            self._render_session_id = self.current_session.id
        super().start_video()
        if not self.render_service.is_running and self.render_service.state is TaskState.IDLE:
            self._render_session_id = None

    def _render_session_adapter(
        self,
        folder: str,
        fps: int,
        audio_loc: str,
        text: str,
        output_name: str,
        cancel_event,
        on_progress,
    ) -> Path:
        del folder, text, output_name
        session_id = self._render_session_id
        if session_id is None or self.repository.get_session(session_id) is None:
            raise RuntimeError("render session is unavailable")
        options = self._next_render_options or RenderOptions(
            fps=fps,
            audio_mode="random" if audio_loc and Path(audio_loc).is_dir() else "none",
            audio_folder=Path(audio_loc) if audio_loc else None,
        )
        self._next_render_options = None
        try:
            outputs = self.session_renderer.render(
                session_id,
                options,
                cancel_event=cancel_event,
                on_progress=on_progress,
            )
        except RenderCancelled as exc:
            raise VideoCancelled(str(exc)) from exc
        return outputs[0]

    def _apply_task_state(self, source: str, state: TaskState) -> None:
        DesktopApplication._apply_task_state(self, source, state)
        if source == "capture":
            session_id = self._capture_session_id
            if session_id is None:
                return
            if state is TaskState.RUNNING:
                self.repository.set_session_status(session_id, "active")
            elif state is TaskState.PAUSED:
                self.repository.set_session_status(session_id, "paused")
            elif state in {TaskState.COMPLETED, TaskState.FAILED}:
                final_status = (
                    "completed"
                    if self._pending_complete_session_id == session_id
                    else "paused"
                )
                self.repository.set_session_status(session_id, final_status)
                if self.current_session is not None and self.current_session.id == session_id:
                    self._refresh_current_session()
                    self._sync_session_ui()
                if final_status == "completed":
                    self._log("当前会话已结束")
                self._capture_session_id = None
                self._pending_complete_session_id = None
        elif source == "render" and state in {
            TaskState.COMPLETED,
            TaskState.CANCELLED,
            TaskState.FAILED,
        }:
            self._render_session_id = None


def run_safe_journal_app() -> None:
    app = SafeJournalApplication()
    app.mainloop()
