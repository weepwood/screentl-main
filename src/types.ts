export type PageKey =
  | "dashboard"
  | "sessions"
  | "timeline"
  | "output"
  | "privacy"
  | "settings";

export type SessionStatus = "active" | "paused" | "completed" | "archived";

export interface AppStatus {
  version: string;
  databasePath: string;
  databaseExists: boolean;
  legacyDatabaseDetected: boolean;
  migrationPhase: string;
  backend: string;
}

export interface SessionSummary {
  id: string;
  name: string;
  rootPath: string;
  mode: string;
  status: SessionStatus;
  startedAt: string;
  endedAt: string | null;
  frames: number;
  keptFrames: number;
  excludedFrames: number;
  estimatedVideoSeconds: number;
  isCurrent: boolean;
}

export interface DashboardSummary {
  totalSessions: number;
  activeSessions: number;
  totalFrames: number;
  keptFrames: number;
  excludedFrames: number;
  estimatedVideoSeconds: number;
  currentSession: SessionSummary | null;
}

export interface SessionFilter {
  query: string;
  status: "all" | SessionStatus;
}
