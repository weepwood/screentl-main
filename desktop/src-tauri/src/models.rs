use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SessionSummary {
    pub id: String,
    pub name: String,
    pub root_path: String,
    pub mode: String,
    pub status: String,
    pub started_at: String,
    pub ended_at: Option<String>,
    pub frame_count: i64,
    pub kept_count: i64,
    pub excluded_count: i64,
    pub estimated_seconds: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TimelineFrame {
    pub id: i64,
    pub session_id: String,
    pub sequence: i64,
    pub captured_at: String,
    pub path: String,
    pub thumbnail_path: Option<String>,
    pub width: i64,
    pub height: i64,
    pub excluded: bool,
    pub duplicate_of: Option<i64>,
    pub app_name: String,
    pub window_title: String,
    pub duration: f64,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TimelinePage {
    pub offset: i64,
    pub limit: i64,
    pub total: i64,
    pub frames: Vec<TimelineFrame>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CaptureOptions {
    pub interval_seconds: u64,
    pub monitor: usize,
    pub region: Option<[i32; 4]>,
    pub active_window_only: bool,
    pub image_format: String,
    pub quality: u8,
    pub scale: f32,
    pub auto_exclude_duplicates: bool,
}

impl Default for CaptureOptions {
    fn default() -> Self {
        Self {
            interval_seconds: 30,
            monitor: 1,
            region: None,
            active_window_only: false,
            image_format: "png".into(),
            quality: 90,
            scale: 1.0,
            auto_exclude_duplicates: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PrivacySettings {
    pub excluded_apps: Vec<String>,
    pub excluded_title_keywords: Vec<String>,
    pub idle_pause_seconds: u64,
    pub pause_when_locked: bool,
    pub pause_on_battery: bool,
    pub collect_window_metadata: bool,
}

impl Default for PrivacySettings {
    fn default() -> Self {
        Self {
            excluded_apps: Vec::new(),
            excluded_title_keywords: Vec::new(),
            idle_pause_seconds: 0,
            pause_when_locked: true,
            pause_on_battery: false,
            collect_window_metadata: false,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AppSettings {
    pub capture: CaptureOptions,
    pub privacy: PrivacySettings,
    pub ffmpeg_path: Option<String>,
    pub minimize_to_tray: bool,
    pub start_with_windows: bool,
}

impl Default for AppSettings {
    fn default() -> Self {
        Self {
            capture: CaptureOptions::default(),
            privacy: PrivacySettings::default(),
            ffmpeg_path: None,
            minimize_to_tray: true,
            start_with_windows: false,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RenderOptions {
    pub output_format: String,
    pub codec: String,
    pub bitrate: String,
    pub width: Option<u32>,
    pub height: Option<u32>,
    pub fps: u32,
    pub audio_mode: String,
    pub audio_path: Option<String>,
    pub audio_volume: f32,
    pub split_by_hour: bool,
    pub include_excluded: bool,
    pub ffmpeg_path: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AppSnapshot {
    pub current_session: Option<SessionSummary>,
    pub capture_status: String,
    pub render_status: String,
    pub render_progress: f64,
    pub last_error: Option<String>,
    pub ffmpeg_available: bool,
    pub data_directory: String,
    pub app_version: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CaptureEvent {
    pub status: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub frame_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RenderEvent {
    pub status: String,
    pub progress: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub output_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
}
