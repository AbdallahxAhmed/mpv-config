# Feature Specification: Installer & KDE Fixes

**Feature Branch**: `003-installer-and-kde-fixes`
**Created**: 2026-04-25
**Status**: Partially superseded — installer design replaced; see [As-built](#as-built-2026-11-19). Open items O1–O3 and O5 fixed 2026-11-20 (O5 needs a Windows test); O4 and O6 open.
**Input**: Fix installer crashes, dependency classification violations, and KDE Plasma 6.6.4 window behavior issues

## As-built (2026-11-19)

The installer design in this spec was replaced. This section describes
the code as it stands. Sections below marked **Superseded** are kept for
history; each says what replaced it.

### Installer and Python dependencies

- **Entry point**: [`src/mpv_config/cli/main.py`](../../src/mpv_config/cli/main.py),
  exposed as the `mpv-config` command (`pyproject.toml`
  `[project.scripts]`: `mpv_config.cli.main:main`). `mpv-config install`
  locates the repository checkout and runs `python -m deploy.deployer
  install …` as a subprocess. There is no `setup.py`.
- **Python dependencies**: [`pyproject.toml`](../../pyproject.toml)
  declares `rich`, `pycryptodomex`, `curl_cffi` and `yt-dlp`. `yt-dlp`
  is both a CLI tool (installed per platform from `SYSTEM_DEPS`, below)
  and a Python library (imported by `src/mpv_config/downloaders/generic.py`
  and `tools/core/registry.py`).
- **Linux/macOS bootstrap**: [`install.sh`](../../install.sh) always
  creates a venv at `${XDG_DATA_HOME:-~/.local/share}/mpv-config/venv`.
  If `ensurepip` is missing (Debian/Ubuntu without `python3-venv`), it
  uses `uv venv`, installing uv with its official installer if needed.
  It installs the checkout into the venv in editable mode (venv `pip` or
  `uv pip`), symlinks `~/.local/bin/mpv-config`, and execs
  `python -m mpv_config install`. It never installs into the system
  Python and never tries a system `python-rich` package. Its messages go
  through `_styled_echo` / `die`: Gum when installed, otherwise ANSI
  colour on a terminal and plain text elsewhere (since 2026-11-20, O2).
- **Windows bootstrap**: `install.ps1` installs missing prerequisites
  with winget, creates a private venv at `%LOCALAPPDATA%\mpv-config\venv`,
  installs the checkout into it in editable mode with the venv's pip,
  writes a `mpv-config.cmd` shim to `%LOCALAPPDATA%\mpv-config\bin`, and
  runs `python -m mpv_config install` with the venv Python. It never runs
  pip against the system Python (since 2026-11-20, O5; needs a Windows
  test). `Download-Video.cmd` / `Watch-Clipboard.cmd` use the venv Python,
  falling back to `python` on PATH.
- **UI fallback**: `deploy/ui.py` imports Rich and falls back to ANSI
  output when Rich is missing (lines 32–43). `_print(text="", **kwargs)`
  is at `deploy/ui.py:129`.

### System dependencies — [`deploy/registry.py`](../../deploy/registry.py) `SYSTEM_DEPS`

| Tool | Windows | Arch | Ubuntu | Fedora | macOS |
|------|---------|------|--------|--------|-------|
| mpv | GitHub release asset (`zhongfly/mpv-winbuild`, fallback `shinchiro/mpv-winbuild-cmake`) | pacman | PPA `ppa:ubuntuhandbook1/mpv` | dnf | brew |
| yt-dlp | direct URL `yt-dlp.exe` (7-day refresh) | pacman | GitHub binary `yt-dlp_linux` → `~/.local/bin` (7-day refresh) | same as Ubuntu | brew |
| ffmpeg | GitHub release zip (`BtbN/FFmpeg-Builds`) | pacman | apt | dnf | brew |
| python | winget | pacman | apt | dnf | brew |
| aria2 *(added)* | winget | pacman | apt | dnf | brew |
| ffsubsync | `uv tool` | AUR `python-ffsubsync` (fallback `ffsubsync`), then `uv tool` | `uv tool` | `uv tool` | `uv tool` |
| alass | GitHub release zip | AUR `alass-bin` (fallback `alass`), then GitHub binary | GitHub binary | GitHub binary | – |
| uv *(added)* | GitHub release zip | OS package manager, then the official installer script | same | same | same (brew) |
| autohotkey *(added)* | GitHub release zip | – | – | – | – |

- `gum` is **not** in the registry, and `install.sh` does not use it.
- winget remains only for `python` and `aria2` on Windows.
- AUR builds use `paru` or `yay`. Arch entries prefer the CachyOS
  optimized repos (`prefer_optimized_repo`).
- `deploy/installer.py` `_install_one` / `_uninstall_one` handle 15
  methods: `pacman`, `apt`, `dnf`, `brew`, `winget`, `aur`, `manual`,
  `ppa`, `pipx`, `uv`, `uv_tool`, `direct_url`, `github_asset`,
  `github_release_file`, `github_release_zip`.
- [`deploy/installer.py::sync_dependencies`](../../deploy/installer.py)
  (the `sync-deps` subcommand, `deploy/deployer.py::cmd_sync_deps`)
  refreshes yt-dlp, ffmpeg, alass and ffsubsync (and AutoHotkey on
  Windows) into a tools directory. Its ffsubsync step runs on every OS
  (`_sync_ffsubsync_cli`) tries `uv tool install --upgrade`, then
  `pipx upgrade` / `pipx install`, and never uses pip. Without uv or pipx
  it installs nothing and tells the user to add one (since 2026-11-20, O1).

### KDE window behaviour

- **Close**: `config/input.conf.template:156` binds
  `CLOSE_WIN set window-minimized yes ; quit`; lines 157–158 bind `q` and
  `Q` the same way (`quit` / `quit-watch-later`).
  [`scripts/fast_close.lua`](../../scripts/fast_close.lua) on Linux
  minimizes the window on `shutdown` and overrides the `quit` /
  `quit-watch-later` bindings to minimize first. This hides the visible
  freeze while the Vulkan / libplacebo / Wayland teardown completes.
  Covered by `tests/lua/test_fast_close.lua`.
- **Fullscreen**: handled by mpv's own Wayland backend (see User Story 4).
  No repo code is involved: the no-op `native-fs = no` line and the
  `{{NATIVE_FS}}` placeholder were removed on 2026-11-20 (O3).
- **Window sizing helpers**: `geometry=50%x50%`, `autofit-larger=90%x90%`
  and `autofit-smaller=30%x30%` come from
  `deploy/deployer.py::_get_linux_visual_tuning_block` (lines 169–172),
  substituted into `{{LINUX_VISUAL_TUNING}}` (see O4).

### Open items (code bugs — to be fixed in a separate change)

O1–O3 and O5 were fixed on 2026-11-20 (one commit each; O5 still needs a
Windows test). O4 and O6 remain open.

- **O1** — **Fixed 2026-11-20** (`58d50f2`): ffsubsync now uses `uv tool`,
  then pipx, never pip; covered by `tests/test_sync_ffsubsync.py`.
  Original finding: `sync_dependencies` falls back to `python -m pip install` and
  bare `pip install` for ffsubsync (`deploy/installer.py:2248-2256`).
  This violates the constitution's rule that pip is never used for CLI
  tools (Principle III, Category A).
- **O2** — **Fixed 2026-11-20** (`729639f`): all output goes through the
  `_styled_echo` / `die` Gum wrappers with an ANSI/plain fallback;
  shellcheck clean; covered by `tests/test_install_sh_output.py`.
  Original finding: `install.sh` prints with raw `echo` and has no Gum wrappers,
  which violates Principle V (Aesthetic CLI UX).
- **O3** — **Fixed 2026-11-20** (`e6eb056`): `native_fs_value`,
  `{{NATIVE_FS}}` and the template block were removed; covered by
  `tests/test_mpv_conf_native_fs.py`. Original finding: the `native-fs`
  line on Linux is a no-op (`--native-fs` is
  macOS-only per the mpv manual) and should be removed from the Linux
  output (`{{NATIVE_FS}}` in `config/mpv.conf.template`,
  `deploy/deployer.py:473`).

Additional findings from this update (not in the original list):

- **O4** — the window sizing helpers (and the Linux OSD/subtitle styling)
  are literal config lines inside `deploy/deployer.py`
  (`_get_linux_visual_tuning_block`), not text in a config template.
  This conflicts with SC-006 and with Principle I ("the deploy package
  … MUST NOT embed configuration literals").
- **O5** — **Fixed 2026-11-20** (`ac1b484`) — **needs Windows test**:
  `install.ps1` now creates `%LOCALAPPDATA%\mpv-config\venv` and installs
  into it, mirroring `install.sh`; the Windows `.cmd` launchers use the
  venv Python. Covered by `tests/test_install_ps1.py` (static checks; the
  pwsh parse check runs only where pwsh is installed). An older `--user`
  install is not removed automatically. Original finding: `install.ps1`
  runs `pip install --user` against the system Python. Principle III
  allows pip only inside the isolated venv.
- **O6** — `install.ps1` prints with plain `Write-Host` (no
  `-ForegroundColor`), which Principle V requires at minimum for
  PowerShell — found while fixing O5.

## User Scenarios & Testing

### User Story 1 — Installer Crash-Free Boot (Priority: P1)

> **Superseded (2026-11-19)**: the `setup.py` Rich bootstrap (scenarios 2–3) was replaced by
> `install.sh`, which always installs the project and its `pyproject.toml`
> dependencies into a venv before `mpv-config install` runs. Scenario 1
> (no `TypeError`) is covered by the `_print` default at `deploy/ui.py:129`.

A user runs `python setup.py --install` on a fresh Arch Linux machine
where Rich is not yet installed. The installer detects the environment,
bootstraps its own UI dependency, and proceeds through the full
install pipeline without crashing.

**Why this priority**: The installer currently crashes with a fatal
`TypeError` after environment detection completes. No user can
proceed past this point on any platform, making this the top blocker.

**Independent Test**: Run `python setup.py --install` on a system
where Rich is installed. The installer must complete environment
detection and display the installation plan without any `TypeError`.

**Acceptance Scenarios**:

1. **Given** a machine with Rich installed,
   **When** the user runs `python setup.py --install`,
   **Then** environment detection completes and the installation plan
   is displayed — no `TypeError` occurs at any step.

2. **Given** a machine where Rich is NOT installed,
   **When** the user runs `python setup.py --install`,
   **Then** the installer prints plain-text bootstrap messages,
   installs Rich (via system package manager or isolated venv),
   re-executes itself, and proceeds with styled output — no crash,
   no manual intervention.

3. **Given** a machine where Rich is NOT available as a system
   package AND the user has no internet,
   **Then** the installer prints a clear plain-text error explaining
   what is needed and exits gracefully — no traceback.

---

### User Story 2 — Safe Dependency Installation (Priority: P1)

> **As-built (2026-11-19)**: scenarios 1 and 4 hold. Scenario 2: the AUR package is
> `python-ffsubsync` (fallback `ffsubsync`), with a `uv tool` fallback.
> Scenario 3 is **Superseded** (Rich comes from the venv, not
> `python-rich`). Scenario 5: Ubuntu gets the yt-dlp GitHub binary, not
> apt. "`pip` is never invoked outside a venv": the `sync-deps` case was
> fixed on 2026-11-20 (O1), and the Windows `pip install --user` on
> 2026-11-20 (O5, pending a Windows test).

A user runs `python setup.py --install` on Arch Linux. The installer
installs `mpv`, `yt-dlp`, `ffmpeg`, `ffsubsync`, and `alass` via the
OS package manager (pacman/paru) — never via pip. It installs `rich`
via the system package manager first, and only falls back to a venv
if the system package is unavailable. At no point does `pip install`
run outside a virtual environment.

**Why this priority**: The current installer uses
`pip install --break-system-packages` on Arch, which violates PEP 668,
can corrupt the system Python, and conflicts with pacman. This is a
data-corruption-class bug.

**Independent Test**: Run the full install on Arch Linux and verify
that `pip` is never invoked outside a venv, and that
`--break-system-packages` never appears in any subprocess call.

**Acceptance Scenarios**:

1. **Given** a fresh Arch Linux system,
   **When** the user runs the installer,
   **Then** `yt-dlp` is installed via `pacman` (it is in the official
   repos) — not via `pip`.

2. **Given** Arch Linux where `ffsubsync` is needed,
   **When** the installer installs `ffsubsync`,
   **Then** it uses `paru -S ffsubsync` (AUR) — not `pip install`.

3. **Given** Arch Linux where `rich` is needed for deploy/ code,
   **When** the installer resolves the dependency,
   **Then** it first attempts `sudo pacman -S python-rich`. If that
   fails, it creates `~/.local/share/mpv-config/venv`, installs
   Rich inside the venv, and re-execs `setup.py` via `os.execv`.

4. **Given** any Linux distribution,
   **When** the installer runs any pip command,
   **Then** the `--break-system-packages` flag NEVER appears in the
   command arguments.

5. **Given** Ubuntu/Debian,
   **When** the installer installs `yt-dlp`,
   **Then** it uses `apt install yt-dlp` — not `pip install`.

---

### User Story 3 — mpv Window Close on KDE (Priority: P2)

> **As-built (2026-11-19)**: implemented as `CLOSE_WIN set window-minimized yes ; quit`
> plus matching `q`/`Q` bindings and `scripts/fast_close.lua` (see
> As-built). The 1-second target was not re-measured in this update.

A user clicks the X button (title bar close) on KDE Plasma 6.6.4.
mpv quits immediately, matching the instant-close behavior on Windows.

**Why this priority**: On Windows, clicking the X button quits mpv
instantly. On KDE Plasma 6.6.4, there is a delay or the process
lingers after the window is closed. This violates the cross-platform
parity principle where Windows is the UX reference target.

**Independent Test**: Open mpv on KDE Plasma 6.6.4, play any file,
click the X button. The mpv process should terminate within 1 second.

**Acceptance Scenarios**:

1. **Given** mpv is running on KDE Plasma 6.6.4 playing a video,
   **When** the user clicks the title bar X button,
   **Then** mpv terminates within 1 second and releases all resources.

2. **Given** mpv is running on KDE Plasma 6.6.4 in fullscreen mode,
   **When** the user exits fullscreen and clicks the X button,
   **Then** mpv terminates within 1 second.

3. **Given** mpv is running on Windows with the same config,
   **When** the user clicks the X button,
   **Then** the close behavior is equivalent — no regression.

---

### User Story 4 — Fullscreen Button State Sync on KDE (Priority: P2)

> **Status (2026-11-19): met by mpv's Wayland backend, no repo code needed.**
> The only change made for this story was `native-fs = no` on Linux.
> The mpv manual marks `--native-fs` as "(macOS only)", so it has no
> effect on Linux (the line was removed on 2026-11-20, O3). In a manual test on KDE
> Plasma Wayland (2026-11-19), mpv's `fullscreen` property and the uosc
> fullscreen icon both followed KWin-initiated fullscreen changes.

When the user toggles fullscreen via the uosc playback bar button,
KDE Plasma's window manager and mpv's internal fullscreen flag stay
synchronized. Conversely, when the user uses KDE's title bar
fullscreen/maximize button, mpv's fullscreen property reflects the
actual state.

**Why this priority**: The uosc fullscreen button and KDE's window
management fullscreen have desynced behavior. KDE's WM-level
fullscreen bypasses mpv's internal `fullscreen` property, causing
the uosc button icon to show the wrong state. This creates a
confusing UX that does not occur on Windows.

**Independent Test**: Toggle fullscreen via the uosc button, then
via the KDE title bar button. The uosc fullscreen icon must always
reflect the actual window state.

**Acceptance Scenarios**:

1. **Given** mpv is windowed on KDE Plasma 6.6.4,
   **When** the user clicks the uosc fullscreen button,
   **Then** mpv enters true fullscreen and the uosc button icon
   changes to the "exit fullscreen" icon.

2. **Given** mpv is in fullscreen on KDE Plasma 6.6.4,
   **When** the user uses the KDE title bar restore button
   (or a KDE keyboard shortcut) to exit fullscreen,
   **Then** the uosc fullscreen button icon reflects "enter fullscreen"
   — not stale state.

3. **Given** the same config is used on Windows,
   **When** the user toggles fullscreen via the uosc button,
   **Then** the behavior is equivalent — no regression.

---

### Edge Cases

- **Rich partially installed**: Rich is importable but corrupted
  (e.g. missing submodules). The bootstrap should detect this and
  attempt reinstallation.
  *Superseded:* there is no Rich bootstrap; Rich comes from the venv
  install, and `deploy/ui.py` only falls back to ANSI on `ImportError`.
- **No AUR helper on Arch**: If neither `paru` nor `yay` is
  installed, the installer must print a clear message for AUR-only
  packages (ffsubsync, alass) and skip them gracefully.
  *As-built:* `paru` or `yay` is used; without either, ffsubsync falls
  back to `uv tool` and alass to its GitHub release binary.
- **Venv already exists but is stale**: If
  `~/.local/share/mpv-config/venv` exists from a previous run but
  Rich is not importable inside it, the installer must recreate the
  venv — not crash.
  *Superseded:* `install.sh` recreates the venv when `bin/python` is
  missing and seeds pip (or switches to uv) when pip is missing; it does
  not test Rich specifically.
- **mpv started with `--no-border` on KDE**: Fullscreen behavior
  may differ when the title bar is hidden. Config must handle both
  `border=yes` and `border=no` window states.
- **KDE compositor disabled**: Without the compositor, some window
  management behaviors change. Config should not assume compositing.

## Requirements

### Functional Requirements

**Problem Set 1 — Installer & Dependency System**

- **FR-001**: The deploy UI module (`deploy/ui.py`) MUST have
  internally consistent method signatures — every public function
  must be callable without `TypeError` from all existing call sites
  in `setup.py`, `deploy/installer.py`, `deploy/detector.py`, and
  all other `deploy/*.py` modules.
  *As-built:* `_print(text="", **kwargs)` at `deploy/ui.py:129`;
  `setup.py` no longer exists.

- **FR-002** — *Superseded: replaced by `install.sh` installing Rich
  into the venv from `pyproject.toml`; `deploy/ui.py` falls back to ANSI
  on `ImportError`.* `setup.py` MUST catch `ImportError` on `rich` at the
  very top of its execution — before importing `deploy.ui` or any
  other module that transitively imports Rich. If Rich is missing,
  it MUST fall back to plain `print()` for bootstrap messages only.

- **FR-003** — *Superseded: no `os.execv` re-exec; `install.sh` execs
  the venv's `python -m mpv_config install` once dependencies are in
  place.* Once Rich is available (either already installed or
  freshly bootstrapped), `setup.py` MUST re-exec itself via
  `os.execv` so the Rich-enabled code path runs from the start —
  no manual user action required.

- **FR-004**: The dependency registry (`deploy/registry.py`) MUST
  classify every dependency as either Category A (CLI executable →
  OS package manager) or Category B (Python library → system package
  or isolated venv). The categories are:
  - **Category A**: `mpv`, `yt-dlp`, `ffmpeg`, `ffsubsync`, `alass`,
    `gum`, `python`
  - **Category B**: `rich` (and only `rich` at this time)
  - *Superseded (gum): `gum` is not in `SYSTEM_DEPS` and is not used by
    `install.sh`.* *As-built: Category B is now `rich`, `pycryptodomex`,
    `curl_cffi` and `yt-dlp` (`pyproject.toml`); `aria2`, `uv` and
    `autohotkey` were added to Category A.*

- **FR-005**: For Category A tools on Arch Linux:
  - `mpv`, `yt-dlp`, `ffmpeg` → `pacman`
  - `ffsubsync`, `alass` → `paru` (AUR)
  - pip MUST NOT be used for any Category A tool.
  - *As-built:* the ffsubsync AUR package is `python-ffsubsync`, with a
    `uv tool` fallback. Since 2026-11-20 `deploy/installer.py` no longer
    calls pip at all (O1).

- **FR-006**: For Category A tools on Ubuntu/Debian:
  - `yt-dlp` → `apt` (not pip)
  - All other tools → `apt` as currently configured.
  - *As-built:* yt-dlp is the GitHub `yt-dlp_linux` binary; mpv comes
    from a PPA; ffsubsync via `uv tool`; alass via GitHub binary.

- **FR-007** — *Superseded: replaced by `install.sh`, which always
  creates the venv and installs all Python dependencies into it; no
  system `python-rich` / `python3-rich` attempt and no re-exec.* For
  Category B (currently `rich` only):
  - First attempt: system package manager (`python-rich` on Arch,
    `python3-rich` on Debian).
  - Fallback: create venv at `~/.local/share/mpv-config/venv`,
    install Rich inside it, re-exec `setup.py` from within the venv.
  - `pip` is ONLY permitted inside this isolated venv.

- **FR-008**: The flag `--break-system-packages` MUST NOT appear
  anywhere in the codebase — not in `registry.py`, not in
  `installer.py`, not in any subprocess call.
  *As-built:* met in code; the only occurrence is the ban itself in
  `.specify/memory/constitution.md`.

**Problem Set 2 — mpv Window Behavior on KDE Plasma 6.6.4**

- **FR-009**: The mpv configuration MUST include settings that
  ensure clicking the WM close button terminates mpv promptly on
  KDE Plasma. Any relevant `mpv.conf` options (e.g.,
  `input-default-bindings`, `input-terminal`, window-related
  properties) MUST be evaluated and configured.
  *As-built:* `CLOSE_WIN set window-minimized yes ; quit`, `q`/`Q`
  bindings, and `scripts/fast_close.lua`.

- **FR-010**: The mpv configuration MUST address fullscreen state
  synchronization between mpv's internal `fullscreen` property and
  KDE Plasma's WM-level fullscreen. This may involve `input.conf`
  bindings, `mpv.conf` options, or Lua script hooks — all within
  the `config/` directory.
  *As-built:* met by mpv's Wayland backend (manual test 2026-11-19);
  the no-op `native-fs = no` line was removed on 2026-11-20 (O3).

- **FR-011**: Window resize/snap behavior is OUT OF SCOPE for mpv
  configuration changes. This is a KDE compositor feature, not an
  mpv feature. The spec documents this boundary explicitly. Only
  `geometry` and `autofit` options may be documented as reasonable
  helpers, but the snap preview itself cannot be controlled by mpv.
  *As-built:* the helpers are in `deploy/deployer.py` (O4).

### Key Entities

- **Dependency Registry** (`deploy/registry.py`): The single source
  of truth mapping each third-party tool to its install method per
  platform. Must be restructured to enforce Category A vs B.
  *As-built:* see the `SYSTEM_DEPS` table under As-built.

- **Bootstrap Sequence** — *Superseded: replaced by `install.sh` /
  `install.ps1` and the `mpv-config` entry point
  (`src/mpv_config/cli/main.py`).* (`setup.py` top-level): The entry point
  that must handle the Rich-not-yet-installed race condition before
  any UI-dependent code runs.

- **UI Module** (`deploy/ui.py`): The centralized output interface.
  Must have consistent method signatures across all public functions.
  `_print` is at `deploy/ui.py:129`.

- **mpv Config Templates** (`config/mpv.conf.template`,
  `config/input.conf.template`): User-facing configuration that
  must address KDE window behavior — strictly inside `config/`.

## Success Criteria

### Measurable Outcomes

- **SC-001** — *Superseded: the equivalent is running `install.sh` on
  a clean Arch system; not re-measured in this update.* Running
  `python setup.py --install` on a clean Arch
  Linux system with Rich NOT pre-installed completes successfully
  without any `TypeError`, `ImportError`, or unhandled exception.

- **SC-002**: After a full install on Arch Linux, the command
  `pip list --user` does NOT show `yt-dlp`, `ffsubsync`, or any
  other Category A tool installed via pip.
  *As-built:* the install path does not pip-install Category A tools
  (ffsubsync uses `uv tool`), and since 2026-11-20 neither does
  `sync-deps` (O1). Not re-measured.

- **SC-003**: Searching the entire codebase for
  `--break-system-packages` returns zero results.
  *As-built:* met for code; the only hit is the ban in the constitution.

- **SC-004**: On KDE Plasma 6.6.4, clicking the mpv window's X
  button terminates the process within 1 second — matching Windows
  behavior. *Not re-measured in this update.*

- **SC-005**: On KDE Plasma 6.6.4, toggling fullscreen via the uosc
  button and via the KDE title bar button both leave the uosc
  fullscreen icon in the correct state.
  *Met (manual test, KDE Plasma Wayland, 2026-11-19)* — by mpv's
  Wayland backend, with no repo code.

- **SC-006**: KDE/Wayland behaviour is expressed in config templates;
  `deploy/deployer.py` only fills template placeholders per platform
  (the same way `{{VIDEO_SYNC}}` and `{{INTERPOLATION}}` work).
  *Status:* partly met. `{{NATIVE_FS}}` is a per-platform placeholder
  fill, but the window sizing helpers are literal config text inside
  `deploy/deployer.py` (O4).

## Scope Boundary: Window Resize Snap

Window snap preview (the visual guide shown when dragging a window
near screen edges on Windows) is a **compositor/WM feature**, not an
mpv feature. On Windows, this is provided by DWM. On KDE Plasma, it
is provided by KWin.

**This is explicitly OUT OF SCOPE** for mpv configuration changes.

mpv options that can _partially_ help with initial window sizing:
- `geometry=50%x50%` — set initial window size
- `autofit-larger=90%x90%` — prevent window from exceeding screen
- `autofit-smaller=30%x30%` — prevent window from being too small

These may be documented as convenience options but MUST NOT be
presented as a solution to window snap behavior, which is entirely
controlled by the desktop environment.

## Assumptions

- The target Linux environment is KDE Plasma 6.6.4 on CachyOS
  (Arch-based) with Wayland as the display server.
- `paru` is the available AUR helper on the target Arch system.
  *As-built:* `yay` is also accepted.
- The `rich` Python library is the only Category B dependency at
  this time. If future `deploy/` code adds new Python library
  imports, they follow the same Category B rules.
  *As-built:* no longer true — see `pyproject.toml`.
- mpv version is recent enough to support all referenced config
  options (0.37+ recommended).
- The existing `uosc.conf` fullscreen button configuration
  (`fullscreen` shorthand in `controls=`) uses mpv's internal
  `fullscreen` property and may not automatically reflect WM-level
  fullscreen changes — this needs investigation during planning.
  *Resolved (2026-11-19):* mpv's Wayland backend keeps `fullscreen` in
  sync with KWin; the uosc icon follows it.
- Changes to `config/` are boundary-compliant: no automation logic
  will be placed in config files (Constitution Principle I).
