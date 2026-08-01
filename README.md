# Screenshot Time-lapse

本地优先、隐私可控的个人工作过程记录与回顾工具。它可以定时记录屏幕，将截图整理为会话时间轴，并生成视频、GIF、联系表和本地摘要。项目默认不会上传截图、视频或元数据。

## 主要能力

### 记录会话

- 创建命名会话、每日会话或固定会话。
- SQLite 仅保存索引和状态，原始截图仍是普通图片文件。
- 程序异常退出后，活动会话会恢复为暂停状态，中断的渲染任务会标记为失败。
- 支持会话结束、继续、ZIP 归档、清单导出和按天数清理。
- 每日模式在同一天重新启动时会复用当天会话，避免目录冲突。

### 屏幕捕获

- 多显示器、全屏、指定区域和当前活动窗口。
- PNG、JPEG、WebP，支持质量与缩放设置。
- 自动识别并排除重复画面。
- 空闲、锁屏或使用电池时自动暂停。
- 可按应用名称或窗口标题关键词排除敏感内容。
- `Ctrl+Alt+P` 全局切换隐私暂停。

### 时间轴

- 分页浏览，并按小时分组。
- 批量保留、排除或删除截图。
- 调整单张截图的停留时间。
- 标记章节。
- 为截图添加模糊、黑块或像素化遮挡。
- 生成缩略图缓存、联系表和静态 HTML 预览。

### 专业输出

- 独立 FFmpeg 进程，支持进度、取消和失败恢复。
- 输出 MP4、GIF 或按小时分段视频。
- 支持 H.264、H.265、VP9，以及 NVENC、QSV、AMF 硬件编码入口。
- 可设置分辨率、帧率、码率和单帧停留时间。
- 音频支持关闭、固定、随机、循环或顺序拼接，并支持音量与淡入淡出。
- 输出使用版本化文件名，先写临时文件，成功后原子提交。

### 本地智能能力

- 可选本地 Tesseract OCR，默认关闭。
- 按 OCR、应用、窗口标题和文件名搜索。
- 按应用聚类，并识别长时间重复或停滞阶段。
- 生成本地 JSON 或 Markdown 工作摘要。
- 不包含内置云端上传逻辑；云端处理开关固定关闭。

## 安装

项目支持 Python 3.10～3.13。运行依赖由 `requirements.lock` 锁定：

```bash
python -m pip install -r requirements.txt
```

视频输出使用随 `imageio-ffmpeg` 安装的 FFmpeg。多显示器捕获使用 MSS。启用 OCR 时，需要用户自行安装 Tesseract 并确保 `tesseract` 命令可用。

## 图形界面

```bash
python app.py
```

主窗口保留开始、暂停、停止截图和视频输出操作，并增加四组菜单：

- **会话**：新建、继续、结束、归档和清理。
- **时间轴**：浏览截图、批量整理、联系表、HTML 预览、本地摘要和清单导出。
- **隐私**：隐私暂停，以及显示器、格式、排除规则、空闲和锁屏策略。
- **输出**：专业视频、GIF 和分段输出。

截图和渲染由受控后台服务执行；后台线程只发布事件，所有 Tkinter 操作均由主线程处理。关闭程序时可以等待视频完成、取消任务退出或返回程序。

Windows 桌面入口使用单实例锁。重复启动不会创建第二个截图进程，而会尝试恢复并激活已有窗口。

## 会话命令行

`journal.py` 提供与桌面应用共用的会话、时间轴和渲染能力：

```bash
# 创建会话
python journal.py create "MRR 功能开发"

# 查看会话
python journal.py list
python journal.py status

# 多显示器记录；按 Ctrl+C 停止
python journal.py capture --monitor 1 --interval 30

# 指定区域、WebP 和隐私规则
python journal.py capture \
  --region 100 100 1600 900 \
  --format webp \
  --quality 85 \
  --exclude-app KeePass.exe \
  --exclude-title password \
  --idle-pause 300

# 时间轴与批量整理
python journal.py timeline --limit 200
python journal.py exclude 12 13 14
python journal.py duration 1.5 12 13
python journal.py mask 12 100 80 360 120
python journal.py collapse

# 专业输出
python journal.py render --codec h264 --bitrate 4M --resolution 1920 1080
python journal.py render --format gif --fps 12
python journal.py render --split-by-hour --audio-mode loop --audio "D:\Music\track.mp3"

# 本地检索与摘要
python journal.py search "project"
python journal.py summary --output summary.md
python journal.py contact-sheet contact-sheet.jpg
python journal.py preview timeline.html

# 归档和清理
python journal.py archive "D:\Archives"
python journal.py cleanup --days 30 --max-sessions 100
```

省略 `--session` 时默认使用最近会话。

## 兼容命令行

旧的独立截图和视频入口继续保留：

```bash
python screenshot.py --folder "D:\Pictures\ScreenshotTimeLapse\2026-08-02" --interval 30
python makevideo.py --folder "D:\Pictures\ScreenshotTimeLapse\2026-08-02" --fps 25
```

不要同时运行多个 `screenshot.py` 进程并写入同一个目录。桌面应用已通过单实例锁避免这一情况，但独立命令行进程之间不提供跨进程目录锁。

## 数据目录

默认会话目录：

```text
%USERPROFILE%\Pictures\ScreenshotTimeLapse\sessions\
└── <会话名>_<日期或ID>\
    ├── frames\
    ├── thumbnails\
    └── output\
```

应用状态：

```text
%APPDATA%\ScreenshotTimeLapse\
├── config.json
├── journal.json
└── sessions.db
```

数据库损坏不会使原始图片消失；截图仍可以直接通过文件管理器访问。

## 测试和检查

测试、静态检查和覆盖率配置统一保存在 `pyproject.toml`：

```bash
python -m pip install -r requirements-ci.txt
python -m ruff check app.py journal.py makevideo.py screenshot.py screentl scripts tests
python -m pytest --cov=screentl --cov-report=term-missing
python -m pip_audit -r requirements.lock
```

覆盖率门槛针对非 GUI 核心层。图形界面、Windows 平台适配和桌面协调器不计入核心覆盖率。

## Windows 构建

双击 `build_windows.bat`，或执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

构建过程会创建隔离环境、安装锁定依赖、运行检查和测试、生成图标与版本资源、使用受版本控制的 PyInstaller spec 构建 EXE、执行 `--diagnose` 冒烟测试，并生成 SHA-256：

```text
dist/
├── ScreenshotTimeLapse.exe
└── ScreenshotTimeLapse.exe.sha256
```

## 自动化发布

仓库包含三条 GitHub Actions：

- `Quality Review`：PR 和 `master` 推送时执行编译、Ruff、覆盖率测试和依赖审计。
- `Windows Package`：PR 和 `master` 推送时构建、诊断并上传 EXE 与 SHA-256。
- `Release Windows Application`：推送与 `screentl/version.py` 一致的标签时创建 GitHub Release。

版本不一致、测试失败、诊断失败或缺少构建产物时，Release 不会创建。

## 隐私原则

- 默认完全离线。
- 不默认采集窗口标题、应用名或 OCR 文本。
- 不默认启用 OCR。
- 不包含自动云端上传。
- 不提供隐蔽采集模式。
- 用户可以随时通过 `Ctrl+Alt+P` 暂停记录。
- 截图可能包含密码、聊天记录和其他敏感内容，请根据实际情况配置排除规则和清理策略。
