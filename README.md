# Screenshot Time-lapse

本地优先、隐私可控的个人工作过程记录与回顾工具。

项目正在从 Python/Tkinter 迁移到 **Tauri 2 + React + Rust**。从 `0.3.0` 开始，新的桌面应用以 React 作为界面层、Rust 作为业务与系统能力层，并继续兼容读取旧版 `%APPDATA%\ScreenshotTimeLapse\sessions.db`。

## 新架构

```text
React + TypeScript
        ↓ Tauri Commands / Events
Rust Application Core
        ├── Session Service
        ├── Timeline Query
        ├── Capture Coordinator
        ├── Privacy Service
        └── Render Coordinator
                ↓
        SQLite / Windows API / FFmpeg sidecar
```

设计原则：

- 前端不直接访问 SQLite、文件系统或进程。
- 所有敏感能力通过受控 Tauri Commands 暴露。
- Rust 负责会话状态、事务一致性和后台任务生命周期。
- FFmpeg 后续作为 sidecar 单独管理，不再打包 MoviePy、NumPy 和 Python。
- 默认不上传截图、视频或元数据。
- 不捆绑固定 WebView2 Runtime，优先使用 Windows 系统 WebView2。

详细设计见 [`docs/TAURI_ARCHITECTURE.md`](docs/TAURI_ARCHITECTURE.md)。

## 当前迁移进度

### 已完成：阶段 1

- Vite + React + TypeScript 桌面界面。
- Tauri 2 Rust 应用壳。
- 现代侧边栏，以及概览、会话、时间轴、输出、隐私和设置页面。
- Rust 兼容读取旧版 SQLite 会话数据库。
- Rust 会话列表、聚合统计和安全会话切换命令。
- 保持任意时刻最多一个活动会话。
- React 生产构建、Rust 格式、Clippy、单元测试和 Windows NSIS 构建门禁。
- Windows 安装包 35 MB 体积预算。

### 后续迁移

- Rust 原生多显示器截图。
- 锁屏、空闲、电池和应用排除规则。
- 时间轴虚拟列表与隐私遮挡编辑。
- FFmpeg sidecar、进度事件、取消和恢复。
- 托盘、全局快捷键和开机启动。
- 移除旧 Python 桌面运行链。

## 开发环境

需要：

- Node.js 22 或更高版本。
- Rust stable。
- Windows 构建需要 Microsoft C++ Build Tools 与 WebView2。

安装依赖：

```bash
npm install
```

启动桌面开发环境：

```bash
npm run tauri:dev
```

只启动浏览器 UI 预览：

```bash
npm run dev
```

浏览器预览会使用模拟会话数据；Tauri 桌面环境会读取真实 SQLite 数据。

## 检查与测试

```bash
npm run check
cargo fmt --manifest-path src-tauri/Cargo.toml -- --check
cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path src-tauri/Cargo.toml
```

## Windows 构建

```bash
npm run tauri:build -- --bundles nsis
```

输出目录：

```text
src-tauri/target/release/bundle/nsis/
```

GitHub Actions 会验证 NSIS 安装包不超过 35 MB。阶段 1 不内置 FFmpeg，目标安装包应明显小于旧版约 66.5 MB 的 PyInstaller 单文件。

## 数据兼容

Rust 后端当前直接使用旧版数据库路径：

```text
%APPDATA%\ScreenshotTimeLapse\sessions.db
```

会话和截图文件仍保存在普通目录中。迁移不会自动删除或移动旧截图。

Rust 查询遵守以下规则：

- 软删除截图不参与统计。
- 已排除截图不计入预计视频时长。
- 切换当前会话使用单个 SQLite 事务。
- 归档会话不能重新激活。

## 旧 Python 实现

现有 Python/Tkinter、PyInstaller 和命令行代码暂时保留，作为迁移期间的功能对照和数据验证工具。

旧桌面入口：

```bash
python app.py
```

旧实现不再作为默认架构继续扩展。完成 Rust 截图和 FFmpeg sidecar 后，将把 Python 代码移动到独立的 `legacy-python` 目录或历史分支。

## 隐私原则

- 默认完全离线。
- 前端没有直接文件系统或数据库权限。
- 窗口元数据与 OCR 默认关闭。
- 不包含自动云端上传。
- 不提供隐蔽采集模式。
- 所有捕获与系统权限都将在 Rust 层集中审计。
