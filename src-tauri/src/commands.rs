use tauri::State;

use crate::{
    domain::{AppStatus, DashboardSummary, SessionSummary},
    repository::SessionRepository,
};

#[derive(Debug)]
pub struct AppState {
    pub repository: SessionRepository,
}

fn command_error(error: impl std::fmt::Display) -> String {
    error.to_string()
}

#[tauri::command]
pub fn get_app_status(state: State<'_, AppState>) -> AppStatus {
    AppStatus {
        version: env!("CARGO_PKG_VERSION").to_owned(),
        database_path: state.repository.database_path().display().to_string(),
        database_exists: state.repository.database_path().is_file(),
        legacy_database_detected: state.repository.existed_at_start(),
        migration_phase: "Phase 1: Tauri shell and SQLite compatibility".to_owned(),
        backend: "Tauri 2 / Rust / rusqlite".to_owned(),
    }
}

#[tauri::command]
pub fn get_dashboard_summary(state: State<'_, AppState>) -> Result<DashboardSummary, String> {
    state.repository.dashboard_summary().map_err(command_error)
}

#[tauri::command]
pub fn list_sessions(
    state: State<'_, AppState>,
    query: String,
    status: String,
) -> Result<Vec<SessionSummary>, String> {
    let normalized_status = match status.as_str() {
        "all" | "active" | "paused" | "completed" | "archived" => status,
        _ => return Err(format!("Unsupported session status: {status}")),
    };
    state
        .repository
        .list_sessions(&query, &normalized_status)
        .map_err(command_error)
}

#[tauri::command]
pub fn select_session(
    state: State<'_, AppState>,
    session_id: String,
) -> Result<SessionSummary, String> {
    state
        .repository
        .select_session(&session_id)
        .map_err(command_error)
}
