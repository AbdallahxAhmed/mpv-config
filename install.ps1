[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/AbdallahxAhmed/mpv-config.git"
$TargetDir = Join-Path $HOME ".mpv-config-deploy"

if ((Test-Path "pyproject.toml") -and (Test-Path "src/mpv_config")) {
    $TargetDir = (Get-Location).Path
} elseif (Test-Path (Join-Path $TargetDir ".git")) {
    Write-Host "Updating existing repository at $TargetDir..."
    git -C $TargetDir pull --quiet
} else {
    Write-Host "Cloning repository to $TargetDir..."
    git clone --quiet $RepoUrl $TargetDir
}

Set-Location $TargetDir

Write-Host "Bootstrapping mpv-config..."
python -m pip install --user .
python -m mpv_config install @args
