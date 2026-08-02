import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getAppStatus,
  getDashboardSummary,
  listSessions,
  selectSession,
} from "./lib/backend";
import type {
  AppStatus,
  DashboardSummary,
  PageKey,
  SessionFilter,
  SessionStatus,
  SessionSummary,
} from "./types";

const navigation: Array<{ key: PageKey; label: string; glyph: string }> = [
  { key: "dashboard", label: "概览", glyph: "◫" },
  { key: "sessions", label: "会话", glyph: "▣" },
  { key: "timeline", label: "时间轴", glyph: "⌁" },
  { key: "output", label: "输出", glyph: "▷" },
  { key: "privacy", label: "隐私", glyph: "◇" },
  { key: "settings", label: "设置", glyph: "⚙" },
];

const statusLabels: Record<SessionStatus, string> = {
  active: "记录中",
  paused: "已暂停",
  completed: "已完成",
  archived: "已归档",
};

function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function formatDuration(seconds: number): string {
  const rounded = Math.max(0, Math.round(seconds));
  const hours = Math.floor(rounded / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  const remaining = rounded % 60;
  if (hours > 0) {
    return `${hours} 小时 ${minutes} 分`;
  }
  if (minutes > 0) {
    return `${minutes} 分 ${remaining} 秒`;
  }
  return `${remaining} 秒`;
}

function formatDate(value: string | null): string {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

interface MetricCardProps {
  label: string;
  value: string;
  detail: string;
  accent?: boolean;
}

function MetricCard({ label, value, detail, accent = false }: MetricCardProps) {
  return (
    <article className={`metric-card${accent ? " metric-card--accent" : ""}`}>
      <span className="metric-card__label">{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

interface EmptyStateProps {
  title: string;
  description: string;
}

function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <div className="empty-state__icon">◎</div>
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}

interface DashboardPageProps {
  summary: DashboardSummary | null;
  onOpenSessions: () => void;
}

function DashboardPage({ summary, onOpenSessions }: DashboardPageProps) {
  const current = summary?.currentSession ?? null;
  return (
    <div className="page-stack">
      <section className="hero-panel">
        <div>
          <span className="eyebrow">LOCAL-FIRST WORK JOURNAL</span>
          <h2>记录过程，而不是监控自己</h2>
          <p>
            Rust 管理会话、截图、SQLite 与渲染任务；React 只负责清晰、可回顾的桌面体验。
          </p>
        </div>
        <div className="hero-panel__actions">
          <button className="button button--primary" type="button" disabled>
            开始记录
          </button>
          <button className="button" type="button" onClick={onOpenSessions}>
            管理会话
          </button>
        </div>
      </section>

      <section className="metric-grid">
        <MetricCard
          label="会话"
          value={formatNumber(summary?.totalSessions ?? 0)}
          detail={`${summary?.activeSessions ?? 0} 个活动会话`}
          accent
        />
        <MetricCard
          label="截图"
          value={formatNumber(summary?.totalFrames ?? 0)}
          detail={`${formatNumber(summary?.excludedFrames ?? 0)} 张已排除`}
        />
        <MetricCard
          label="保留画面"
          value={formatNumber(summary?.keptFrames ?? 0)}
          detail="仅统计可用于输出的帧"
        />
        <MetricCard
          label="预计视频"
          value={formatDuration(summary?.estimatedVideoSeconds ?? 0)}
          detail="按当前停留时间汇总"
        />
      </section>

      <section className="two-column-grid">
        <article className="panel current-session-card">
          <div className="panel__heading">
            <div>
              <span className="eyebrow">CURRENT SESSION</span>
              <h3>当前会话</h3>
            </div>
            {current ? (
              <span className={`status-pill status-pill--${current.status}`}>
                {statusLabels[current.status]}
              </span>
            ) : null}
          </div>
          {current ? (
            <div className="session-focus">
              <strong>{current.name}</strong>
              <p>{current.rootPath}</p>
              <div className="session-focus__stats">
                <span>{formatNumber(current.frames)} 张截图</span>
                <span>{formatDuration(current.estimatedVideoSeconds)}</span>
                <span>{formatDate(current.startedAt)} 开始</span>
              </div>
            </div>
          ) : (
            <EmptyState
              title="尚未选择会话"
              description="可以从旧版 SQLite 数据库恢复会话，或在后续阶段创建新的 Rust 会话。"
            />
          )}
        </article>

        <article className="panel roadmap-card">
          <div className="panel__heading">
            <div>
              <span className="eyebrow">MIGRATION</span>
              <h3>Tauri 迁移进度</h3>
            </div>
            <span className="progress-badge">阶段 1 / 4</span>
          </div>
          <ol className="roadmap-list">
            <li className="is-complete">React 桌面壳与 Rust 命令层</li>
            <li className="is-complete">兼容旧版 SQLite 会话数据</li>
            <li>Rust 原生截图与隐私规则</li>
            <li>FFmpeg sidecar 与 Python 完全移除</li>
          </ol>
        </article>
      </section>
    </div>
  );
}

interface SessionsPageProps {
  sessions: SessionSummary[];
  filter: SessionFilter;
  loading: boolean;
  onFilterChange: (filter: SessionFilter) => void;
  onSelect: (sessionId: string) => Promise<void>;
}

function SessionsPage({
  sessions,
  filter,
  loading,
  onFilterChange,
  onSelect,
}: SessionsPageProps) {
  return (
    <div className="page-stack">
      <section className="page-header">
        <div>
          <span className="eyebrow">SESSIONS</span>
          <h2>会话管理</h2>
          <p>直接读取旧版数据库，并由 Rust 保证任意时刻最多一个活动会话。</p>
        </div>
        <button className="button button--primary" type="button" disabled>
          新建会话
        </button>
      </section>

      <section className="panel">
        <div className="filter-bar">
          <label className="search-field">
            <span>⌕</span>
            <input
              value={filter.query}
              onChange={(event) =>
                onFilterChange({ ...filter, query: event.target.value })
              }
              placeholder="搜索会话名称"
            />
          </label>
          <select
            value={filter.status}
            onChange={(event) =>
              onFilterChange({
                ...filter,
                status: event.target.value as SessionFilter["status"],
              })
            }
          >
            <option value="all">全部状态</option>
            <option value="active">记录中</option>
            <option value="paused">已暂停</option>
            <option value="completed">已完成</option>
            <option value="archived">已归档</option>
          </select>
        </div>

        {loading ? <div className="loading-row">正在读取 SQLite 会话…</div> : null}
        {!loading && sessions.length === 0 ? (
          <EmptyState
            title="没有匹配的会话"
            description="修改搜索条件，或确认旧版 sessions.db 位于 APPDATA/ScreenshotTimeLapse。"
          />
        ) : null}
        {sessions.length > 0 ? (
          <div className="session-table" role="table" aria-label="会话列表">
            <div className="session-table__row session-table__header" role="row">
              <span>会话</span>
              <span>状态</span>
              <span>截图</span>
              <span>预计时长</span>
              <span>开始时间</span>
              <span />
            </div>
            {sessions.map((session) => (
              <div
                className={`session-table__row${session.isCurrent ? " is-current" : ""}`}
                role="row"
                key={session.id}
              >
                <div className="session-name-cell">
                  <strong>{session.name}</strong>
                  <small>{session.rootPath}</small>
                </div>
                <span className={`status-pill status-pill--${session.status}`}>
                  {statusLabels[session.status]}
                </span>
                <span>
                  {formatNumber(session.keptFrames)} / {formatNumber(session.frames)}
                </span>
                <span>{formatDuration(session.estimatedVideoSeconds)}</span>
                <span>{formatDate(session.startedAt)}</span>
                <button
                  className="button button--small"
                  type="button"
                  disabled={session.status === "archived" || session.isCurrent}
                  onClick={() => void onSelect(session.id)}
                >
                  {session.isCurrent ? "当前" : "设为当前"}
                </button>
              </div>
            ))}
          </div>
        ) : null}
      </section>
    </div>
  );
}

function TimelinePage({ current }: { current: SessionSummary | null }) {
  return (
    <div className="page-stack">
      <section className="page-header">
        <div>
          <span className="eyebrow">TIMELINE</span>
          <h2>时间轴</h2>
          <p>下一阶段将使用虚拟列表加载大量缩略图，不再创建成千上万个桌面控件。</p>
        </div>
      </section>
      <section className="timeline-layout panel">
        <aside className="timeline-hours">
          <strong>小时</strong>
          {["09:00", "10:00", "11:00", "13:00", "14:00"].map((hour, index) => (
            <button className={index === 2 ? "is-active" : ""} key={hour} type="button">
              {hour}
            </button>
          ))}
        </aside>
        <div className="timeline-canvas">
          <div className="timeline-canvas__header">
            <div>
              <strong>{current?.name ?? "未选择会话"}</strong>
              <span>{current ? `${current.keptFrames} 个可用画面` : "选择会话后加载"}</span>
            </div>
            <span className="progress-badge">Rust 查询接口待接入</span>
          </div>
          <div className="thumbnail-grid">
            {Array.from({ length: 12 }, (_, index) => (
              <article className="thumbnail-placeholder" key={index}>
                <div className="thumbnail-placeholder__screen">
                  <span>{String(index + 1).padStart(2, "0")}</span>
                </div>
                <small>11:{String(index * 5).padStart(2, "0")}</small>
              </article>
            ))}
          </div>
        </div>
        <aside className="inspector-panel">
          <span className="eyebrow">INSPECTOR</span>
          <h3>截图详情</h3>
          <dl>
            <div><dt>应用</dt><dd>等待 Rust 元数据</dd></div>
            <div><dt>停留</dt><dd>1.0 秒</dd></div>
            <div><dt>隐私</dt><dd>无遮挡</dd></div>
          </dl>
          <button className="button" type="button" disabled>添加遮挡</button>
        </aside>
      </section>
    </div>
  );
}

function OutputPage() {
  return (
    <div className="page-stack">
      <section className="page-header">
        <div>
          <span className="eyebrow">RENDER QUEUE</span>
          <h2>输出任务</h2>
          <p>FFmpeg 将作为独立 sidecar 运行，主应用不再携带 MoviePy、NumPy 和 Python。</p>
        </div>
        <button className="button button--primary" type="button" disabled>新建输出</button>
      </section>
      <section className="panel task-list">
        <div className="task-row">
          <div className="task-icon">MP4</div>
          <div><strong>会话视频输出</strong><small>H.264 · 1920×1080 · 4 Mbps</small></div>
          <span className="status-pill status-pill--paused">等待迁移</span>
        </div>
        <div className="architecture-note">
          <strong>目标调用链</strong>
          <code>React → Tauri Command → Rust RenderCoordinator → FFmpeg sidecar</code>
        </div>
      </section>
    </div>
  );
}

function PrivacyPage() {
  const rules = [
    ["全局隐私暂停", "通过 Rust 全局快捷键立即暂停截图"],
    ["排除应用", "密码管理器、聊天工具和其他敏感应用"],
    ["空闲与锁屏暂停", "系统无操作或锁屏时不采集"],
    ["本地 OCR", "默认关闭，仅调用本机工具，不上传图片"],
  ];
  return (
    <div className="page-stack">
      <section className="page-header">
        <div><span className="eyebrow">PRIVACY</span><h2>隐私控制</h2><p>所有敏感权限都在 Rust 侧收口，前端只能调用被授权的命令。</p></div>
      </section>
      <section className="settings-grid">
        {rules.map(([title, detail], index) => (
          <article className="panel setting-card" key={title}>
            <div><strong>{title}</strong><p>{detail}</p></div>
            <button className={`switch${index === 2 ? " is-on" : ""}`} type="button" aria-label={title} disabled><span /></button>
          </article>
        ))}
      </section>
    </div>
  );
}

function SettingsPage({ status }: { status: AppStatus | null }) {
  return (
    <div className="page-stack">
      <section className="page-header">
        <div><span className="eyebrow">SETTINGS</span><h2>应用设置</h2><p>当前阶段优先验证数据兼容、架构边界和包体积。</p></div>
      </section>
      <section className="panel info-list">
        <div><span>应用版本</span><strong>{status?.version ?? "读取中"}</strong></div>
        <div><span>后端</span><strong>{status?.backend ?? "Rust / Tauri"}</strong></div>
        <div><span>迁移阶段</span><strong>{status?.migrationPhase ?? "读取中"}</strong></div>
        <div><span>SQLite 路径</span><code>{status?.databasePath ?? "读取中"}</code></div>
        <div><span>检测到旧数据</span><strong>{status?.legacyDatabaseDetected ? "是" : "否"}</strong></div>
        <div><span>数据库可用</span><strong>{status?.databaseExists ? "是" : "否"}</strong></div>
      </section>
      <section className="panel size-budget">
        <div><span className="eyebrow">BUNDLE BUDGET</span><h3>Windows 包体积目标</h3></div>
        <div className="budget-track"><span style={{ width: "38%" }} /></div>
        <div className="budget-labels"><span>Tauri 主体目标 &lt; 15 MB</span><span>旧版 66.5 MB</span></div>
      </section>
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState<PageKey>("dashboard");
  const [status, setStatus] = useState<AppStatus | null>(null);
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [filter, setFilter] = useState<SessionFilter>({ query: "", status: "all" });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadOverview = useCallback(async () => {
    const [nextStatus, nextDashboard] = await Promise.all([
      getAppStatus(),
      getDashboardSummary(),
    ]);
    setStatus(nextStatus);
    setDashboard(nextDashboard);
  }, []);

  const loadSessions = useCallback(async (nextFilter: SessionFilter) => {
    setLoading(true);
    try {
      setSessions(await listSessions(nextFilter));
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadOverview().catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : String(reason));
    });
  }, [loadOverview]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadSessions(filter), 180);
    return () => window.clearTimeout(timer);
  }, [filter, loadSessions]);

  const currentSession = dashboard?.currentSession ?? null;
  const activeLabel = useMemo(
    () => navigation.find((item) => item.key === page)?.label ?? "概览",
    [page],
  );

  const handleSelectSession = useCallback(
    async (sessionId: string) => {
      try {
        await selectSession(sessionId);
        await Promise.all([loadOverview(), loadSessions(filter)]);
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : String(reason));
      }
    },
    [filter, loadOverview, loadSessions],
  );

  let content;
  switch (page) {
    case "sessions":
      content = (
        <SessionsPage
          sessions={sessions}
          filter={filter}
          loading={loading}
          onFilterChange={setFilter}
          onSelect={handleSelectSession}
        />
      );
      break;
    case "timeline":
      content = <TimelinePage current={currentSession} />;
      break;
    case "output":
      content = <OutputPage />;
      break;
    case "privacy":
      content = <PrivacyPage />;
      break;
    case "settings":
      content = <SettingsPage status={status} />;
      break;
    default:
      content = <DashboardPage summary={dashboard} onOpenSessions={() => setPage("sessions")} />;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand__mark"><span /></div>
          <div><strong>ScreenTL</strong><small>Local work journal</small></div>
        </div>
        <nav>
          {navigation.map((item) => (
            <button
              className={page === item.key ? "is-active" : ""}
              key={item.key}
              type="button"
              onClick={() => setPage(item.key)}
            >
              <span className="nav-glyph">{item.glyph}</span>
              {item.label}
            </button>
          ))}
        </nav>
        <div className="sidebar__footer">
          <div className="runtime-dot" />
          <div><strong>Rust Core</strong><small>{status?.version ?? "正在连接"}</small></div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div><span>Screenshot Time-lapse</span><strong>{activeLabel}</strong></div>
          <div className="topbar__status">
            <span className={`record-indicator${currentSession?.status === "active" ? " is-active" : ""}`} />
            {currentSession?.status === "active" ? "正在记录" : "本地模式"}
          </div>
        </header>
        {error ? (
          <div className="error-banner"><strong>操作失败</strong><span>{error}</span><button type="button" onClick={() => setError(null)}>×</button></div>
        ) : null}
        <div className="content-area">{content}</div>
      </main>
    </div>
  );
}
