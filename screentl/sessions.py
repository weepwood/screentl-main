"""SQLite-backed local recording sessions and frame timeline."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def safe_name(value: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character in "-_. " else "_"
        for character in value.strip()
    ).strip(" .")
    return cleaned or "session"


def image_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def difference_hash(path: Path) -> str:
    with Image.open(path) as image:
        sample = image.convert("L").resize((9, 8))
        pixels = list(sample.getdata())
    bits = []
    for row in range(8):
        offset = row * 9
        for column in range(8):
            bits.append(pixels[offset + column] > pixels[offset + column + 1])
    value = sum(int(bit) << index for index, bit in enumerate(bits))
    return f"{value:016x}"


@dataclass(frozen=True)
class RecordingSession:
    id: str
    name: str
    root_path: Path
    mode: str
    status: str
    started_at: str
    ended_at: str | None = None

    @property
    def frames_path(self) -> Path:
        return self.root_path / "frames"

    @property
    def thumbnails_path(self) -> Path:
        return self.root_path / "thumbnails"

    @property
    def output_path(self) -> Path:
        return self.root_path / "output"


@dataclass(frozen=True)
class TimelineFrame:
    id: int
    session_id: str
    sequence: int
    captured_at: str
    path: Path
    width: int
    height: int
    sha256: str
    dhash: str
    duplicate_of: int | None
    excluded: bool
    window_title: str
    app_name: str
    ocr_text: str
    duration: float
    masks: tuple[tuple[int, int, int, int], ...]


class SessionRepository:
    def __init__(self, database: Path) -> None:
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    root_path TEXT NOT NULL UNIQUE,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    created_at TEXT NOT NULL,
                    archived_at TEXT,
                    settings_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS frames (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL,
                    captured_at TEXT NOT NULL,
                    path TEXT NOT NULL UNIQUE,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    dhash TEXT NOT NULL,
                    duplicate_of INTEGER REFERENCES frames(id),
                    excluded INTEGER NOT NULL DEFAULT 0,
                    window_title TEXT NOT NULL DEFAULT '',
                    app_name TEXT NOT NULL DEFAULT '',
                    ocr_text TEXT NOT NULL DEFAULT '',
                    duration REAL NOT NULL DEFAULT 1.0,
                    masks_json TEXT NOT NULL DEFAULT '[]',
                    deleted_at TEXT,
                    UNIQUE(session_id, sequence)
                );

                CREATE INDEX IF NOT EXISTS idx_frames_session_time
                    ON frames(session_id, captured_at);
                CREATE INDEX IF NOT EXISTS idx_frames_dhash
                    ON frames(session_id, dhash);

                CREATE TABLE IF NOT EXISTS chapters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    frame_id INTEGER NOT NULL REFERENCES frames(id) ON DELETE CASCADE,
                    title TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS render_jobs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    format TEXT NOT NULL,
                    status TEXT NOT NULL,
                    output_path TEXT,
                    progress REAL NOT NULL DEFAULT 0,
                    error TEXT,
                    options_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    finished_at TEXT
                );
                """
            )

    def create_session(
        self,
        root: Path,
        name: str,
        mode: str = "named",
        settings: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> RecordingSession:
        if mode not in {"named", "daily", "fixed"}:
            raise ValueError(f"unsupported session mode: {mode}")
        identifier = session_id or uuid.uuid4().hex
        now = utc_now()
        suffix = now[:10] if mode == "daily" else identifier[:8]
        folder = root.expanduser().resolve() / f"{safe_name(name)}_{suffix}"
        for child in ("frames", "thumbnails", "output"):
            (folder / child).mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (
                    id, name, root_path, mode, status, started_at, created_at, settings_json
                ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
                """,
                (
                    identifier,
                    name.strip() or "Untitled session",
                    str(folder),
                    mode,
                    now,
                    now,
                    json.dumps(settings or {}, ensure_ascii=False),
                ),
            )
        return RecordingSession(identifier, name, folder, mode, "active", now)

    def get_session(self, session_id: str) -> RecordingSession | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        return self._session_from_row(row) if row else None

    def latest_session(self, include_archived: bool = False) -> RecordingSession | None:
        condition = "" if include_archived else "WHERE status != 'archived'"
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT * FROM sessions {condition} ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        return self._session_from_row(row) if row else None

    def list_sessions(self, limit: int = 100) -> list[RecordingSession]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?",
                (max(1, limit),),
            ).fetchall()
        return [self._session_from_row(row) for row in rows]

    @staticmethod
    def _session_from_row(row: sqlite3.Row) -> RecordingSession:
        return RecordingSession(
            id=row["id"],
            name=row["name"],
            root_path=Path(row["root_path"]),
            mode=row["mode"],
            status=row["status"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
        )

    def set_session_status(self, session_id: str, status: str) -> None:
        if status not in {"active", "paused", "completed", "archived"}:
            raise ValueError(f"unsupported session status: {status}")
        ended_at = utc_now() if status in {"completed", "archived"} else None
        with self._connect() as connection:
            connection.execute(
                "UPDATE sessions SET status = ?, ended_at = COALESCE(?, ended_at) WHERE id = ?",
                (status, ended_at, session_id),
            )

    def recover_active_sessions(self) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE sessions SET status = 'paused' WHERE status = 'active'"
            )
            return cursor.rowcount

    def add_frame(
        self,
        session_id: str,
        path: Path,
        captured_at: str | None = None,
        window_title: str = "",
        app_name: str = "",
        ocr_text: str = "",
    ) -> TimelineFrame:
        session = self.get_session(session_id)
        if session is None:
            raise KeyError(f"unknown session: {session_id}")
        resolved = path.expanduser().resolve()
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        with Image.open(resolved) as image:
            width, height = image.size
        sha256 = image_hash(resolved)
        dhash = difference_hash(resolved)
        timestamp = captured_at or utc_now()

        with self._connect() as connection:
            sequence = int(
                connection.execute(
                    "SELECT COALESCE(MAX(sequence), -1) + 1 FROM frames WHERE session_id = ?",
                    (session_id,),
                ).fetchone()[0]
            )
            duplicate_row = connection.execute(
                """
                SELECT id FROM frames
                WHERE session_id = ? AND dhash = ? AND deleted_at IS NULL
                ORDER BY sequence DESC LIMIT 1
                """,
                (session_id, dhash),
            ).fetchone()
            duplicate_of = int(duplicate_row["id"]) if duplicate_row else None
            cursor = connection.execute(
                """
                INSERT INTO frames (
                    session_id, sequence, captured_at, path, width, height,
                    sha256, dhash, duplicate_of, window_title, app_name, ocr_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    sequence,
                    timestamp,
                    str(resolved),
                    width,
                    height,
                    sha256,
                    dhash,
                    duplicate_of,
                    window_title,
                    app_name,
                    ocr_text,
                ),
            )
            frame_id = int(cursor.lastrowid)
        frame = self.get_frame(frame_id)
        if frame is None:
            raise RuntimeError("frame insert did not return a record")
        return frame

    def get_frame(self, frame_id: int) -> TimelineFrame | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM frames WHERE id = ? AND deleted_at IS NULL",
                (frame_id,),
            ).fetchone()
        return self._frame_from_row(row) if row else None

    def list_frames(
        self,
        session_id: str,
        offset: int = 0,
        limit: int = 200,
        include_excluded: bool = True,
    ) -> list[TimelineFrame]:
        excluded_clause = "" if include_excluded else "AND excluded = 0"
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM frames
                WHERE session_id = ? AND deleted_at IS NULL {excluded_clause}
                ORDER BY sequence LIMIT ? OFFSET ?
                """,
                (session_id, max(1, limit), max(0, offset)),
            ).fetchall()
        return [self._frame_from_row(row) for row in rows]

    @staticmethod
    def _frame_from_row(row: sqlite3.Row) -> TimelineFrame:
        masks = tuple(tuple(int(value) for value in item) for item in json.loads(row["masks_json"]))
        return TimelineFrame(
            id=int(row["id"]),
            session_id=row["session_id"],
            sequence=int(row["sequence"]),
            captured_at=row["captured_at"],
            path=Path(row["path"]),
            width=int(row["width"]),
            height=int(row["height"]),
            sha256=row["sha256"],
            dhash=row["dhash"],
            duplicate_of=int(row["duplicate_of"]) if row["duplicate_of"] else None,
            excluded=bool(row["excluded"]),
            window_title=row["window_title"],
            app_name=row["app_name"],
            ocr_text=row["ocr_text"],
            duration=float(row["duration"]),
            masks=masks,
        )

    def set_frames_excluded(self, frame_ids: list[int], excluded: bool) -> int:
        if not frame_ids:
            return 0
        placeholders = ",".join("?" for _ in frame_ids)
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE frames SET excluded = ? WHERE id IN ({placeholders})",
                (int(excluded), *frame_ids),
            )
            return cursor.rowcount

    def set_frame_duration(self, frame_id: int, duration: float) -> None:
        if duration <= 0:
            raise ValueError("frame duration must be greater than zero")
        with self._connect() as connection:
            connection.execute(
                "UPDATE frames SET duration = ? WHERE id = ?",
                (duration, frame_id),
            )

    def set_frame_masks(
        self,
        frame_id: int,
        masks: list[tuple[int, int, int, int]],
    ) -> None:
        normalized = []
        for x, y, width, height in masks:
            if width <= 0 or height <= 0:
                raise ValueError("mask width and height must be greater than zero")
            normalized.append((int(x), int(y), int(width), int(height)))
        with self._connect() as connection:
            connection.execute(
                "UPDATE frames SET masks_json = ? WHERE id = ?",
                (json.dumps(normalized), frame_id),
            )

    def delete_frames(self, frame_ids: list[int], delete_files: bool = True) -> int:
        if not frame_ids:
            return 0
        placeholders = ",".join("?" for _ in frame_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT id, path FROM frames WHERE id IN ({placeholders})",
                frame_ids,
            ).fetchall()
            cursor = connection.execute(
                f"UPDATE frames SET deleted_at = ? WHERE id IN ({placeholders})",
                (utc_now(), *frame_ids),
            )
        if delete_files:
            for row in rows:
                Path(row["path"]).unlink(missing_ok=True)
        return cursor.rowcount

    def collapse_duplicates(self, session_id: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE frames SET excluded = 1
                WHERE session_id = ? AND duplicate_of IS NOT NULL AND deleted_at IS NULL
                """,
                (session_id,),
            )
            return cursor.rowcount

    def add_chapter(self, session_id: str, frame_id: int, title: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO chapters (session_id, frame_id, title) VALUES (?, ?, ?)",
                (session_id, frame_id, title.strip()),
            )
            return int(cursor.lastrowid)

    def create_render_job(
        self,
        session_id: str,
        output_format: str,
        options: dict[str, Any],
    ) -> str:
        identifier = uuid.uuid4().hex
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO render_jobs (
                    id, session_id, format, status, options_json, created_at
                ) VALUES (?, ?, ?, 'queued', ?, ?)
                """,
                (identifier, session_id, output_format, json.dumps(options), utc_now()),
            )
        return identifier

    def update_render_job(
        self,
        job_id: str,
        status: str,
        progress: float | None = None,
        output_path: Path | None = None,
        error: str | None = None,
    ) -> None:
        finished = utc_now() if status in {"completed", "failed", "cancelled"} else None
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE render_jobs
                SET status = ?, progress = COALESCE(?, progress),
                    output_path = COALESCE(?, output_path), error = ?,
                    finished_at = COALESCE(?, finished_at)
                WHERE id = ?
                """,
                (
                    status,
                    progress,
                    str(output_path) if output_path else None,
                    error,
                    finished,
                    job_id,
                ),
            )

    def archive_session(self, session_id: str, destination: Path) -> Path:
        session = self.get_session(session_id)
        if session is None:
            raise KeyError(f"unknown session: {session_id}")
        destination.mkdir(parents=True, exist_ok=True)
        archive_base = destination / safe_name(session.name)
        archive = Path(
            shutil.make_archive(
                str(archive_base),
                "zip",
                root_dir=session.root_path.parent,
                base_dir=session.root_path.name,
            )
        )
        with self._connect() as connection:
            connection.execute(
                "UPDATE sessions SET status = 'archived', archived_at = ?, ended_at = COALESCE(ended_at, ?) WHERE id = ?",
                (utc_now(), utc_now(), session_id),
            )
        return archive

    def cleanup(
        self,
        retention_days: int | None = None,
        max_sessions: int | None = None,
    ) -> list[Path]:
        sessions = self.list_sessions(limit=10000)
        now = dt.datetime.now(dt.UTC)
        removable: list[RecordingSession] = []
        for index, session in enumerate(sessions):
            too_many = max_sessions is not None and index >= max_sessions
            too_old = False
            if retention_days is not None and session.ended_at:
                ended = dt.datetime.fromisoformat(session.ended_at)
                too_old = now - ended >= dt.timedelta(days=retention_days)
            if session.status in {"completed", "archived"} and (too_many or too_old):
                removable.append(session)

        removed_paths = []
        with self._connect() as connection:
            for session in removable:
                if session.root_path.exists():
                    shutil.rmtree(session.root_path)
                connection.execute("DELETE FROM sessions WHERE id = ?", (session.id,))
                removed_paths.append(session.root_path)
        return removed_paths

    def session_summary(self, session_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS frames,
                       SUM(CASE WHEN excluded = 1 THEN 1 ELSE 0 END) AS excluded,
                       SUM(CASE WHEN duplicate_of IS NOT NULL THEN 1 ELSE 0 END) AS duplicates,
                       COALESCE(SUM(duration), 0) AS duration
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

    def export_session_manifest(self, session_id: str, destination: Path) -> Path:
        session = self.get_session(session_id)
        if session is None:
            raise KeyError(f"unknown session: {session_id}")
        frames = self.list_frames(session_id, limit=100000)
        payload = {
            "session": {
                **asdict(session),
                "root_path": str(session.root_path),
            },
            "frames": [
                {
                    **asdict(frame),
                    "path": str(frame.path),
                    "masks": list(frame.masks),
                }
                for frame in frames
            ],
            "summary": self.session_summary(session_id),
        }
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return destination
