"""Tkinter desktop UI backed by thread-safe application services."""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .events import AppEvent, EventBus, EventKind
from .models import CaptureConfig, RenderConfig, TaskState
from .services import CaptureService, RenderService
from .settings import AppSettings, SettingsRepository
from .windows import open_folder, set_startup

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    pystray = None
    Image = None
    ImageDraw = None


APP_NAME = "Screenshot Time-lapse"


class ScreenshotTimeLapseApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("800x690")
        self.minsize(720, 590)

        self.event_bus = EventBus()
        self.capture_service = CaptureService(self.event_bus)
        self.render_service = RenderService(self.event_bus)
        self.settings_repository = SettingsRepository()
        self.settings = self.settings_repository.load()

        self.capture_count = 0
        self.last_capture: Path | None = None
        self.tray_icon = None
        self.is_exiting = False
        self._destroyed = False

        self.folder_var = tk.StringVar(value=self.settings.folder)
        self.interval_var = tk.StringVar(value=str(self.settings.interval))
        self.fps_var = tk.StringVar(value=str(self.settings.fps))
        self.audio_var = tk.StringVar(value=self.settings.audio)
        self.text_var = tk.StringVar(value=self.settings.text)
        self.startup_var = tk.BooleanVar(value=self.settings.startup)
        self.minimize_to_tray_var = tk.BooleanVar(
            value=self.settings.minimize_to_tray
        )
        self.status_var = tk.StringVar(value="就绪")
        self.detail_var = tk.StringVar(value="尚未开始截屏")
        self.status_var.trace_add("write", self._update_tray_title)

        self._configure_style()
        self._build_ui()
        self._start_tray()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll_events)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure(
            "Section.TLabelframe.Label",
            font=("Segoe UI", 10, "bold"),
        )
        style.configure("Accent.TButton", padding=(12, 7))

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=20)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(4, weight=1)

        ttk.Label(root, text=APP_NAME, style="Title.TLabel").grid(
            row=0,
            column=0,
            sticky="w",
        )
        ttk.Label(
            root,
            text="定时记录工作过程，生成可回顾的延时视频",
        ).grid(row=1, column=0, sticky="w", pady=(4, 16))

        capture = ttk.LabelFrame(
            root,
            text="定时截屏",
            style="Section.TLabelframe",
            padding=12,
        )
        capture.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        capture.columnconfigure(1, weight=1)
        self._path_row(capture, 0, "保存目录", self.folder_var)
        ttk.Label(capture, text="间隔（秒）").grid(
            row=1,
            column=0,
            sticky="w",
            pady=(10, 0),
        )
        ttk.Spinbox(
            capture,
            from_=1,
            to=86400,
            textvariable=self.interval_var,
            width=12,
        ).grid(row=1, column=1, sticky="w", pady=(10, 0))

        capture_buttons = ttk.Frame(capture)
        capture_buttons.grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(14, 0),
        )
        self.start_button = ttk.Button(
            capture_buttons,
            text="开始截屏",
            command=self.start_capture,
            style="Accent.TButton",
        )
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(
            capture_buttons,
            text="停止截屏",
            command=self.stop_capture,
            state="disabled",
        )
        self.stop_button.pack(side="left", padx=(8, 0))
        self.pause_button = ttk.Button(
            capture_buttons,
            text="暂停",
            command=self.toggle_capture_pause,
            state="disabled",
        )
        self.pause_button.pack(side="left", padx=(8, 0))
        ttk.Button(
            capture_buttons,
            text="打开目录",
            command=self.open_capture_folder,
        ).pack(side="left", padx=(8, 0))

        video = ttk.LabelFrame(
            root,
            text="生成视频",
            style="Section.TLabelframe",
            padding=12,
        )
        video.grid(row=3, column=0, sticky="new", pady=(0, 12))
        video.columnconfigure(1, weight=1)
        self._path_row(video, 0, "截图目录", self.folder_var, browse=False)
        self._path_row(video, 1, "音乐目录", self.audio_var)
        ttk.Label(video, text="视频帧率").grid(
            row=2,
            column=0,
            sticky="w",
            pady=(10, 0),
        )
        ttk.Spinbox(
            video,
            from_=1,
            to=120,
            textvariable=self.fps_var,
            width=12,
        ).grid(row=2, column=1, sticky="w", pady=(10, 0))
        ttk.Label(video, text="标题文字").grid(
            row=3,
            column=0,
            sticky="w",
            pady=(10, 0),
        )
        ttk.Entry(video, textvariable=self.text_var).grid(
            row=3,
            column=1,
            sticky="ew",
            pady=(10, 0),
        )

        video_buttons = ttk.Frame(video)
        video_buttons.grid(
            row=4,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(14, 0),
        )
        self.video_button = ttk.Button(
            video_buttons,
            text="生成 video.mp4",
            command=self.start_video,
            style="Accent.TButton",
        )
        self.video_button.pack(side="left")
        self.cancel_video_button = ttk.Button(
            video_buttons,
            text="取消生成",
            command=self.cancel_video,
            state="disabled",
        )
        self.cancel_video_button.pack(side="left", padx=(8, 0))
        ttk.Button(
            video_buttons,
            text="打开设置",
            command=self.show_settings,
        ).pack(side="left", padx=(8, 0))

        log_frame = ttk.LabelFrame(
            root,
            text="运行日志",
            style="Section.TLabelframe",
            padding=8,
        )
        log_frame.grid(row=4, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(
            log_frame,
            height=8,
            state="disabled",
            wrap="word",
            background="#f7f7f7",
            relief="flat",
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(
            log_frame,
            orient="vertical",
            command=self.log_text.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

        status = ttk.Frame(root)
        status.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        status.columnconfigure(0, weight=1)
        ttk.Label(
            status,
            textvariable=self.status_var,
            foreground="#333",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            status,
            textvariable=self.detail_var,
            foreground="#666",
        ).grid(row=0, column=1, sticky="e")

    def _path_row(
        self,
        parent,
        row: int,
        label: str,
        variable: tk.StringVar,
        browse: bool = True,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w")
        ttk.Entry(parent, textvariable=variable).grid(
            row=row,
            column=1,
            sticky="ew",
            padx=(12, 8),
        )
        if browse:
            ttk.Button(
                parent,
                text="选择…",
                command=lambda: self._choose_folder(variable),
            ).grid(row=row, column=2, sticky="e")

    def _choose_folder(self, variable: tk.StringVar) -> None:
        selected = filedialog.askdirectory(initialdir=variable.get() or ".")
        if selected:
            variable.set(selected)

    def _current_settings(self) -> AppSettings:
        return AppSettings(
            folder=self.folder_var.get().strip(),
            interval=int(self.interval_var.get()),
            fps=int(self.fps_var.get()),
            audio=self.audio_var.get().strip(),
            text=self.text_var.get(),
            startup=self.startup_var.get(),
            minimize_to_tray=self.minimize_to_tray_var.get(),
        )

    def _save_config(self) -> bool:
        try:
            settings = self._current_settings()
            self.settings_repository.save(settings)
        except (OSError, TypeError, ValueError) as exc:
            self._log(f"配置保存失败：{exc}")
            return False
        self.settings = settings
        return True

    def _log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message.rstrip() + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _poll_events(self) -> None:
        if self._destroyed:
            return
        for event in self.event_bus.drain(200):
            self._handle_event(event)
        if self.is_exiting:
            self._poll_shutdown()
        if not self._destroyed:
            self.after(100, self._poll_events)

    def _handle_event(self, event: AppEvent) -> None:
        if event.kind is EventKind.LOG:
            self._log(event.message)
        elif event.kind is EventKind.ERROR:
            self._log(event.message)
            if not self.is_exiting:
                messagebox.showerror("任务失败", event.message)
        elif event.kind is EventKind.CAPTURED:
            self.capture_count += 1
            self.last_capture = Path(event.data)
            self.detail_var.set(f"已截取 {self.capture_count} 张")
            self._log(
                f"已截取第 {self.capture_count} 张：{self.last_capture.name}"
            )
        elif event.kind is EventKind.RENDER_PROGRESS:
            progress = int(float(event.data) * 100)
            self.detail_var.set(f"视频生成进度 {progress}%")
        elif event.kind is EventKind.RENDER_FINISHED:
            output = Path(event.data).resolve()
            self.detail_var.set("视频生成完成")
            self._log(f"视频已生成：{output}")
        elif event.kind is EventKind.TASK_STATE:
            self._apply_task_state(event.source, TaskState(event.data))
        elif event.kind is EventKind.COMMAND:
            self._run_command(str(event.data))

    def _apply_task_state(self, source: str, state: TaskState) -> None:
        if source == "capture":
            active = state in {
                TaskState.RUNNING,
                TaskState.PAUSED,
                TaskState.STOPPING,
            }
            self.start_button.configure(
                state="disabled" if active else "normal"
            )
            self.stop_button.configure(
                state="normal" if active else "disabled"
            )
            self.pause_button.configure(
                state=(
                    "normal"
                    if state in {TaskState.RUNNING, TaskState.PAUSED}
                    else "disabled"
                ),
                text="继续" if state is TaskState.PAUSED else "暂停",
            )
            labels = {
                TaskState.RUNNING: "正在截屏…",
                TaskState.PAUSED: "截屏已暂停",
                TaskState.STOPPING: "正在停止截屏…",
                TaskState.FAILED: "截屏失败",
            }
            self.status_var.set(labels.get(state, "就绪"))
        elif source == "render":
            active = state in {TaskState.RUNNING, TaskState.STOPPING}
            self.video_button.configure(
                state="disabled" if active else "normal"
            )
            self.cancel_video_button.configure(
                state="normal" if state is TaskState.RUNNING else "disabled"
            )
            labels = {
                TaskState.RUNNING: "正在生成视频…",
                TaskState.STOPPING: "正在取消视频生成…",
                TaskState.CANCELLED: "视频生成已取消",
                TaskState.FAILED: "视频生成失败",
            }
            self.status_var.set(labels.get(state, "就绪"))

    def start_capture(self) -> None:
        if self.is_exiting:
            return
        try:
            config = CaptureConfig(
                folder=Path(self.folder_var.get().strip()),
                interval=int(self.interval_var.get()),
            )
            config.validate()
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return
        if not self._save_config():
            return
        self.capture_count = 0
        self.capture_service.start(config)

    def stop_capture(self) -> None:
        self.capture_service.stop()

    def toggle_capture_pause(self) -> None:
        if self.capture_service.state is TaskState.PAUSED:
            self.capture_service.resume()
            self._log("截屏已继续")
        else:
            self.capture_service.pause()
            self._log("截屏已暂停")

    def open_capture_folder(self) -> None:
        folder = Path(self.folder_var.get().strip())
        if not folder.is_dir():
            messagebox.showinfo(
                "目录不存在",
                "截图目录尚未创建。开始截屏后即可打开。",
            )
            return
        try:
            open_folder(folder)
        except OSError as exc:
            messagebox.showerror("打开失败", str(exc))

    def start_video(self) -> None:
        if self.is_exiting:
            return
        try:
            audio_value = self.audio_var.get().strip()
            config = RenderConfig(
                folder=Path(self.folder_var.get().strip()),
                fps=int(self.fps_var.get()),
                audio_folder=Path(audio_value) if audio_value else None,
                title=self.text_var.get(),
            )
            config.validate()
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return
        if not self._save_config():
            return
        self.render_service.start(config)

    def cancel_video(self) -> None:
        if self.render_service.is_running:
            self.render_service.cancel()
            self._log("正在取消视频生成…")

    def show_settings(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("设置")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        draft_folder = tk.StringVar(value=self.folder_var.get())
        draft_interval = tk.StringVar(value=self.interval_var.get())
        draft_audio = tk.StringVar(value=self.audio_var.get())
        draft_startup = tk.BooleanVar(value=self.startup_var.get())
        draft_minimize = tk.BooleanVar(
            value=self.minimize_to_tray_var.get()
        )

        frame = ttk.Frame(dialog, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="截图存放位置").grid(
            row=0,
            column=0,
            sticky="w",
            pady=5,
        )
        ttk.Entry(frame, textvariable=draft_folder, width=46).grid(
            row=0,
            column=1,
            padx=10,
            pady=5,
        )
        ttk.Button(
            frame,
            text="选择…",
            command=lambda: self._choose_folder(draft_folder),
        ).grid(row=0, column=2, pady=5)

        ttk.Label(frame, text="截屏间隔（秒）").grid(
            row=1,
            column=0,
            sticky="w",
            pady=5,
        )
        ttk.Spinbox(
            frame,
            from_=1,
            to=86400,
            textvariable=draft_interval,
            width=12,
        ).grid(row=1, column=1, sticky="w", padx=10, pady=5)

        ttk.Label(frame, text="音乐目录").grid(
            row=2,
            column=0,
            sticky="w",
            pady=5,
        )
        ttk.Entry(frame, textvariable=draft_audio, width=46).grid(
            row=2,
            column=1,
            padx=10,
            pady=5,
        )
        ttk.Button(
            frame,
            text="选择…",
            command=lambda: self._choose_folder(draft_audio),
        ).grid(row=2, column=2, pady=5)

        ttk.Checkbutton(
            frame,
            text="随 Windows 开机启动",
            variable=draft_startup,
        ).grid(
            row=3,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(12, 4),
        )
        ttk.Checkbutton(
            frame,
            text="关闭窗口时最小化到右下角托盘",
            variable=draft_minimize,
        ).grid(
            row=4,
            column=0,
            columnspan=3,
            sticky="w",
            pady=4,
        )
        ttk.Label(frame, text="点击取消不会修改当前配置。").grid(
            row=5,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(10, 4),
        )

        buttons = ttk.Frame(frame)
        buttons.grid(
            row=6,
            column=0,
            columnspan=3,
            sticky="e",
            pady=(12, 0),
        )
        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(
            side="right"
        )
        ttk.Button(
            buttons,
            text="保存",
            style="Accent.TButton",
            command=lambda: self._apply_settings_draft(
                dialog,
                draft_folder,
                draft_interval,
                draft_audio,
                draft_startup,
                draft_minimize,
            ),
        ).pack(side="right", padx=(0, 8))

    def _apply_settings_draft(
        self,
        dialog: tk.Toplevel,
        folder: tk.StringVar,
        interval: tk.StringVar,
        audio: tk.StringVar,
        startup: tk.BooleanVar,
        minimize: tk.BooleanVar,
    ) -> None:
        try:
            parsed_interval = int(interval.get())
            if parsed_interval <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "参数错误",
                "截屏间隔必须是大于 0 的整数。",
                parent=dialog,
            )
            return

        self.folder_var.set(folder.get().strip())
        self.interval_var.set(str(parsed_interval))
        self.audio_var.set(audio.get().strip())
        self.startup_var.set(startup.get())
        self.minimize_to_tray_var.set(minimize.get())

        if not self._save_config():
            return
        try:
            set_startup(
                APP_NAME,
                self._startup_command(),
                self.startup_var.get(),
            )
        except OSError as exc:
            self._log(f"开机启动设置失败：{exc}")
        self._log("设置已保存")
        dialog.destroy()

    def _startup_command(self) -> str:
        if getattr(sys, "frozen", False):
            return f'"{Path(sys.executable).resolve()}"'
        script = Path(__file__).resolve().parent.parent / "app.py"
        return f'"{Path(sys.executable).resolve()}" "{script}"'

    def _start_tray(self) -> None:
        if pystray is None or Image is None:
            self._log("未安装 pystray，托盘功能不可用")
            return
        image = Image.new("RGB", (64, 64), "#2563eb")
        draw = ImageDraw.Draw(image)
        draw.rectangle((14, 16, 50, 48), fill="white")
        draw.rectangle((20, 22, 44, 28), fill="#2563eb")
        draw.rectangle((20, 33, 38, 39), fill="#2563eb")
        menu = pystray.Menu(
            pystray.MenuItem(
                "打开窗口",
                lambda _icon, _item: self._publish_command("show"),
            ),
            pystray.MenuItem(
                "开始截屏",
                lambda _icon, _item: self._publish_command("start"),
            ),
            pystray.MenuItem(
                "停止截屏",
                lambda _icon, _item: self._publish_command("stop"),
            ),
            pystray.MenuItem(
                "设置",
                lambda _icon, _item: self._publish_command("settings"),
            ),
            pystray.MenuItem(
                "退出",
                lambda _icon, _item: self._publish_command("exit"),
            ),
        )
        self.tray_icon = pystray.Icon("screentl", image, APP_NAME, menu)
        threading.Thread(
            target=self.tray_icon.run,
            name="screentl-tray",
            daemon=True,
        ).start()
        self._update_tray_title()

    def _publish_command(self, command: str) -> None:
        self.event_bus.publish(
            AppEvent(EventKind.COMMAND, "tray", data=command)
        )

    def _run_command(self, command: str) -> None:
        commands = {
            "show": self.show_window,
            "start": self.start_capture,
            "stop": self.stop_capture,
            "settings": self.show_settings,
            "exit": self.exit_app,
        }
        action = commands.get(command)
        if action is not None:
            action()

    def _update_tray_title(self, *_args) -> None:
        if self.tray_icon is not None:
            self.tray_icon.title = f"{APP_NAME} - {self.status_var.get()}"

    def show_window(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def _on_close(self) -> None:
        if (
            self.minimize_to_tray_var.get()
            and self.tray_icon is not None
            and not self.is_exiting
        ):
            self.withdraw()
            self._log("程序已最小化到右下角托盘")
        else:
            self.exit_app()

    def exit_app(self) -> None:
        if self.is_exiting:
            return
        if self.render_service.is_running:
            confirmed = messagebox.askyesno(
                "视频仍在生成",
                "退出将取消当前视频生成任务。是否继续退出？",
            )
            if not confirmed:
                return

        self.is_exiting = True
        self.status_var.set("正在安全退出…")
        self.start_button.configure(state="disabled")
        self.video_button.configure(state="disabled")
        self.pause_button.configure(state="disabled")
        self.stop_button.configure(state="disabled")
        self.cancel_video_button.configure(state="disabled")
        self._save_config()
        self.capture_service.stop()
        self.render_service.cancel()

    def _poll_shutdown(self) -> None:
        if self.capture_service.is_running or self.render_service.is_running:
            return
        self.capture_service.join(0)
        self.render_service.join(0)
        if self.tray_icon is not None:
            self.tray_icon.stop()
        self._destroyed = True
        self.destroy()


def main() -> None:
    app = ScreenshotTimeLapseApp()
    app.mainloop()


if __name__ == "__main__":
    main()
