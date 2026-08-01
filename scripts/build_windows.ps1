param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Venv = Join-Path $Root ".build-venv"
$Python = Join-Path $Venv "Scripts/python.exe"

if (Test-Path $Venv) {
    Remove-Item -Recurse -Force $Venv
}

try {
    py -3.13 -m venv $Venv
} catch {
    py -3 -m venv $Venv
}

& $Python -m pip install --disable-pip-version-check pip==26.1.2
& $Python -m pip install --disable-pip-version-check -r requirements-build.lock

if (-not $SkipTests) {
    & $Python -m pip install --disable-pip-version-check -r requirements-ci.lock
    & $Python -m ruff check app.py makevideo.py screenshot.py screentl scripts tests
    & $Python -m pytest --cov=screentl --cov-report=term-missing
}

& $Python scripts/prepare_build_assets.py
& $Python -m PyInstaller --noconfirm --clean ScreenshotTimeLapse.spec

$Exe = Join-Path $Root "dist/ScreenshotTimeLapse.exe"
if (!(Test-Path $Exe)) {
    throw "Package not found: $Exe"
}
if ((Get-Item $Exe).Length -lt 1MB) {
    throw "Package is unexpectedly small: $((Get-Item $Exe).Length) bytes"
}

$Process = Start-Process -FilePath $Exe -ArgumentList "--diagnose" -PassThru -Wait
if ($Process.ExitCode -ne 0) {
    throw "Packaged diagnostic failed with exit code $($Process.ExitCode)"
}

$Hash = (Get-FileHash -Algorithm SHA256 $Exe).Hash.ToLowerInvariant()
$Checksum = Join-Path $Root "dist/ScreenshotTimeLapse.exe.sha256"
"$Hash  ScreenshotTimeLapse.exe" | Set-Content -Encoding ascii $Checksum

Write-Host "Built $Exe"
Write-Host "SHA-256: $Hash"
