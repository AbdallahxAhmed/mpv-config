[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/AbdallahxAhmed/mpv-config.git"
$TargetDir = Join-Path $HOME ".mpv-config-deploy"

if ((Test-Path "pyproject.toml") -and (Test-Path "src/mpv_config")) {
    # Running from inside a checkout (e.g. the deploy clone itself): the
    # editable install below would otherwise silently reinstall whatever
    # stale code is checked out — an earlier run demonstrated this by
    # "freezing" in the downloader that had already been fixed on main.
    # Fast-forward first; a dirty/diverged checkout fails ff-only without
    # losing anything and gets installed as-is.
    $TargetDir = (Get-Location).Path
    Write-Host "Updating checkout at $TargetDir..."
    git pull --ff-only --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Could not fast-forward this checkout (local changes?); installing it as-is."
    }
} elseif (Test-Path (Join-Path $TargetDir ".git")) {
    Write-Host "Updating existing repository at $TargetDir..."
    git -C $TargetDir pull --ff-only --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Could not fast-forward $TargetDir (local changes?); reinstalling it as-is."
    }
} else {
    Write-Host "Cloning repository to $TargetDir..."
    git clone --quiet $RepoUrl $TargetDir
}

Set-Location $TargetDir

Write-Host "Bootstrapping mpv-config (quiet; details are shown only on failure)..."
# --quiet keeps the ~25 'Requirement already satisfied' / uninstall lines out
# of the console; on failure the captured output is reprinted for diagnosis.
$pipOutput = python -m pip install --user --quiet --editable . --no-warn-script-location --disable-pip-version-check 2>&1
if ($LASTEXITCODE -ne 0) {
    $pipOutput | Write-Host
    throw "pip install failed with exit code $LASTEXITCODE"
}

$UserScripts = python -c "import site, os; print(os.path.join(site.USER_BASE, 'Scripts'))" 2>$null
if ($UserScripts -and -not ($env:PATH -split ';' -contains $UserScripts)) {
    Write-Host "note: $UserScripts is not on your PATH; add it to run 'mpv-config' directly."
}
python -m mpv_config install @args
