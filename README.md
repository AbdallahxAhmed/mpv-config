# MPV Auto-Deploy

## What this does
MPV Auto-Deploy installs a fully configured mpv setup with curated scripts, Anime4K shaders, and platform-aware defaults. It targets smooth fixed-refresh playback with reliable frame pacing while keeping the UI responsive.

## Hardware detection
The deployer auto-detects:
- **OS + display server** (Windows/Linux/macOS, Wayland/X11)
- **GPU vendor** (NVIDIA/AMD/Intel)
- **AVX2** (to select optimized Windows mpv builds)
- **Display refresh rate** (diagnostic logging only; no forced override)

## Quick install

### Windows (PowerShell)
```powershell
irm https://raw.githubusercontent.com/AbdallahxAhmed/mpv-config/main/install.ps1 | iex
```

### Linux / macOS
```bash
curl -fsSL https://raw.githubusercontent.com/AbdallahxAhmed/mpv-config/main/install.sh | bash
```

**Security note:** Release assets include SHA256 files. Verify downloads before running installers.

## Manual install (full CLI)
```bash
git clone https://github.com/AbdallahxAhmed/mpv-config.git
cd mpv-config
python setup.py --install
```

Key flags:
- `--mpv-profile {windows-like,native,linux-like}`
- `--anime-preset {fast,A,A+A,B,C,off}` (default: A)
- `--scaler-tier {light,balanced,quality}` (default: balanced)
- `--display-mode {auto,fixed,vrr}` (default: fixed)
- `--dither-depth {auto,8,10}` (default: auto)
- `--mpv-version <tag>` (Windows only: override pinned mpv build)
- `--migrate-from-old` (extract user overrides into `mpv.conf.user`)
- `--update`, `--rollback`, `--verify`, `--status`, `--uninstall`, `--dry-run`

**VRR warning:** `--display-mode vrr` makes the entire desktop UI refresh at the content FPS (25–60Hz). Use only for HTPC/darkroom setups; desktop use should stay on `fixed`.

## NVIDIA Control Panel setup (Windows)
**Manage 3D Settings → Program Settings → Add mpv.exe**

| Setting | Value | Reason |
|---|---|---|
| Monitor Technology | G-SYNC Compatible | Keeps G-Sync active for games |
| Vertical sync | Use the 3D application setting (or Off) | Let mpv `display-resample` control VSync |
| Max Frame Rate | Off | Remove any FPS cap |
| Low Latency Mode | Off | Avoid conflicts with `display-resample` scheduling |
| Power management mode | Prefer maximum performance | Prevent GPU downclocking during shaders |
| Threaded optimization | On | Default safe setting |
| Triple buffering | Off | Not needed with flip-model |
| Preferred refresh rate | Highest available | Ensure 144Hz mode |

**Windows Settings → System → Display → Graphics**
- Default graphics settings → **Variable refresh rate: OFF**
- mpv.exe → **High performance**

## Verification (Shift+I → 2)
After 30s on a local 25fps file:

| Metric | Expected | Fail sign |
|---|---|---|
| Estimated display FPS | 143.97–143.99 Hz | 282Hz or <100Hz |
| VSync Ratio | ~5.76 (25fps) | 1.000 = VRR active |
| VSync Jitter | < 0.05 | > 0.1 |
| A-V desync | ±0.001 | Drifting > 0.1 |
| Dropped | 0 | Any drops |
| Mistimed | < 5/min | Rapidly increasing |
| Delayed | < 10/min | > 50 |
| Frame Timing avg | < 2 ms | > 5 ms |
| HW (decoder) | d3d11va | d3d11va-copy / nvdec-copy |
| Format | rgb10a2 | rgb8 |

## Tuning (`mpv.conf.user`)
User overrides live in `mpv.conf.user`, which is loaded after `mpv.conf`. Put personal settings here (fonts, volume, cache size) so updates don’t overwrite them. The `--migrate-from-old` flag will populate this file from an existing config.

## Troubleshooting
| Symptom (OSD) | Likely cause | Fix |
|---|---|---|
| Estimated FPS reads 282Hz | Manual FPS override or driver conflict | Remove overrides, keep `display-resample` |
| VSync Ratio = 1.000 | VRR active | Disable VRR or use `--display-mode fixed` |
| Frame timing > 5ms | Copy-path hwdec | Ensure `hwdec=d3d11va` |
| UI sluggish during playback | `video-sync=audio` with VRR | Use `--display-mode fixed` |
| Seek clicks freeze UI | `hr-seek` exact + no framedrop | Use defaults in template (`hr-seek=default`, `hr-seek-framedrop=yes`) |

## Architecture
```
install.sh / install.ps1
        ↓
     setup.py
        ↓
   detect → plan → install deps → fetch → deploy → verify
        ↓
     config/ + audit log + lockfile
```
