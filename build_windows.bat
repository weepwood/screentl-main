@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_windows.ps1"
if errorlevel 1 (
  echo.
  echo Build failed.
  pause
  exit /b 1
)
echo.
echo Build complete: dist\ScreenshotTimeLapse.exe
echo Checksum: dist\ScreenshotTimeLapse.exe.sha256
pause
