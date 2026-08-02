import { useCallback, useEffect, useMemo, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { api, onCaptureEvent, onRenderEvent, onSessionChanged } from "./api";
import { Icon } from "./components/Icon";
import type {
  AppSettings,
  AppSnapshot,
  CaptureOptions,
  PageKey,
  RenderOptions,
  SessionStatus,
  SessionSummary,
  TimelineFrame,
  TimelinePage,
} from "./types";

const pageItems: Array<{ key: PageKey; label: string }> = [
  { key: "dashboard", label: "概览" },
  { key: "sessions", label: "会话" },
  { key: "timeline", label: "时间轴" },
  { key: "render", label: "输出" },
  { key: "settings", label: "设置" },
];

const emptySnapshot: AppSnapshot = {
  currentSession: null,
  captureStatus: "idle",
  renderStatus: "idle",
  renderProgress: 0,
  lastError: null,
  ffmpegAvailable: false,
  dataDirectory: "",
  appVersion: "0.3.0",
};

const defaultCapture: CaptureOptions = {
  intervalSeconds: 30,
  monitor: 1,
  region: null,
  activeWindowOnly: false,
  imageFormat: "png",
  quality: 90,
  scale: 1,
  autoExcludeDuplicates: true,
};

const defaultSettings: AppSettings = {
  capture: defaultCapture,
  privacy: {
    excludedApps: [],
    excludedTitleKeywords: [],
    idlePauseSeconds: 0,
    pauseWhenLocked: true,
    pauseOnBattery: false,
    collectWindowMetadata: false,
  },
  ffmpegPath: null,
  minimizeToTray: true,
  startWithWindows: false,
};

const defaultRender: RenderOptions = {
  outputFormat: "mp4",
  codec: "h264",
  bitrate: "4M",
  width: 1920,
  height: 1080,
  fps: 25,
  audioMode: "none",
  audioPath: null,
  audioVolume: 0.2,
  splitByHour: false,
  includeExcluded: false,
  ffmpegPath: null,
};

function formatDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function formatDuration(seconds: number): string {
  const value = Math.max(0, Math.round(seconds));
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const remain = value % 60;
  return [hours, minutes, remain].map((part) => String(part).padStart(2, "0")).join(":");
}

function statusText(status: string): string {
  return {
    idle: "空闲",
    running: "运行中",
    paused: "已暂停",
    stopping: "正在停止",
    completed: "已完成",
    failed: "失败",
    cancelled: "已取消",
    active: "活动",
    archived: "已归档",
  }[status] ?? status;
}

function classNames(...names: Array<string | false | null | undefined>): string {
  return names.filter(Boolean).join(" ");
}

interface Notice {
  type: "info" | "success" | "error";
  message: string;
}

export default function App() {
  const [page, setPage] = useState<PageKey>("dashboard");
  const [snapshot, setSnapshot] = useState<AppSnapshot>(emptySnapshot);
  const [settings, setSettings] = useState<AppSettings>(defaultSettings);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<Notice | null>(null);

  const reportError = useCallback((error: unknown) => {
    setNotice({ type: "error", message: error instanceof Error ? error.message : String(error) });
  }, []);

  const refresh = useCallback(async () => {
    const [nextSnapshot, nextSessions] = await Promise.all([
      api.snapshot(),
      api.listSessions(),
    ]);
    setSnapshot(nextSnapshot);
    setSessions(nextSessions);
  }, []);

  useEffect(() => {
    let mounted = true;
    Promise.all([api.snapshot(), api.getSettings(), api.listSessions()])
      .then(([nextSnapshot, nextSettings, nextSessions]) => {
        if (!mounted) return;
        setSnapshot(nextSnapshot);
        setSettings(nextSettings);
        setSessions(nextSessions);
      })
      .catch(reportError)
      .finally(() => mounted && setLoading(false));

    const unlisteners = Promise.all([
      onCaptureEvent((event) => {
        setSnapshot((current) => ({
          ...current,
          captureStatus: event.status,
          lastError: event.status === "failed" ? event.message ?? "截图失败" : current.lastError,
        }));
        if (event.framePath) void refresh();
      }),
      onRenderEvent((event) => {
        setSnapshot((current) => ({
          ...current,
          renderStatus: event.status,
          renderProgress: event.progress,
          lastError: event.status === "failed" ? event.message ?? "输出失败" : current.lastError,
        }));
        if (event.outputPath) {
          setNotice({ type: "success", message: `输出完成：${event.outputPath}` });
        }
      }),
      onSessionChanged((session) => {
        setSnapshot((current) => ({ ...current, currentSession: session }));
        void refresh();
      }),
    ]);

    return () => {
      mounted = false;
      void unlisteners.then((items) => items.forEach((unlisten) => unlisten()));
    };
  }, [refresh, reportError]);

  const run = useCallback(
    async (action: () => Promise<unknown>, success?: string) => {
      try {
        await action();
        if (success) setNotice({ type: "success", message: success });
        await refresh();
      } catch (error) {
        reportError(error);
      }
    },
    [refresh, reportError],
  );

  if (loading) {
    return <div className="startup-screen"><div className="spinner" /><p>正在加载本地会话…</p></div>;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">ST</div>
          <div><strong>Screenshot</strong><span>Time-lapse</span></div>
        </div>
        <nav>
          {pageItems.map((item) => (
            <button
              key={item.key}
              className={classNames("nav-item", page === item.key && "active")}
              onClick={() => setPage(item.key)}
            >
              <Icon name={item.key} size={19} />
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className={classNames("status-dot", snapshot.captureStatus === "running" && "live")} />
          <div>
            <span>{snapshot.captureStatus === "running" ? "正在记录" : "本地模式"}</span>
            <small>v{snapshot.appVersion}</small>
          </div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar" data-tauri-drag-region>
          <div>
            <h1>{pageItems.find((item) => item.key === page)?.label}</h1>
            <p>{snapshot.currentSession ? `当前会话：${snapshot.currentSession.name}` : "尚未选择会话"}</p>
          </div>
          <div className="topbar-actions">
            <span className={classNames("privacy-chip", settings.privacy.collectWindowMetadata && "warning")}>完全本地</span>
            <button className="icon-button" title="刷新" onClick={() => void refresh()}><Icon name="refresh" stroke /></button>
          </div>
        </header>

        {notice && (
          <div className={classNames("notice", notice.type)}>
            <span>{notice.message}</span>
            <button onClick={() => setNotice(null)}>×</button>
          </div>
        )}

        <section className="content">
          {page === "dashboard" && (
            <Dashboard
              snapshot={snapshot}
              settings={settings}
              onNavigate={setPage}
              onRun={run}
            />
          )}
          {page === "sessions" && (
            <Sessions
              sessions={sessions}
              currentId={snapshot.currentSession?.id ?? null}
              onRefresh={refresh}
              onRun={run}
            />
          )}
          {page === "timeline" && (
            <Timeline session={snapshot.currentSession} onError={reportError} />
          )}
          {page === "render" && (
            <Render
              snapshot={snapshot}
              settings={settings}
              onRun={run}
            />
          )}
          {page === "settings" && (
            <Settings
              value={settings}
              dataDirectory={snapshot.dataDirectory}
              onChange={setSettings}
              onSaved={(next) => {
                setSettings(next);
                setNotice({ type: "success", message: "设置已保存" });
              }}
              onError={reportError}
            />
          )}
        </section>
      </main>
    </div>
  );
}

interface DashboardProps {
  snapshot: AppSnapshot;
  settings: AppSettings;
  onNavigate: (page: PageKey) => void;
  onRun: (action: () => Promise<unknown>, success?: string) => Promise<void>;
}

function Dashboard({ snapshot, settings, onNavigate, onRun }: DashboardProps) {
  const session = snapshot.currentSession;
  const captureRunning = snapshot.captureStatus === "running" || snapshot.captureStatus === "paused";
  return (
    <div className="page-grid dashboard-grid">
      <article className="hero-card">
        <div>
          <span className="eyebrow">当前工作记录</span>
          <h2>{session?.name ?? "创建一个记录会话"}</h2>
          <p>{session ? `开始于 ${formatDate(session.startedAt)}` : "截图、索引和视频均保存在本机。"}</p>
        </div>
        <div className="record-controls">
          {!session ? (
            <button className="primary" onClick={() => onNavigate("sessions")}>新建会话</button>
          ) : !captureRunning ? (
            <button className="primary record" onClick={() => void onRun(() => api.startCapture(settings.capture))}>
              <Icon name="play" size={18} />开始记录
            </button>
          ) : (
            <>
              <button className="secondary" onClick={() => void onRun(() => snapshot.captureStatus === "paused" ? api.resumeCapture() : api.pauseCapture())}>
                <Icon name={snapshot.captureStatus === "paused" ? "play" : "pause"} size={18} />
                {snapshot.captureStatus === "paused" ? "继续" : "暂停"}
              </button>
              <button className="danger" onClick={() => void onRun(() => api.stopCapture(false), "记录已停止")}>
                <Icon name="stop" size={18} />停止
              </button>
            </>
          )}
        </div>
      </article>

      <article className="metric-card"><span>截图</span><strong>{session?.frameCount ?? 0}</strong><small>保留 {session?.keptCount ?? 0}</small></article>
      <article className="metric-card"><span>预计视频</span><strong>{formatDuration(session?.estimatedSeconds ?? 0)}</strong><small>按单帧停留时间</small></article>
      <article className="metric-card"><span>截图任务</span><strong className={`status-${snapshot.captureStatus}`}>{statusText(snapshot.captureStatus)}</strong><small>{settings.capture.intervalSeconds} 秒一次</small></article>
      <article className="metric-card"><span>视频引擎</span><strong>{snapshot.ffmpegAvailable ? "可用" : "未配置"}</strong><small>{snapshot.ffmpegAvailable ? "FFmpeg 已检测" : "可在设置中指定"}</small></article>

      <article className="panel activity-panel">
        <div className="panel-heading"><div><h3>快速操作</h3><p>常用工作流入口</p></div></div>
        <div className="quick-actions">
          <button onClick={() => onNavigate("timeline")}><Icon name="timeline" /><span>整理时间轴<small>排除重复或敏感截图</small></span></button>
          <button onClick={() => onNavigate("render")}><Icon name="render" /><span>生成视频<small>MP4、GIF 和分段输出</small></span></button>
          <button onClick={() => session && void api.openPath(session.rootPath)} disabled={!session}><Icon name="folder" /><span>打开会话目录<small>直接访问原始文件</small></span></button>
          <button onClick={() => onNavigate("settings")}><Icon name="settings" /><span>隐私规则<small>排除应用、锁屏和空闲暂停</small></span></button>
        </div>
      </article>

      <article className="panel privacy-panel">
        <div className="panel-heading"><div><h3>隐私状态</h3><p>默认不采集额外元数据</p></div><span className="success-badge">本地优先</span></div>
        <ul className="check-list">
          <li><Icon name="check" stroke />云端上传：关闭</li>
          <li><Icon name="check" stroke />窗口元数据：{settings.privacy.collectWindowMetadata ? "开启" : "关闭"}</li>
          <li><Icon name="check" stroke />锁屏暂停：{settings.privacy.pauseWhenLocked ? "开启" : "关闭"}</li>
          <li><Icon name="check" stroke />应用排除：{settings.privacy.excludedApps.length} 条</li>
        </ul>
      </article>
    </div>
  );
}

interface SessionsProps {
  sessions: SessionSummary[];
  currentId: string | null;
  onRefresh: () => Promise<void>;
  onRun: (action: () => Promise<unknown>, success?: string) => Promise<void>;
}

function Sessions({ sessions, currentId, onRefresh, onRun }: SessionsProps) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<SessionStatus | "all">("all");
  const [name, setName] = useState("");
  const filtered = useMemo(() => sessions.filter((session) => {
    const matchesQuery = !query || session.name.toLocaleLowerCase().includes(query.toLocaleLowerCase());
    return matchesQuery && (status === "all" || session.status === status);
  }), [query, sessions, status]);

  const create = async () => {
    const value = name.trim();
    if (!value) return;
    await onRun(() => api.createSession(value), "会话已创建");
    setName("");
  };

  return (
    <div className="sessions-layout">
      <article className="panel session-create">
        <div><h3>新建会话</h3><p>将同一段工作过程组织在独立目录中。</p></div>
        <div className="inline-form">
          <input value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：MRR 功能开发" onKeyDown={(event) => event.key === "Enter" && void create()} />
          <button className="primary" onClick={() => void create()} disabled={!name.trim()}>创建</button>
        </div>
      </article>

      <div className="list-toolbar">
        <label className="search-box"><Icon name="search" stroke size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索会话" /></label>
        <select value={status} onChange={(event) => setStatus(event.target.value as SessionStatus | "all")}>
          <option value="all">全部状态</option><option value="active">活动</option><option value="paused">暂停</option><option value="completed">完成</option><option value="archived">归档</option>
        </select>
        <button className="secondary icon-only" title="刷新" onClick={() => void onRefresh()}><Icon name="refresh" stroke /></button>
      </div>

      <div className="session-table">
        <div className="table-head"><span>会话</span><span>状态</span><span>截图</span><span>预计时长</span><span>开始时间</span><span /></div>
        {filtered.map((session) => (
          <div className={classNames("table-row", session.id === currentId && "selected")} key={session.id}>
            <div className="session-name"><strong>{session.name}</strong><small>{session.rootPath}</small></div>
            <span><span className={`state-badge ${session.status}`}>{statusText(session.status)}</span></span>
            <span>{session.keptCount}<small className="muted"> / {session.frameCount}</small></span>
            <span>{formatDuration(session.estimatedSeconds)}</span>
            <span>{formatDate(session.startedAt)}</span>
            <div className="row-actions">
              <button title="打开目录" onClick={() => void api.openPath(session.rootPath)}><Icon name="folder" size={17} /></button>
              {session.status !== "archived" && session.id !== currentId && <button title="设为当前" onClick={() => void onRun(() => api.selectSession(session.id, false))}><Icon name="check" stroke size={17} /></button>}
              {session.status === "completed" && <button title="继续记录" onClick={() => void onRun(() => api.selectSession(session.id, true), "会话已恢复")}><Icon name="play" size={17} /></button>}
            </div>
          </div>
        ))}
        {filtered.length === 0 && <div className="empty-state">没有符合条件的会话</div>}
      </div>
    </div>
  );
}

function Timeline({ session, onError }: { session: SessionSummary | null; onError: (error: unknown) => void }) {
  const [page, setPage] = useState<TimelinePage>({ offset: 0, limit: 80, total: 0, frames: [] });
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [includeExcluded, setIncludeExcluded] = useState(true);
  const load = useCallback(async (offset = 0) => {
    if (!session) return;
    try {
      const result = await api.listTimeline(session.id, offset, page.limit, includeExcluded);
      setPage(result);
      setSelected(new Set());
    } catch (error) {
      onError(error);
    }
  }, [includeExcluded, onError, page.limit, session]);

  useEffect(() => { void load(0); }, [load]);

  if (!session) return <EmptyPage title="尚未选择会话" description="在会话页面创建或选择一个会话后即可整理时间轴。" />;

  const mutate = async (action: () => Promise<unknown>) => {
    try { await action(); await load(page.offset); } catch (error) { onError(error); }
  };
  const ids = [...selected];
  return (
    <div className="timeline-layout">
      <div className="list-toolbar timeline-toolbar">
        <strong>{page.total} 张截图</strong>
        <label className="switch-label"><input type="checkbox" checked={includeExcluded} onChange={(event) => setIncludeExcluded(event.target.checked)} />显示已排除</label>
        <div className="toolbar-spacer" />
        <button className="secondary" disabled={!ids.length} onClick={() => void mutate(() => api.setFramesExcluded(ids, false))}>保留</button>
        <button className="secondary" disabled={!ids.length} onClick={() => void mutate(() => api.setFramesExcluded(ids, true))}>排除</button>
        <button className="danger subtle" disabled={!ids.length} onClick={() => void mutate(() => api.deleteFrames(ids, true))}><Icon name="trash" stroke size={16} />删除</button>
      </div>
      <div className="timeline-grid">
        {page.frames.map((frame) => (
          <FrameCard key={frame.id} frame={frame} selected={selected.has(frame.id)} onToggle={() => setSelected((current) => {
            const next = new Set(current); next.has(frame.id) ? next.delete(frame.id) : next.add(frame.id); return next;
          })} />
        ))}
      </div>
      {page.frames.length === 0 && <div className="empty-state">此会话还没有截图</div>}
      <div className="pager">
        <button className="secondary" disabled={page.offset === 0} onClick={() => void load(Math.max(0, page.offset - page.limit))}>上一页</button>
        <span>{page.total ? `${page.offset + 1}–${Math.min(page.offset + page.limit, page.total)} / ${page.total}` : "0 / 0"}</span>
        <button className="secondary" disabled={page.offset + page.limit >= page.total} onClick={() => void load(page.offset + page.limit)}>下一页</button>
      </div>
    </div>
  );
}

function FrameCard({ frame, selected, onToggle }: { frame: TimelineFrame; selected: boolean; onToggle: () => void }) {
  const source = frame.thumbnailPath ? `asset://${encodeURI(frame.thumbnailPath.replaceAll("\\", "/"))}` : "";
  return (
    <button className={classNames("frame-card", selected && "selected", frame.excluded && "excluded")} onClick={onToggle}>
      <div className="frame-image">{source ? <img src={source} alt={`截图 ${frame.sequence}`} loading="lazy" /> : <span>#{frame.sequence}</span>}<span className="frame-check">✓</span></div>
      <div className="frame-meta"><strong>#{frame.sequence}</strong><span>{formatDate(frame.capturedAt)}</span></div>
      <div className="frame-meta small"><span>{frame.appName || frame.windowTitle || `${frame.width}×${frame.height}`}</span><span>{frame.duration.toFixed(1)}s</span></div>
    </button>
  );
}

function Render({ snapshot, settings, onRun }: { snapshot: AppSnapshot; settings: AppSettings; onRun: (action: () => Promise<unknown>, success?: string) => Promise<void> }) {
  const [options, setOptions] = useState<RenderOptions>({ ...defaultRender, ffmpegPath: settings.ffmpegPath });
  const running = snapshot.renderStatus === "running" || snapshot.renderStatus === "stopping";
  const chooseAudio = async () => {
    const selected = await open({ multiple: false, filters: [{ name: "音频", extensions: ["mp3", "wav", "m4a", "aac", "ogg", "flac"] }] });
    if (selected) setOptions((current) => ({ ...current, audioPath: selected, audioMode: "fixed" }));
  };
  if (!snapshot.currentSession) return <EmptyPage title="没有可输出的会话" description="先选择一个包含截图的会话。" />;
  return (
    <div className="render-layout">
      <article className="panel render-form">
        <div className="panel-heading"><div><h3>视频参数</h3><p>使用独立 FFmpeg 进程，不阻塞界面。</p></div><span className={classNames("state-badge", snapshot.ffmpegAvailable ? "active" : "paused")}>{snapshot.ffmpegAvailable ? "FFmpeg 可用" : "需要配置"}</span></div>
        <div className="form-grid">
          <Field label="格式"><select value={options.outputFormat} onChange={(event) => setOptions({ ...options, outputFormat: event.target.value as RenderOptions["outputFormat"] })}><option value="mp4">MP4</option><option value="gif">GIF</option></select></Field>
          <Field label="编码"><select value={options.codec} onChange={(event) => setOptions({ ...options, codec: event.target.value as RenderOptions["codec"] })}><option value="h264">H.264</option><option value="h265">H.265</option><option value="vp9">VP9</option><option value="nvenc">NVIDIA NVENC</option><option value="qsv">Intel QSV</option><option value="amf">AMD AMF</option></select></Field>
          <Field label="帧率"><input type="number" min={1} max={60} value={options.fps} onChange={(event) => setOptions({ ...options, fps: Number(event.target.value) })} /></Field>
          <Field label="码率"><input value={options.bitrate} onChange={(event) => setOptions({ ...options, bitrate: event.target.value })} /></Field>
          <Field label="宽度"><input type="number" value={options.width ?? ""} onChange={(event) => setOptions({ ...options, width: event.target.value ? Number(event.target.value) : null })} /></Field>
          <Field label="高度"><input type="number" value={options.height ?? ""} onChange={(event) => setOptions({ ...options, height: event.target.value ? Number(event.target.value) : null })} /></Field>
          <Field label="背景音乐" wide><div className="path-input"><input readOnly value={options.audioPath ?? "未选择"} /><button className="secondary" onClick={() => void chooseAudio()}>选择</button></div></Field>
          <Field label="音量"><input type="number" min={0} max={4} step={0.1} value={options.audioVolume} onChange={(event) => setOptions({ ...options, audioVolume: Number(event.target.value) })} /></Field>
          <Field label="音乐模式"><select value={options.audioMode} onChange={(event) => setOptions({ ...options, audioMode: event.target.value as RenderOptions["audioMode"] })}><option value="none">关闭</option><option value="fixed">单曲</option><option value="loop">循环</option></select></Field>
        </div>
        <div className="check-row"><label><input type="checkbox" checked={options.splitByHour} onChange={(event) => setOptions({ ...options, splitByHour: event.target.checked })} />按小时分段</label><label><input type="checkbox" checked={options.includeExcluded} onChange={(event) => setOptions({ ...options, includeExcluded: event.target.checked })} />包含已排除截图</label></div>
        <div className="render-actions">
          {!running ? <button className="primary" disabled={!snapshot.ffmpegAvailable} onClick={() => void onRun(() => api.startRender(options))}><Icon name="render" size={18} />开始输出</button> : <button className="danger" onClick={() => void onRun(() => api.cancelRender())}>取消输出</button>}
        </div>
      </article>
      <article className="panel render-progress-card">
        <div className="progress-ring" style={{ "--progress": `${snapshot.renderProgress * 360}deg` } as React.CSSProperties}><div><strong>{Math.round(snapshot.renderProgress * 100)}%</strong><span>{statusText(snapshot.renderStatus)}</span></div></div>
        <h3>{snapshot.currentSession.name}</h3><p>输出文件保存在会话的 output 目录中，失败不会覆盖已有文件。</p>
        <button className="secondary" onClick={() => void api.openPath(`${snapshot.currentSession!.rootPath}\\output`)}><Icon name="folder" size={17} />打开输出目录</button>
      </article>
    </div>
  );
}

function Settings({ value, dataDirectory, onChange, onSaved, onError }: { value: AppSettings; dataDirectory: string; onChange: (value: AppSettings) => void; onSaved: (value: AppSettings) => void; onError: (error: unknown) => void }) {
  const chooseFfmpeg = async () => {
    const selected = await open({ multiple: false, filters: [{ name: "FFmpeg", extensions: ["exe"] }] });
    if (selected) onChange({ ...value, ffmpegPath: selected });
  };
  const updateCapture = (patch: Partial<CaptureOptions>) => onChange({ ...value, capture: { ...value.capture, ...patch } });
  const save = async () => { try { onSaved(await api.saveSettings(value)); } catch (error) { onError(error); } };
  return (
    <div className="settings-stack">
      <article className="panel settings-section"><div className="panel-heading"><div><h3>捕获</h3><p>截图由 Rust 后台任务执行。</p></div></div><div className="form-grid">
        <Field label="间隔（秒）"><input type="number" min={1} value={value.capture.intervalSeconds} onChange={(event) => updateCapture({ intervalSeconds: Number(event.target.value) })} /></Field>
        <Field label="显示器"><input type="number" min={0} value={value.capture.monitor} onChange={(event) => updateCapture({ monitor: Number(event.target.value) })} /></Field>
        <Field label="格式"><select value={value.capture.imageFormat} onChange={(event) => updateCapture({ imageFormat: event.target.value as CaptureOptions["imageFormat"] })}><option value="png">PNG</option><option value="jpeg">JPEG</option><option value="webp">WebP</option></select></Field>
        <Field label="质量"><input type="number" min={1} max={100} value={value.capture.quality} onChange={(event) => updateCapture({ quality: Number(event.target.value) })} /></Field>
        <Field label="缩放"><input type="number" min={0.1} max={1} step={0.1} value={value.capture.scale} onChange={(event) => updateCapture({ scale: Number(event.target.value) })} /></Field>
      </div><div className="check-row"><label><input type="checkbox" checked={value.capture.activeWindowOnly} onChange={(event) => updateCapture({ activeWindowOnly: event.target.checked })} />仅活动窗口</label><label><input type="checkbox" checked={value.capture.autoExcludeDuplicates} onChange={(event) => updateCapture({ autoExcludeDuplicates: event.target.checked })} />自动排除重复</label></div></article>

      <article className="panel settings-section"><div className="panel-heading"><div><h3>隐私</h3><p>元数据默认关闭，应用不会上传任何截图。</p></div></div><div className="form-grid">
        <Field label="排除应用" wide><input value={value.privacy.excludedApps.join(", ")} onChange={(event) => onChange({ ...value, privacy: { ...value.privacy, excludedApps: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) } })} placeholder="KeePass.exe, 1Password.exe" /></Field>
        <Field label="排除标题关键词" wide><input value={value.privacy.excludedTitleKeywords.join(", ")} onChange={(event) => onChange({ ...value, privacy: { ...value.privacy, excludedTitleKeywords: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) } })} placeholder="password, private" /></Field>
        <Field label="空闲暂停（秒）"><input type="number" min={0} value={value.privacy.idlePauseSeconds} onChange={(event) => onChange({ ...value, privacy: { ...value.privacy, idlePauseSeconds: Number(event.target.value) } })} /></Field>
      </div><div className="check-row"><label><input type="checkbox" checked={value.privacy.pauseWhenLocked} onChange={(event) => onChange({ ...value, privacy: { ...value.privacy, pauseWhenLocked: event.target.checked } })} />锁屏暂停</label><label><input type="checkbox" checked={value.privacy.pauseOnBattery} onChange={(event) => onChange({ ...value, privacy: { ...value.privacy, pauseOnBattery: event.target.checked } })} />电池供电暂停</label><label><input type="checkbox" checked={value.privacy.collectWindowMetadata} onChange={(event) => onChange({ ...value, privacy: { ...value.privacy, collectWindowMetadata: event.target.checked } })} />采集窗口标题和应用名</label></div></article>

      <article className="panel settings-section"><div className="panel-heading"><div><h3>视频与存储</h3><p>Lite 版本不捆绑 FFmpeg，因此安装包更小。</p></div></div><div className="form-grid">
        <Field label="FFmpeg 路径" wide><div className="path-input"><input value={value.ffmpegPath ?? ""} onChange={(event) => onChange({ ...value, ffmpegPath: event.target.value || null })} placeholder="自动从 PATH 检测" /><button className="secondary" onClick={() => void chooseFfmpeg()}>浏览</button></div></Field>
        <Field label="数据目录" wide><div className="path-input"><input readOnly value={dataDirectory} /><button className="secondary" onClick={() => void api.openPath(dataDirectory)}>打开</button></div></Field>
      </div></article>
      <div className="settings-actions"><button className="primary" onClick={() => void save()}>保存设置</button></div>
    </div>
  );
}

function Field({ label, wide = false, children }: { label: string; wide?: boolean; children: React.ReactNode }) {
  return <label className={classNames("field", wide && "wide")}><span>{label}</span>{children}</label>;
}

function EmptyPage({ title, description }: { title: string; description: string }) {
  return <div className="empty-page"><div className="empty-icon"><Icon name="sessions" size={34} /></div><h2>{title}</h2><p>{description}</p></div>;
}
