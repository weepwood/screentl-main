use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct AppStatus {
    pub version: String,
    pub database_path: String,
    pub database_exists: bool,
    pub legacy_database_detected: bool,
    pub migration_phase: String,
    pub backend: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct SessionSummary {
    pub id: String,
    pub name: String,
    pub root_path: String,
    pub mode: String,
    pub status: String,
    pub started_at: String,
    pub ended_at: Option<String>,
    pub frames: i64,
    pub kept_frames: i64,
    pub excluded_frames: i64,
    pub estimated_video_seconds: f64,
    pub is_current: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct DashboardSummary {
    pub total_sessions: i64,
    pub active_sessions: i64,
    pub total_frames: i64,
    pub kept_frames: i64,
    pub excluded_frames: i64,
    pub estimated_video_seconds: f64,
    pub current_session: Option<SessionSummary>,
}
