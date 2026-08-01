"""Desktop application coordination and shutdown policy."""

from __future__ import annotations

from tkinter import messagebox

from .ui import ScreenshotTimeLapseApp


class DesktopApplication(ScreenshotTimeLapseApp):
    """Apply the three-way shutdown policy around active render jobs."""

    def exit_app(self) -> None:
        if self.is_exiting:
            return

        cancel_render = False
        if self.render_service.is_running:
            decision = messagebox.askyesnocancel(
                "视频仍在生成",
                "视频任务尚未完成。\n\n"
                "选择“是”将等待任务完成后退出；\n"
                "选择“否”将取消任务并退出；\n"
                "选择“取消”将返回程序。",
            )
            if decision is None:
                return
            cancel_render = decision is False

        self.is_exiting = True
        self.status_var.set("正在安全退出…")
        self.start_button.configure(state="disabled")
        self.video_button.configure(state="disabled")
        self.pause_button.configure(state="disabled")
        self.stop_button.configure(state="disabled")
        self.cancel_video_button.configure(state="disabled")
        self._save_config()
        self.capture_service.stop()
        if cancel_render:
            self.render_service.cancel()


def run_desktop_app() -> None:
    app = DesktopApplication()
    app.mainloop()
