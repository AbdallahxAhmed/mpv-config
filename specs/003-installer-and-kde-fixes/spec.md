# Feature Specification: Installer & KDE Fixes

**Feature Branch**: `002-installer-and-kde-fixes`
**Created**: 2026-04-25
**Status**: Draft
**Input**: Fix installer crashes, dependency classification violations, and KDE Plasma 6.6.4 window behavior issues

## User Scenarios & Testing

### User Story 1 — Installer Crash-Free Boot (Priority: P1)

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
- **No AUR helper on Arch**: If neither `paru` nor `yay` is
  installed, the installer must print a clear message for AUR-only
  packages (ffsubsync, alass) and skip them gracefully.
- **Venv already exists but is stale**: If
  `~/.local/share/mpv-config/venv` exists from a previous run but
  Rich is not importable inside it, the installer must recreate the
  venv — not crash.
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

- **FR-002**: `setup.py` MUST catch `ImportError` on `rich` at the
  very top of its execution — before importing `deploy.ui` or any
  other module that transitively imports Rich. If Rich is missing,
  it MUST fall back to plain `print()` for bootstrap messages only.

- **FR-003**: Once Rich is available (either already installed or
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

- **FR-005**: For Category A tools on Arch Linux:
  - `mpv`, `yt-dlp`, `ffmpeg` → `pacman`
  - `ffsubsync`, `alass` → `paru` (AUR)
  - pip MUST NOT be used for any Category A tool.

- **FR-006**: For Category A tools on Ubuntu/Debian:
  - `yt-dlp` → `apt` (not pip)
  - All other tools → `apt` as currently configured.

- **FR-007**: For Category B (currently `rich` only):
  - First attempt: system package manager (`python-rich` on Arch,
    `python3-rich` on Debian).
  - Fallback: create venv at `~/.local/share/mpv-config/venv`,
    install Rich inside it, re-exec `setup.py` from within the venv.
  - `pip` is ONLY permitted inside this isolated venv.

- **FR-008**: The flag `--break-system-packages` MUST NOT appear
  anywhere in the codebase — not in `registry.py`, not in
  `installer.py`, not in any subprocess call.

**Problem Set 2 — mpv Window Behavior on KDE Plasma 6.6.4**

- **FR-009**: The mpv configuration MUST include settings that
  ensure clicking the WM close button terminates mpv promptly on
  KDE Plasma. Any relevant `mpv.conf` options (e.g.,
  `input-default-bindings`, `input-terminal`, window-related
  properties) MUST be evaluated and configured.

- **FR-010**: The mpv configuration MUST address fullscreen state
  synchronization between mpv's internal `fullscreen` property and
  KDE Plasma's WM-level fullscreen. This may involve `input.conf`
  bindings, `mpv.conf` options, or Lua script hooks — all within
  the `config/` directory.

- **FR-011**: Window resize/snap behavior is OUT OF SCOPE for mpv
  configuration changes. This is a KDE compositor feature, not an
  mpv feature. The spec documents this boundary explicitly. Only
  `geometry` and `autofit` options may be documented as reasonable
  helpers, but the snap preview itself cannot be controlled by mpv.

### Key Entities

- **Dependency Registry** (`deploy/registry.py`): The single source
  of truth mapping each third-party tool to its install method per
  platform. Must be restructured to enforce Category A vs B.

- **Bootstrap Sequence** (`setup.py` top-level): The entry point
  that must handle the Rich-not-yet-installed race condition before
  any UI-dependent code runs.

- **UI Module** (`deploy/ui.py`): The centralized output interface.
  Must have consistent method signatures across all public functions.

- **mpv Config Templates** (`config/mpv.conf.template`,
  `config/input.conf.template`): User-facing configuration that
  must address KDE window behavior — strictly inside `config/`.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Running `python setup.py --install` on a clean Arch
  Linux system with Rich NOT pre-installed completes successfully
  without any `TypeError`, `ImportError`, or unhandled exception.

- **SC-002**: After a full install on Arch Linux, the command
  `pip list --user` does NOT show `yt-dlp`, `ffsubsync`, or any
  other Category A tool installed via pip.

- **SC-003**: Searching the entire codebase for
  `--break-system-packages` returns zero results.

- **SC-004**: On KDE Plasma 6.6.4, clicking the mpv window's X
  button terminates the process within 1 second — matching Windows
  behavior.

- **SC-005**: On KDE Plasma 6.6.4, toggling fullscreen via the uosc
  button and via the KDE title bar button both leave the uosc
  fullscreen icon in the correct state.

- **SC-006**: All changes for Problem Set 2 reside exclusively in
  `config/` — zero modifications to `deploy/` or root-level scripts
  for KDE window fixes.

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
- The `rich` Python library is the only Category B dependency at
  this time. If future `deploy/` code adds new Python library
  imports, they follow the same Category B rules.
- mpv version is recent enough to support all referenced config
  options (0.37+ recommended).
- The existing `uosc.conf` fullscreen button configuration
  (`fullscreen` shorthand in `controls=`) uses mpv's internal
  `fullscreen` property and may not automatically reflect WM-level
  fullscreen changes — this needs investigation during planning.
- Changes to `config/` are boundary-compliant: no automation logic
  will be placed in config files (Constitution Principle I).
