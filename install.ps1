# ─────────────────────────────────────────────────────────────────
#  MPV Auto-Deploy — Windows One-Liner Installer (PowerShell)
#
#  Usage:
#    irm https://raw.githubusercontent.com/AbdallahxAhmed/mpv-config/main/install.ps1 | iex
#
#  Or manually:
#    git clone https://github.com/AbdallahxAhmed/mpv-config.git
#    cd mpv-config
#    python setup.py
# ─────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"
$REPO = "AbdallahxAhmed/mpv-config"
$BRANCH = "main"
$INSTALL_DIR = "$env:USERPROFILE\.mpv-deploy"

Write-Host ""
Write-Host "+=============================================+" -ForegroundColor Cyan
Write-Host "|       MPV Auto-Deploy - Bootstrap            |" -ForegroundColor Cyan
Write-Host "+=============================================+" -ForegroundColor Cyan
Write-Host ""

# ─── Step 1: Check prerequisites ─────────────────────────────────
Write-Host "[1/4] Checking prerequisites..." -ForegroundColor White

# Python
$python = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $python = "python"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $python = "python3"
} else {
    Write-Host "  ERROR: Python 3 is required but not found." -ForegroundColor Red
    Write-Host "  Install with:  winget install Python.Python.3.11" -ForegroundColor Yellow
    exit 1
}

$pyVer = & $python --version 2>&1
Write-Host "  + $pyVer" -ForegroundColor Green

# Git
$useGit = $false
if (Get-Command git -ErrorAction SilentlyContinue) {
    $useGit = $true
    Write-Host "  + git found" -ForegroundColor Green
} else {
    Write-Host "  i git not found, will download zip" -ForegroundColor Yellow
}

# ─── Step 2: Download the repo ────────────────────────────────────
Write-Host ""
Write-Host "[2/4] Downloading mpv-config..." -ForegroundColor White

if (Test-Path $INSTALL_DIR) {
    Write-Host "  > Removing old install dir..." -ForegroundColor Gray
    Remove-Item -Recurse -Force $INSTALL_DIR
}

if ($useGit) {
    git clone --depth=1 "https://github.com/$REPO.git" $INSTALL_DIR 2>$null
    Write-Host "  + Cloned successfully" -ForegroundColor Green
} else {
    $zipUrl = "https://github.com/$REPO/archive/refs/heads/$BRANCH.zip"
    $zipPath = "$env:TEMP\mpv-config.zip"
    $extractPath = "$env:TEMP\mpv-config-extract"

    Write-Host "  > Downloading..." -ForegroundColor Gray
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing

    Write-Host "  > Extracting..." -ForegroundColor Gray
    if (Test-Path $extractPath) { Remove-Item -Recurse -Force $extractPath }
    Expand-Archive -Path $zipPath -DestinationPath $extractPath

    # Move contents (strip top-level dir)
    $inner = Get-ChildItem $extractPath | Select-Object -First 1
    Move-Item $inner.FullName $INSTALL_DIR

    Remove-Item -Force $zipPath
    Remove-Item -Recurse -Force $extractPath
    Write-Host "  + Downloaded and extracted" -ForegroundColor Green
}

# ─── Step 3: Ensure pip/setuptools ────────────────────────────────
Write-Host ""
Write-Host "[3/4] Ensuring build dependencies..." -ForegroundColor White

Write-Host "  > Upgrading pip and pinning setuptools..." -ForegroundColor Gray
& $python -m pip install --quiet --upgrade "pip>=23.0" "setuptools<74.0" wheel 2>$null

# Check for Visual C++ Build Tools (needed for webrtcvad in ffsubsync)
$hasVCTools = $false
$vsWhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (Test-Path $vsWhere) {
    $result = & $vsWhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2>$null
    if ($result) { $hasVCTools = $true }
}

if ($hasVCTools) {
    Write-Host "  + Visual C++ Build Tools found" -ForegroundColor Green
} else {
    Write-Host "  ! Visual C++ Build Tools not detected" -ForegroundColor Yellow
    Write-Host "    ffsubsync may fail to install without them." -ForegroundColor Yellow
    Write-Host "    Get them from: https://visualstudio.microsoft.com/visual-cpp-build-tools/" -ForegroundColor Yellow
}

# ─── Step 4: Run the deployer ─────────────────────────────────────
Write-Host ""
Write-Host "[4/4] Running MPV Auto-Deploy..." -ForegroundColor White
Write-Host ""

Set-Location $INSTALL_DIR
& $python setup.py

Write-Host ""
Write-Host "---------------------------------------------" -ForegroundColor Gray
Write-Host "  Install dir: $INSTALL_DIR" -ForegroundColor Gray
Write-Host "  Re-run:  cd $INSTALL_DIR; python setup.py" -ForegroundColor Gray
Write-Host "  Update:  cd $INSTALL_DIR; python setup.py --update" -ForegroundColor Gray
Write-Host "---------------------------------------------" -ForegroundColor Gray
