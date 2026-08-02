export type PageKey = "dashboard" | "sessions" | "timeline" | "render" | "settings";

export type SessionStatus = "active" | "paused" | "completed" | "archived";
export type TaskStatus = "idle" | "running" | "paused" | "stopping" | "completed" | "failed" | "cancelled";

export interface SessionSummary {
  id: string;
  name: string;
  rootPath: string;
  mode: string;
  status: SessionStatus;
  startedAt: string;
  endedAt: string | null;
  frameCount: number;
  keptCount: number;
  excludedCount: number;
  estimatedSeconds: number;
}

export interface TimelineFrame {
  id: number;
  sessionId: string;
  sequence: number;
  capturedAt: string;
  path: string;
  thumbnailPath: string | null;
  width: number;
  height: number;
  excluded: boolean;
  duplicateOf: number | null;
  appName: string;
  windowTitle: string;
  duration: number;
}

export interface TimelinePage {
  offset: number;
  limit: number;
  total: number;
  frames: TimelineFrame[];
}

export interface CaptureOptions {
  intervalSeconds: number;
  monitor: number;
  region: [number, number, number, number] | null;
  activeWindowOnly: boolean;
  imageFormat: "png" | "jpeg" | "webp";
  quality: number;
  scale: number;
  autoExcludeDuplicates: boolean;
}

export interface PrivacySettings {
  excludedApps: string[];
  excludedTitleKeywords: string[];
  idlePauseSeconds: number;
  pauseWhenLocked: boolean;
  pauseOnBattery: boolean;
  collectWindowMetadata: boolean;
}

export interface RenderOptions {
  outputFormat: "mp4" | "gif";
  codec: "h264" | "h265" | "vp9" | "nvenc" | "qsv" | "amf";
  bitrate: string;
  width: number | null;
  height: number | null;
  fps: number;
  audioMode: "none" | "fixed" | "loop";
  audioPath: string | null;
  audioVolume: number;
  splitByHour: boolean;
  includeExcluded: boolean;
  ffmpegPath: string | null;
}

export interface AppSettings {
  capture: CaptureOptions;
  privacy: PrivacySettings;
  ffmpegPath: string | null;
  minimizeToTray: boolean;
  startWithWindows: boolean;
}

export interface AppSnapshot {
  currentSession: SessionSummary | null;
  captureStatus: TaskStatus;
  renderStatus: TaskStatus;
  renderProgress: number;
  lastError: string | null;
  ffmpegAvailable: boolean;
  dataDirectory: string;
  appVersion: string;
}

export interface CaptureEvent {
  status: TaskStatus;
  framePath?: string;
  message?: string;
}

export interface RenderEvent {
  status: TaskStatus;
  progress: number;
  outputPath?: string;
  message?: string;
}
