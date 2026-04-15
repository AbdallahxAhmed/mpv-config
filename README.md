# MPV Auto-Deploy

One command to deploy a fully configured MPV media player with scripts, shaders, and keybindings — on **Windows**, **Linux**, and **macOS**.

## Quick Install

### Windows (PowerShell)
```powershell
irm https://raw.githubusercontent.com/AbdallahxAhmed/mpv-config/main/install.ps1 | iex
```

### Linux / macOS
```bash
curl -fsSL https://raw.githubusercontent.com/AbdallahxAhmed/mpv-config/main/install.sh | bash
```

## What It Does

1. **Detects** your OS, GPU vendor, display server, and installed tools
2. **Installs** missing dependencies (mpv, yt-dlp, ffmpeg, ffsubsync)
3. **Fetches** latest scripts & shaders directly from their GitHub repos
4. **Patches** configs for your platform (GPU API, shader separators, paths)
5. **Deploys** everything to your mpv config directory
6. **Verifies** the entire installation with 20+ automated checks

## Included Scripts

| Script | Source | Description |
|--------|--------|-------------|
| [uosc](https://github.com/tomasklaen/uosc) | Release | Modern on-screen UI |
| [thumbfast](https://github.com/po5/thumbfast) | Raw | Live thumbnail previews |
| [SmartSkip](https://github.com/Eisa01/mpv-scripts) | Raw | Intelligent chapter/silence skip |
| [sponsorblock](https://github.com/po5/mpv_sponsorblock) | Raw | Skip YouTube sponsors |
| [autosubsync](https://github.com/joaquintorres/autosubsync-mpv) | Raw | Auto subtitle synchronization |
| [autoload](https://github.com/mpv-player/mpv) | Raw | Auto-load directory into playlist |
| [memo](https://github.com/po5/memo) | Raw | Watch history menu |
| [evafast](https://github.com/po5/evafast) | Raw | Hybrid fast-forward |
| [pause-when-minimize](https://github.com/mpv-player/mpv) | Raw | Pause on minimize |
| [Anime4K](https://github.com/bloc97/Anime4K) | Release | Real-time anime upscaling (v4.0.1) |

## Manual Usage

```bash
git clone https://github.com/AbdallahxAhmed/mpv-config.git
cd mpv-config
python setup.py              # Full install
python setup.py --update     # Update scripts only
python setup.py --verify     # Verify installation
python setup.py --status     # Show installed versions
python setup.py --dry-run    # Preview without changes
```

## Platform Handling

Settings are automatically configured per platform:

| Setting | Windows | Linux |
|---------|---------|-------|
| GPU API | `d3d11` | `vulkan` |
| HW Decode | `auto` | `nvdec`/`vaapi` (GPU-specific) |
| GPU Context | — | `waylandvk` / `x11vk` |
| Shader separator | `;` | `:` |
| Config dir | `%APPDATA%/mpv` | `~/.config/mpv` |

## Architecture

```
├── setup.py              # CLI entry point
├── install.sh            # Linux/macOS bootstrap
├── install.ps1           # Windows bootstrap
├── deploy/
│   ├── ui.py             # Terminal UI
│   ├── registry.py       # Script sources + platform defaults
│   ├── detector.py       # OS/GPU/environment detection
│   ├── fetcher.py        # GitHub downloader (retry + backoff)
│   ├── installer.py      # Dependency installer
│   ├── deployer.py       # Deploy + backup + template patching
│   └── verifier.py       # Post-install verification
└── config/
    ├── mpv.conf.template
    ├── input.conf.template
    └── script-opts/
```

## Requirements

- **Python 3.8+** (no external packages needed)
- **Internet connection** (to fetch scripts from GitHub)

## License

Personal configuration. Scripts retain their original licenses.
