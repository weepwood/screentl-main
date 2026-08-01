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

界面支持选择截图目录和音乐目录、设置截屏间隔与视频帧率、填写标题，并分别控制截屏和视频生成。截屏与视频生成在后台线程执行，窗口不会因处理过程卡住。截屏过程中可以暂停/继续，配置会自动保存到用户配置目录。

### 打包为单体 EXE

在 Windows 上双击 `build_windows.bat`，或执行：

```bash
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed --name ScreenshotTimeLapse app.py
```

生成的 `dist/ScreenshotTimeLapse.exe` 可以直接双击运行，不需要打开命令行。首次运行后，右下角通知区域会出现托盘图标；关闭窗口默认只隐藏到托盘，右键托盘图标可以重新打开、开始/停止截屏、进入设置或退出程序。

设置中的“随 Windows 开机启动”使用当前用户的启动项，不需要管理员权限。截图配置保存在 `%APPDATA%\\ScreenshotTimeLapse\\config.json`。

### 截屏

```bash
python screenshot.py --folder "D:\\Root\\Pictures\\Day\\2023-02-24" --interval 30
```

`--folder` 默认为当天日期目录，`--interval` 单位为秒，默认 30 秒。程序启动后会立即截取第一张图片，之后按间隔继续截屏。

按 `Ctrl+C` 停止截屏。图片命名为 `screenshot_<编号>_<时间>.png`，编号会保存在 `num.json` 中，程序重启后可继续编号。

### 生成视频

```bash
python makevideo.py --folder "D:\\Root\\Pictures\\Day\\2023-02-24" --fps 25 --audio audio
```

参数：

- `--folder`：截图目录，默认当天日期。
- `--fps`：每秒帧数，默认 25。
- `--audio`：音乐目录，默认 `audio`。
- `--text`：视频开头显示的标题，默认当天日期；传入空字符串可关闭标题。

程序会自动读取 `screenshot_*.png`，按编号排序。删除不需要的图片后再生成视频即可。

如果没有足够长的音频文件，程序会生成无背景音乐的视频并打印警告。

### Windows 隐藏启动

可以运行 `weepwood_script.vbs`，它会使用同目录下的 `screenshot_weepwood.bat` 在隐藏窗口中启动截屏程序。也可以直接运行 Python 入口脚本。

## 注意事项

截屏可能包含密码、聊天记录或其他敏感信息，请妥善保护输出目录。项目不会上传截图或视频。
