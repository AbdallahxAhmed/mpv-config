# Feature Specification: MPV Auto-Deploy Automation

**Feature Branch**: `001-mpv-automation`
**Created**: 2026-04-18
**Status**: Draft
**Input**: User description: "Automate mpv installation: OS detection, interactive UI menu, config deployment to correct paths without conflicts"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — One-Command Full Install (Priority: P1)

A user who has never configured mpv before runs a single command
(`curl … | bash` on Linux or `irm … | iex` on Windows). The system
automatically detects their operating system, GPU vendor, display
server, and installed tools. It then presents a clear, visually
polished summary of what it found and what it intends to do. After
the user confirms, the system installs any missing dependencies,
downloads all scripts and shaders from their upstream GitHub
repositories, patches configuration templates for the detected
platform, and deploys everything to the correct mpv config directory.
Finally, it runs a full verification suite and presents a
color-coded summary.

**Why this priority**: This is the core value proposition — a
zero-knowledge user should go from nothing to a fully working,
optimized mpv setup in one step.

**Independent Test**: Can be fully tested by running the install on
a clean machine (or container) and verifying that mpv launches with
the deployed config and all scripts load without errors.

**Acceptance Scenarios**:

1. **Given** a clean Linux machine with no mpv config,
   **When** the user runs `curl -fsSL … | bash`,
   **Then** the system detects OS/GPU/display, installs deps,
   fetches 9 scripts + Anime4K shaders, patches configs, deploys
   everything to `~/.config/mpv/`, and reports all verification
   checks as passed.

2. **Given** a clean Windows machine with no mpv config,
   **When** the user runs `irm … | iex`,
   **Then** the system detects OS/GPU, installs deps via winget,
   fetches scripts/shaders, patches configs with Windows-specific
   values (`;` separator, `d3d11` GPU API), deploys to
   `%APPDATA%/mpv/`, and reports all checks as passed.

3. **Given** a machine where mpv is already installed but config
   is missing,
   **When** the user runs the install command,
   **Then** the system detects mpv as "already installed", skips
   its installation, but still installs other missing deps,
   fetches scripts, and deploys the config.

4. **Given** a machine where an existing mpv config exists,
   **When** the user runs the install command,
   **Then** the system creates a timestamped backup of the existing
   config before overwriting anything, and the user is informed of
   the backup location.

---

### User Story 2 — Interactive Menu Experience (Priority: P2)

A returning user who has already installed via the bootstrap script
launches the tool again (via the `mpv-config` launcher command or
`python setup.py --interactive`). Instead of repeating the full
install, they see a visually attractive, numbered menu offering:
full install, update scripts only, rollback to backup, verify
installation, show status, and uninstall. Each option has clear
descriptions. The user selects by number, and the tool executes the
chosen action with the same detection → plan → confirm → execute →
verify flow.

**Why this priority**: Returning users need a guided way to manage
their deployment without memorizing CLI flags.

**Independent Test**: Can be tested by running the interactive mode
and verifying that all menu options are displayed, selectable, and
each triggers the correct underlying operation.

**Acceptance Scenarios**:

1. **Given** a user with an existing deployment,
   **When** they run `mpv-config` without flags,
   **Then** they see a numbered menu with at least 7 options
   (install, update, rollback-latest, rollback-specific, verify,
   status, uninstall, full-remove), each clearly labeled.

2. **Given** a user selects "Update scripts/shaders" from the menu,
   **When** the update runs,
   **Then** only scripts, shaders, and fonts are re-fetched and
   deployed; user config files (mpv.conf, input.conf, script-opts)
   are NOT overwritten.

3. **Given** a user selects "Rollback (latest backup)",
   **When** the rollback executes,
   **Then** the current config is saved as a pre-rollback snapshot,
   the latest backup is restored to the config directory, and both
   paths are displayed to the user.

---

### User Story 3 — OS Detection & Environment Profiling (Priority: P1)

The system automatically detects the user's operating environment
without any manual input. This includes: operating system (Windows,
Linux, macOS), Linux distribution (Arch, Ubuntu/Debian, Fedora),
display server (Wayland vs X11), GPU vendor (NVIDIA, AMD, Intel),
available package manager (winget, pacman, apt, dnf, brew), AUR
helper if on Arch (paru/yay), Python/pip availability, and the
correct mpv config directory for the platform.

**Why this priority**: Detection drives every downstream decision
(which package manager to use, which GPU API to set, which shader
separator to write). Without accurate detection, nothing else works.

**Independent Test**: Can be tested by running the detector module
on different OSes and verifying the returned `Environment` object
has correct values for each field.

**Acceptance Scenarios**:

1. **Given** an Arch Linux machine with NVIDIA GPU on Wayland,
   **When** detection runs,
   **Then** the Environment reports: os=linux, distro=arch,
   display=wayland, gpu_vendor=nvidia, pkg_manager=pacman,
   config_dir=~/.config/mpv.

2. **Given** a Windows 11 machine with an AMD GPU,
   **When** detection runs,
   **Then** the Environment reports: os=windows, gpu_vendor=amd,
   pkg_manager=winget, config_dir=%APPDATA%/mpv.

3. **Given** a machine where no GPU can be detected (e.g. VM),
   **When** detection runs,
   **Then** gpu_vendor is empty, and the system falls back to
   safe defaults (gpu_api=auto, hwdec=auto) instead of crashing.

---

### User Story 4 — Config Deployment Without Conflicts (Priority: P1)

The system deploys configuration files to the correct mpv config
directory for the detected platform. It handles: static config files
(script-opts like uosc.conf, SmartSkip.conf), template-patched files
(mpv.conf from mpv.conf.template, input.conf, autosubsync.conf),
fetched scripts (Lua files to scripts/), fetched shaders (.glsl
files to shaders/), and fonts. Template patching replaces platform
placeholders (GPU API, hardware decoding, shader separator, GPU
context) with detected values. No file conflicts occur because the
deploy always backs up first, then overwrites cleanly.

**Why this priority**: This is the physical outcome of the whole
system — files must end up in the right place with the right
content, or mpv will not work properly.

**Independent Test**: Can be tested by running deploy on a staging
directory and verifying that all output files exist, have no
unresolved `{{placeholders}}`, and match expected values for the
platform.

**Acceptance Scenarios**:

1. **Given** detection found Linux/NVIDIA/Wayland with
   windows-like profile,
   **When** config deployment runs,
   **Then** mpv.conf contains gpu-api=vulkan (d3d11→vulkan
   fallback), hwdec=nvdec (NVIDIA optimization), and input.conf
   uses `:` as shader separator.

2. **Given** detection found Windows with default profile,
   **When** config deployment runs,
   **Then** mpv.conf contains gpu-api=d3d11, hwdec=auto-copy,
   and input.conf uses `;` as shader separator.

3. **Given** the config directory already has user-modified files,
   **When** deployment runs,
   **Then** the entire existing directory is backed up to
   `<config_dir>.backup.<YYYYMMDD_HHMMSS>` before any files are
   touched.

4. **Given** deployment completes on Linux,
   **When** the user opens a .conf or .lua file,
   **Then** all files have LF line endings (CRLF→LF normalization
   was applied).

---

### User Story 5 — Safe Uninstall & Rollback (Priority: P3)

A user decides to remove the deployed configuration. They run the
uninstall command. The system consults the audit log to determine
which system packages were installed by this tool vs. already
present before. Only packages installed by this tool are offered
for removal. Pre-existing packages are never touched. The user can
also rollback to any previous backup at any time.

**Why this priority**: Safety and reversibility are essential for
user trust, but this is an exit path, not the primary flow.

**Independent Test**: Can be tested by performing an install,
then an uninstall, and verifying: deployed files are removed,
pre-existing packages remain, audit log is preserved during
partial uninstall, backups can be restored.

**Acceptance Scenarios**:

1. **Given** mpv was installed before this tool, and ffsubsync
   was installed by this tool,
   **When** the user runs uninstall with --remove-deps,
   **Then** ffsubsync is removed, but mpv is skipped with
   "pre-existing, not removed" message.

2. **Given** no audit log exists (first-ever run then immediate
   uninstall),
   **When** the user runs uninstall with --remove-deps,
   **Then** all packages are assumed pre-existing and none are
   auto-removed, with a clear warning message.

---

### Edge Cases

- What happens when the internet connection drops mid-fetch?
  → The fetch operation retries with exponential backoff (3
  attempts), then reports the specific script as failed while
  continuing with others.

- What happens when a GitHub API rate limit is hit?
  → The system detects HTTP 403, waits with exponential backoff,
  and retries up to 3 times before failing gracefully.

- What happens when the user has no package manager detected?
  → Dependencies are reported as "must be installed manually"
  with links to download pages.

- What happens when a backup directory already exists with the
  same timestamp?
  → The backup name includes seconds precision
  (YYYYMMDD_HHMMSS), making collisions practically impossible.

- What happens when the user runs install on a read-only
  filesystem?
  → The backup/deploy step fails with a clear error message,
  and no partial state is left.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST detect the operating system (Windows,
  Linux, macOS) and resolve the correct mpv config directory
  automatically.

- **FR-002**: System MUST detect the Linux distribution family
  (Arch-based, Debian/Ubuntu-based, Fedora-based) and select
  the appropriate package manager.

- **FR-003**: System MUST detect the GPU vendor (NVIDIA, AMD,
  Intel) and apply optimal hardware decoding and GPU API
  settings.

- **FR-004**: System MUST detect the display server on Linux
  (Wayland vs X11) and configure GPU context accordingly.

- **FR-005**: System MUST install missing system dependencies
  (mpv, yt-dlp, ffmpeg, python) using the detected package
  manager, with user confirmation before any installation.

- **FR-006**: System MUST download scripts and shaders from
  their upstream GitHub repositories using two strategies:
  individual raw file downloads, and zip asset extraction from
  GitHub Releases.

- **FR-007**: System MUST patch configuration templates by
  replacing platform placeholders (GPU API, hardware decoder,
  shader separator, GPU context, tool paths) with values derived
  from detection.

- **FR-008**: System MUST deploy all files (scripts, shaders,
  fonts, configs, script-opts) to the correct mpv config
  directory.

- **FR-009**: System MUST create a timestamped backup of any
  existing mpv config directory before overwriting.

- **FR-010**: System MUST normalize line endings (CRLF→LF) for
  all deployed text files on non-Windows systems.

- **FR-011**: System MUST run a comprehensive post-deployment
  verification suite checking: binary availability, config file
  presence, script directory contents, shader count, font
  presence, unresolved placeholders, and mpv launch test.

- **FR-012**: System MUST present a pre-flight action plan
  showing every planned operation (install, fetch, backup,
  deploy) and require explicit user approval before executing.

- **FR-013**: System MUST maintain an audit log recording every
  package install, file operation, and backup, including whether
  each package was pre-existing.

- **FR-014**: System MUST support a dry-run mode that previews
  all planned actions without making any changes.

- **FR-015**: System MUST provide an interactive menu for
  returning users with options for: install, update, rollback,
  verify, status, and uninstall.

- **FR-016**: System MUST support updating scripts/shaders
  without touching user config files (mpv.conf, input.conf,
  script-opts).

- **FR-017**: System MUST support rollback to the latest or a
  specific backup, preserving the current config as a
  pre-rollback snapshot.

- **FR-018**: System MUST support safe uninstall that only
  removes packages installed by this tool, never pre-existing
  packages.

### Key Entities

- **Environment**: Represents the detected machine state (OS,
  distro, GPU, display, package manager, config directory,
  installed dependencies).

- **Script Entry**: Represents a third-party mpv script with
  its upstream source location, fetch strategy, file mapping,
  config file, and dependency chain.

- **Shader Entry**: Represents a shader pack (Anime4K) with
  its GitHub Release source, version pin, and file extensions.

- **System Dependency**: Represents an installable package
  (mpv, yt-dlp, ffmpeg, ffsubsync) with per-platform install
  methods and verification commands.

- **Audit Log / Session**: Represents a single tool invocation
  (install, update, uninstall, rollback) recording all package
  and file operations for safe rollback.

- **Plan Entry**: Represents a single planned action (install,
  fetch, backup, deploy, remove, skip) before execution.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A first-time user can go from zero to a fully
  working mpv setup in under 5 minutes on a reasonably fast
  internet connection.

- **SC-002**: The system correctly detects OS, GPU, and display
  server on 100% of supported platforms (Windows 10+, Arch,
  Ubuntu/Debian, Fedora, macOS).

- **SC-003**: All 9 scripts and Anime4K shaders are fetched
  and deployed successfully with zero unresolved placeholders
  in all generated config files.

- **SC-004**: Post-deployment verification passes 100% of
  checks (20+ automated checks) on a clean install.

- **SC-005**: Rolling back a deployment restores the previous
  state with no data loss and no orphaned files.

- **SC-006**: Uninstalling with --remove-deps never removes a
  package that existed before this tool was run.

- **SC-007**: The install experience is visually polished with
  color-coded output, progress indicators, and structured
  summary panels on both Windows and Linux terminals.

- **SC-008**: Windows and Linux installations produce identical
  functional results (same scripts, same mpv behavior, same
  user experience), differing only in platform-required values
  (paths, separators, GPU API).

## Assumptions

- Users have a stable internet connection to reach GitHub
  (api.github.com and raw.githubusercontent.com).

- Python 3.8+ is either already installed or can be installed
  via the platform's package manager.

- Users have sufficient permissions to write to their mpv config
  directory (~/.config/mpv on Linux, %APPDATA%/mpv on Windows).

- The `install.sh` bootstrap script is run via `curl | bash`,
  which means Bash is available for the bootstrap phase, even
  on systems where fish is the default shell.

- macOS is a secondary platform: the system MUST NOT break on
  macOS but MAY have reduced functionality (e.g., no AUR helper,
  limited GPU detection).

- No external Python packages are required for core functionality
  except Rich (for deploy/ UI per Constitution Principle IV).
