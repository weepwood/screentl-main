"""Repository extensions used by the desktop work journal."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .sessions import RecordingSession, SessionRepository, safe_name, utc_now


@dataclass(frozen=True)
class SessionOverview:
    id: str
    name: str
    root_path: Path
    mode: str
    status: str
    started_at: str
    ended_at: str | None
    frames: int
    kept_frames: int
    excluded_frames: int
    estimated_video_seconds: float


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
                    "SELECT id FROM sessions WHERE root_path = ?",
                    (str(expected),),
                ).fetchone()
            if row is not None:
                selected = self.select_session(row["id"], resume=True)
                if selected is not None:
                    return selected
        created = super().create_session(
            root,
            normalized_name,
            mode,
            settings,
            session_id,
        )
        return self.select_session(created.id, resume=True) or created

    def set_session_status(self, session_id: str, status: str) -> None:
        if status not in {"active", "paused", "completed", "archived"}:
            raise ValueError(f"unsupported session status: {status}")
        ended_at = utc_now() if status in {"completed", "archived"} else None
        with self._connect() as connection:
            if status == "active":
                connection.execute(
                    """
                    UPDATE sessions SET status = 'paused', ended_at = NULL
                    WHERE status = 'active' AND id != ?
                    """,
                    (session_id,),
                )
            connection.execute(
                "UPDATE sessions SET status = ?, ended_at = ? WHERE id = ?",
                (status, ended_at, session_id),
            )

    def select_session(
        self,
        session_id: str,
        resume: bool = False,
    ) -> RecordingSession | None:
        """Select one session and preserve the single-active-session invariant."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            if resume and row["status"] == "archived":
                raise ValueError("archived sessions cannot be resumed")
            connection.execute(
                """
                UPDATE sessions SET status = 'paused', ended_at = NULL
                WHERE status = 'active' AND id != ?
                """,
                (session_id,),
            )
            if resume:
                connection.execute(
                    "UPDATE sessions SET status = 'active', ended_at = NULL WHERE id = ?",
                    (session_id,),
                )
            refreshed = connection.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        return self._session_from_row(refreshed) if refreshed is not None else None

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

    def list_session_overviews(
        self,
        query: str = "",
        status: str | None = None,
        limit: int = 500,
    ) -> list[SessionOverview]:
        if status is not None and status not in {
            "active",
            "paused",
            "completed",
            "archived",
        }:
            raise ValueError(f"unsupported session status: {status}")
        conditions: list[str] = []
        parameters: list[Any] = []
        normalized_query = query.strip()
        if normalized_query:
            conditions.append("s.name LIKE ? COLLATE NOCASE")
            parameters.append(f"%{normalized_query}%")
        if status is not None:
            conditions.append("s.status = ?")
            parameters.append(status)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        parameters.append(max(1, min(limit, 5000)))

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT s.id,
                       s.name,
                       s.root_path,
                       s.mode,
                       s.status,
                       s.started_at,
                       s.ended_at,
                       COUNT(f.id) AS frames,
                       COALESCE(
                           SUM(CASE WHEN f.id IS NOT NULL AND f.excluded = 0 THEN 1 ELSE 0 END),
                           0
                       ) AS kept_frames,
                       COALESCE(
                           SUM(CASE WHEN f.id IS NOT NULL AND f.excluded = 1 THEN 1 ELSE 0 END),
                           0
                       ) AS excluded_frames,
                       COALESCE(
                           SUM(CASE WHEN f.id IS NOT NULL AND f.excluded = 0 THEN f.duration ELSE 0 END),
                           0
                       ) AS estimated_video_seconds
                FROM sessions AS s
                LEFT JOIN frames AS f
                    ON f.session_id = s.id AND f.deleted_at IS NULL
                {where_clause}
                GROUP BY s.id, s.name, s.root_path, s.mode, s.status,
                         s.started_at, s.ended_at
                ORDER BY s.started_at DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [
            SessionOverview(
                id=row["id"],
                name=row["name"],
                root_path=Path(row["root_path"]),
                mode=row["mode"],
                status=row["status"],
                started_at=row["started_at"],
                ended_at=row["ended_at"],
                frames=int(row["frames"] or 0),
                kept_frames=int(row["kept_frames"] or 0),
                excluded_frames=int(row["excluded_frames"] or 0),
                estimated_video_seconds=float(
                    row["estimated_video_seconds"] or 0
                ),
            )
            for row in rows
        ]

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
