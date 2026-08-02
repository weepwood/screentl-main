"""Repository extensions used by the desktop work journal."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from .sessions import RecordingSession, SessionRepository, safe_name, utc_now


class JournalRepository(SessionRepository):
    def create_session(
        self,
        root: Path,
        name: str,
        mode: str = "named",
        settings: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> RecordingSession:
        normalized_name = name.strip() or "Untitled session"
        if mode == "daily":
            today = dt.datetime.now(dt.UTC).date().isoformat()
            expected = root.expanduser().resolve() / f"{safe_name(normalized_name)}_{today}"
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
        created = super().create_session(
            root,
            normalized_name,
            mode,
            settings,
            session_id,
        )
        return self.get_session(created.id) or created

    def set_session_status(self, session_id: str, status: str) -> None:
        if status not in {"active", "paused", "completed", "archived"}:
            raise ValueError(f"unsupported session status: {status}")
        ended_at = utc_now() if status in {"completed", "archived"} else None
        with self._connect() as connection:
            connection.execute(
                "UPDATE sessions SET status = ?, ended_at = ? WHERE id = ?",
                (status, ended_at, session_id),
            )

    def count_frames(self, session_id: str, include_excluded: bool = True) -> int:
        excluded_clause = "" if include_excluded else "AND excluded = 0"
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(*) AS count FROM frames
                WHERE session_id = ? AND deleted_at IS NULL {excluded_clause}
                """,
                (session_id,),
            ).fetchone()
        return int(row["count"] or 0)

    def session_summary(self, session_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS frames,
                       SUM(CASE WHEN excluded = 1 THEN 1 ELSE 0 END) AS excluded,
                       SUM(CASE WHEN duplicate_of IS NOT NULL THEN 1 ELSE 0 END) AS duplicates,
                       COALESCE(
                           SUM(CASE WHEN excluded = 0 THEN duration ELSE 0 END),
                           0
                       ) AS duration
                FROM frames WHERE session_id = ? AND deleted_at IS NULL
                """,
                (session_id,),
            ).fetchone()
            apps = connection.execute(
                """
                SELECT app_name, COUNT(*) AS count FROM frames
                WHERE session_id = ? AND deleted_at IS NULL AND app_name != ''
                GROUP BY app_name ORDER BY count DESC LIMIT 10
                """,
                (session_id,),
            ).fetchall()
        return {
            "session_id": session_id,
            "frames": int(row["frames"] or 0),
            "excluded": int(row["excluded"] or 0),
            "duplicates": int(row["duplicates"] or 0),
            "estimated_video_seconds": float(row["duration"] or 0),
            "top_apps": [(item["app_name"], int(item["count"])) for item in apps],
        }

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
