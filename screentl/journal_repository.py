"""Repository extensions used by the desktop work journal."""

from __future__ import annotations

import datetime as dt

from .sessions import SessionRepository


class JournalRepository(SessionRepository):
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
