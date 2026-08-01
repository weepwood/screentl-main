@echo off
setlocal
cd /d "%~dp0"
py -3 -m pip install -r requirements-build.txt
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed --name ScreenshotTimeLapse ^
  --copy-metadata imageio --copy-metadata moviepy --copy-metadata imageio-ffmpeg app.py
echo.
echo Build complete: dist\ScreenshotTimeLapse.exe
pause
