# Tauri 2 + React + Rust 架构设计

## 目标

本次迁移不是简单替换 UI，而是将桌面应用从继承式 Python/Tkinter 单体改造成边界清晰的本地桌面系统：

- React 只负责状态展示与用户交互。
- Rust 负责业务规则、SQLite、系统权限和后台任务。
- Tauri 负责安全命令桥、窗口、事件与安装包。
- FFmpeg 作为可替换 sidecar，不进入 Rust 主进程。

## 分层

```text
src/                              React presentation
├── App.tsx
├── lib/backend.ts                Tauri command adapter
└── types.ts                      Frontend DTOs

src-tauri/src/
├── domain.rs                     Serializable domain/read models
├── commands.rs                   Tauri command boundary
├── repository.rs                 SQLite adapter
├── lib.rs                        Dependency assembly / bootstrap
└── main.rs                       Desktop entry point
```

后续模块：

```text
src-tauri/src/
├── application/
│   ├── capture_coordinator.rs
│   ├── render_coordinator.rs
│   └── privacy_service.rs
├── domain/
│   ├── session.rs
│   ├── frame.rs
│   └── render_job.rs
├── infrastructure/
│   ├── sqlite.rs
│   ├── windows_capture.rs
│   └── ffmpeg_sidecar.rs
└── commands/
    ├── session.rs
    ├── timeline.rs
    ├── capture.rs
    └── render.rs
```

阶段 1 保持文件数量较少，避免在业务尚未迁移时建立过度抽象。

## 命令安全边界

前端允许调用的命令必须满足：

1. 参数由 Rust 再次验证。
2. 不允许前端提交任意 SQL。
3. 不允许前端执行任意进程或 Shell 字符串。
4. 文件路径必须来自会话记录或受控文件选择器。
5. 截图、OCR、全局快捷键和开机启动必须具有独立权限。

阶段 1 命令：

- `get_app_status`
- `get_dashboard_summary`
- `list_sessions`
- `select_session`

`capabilities/default.json` 目前只启用 `core:default`。

## SQLite 兼容

Rust 继续读取：

```text
%APPDATA%\ScreenshotTimeLapse\sessions.db
```

兼容旧表：

- `sessions`
- `frames`

Rust 仓库不会在读取时迁移或移动截图文件。首次运行只有数据库不存在时才创建兼容表。

会话切换规则：

```text
BEGIN TRANSACTION
  active sessions except target → paused
  target session → active, ended_at = NULL
COMMIT
```

归档会话在事务开始前拒绝恢复。

## React 状态策略

阶段 1 不引入 Redux、路由器或大型组件库：

- 页面导航由本地 `PageKey` 状态管理。
- 远程状态通过小型 Tauri 适配器加载。
- 浏览器模式提供模拟数据。
- 复杂时间轴迁移时再引入虚拟列表，而不是预先增加依赖。

这样可以减少前端产物、依赖风险和迁移复杂度。

## 截图迁移

目标调用链：

```text
React
  → start_capture command
  → CaptureCoordinator
  → WindowsCapturePort
  → Windows Graphics Capture / DXGI
  → image encoder
  → SQLite frame index
  → Tauri event
  → React status update
```

截图任务必须：

- 单会话绑定。
- 支持暂停、停止和安全退出。
- 文件先写临时文件，再原子替换。
- 后台线程不直接操作 WebView。
- 通过事件发送进度和错误。

## FFmpeg sidecar

FFmpeg 使用 Tauri sidecar 规范：

```text
src-tauri/binaries/ffmpeg-<target-triple>.exe
```

Rust 负责：

- 构造固定参数模板。
- 验证输入输出路径。
- 解析 `-progress pipe:1`。
- 保存渲染任务状态。
- 取消并清理临时文件。

前端不能调用任意 sidecar 参数。

发布时可以提供两种安装包：

- Core：不含 FFmpeg，体积最小。
- Full：包含 FFmpeg sidecar，开箱即用。

## 包体积预算

阶段 1 目标：

- React 静态资源：小于 1 MB。
- Rust 主程序：小于 10 MB。
- NSIS 安装包：小于 15 MB，CI 硬上限 35 MB。
- 不捆绑固定 WebView2 Runtime。

阶段 3 加入 FFmpeg 后：

- Core 安装包继续保持小体积。
- Full 安装包按 FFmpeg 二进制大小单独预算。

## 迁移顺序

1. Tauri 壳、现代 UI、SQLite 读取。
2. 会话创建、时间轴查询和文件管理。
3. Rust 原生截图、隐私规则、托盘与快捷键。
4. FFmpeg sidecar 和输出任务中心。
5. 数据对比测试与 Python 旧实现移除。

每个阶段都必须保持现有 SQLite 和截图目录可恢复，不能用一次性重写破坏用户数据。
