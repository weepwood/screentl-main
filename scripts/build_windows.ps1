param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Assert-LastExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

$Venv = Join-Path $Root ".build-venv"
$Python = Join-Path $Venv "Scripts/python.exe"

if (Test-Path $Venv) {
    Remove-Item -Recurse -Force $Venv
}

& py -3.13 -m venv $Venv
if ($LASTEXITCODE -ne 0) {
    & py -3 -m venv $Venv
    Assert-LastExitCode "Create build virtual environment"
}

& $Python -m pip install --disable-pip-version-check pip==26.1.2
Assert-LastExitCode "Install pinned pip"
& $Python -m pip install --disable-pip-version-check -r requirements-build.lock
Assert-LastExitCode "Install locked build dependencies"

if (-not $SkipTests) {
    & $Python -m pip install --disable-pip-version-check -r requirements-ci.lock
    Assert-LastExitCode "Install locked CI dependencies"
    & $Python -m ruff check app.py journal.py makevideo.py screenshot.py screentl scripts tests
    Assert-LastExitCode "Ruff review"
    & $Python -m pytest --cov=screentl --cov-report=term-missing
    Assert-LastExitCode "Test suite"
}

& $Python -m scripts.prepare_build_assets
Assert-LastExitCode "Generate build assets"
& $Python -m PyInstaller --noconfirm --clean ScreenshotTimeLapse.spec
Assert-LastExitCode "PyInstaller build"

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
