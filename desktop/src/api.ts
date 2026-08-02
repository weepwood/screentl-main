import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import type {
  AppSettings,
  AppSnapshot,
  CaptureEvent,
  CaptureOptions,
  RenderEvent,
  RenderOptions,
  SessionStatus,
  SessionSummary,
  TimelinePage,
} from "./types";

export const api = {
  snapshot: () => invoke<AppSnapshot>("get_app_snapshot"),
  listSessions: (query = "", status: SessionStatus | "all" = "all") =>
    invoke<SessionSummary[]>("list_sessions", { query, status }),
  createSession: (name: string, mode = "named") =>
    invoke<SessionSummary>("create_session", { name, mode }),
  selectSession: (sessionId: string, resume = false) =>
    invoke<SessionSummary>("select_session", { sessionId, resume }),
  completeSession: () => invoke<void>("complete_current_session"),
  archiveSession: (sessionId: string, destination: string) =>
    invoke<string>("archive_session", { sessionId, destination }),
  startCapture: (options: CaptureOptions) =>
    invoke<void>("start_capture", { options }),
  pauseCapture: () => invoke<void>("pause_capture"),
  resumeCapture: () => invoke<void>("resume_capture"),
  stopCapture: (completeSession = false) =>
    invoke<void>("stop_capture", { completeSession }),
  listTimeline: (
    sessionId: string,
    offset: number,
    limit: number,
    includeExcluded = true,
  ) =>
    invoke<TimelinePage>("list_timeline", {
      sessionId,
      offset,
      limit,
      includeExcluded,
    }),
  setFramesExcluded: (frameIds: number[], excluded: boolean) =>
    invoke<number>("set_frames_excluded", { frameIds, excluded }),
  deleteFrames: (frameIds: number[], deleteFiles = true) =>
    invoke<number>("delete_frames", { frameIds, deleteFiles }),
  setFrameDuration: (frameIds: number[], duration: number) =>
    invoke<void>("set_frame_duration", { frameIds, duration }),
  startRender: (options: RenderOptions) => invoke<void>("start_render", { options }),
  cancelRender: () => invoke<void>("cancel_render"),
  getSettings: () => invoke<AppSettings>("get_settings"),
  saveSettings: (settings: AppSettings) =>
    invoke<AppSettings>("save_settings", { settings }),
  revealPath: (path: string) => invoke<void>("reveal_path", { path }),
  openPath: (path: string) => invoke<void>("open_path", { path }),
};

export const onCaptureEvent = (
  handler: (event: CaptureEvent) => void,
): Promise<UnlistenFn> => listen<CaptureEvent>("capture:event", ({ payload }) => handler(payload));

export const onRenderEvent = (
  handler: (event: RenderEvent) => void,
): Promise<UnlistenFn> => listen<RenderEvent>("render:event", ({ payload }) => handler(payload));

export const onSessionChanged = (
  handler: (session: SessionSummary | null) => void,
): Promise<UnlistenFn> =>
  listen<SessionSummary | null>("session:changed", ({ payload }) => handler(payload));
