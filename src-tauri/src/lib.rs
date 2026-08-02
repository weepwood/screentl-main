mod commands;
mod domain;
mod repository;

use commands::{
    get_app_status, get_dashboard_summary, list_sessions, select_session, AppState,
};
use repository::{legacy_database_path, SessionRepository};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let database_path = legacy_database_path();
    let repository = SessionRepository::new(database_path)
        .expect("failed to initialize Screenshot Time-lapse database");

    tauri::Builder::default()
        .manage(AppState { repository })
        .invoke_handler(tauri::generate_handler![
            get_app_status,
            get_dashboard_summary,
            list_sessions,
            select_session
        ])
        .run(tauri::generate_context!())
        .expect("error while running Screenshot Time-lapse");
}
