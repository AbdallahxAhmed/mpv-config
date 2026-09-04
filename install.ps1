# ───────────────────────────────────────────────────────────────────
#  MPV Auto-Deploy — Windows One-Liner Installer (PowerShell)
#
#  Usage (Recommended):
#    1. Open Windows Terminal as Administrator (Right-click → Run as Administrator)
#    2. Run: irm https://raw.githubusercontent.com/AbdallahxAhmed/mpv-config/main/install.ps1 | iex
#
#  Alternative (Auto-elevation):
#    Run from a non-admin shell and it will request elevation automatically:
#    irm https://raw.githubusercontent.com/AbdallahxAhmed/mpv-config/main/install.ps1 | iex
#    (Note: Opens in ConHost, not Windows Terminal, due to elevation limitations)
#
#  Environment variables (optional):
#    MPV_NO_PAUSE=1            — skip the "Press Enter to close" prompt
#    MPV_FFSUBSYNC_BUILD=1     — allow ffsubsync source builds
#    MPV_BOOTSTRAPPED=1        — internal flag, set by self-elevation
# ───────────────────────────────────────────────────────────────────

[CmdletBinding()]
param(
    [switch]$SyncDeps
)

# IMPORTANT: We deliberately do NOT use `$ErrorActionPreference = "Stop"` at
# script scope. When this script is piped via `irm | iex`, any cmdlet that
# writes to stderr (git, pip, winget) can terminate the entire pipeline and
# the window closes before the user sees what happened. We scope "Stop" only
# around the operations that genuinely need it (clone, download, extract).
$ErrorActionPreference = "Continue"

$REPO        = "AbdallahxAhmed/mpv-config"
$BRANCH      = "main"
$INSTALL_DIR = "$env:USERPROFILE\.mpv-deploy"
$SCRIPT_URL  = "https://raw.githubusercontent.com/$REPO/$BRANCH/install.ps1"

# ─── Self-elevation block ────────────────────────────────────────────
#
# Design decisions (read carefully before changing):
#
# 1. We do NOT use `wt.exe` (Windows Terminal). Going through wt introduces
#    a second middleman process whose argv parsing of nested quotes is
#    fragile and produces the "3 windows" phenomenon reported by users.
#    Launching the shell exe directly with `-Verb RunAs` opens exactly ONE
#    new ConHost window with the correct PowerShell logo (matches the host).
#
# 2. We launch the SAME host the user is currently running. If the user
#    typed the one-liner in PowerShell 7 (pwsh.exe), the elevated window is
#    also pwsh.exe — same edition, same logo, same intrinsics available for
#    AVX2 detection. We discover this via `(Get-Process -Id $PID).Path`,
#    which is the canonical Windows way (no fragile `Get-Command` guess).
#
# 3. We do NOT pass the script body through `-Command "irm ... | iex"`.
#    Nested quoting in argv strings is the #1 source of PowerShell installer
#    bugs. Instead, we download the script ONCE to a temp .ps1 file and pass
#    it to the elevated child via `-File`. Side effect: nested quotes are
#    completely eliminated, errors show real file/line numbers, and the
#    final `Read-Host` actually waits for input (which it does NOT when
#    invoked inside a `-Command` string under certain hosts).
#
# 4. MPV_BOOTSTRAPPED guards against accidental re-entry if a malformed
#    temp file ever calls the URL again from inside the elevated shell.

$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    if ($env:MPV_BOOTSTRAPPED -eq "1") {
        Write-Host "ERROR: Elevation appears to have failed (still not admin)." -ForegroundColor Red
        Read-Host "Press Enter to close"
        exit 1
    }

    Write-Host ""
    Write-Host "╔════════════════════════════════════════════════════════════════╗" -ForegroundColor Yellow
    Write-Host "║  Administrator privileges required                             ║" -ForegroundColor Yellow
    Write-Host "╠════════════════════════════════════════════════════════════════╣" -ForegroundColor Yellow
    Write-Host "║  Recommended: Open Windows Terminal as Admin and run again     ║" -ForegroundColor Cyan
    Write-Host "║  Alternative: Continue with auto-elevation (opens ConHost)     ║" -ForegroundColor Gray
    Write-Host "╚════════════════════════════════════════════════════════════════╝" -ForegroundColor Yellow
    Write-Host ""

    $choice = Read-Host "Continue with auto-elevation? (Y/n)"
    if ($choice -eq "n" -or $choice -eq "N") {
        Write-Host "Cancelled. Please run from an elevated Windows Terminal." -ForegroundColor Yellow
        exit 0
    }

    # Discover the exact shell executable the user is running. This is what
    # makes pwsh stay pwsh and powershell stay powershell — without hardcoding.
    $hostExe = $null
    try {
        $hostExe = (Get-Process -Id $PID -ErrorAction Stop).Path
    } catch { }
    if (-not $hostExe -or -not (Test-Path $hostExe)) {
        # Last-resort fallback: prefer pwsh if installed, else Windows PowerShell.
        $hostExe = (Get-Command pwsh.exe -ErrorAction SilentlyContinue).Source
        if (-not $hostExe) {
            $hostExe = (Get-Command powershell.exe -ErrorAction SilentlyContinue).Source
        }
    }
    if (-not $hostExe) {
        Write-Host "ERROR: Could not locate a PowerShell executable to relaunch." -ForegroundColor Red
        exit 1
    }

    $hostName = [IO.Path]::GetFileNameWithoutExtension($hostExe)
    Write-Host ""
    Write-Host "Requesting Administrator privileges via $hostName..." -ForegroundColor Yellow
    Write-Host "(A UAC prompt will appear. This window will close once accepted.)" -ForegroundColor DarkGray

    # Download the script to a temp file. Using `-UseBasicParsing` keeps this
    # working on systems where IE engine init is broken (common on Server SKUs).
    $tempScript = Join-Path $env:TEMP ("mpv-bootstrap-{0}.ps1" -f $PID)
    try {
        $ErrorActionPreference = "Stop"
        Invoke-WebRequest -Uri $SCRIPT_URL -OutFile $tempScript -UseBasicParsing
        $ErrorActionPreference = "Continue"
    } catch {
        Write-Host "ERROR: Failed to download bootstrap script: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }

    # Launch elevated shell directly (most reliable method).
    # Try with -Environment first (pwsh 7.3+), fall back without it (PS 5.1).
    # Try with -Environment first (pwsh 7.3+), fall back without it (PS 5.1).
    $elevatedArgs = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $tempScript
    )
    if ($SyncDeps) { $elevatedArgs += "-SyncDeps" }

    try {
        Start-Process -FilePath $hostExe -Verb RunAs -ArgumentList $elevatedArgs -Environment @{ "MPV_BOOTSTRAPPED" = "1" } -ErrorAction Stop
    } catch {
        # PS 5.1's Start-Process doesn't support -Environment.
        try {
            Start-Process -FilePath $hostExe -Verb RunAs -ArgumentList $elevatedArgs -ErrorAction Stop
        } catch {
            Write-Host "ERROR: UAC was cancelled or elevation failed." -ForegroundColor Red
            Remove-Item -Force $tempScript -ErrorAction SilentlyContinue
            exit 1
        }
    }

    # Close the original (non-admin) window. The elevated child is independent.
    exit 0
}

# ─── Main install flow (runs as Administrator) ──────────────────────

# Set a clear console title for the elevated window.
try { $Host.UI.RawUI.WindowTitle = "MPV Auto-Deploy (Administrator)" } catch { }

Write-Host ""
Write-Host "+=============================================+" -ForegroundColor Cyan
Write-Host "|       MPV Auto-Deploy - Bootstrap            |" -ForegroundColor Cyan
Write-Host "+=============================================+" -ForegroundColor Cyan
Write-Host ""

# Show which PowerShell edition we're on — useful for debugging AVX2 issues.
$psEditionInfo = if ($PSVersionTable.PSEdition) { $PSVersionTable.PSEdition } else { "Desktop" }
Write-Host "  PowerShell: $($PSVersionTable.PSVersion) ($psEditionInfo)" -ForegroundColor DarkGray
Write-Host ""

# ─── Automated Dependency Suite Pipeline ──────────────────────────────
function Sync-MpvDependencies {
    [CmdletBinding()]
    param(
        [string]$TargetDir = "",
        [switch]$Force
    )

    Write-Host ""
    Write-Host "+================================================================+" -ForegroundColor Cyan
    Write-Host "|       Automated Dependency Suite Pipeline (Sync-Deps)          |" -ForegroundColor Cyan
    Write-Host "+================================================================+" -ForegroundColor Cyan
    Write-Host ""

    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $TargetDir) {
        if ($isAdmin) {
            $TargetDir = "$env:ProgramFiles\mpv"
        } else {
            $TargetDir = "$env:APPDATA\mpv\tools"
        }
    }

    if (-not (Test-Path $TargetDir)) {
        New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
    }

    if ($TargetDir -like "*tools*") {
        $userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
        if ($userPath -notlike "*$TargetDir*") {
            [Environment]::SetEnvironmentVariable("PATH", "$userPath;$TargetDir", "User")
            $env:PATH = "$env:PATH;$TargetDir"
            Write-Host "  + Added $TargetDir to User PATH" -ForegroundColor Green
        }
    }

    # 1. yt-dlp (64-bit Windows binary)
    Write-Host "  > Provisioning yt-dlp (64-bit)..." -ForegroundColor Gray
    $ytdlpDestDir = if ($isAdmin) { Join-Path $TargetDir "yt-dlp" } else { $TargetDir }
    if (-not (Test-Path $ytdlpDestDir)) { New-Item -ItemType Directory -Path $ytdlpDestDir -Force | Out-Null }
    $ytdlpExe = Join-Path $ytdlpDestDir "yt-dlp.exe"
    try {
        Invoke-WebRequest -Uri "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" -OutFile $ytdlpExe -UseBasicParsing
        Unblock-File -LiteralPath $ytdlpExe -ErrorAction SilentlyContinue
        Write-Host "  + yt-dlp verified: $ytdlpExe" -ForegroundColor Green
    } catch {
        Write-Host "  ! yt-dlp download notice: $($_.Exception.Message)" -ForegroundColor Yellow
    }

    # 2. ffmpeg-full (ffmpeg, ffprobe, ffplay from BtbN/Gyan release)
    Write-Host "  > Provisioning ffmpeg-full suite..." -ForegroundColor Gray
    $ffmpegDestDir = if ($isAdmin) { Join-Path $TargetDir "ffmpeg\bin" } else { $TargetDir }
    if (-not (Test-Path $ffmpegDestDir)) { New-Item -ItemType Directory -Path $ffmpegDestDir -Force | Out-Null }
    try {
        $zipUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
        $tempZip = Join-Path $env:TEMP "ffmpeg-release.zip"
        Invoke-WebRequest -Uri $zipUrl -OutFile $tempZip -UseBasicParsing
        $tempExtract = Join-Path $env:TEMP "ffmpeg-extract"
        if (Test-Path $tempExtract) { Remove-Item -Recurse -Force $tempExtract }
        Expand-Archive -LiteralPath $tempZip -DestinationPath $tempExtract -Force
        $bins = Get-ChildItem -Path $tempExtract -Recurse -Filter "*.exe" | Where-Object { $_.Name -in @("ffmpeg.exe", "ffprobe.exe", "ffplay.exe") }
        foreach ($b in $bins) {
            $destFile = Join-Path $ffmpegDestDir $b.Name
            Copy-Item -LiteralPath $b.FullName -Destination $destFile -Force
            Unblock-File -LiteralPath $destFile -ErrorAction SilentlyContinue
        }
        Remove-Item -Force $tempZip -ErrorAction SilentlyContinue
        Remove-Item -Recurse -Force $tempExtract -ErrorAction SilentlyContinue
        Write-Host "  + ffmpeg-full (ffmpeg, ffprobe, ffplay) verified in: $ffmpegDestDir" -ForegroundColor Green
    } catch {
        Write-Host "  ! ffmpeg-full fetch notice: $($_.Exception.Message)" -ForegroundColor Yellow
    }

    # 3. alass (subtitle auto-synchronization from kaegi/alass)
    Write-Host "  > Provisioning alass (subtitle auto-sync)..." -ForegroundColor Gray
    $alassDestDir = if ($isAdmin) { Join-Path $TargetDir "alass" } else { $TargetDir }
    if (-not (Test-Path $alassDestDir)) { New-Item -ItemType Directory -Path $alassDestDir -Force | Out-Null }
    try {
        $alassRelease = Invoke-RestMethod -Uri "https://api.github.com/repos/kaegi/alass/releases/latest" -Headers @{ "User-Agent" = "mpv-config" }
        $asset = $alassRelease.assets | Where-Object { $_.name -match "windows.*x64|win64|win" } | Select-Object -First 1
        if ($asset) {
            $tempAlassZip = Join-Path $env:TEMP $asset.name
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $tempAlassZip -UseBasicParsing
            $tempAlassExtract = Join-Path $env:TEMP "alass-extract"
            if (Test-Path $tempAlassExtract) { Remove-Item -Recurse -Force $tempAlassExtract }
            Expand-Archive -LiteralPath $tempAlassZip -DestinationPath $tempAlassExtract -Force
            $alassBins = Get-ChildItem -Path $tempAlassExtract -Recurse -Filter "*.exe"
            foreach ($ab in $alassBins) {
                $destFile = Join-Path $alassDestDir $ab.Name
                Copy-Item -LiteralPath $ab.FullName -Destination $destFile -Force
                Unblock-File -LiteralPath $destFile -ErrorAction SilentlyContinue
            }
            Remove-Item -Force $tempAlassZip -ErrorAction SilentlyContinue
            Remove-Item -Recurse -Force $tempAlassExtract -ErrorAction SilentlyContinue
            Write-Host "  + alass verified in: $alassDestDir" -ForegroundColor Green
        }
    } catch {
        Write-Host "  ! alass fetch notice: $($_.Exception.Message)" -ForegroundColor Yellow
    }

    # 4. ffsubsync (Python/pip/uv)
    Write-Host "  > Provisioning ffsubsync..." -ForegroundColor Gray
    try {
        if (Get-Command uv.exe -ErrorAction SilentlyContinue) {
            & uv tool install --upgrade ffsubsync 2>$null
        } elseif (Get-Command python.exe -ErrorAction SilentlyContinue) {
            & python -m pip install --upgrade ffsubsync 2>$null
        } elseif (Get-Command pip.exe -ErrorAction SilentlyContinue) {
            & pip install --upgrade ffsubsync 2>$null
        }
        Write-Host "  + ffsubsync verified" -ForegroundColor Green
    } catch {
        Write-Host "  ! ffsubsync notice: $($_.Exception.Message)" -ForegroundColor Yellow
    }

    # 5. Local deployment artifact: update ytdl_hook.conf
    try {
        $optsDir = "$env:APPDATA\mpv\script-opts"
        if (-not (Test-Path $optsDir)) { New-Item -ItemType Directory -Path $optsDir -Force | Out-Null }
        $resolvedYtdl = if (Test-Path $ytdlpExe) { $ytdlpExe.Replace('\', '/') } else { "yt-dlp" }
        $hookConf = Join-Path $optsDir "ytdl_hook.conf"
        "ytdl_path=$resolvedYtdl" | Out-File -FilePath $hookConf -Encoding utf8 -Force
        Write-Host "  + Localized deployment artifact updated: $hookConf (ytdl_path=$resolvedYtdl)" -ForegroundColor Green
    } catch {
        Write-Host "  ! ytdl_hook.conf notice: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

if ($SyncDeps) {
    Sync-MpvDependencies
    if (-not $env:MPV_NO_PAUSE) {
        Write-Host ""
        Read-Host "Press Enter to close this window"
    }
    exit 0
}

# ─── Step 1: Check prerequisites ─────────────────────────────────────
Write-Host "[1/4] Checking prerequisites..." -ForegroundColor White

$python = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $python = "python"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $python = "python3"
} else {
    Write-Host "  ERROR: Python 3 is required but not found." -ForegroundColor Red
    Write-Host "  Install with:  winget install Python.Python.3.11" -ForegroundColor Yellow
    if (-not $env:MPV_NO_PAUSE) { Read-Host "Press Enter to close" }
    exit 1
}
$pyVer = & $python --version 2>&1
Write-Host "  + $pyVer" -ForegroundColor Green

$useGit = $false
if (Get-Command git -ErrorAction SilentlyContinue) {
    $useGit = $true
    Write-Host "  + git found" -ForegroundColor Green
} else {
    Write-Host "  i git not found, will download zip" -ForegroundColor Yellow
}

# ─── Step 2: Download the repo ────────────────────────────────────────
Write-Host ""
Write-Host "[2/4] Downloading mpv-config..." -ForegroundColor White

if (Test-Path $INSTALL_DIR) {
    Write-Host "  > Removing old install dir..." -ForegroundColor Gray
    Remove-Item -Recurse -Force $INSTALL_DIR
}

if ($useGit) {
    # Git writes its normal progress to stderr. We scope Stop locally so a
    # stray progress line doesn't kill the script — we check $LASTEXITCODE
    # ourselves, which is the real signal.
    $prevPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        git clone --depth=1 "https://github.com/$REPO.git" $INSTALL_DIR 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  ERROR: git clone failed (exit $LASTEXITCODE)" -ForegroundColor Red
            if (-not $env:MPV_NO_PAUSE) { Read-Host "Press Enter to close" }
            exit 1
        }
        Write-Host "  + Cloned successfully" -ForegroundColor Green
    } finally {
        $ErrorActionPreference = $prevPref
    }
} else {
    $zipUrl      = "https://github.com/$REPO/archive/refs/heads/$BRANCH.zip"
    $zipPath     = "$env:TEMP\mpv-config.zip"
    $extractPath = "$env:TEMP\mpv-config-extract"

    Write-Host "  > Downloading..." -ForegroundColor Gray
    try {
        $ErrorActionPreference = "Stop"
        Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing
        $ErrorActionPreference = "Continue"
    } catch {
        Write-Host "  ERROR: download failed: $($_.Exception.Message)" -ForegroundColor Red
        if (-not $env:MPV_NO_PAUSE) { Read-Host "Press Enter to close" }
        exit 1
    }

    Write-Host "  > Extracting..." -ForegroundColor Gray
    if (Test-Path $extractPath) { Remove-Item -Recurse -Force $extractPath }
    Expand-Archive -Path $zipPath -DestinationPath $extractPath

    $inner = Get-ChildItem $extractPath | Select-Object -First 1
    Move-Item $inner.FullName $INSTALL_DIR

    Remove-Item -Force $zipPath
    Remove-Item -Recurse -Force $extractPath
    Write-Host "  + Downloaded and extracted" -ForegroundColor Green
}

# ─── Step 3: Ensure pip/setuptools ────────────────────────────────────
Write-Host ""
Write-Host "[3/4] Ensuring build dependencies..." -ForegroundColor White

if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host "  + uv found" -ForegroundColor Green
} else {
    Write-Host "  i uv not found; setup.py will install it into the mpv folder." -ForegroundColor Yellow
}

Write-Host "  > Upgrading pip and pinning setuptools..." -ForegroundColor Gray
& $python -m pip install --quiet --upgrade "pip>=23.0" "setuptools<74.0" wheel 2>$null

Write-Host "  > Installing CLI UI dependencies (rich)..." -ForegroundColor Gray
& $python -m pip install --quiet "rich>=13.0.0" 2>$null

$forceBuild = $env:MPV_FFSUBSYNC_BUILD -eq "1"
if ($forceBuild) {
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
} else {
    Write-Host "  + ffsubsync will use uv with Python 3.11 (prebuilt wheels; no build tools needed)" -ForegroundColor Green
    Write-Host "    Set MPV_FFSUBSYNC_BUILD=1 to allow source builds if needed." -ForegroundColor Gray
}

# ─── Step 4: Run the deployer ─────────────────────────────────────────
Write-Host ""
Write-Host "[4/4] Running MPV Auto-Deploy..." -ForegroundColor White
Write-Host ""

Set-Location $INSTALL_DIR
& $python setup.py
$deployExit = $LASTEXITCODE

# ─── Ensure Shortcuts enforce User WorkingDirectory ─────────────────
try {
    $mpvExe = "$env:ProgramFiles\mpv\mpv.exe"
    if (-not (Test-Path $mpvExe)) {
        $foundMpv = Get-Command mpv.exe -ErrorAction SilentlyContinue
        if ($foundMpv) { $mpvExe = $foundMpv.Source }
    }
    if (Test-Path $mpvExe) {
        $wsh = New-Object -ComObject WScript.Shell
        $shortcutTargets = @(
            @{ Path = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\mpv.lnk"; Always = $true },
            @{ Path = "$env:USERPROFILE\Desktop\mpv.lnk"; Always = $false }
        )
        foreach ($t in $shortcutTargets) {
            $p = $t.Path
            if ((Test-Path $p) -or $t.Always) {
                $pDir = Split-Path -Parent $p
                if (-not (Test-Path $pDir)) { New-Item -ItemType Directory -Path $pDir -Force | Out-Null }
                $sc = $wsh.CreateShortcut($p)
                $sc.TargetPath = $mpvExe
                $sc.WorkingDirectory = "$env:USERPROFILE"
                $sc.IconLocation = "$mpvExe,0"
                $sc.Save()
                Write-Host "  + Shortcut verified: $p (WorkingDirectory: $env:USERPROFILE)" -ForegroundColor Green
            }
        }
    }
} catch {
    Write-Host "  ! Shortcut configuration notice: $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "---------------------------------------------" -ForegroundColor Gray
Write-Host "  Install dir: $INSTALL_DIR" -ForegroundColor Gray
Write-Host "  Re-run:  cd $INSTALL_DIR; python setup.py" -ForegroundColor Gray
Write-Host "  Update:  cd $INSTALL_DIR; python setup.py --update" -ForegroundColor Gray
Write-Host "---------------------------------------------" -ForegroundColor Gray

# Self-cleanup: if we were launched from a temp bootstrap file, remove it.
if ($PSCommandPath -and $PSCommandPath -like "$env:TEMP\mpv-bootstrap-*.ps1") {
    # Schedule removal after exit so we don't try to delete the file we're
    # currently executing. Done via cmd /c to fully detach.
    Start-Process cmd.exe -ArgumentList "/c","timeout","/t","2","/nobreak",">nul","&","del","/q",("`"{0}`"" -f $PSCommandPath) -WindowStyle Hidden
}

# Keep window open so the user can read the output. Skippable for CI.
if (-not $env:MPV_NO_PAUSE) {
    Write-Host ""
    Read-Host "Press Enter to close this window"
}

exit $deployExit
