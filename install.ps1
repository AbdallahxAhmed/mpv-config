# Bootstrap mpv-config on Windows: fetch the repository, install the CLI into a
# private virtual environment (never into the system Python), then run
# `mpv-config install`. Mirrors install.sh.
#   irm https://raw.githubusercontent.com/AbdallahxAhmed/mpv-config/main/install.ps1 | iex
# Extra arguments reach the deployer when the script is invoked as a script block:
#   & ([scriptblock]::Create((irm .../install.ps1))) --dry-run
# (No [CmdletBinding()]/param() block: advanced scripts reject unbound
# arguments and leave $args empty, which made pass-through impossible.)

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/AbdallahxAhmed/mpv-config.git"
$TargetDir = Join-Path $HOME ".mpv-config-deploy"
$DataRoot = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $HOME "AppData\Local" }
$DataDir = Join-Path $DataRoot "mpv-config"
$VenvDir = Join-Path $DataDir "venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$BinDir = Join-Path $DataDir "bin"
$ForwardedArgs = @($args)

function Invoke-Native {
    # Windows PowerShell 5.1 turns every stderr line of a native command whose
    # stderr is redirected into a terminating NativeCommandError while
    # $ErrorActionPreference is "Stop" (pip/git warnings included). Run native
    # tools with "Continue" and judge them by $LASTEXITCODE instead.
    param([scriptblock]$Command)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Command
    } finally {
        $ErrorActionPreference = $previous
    }
}

function Test-Command([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Update-SessionPath {
    # winget updates the registry PATH; this session still has the old copy.
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = (@($machine, $user) | Where-Object { $_ }) -join ";"
}

function Install-WithWinget([string]$Id, [string]$Label) {
    if (-not (Test-Command "winget")) {
        throw "$Label is required but missing, and winget is unavailable. Install $Label, then re-run."
    }
    Write-Host "$Label not found - installing it with winget ($Id)..."
    Invoke-Native {
        winget install --id $Id --exact --source winget --silent `
            --accept-package-agreements --accept-source-agreements
    }
    if ($LASTEXITCODE -ne 0) {
        throw "winget could not install $Label (exit code $LASTEXITCODE)."
    }
    Update-SessionPath
}

function Get-Python {
    # Returns the command (as an array: exe + leading args) of a Python >= 3.10.
    # A fresh Windows has a Microsoft Store "python" alias that only opens the
    # Store and exits 9009, so every candidate is probed, not just located.
    foreach ($candidate in @(@("py", "-3"), @("python"))) {
        $exe = $candidate[0]
        if (-not (Test-Command $exe)) {
            continue
        }
        $leading = @($candidate | Select-Object -Skip 1)
        $answer = Invoke-Native { & $exe @leading -c "import sys; print(sys.version_info >= (3, 10))" 2>$null }
        if ($LASTEXITCODE -eq 0 -and "$answer".Trim() -eq "True") {
            return , $candidate
        }
    }
    return $null
}

if (-not (Test-Command "git")) {
    Install-WithWinget "Git.Git" "Git"
    if (-not (Test-Command "git")) {
        throw "Git was installed but is not on PATH yet. Open a new terminal and re-run."
    }
}

$Python = Get-Python
if (-not $Python) {
    Install-WithWinget "Python.Python.3.12" "Python 3.12"
    $Python = Get-Python
    if (-not $Python) {
        throw "Python 3.10+ is required. It was installed but is not usable yet: open a new terminal and re-run."
    }
}
$PyExe = $Python[0]
$PyArgs = @($Python | Select-Object -Skip 1)

if ((Test-Path "pyproject.toml") -and (Test-Path "src/mpv_config")) {
    # Running from inside a checkout (e.g. the deploy clone itself): the
    # editable install below would otherwise silently reinstall whatever
    # stale code is checked out — an earlier run demonstrated this by
    # "freezing" in the downloader that had already been fixed on main.
    # Fast-forward first; a dirty/diverged checkout fails ff-only without
    # losing anything and gets installed as-is.
    $TargetDir = (Get-Location).Path
    Write-Host "Updating checkout at $TargetDir..."
    Invoke-Native { git pull --ff-only --quiet }
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Could not fast-forward this checkout (local changes?); installing it as-is."
    }
} elseif (Test-Path (Join-Path $TargetDir ".git")) {
    Write-Host "Updating existing repository at $TargetDir..."
    Invoke-Native { git -C $TargetDir pull --ff-only --quiet }
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Could not fast-forward $TargetDir (local changes?); reinstalling it as-is."
    }
} else {
    Write-Host "Cloning repository to $TargetDir..."
    Invoke-Native { git clone --quiet $RepoUrl $TargetDir }
    if ($LASTEXITCODE -ne 0) {
        throw "git clone failed with exit code $LASTEXITCODE (network or proxy problem?)."
    }
}

Set-Location $TargetDir

Write-Host "Bootstrapping mpv-config (quiet; details are shown only on failure)..."
# The CLI lives in a private virtual environment, like install.sh does on
# Linux/macOS: pip runs only inside it, never against the system Python
# (constitution Principle III).
if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating virtual environment at $VenvDir..."
    if (Test-Path $VenvDir) {
        Remove-Item -Recurse -Force $VenvDir
    }
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    $venvOutput = Invoke-Native { & $PyExe @PyArgs -m venv $VenvDir 2>&1 }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPython)) {
        $venvOutput | Write-Host
        if (Test-Path $VenvDir) {
            Remove-Item -Recurse -Force $VenvDir
        }
        throw "Could not create a virtual environment at $VenvDir (exit code $LASTEXITCODE)."
    }
}

# A venv left without pip (e.g. an interrupted earlier run): seed pip into it
# instead of failing on "No module named pip".
Invoke-Native { & $VenvPython -m pip --version *> $null }
if ($LASTEXITCODE -ne 0) {
    Invoke-Native { & $VenvPython -m ensurepip --upgrade *> $null }
    if ($LASTEXITCODE -ne 0) {
        throw "The virtual environment at $VenvDir has no pip; remove it and re-run."
    }
}

# Editable, so the CLI always finds this checkout: deploy/ and config/ are not
# packaged. --quiet keeps the ~25 'Requirement already satisfied' lines out of
# the console; on failure the captured output is reprinted for diagnosis.
$pipOutput = Invoke-Native {
    & $VenvPython -m pip install --quiet --editable . --disable-pip-version-check 2>&1
}
if ($LASTEXITCODE -ne 0) {
    $pipOutput | Write-Host
    throw "pip install failed with exit code $LASTEXITCODE"
}

# Put `mpv-config` on PATH through a small .cmd shim next to the renderer in
# %LOCALAPPDATA%\mpv-config\bin (install.sh links ~/.local/bin instead). A
# .cmd needs no symlink privilege; it finds the venv relative to itself, so it
# holds no absolute (possibly non-ASCII) path. An unrelated file is left alone.
$Shim = Join-Path $BinDir "mpv-config.cmd"
$ShimMarker = "rem mpv-config venv shim"
$ownShim = (-not (Test-Path $Shim)) -or ((Get-Content -Raw $Shim) -match [regex]::Escape($ShimMarker))
if ($ownShim) {
    New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
    Set-Content -Path $Shim -Encoding ASCII -Value @(
        "@echo off",
        $ShimMarker,
        '"%~dp0..\venv\Scripts\mpv-config.exe" %*'
    )
} else {
    Write-Host "note: $Shim already exists and was not created by mpv-config; left unchanged."
}
if (-not ($env:PATH -split ';' -contains $BinDir)) {
    Write-Host "note: $BinDir is not on your PATH; add it to run 'mpv-config' directly."
}
Invoke-Native { & $VenvPython -m mpv_config install @ForwardedArgs }
# No `exit` here: under `irm | iex` it would close the user's PowerShell window.
if ($LASTEXITCODE -ne 0) {
    Write-Warning "mpv-config install exited with code $LASTEXITCODE."
}
