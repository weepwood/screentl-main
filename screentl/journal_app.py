"""Session, timeline, privacy and professional-render desktop integration."""

from __future__ import annotations

import json
import threading
import time
import tkinter as tk
import webbrowser
from dataclasses import asdict
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .application import DesktopApplication
from .capture_engine import SessionCaptureEngine, SessionCaptureOptions
from .events import AppEvent, EventKind
from .intelligence import LocalIntelligenceService
from .journal_repository import JournalRepository
from .models import TaskState
from .privacy import GlobalPrivacyHotkey, PrivacyGuard, PrivacyRules
from .renderer import FFmpegSessionRenderer, RenderCancelled, RenderOptions
from .services import CaptureService, RenderService
from .settings import SettingsRepository, default_data_root
from .storage import atomic_write_json
from .timeline import TimelineService
from .video import VideoCancelled
from .windows import open_folder


class JournalApplication(DesktopApplication):
    def __init__(self) -> None:
        super().__init__()
        app_dir = SettingsRepository.default_path().parent
        self.journal_preferences_path = app_dir / "journal.json"
        self.repository = JournalRepository(app_dir / "sessions.db")
        self.repository.recover_active_sessions()
        self.repository.recover_render_jobs()
        self.timeline_service = TimelineService(self.repository)
        self.intelligence = LocalIntelligenceService(self.repository)
        self.session_renderer = FFmpegSessionRenderer(self.repository)
        self.current_session = self.repository.latest_session()
        self.capture_options, privacy_rules = self._load_journal_preferences()
        self.privacy_guard = PrivacyGuard(privacy_rules)
        self._next_render_options: RenderOptions | None = None
        self._last_skip_reason = ""
        self._last_skip_log = 0.0
        self.privacy_hotkey = GlobalPrivacyHotkey(
            lambda: self._publish_command("privacy-toggle")
        )
        self.privacy_hotkey.start()
        self.render_service = RenderService(
            self.event_bus,
            render_func=self._render_session_adapter,
        )
        self._build_journal_menu()
        self._sync_session_ui()

    @property
    def journal_root(self) -> Path:
        return default_data_root() / "sessions"

    def _load_journal_preferences(
        self,
    ) -> tuple[SessionCaptureOptions, PrivacyRules]:
        try:
            raw = json.loads(self.journal_preferences_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return SessionCaptureOptions(), PrivacyRules()
        capture_raw = raw.get("capture", {})
        privacy_raw = raw.get("privacy", {})
        region = capture_raw.get("region")
        return (
            SessionCaptureOptions(
                monitor=int(capture_raw.get("monitor", 1)),
                region=tuple(region) if region else None,
                active_window_only=bool(capture_raw.get("active_window_only", False)),
                image_format=str(capture_raw.get("image_format", "png")),
                quality=int(capture_raw.get("quality", 90)),
                scale=float(capture_raw.get("scale", 1.0)),
                auto_exclude_duplicates=bool(
                    capture_raw.get("auto_exclude_duplicates", True)
                ),
                daily_rollover=bool(capture_raw.get("daily_rollover", False)),
                continue_across_midnight=bool(
                    capture_raw.get("continue_across_midnight", True)
                ),
            ),
            PrivacyRules(
                excluded_apps=list(privacy_raw.get("excluded_apps", [])),
                excluded_title_keywords=list(
                    privacy_raw.get("excluded_title_keywords", [])
                ),
                idle_pause_seconds=int(privacy_raw.get("idle_pause_seconds", 0)),
                pause_when_locked=bool(privacy_raw.get("pause_when_locked", True)),
                pause_on_battery=bool(privacy_raw.get("pause_on_battery", False)),
                collect_window_metadata=bool(
                    privacy_raw.get("collect_window_metadata", False)
                ),
                ocr_enabled=bool(privacy_raw.get("ocr_enabled", False)),
                cloud_enabled=False,
            ),
        )

    def _save_journal_preferences(self) -> None:
        atomic_write_json(
            self.journal_preferences_path,
            {
                "capture": asdict(self.capture_options),
                "privacy": asdict(self.privacy_guard.rules),
            },
        )

    def _build_journal_menu(self) -> None:
        menu = tk.Menu(self)
        session_menu = tk.Menu(menu, tearoff=False)
        session_menu.add_command(label="新建会话…", command=self.new_session)
        session_menu.add_command(label="继续最近会话", command=self.continue_latest_session)
        session_menu.add_command(label="结束当前会话", command=self.complete_session)
        session_menu.add_separator()
        session_menu.add_command(label="打开会话目录", command=self.open_session_folder)
        session_menu.add_command(label="归档当前会话…", command=self.archive_session)
        session_menu.add_command(label="清理旧会话…", command=self.cleanup_sessions)
        menu.add_cascade(label="会话", menu=session_menu)

        timeline_menu = tk.Menu(menu, tearoff=False)
        timeline_menu.add_command(label="打开时间轴", command=self.show_timeline)
        timeline_menu.add_command(label="导出联系表…", command=self.export_contact_sheet)
        timeline_menu.add_command(label="导出 HTML 预览…", command=self.export_html_preview)
        timeline_menu.add_command(label="导出本地摘要…", command=self.export_summary)
        timeline_menu.add_command(label="导出会话清单…", command=self.export_manifest)
        menu.add_cascade(label="时间轴", menu=timeline_menu)

        privacy_menu = tk.Menu(menu, tearoff=False)
        privacy_menu.add_command(
            label="切换隐私暂停（Ctrl+Alt+P）",
            command=self.toggle_privacy_pause,
        )
        privacy_menu.add_command(label="隐私与捕获设置…", command=self.show_privacy_settings)
        menu.add_cascade(label="隐私", menu=privacy_menu)

        output_menu = tk.Menu(menu, tearoff=False)
        output_menu.add_command(label="专业输出…", command=self.show_render_settings)
        output_menu.add_command(label="打开输出目录", command=self.open_output_folder)
        menu.add_cascade(label="输出", menu=output_menu)
        self.configure(menu=menu)

    def _ensure_session(self) -> None:
        if self.current_session is not None and self.current_session.status != "archived":
            return
        self.new_session(default_name=time.strftime("%Y-%m-%d"))
        if self.current_session is None:
            raise RuntimeError("no recording session is selected")

    def new_session(self, default_name: str = "") -> None:
        name = simpledialog.askstring(
            "新建记录会话",
            "会话名称：",
            initialvalue=default_name or time.strftime("%Y-%m-%d 工作记录"),
            parent=self,
        )
        if name is None:
            return
        mode = "daily" if self.capture_options.daily_rollover else "named"
        self.current_session = self.repository.create_session(
            self.journal_root,
            name,
            mode=mode,
            settings={
                "capture": asdict(self.capture_options),
                "privacy": asdict(self.privacy_guard.rules),
            },
        )
        self._sync_session_ui()
        self._log(f"已创建会话：{self.current_session.name}")

    def continue_latest_session(self) -> None:
        session = self.repository.latest_session()
        if session is None:
            self.new_session()
            return
        self.current_session = session
        self.repository.set_session_status(session.id, "active")
        self._sync_session_ui()
        self._log(f"继续会话：{session.name}")

    def complete_session(self) -> None:
        if self.current_session is None:
            return
        if self.capture_service.is_running:
            self.capture_service.stop()
        self.repository.set_session_status(self.current_session.id, "completed")
        self.current_session = self.repository.get_session(self.current_session.id)
        self._sync_session_ui()
        self._log("当前会话已结束")

    def _sync_session_ui(self) -> None:
        if self.current_session is None:
            self.detail_var.set("未选择记录会话")
            return
        self.folder_var.set(str(self.current_session.frames_path))
        summary = self.repository.session_summary(self.current_session.id)
        self.detail_var.set(
            f"会话：{self.current_session.name} · {summary['frames']} 帧"
        )

    def _capture_skip(self, reason: str) -> None:
        now = time.monotonic()
        if reason != self._last_skip_reason or now - self._last_skip_log > 60:
            self.event_bus.publish(
                AppEvent(EventKind.LOG, "privacy", f"隐私规则已暂停截屏：{reason}")
            )
            self._last_skip_reason = reason
            self._last_skip_log = now

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
        self.repository.set_session_status(self.current_session.id, "active")
        engine = SessionCaptureEngine(
            repository=self.repository,
            session=self.current_session,
            options=self.capture_options,
            privacy=self.privacy_guard,
            on_skip=self._capture_skip,
        )
        self.capture_service = CaptureService(
            self.event_bus,
            capture_func=engine,
        )
        self.folder_var.set(str(self.current_session.frames_path))
        super().start_capture()

    def _apply_task_state(self, source: str, state: TaskState) -> None:
        super()._apply_task_state(source, state)
        if source == "capture" and self.current_session is not None:
            if state is TaskState.PAUSED:
                self.repository.set_session_status(self.current_session.id, "paused")
            elif state is TaskState.COMPLETED:
                self.repository.set_session_status(self.current_session.id, "paused")
                self._sync_session_ui()

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
        if self.current_session is None:
            raise RuntimeError("no recording session is selected")
        options = self._next_render_options or RenderOptions(
            fps=fps,
            audio_mode="random" if audio_loc and Path(audio_loc).is_dir() else "none",
            audio_folder=Path(audio_loc) if audio_loc else None,
        )
        self._next_render_options = None
        try:
            outputs = self.session_renderer.render(
                self.current_session.id,
                options,
                cancel_event=cancel_event,
                on_progress=on_progress,
            )
        except RenderCancelled as exc:
            raise VideoCancelled(str(exc)) from exc
        return outputs[0]

    def start_video(self) -> None:
        if self.current_session is None:
            messagebox.showinfo("没有会话", "请先创建或继续一个记录会话。", parent=self)
            return
        self.folder_var.set(str(self.current_session.frames_path))
        super().start_video()

    def toggle_privacy_pause(self) -> None:
        paused = self.privacy_guard.toggle_manual_pause()
        state = "已开启" if paused else "已解除"
        self.status_var.set(f"隐私暂停{state}")
        self._log(f"隐私暂停{state}（Ctrl+Alt+P）")

    def _run_command(self, command: str) -> None:
        if command == "privacy-toggle":
            self.toggle_privacy_pause()
            return
        super()._run_command(command)

    def show_privacy_settings(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("隐私与捕获设置")
        dialog.transient(self)
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)

        monitor = tk.IntVar(value=self.capture_options.monitor)
        active_window = tk.BooleanVar(value=self.capture_options.active_window_only)
        image_format = tk.StringVar(value=self.capture_options.image_format)
        quality = tk.IntVar(value=self.capture_options.quality)
        scale = tk.DoubleVar(value=self.capture_options.scale)
        duplicate = tk.BooleanVar(value=self.capture_options.auto_exclude_duplicates)
        daily = tk.BooleanVar(value=self.capture_options.daily_rollover)
        cross_midnight = tk.BooleanVar(value=self.capture_options.continue_across_midnight)
        apps = tk.StringVar(value=", ".join(self.privacy_guard.rules.excluded_apps))
        titles = tk.StringVar(
            value=", ".join(self.privacy_guard.rules.excluded_title_keywords)
        )
        idle = tk.IntVar(value=self.privacy_guard.rules.idle_pause_seconds)
        locked = tk.BooleanVar(value=self.privacy_guard.rules.pause_when_locked)
        battery = tk.BooleanVar(value=self.privacy_guard.rules.pause_on_battery)
        metadata = tk.BooleanVar(value=self.privacy_guard.rules.collect_window_metadata)
        ocr = tk.BooleanVar(value=self.privacy_guard.rules.ocr_enabled)

        rows = [
            ("显示器编号（0=全部）", monitor),
            ("图片格式 png/jpeg/webp", image_format),
            ("图片质量 1-100", quality),
            ("缩放比例 0.1-1.0", scale),
            ("空闲暂停秒数（0=关闭）", idle),
            ("排除应用，逗号分隔", apps),
            ("排除窗口关键词，逗号分隔", titles),
        ]
        for row, (label, variable) in enumerate(rows):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(frame, textvariable=variable, width=42).grid(
                row=row,
                column=1,
                sticky="ew",
                pady=4,
            )
        checks = [
            ("只截取当前活动窗口", active_window),
            ("自动排除重复画面", duplicate),
            ("按天创建会话", daily),
            ("跨越午夜继续当前会话", cross_midnight),
            ("锁屏时暂停", locked),
            ("使用电池时暂停", battery),
            ("采集窗口标题与应用名（默认关闭）", metadata),
            ("启用本地 OCR（需要自行安装 Tesseract）", ocr),
        ]
        start_row = len(rows)
        for index, (label, variable) in enumerate(checks):
            ttk.Checkbutton(frame, text=label, variable=variable).grid(
                row=start_row + index,
                column=0,
                columnspan=2,
                sticky="w",
                pady=3,
            )
        ttk.Label(
            frame,
            text="不会自动启用云端处理。全局隐私暂停快捷键：Ctrl+Alt+P。",
        ).grid(
            row=start_row + len(checks),
            column=0,
            columnspan=2,
            sticky="w",
            pady=(10, 4),
        )

        def save() -> None:
            try:
                options = SessionCaptureOptions(
                    monitor=monitor.get(),
                    active_window_only=active_window.get(),
                    image_format=image_format.get().strip().casefold(),
                    quality=quality.get(),
                    scale=scale.get(),
                    auto_exclude_duplicates=duplicate.get(),
                    daily_rollover=daily.get(),
                    continue_across_midnight=cross_midnight.get(),
                )
                options.validate()
                rules = PrivacyRules(
                    excluded_apps=[item.strip() for item in apps.get().split(",") if item.strip()],
                    excluded_title_keywords=[
                        item.strip() for item in titles.get().split(",") if item.strip()
                    ],
                    idle_pause_seconds=max(0, idle.get()),
                    pause_when_locked=locked.get(),
                    pause_on_battery=battery.get(),
                    collect_window_metadata=metadata.get(),
                    ocr_enabled=ocr.get(),
                    cloud_enabled=False,
                )
            except (ValueError, tk.TclError) as exc:
                messagebox.showerror("设置无效", str(exc), parent=dialog)
                return
            self.capture_options = options
            self.privacy_guard.rules = rules
            self._save_journal_preferences()
            dialog.destroy()
            self._log("隐私与捕获设置已保存")

        buttons = ttk.Frame(frame)
        buttons.grid(
            row=start_row + len(checks) + 1,
            column=0,
            columnspan=2,
            sticky="e",
            pady=(12, 0),
        )
        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text="保存", command=save).pack(side="right", padx=(0, 8))

    def show_timeline(self) -> None:
        if self.current_session is None:
            messagebox.showinfo("没有会话", "请先选择记录会话。", parent=self)
            return
        window = tk.Toplevel(self)
        window.title(f"时间轴 - {self.current_session.name}")
        window.geometry("980x620")
        frame = ttk.Frame(window, padding=12)
        frame.pack(fill="both", expand=True)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        search_var = tk.StringVar()
        toolbar = ttk.Frame(frame)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Entry(toolbar, textvariable=search_var, width=30).pack(side="left")

        tree = ttk.Treeview(
            frame,
            columns=("time", "app", "status", "duplicate", "duration"),
            show="tree headings",
            selectmode="extended",
        )
        tree.heading("#0", text="编号 / 小时")
        tree.heading("time", text="时间")
        tree.heading("app", text="应用 / 窗口")
        tree.heading("status", text="状态")
        tree.heading("duplicate", text="重复")
        tree.heading("duration", text="停留秒数")
        tree.column("#0", width=150)
        tree.column("time", width=160)
        tree.column("app", width=260)
        tree.column("status", width=80)
        tree.column("duplicate", width=70)
        tree.column("duration", width=80)
        tree.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        tree.configure(yscrollcommand=scrollbar.set)

        offset = tk.IntVar(value=0)
        limit = 200

        def selected_ids() -> list[int]:
            result = []
            for item in tree.selection():
                if item.startswith("frame-"):
                    result.append(int(item.removeprefix("frame-")))
            return result

        def load() -> None:
            for item in tree.get_children():
                tree.delete(item)
            query = search_var.get().strip()
            if query:
                frames = [result.frame for result in self.intelligence.search(
                    self.current_session.id,
                    query,
                    limit=limit,
                )]
                groups = {"搜索结果": frames}
            else:
                page = self.timeline_service.page(
                    self.current_session.id,
                    offset=offset.get(),
                    limit=limit,
                )
                groups = {group.hour: list(group.frames) for group in page.groups}
            for hour, frames in groups.items():
                parent = tree.insert("", "end", text=hour, open=True)
                for item in frames:
                    tree.insert(
                        parent,
                        "end",
                        iid=f"frame-{item.id}",
                        text=f"#{item.sequence}",
                        values=(
                            item.captured_at,
                            item.app_name or item.window_title,
                            "排除" if item.excluded else "保留",
                            "是" if item.duplicate_of else "",
                            f"{item.duration:.2f}",
                        ),
                    )

        def set_excluded(value: bool) -> None:
            self.repository.set_frames_excluded(selected_ids(), value)
            load()

        def delete_selected() -> None:
            ids = selected_ids()
            if ids and messagebox.askyesno(
                "删除截图",
                f"将从索引和磁盘删除 {len(ids)} 张截图，是否继续？",
                parent=window,
            ):
                self.repository.delete_frames(ids, delete_files=True)
                load()

        def edit_duration() -> None:
            ids = selected_ids()
            if not ids:
                return
            value = simpledialog.askfloat(
                "设置停留时间",
                "每张截图停留秒数：",
                minvalue=0.04,
                parent=window,
            )
            if value is not None:
                for frame_id in ids:
                    self.repository.set_frame_duration(frame_id, value)
                load()

        def add_mask() -> None:
            ids = selected_ids()
            if len(ids) != 1:
                messagebox.showinfo("选择一张截图", "添加遮挡时只能选择一张截图。", parent=window)
                return
            raw = simpledialog.askstring(
                "添加隐私遮挡",
                "输入 x,y,width,height：",
                parent=window,
            )
            if not raw:
                return
            try:
                values = tuple(int(value.strip()) for value in raw.split(","))
                if len(values) != 4:
                    raise ValueError
                frame = self.repository.get_frame(ids[0])
                if frame is None:
                    return
                self.repository.set_frame_masks(ids[0], [*frame.masks, values])
            except ValueError:
                messagebox.showerror("格式错误", "请输入四个整数。", parent=window)

        def add_chapter() -> None:
            ids = selected_ids()
            if len(ids) != 1:
                return
            title = simpledialog.askstring("章节标题", "标题：", parent=window)
            if title:
                self.repository.add_chapter(self.current_session.id, ids[0], title)

        ttk.Button(toolbar, text="搜索", command=load).pack(side="left", padx=4)
        ttk.Button(toolbar, text="保留", command=lambda: set_excluded(False)).pack(side="left")
        ttk.Button(toolbar, text="排除", command=lambda: set_excluded(True)).pack(side="left", padx=4)
        ttk.Button(toolbar, text="删除", command=delete_selected).pack(side="left")
        ttk.Button(toolbar, text="合并重复", command=lambda: (
            self.repository.collapse_duplicates(self.current_session.id), load()
        )).pack(side="left", padx=4)
        ttk.Button(toolbar, text="停留时间", command=edit_duration).pack(side="left")
        ttk.Button(toolbar, text="隐私遮挡", command=add_mask).pack(side="left", padx=4)
        ttk.Button(toolbar, text="章节", command=add_chapter).pack(side="left")

        navigation = ttk.Frame(frame)
        navigation.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(
            navigation,
            text="上一页",
            command=lambda: (offset.set(max(0, offset.get() - limit)), load()),
        ).pack(side="left")
        ttk.Button(
            navigation,
            text="下一页",
            command=lambda: (offset.set(offset.get() + limit), load()),
        ).pack(side="left", padx=4)
        ttk.Button(navigation, text="联系表", command=self.export_contact_sheet).pack(side="right")
        ttk.Button(navigation, text="HTML 预览", command=self.export_html_preview).pack(side="right", padx=4)
        load()

    def show_render_settings(self) -> None:
        if self.current_session is None:
            messagebox.showinfo("没有会话", "请先选择记录会话。", parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title("专业输出")
        dialog.transient(self)
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        output_format = tk.StringVar(value="mp4")
        codec = tk.StringVar(value="h264")
        bitrate = tk.StringVar(value="4M")
        resolution = tk.StringVar(value="")
        audio_mode = tk.StringVar(value="none")
        volume = tk.DoubleVar(value=0.2)
        fade = tk.DoubleVar(value=1.0)
        split = tk.BooleanVar(value=False)
        rows = [
            ("格式 mp4/gif", output_format),
            ("编码 h264/h265/vp9/nvenc/qsv/amf", codec),
            ("码率", bitrate),
            ("分辨率，例如 1920x1080", resolution),
            ("音乐 none/fixed/random/loop/sequence", audio_mode),
            ("音乐音量", volume),
            ("淡入淡出秒数", fade),
        ]
        for row, (label, variable) in enumerate(rows):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(frame, textvariable=variable, width=34).grid(
                row=row,
                column=1,
                sticky="ew",
                pady=4,
            )
        ttk.Checkbutton(frame, text="按小时分段输出", variable=split).grid(
            row=len(rows),
            column=0,
            columnspan=2,
            sticky="w",
            pady=5,
        )

        def start() -> None:
            try:
                parsed_resolution = None
                if resolution.get().strip():
                    width, height = resolution.get().lower().split("x", maxsplit=1)
                    parsed_resolution = (int(width), int(height))
                audio_folder = Path(self.audio_var.get()) if self.audio_var.get().strip() else None
                options = RenderOptions(
                    output_format=output_format.get().strip().casefold(),
                    codec=codec.get().strip().casefold(),
                    bitrate=bitrate.get().strip(),
                    resolution=parsed_resolution,
                    audio_mode=audio_mode.get().strip().casefold(),
                    audio_folder=audio_folder,
                    audio_volume=volume.get(),
                    audio_fade_seconds=fade.get(),
                    fps=int(self.fps_var.get()),
                    split_by_hour=split.get(),
                )
                options.validate()
            except (ValueError, tk.TclError) as exc:
                messagebox.showerror("参数错误", str(exc), parent=dialog)
                return
            self._next_render_options = options
            dialog.destroy()
            self.start_video()

        buttons = ttk.Frame(frame)
        buttons.grid(row=len(rows) + 1, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text="开始输出", command=start).pack(side="right", padx=(0, 8))

    def _choose_export_path(self, default_name: str, extension: str) -> Path | None:
        selected = filedialog.asksaveasfilename(
            parent=self,
            initialfile=default_name,
            defaultextension=extension,
        )
        return Path(selected) if selected else None

    def export_contact_sheet(self) -> None:
        if self.current_session is None:
            return
        destination = self._choose_export_path("contact-sheet.jpg", ".jpg")
        if destination:
            self.timeline_service.build_contact_sheet(self.current_session.id, destination)
            self._log(f"联系表已导出：{destination}")

    def export_html_preview(self) -> None:
        if self.current_session is None:
            return
        destination = self._choose_export_path("timeline.html", ".html")
        if destination:
            self.timeline_service.build_html_preview(self.current_session.id, destination)
            webbrowser.open(destination.resolve().as_uri())

    def export_summary(self) -> None:
        if self.current_session is None:
            return
        destination = self._choose_export_path("summary.md", ".md")
        if destination:
            self.intelligence.export_summary(self.current_session.id, destination)
            self._log(f"本地摘要已导出：{destination}")

    def export_manifest(self) -> None:
        if self.current_session is None:
            return
        destination = self._choose_export_path("session.json", ".json")
        if destination:
            self.repository.export_session_manifest(self.current_session.id, destination)
            self._log(f"会话清单已导出：{destination}")

    def archive_session(self) -> None:
        if self.current_session is None:
            return
        selected = filedialog.askdirectory(parent=self)
        if selected:
            archive = self.repository.archive_session(
                self.current_session.id,
                Path(selected),
            )
            self._log(f"会话已归档：{archive}")

    def cleanup_sessions(self) -> None:
        days = simpledialog.askinteger(
            "清理旧会话",
            "删除多少天以前已完成的会话？",
            initialvalue=30,
            minvalue=1,
            parent=self,
        )
        if days is None:
            return
        removed = self.repository.cleanup(retention_days=days)
        self._log(f"已清理 {len(removed)} 个旧会话")

    def open_session_folder(self) -> None:
        if self.current_session is not None:
            open_folder(self.current_session.root_path)

    def open_output_folder(self) -> None:
        if self.current_session is not None:
            open_folder(self.current_session.output_path)

    def _poll_shutdown(self) -> None:
        if not self.capture_service.is_running and not self.render_service.is_running:
            self.privacy_hotkey.stop()
        super()._poll_shutdown()


def run_journal_app() -> None:
    app = JournalApplication()
    app.mainloop()
