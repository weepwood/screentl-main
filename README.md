# Screenshot Time-lapse

本地定时截屏并生成延时视频，用于回顾一天的工作过程。截图和视频默认只保存在本机，不会自动上传。

## 安装

项目支持 Python 3.10～3.13。运行依赖由 `requirements.lock` 锁定：

```bash
python -m pip install -r requirements.txt
```

MoviePy 会调用随 `imageio-ffmpeg` 安装的 FFmpeg。标题文字使用 MoviePy 1.x `TextClip`，部分环境可能还需要 ImageMagick；不可用时会自动跳过标题，不影响视频生成。

## 图形界面

```bash
python app.py
```

界面支持：

- 设置截图目录、间隔、音乐目录、视频帧率和标题。
- 开始、暂停、继续和停止截图。
- 查看视频生成进度并主动取消。
- 关闭时等待视频完成、取消任务退出或返回程序。
- 托盘驻留和当前用户开机启动。

截图和渲染由独立服务执行，后台线程只发布事件，所有 Tkinter 操作均由主线程处理。视频先写入隐藏临时文件，完整生成后才原子替换正式文件；失败或取消不会破坏已有视频。

Windows 桌面入口使用单实例锁。重复启动程序时不会创建第二个截图进程，而会尝试恢复并激活已经运行的窗口。

默认截图目录位于用户图片目录下的 `ScreenshotTimeLapse/<日期>`。旧版本保存的相对目录会自动迁移到该目录。设置窗口使用独立草稿，点击取消不会修改当前配置。

## 命令行

### 截屏

```bash
python screenshot.py --folder "D:\\Pictures\\ScreenshotTimeLapse\\2026-08-02" --interval 30
```

按 `Ctrl+C` 停止。图片命名为 `screenshot_<编号>_<时间>.png`。计数器缺失或损坏时，会根据已有截图恢复下一个编号。

不要同时运行多个 `screenshot.py` 进程并写入同一个目录。桌面 GUI 已通过单实例锁避免这种情况，独立命令行进程之间目前不提供跨进程目录锁。

### 生成视频

```bash
python makevideo.py \
  --folder "D:\\Pictures\\ScreenshotTimeLapse\\2026-08-02" \
  --fps 25 \
  --audio "D:\\Music" \
  --text "2026-08-02" \
  --output video.mp4
```

程序读取 `screenshot_*.png`，按编号、时间戳和文件名稳定排序。没有可用音乐时会生成静音视频。

## 测试和检查

测试、静态检查和覆盖率配置统一保存在 `pyproject.toml`。CI 依赖由 `requirements-ci.lock` 锁定：

```bash
python -m pip install -r requirements-ci.txt
python -m ruff check app.py makevideo.py screenshot.py screentl scripts tests
python -m pytest --cov=screentl --cov-report=term-missing
python -m pip_audit -r requirements.lock
```

覆盖率门槛针对非 GUI 核心层，GUI、Windows 平台适配和桌面协调器不计入核心覆盖率。

## Windows 构建

双击 `build_windows.bat`，或执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

构建过程会：

1. 创建全新的 `.build-venv` 隔离环境。
2. 安装锁定的运行、构建和测试依赖。
3. 执行 Ruff、pytest 和覆盖率检查。
4. 生成确定性的应用图标和 Windows 版本资源。
5. 使用受版本控制的 `ScreenshotTimeLapse.spec` 构建单文件 EXE。
6. 执行 `ScreenshotTimeLapse.exe --diagnose` 冒烟测试。
7. 生成 `dist/ScreenshotTimeLapse.exe.sha256`。

输出文件：

```text
dist/
├── ScreenshotTimeLapse.exe
└── ScreenshotTimeLapse.exe.sha256
```

## 自动化发布

仓库包含三条 GitHub Actions：

- `Quality Review`：PR 和 `master` 推送时执行编译、Ruff、覆盖率测试和依赖漏洞审计。
- `Windows Package`：`master` 推送时在干净环境构建并诊断 EXE，上传 EXE 和 SHA-256。
- `Release Windows Application`：推送与应用版本一致的标签时创建 GitHub Release。

当前应用版本定义在 `screentl/version.py`。发布标签必须与其一致，例如版本为 `0.2.0` 时：

```bash
git tag v0.2.0
git push origin v0.2.0
```

版本不一致、测试失败、诊断失败或缺少构建产物时，Release 不会创建。

## 配置和隐私

配置文件保存在：

```text
%APPDATA%\ScreenshotTimeLapse\config.json
```

截图可能包含密码、聊天记录或其他敏感信息，请妥善保护输出目录。项目不会自动上传截图、视频或配置。
