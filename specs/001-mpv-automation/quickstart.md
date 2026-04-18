# Quickstart: MPV Auto-Deploy

## First-Time Installation

### Linux / macOS
```bash
curl -fsSL https://raw.githubusercontent.com/AbdallahxAhmed/mpv-config/main/install.sh | bash
```

### Windows (PowerShell)
```powershell
irm https://raw.githubusercontent.com/AbdallahxAhmed/mpv-config/main/install.ps1 | iex
```

This will:
1. Detect your OS, GPU, and display server
2. Show you a plan of what will be installed
3. Ask for your confirmation
4. Install missing dependencies (mpv, yt-dlp, ffmpeg, ffsubsync)
5. Download 9 mpv scripts + Anime4K shaders from GitHub
6. Patch configs for your platform
7. Deploy everything to your mpv config directory
8. Run 20+ verification checks

## After Installation

Use the launcher command:
```bash
mpv-config                    # Interactive menu
mpv-config --update           # Update scripts only
mpv-config --rollback         # Restore latest backup
mpv-config --verify           # Verify deployment
mpv-config --status           # Show installed versions
mpv-config --uninstall        # Remove deployed files
```

## Manual Installation (Advanced)

```bash
git clone https://github.com/AbdallahxAhmed/mpv-config.git
cd mpv-config
python setup.py               # Full install with interactive menu
python setup.py --dry-run     # Preview without changes
```

## Verification

After install, verify everything works:
```bash
mpv-config --verify
```

Expected: All 20+ checks pass (✓ green).

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Cannot reach GitHub" | Check internet connection. If behind proxy, set `HTTP_PROXY`. |
| "pip not found" | Install Python 3.8+ first, then re-run. |
| mpv doesn't launch | Run `mpv-config --verify` to see which files are missing. |
| Want old config back | Run `mpv-config --rollback` to restore the backup. |
