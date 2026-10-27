# mpv-config

[![CI](https://github.com/AbdallahxAhmed/mpv-config/actions/workflows/test.yml/badge.svg)](https://github.com/AbdallahxAhmed/mpv-config/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**English** | [العربية](README.ar.md)

> Unified MPV configuration, deployment, and media-download toolkit.

`mpv-config` transforms [mpv](https://mpv.io) into an out-of-the-box, high-fidelity media player with curated Lua scripts, Anime4K upscaling shaders, platform-aware hardware decoding, a mouse-first uosc interface, and an integrated yt-dlp/FFmpeg download engine — all deployed transactionally with rollback safety.

---

## 📑 Table of Contents

- [📊 Project status](#project-status)
- [✨ Features](#features)
  - [🎬 Playback quality](#playback-quality)
  - [🖥️ Interface](#interface)
  - [📺 YouTube & streaming](#youtube--streaming)
  - [🧰 Player utilities](#player-utilities)
  - [⬇️ Downloading](#downloading)
  - [🛡️ Deployment safety](#deployment-safety)
  - [🌍 Arabic layout support](#arabic-layout-support)
- [⌨️ Keybindings](#keybindings)
  - [Anime4K shader chains (`Ctrl` + number)](#anime4k-shader-chains-ctrl--number)
  - [Screenshots & audio/video controls (`F1`–`F10`)](#screenshots--audiovideo-controls-f1f10)
  - [Everyday script keys](#everyday-script-keys)
  - [SmartSkip — skipping & chapters](#smartskip--skipping--chapters)
  - [SponsorBlock (YouTube segments)](#sponsorblock-youtube-segments)
  - [Mouse & window](#mouse--window)
  - [Arabic keyboard twins (same physical key)](#arabic-keyboard-twins-same-physical-key)
- [📦 Installation](#installation)
  - [Quick Bootstrap](#quick-bootstrap)
    - [Windows (PowerShell)](#windows-powershell)
    - [Linux / macOS](#linux--macos)
- [🚀 Usage](#usage)
  - [1. Install & Deploy Configuration](#1-install--deploy-configuration)
  - [2. Verify Installation](#2-verify-installation)
  - [3. Manage the Deployment](#3-manage-the-deployment)
  - [4. Download Media](#4-download-media)
  - [5. Background Clipboard Watcher](#5-background-clipboard-watcher)
- [🧩 What gets deployed](#what-gets-deployed)
  - [Managed third-party components (pinned upstream sources)](#managed-third-party-components-pinned-upstream-sources)
  - [Custom scripts shipped in this repository](#custom-scripts-shipped-in-this-repository)
  - [System dependencies managed by the installer](#system-dependencies-managed-by-the-installer)
  - [Repository tooling](#repository-tooling)
- [🛠️ Development](#development)
  - [Setup Development Environment](#setup-development-environment)
  - [Running Tests & Quality Checks](#running-tests--quality-checks)
- [📄 License](#license)

---

<a id="project-status"></a>
## 📊 Project status

| | |
| --- | --- |
| Release | **v1.0.0** (2026-10-07) — see [CHANGELOG.md](CHANGELOG.md) |
| CLI | `mpv-config` with `install` / `verify` / `update` / `rollback` / `status` / `sync-deps` / `download` / `uninstall` |
| Tests | 470 Python tests + 11 Lua test suites on a CI matrix of 3 OS × Python 3.10–3.12, plus Ruff lint/format |
| Platforms | Windows 10/11, Linux (X11 & KDE Wayland), macOS |
| Requires | mpv ≥ 0.40 (auto-upgraded by the installer), Python 3.10+ |

Recent work now on `main` (unreleased in the changelog):

- **Anime4K Auto-Detection & Default A+A (Ultra Sharp)** — `scripts/profile_picker.lua` automatically identifies anime releases offline, activates Anime4K shaders on the "A+A (Ultra Sharp)" preset by default, and presents an on-screen verification badge (`Anime Detected: Anime4K [A+A] Active`). Shipped default choice is customizable during installation (where A+A is #1 recommended alongside A, B, B+B, C, C+A, fast, off) and can be changed later via 3 permanent methods.
- **Dynamic 144Hz Playback & Video Enhancement Controls** — `F4` toggles motion interpolation ON/OFF (144Hz Smooth vs Native Cadence); `Shift+F4` (or `Alt+t`) switches the temporal motion scaler (`oversample` crisp/zero blur vs `linear` smooth/blended); `F10` toggles native mpv sharpening (crisp 0.35 / OFF); `F3` toggles grain-free debanding (clean 1-pass filtering without artificial grain).
- **Streaming Clarity & 144Hz Fluidity** — modern codec prioritization (`format-sort=res,fps,codec:av01,codec:vp9.2,codec:vp9,vbr`) prioritizing AV1 > VP9 > H.264 for maximum 1080p clarity, timeline fluidity, and 144Hz responsiveness without stutter (`cache-pause=no`).
- **Silent Hardware-Level Arabic Layout Parity** — on Windows, `tools/mpv_arabic_layout.ahk` provides 1:1 physical scan-code parity for all letter keys (`h`, `b`, `g`, etc.) when mpv is focused and Arabic is active, launched 100% silently on startup via native Win32 subprocess with `CREATE_NO_WINDOW` and detached execution. On Linux/macOS, native layout twins in `input.conf` cover printable keys (`c→ؤ`, `a→ش`, `n→ى`, `?→؟`) with bare Shift (`أ/’/ٍ/آ/‘`) and `Ctrl+Shift` backup routes for the five lam-alef keys.
- **Hardened management commands** — `rollback` restores only this config's own `mpv.backup.*` folders; `uninstall` can cleanly purge the config, backups, managed dependencies and the install directory.
- **Robust installers** — `install` / `verify` wired to the real deployer; the shell bootstrap works on PEP 668 systems (Ubuntu 24.04) via a private venv.
- **Security hygiene** — no key material or personal paths tracked; enforced by `tests/test_repo_hygiene.py`.

---

<a id="features"></a>
## ✨ Features

<a id="playback-quality"></a>
### 🎬 Playback quality
- **Automatic anime detection & default A+A preset** — `scripts/profile_picker.lua` automatically identifies anime releases offline (release groups, Japanese audio track, episode markers, multi-language tags, or titles in `script-opts/anime_series.conf`). When detected, it activates Anime4K on the **"A+A (Ultra Sharp)"** preset by default and presents an on-screen verification badge (`Anime Detected: Anime4K [A+A] Active`). Japanese live action and Hollywood movies remain unscaled on the clean `[live-action]` profile.
- **Select your default preset during installation** — the interactive installer shows a numbered **1–8 menu** with a short description per preset (arrow keys + `Enter` to browse, digits `1`–`8` select instantly, `Esc` keeps the default), where **A+A (Ultra Sharp)** is pre-highlighted as the #1 recommended default alongside `A`, `B`, `B+B`, `C`, `C+A`, `fast`, and `off`. Non-interactive installs accept `--anime-preset <MODE>`.
- **Change and save your default preset anytime (3 methods)**:
  1. *In-player shortcuts*: Press `Ctrl+1`..`Ctrl+6`, `Ctrl+0` (off), or `Ctrl+g` (cycle). The choice is instantly applied, displayed on-screen (`Anime4K: <MODE> - <LABEL> (Saved as Default)`), and persisted to `script-opts/anime4k.conf`.
  2. *Configuration file*: Edit `script-opts/anime4k.conf` directly (e.g. `mode=A+A`).
  3. *CLI update*: Run `mpv-config update --anime-preset <MODE>` or `python -m deploy.deployer --update --anime-preset <MODE>`.
- **Dynamic 144Hz motion & video enhancement controls**:
  - `F4`: Toggle motion interpolation ON/OFF (144Hz Smooth vs Native Cadence).
  - `Shift+F4` (or `Alt+t`): Switch motion scaler (`oversample` crisp/zero blur vs `linear` smooth/blended).
  - `F10`: Toggle native mpv sharpening (crisp `0.35` / `OFF`).
  - `F3`: Toggle grain-free debanding (`deband=no` default; 1-pass clean gradient smoothing with 0 synthetic grain).
- **One-key ASS cheat sheet** (`?` or `F9`) — native vector ASS overlay listing keys and mouse actions; physical `/` bare is ignored to prevent accidental volume drops.
- **Anime4K v4.0.1** shader chains (`Ctrl+1`…`6`) — applied automatically by the auto-detected `[anime]` profile (Anime4K + 2-pass deband); `[live-action]` stays clean by default, while `Ctrl+1`–`6` remain a manual override on any video.
- **gpu-next (libplacebo)** renderer with platform auto-detection: `d3d11` + `d3d11va` zero-copy on Windows (measured 1.4 ms/frame vs 5.3 ms for `nvdec-copy`), Vulkan + `auto-safe` on Linux, VideoToolbox on macOS.
- **Fixed-refresh display sync** — calibrated for 1080p 144 Hz panels; linear temporal scaling absorbs non-integer VSync ratios without judder, with a dedicated KDE-Wayland stabilization profile.
- **Source-aware profiles** — `[anime]` (Anime4K + 2-pass deband), `[live-action]` (clean native playback), `[protocol.https]` streaming (800 MiB buffer / 60 s readahead, same vblank alignment).
- **Full 10-bit pipeline** — explicit `dither-depth=10` (mpv's `auto` silently drops to 8-bit on gpu-next), temporal dithering, calibrated deband thresholds.

<a id="interface"></a>
### 🖥️ Interface
- **Mouse-first uosc toolbar** — `Menu · Paste | CC · Dubs · Quality · Download | Stable Volume … Fullscreen`; no keyboard required (see [docs/YOUTUBE_GUI.md](docs/YOUTUBE_GUI.md)).
- **thumbfast** seekbar hover previews (with local race-condition hardening patches).
- **Watch history & recent files** (memo) on `h`, subtitle backdrop "Netflix look" toggle on `b` with clear OSD feedback.
- Playlists, editions and quality selectors appear contextually; window close always exits instantly.

<a id="youtube--streaming"></a>
<a id="youtube-streaming"></a>
### 📺 YouTube & streaming
- **Modern codec prioritization & 144Hz fluidity** — `ytdl-raw-options-append = format-sort=res,fps,codec:av01,codec:vp9.2,codec:vp9,vbr` prioritizing AV1 > VP9 > H.264 for maximum 1080p clarity, timeline fluidity, and 144Hz UI responsiveness without buffer stalls (`cache-pause=no`).
- **Custom hardened `yt-dlp` hook** — in-player streaming of YouTube/network URLs with a self-refreshing yt-dlp stub and mpv 0.41+ compatible subprocess handling.
- **On-demand caption menu** (`Ctrl+C` or CC button) with *Creator / Auto-generated / Auto-translated* groups, cancellable async loading, no reloads and per-session reuse.
- **Smart dub filtering** — the playback hook keeps the best-bitrate rendition per language/role and defaults video selection to match the chosen dub.
- **SponsorBlock** integration with segment marking, submission and up/down-vote keybindings.
- **Configurable default quality** — the streaming ceiling lives in one file (`script-opts/stream_quality.conf`, default 1080p): pick it in the installer (`--stream-quality`), or change it in two clicks from the player's Quality menu — *720p ▸ Set as default* persists it and switches the playing stream (*Just this video* stays session-only). No hardcoded caps anywhere.

<a id="player-utilities"></a>
### 🧰 Player utilities
- **Stable Volume / night mode** (`F8` or toolbar button) — `dynaudnorm` + `alimiter` chain that lifts quiet dialogue without pumping or clipping.
- **Subtitle sync menu** (`n`, autosubsync + optional `alass`), screenshots with/without subtitles (`F1`/`F2`, PNG → `Pictures/mpv-screenshots`).
- **SmartSkip** (`>` `<` `?`) — smart intro/outro/silence skipping, auto-skip countdowns, and chapter add/remove/save.
- **evafast** hybrid fast-forward on `Right`; `autoload` fills the playlist from the folder; playback pauses when the window is minimized.
- **Paste-to-open** inside the player (`Ctrl+V`) — normalizes `youtu.be`, `watch?v=`, `shorts/…` fragments and quoted paths; local files are never rewritten into URLs.

<a id="downloading"></a>
### ⬇️ Downloading
- **Plugin-based downloader** (`BaseDownloader` → `GenericDownloader`) powered by native in-process `yt-dlp` with FFmpeg remuxing.
- **16-connection turbo worker** (`tools/download_worker.py`) — aria2c (`-x16 -s16 -j16`) or native concurrent fragments.
- **Clipboard watcher** (`mpv-config download --watch`) that downloads every media link you copy, with per-URL exception recovery.

<a id="deployment-safety"></a>
### 🛡️ Deployment safety
- **Transactional deploys** with a recoverable same-filesystem engine, package-ownership audit log, and read-only verification (Lua syntax checks included).
- **Backups & rollback** — every change snapshots the current config as `mpv.backup.*`; `update` preserves your personal `mpv.conf.user` overrides.
- **Clean uninstall** — with optional `--purge-config`, `--remove-backups`, `--remove-deps`, `--remove-install-dir`.

<a id="arabic-layout-support"></a>
### 🌍 Arabic layout support
- **Windows physical key parity**: `tools/mpv_arabic_layout.ahk` maps physical scan codes directly when mpv is focused and Arabic is active (`h`, `b`, `g`, etc.), launched 100% silently via native Win32 subprocess with `CREATE_NO_WINDOW` and detached execution.
- **Cross-platform layout twins**: generated at deploy time in `input.conf` for printable Latin keys (`c→ؤ`, `a→ش`, `n→ى`, `?→؟`) and modified combos, with bare Shift (`Shift+H/M/S/B/U` → `أ/’/ٍ/آ/‘`) and `Ctrl+Shift` backup routes for the five lam-alef keys.

---

<a id="keybindings"></a>
## ⌨️ Keybindings

The quick-reference below ships inside `config/input.conf.template`; SmartSkip's own bindings live in `config/script-opts/SmartSkip.conf`.

<a id="anime4k-shader-chains-ctrl--number"></a>
<a id="anime4k-shader-chains"></a>
### Anime4K shader chains (`Ctrl` + number)

> Any shortcut below immediately persists the chosen preset as default to `script-opts/anime4k.conf`.

| Key | Action |
| --- | --- |
| `Ctrl+1` | Mode A (Sharp) |
| `Ctrl+2` | Mode B (Soft) |
| `Ctrl+3` | Mode C (Denoise) |
| `Ctrl+4` | Mode A+A (Ultra Sharp) — **Default** |
| `Ctrl+5` | Mode B+B (Ultra Soft) |
| `Ctrl+6` | Mode C+A (Denoise + Sharp) |
| `Ctrl+0` | Clear all shaders (Off) |
| `Ctrl+g` | Cycle Anime4K mode |
| `Ctrl+Shift+t` | Toggle profile mode (Auto / Anime / Live-Action) |

<a id="screenshots--audiovideo-controls-f1f10"></a>
<a id="screenshots-audiovideo-controls"></a>
### Screenshots & audio/video controls (`F1`–`F10`)

| Key | Action |
| --- | --- |
| `F1` | Screenshot (video only, no subtitles) |
| `F2` | Screenshot (with subtitles) |
| `F3` | Toggle grain-free deband filter (1-pass, 0 synthetic grain) |
| `F4` | Toggle motion interpolation (144Hz Smooth vs Native Cadence) |
| `Shift+F4` / `Alt+t` | Switch motion scaler (`oversample` crisp/zero blur vs `linear` smooth/blended) |
| `F5` | Cycle audio track |
| `F6` | Cycle subtitle track |
| `F7` | Show/hide subtitles |
| `F8` | Stable Volume (night-mode loudness normalization) |
| `F10` | Toggle native sharpening (crisp `0.35` / `OFF`) |
| `?` / `F9` | Help Overlay cheat sheet (ASS formatted) |
| `/` (bare) | Ignored (prevents accidental volume drops) |

<a id="everyday-script-keys"></a>
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

<a id="smartskip--skipping--chapters"></a>
<a id="smartskip"></a>
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

<a id="sponsorblock-youtube-segments"></a>
### SponsorBlock (YouTube segments)

| Key | Action |
| --- | --- |
| `g` | Mark segment start/end |
| `G` | Submit segment to SponsorBlock |
| `B` | Upvote segment |
| `Ctrl+B` | Downvote segment |

<a id="mouse--window"></a>
<a id="mouse-window"></a>
### Mouse & window

| Input | Action |
| --- | --- |
| Right-click | Pause / resume (classic mpv behavior, no context menu) |
| Double right-click | Ignored |
| Window close (X) | Quit mpv instantly (`CLOSE_WIN quit`) |

> Everything above also has a mouse equivalent in the uosc toolbar — see [docs/YOUTUBE_GUI.md](docs/YOUTUBE_GUI.md).

<a id="arabic-keyboard-twins-same-physical-key"></a>
<a id="arabic-keyboard-twins"></a>
### Arabic keyboard twins (same physical key)

mpv matches a binding against the **character** a key produces ("mpv uses input translated by the
current OS keyboard layout, rather than physical scan codes"), so with an Arabic layout active the
Latin letter bindings never fire. The fix is pure config: on every install/update the deployer
appends a generated twin block to the **deployed** `input.conf` — for each printable Latin binding,
an extra binding on the character the **same physical key** produces on Arabic 101 (probed from the
real layout with `ToUnicodeEx`, cross-checked against xkeyboard-config). Your template and your own
lines stay Latin-only; the twins regenerate themselves, so nothing is maintained by hand. The
old Python keyboard-hook guard was removed entirely: on Windows, `scripts/keyboard_layout.lua`
silently starts the AutoHotkey helper (`tools/mpv_arabic_layout.ahk`) at mpv startup — a
detached native subprocess with `CREATE_NO_WINDOW` — and the helper exits 2 seconds after mpv
closes (opt out with `ahk=no` in `script-opts/keyboard_layout.conf`); on Linux/macOS nothing
runs beyond the config itself.

Five keys cannot have a bare twin: **h g b G B**. Measured on the real key stream (an
`--input-test` capture): pressing `b` delivers **only `ا`** to mpv — the `ل` of the lam-alef pair
never arrives — so `b` and `h` send the *identical* character (`G`/`H` alias on `أ`, `B`/`N` on
`آ`); no configuration can tell them apart. But two routes cover them with the **same physical keys**: plain **`Shift+H`** (history),
**`Shift+M`** (mark), **`Shift+S`** (submit), **`Shift+B`** (backdrop), **`Shift+U`** (upvote) —
under Arabic those deliver the distinct shift-layer characters `أ/’/ٍ/آ/‘`, which the config binds
(no Ctrl at all; in English the same presses are plain uppercase letters, so nothing changes) —
and the **`Ctrl+Shift+`** combos, which reach mpv under Arabic as `Ctrl+<Arabic char>`
(`Ctrl+Shift+H` arrives as `Ctrl+أ`, measured) and are twinned the same way. (`Ctrl+Shift+G` moved to `Ctrl+Shift+T`: under Arabic it
would collide with history's `Ctrl+أ`; likewise Shift+G delivers أ with Shift+H — mark lives on
Shift+M.) Plain `Ctrl+<letter>` is a Windows control code and works
in any layout, as do the function keys and `?` (twin `؟`); `Alt+<letter>` does not — the mouse
menu carries those actions.

| Key | Physical key | Action |
| --- | --- | --- |
| `ؤ` | C | Subtitles menu (twin of `c`) |
| `ش` | A | Audio tracks & dubs menu (twin of `a`) |
| `ى` | N | Subtitle sync menu (twin of `n`) |
| `؟` | `?` | Cheat sheet (twin of `?`) |
| `Shift+h` / `Ctrl+Shift+h` | H | Watch history (memo) |
| `Shift+m` / `Ctrl+Shift+m` | M | Mark SponsorBlock segment |
| `Shift+s` / `Ctrl+Shift+s` | S | Submit SponsorBlock segment |
| `Shift+b` / `Ctrl+Shift+b` | B | Subtitle backdrop toggle |
| `Shift+u` / `Ctrl+Shift+u` | U | SponsorBlock upvote |
| `ز` | `.` | Toggle auto-skip (same as `Ctrl+.`) |
| `د` | `.` | Toggle category auto-skip (same as `Alt+.`) |
| `غ` | Y | Confirm auto-skip countdown |
| `ء` | X | Add chapter (same as `Shift+N`) |
| `ق` | R | Remove chapter (same as `Alt+N`) |
| `ك` | `;` | Save chapters (same as `Ctrl+N`) |
| `؟` | `?` | Trigger silence skip |

> Modified Arabic combos (`Ctrl`/`Alt`/`Shift` + Arabic letter) are unreachable on Windows — every modified shortcut is owned by its Latin twin (`Ctrl+C`, `Ctrl+V`, `Ctrl+N`, …).

---

<a id="installation"></a>
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

<a id="quick-bootstrap"></a>
### Quick Bootstrap

#### Windows (PowerShell)
```powershell
irm https://raw.githubusercontent.com/AbdallahxAhmed/mpv-config/main/install.ps1 | iex
```

<a id="linux--macos"></a>
<a id="linux-macos"></a>
#### Linux / macOS
```bash
curl -fsSL https://raw.githubusercontent.com/AbdallahxAhmed/mpv-config/main/install.sh | bash
```

The script installs the CLI into its own virtual environment (`~/.local/share/mpv-config/venv`) and links `mpv-config` into `~/.local/bin`, so it also works on distributions that refuse `pip install --user` (PEP 668, e.g. Ubuntu 24.04). It needs Python 3.10+ (on Debian/Ubuntu also `python3-venv`). Pass options through with `... | bash -s -- --dry-run`.

`mpv-config install` — which both bootstrap scripts run for you — is interactive in a real terminal: it shows a numbered menu (1–8) of the Anime4K chains the auto-detected `[anime]` profile can use, with **A+A (Ultra Sharp)** highlighted as the #1 recommended default. Press `Enter` to keep the highlighted row, move with `Up`/`Down`, press `1`–`8` to select directly, or press `Esc` to keep the default. Piped or CI runs never see the menu (the shipped A+A default applies), and an explicit `--anime-preset <MODE>` skips it.

---

<a id="usage"></a>
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
| `--anime-preset` | `off` / `fast` / `A` / `A+A` / `B` / `B+B` / `C` / `C+A` (`A+A`) | Anime4K preset powering the auto `[anime]` profile. Interactive install shows the numbered menu (`A+A` #1 highlighted). |
| `--scaler-tier` | `light` / `balanced` / `quality` (`balanced`) | `scale` / `cscale` / `dscale` quality tier |
| `--display-mode` | `auto` / `fixed` / `vrr` (`fixed`) | Display-sync mode; `fixed` = display-resample, `vrr` opt-in for FreeSync/G-Sync |
| `--dither-depth` | `auto` / `8` / `10` (`auto`, auto-resolved) | Output dither depth |
| `--stream-quality` | `best` / `144` … `4320` (`1080`) | Default streaming ceiling seeded into `script-opts/stream_quality.conf` on **fresh** installs only — an existing file (player Quality-menu choice / hand edit) is always preserved |
| `--mpv-version` | tag override | Pin the Windows mpv build tag (e.g. `2026-05-15-4498c0ff81`) |

<a id="2-verify-installation"></a>
### 2. Verify Installation
```bash
mpv-config verify
```

### 3. Manage the Deployment
```bash
mpv-config status             # installed script/shader versions and the last installer session
mpv-config update             # refresh scripts and shaders; personal config preserved (or pass --anime-preset <MODE>)
mpv-config rollback           # restore the newest backup (the current config is snapshotted first)
mpv-config rollback <backup>  # restore a specific one of this config's mpv.backup.* folders
mpv-config sync-deps          # update yt-dlp, ffmpeg, alass and ffsubsync
mpv-config uninstall          # remove what was deployed (a backup is taken first)
```

The commands that change something accept `--dry-run`. `rollback` only restores one of the configuration's own backups (full path or bare folder name) and lists the available ones if you name anything else. `uninstall --purge-config` also removes the config directory itself, `--remove-backups` the backups, and `--remove-install-dir` the `~/.mpv-config-deploy` clone plus the private virtual environment that `install.sh` created.

<a id="4-download-media"></a>
### 4. Download Media
```bash
# Download a video (defaults to ~/Downloads at up to 1080p)
mpv-config download "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Specify custom destination and quality ceiling
mpv-config download "https://example.com/video" -o ~/Videos -q 720
```

On Windows, the repo-root launchers `Download-Video.cmd` and `Watch-Clipboard.cmd` wrap the same commands with a UTF-8 console.

<a id="5-background-clipboard-watcher"></a>
### 5. Background Clipboard Watcher
```bash
mpv-config download --watch
```

---

<a id="what-gets-deployed"></a>
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

<a id="custom-scripts-shipped-in-this-repository"></a>
### Custom scripts shipped in this repository

| Script | Purpose |
| --- | --- |
| `scripts/ytdl_hook.lua` | Hardened yt-dlp streaming hook, self-refreshing yt-dlp stub, dub filtering |
| `scripts/ytdl-sub-menu.lua` | On-demand YouTube captions menu (creator / auto / auto-translated) |
| `scripts/smart-paste.lua` | Clipboard paste-open + drag & drop URL normalization |
| `scripts/sub_backdrop.lua` | Subtitle backdrop toggle with bilingual OSD |
| `scripts/profile_picker.lua` | Offline anime auto-detection, Anime4K A+A default activation, and preset persistence |
| `scripts/smart_motion.lua` | 144Hz display-resample and interpolation management |
| `scripts/keyboard_layout.lua` | Silent native async Win32 launcher for the Arabic AHK helper |
| `scripts/help_overlay.lua` | ASS vector keybinding cheat sheet on `?` / `F9` |
| `scripts/player-toolbar.lua` | Stable Volume toolbar button and codec-prioritized quality switching (AV1 > VP9 > H.264) |
| `scripts/modules/stream_policy.lua` | Shared YouTube/stream policy module |

<a id="system-dependencies-managed-by-the-installer"></a>
### System dependencies managed by the installer

mpv ≥ 0.40 (zhongfly daily builds on Windows with shinchiro fallback, `ppa:ubuntuhandbook1/mpv` on Ubuntu/Mint, optimized x86-64-v3/v4 repos on CachyOS, brew/dnf/pacman elsewhere), [yt-dlp](https://github.com/yt-dlp/yt-dlp) (standalone, kept fresh), ffmpeg, ffsubsync, alass and uv.

<a id="repository-tooling"></a>
### Repository tooling

- **MPV Companion browser extension** (`tools/extension/`, Chrome MV3) + native messaging host — one-click playback and site-cookie sync to mpv/yt-dlp for Cloudflare-protected sites, with optional FlareSolverr support (`tools/core/flaresolverr.py`). Register it with `tools/register_extension.py`.
- **`tools/download_worker.py`** — headless 16-connection download worker (aria2c or native concurrent fragments).
- **`tools/vtt_translate.py`** — translate WebVTT subtitles (e.g. into Arabic) without cookies or API keys.
- **`tools/apply_youtube_gui.py`** — standalone, preview-first toolbar layout upgrade for uosc.

---

<a id="development"></a>
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

<a id="running-tests--quality-checks"></a>
<a id="running-tests-quality-checks"></a>
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

<a id="license"></a>
## 📄 License

This project is licensed under the [MIT License](LICENSE).
