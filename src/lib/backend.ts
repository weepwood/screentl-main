import { invoke } from "@tauri-apps/api/core";

import type {
  AppStatus,
  DashboardSummary,
  SessionFilter,
  SessionSummary,
} from "../types";

const browserSessions: SessionSummary[] = [
  {
    id: "demo-active",
    name: "Tauri 迁移开发",
    rootPath: "C:\\Users\\Demo\\Pictures\\ScreenshotTimeLapse\\sessions\\tauri-migration",
    mode: "named",
    status: "active",
    startedAt: "2026-08-02T05:30:00+00:00",
    endedAt: null,
    frames: 428,
    keptFrames: 401,
    excludedFrames: 27,
    estimatedVideoSeconds: 401,
    isCurrent: true,
  },
  {
    id: "demo-completed",
    name: "MRR 功能开发",
    rootPath: "C:\\Users\\Demo\\Pictures\\ScreenshotTimeLapse\\sessions\\mrr",
    mode: "named",
    status: "completed",
    startedAt: "2026-08-01T01:00:00+00:00",
    endedAt: "2026-08-01T09:10:00+00:00",
    frames: 984,
    keptFrames: 912,
    excludedFrames: 72,
    estimatedVideoSeconds: 912,
    isCurrent: false,
  },
];

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

function summarize(sessions: SessionSummary[]): DashboardSummary {
  return {
    totalSessions: sessions.length,
    activeSessions: sessions.filter((session) => session.status === "active").length,
    totalFrames: sessions.reduce((total, session) => total + session.frames, 0),
    keptFrames: sessions.reduce((total, session) => total + session.keptFrames, 0),
    excludedFrames: sessions.reduce(
      (total, session) => total + session.excludedFrames,
      0,
    ),
    estimatedVideoSeconds: sessions.reduce(
      (total, session) => total + session.estimatedVideoSeconds,
      0,
    ),
    currentSession: sessions.find((session) => session.isCurrent) ?? null,
  };
}

export async function getAppStatus(): Promise<AppStatus> {
  if (!isTauriRuntime()) {
    return {
      version: "0.3.0-browser-preview",
      databasePath: "%APPDATA%\\ScreenshotTimeLapse\\sessions.db",
      databaseExists: true,
      legacyDatabaseDetected: true,
      migrationPhase: "Tauri UI preview",
      backend: "browser mock",
    };
  }
  return invoke<AppStatus>("get_app_status");
}

export async function getDashboardSummary(): Promise<DashboardSummary> {
  if (!isTauriRuntime()) {
    return summarize(browserSessions);
  }
  return invoke<DashboardSummary>("get_dashboard_summary");
}

export async function listSessions(
  filter: SessionFilter,
): Promise<SessionSummary[]> {
  if (!isTauriRuntime()) {
    const normalized = filter.query.trim().toLocaleLowerCase();
    return browserSessions.filter((session) => {
      const matchesQuery =
        !normalized || session.name.toLocaleLowerCase().includes(normalized);
      const matchesStatus =
        filter.status === "all" || session.status === filter.status;
      return matchesQuery && matchesStatus;
    });
  }
  return invoke<SessionSummary[]>("list_sessions", {
    query: filter.query,
    status: filter.status,
  });
}

export async function selectSession(sessionId: string): Promise<SessionSummary> {
  if (!isTauriRuntime()) {
    const selected = browserSessions.find((session) => session.id === sessionId);
    if (!selected) {
      throw new Error("会话不存在");
    }
    for (const session of browserSessions) {
      session.isCurrent = session.id === sessionId;
      if (session.id === sessionId && session.status !== "archived") {
        session.status = "active";
        session.endedAt = null;
      } else if (session.status === "active") {
        session.status = "paused";
      }
    }
    return selected;
  }
  return invoke<SessionSummary>("select_session", { sessionId });
}
