# Screenshot Time-lapse

定时截屏并生成延时视频，用于回顾一天的工作过程。

## 安装

安装 Python 3.10 或更高版本，然后执行：

```bash
python -m pip install -r requirements.txt
```

视频生成还需要 MoviePy 能调用 FFmpeg；如果要显示标题文字，MoviePy 1.x 的 `TextClip` 可能还需要 ImageMagick。

## 使用

### 图形界面

运行：

```bash
python app.py
```

界面支持选择截图目录和音乐目录、设置截屏间隔与视频帧率、填写标题，并分别控制截屏和视频生成。截图和渲染由独立服务执行，后台线程只发送事件，所有 Tkinter 操作均由主线程处理。

截图过程中可以暂停、继续或停止。视频生成过程中会显示进度，也可以主动取消。关闭程序时会先停止截图并取消或等待视频任务，任务结束后才销毁窗口，避免留下仍在访问 UI 的后台线程。

视频先写入同目录临时文件，完整生成后才替换 `video.mp4`。编码失败或取消时会删除临时文件，并保留已有的正式视频。

Windows 桌面入口使用单实例锁。重复启动程序时不会创建第二个截图进程，而会尝试恢复并激活已经运行的窗口。

默认截图目录位于用户图片目录下的 `ScreenshotTimeLapse/<日期>`。设置窗口使用独立草稿，点击取消不会修改当前配置。

### 打包为单体 EXE

在 Windows 上双击 `build_windows.bat`，或执行：

```bash
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed --name ScreenshotTimeLapse app.py
```

生成的 `dist/ScreenshotTimeLapse.exe` 可以直接双击运行，不需要打开命令行。首次运行后，右下角通知区域会出现托盘图标；关闭窗口默认只隐藏到托盘，右键托盘图标可以重新打开、开始/停止截屏、进入设置或退出程序。

### GitHub Actions 自动审查与发布

仓库包含三条自动化流程：

- `Quality Review`：在 Pull Request、`master` 推送时运行编译检查、Ruff 静态检查、pytest 测试和依赖漏洞审计。
- `Windows Package`：在 `master` 推送时构建 Windows 单文件 EXE，并上传为 Actions Artifact。
- `Release Windows Application`：推送版本标签（例如 `v1.0.0`）时自动构建 EXE 并创建 GitHub Release。

发布新版本：

```bash
git tag v1.0.0
git push origin v1.0.0
```

设置中的“随 Windows 开机启动”使用当前用户的启动项，不需要管理员权限。截图配置保存在 `%APPDATA%\\ScreenshotTimeLapse\\config.json`。

### 截屏

```bash
python screenshot.py --folder "D:\\Root\\Pictures\\Day\\2023-02-24" --interval 30
```

`--folder` 默认为当天日期目录，`--interval` 单位为秒，默认 30 秒。程序启动后会立即截取第一张图片，之后按间隔继续截屏。

按 `Ctrl+C` 停止截屏。图片命名为 `screenshot_<编号>_<时间>.png`，编号会保存在 `num.json` 中，程序重启后可继续编号。计数器缺失或损坏时，程序会根据目录中已有截图恢复下一个编号。

不要同时运行多个 `screenshot.py` 进程并写入同一个目录。桌面 GUI 已通过单实例锁避免这种情况，但独立命令行进程之间目前不提供跨进程目录锁。

### 生成视频

```bash
python makevideo.py --folder "D:\\Root\\Pictures\\Day\\2023-02-24" --fps 25 --audio audio
```

参数：

- `--folder`：截图目录，默认当天日期。
- `--fps`：每秒帧数，默认 25。
- `--audio`：音乐目录，默认 `audio`。
- `--text`：视频开头显示的标题，默认当天日期；传入空字符串可关闭标题。

程序会自动读取 `screenshot_*.png`，按编号、时间戳和文件名稳定排序。删除不需要的图片后再生成视频即可。

如果没有足够长的音频文件，程序会生成无背景音乐的视频并打印警告。

### Windows 隐藏启动

可以运行 `weepwood_script.vbs`，它会使用同目录下的 `screenshot_weepwood.bat` 在隐藏窗口中启动截屏程序。也可以直接运行 Python 入口脚本。

## 注意事项

截屏可能包含密码、聊天记录或其他敏感信息，请妥善保护输出目录。项目不会上传截图或视频。
