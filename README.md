# MPV Auto-Deploy

## What this does
MPV Auto-Deploy installs a fully configured mpv setup with curated scripts, Anime4K shaders, and platform-aware defaults. It targets smooth fixed-refresh playback with reliable frame pacing while keeping the UI responsive.

## Hardware detection
The deployer auto-detects:
- **OS + display server** (Windows/Linux/macOS, Wayland/X11)
- **GPU vendor** (NVIDIA/AMD/Intel)
- **AVX2** (to select optimized Windows mpv builds)
- **Display refresh rate** (diagnostic logging only; no forced override)
- **Display bit depth** (Windows: reads `CurrentBitsPerPixel` to pick 8 or 10-bit dither automatically)

## What gets installed

**Scripts** (fetched from upstream):
- `uosc` — Modern on-screen UI for mpv
- `thumbfast` — On-the-fly thumbnail generator
- `SmartSkip` — Smart chapter/silence skip & auto-skip
- `sponsorblock` — Skip YouTube sponsored segments
- `autosubsync` — Automatic subtitle synchronization
- `autoload` — Auto-load directory files into playlist
- `memo` — Recent files / watch history menu
- `evafast` — Hybrid fast-forward and seeking
- `pause-when-minimize` — Pause playback on window minimize

**Shaders:** Anime4K real-time anime upscaling shaders.

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

## CLI flags reference

### `--mpv-profile {windows-like, native, linux-like}`
Selects the baseline GPU API + hardware-decoder pairing.

| Profile | gpu-api | hwdec | vo | Notes |
|---|---|---|---|---|
| `windows-like` | `d3d11` | `d3d11va` | `gpu-next` | Default on Windows. Also forces `nvdec` on Linux/NVIDIA to avoid copy-path overhead. |
| `linux-like` | `vulkan` | `auto-safe` | `gpu-next` | Default on Linux/macOS. |
| `native` | (inherited) | OS+GPU specific (`nvdec` on Linux/NVIDIA, `vaapi` on Linux/AMD) | (inherited) | Legacy per-platform behavior. |

**Default:** auto-picked — `windows-like` on Windows, `linux-like` elsewhere.

### `--anime-preset {fast, A, A+A, B, C, off}` *(default: `A+A`)*
Selects the Anime4K shader chain that gets written into `mpv.conf`.

| Preset | Use case | GPU cost |
|---|---|---|
| `fast` | Weak GPUs / low-power mode | Lowest |
| `A` | Sharp-line anime (standard A chain) | Medium |
| `A+A` | Enhanced A chain — doubled refinement passes | **High (default — best quality on modern GPUs)** |
| `B` | Soft-line anime | Medium |
| `C` | Complex/detailed artwork | Medium |
| `off` | Disable Anime4K entirely | None |

### `--scaler-tier {light, balanced, quality}` *(default: `quality`)*
Picks the scaling algorithm trio (`scale` / `cscale` / `dscale`).

| Tier | Quality | GPU cost |
|---|---|---|
| `light` | Basic algorithms | Lowest |
| `balanced` | Good visual quality, moderate cost | Medium |
| `quality` | Highest-quality EWA-class scalers | **High (default — best image quality)** |

### `--display-mode {auto, fixed, vrr}` *(default: `fixed`)*
Configures how mpv synchronizes frames with your display.

| Mode | video-sync | interpolation | d3d11-flip | When to use |
|---|---|---|---|---|
| `fixed` / `auto` | `display-resample` | `yes` | `yes` | **Default.** Traditional fixed-refresh monitors (60/120/144/240 Hz). |
| `vrr` | `audio` | `no` | `no` | G-Sync / FreeSync setups in HTPC / darkroom contexts. |

> **VRR warning:** `--display-mode vrr` makes the entire desktop UI refresh at the content FPS (25-60 Hz). Use only for HTPC/darkroom setups; desktop use should stay on `fixed`. `auto` is currently treated as `fixed` — VRR requires explicit opt-in.

### `--dither-depth {auto, 8, 10}` *(default: `auto`)*
Bit depth used for dithering, to prevent color banding.

- `auto` — On Windows the installer probes `CurrentBitsPerPixel` via PowerShell: >= 30 bpp -> `10`, otherwise -> `8`. On Linux/macOS stays `auto`.
- `8` — Force 8-bit dither (older monitors / SDR pipelines).
- `10` — Force 10-bit dither (HDR-capable / 10-bit panels).

### `--mpv-version <tag>` *(Windows only)*
Overrides the pinned mpv Windows build tag (e.g. `--mpv-version 2025-01-15`). Useful when the pinned build has a regression or you want to test a newer build
.

### `--migrate-from-old`
Compares your existing `mpv.conf` against the previous template (`mpv.conf.template.old`), extracts only the values you actually changed, and writes them into `mpv.conf.user`. After migration, `mpv.conf` is rebuilt from the new template so future updates don't overwrite your tweaks.

### Operation flags
| Flag | What it does |
|---|---|
| `--install` | Full install: detect -> plan -> confirm -> deps -> fetch -> deploy -> verify |
| `--update` | Re-fetch and redeploy scripts/shaders/fonts only (config untouched) |
| `--rollback [BACKUP_DIR]` | Restore latest backup, or a specific backup directory |
| `--verify` | Run self-diagnostic checks against the current install |
| `--status` | Show installed script/shader versions from `.deploy.lock.json` |
| `--uninstall` | Remove deployed files. Combine with `--purge-config`, `--remove-backups`, `--remove-deps`, `--remove-python`, `--remove-install-dir` |
| `--dry-run` | Preview every action without writing anything |
| `--interactive` | Force the interactive menu even when piped/non-TTY |

**VRR warning recap:** `--display-mode vrr` makes the entire desktop UI refresh at the content FPS (25-60 Hz). Use only for HTPC/darkroom setups; desktop use should stay on `fixed`.

## NVIDIA Control Panel setup (Windows)
**Manage 3D Settings -> Program Settings -> Add mpv.exe**

| Setting | Value | Reason |
|---|---|---|
| Monitor Technology | G-SYNC Compatible | Keeps G-Sync active for games |
| Vertical sync | Use the 3D application setting (or Off) | Let mpv `display-resample` control VSync |
| Max Frame Rate | Off | Remove any FPS cap |
| Low Latency Mode | Off | Avoid conflicts with `display-resample` scheduling |
| Power management mode | Prefer maximum performance | Prevent GPU downclocking during shaders |
| Threaded optimization | On | Default safe setting |
| Triple buffering | Off | Not needed with flip-model |
| Preferred refresh rate | Highest available | Ensure 144 Hz mode |

**Windows Settings -> System -> Display -> Graphics**
- Default graphics settings -> **Variable refresh rate: OFF**
- mpv.exe -> **High performance**

## Verification (Shift+I -> 2)
After 30s on a local 25fps file:

| Metric | Expected | Fail sign |
|---|---|---|
| Estimated display FPS | 143.97-143.99 Hz | 282 Hz or <100 Hz |
| VSync Ratio | ~5.76 (25fps) | 1.000 = VRR active |
| VSync Jitter | < 0.05 | > 0.1 |
| A-V desync | +/-0.001 | Drifting > 0.1 |
| Dropped | 0 | Any drops |
| Mistimed | < 5/min | Rapidly increasing |
| Delayed | < 10/min | > 50 |
| Frame Timing avg | < 2 ms | > 5 ms |
| HW (decoder) | d3d11va | d3d11va-copy / nvdec-copy |
| Format | rgb10a2 | rgb8 |

## Tuning (`mpv.conf.user`)
User overrides live in `mpv.conf.user`, which is loaded **after** `mpv.conf`. Put personal settings here (fonts, volume, cache size) so updates don't overwrite them. The `--migrate-from-old` flag will populate this file from an existing config.

## Troubleshooting
| Symptom (OSD) | Likely cause | Fix |
|---|---|---|
| Estimated FPS reads 282 Hz | Manual FPS override or driver conflict | Remove overrides, keep `display-resample` |
| VSync Ratio = 1.000 | VRR active | Disable VRR or use `--display-mode fixed` |
| Frame timing > 5 ms | Copy-path hwdec | Ensure `hwdec=d3d11va` |
| UI sluggish during playback | `video-sync=audio` with VRR | Use `--display-mode fixed` |
| Seek clicks freeze UI | `hr-seek` exact + no framedrop | Use defaults in template (`hr-seek=default`, `hr-seek-framedrop=yes`) |
| `git clone` errors with `NativeCommandError` in PowerShell | Git writes progress to stderr; `$ErrorActionPreference = "Stop"` treats it as fatal | Already handled in `install.ps1` via scoped `ErrorActionPreference` around the clone call |

## Architecture
```
install.sh / install.ps1
        |
     setup.py
        |
   detect -> plan -> install deps -> fetch -> deploy -> verify
        |
     config/ + audit log + lockfile
```
