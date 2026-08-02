"""Desktop application with searchable historical session management."""

from __future__ import annotations

from tkinter import messagebox

from .safe_journal_app import SafeJournalApplication
from .session_manager import SessionManagerDialog


class ManagedJournalApplication(SafeJournalApplication):
    """Add historical session browsing without weakening task isolation."""

    def _build_journal_menu(self) -> None:
        super()._build_journal_menu()
        root_menu = self.nametowidget(self["menu"])
        session_menu = self.nametowidget(root_menu.entrycget(0, "menu"))
        session_menu.insert_command(
            1,
            label="管理会话…",
            command=self.show_session_manager,
        )

    def show_session_manager(self) -> None:
        SessionManagerDialog(
            parent=self,
            repository=self.repository,
            current_session_id=(
                self.current_session.id if self.current_session is not None else None
            ),
            on_choose=self._choose_managed_session,
        )

    def _choose_managed_session(self, session_id: str, resume: bool) -> bool:
        if self._session_change_blocked("切换会话"):
            return False
        session = self.repository.get_session(session_id)
        if session is None:
            messagebox.showerror(
                "会话不存在",
                "所选会话可能已被清理，请刷新列表后重试。",
                parent=self,
            )
            return False
        if resume and session.status == "archived":
            messagebox.showinfo(
                "归档会话",
                "归档会话只能查看，不能继续记录。",
                parent=self,
            )
            return False
        if resume:
            self.repository.set_session_status(session.id, "active")
            session = self.repository.get_session(session.id) or session
        self.current_session = session
        self._sync_session_ui()
        action = "继续记录" if resume else "切换查看"
        self._log(f"已{action}会话：{session.name}")
        return True


def run_managed_journal_app() -> None:
    app = ManagedJournalApplication()
    app.mainloop()
