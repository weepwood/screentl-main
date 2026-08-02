use std::{env, fs, path::PathBuf};

use rusqlite::{Connection, OptionalExtension, Row, params};
use thiserror::Error;

use crate::domain::{DashboardSummary, SessionSummary};

#[derive(Debug, Error)]
pub enum RepositoryError {
    #[error("SQLite operation failed: {0}")]
    Sqlite(#[from] rusqlite::Error),
    #[error("File-system operation failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("Session not found: {0}")]
    SessionNotFound(String),
    #[error("Archived sessions cannot be resumed")]
    ArchivedSession,
}

pub type RepositoryResult<T> = Result<T, RepositoryError>;

#[derive(Debug)]
pub struct SessionRepository {
    database_path: PathBuf,
    existed_at_start: bool,
}

impl SessionRepository {
    pub fn new(database_path: PathBuf) -> RepositoryResult<Self> {
        let existed_at_start = database_path.is_file();
        if let Some(parent) = database_path.parent() {
            fs::create_dir_all(parent)?;
        }
        let repository = Self {
            database_path,
            existed_at_start,
        };
        repository.initialize()?;
        Ok(repository)
    }

    pub fn database_path(&self) -> &PathBuf {
        &self.database_path
    }

    pub fn existed_at_start(&self) -> bool {
        self.existed_at_start
    }

    fn connect(&self) -> RepositoryResult<Connection> {
        let connection = Connection::open(&self.database_path)?;
        connection.pragma_update(None, "foreign_keys", "ON")?;
        connection.pragma_update(None, "journal_mode", "WAL")?;
        connection.busy_timeout(std::time::Duration::from_secs(15))?;
        Ok(connection)
    }

    fn initialize(&self) -> RepositoryResult<()> {
        let connection = self.connect()?;
        connection.execute_batch(
            r#"
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
            "#,
        )?;
        Ok(())
    }

    fn session_from_row(row: &Row<'_>) -> rusqlite::Result<SessionSummary> {
        let status: String = row.get("status")?;
        Ok(SessionSummary {
            id: row.get("id")?,
            name: row.get("name")?,
            root_path: row.get("root_path")?,
            mode: row.get("mode")?,
            is_current: status == "active",
            status,
            started_at: row.get("started_at")?,
            ended_at: row.get("ended_at")?,
            frames: row.get("frames")?,
            kept_frames: row.get("kept_frames")?,
            excluded_frames: row.get("excluded_frames")?,
            estimated_video_seconds: row.get("estimated_video_seconds")?,
        })
    }

    pub fn list_sessions(
        &self,
        query: &str,
        status: &str,
    ) -> RepositoryResult<Vec<SessionSummary>> {
        let connection = self.connect()?;
        let mut statement = connection.prepare(
            r#"
            SELECT
                s.id,
                s.name,
                s.root_path,
                s.mode,
                s.status,
                s.started_at,
                s.ended_at,
                COUNT(f.id) AS frames,
                COALESCE(SUM(CASE WHEN f.excluded = 0 THEN 1 ELSE 0 END), 0) AS kept_frames,
                COALESCE(SUM(CASE WHEN f.excluded = 1 THEN 1 ELSE 0 END), 0) AS excluded_frames,
                COALESCE(SUM(CASE WHEN f.excluded = 0 THEN f.duration ELSE 0 END), 0.0)
                    AS estimated_video_seconds
            FROM sessions s
            LEFT JOIN frames f
                ON f.session_id = s.id AND f.deleted_at IS NULL
            WHERE (?1 = '' OR LOWER(s.name) LIKE '%' || LOWER(?1) || '%')
              AND (?2 = 'all' OR s.status = ?2)
            GROUP BY s.id
            ORDER BY s.started_at DESC
            LIMIT 1000
            "#,
        )?;
        let rows = statement.query_map(params![query.trim(), status], Self::session_from_row)?;
        rows.collect::<Result<Vec<_>, _>>().map_err(Into::into)
    }

    pub fn get_session(&self, session_id: &str) -> RepositoryResult<SessionSummary> {
        let connection = self.connect()?;
        connection
            .query_row(
                r#"
                SELECT
                    s.id,
                    s.name,
                    s.root_path,
                    s.mode,
                    s.status,
                    s.started_at,
                    s.ended_at,
                    COUNT(f.id) AS frames,
                    COALESCE(SUM(CASE WHEN f.excluded = 0 THEN 1 ELSE 0 END), 0) AS kept_frames,
                    COALESCE(SUM(CASE WHEN f.excluded = 1 THEN 1 ELSE 0 END), 0) AS excluded_frames,
                    COALESCE(SUM(CASE WHEN f.excluded = 0 THEN f.duration ELSE 0 END), 0.0)
                        AS estimated_video_seconds
                FROM sessions s
                LEFT JOIN frames f
                    ON f.session_id = s.id AND f.deleted_at IS NULL
                WHERE s.id = ?1
                GROUP BY s.id
                "#,
                [session_id],
                Self::session_from_row,
            )
            .optional()?
            .ok_or_else(|| RepositoryError::SessionNotFound(session_id.to_owned()))
    }

    pub fn select_session(&self, session_id: &str) -> RepositoryResult<SessionSummary> {
        let mut connection = self.connect()?;
        let transaction = connection.transaction()?;
        let target_status = transaction
            .query_row(
                "SELECT status FROM sessions WHERE id = ?1",
                [session_id],
                |row| row.get::<_, String>(0),
            )
            .optional()?
            .ok_or_else(|| RepositoryError::SessionNotFound(session_id.to_owned()))?;
        if target_status == "archived" {
            return Err(RepositoryError::ArchivedSession);
        }

        transaction.execute(
            "UPDATE sessions SET status = 'paused' WHERE status = 'active' AND id != ?1",
            [session_id],
        )?;
        transaction.execute(
            "UPDATE sessions SET status = 'active', ended_at = NULL WHERE id = ?1",
            [session_id],
        )?;
        transaction.commit()?;
        self.get_session(session_id)
    }

    pub fn dashboard_summary(&self) -> RepositoryResult<DashboardSummary> {
        let sessions = self.list_sessions("", "all")?;
        Ok(DashboardSummary {
            total_sessions: sessions.len() as i64,
            active_sessions: sessions
                .iter()
                .filter(|session| session.status == "active")
                .count() as i64,
            total_frames: sessions.iter().map(|session| session.frames).sum(),
            kept_frames: sessions.iter().map(|session| session.kept_frames).sum(),
            excluded_frames: sessions.iter().map(|session| session.excluded_frames).sum(),
            estimated_video_seconds: sessions
                .iter()
                .map(|session| session.estimated_video_seconds)
                .sum(),
            current_session: sessions.into_iter().find(|session| session.is_current),
        })
    }
}

pub fn legacy_database_path() -> PathBuf {
    let app_data = env::var_os("APPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(|| env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));
    app_data.join("ScreenshotTimeLapse").join("sessions.db")
}

#[cfg(test)]
mod tests {
    use tempfile::tempdir;

    use super::*;

    fn repository() -> (tempfile::TempDir, SessionRepository) {
        let directory = tempdir().expect("create temp directory");
        let repository = SessionRepository::new(directory.path().join("sessions.db"))
            .expect("create repository");
        (directory, repository)
    }

    fn seed(repository: &SessionRepository) {
        let connection = repository.connect().expect("connect");
        connection
            .execute(
                "INSERT INTO sessions (id, name, root_path, mode, status, started_at, created_at) VALUES (?1, ?2, ?3, 'named', ?4, ?5, ?5)",
                params!["one", "First", "C:/sessions/one", "active", "2026-08-02T01:00:00+00:00"],
            )
            .expect("insert first session");
        connection
            .execute(
                "INSERT INTO sessions (id, name, root_path, mode, status, started_at, created_at) VALUES (?1, ?2, ?3, 'named', ?4, ?5, ?5)",
                params!["two", "Second", "C:/sessions/two", "completed", "2026-08-01T01:00:00+00:00"],
            )
            .expect("insert second session");
        connection
            .execute(
                "INSERT INTO frames (session_id, sequence, captured_at, path, width, height, sha256, dhash, excluded, duration) VALUES ('one', 0, '2026-08-02T01:01:00+00:00', 'C:/frames/one.png', 100, 100, 'a', 'a', 0, 2.5)",
                [],
            )
            .expect("insert kept frame");
        connection
            .execute(
                "INSERT INTO frames (session_id, sequence, captured_at, path, width, height, sha256, dhash, excluded, duration) VALUES ('one', 1, '2026-08-02T01:02:00+00:00', 'C:/frames/two.png', 100, 100, 'b', 'b', 1, 8.0)",
                [],
            )
            .expect("insert excluded frame");
    }

    #[test]
    fn reads_legacy_session_aggregates() {
        let (_directory, repository) = repository();
        seed(&repository);

        let sessions = repository
            .list_sessions("fir", "all")
            .expect("list sessions");

        assert_eq!(sessions.len(), 1);
        assert_eq!(sessions[0].frames, 2);
        assert_eq!(sessions[0].kept_frames, 1);
        assert_eq!(sessions[0].excluded_frames, 1);
        assert_eq!(sessions[0].estimated_video_seconds, 2.5);
    }

    #[test]
    fn selecting_session_preserves_single_active_invariant() {
        let (_directory, repository) = repository();
        seed(&repository);

        let selected = repository.select_session("two").expect("select session");
        let sessions = repository.list_sessions("", "all").expect("list sessions");

        assert_eq!(selected.status, "active");
        assert_eq!(
            sessions
                .iter()
                .filter(|session| session.status == "active")
                .count(),
            1
        );
        assert!(
            sessions
                .iter()
                .find(|session| session.id == "one")
                .is_some_and(|session| session.status == "paused")
        );
    }

    #[test]
    fn dashboard_uses_kept_frame_duration() {
        let (_directory, repository) = repository();
        seed(&repository);

        let summary = repository.dashboard_summary().expect("dashboard");

        assert_eq!(summary.total_sessions, 2);
        assert_eq!(summary.total_frames, 2);
        assert_eq!(summary.kept_frames, 1);
        assert_eq!(summary.excluded_frames, 1);
        assert_eq!(summary.estimated_video_seconds, 2.5);
    }
}
