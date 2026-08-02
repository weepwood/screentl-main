"""Desktop dialog for searching and selecting recording sessions."""

from __future__ import annotations

import datetime as dt
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, ttk

from .journal_repository import JournalRepository, SessionOverview
from .windows import open_folder

STATUS_LABELS = {
    "active": "活动",
    "paused": "暂停",
    "completed": "已完成",
    "archived": "已归档",
}
STATUS_FILTERS = {
    "全部状态": None,
    "活动": "active",
    "暂停": "paused",
    "已完成": "completed",
    "已归档": "archived",
}


def format_local_time(value: str | None) -> str:
    if not value:
        return "—"
    try:
        parsed = dt.datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return value


class SessionManagerDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        repository: JournalRepository,
        current_session_id: str | None,
        on_choose: Callable[[str, bool], bool],
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.current_session_id = current_session_id
        self.on_choose = on_choose
        self.overviews: dict[str, SessionOverview] = {}

        self.title("会话管理中心")
        self.geometry("1080x620")
        self.minsize(860, 480)
        self.transient(parent)

        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="全部状态")
        self.summary_var = tk.StringVar(value="正在加载…")
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(root)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        toolbar.columnconfigure(0, weight=1)
        search = ttk.Entry(toolbar, textvariable=self.search_var)
        search.grid(row=0, column=0, sticky="ew")
        search.bind("<Return>", lambda _event: self.reload())
        status = ttk.Combobox(
            toolbar,
            textvariable=self.status_var,
            values=list(STATUS_FILTERS),
            state="readonly",
            width=12,
        )
        status.grid(row=0, column=1, padx=(8, 0))
        status.bind("<<ComboboxSelected>>", lambda _event: self.reload())
        ttk.Button(toolbar, text="搜索", command=self.reload).grid(
            row=0,
            column=2,
            padx=(8, 0),
        )
        ttk.Button(toolbar, text="清除", command=self._clear_filters).grid(
            row=0,
            column=3,
            padx=(8, 0),
        )

        columns = (
            "status",
            "started",
            "ended",
            "frames",
            "kept",
            "excluded",
            "duration",
        )
        self.tree = ttk.Treeview(
            root,
            columns=columns,
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="会话名称")
        self.tree.heading("status", text="状态")
        self.tree.heading("started", text="开始时间")
        self.tree.heading("ended", text="结束时间")
        self.tree.heading("frames", text="总帧")
        self.tree.heading("kept", text="保留")
        self.tree.heading("excluded", text="排除")
        self.tree.heading("duration", text="预计时长")
        self.tree.column("#0", width=250, minwidth=180)
        self.tree.column("status", width=80, anchor="center")
        self.tree.column("started", width=155)
        self.tree.column("ended", width=155)
        self.tree.column("frames", width=70, anchor="e")
        self.tree.column("kept", width=70, anchor="e")
        self.tree.column("excluded", width=70, anchor="e")
        self.tree.column("duration", width=90, anchor="e")
        self.tree.grid(row=1, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._update_buttons)
        self.tree.bind("<Double-1>", lambda _event: self.choose_for_view())

        scrollbar = ttk.Scrollbar(root, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        footer = ttk.Frame(root)
        footer.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.summary_var).grid(
            row=0,
            column=0,
            sticky="w",
        )
        self.open_button = ttk.Button(
            footer,
            text="打开目录",
            command=self.open_selected_folder,
            state="disabled",
        )
        self.open_button.grid(row=0, column=1, padx=(8, 0))
        self.output_button = ttk.Button(
            footer,
            text="打开输出",
            command=self.open_selected_output,
            state="disabled",
        )
        self.output_button.grid(row=0, column=2, padx=(8, 0))
        self.view_button = ttk.Button(
            footer,
            text="设为当前查看",
            command=self.choose_for_view,
            state="disabled",
        )
        self.view_button.grid(row=0, column=3, padx=(8, 0))
        self.resume_button = ttk.Button(
            footer,
            text="继续记录",
            command=self.resume_selected,
            state="disabled",
        )
        self.resume_button.grid(row=0, column=4, padx=(8, 0))
        ttk.Button(footer, text="关闭", command=self.destroy).grid(
            row=0,
            column=5,
            padx=(8, 0),
        )

    def _clear_filters(self) -> None:
        self.search_var.set("")
        self.status_var.set("全部状态")
        self.reload()

    def reload(self) -> None:
        status = STATUS_FILTERS.get(self.status_var.get())
        rows = self.repository.list_session_overviews(
            query=self.search_var.get(),
            status=status,
        )
        self.overviews = {item.id: item for item in rows}
        for item in self.tree.get_children():
            self.tree.delete(item)
        for overview in rows:
            marker = "▶ " if overview.id == self.current_session_id else ""
            self.tree.insert(
                "",
                "end",
                iid=overview.id,
                text=f"{marker}{overview.name}",
                values=(
                    STATUS_LABELS.get(overview.status, overview.status),
                    format_local_time(overview.started_at),
                    format_local_time(overview.ended_at),
                    overview.frames,
                    overview.kept_frames,
                    overview.excluded_frames,
                    f"{overview.estimated_video_seconds:.1f} 秒",
                ),
            )
        kept = sum(item.kept_frames for item in rows)
        self.summary_var.set(f"共 {len(rows)} 个会话，保留截图 {kept} 张")
        self._update_buttons()

    def _selected(self) -> SessionOverview | None:
        selected = self.tree.selection()
        if not selected:
            return None
        return self.overviews.get(selected[0])

    def _update_buttons(self, _event=None) -> None:
        selected = self._selected()
        state = "normal" if selected is not None else "disabled"
        self.open_button.configure(state=state)
        self.output_button.configure(state=state)
        self.view_button.configure(state=state)
        resume_state = (
            "normal"
            if selected is not None and selected.status != "archived"
            else "disabled"
        )
        self.resume_button.configure(state=resume_state)

    def _choose(self, resume: bool) -> None:
        selected = self._selected()
        if selected is None:
            return
        if resume and selected.status == "archived":
            messagebox.showinfo(
                "归档会话",
                "归档会话只能查看，不能继续记录。",
                parent=self,
            )
            return
        if self.on_choose(selected.id, resume):
            self.current_session_id = selected.id
            self.reload()

    def choose_for_view(self) -> None:
        self._choose(resume=False)

    def resume_selected(self) -> None:
        self._choose(resume=True)

    def _open_path(self, path: Path) -> None:
        try:
            path.mkdir(parents=True, exist_ok=True)
            open_folder(path)
        except OSError as exc:
            messagebox.showerror("打开失败", str(exc), parent=self)

    def open_selected_folder(self) -> None:
        selected = self._selected()
        if selected is not None:
            self._open_path(selected.root_path)

    def open_selected_output(self) -> None:
        selected = self._selected()
        if selected is not None:
            self._open_path(selected.root_path / "output")
