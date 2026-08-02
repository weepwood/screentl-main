use crate::error::{AppError, AppResult};
use crate::models::{SessionSummary, TimelineFrame, TimelinePage};
use chrono::{SecondsFormat, Utc};
use image::{imageops::FilterType, DynamicImage, GenericImageView};
use rusqlite::{params, Connection, OptionalExtension};
use sha2::{Digest, Sha256};
use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use uuid::Uuid;
use walkdir::WalkDir;
use zip::write::SimpleFileOptions;

#[derive(Debug, Clone)]
pub struct Database {
    path: PathBuf,
}

impl Database {
    pub fn new(path: PathBuf) -> AppResult<Self> {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        let database = Self { path };
        database.initialize()?;
        Ok(database)
    }

    fn connect(&self) -> AppResult<Connection> {
        let connection = Connection::open(&self.path)?;
        connection.pragma_update(None, "foreign_keys", "ON")?;
        connection.pragma_update(None, "journal_mode", "WAL")?;
        connection.busy_timeout(std::time::Duration::from_secs(30))?;
        Ok(connection)
    }

    fn initialize(&self) -> AppResult<()> {
        self.connect()?.execute_batch(
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
            "#,
        )?;
        Ok(())
    }

    pub fn recover_interrupted(&self) -> AppResult<()> {
        let now = utc_now();
        let connection = self.connect()?;
        connection.execute("UPDATE sessions SET status = 'paused' WHERE status = 'active'", [])?;
        connection.execute(
            "UPDATE render_jobs SET status = 'failed', error = 'application interrupted', finished_at = ?1 WHERE status IN ('queued', 'running')",
            params![now],
        )?;
        Ok(())
    }

    pub fn create_session(&self, root: &Path, name: &str, mode: &str) -> AppResult<SessionSummary> {
        if !matches!(mode, "named" | "daily" | "fixed") {
            return Err(AppError(format!("不支持的会话模式：{mode}")));
        }
        let normalized = normalize_name(name);
        let id = Uuid::new_v4().simple().to_string();
        let now = utc_now();
        let suffix = if mode == "daily" { now[..10].to_string() } else { id[..8].to_string() };
        let folder = root.join(format!("{}_{}", safe_filename(&normalized), suffix));

        if mode == "daily" {
            if let Some(existing) = self.session_by_path(&folder)? {
                return self.activate_session(&existing.id);
            }
        }
        fs::create_dir_all(folder.join("frames"))?;
        fs::create_dir_all(folder.join("thumbnails"))?;
        fs::create_dir_all(folder.join("output"))?;

        let mut connection = self.connect()?;
        let transaction = connection.transaction()?;
        transaction.execute("UPDATE sessions SET status = 'paused' WHERE status = 'active'", [])?;
        transaction.execute(
            "INSERT INTO sessions (id, name, root_path, mode, status, started_at, created_at, settings_json) VALUES (?1, ?2, ?3, ?4, 'active', ?5, ?5, '{}')",
            params![id, normalized, folder.to_string_lossy(), mode, now],
        )?;
        transaction.commit()?;
        self.get_session(&id)?.ok_or_else(|| AppError("创建会话后无法读取记录".into()))
    }

    pub fn list_sessions(&self, query: &str, status: &str) -> AppResult<Vec<SessionSummary>> {
        let connection = self.connect()?;
        let mut statement = connection.prepare(
            r#"
            SELECT s.id, s.name, s.root_path, s.mode, s.status, s.started_at, s.ended_at,
                   COUNT(f.id) AS frame_count,
                   COALESCE(SUM(CASE WHEN f.excluded = 0 THEN 1 ELSE 0 END), 0) AS kept_count,
                   COALESCE(SUM(CASE WHEN f.excluded = 1 THEN 1 ELSE 0 END), 0) AS excluded_count,
                   COALESCE(SUM(CASE WHEN f.excluded = 0 THEN f.duration ELSE 0 END), 0) AS estimated_seconds
            FROM sessions s
            LEFT JOIN frames f ON f.session_id = s.id AND f.deleted_at IS NULL
            WHERE (?1 = '' OR lower(s.name) LIKE '%' || lower(?1) || '%')
              AND (?2 = 'all' OR s.status = ?2)
            GROUP BY s.id
            ORDER BY CASE s.status WHEN 'active' THEN 0 WHEN 'paused' THEN 1 WHEN 'completed' THEN 2 ELSE 3 END,
                     s.started_at DESC
            "#,
        )?;
        let rows = statement.query_map(params![query.trim(), status], map_session)?;
        rows.collect::<Result<Vec<_>, _>>().map_err(Into::into)
    }

    pub fn latest_session(&self) -> AppResult<Option<SessionSummary>> {
        let connection = self.connect()?;
        connection.query_row(
            &session_select("WHERE s.status != 'archived'", "ORDER BY CASE WHEN s.status = 'active' THEN 0 ELSE 1 END, s.started_at DESC LIMIT 1"),
            [],
            map_session,
        ).optional().map_err(Into::into)
    }

    pub fn get_session(&self, id: &str) -> AppResult<Option<SessionSummary>> {
        let connection = self.connect()?;
        connection.query_row(&session_select("WHERE s.id = ?1", ""), params![id], map_session)
            .optional().map_err(Into::into)
    }

    fn session_by_path(&self, path: &Path) -> AppResult<Option<SessionSummary>> {
        let connection = self.connect()?;
        connection.query_row(
            &session_select("WHERE s.root_path = ?1", ""),
            params![path.to_string_lossy()],
            map_session,
        ).optional().map_err(Into::into)
    }

    pub fn activate_session(&self, id: &str) -> AppResult<SessionSummary> {
        let session = self.get_session(id)?.ok_or_else(|| AppError("会话不存在".into()))?;
        if session.status == "archived" {
            return Err(AppError("归档会话不能恢复记录".into()));
        }
        let mut connection = self.connect()?;
        let transaction = connection.transaction()?;
        transaction.execute("UPDATE sessions SET status = 'paused' WHERE status = 'active' AND id != ?1", params![id])?;
        transaction.execute("UPDATE sessions SET status = 'active', ended_at = NULL WHERE id = ?1", params![id])?;
        transaction.commit()?;
        self.get_session(id)?.ok_or_else(|| AppError("无法读取已恢复会话".into()))
    }

    pub fn complete_session(&self, id: &str) -> AppResult<SessionSummary> {
        self.connect()?.execute(
            "UPDATE sessions SET status = 'completed', ended_at = ?1 WHERE id = ?2",
            params![utc_now(), id],
        )?;
        self.get_session(id)?.ok_or_else(|| AppError("会话不存在".into()))
    }

    pub fn pause_session(&self, id: &str) -> AppResult<()> {
        self.connect()?.execute(
            "UPDATE sessions SET status = 'paused' WHERE id = ?1 AND status = 'active'",
            params![id],
        )?;
        Ok(())
    }

    pub fn session_paths(&self, id: &str) -> AppResult<(PathBuf, PathBuf, PathBuf)> {
        let session = self.get_session(id)?.ok_or_else(|| AppError("会话不存在".into()))?;
        let root = PathBuf::from(session.root_path);
        Ok((root.join("frames"), root.join("thumbnails"), root.join("output")))
    }

    pub fn add_frame(&self, session_id: &str, path: &Path, window_title: &str, app_name: &str) -> AppResult<TimelineFrame> {
        let image = image::open(path)?;
        let (width, height) = image.dimensions();
        let sha256 = sha256_file(path)?;
        let dhash = difference_hash(&image);
        let mut connection = self.connect()?;
        let transaction = connection.transaction()?;
        let sequence: i64 = transaction.query_row(
            "SELECT COALESCE(MAX(sequence), -1) + 1 FROM frames WHERE session_id = ?1",
            params![session_id],
            |row| row.get(0),
        )?;
        let duplicate_of: Option<i64> = transaction.query_row(
            "SELECT id FROM frames WHERE session_id = ?1 AND dhash = ?2 AND deleted_at IS NULL ORDER BY sequence DESC LIMIT 1",
            params![session_id, dhash], |row| row.get(0),
        ).optional()?;
        transaction.execute(
            "INSERT INTO frames (session_id, sequence, captured_at, path, width, height, sha256, dhash, duplicate_of, window_title, app_name) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)",
            params![session_id, sequence, utc_now(), path.to_string_lossy(), width, height, sha256, dhash, duplicate_of, window_title, app_name],
        )?;
        let id = transaction.last_insert_rowid();
        transaction.commit()?;
        self.frame_by_id(id)?.ok_or_else(|| AppError("保存截图索引失败".into()))
    }

    pub fn set_excluded(&self, ids: &[i64], excluded: bool) -> AppResult<usize> {
        if ids.is_empty() { return Ok(0); }
        let connection = self.connect()?;
        let mut changed = 0;
        let mut statement = connection.prepare("UPDATE frames SET excluded = ?1 WHERE id = ?2")?;
        for id in ids { changed += statement.execute(params![excluded as i64, id])?; }
        Ok(changed)
    }

    pub fn delete_frames(&self, ids: &[i64], delete_files: bool) -> AppResult<usize> {
        if ids.is_empty() { return Ok(0); }
        let connection = self.connect()?;
        let mut changed = 0;
        for id in ids {
            let path: Option<String> = connection.query_row("SELECT path FROM frames WHERE id = ?1 AND deleted_at IS NULL", params![id], |row| row.get(0)).optional()?;
            changed += connection.execute("UPDATE frames SET deleted_at = ?1 WHERE id = ?2 AND deleted_at IS NULL", params![utc_now(), id])?;
            if delete_files { if let Some(path) = path { let _ = fs::remove_file(path); } }
        }
        Ok(changed)
    }

    pub fn set_duration(&self, ids: &[i64], duration: f64) -> AppResult<()> {
        if duration <= 0.0 { return Err(AppError("停留时间必须大于零".into())); }
        let connection = self.connect()?;
        for id in ids { connection.execute("UPDATE frames SET duration = ?1 WHERE id = ?2", params![duration, id])?; }
        Ok(())
    }

    pub fn list_timeline(&self, session_id: &str, offset: i64, limit: i64, include_excluded: bool) -> AppResult<TimelinePage> {
        let connection = self.connect()?;
        let condition = if include_excluded { "" } else { "AND excluded = 0" };
        let total: i64 = connection.query_row(
            &format!("SELECT COUNT(*) FROM frames WHERE session_id = ?1 AND deleted_at IS NULL {condition}"),
            params![session_id], |row| row.get(0),
        )?;
        let mut statement = connection.prepare(&format!(
            "SELECT id, session_id, sequence, captured_at, path, width, height, excluded, duplicate_of, app_name, window_title, duration, sha256 FROM frames WHERE session_id = ?1 AND deleted_at IS NULL {condition} ORDER BY sequence LIMIT ?2 OFFSET ?3"
        ))?;
        let raw = statement.query_map(params![session_id, limit.max(1), offset.max(0)], |row| {
            Ok((
                row.get::<_, i64>(0)?, row.get::<_, String>(1)?, row.get::<_, i64>(2)?, row.get::<_, String>(3)?, row.get::<_, String>(4)?,
                row.get::<_, i64>(5)?, row.get::<_, i64>(6)?, row.get::<_, i64>(7)? != 0, row.get::<_, Option<i64>>(8)?,
                row.get::<_, String>(9)?, row.get::<_, String>(10)?, row.get::<_, f64>(11)?, row.get::<_, String>(12)?,
            ))
        })?;
        let (_, thumbnails, _) = self.session_paths(session_id)?;
        let mut frames = Vec::new();
        for item in raw {
            let (id, session_id, sequence, captured_at, path, width, height, excluded, duplicate_of, app_name, window_title, duration, sha256) = item?;
            let thumbnail = thumbnails.join(format!("{}_{}.jpg", id, &sha256[..sha256.len().min(12)]));
            if !thumbnail.exists() { let _ = create_thumbnail(Path::new(&path), &thumbnail); }
            frames.push(TimelineFrame { id, session_id, sequence, captured_at, path, thumbnail_path: thumbnail.exists().then(|| thumbnail.to_string_lossy().into_owned()), width, height, excluded, duplicate_of, app_name, window_title, duration });
        }
        Ok(TimelinePage { offset: offset.max(0), limit: limit.max(1), total, frames })
    }

    pub fn frames_for_render(&self, session_id: &str, include_excluded: bool) -> AppResult<Vec<TimelineFrame>> {
        let total = self.list_timeline(session_id, 0, 1, include_excluded)?.total;
        Ok(self.list_timeline(session_id, 0, total.max(1), include_excluded)?.frames)
    }

    fn frame_by_id(&self, id: i64) -> AppResult<Option<TimelineFrame>> {
        let connection = self.connect()?;
        connection.query_row(
            "SELECT id, session_id, sequence, captured_at, path, width, height, excluded, duplicate_of, app_name, window_title, duration FROM frames WHERE id = ?1 AND deleted_at IS NULL",
            params![id],
            |row| Ok(TimelineFrame { id: row.get(0)?, session_id: row.get(1)?, sequence: row.get(2)?, captured_at: row.get(3)?, path: row.get(4)?, thumbnail_path: None, width: row.get(5)?, height: row.get(6)?, excluded: row.get::<_, i64>(7)? != 0, duplicate_of: row.get(8)?, app_name: row.get(9)?, window_title: row.get(10)?, duration: row.get(11)? }),
        ).optional().map_err(Into::into)
    }

    pub fn archive_session(&self, id: &str, destination: &Path) -> AppResult<PathBuf> {
        let session = self.get_session(id)?.ok_or_else(|| AppError("会话不存在".into()))?;
        fs::create_dir_all(destination)?;
        let source = PathBuf::from(&session.root_path);
        let archive = destination.join(format!("{}.zip", safe_filename(&session.name)));
        let file = fs::File::create(&archive)?;
        let mut zip = zip::ZipWriter::new(file);
        let options = SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);
        for entry in WalkDir::new(&source).into_iter().filter_map(Result::ok).filter(|item| item.file_type().is_file()) {
            let relative = entry.path().strip_prefix(&source).map_err(|error| AppError(error.to_string()))?;
            zip.start_file(relative.to_string_lossy().replace('\\', "/"), options)?;
            let mut input = fs::File::open(entry.path())?;
            std::io::copy(&mut input, &mut zip)?;
        }
        zip.finish()?;
        self.connect()?.execute("UPDATE sessions SET status = 'archived', archived_at = ?1, ended_at = COALESCE(ended_at, ?1) WHERE id = ?2", params![utc_now(), id])?;
        Ok(archive)
    }
}

fn session_select(condition: &str, order: &str) -> String {
    format!(r#"
        SELECT s.id, s.name, s.root_path, s.mode, s.status, s.started_at, s.ended_at,
               COUNT(f.id), COALESCE(SUM(CASE WHEN f.excluded = 0 THEN 1 ELSE 0 END), 0),
               COALESCE(SUM(CASE WHEN f.excluded = 1 THEN 1 ELSE 0 END), 0),
               COALESCE(SUM(CASE WHEN f.excluded = 0 THEN f.duration ELSE 0 END), 0)
        FROM sessions s LEFT JOIN frames f ON f.session_id = s.id AND f.deleted_at IS NULL
        {condition} GROUP BY s.id {order}
    "#)
}

fn map_session(row: &rusqlite::Row<'_>) -> rusqlite::Result<SessionSummary> {
    Ok(SessionSummary { id: row.get(0)?, name: row.get(1)?, root_path: row.get(2)?, mode: row.get(3)?, status: row.get(4)?, started_at: row.get(5)?, ended_at: row.get(6)?, frame_count: row.get(7)?, kept_count: row.get(8)?, excluded_count: row.get(9)?, estimated_seconds: row.get(10)? })
}

fn utc_now() -> String { Utc::now().to_rfc3339_opts(SecondsFormat::Secs, true) }
fn normalize_name(value: &str) -> String { let value = value.trim(); if value.is_empty() { "Untitled session".into() } else { value.into() } }
fn safe_filename(value: &str) -> String {
    let result: String = value.chars().map(|ch| if ch.is_alphanumeric() || "-_. ".contains(ch) { ch } else { '_' }).collect();
    let result = result.trim_matches([' ', '.']);
    if result.is_empty() { "session".into() } else { result.into() }
}
fn sha256_file(path: &Path) -> AppResult<String> {
    let mut file = fs::File::open(path)?;
    let mut digest = Sha256::new();
    let mut buffer = [0u8; 1024 * 1024];
    loop { let read = file.read(&mut buffer)?; if read == 0 { break; } digest.update(&buffer[..read]); }
    Ok(format!("{:x}", digest.finalize()))
}
fn difference_hash(image: &DynamicImage) -> String {
    let sample = image.resize_exact(9, 8, FilterType::Triangle).to_luma8();
    let mut value = 0u64;
    for y in 0..8 { for x in 0..8 { if sample.get_pixel(x, y)[0] > sample.get_pixel(x + 1, y)[0] { value |= 1 << (y * 8 + x); } } }
    format!("{value:016x}")
}
fn create_thumbnail(source: &Path, destination: &Path) -> AppResult<()> {
    let image = image::open(source)?.thumbnail(320, 180).to_rgb8();
    if let Some(parent) = destination.parent() { fs::create_dir_all(parent)?; }
    image.save_with_format(destination, image::ImageFormat::Jpeg)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn safe_names_remove_windows_reserved_characters() {
        assert_eq!(safe_filename("A/B:C*D?"), "A_B_C_D_");
        assert_eq!(safe_filename("..."), "session");
    }
}
