# create-clean-repo.ps1
# Creates a fresh, clean repository without any history containing secrets

$ErrorActionPreference = "Stop"

Write-Host "=== Creating Clean Repository ===" -ForegroundColor Cyan

# Configuration
$SourceDir = "C:\Users\Abdallah_Ahmed\Desktop\mpv-config"
$CleanDir = "C:\Users\Abdallah_Ahmed\Desktop\mpv-config-clean"
$GitHubRepo = "AbdallahxAhmed/mpv-config"

# Step 1: Create new directory
Write-Host "Step 1: Creating clean directory..." -ForegroundColor Yellow
if (Test-Path $CleanDir) {
    Remove-Item -Recurse -Force $CleanDir
}
New-Item -ItemType Directory -Path $CleanDir | Out-Null

# Step 2: Copy all files except .git and secrets
Write-Host "Step 2: Copying files (excluding .git and secrets)..." -ForegroundColor Yellow
$ExcludeDirs = @('.git', '__pycache__', '.pytest_cache', 'node_modules', '.venv', 'venv')
$ExcludeFiles = @('*.pem', '*.key', '*.crt', '.env', 'secrets.json', 'cookies.txt')

robocopy $SourceDir $CleanDir /E /XD $ExcludeDirs /XF $ExcludeFiles /NFL /NDL /NJH /NJS

# Step 3: Initialize fresh git repo
Write-Host "Step 3: Initializing fresh git repository..." -ForegroundColor Yellow
Set-Location $CleanDir
git init
git branch -M main

# Step 4: Create initial commit
Write-Host "Step 4: Creating initial commit..." -ForegroundColor Yellow
git add .
git commit -m "🎉 Initial clean release v1.0.0

- Modern pyproject.toml (hatchling) and src/ layout
- Unified CLI (mpv-config install/verify/download)
- Plugin-based Downloader Framework
- Purged all adult content and legacy scripts
- Robust CI/CD pipelines and pre-commit hooks
- Security hardened: no secrets, no personal paths"

# Step 5: Verify no secrets remain
Write-Host "Step 5: Running final security check..." -ForegroundColor Yellow
Write-Host "Checking for tracked secrets..." -ForegroundColor Yellow
$trackedSecrets = git ls-files | Where-Object { $_ -match '\.(pem|key|crt)$' }
if ($trackedSecrets) {
    Write-Host "ERROR: Found tracked secrets:" -ForegroundColor Red
    $trackedSecrets
    Write-Host "Please remove them before proceeding!" -ForegroundColor Red
    exit 1
}
else {
    Write-Host "✓ No tracked secrets found" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Clean Repository Created Successfully ===" -ForegroundColor Green
Write-Host "Location: $CleanDir" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Go to GitHub and create a new repository: $GitHubRepo" -ForegroundColor White
Write-Host "2. Run these commands:" -ForegroundColor White
Write-Host "   cd $CleanDir" -ForegroundColor Cyan
Write-Host "   git remote add origin https://github.com/$GitHubRepo.git" -ForegroundColor Cyan
Write-Host "   git push -u origin main" -ForegroundColor Cyan
Write-Host "   git tag -a v1.0.0 -m '🎉 v1.0.0: Initial secure release'" -ForegroundColor Cyan
Write-Host "   git push origin v1.0.0" -ForegroundColor Cyan
Write-Host ""
Write-Host "3. Make the repository PUBLIC on GitHub" -ForegroundColor White
Write-Host "4. Test the installer:" -ForegroundColor White
Write-Host "   irm https://raw.githubusercontent.com/$GitHubRepo/main/install.ps1 | iex" -ForegroundColor Cyan