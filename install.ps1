[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/AbdallahxAhmed/mpv-config.git"
$TargetDir = Join-Path $HOME ".mpv-config-deploy"

if ((Test-Path "pyproject.toml") -and (Test-Path "src/mpv_config")) {
    $TargetDir = (Get-Location).Path
} elseif (Test-Path (Join-Path $TargetDir ".git")) {
    Write-Host "Updating existing repository at $TargetDir..."
    git -C $TargetDir pull --ff-only --quiet
} else {
    Write-Host "Cloning repository to $TargetDir..."
    git clone --quiet $RepoUrl $TargetDir
}

Set-Location $TargetDir

Write-Host "Bootstrapping mpv-config..."
python -m pip install --user --editable . --no-warn-script-location
$UserScripts = python -c "import site, os; print(os.path.join(site.USER_BASE, 'Scripts'))" 2>$null
if ($UserScripts -and -not ($env:PATH -split ';' -contains $UserScripts)) {
    Write-Host "note: $UserScripts is not on your PATH; add it to run 'mpv-config' directly."
}
python -m mpv_config install @args
