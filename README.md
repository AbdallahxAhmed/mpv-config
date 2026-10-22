# mpv-config

[![CI](https://github.com/AbdallahxAhmed/mpv-config/actions/workflows/test.yml/badge.svg)](https://github.com/AbdallahxAhmed/mpv-config/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**English** | [العربية](README.ar.md)

> Unified MPV configuration, deployment, and media-download toolkit.

`mpv-config` transforms [mpv](https://mpv.io) into an out-of-the-box, high-fidelity media player with curated Lua scripts, Anime4K upscaling shaders, platform-aware hardware decoding, a mouse-first uosc interface, and an integrated yt-dlp/FFmpeg download engine — all deployed transactionally with rollback safety.

---

## 📊 Project status

| | |
| --- | --- |
| Release | **v1.0.0** (2026-10-07) — see [CHANGELOG.md](CHANGELOG.md) |
| CLI | `mpv-config` with `install` / `verify` / `update` / `rollback` / `status` / `sync-deps` / `download` / `uninstall` |
| Tests | Python + Lua suite (~370 cases) on a CI matrix of 3 OS × Python 3.10–3.12, plus Ruff lint/format |
| Platforms | Windows 10/11, Linux (X11 & KDE Wayland), macOS |
| Requires | mpv ≥ 0.40 (auto-upgraded by the installer), Python 3.10+ |

Recent work now on `main` (unreleased in the changelog):

- **Playback display-sync fixes** — `tscale=linear` + `video-timing-offset=0.01` for jitter-free `display-resample` at fixed 144 Hz, and a KDE-Wayland-only refresh-rate stabilization profile.
- **Conflict-free Arabic (AZERTY 102) keybindings** — probed against the real keyboard layout and audited for conflicts (`tests/test_keybinding_conflicts.py`).
- **Hardened management commands** — `rollback` restores only this config's own `mpv.backup.*` folders; `uninstall` can cleanly purge the config, backups, managed dependencies and the install directory.
- **Robust installers** — `install` / `verify` wired to the real deployer; the shell bootstrap works on PEP 668 systems (Ubuntu 24.04) via a private venv.
- **Security hygiene** — no key material or personal paths tracked; enforced by `tests/test_repo_hygiene.py`.

---

## ✨ Features

### 🎬 Playback quality
- **Automatic anime detection** - `scripts/profile_picker.lua` decides per file whether the file is anime
  (release group, Japanese audio track, episode marker, multi-language tag, or a title from your own
  `script-opts/anime_series.conf` list) and applies the matching profile. Offline, explainable, and it
  leaves Japanese live action and Hollywood movies on the light profile.
- **The Anime4K mode is your choice** - the installer asks which chain to ship (`off`, `fast`, `A`, `A+A`,
  `B`, `B+B`, `C`, `C+A`); `Ctrl+1`..`Ctrl+6` and `Ctrl+g` change it inside the player and the choice
  is remembered in `script-opts/anime4k.conf`.
- **A one-key cheat sheet** (`?` or `F9`) listing the keys and the mouse actions, including the Arabic
  layout twins.
- **Anime4K v4.0.1** shader chains (`Ctrl+1`…`6`), applied by the auto-detected `[anime]` profile
  (Anime4K + 2-pass deband) or by the light `[live-action]` one.
- **gpu-next (libplacebo)** renderer with platform auto-detection: `d3d11` + `d3d11va` zero-copy on Windows (measured 1.4 ms/frame vs 5.3 ms for `nvdec-copy`), Vulkan + `auto-safe` on Linux, VideoToolbox on macOS.
- **Fixed-refresh display sync** — calibrated for 1080p 144 Hz panels; linear temporal scaling absorbs non-integer VSync ratios without judder, with a dedicated KDE-Wayland stabilization profile.
- **Source-aware profiles** — `[anime]` (Anime4K + 2-pass deband), `[live-action]` (mild 1-pass deband + grain), `[protocol.https]` streaming (800 MiB buffer / 60 s readahead, same vblank alignment).
- **Full 10-bit pipeline** — explicit `dither-depth=10` (mpv's `auto` silently drops to 8-bit on gpu-next), temporal dithering, calibrated deband thresholds.

### 🖥️ Interface
- **Mouse-first uosc toolbar** — `Menu · Paste | CC · Dubs · Quality · Download | Stable Volume … Fullscreen`; no keyboard required (see [docs/YOUTUBE_GUI.md](docs/YOUTUBE_GUI.md)).
- **thumbfast** seekbar hover previews (with local race-condition hardening patches).
- **Watch history & recent files** (memo) on `h`, subtitle backdrop "Netflix look" toggle on `b` with clear OSD feedback.
- Playlists, editions and quality selectors appear contextually; window close always exits instantly.

### 📺 YouTube & streaming
- **Custom hardened `yt-dlp` hook** — in-player streaming of YouTube/network URLs with a self-refreshing yt-dlp stub and mpv 0.41+ compatible subprocess handling.
- **On-demand caption menu** (`Ctrl+C` or CC button) with *Creator / Auto-generated / Auto-translated* groups, cancellable async loading, no reloads and per-session reuse.
- **Smart dub filtering** — the playback hook keeps the best-bitrate rendition per language/role and defaults video selection to match the chosen dub.
- **SponsorBlock** integration with segment marking, submission and up/down-vote keybindings.
- **Configurable default quality** — the streaming ceiling lives in one file (`script-opts/stream_quality.conf`, default 1080p): pick it in the installer (`--stream-quality`), or change it in two clicks from the player's Quality menu — *720p ▸ Set as default* persists it and switches the playing stream (*Just this video* stays session-only). No hardcoded caps anywhere.

### 🧰 Player utilities
- **Stable Volume / night mode** (`F8` or toolbar button) — `dynaudnorm` + `alimiter` chain that lifts quiet dialogue without pumping or clipping.
- **Subtitle sync menu** (`n`, autosubsync + optional `alass`), screenshots with/without subtitles (`F1`/`F2`, PNG → `Pictures/mpv-screenshots`).
- **SmartSkip** (`>` `<` `?`) — smart intro/outro/silence skipping, auto-skip countdowns, and chapter add/remove/save.
- **evafast** hybrid fast-forward on `Right`; `autoload` fills the playlist from the folder; playback pauses when the window is minimized.
- **Paste-to-open** inside the player (`Ctrl+V`) — normalizes `youtu.be`, `watch?v=`, `shorts/…` fragments and quoted paths; local files are never rewritten into URLs.

### ⬇️ Downloading
- **Plugin-based downloader** (`BaseDownloader` → `GenericDownloader`) powered by native in-process `yt-dlp` with FFmpeg remuxing.
- **16-connection turbo worker** (`tools/download_worker.py`) — aria2c (`-x16 -s16 -j16`) or native concurrent fragments.
- **Clipboard watcher** (`mpv-config download --watch`) that downloads every media link you copy, with per-URL exception recovery.

### 🛡️ Deployment safety
- **Transactional deploys** with a recoverable same-filesystem engine, package-ownership audit log, and read-only verification (Lua syntax checks included).
- **Backups & rollback** — every change snapshots the current config as `mpv.backup.*`; `update` preserves your personal `mpv.conf.user` overrides.
- **Clean uninstall** — with optional `--purge-config`, `--remove-backups`, `--remove-deps`, `--remove-install-dir`.

### 🌍 Arabic layout support
- Bilingual twin keybindings for the Arabic 102 AZERTY layout, probed from the deployed keyboard layout and audited so no binding can misfire from lam-alef composites (see the keybinding tables below).

---

## ⌨️ Keybindings

The quick-reference below ships inside `config/input.conf.template`; SmartSkip's own bindings live in `config/script-opts/SmartSkip.conf`.

### Anime4K shader chains (`Ctrl` + number)

| Key | Action |
| --- | --- |
| `Ctrl+1` | Mode A (Sharp) |
| `Ctrl+2` | Mode B (Soft) |
| `Ctrl+3` | Mode C (Denoise) |
| `Ctrl+4` | Mode A+A (Ultra Sharp) |
| `Ctrl+5` | Mode B+B (Ultra Soft) |
| `Ctrl+6` | Mode C+A (Denoise + Sharp) |
| `Ctrl+0` | Clear all shaders |

### Screenshots & audio/video controls (`F1`–`F8`)

| Key | Action |
| --- | --- |
| `F1` | Screenshot (video only, no subtitles) |
| `F2` | Screenshot (with subtitles) |
| `F3` | Toggle deband filter |
| `F4` | Toggle interpolation (motion smoothing) |
| `F5` | Cycle audio track |
| `F6` | Cycle subtitle track |
| `F7` | Show/hide subtitles |
| `F8` | Stable Volume (night-mode loudness normalization) |

### Everyday script keys

| Key | Action |
| --- | --- |
| `c` | Subtitles menu (uosc) |
| `Ctrl+C` | YouTube auto-subtitles menu (on-demand captions) |
| `a` | Audio tracks & dubs menu (uosc) |
| `h` | Watch history / recent files (memo) |
| `n` | Subtitle sync menu (autosubsync) |
| `b` | Subtitle backdrop box on/off (Netflix look) |
| `Right` | Hybrid fast-forward (evafast) |
| `Ctrl+V` | Open the link/file from the clipboard (auto-normalized) |
| `Ctrl+Shift+V` | Append the clipboard link to the playlist |

### SmartSkip — skipping & chapters

| Key | Action |
| --- | --- |
| `>` | Smart next (skip intro/outro/silence) |
| `<` | Smart previous |
| `?` | Trigger silence skip |
| `Ctrl+.` | Toggle auto-skip on/off |
| `Alt+.` | Toggle category auto-skip |
| `Esc` | Cancel an active skip / countdown |
| `Enter` / `y` | Confirm the auto-skip countdown |
| `Ctrl+Right` | Next chapter |
| `Ctrl+Left` | Previous chapter |
| `Shift+N` | Add chapter at current position |
| `Alt+N` | Remove current chapter |
| `Ctrl+N` | Save chapters to file |

### SponsorBlock (YouTube segments)

| Key | Action |
| --- | --- |
| `g` | Mark segment start/end |
| `G` | Submit segment to SponsorBlock |
| `B` | Upvote segment |
| `Ctrl+B` | Downvote segment |

### Mouse & window

| Input | Action |
| --- | --- |
| Right-click | Pause / resume (classic mpv behavior, no context menu) |
| Double right-click | Ignored |
| Window close (X) | Quit mpv instantly (`CLOSE_WIN quit`) |

> Everything above also has a mouse equivalent in the uosc toolbar — see [docs/YOUTUBE_GUI.md](docs/YOUTUBE_GUI.md).

### Arabic keyboard twins (AZERTY 102)

`Ctrl+<letter>`, the function keys and punctuation are **layout independent** (Windows turns
`Ctrl+letter` into a control code, and `?`/`F9` are not letters), so every binding added from
now on uses them - `Ctrl+1`..`Ctrl+6` for the Anime4K modes, `Ctrl+g` to cycle them, `?`/`F9` for
the cheat sheet. `Alt+<letter>` is *not* layout independent: with an Arabic layout active the key
produces an Arabic character and the binding never matches - which is why the new bindings avoid
it. The letters that carry an Arabic twin keep it; the ones that would fire while typing
(`b` → `لا`, `h` → `ا`) are deliberately left to the mouse menu instead.

Ground truth probed from the deployed layout (`00000C01`): `b→لا`, `f→ب`, `j→ت`, `l→م`, `p→ح`, `a→ش`, `c→ؤ`, `n→ى`, `y→غ`, `x→ء`, `r→ق`, `;→ك`. mpv can only bind single codepoints, so the lam-alef composite `لا` can never be bound — those characters are deliberately left unbound, and every twin lives on a safe letter:

| Key | Physical key | Action |
| --- | --- | --- |
| `ؤ` | C | Subtitles menu |
| `ش` | A | Audio tracks & dubs menu |
| `ح` | P | Watch history (memo) |
| `ى` | N | Subtitle sync menu |
| `ب` | F | Subtitle backdrop toggle |
| `ت` | J | Mark SponsorBlock segment |
| `م` | L | Submit SponsorBlock segment |
| `ز` | `.` | Toggle auto-skip (same as `Ctrl+.`) |
| `د` | `.` | Toggle category auto-skip (same as `Alt+.`) |
| `غ` | Y | Confirm auto-skip countdown |
| `ء` | X | Add chapter (same as `Shift+N`) |
| `ق` | R | Remove chapter (same as `Alt+N`) |
| `ك` | `;` | Save chapters (same as `Ctrl+N`) |
| `؟` | `?` | Trigger silence skip |

> Modified Arabic combos (`Ctrl`/`Alt`/`Shift` + Arabic letter) are unreachable on Windows — every modified shortcut is owned by its Latin twin (`Ctrl+C`, `Ctrl+V`, `Ctrl+N`, …).

---

## 📦 Installation

`mpv-config` deploys from a checkout of this repository (`deploy/`, `config/` and `scripts/` are not part of the installed package), so install it **editable** from a clone. The command can then find the checkout from any directory:

```bash
git clone https://github.com/AbdallahxAhmed/mpv-config.git
cd mpv-config

# Isolated global CLI install via pipx (recommended)
pipx install --editable .

# Or, inside a virtual environment
pip install --editable .
```

A regular (non-editable) install only works while you run it from inside the clone, or with `MPV_CONFIG_REPO` pointing at the clone.

### Quick Bootstrap

#### Windows (PowerShell)
```powershell
irm https://raw.githubusercontent.com/AbdallahxAhmed/mpv-config/main/install.ps1 | iex
```

#### Linux / macOS
```bash
curl -fsSL https://raw.githubusercontent.com/AbdallahxAhmed/mpv-config/main/install.sh | bash
```

The script installs the CLI into its own virtual environment (`~/.local/share/mpv-config/venv`) and links `mpv-config` into `~/.local/bin`, so it also works on distributions that refuse `pip install --user` (PEP 668, e.g. Ubuntu 24.04). It needs Python 3.10+ (on Debian/Ubuntu also `python3-venv`). Pass options through with `... | bash -s -- --dry-run`.

---

## 🚀 Usage

`mpv-config` provides a unified command-line interface:

### 1. Install & Deploy Configuration
Deploy curated configurations, scripts, and shaders to your local MPV setup:
```bash
mpv-config install
```

Preview first with `mpv-config install --dry-run`: nothing is downloaded, installed or replaced.

Deploy-time options (forwarded to the deployer; run `python -m deploy.deployer --help` for the full list):

| Option | Choices (default) | Meaning |
| --- | --- | --- |
| `--mpv-profile` | `windows-like` / `linux-like` / `native` (OS-dependent) | GPU API, hardware decoder and VO selection |
| `--anime-preset` | `off` / `fast` / `A` / `A+A` / `B` / `C` (`A`) | Anime4K chain powering the auto `[anime]` profile |
| `--scaler-tier` | `light` / `balanced` / `quality` (`balanced`) | `scale` / `cscale` / `dscale` quality tier |
| `--display-mode` | `auto` / `fixed` / `vrr` (`fixed`) | Display-sync mode; `fixed` = display-resample, `vrr` opt-in for FreeSync/G-Sync |
| `--dither-depth` | `auto` / `8` / `10` (`auto`, auto-resolved) | Output dither depth |
| `--stream-quality` | `best` / `144` … `4320` (`1080`) | Default streaming ceiling seeded into `script-opts/stream_quality.conf` on **fresh** installs only — an existing file (player Quality-menu choice / hand edit) is always preserved |
| `--mpv-version` | tag override | Pin the Windows mpv build tag (e.g. `2026-05-15-4498c0ff81`) |

### 2. Verify Installation
```bash
mpv-config verify
```

### 3. Manage the Deployment
```bash
mpv-config status             # installed script/shader versions and the last installer session
mpv-config update             # refresh scripts and shaders; your personal config is preserved
mpv-config rollback           # restore the newest backup (the current config is snapshotted first)
mpv-config rollback <backup>  # restore a specific one of this config's mpv.backup.* folders
mpv-config sync-deps          # update yt-dlp, ffmpeg, alass and ffsubsync
mpv-config uninstall          # remove what was deployed (a backup is taken first)
```

The commands that change something accept `--dry-run`. `rollback` only restores one of the configuration's own backups (full path or bare folder name) and lists the available ones if you name anything else. `uninstall --purge-config` also removes the config directory itself, `--remove-backups` the backups, and `--remove-install-dir` the `~/.mpv-config-deploy` clone plus the private virtual environment that `install.sh` created.

### 4. Download Media
```bash
# Download a video (defaults to ~/Downloads at up to 1080p)
mpv-config download "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Specify custom destination and quality ceiling
mpv-config download "https://example.com/video" -o ~/Videos -q 720
```

On Windows, the repo-root launchers `Download-Video.cmd` and `Watch-Clipboard.cmd` wrap the same commands with a UTF-8 console.

### 5. Background Clipboard Watcher
```bash
mpv-config download --watch
```

---

## 🧩 What gets deployed

### Managed third-party components (pinned upstream sources)

| Component | Purpose |
| --- | --- |
| [uosc](https://github.com/tomasklaen/uosc) | Modern mouse-first UI, menus and toolbar |
| [thumbfast](https://github.com/po5/thumbfast) | Seekbar hover thumbnails |
| [SmartSkip](https://github.com/Eisa01/mpv-scripts) | Smart intro/outro/silence skip + chapter management |
| [mpv_sponsorblock](https://github.com/po5/mpv_sponsorblock) | Skip YouTube sponsored segments |
| [autosubsync-mpv](https://github.com/joaquintorres/autosubsync-mpv) | Automatic subtitle synchronization |
| [autoload](https://github.com/mpv-player/mpv) | Auto-load directory files into the playlist |
| [memo](https://github.com/po5/memo) | Watch history / recent-files menu |
| [evafast](https://github.com/po5/evafast) | Hybrid fast-forward and seeking |
| [pause-when-minimize](https://github.com/mpv-player/mpv) | Pause playback when the window is minimized |
| [Anime4K](https://github.com/bloc97/Anime4K) v4.0.1 | Real-time anime upscaling shaders |

### Custom scripts shipped in this repository

| Script | Purpose |
| --- | --- |
| `scripts/ytdl_hook.lua` | Hardened yt-dlp streaming hook, self-refreshing yt-dlp stub, dub filtering |
| `scripts/ytdl-sub-menu.lua` | On-demand YouTube captions menu (creator / auto / auto-translated) |
| `scripts/smart-paste.lua` | Clipboard paste-open + drag & drop URL normalization |
| `scripts/sub_backdrop.lua` | Subtitle backdrop toggle with bilingual OSD |
| `scripts/player-toolbar.lua` | Stable Volume toolbar button wiring |
| `scripts/modules/stream_policy.lua` | Shared YouTube/stream policy module |

### System dependencies managed by the installer

mpv ≥ 0.40 (zhongfly daily builds on Windows with shinchiro fallback, `ppa:ubuntuhandbook1/mpv` on Ubuntu/Mint, optimized x86-64-v3/v4 repos on CachyOS, brew/dnf/pacman elsewhere), [yt-dlp](https://github.com/yt-dlp/yt-dlp) (standalone, kept fresh), ffmpeg, ffsubsync, alass and uv.

### Repository tooling

- **MPV Companion browser extension** (`tools/extension/`, Chrome MV3) + native messaging host — one-click playback and site-cookie sync to mpv/yt-dlp for Cloudflare-protected sites, with optional FlareSolverr support (`tools/core/flaresolverr.py`). Register it with `tools/register_extension.py`.
- **`tools/download_worker.py`** — headless 16-connection download worker (aria2c or native concurrent fragments).
- **`tools/vtt_translate.py`** — translate WebVTT subtitles (e.g. into Arabic) without cookies or API keys.
- **`tools/apply_youtube_gui.py`** — standalone, preview-first toolbar layout upgrade for uosc.

---

## 🛠️ Development

### Setup Development Environment
```bash
# Clone the repository
git clone https://github.com/AbdallahxAhmed/mpv-config.git
cd mpv-config

# Install in editable mode with development dependencies
pip install -e .
pip install -r requirements-dev.txt

# Install pre-commit git hooks
pre-commit install
```

### Running Tests & Quality Checks
```bash
# Run unit test suite
python -m unittest discover -s tests

# Run Lua script tests
python tests/run_lua_tests.py

# Run linter and code formatting
ruff check .
ruff format .
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
