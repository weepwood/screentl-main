"""Repository extensions used by the desktop work journal."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from .sessions import RecordingSession, SessionRepository, safe_name


class JournalRepository(SessionRepository):
    def create_session(
        self,
        root: Path,
        name: str,
        mode: str = "named",
        settings: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> RecordingSession:
        if mode == "daily":
            today = dt.datetime.now(dt.UTC).date().isoformat()
            expected = root.expanduser().resolve() / f"{safe_name(name)}_{today}"
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM sessions WHERE root_path = ?",
                    (str(expected),),
                ).fetchone()
                if row is not None:
                    connection.execute(
                        "UPDATE sessions SET status = 'active', ended_at = NULL WHERE id = ?",
                        (row["id"],),
                    )
                    refreshed = connection.execute(
                        "SELECT * FROM sessions WHERE id = ?",
                        (row["id"],),
                    ).fetchone()
                    return self._session_from_row(refreshed)
        return super().create_session(root, name, mode, settings, session_id)

    def recover_render_jobs(self) -> int:
        finished_at = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE render_jobs
                SET status = 'failed', error = 'application interrupted', finished_at = ?
                WHERE status IN ('queued', 'running')
                """,
                (finished_at,),
            )
            return cursor.rowcount
