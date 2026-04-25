<!--
╔══════════════════════════════════════════════════════════════════╗
║                    SYNC IMPACT REPORT                          ║
╠══════════════════════════════════════════════════════════════════╣
║  Version change: 1.0.0 → 1.1.0                                ║
║                                                                ║
║  Modified Principles:                                          ║
║    I.   Boundary Separation → refined terminology definitions  ║
║    II.  Cross-Platform Parity → explicit UX reference target   ║
║    III. (was Shell Compat) → renumbered to IV                  ║
║    IV.  (was Aesthetic CLI) → renumbered to V                  ║
║    V.   (was Customization) → renumbered to VI                 ║
║    VI.  (was Idempotent) → renumbered to VII                   ║
║                                                                ║
║  Added Principles:                                             ║
║    III. Dependency Classification (Category A/B/C)             ║
║                                                                ║
║  Added Sections: (none)                                        ║
║  Removed Sections: (none)                                      ║
║                                                                ║
║  Templates requiring updates:                                  ║
║    ✅ plan-template.md — Constitution Check section present    ║
║    ✅ spec-template.md — Requirements section compatible       ║
║    ✅ tasks-template.md — Phase structure compatible            ║
║                                                                ║
║  Follow-up TODOs: none                                         ║
╚══════════════════════════════════════════════════════════════════╝
-->

# MPV Auto-Deploy Constitution

## Core Principles

### I. Boundary Separation (Terminology)

Two distinct categories of code exist in this project and MUST NEVER
be mixed in implementation:

- **Automation Scripts**: `deploy/*.py`, `setup.py`, `install.sh`,
  `install.ps1` — code that installs, deploys, fetches, verifies,
  or uninstalls the mpv configuration.
- **mpv Internal Scripts/Configs**: `config/*`, `config/script-opts/*`
  — user-facing media-player configuration, Lua/JS scripts, shaders,
  and option files.

Rules:

- No automation logic (Python imports, shell functions, CI helpers)
  may be placed inside `config/` or any of its subdirectories.
- No mpv configuration fragments (`mpv.conf`, `input.conf`,
  `script-opts/`, shaders, Lua/JS scripts) may be placed in the
  deploy package or root-level installer scripts.
- Template files (e.g., `mpv.conf.template`) live in `config/`
  because they *are* configuration — the deploy package reads them
  at deploy-time but MUST NOT embed configuration literals.
- Rationale: A clean boundary means the config directory can be
  audited, forked, or hand-edited without risk of breaking the
  automation layer, and vice-versa.

### II. Cross-Platform Parity

Every user-facing feature MUST work equivalently on Windows and Linux.
**Windows behavior is the UX reference target** — Linux implementations
MUST match the Windows experience unless a platform limitation makes
exact parity technically impossible, in which case the divergence MUST
be documented and produce a functionally equivalent result.

- macOS MUST be supported on a best-effort basis with graceful
  fallback.
- Path separators, config directory detection, GPU API selection,
  and shader separator patching MUST be handled by the `detector`
  and `deployer` modules at deploy-time — never hard-coded into
  config templates.
- The default `--mpv-profile windows-like` MUST produce visually and
  functionally equivalent results on both Windows and Linux.
  Platform-required divergences (e.g., `d3d11` → `vulkan`) MUST be
  documented in the profile mapping and logged at deploy-time.
- Every new script, shader, or config option MUST be tested on at
  least Windows 10+ (PowerShell 5.1+) and one Linux distro (Arch
  or Debian-family) before merge.

### III. Dependency Classification

The determining factor is **how** a package is used, not what language
it is built with. All dependencies fall into one of three categories:

#### Category A — CLI Executables

Tools invoked as terminal commands MUST ALWAYS be installed via the
OS package manager. This includes tools built in any language:

- Python-built: `yt-dlp`, `ffsubsync`
- Rust-built: `alass`
- C-built: `mpv`, `ffmpeg`, `gum`

Platform-specific rules:

- **Arch Linux**: `pacman` for official repos, `paru` for AUR.
- **Debian/Ubuntu**: `apt`.
- **Windows**: `winget`, `scoop`, or `choco` as appropriate.

**`pip` is NEVER used for Category A tools — zero exceptions.**

#### Category B — Python Libraries

Modules imported directly by `deploy/` code (i.e., `import X` appears
in a `deploy/*.py` file). Currently the ONLY member is **`rich`**.

Installation strategy (in strict order):

1. Check the OS package manager first
   (`python-rich` on Arch via `pacman`, `python3-rich` on Debian
   via `apt`).
2. If not available as a system package: create a virtual environment
   at `~/.local/share/mpv-config/venv`, install inside the venv,
   then re-exec `setup.py` via `os.execv`.

**`pip` is ONLY permitted inside the isolated venv — never system-wide.**
**`--break-system-packages` is BANNED project-wide — zero exceptions.**

#### Category C — Bootstrap Race Condition

Rich is needed for UI rendering but may not be installed when
`setup.py` first runs. The bootstrap sequence MUST be:

1. `setup.py` catches `ImportError` on `rich` BEFORE any UI code
   executes.
2. Falls back to plain `print()` for bootstrap messages only
   (installing Rich, creating venv).
3. Once Rich is confirmed available, re-exec `setup.py` via
   `os.execv` automatically — no manual steps from the user.

Rationale: System Python integrity is non-negotiable. External
tools belong to the OS; library dependencies belong in isolation.

### IV. Shell Compatibility

All Bash scripts MUST use the `#!/usr/bin/env bash` shebang and MUST
NOT rely on Bash-specific features above version 4.0 unless gated
behind a version check.

- Scripts MUST begin with `set -euo pipefail`.
- When a user's shell is **not** Bash (e.g., fish, zsh, nushell),
  installer output MUST detect `$SHELL` or `$FISH_VERSION` and print
  the shell-specific equivalent command (e.g., `set -Ux PATH ...`
  for fish, `export PATH=...` for zsh/bash). Do NOT assume every
  user sources `~/.bashrc`.
- PowerShell scripts MUST target PowerShell 5.1+ and MUST set
  `$ErrorActionPreference = "Stop"`. They MUST NOT use Unix-style
  aliases (`ls`, `cat`, `rm`) — use native cmdlets instead
  (`Get-ChildItem`, `Get-Content`, `Remove-Item`).
- Rationale: Users run the one-liner in their default shell; the
  installer must adapt to them, not the other way around.

### V. Aesthetic CLI UX

All user-facing CLI output — Bash, PowerShell, and Python — MUST
use styled, structured terminal UI. Raw `echo`, raw `Write-Host`
without `-ForegroundColor`, and unstyled `print()` are PROHIBITED
in user-facing paths.

- **Python** (`deploy/` package): MUST route all output through
  `deploy/ui.py`, which uses [Rich](https://github.com/Textualize/rich)
  as the primary renderer with an ANSI fallback when Rich is
  unavailable. Direct `print()` calls in any module other than
  `ui.py` are forbidden.
- **Bash** (`install.sh`): MUST use
  [Gum](https://github.com/charmbracelet/gum) for spinners,
  confirmations, and styled text via the `_styled_echo`,
  `_gum_spin`, and `_confirm` wrappers. When Gum is not installed,
  the wrappers MUST fall back to ANSI-colored output — never to
  bare `echo`.
- **PowerShell** (`install.ps1`): MUST use `Write-Host` with
  `-ForegroundColor` at minimum. For future enhancements, prefer
  structured output via
  [PSWriteColor](https://github.com/EvotecIT/PSWriteColor) or
  similar modules if available.
- Error messages MUST be displayed inside a Rich `Panel` (Python),
  a Gum `style --border` block (Bash), or a colored box drawn with
  `Write-Host` (PowerShell).
- When implementing any UI component, the `@[ui-ux-pro-max]` skill
  MUST be consulted for design guidance and aesthetic standards.
- Rationale: First impressions matter. A polished CLI builds user
  trust and makes error diagnosis faster.

### VI. User Customization Sovereignty

The deploy system MUST NEVER overwrite, truncate, or silently discard
user customizations without explicit, interactive confirmation.

- Before overwriting `mpv.conf` or `input.conf`, the deployer MUST
  create a timestamped backup under the config directory and log
  the backup path to the audit log.
- User-added files inside the config directory that are not managed
  by this tool MUST be preserved during deploy, update, and
  rollback operations.
- Template patching MUST be additive: platform-specific values are
  injected into clearly marked sections; user sections outside
  those markers are left untouched.
- The `--dry-run` flag MUST be available for every destructive
  operation (install, update, rollback, uninstall) so users can
  preview changes before committing.

### VII. Idempotent & Safe Operations

Every operation exposed by `setup.py` MUST be safely re-runnable.
Running the same command twice with the same inputs MUST produce
the same end state without errors or data loss.

- `--install` on an already-installed system MUST detect the existing
  deployment, back up the current state, and re-deploy cleanly.
- `--update` MUST be a subset of `--install` — it re-fetches scripts
  and shaders but MUST NOT re-run dependency installation or
  overwrite config files.
- `--uninstall` without `--purge-config` MUST remove only files
  deployed by this tool, identified via the `.deploy.lock.json`
  manifest and the `.audit-log.json` provenance record.
- Rationale: Users will inevitably run the installer multiple times.
  Each run must be a safe, predictable operation.

## Platform & Shell Matrix

The following matrix defines the supported environments. Any new
feature or fix MUST be validated against this matrix before merge.

| Dimension       | Tier 1 (MUST work)            | Tier 2 (SHOULD work)      |
|-----------------|-------------------------------|---------------------------|
| OS              | Windows 10/11, Arch Linux     | Ubuntu/Debian, macOS      |
| Shell (Linux)   | bash 4.0+                     | zsh, fish                 |
| Shell (Windows) | PowerShell 5.1+               | pwsh 7+                   |
| Python          | 3.8+                          | 3.12+                     |
| Terminal        | Windows Terminal, most VTEs   | ConHost, TTY              |

Shell-specific PATH instructions MUST be printed for fish (`set -Ux`)
and zsh (`export` in `~/.zshrc`) when the launcher is created.

## Development Workflow

- **Branching**: Feature work MUST happen on a branch named
  `NNN-short-description` (e.g., `001-add-sponsorblock`).
- **Commits**: Follow Conventional Commits
  (`feat:`, `fix:`, `docs:`, `chore:`).
- **Pre-merge checklist**:
  1. `python setup.py --dry-run` exits 0 on both Windows and Linux.
  2. `python setup.py --verify` reports 0 failures.
  3. All Bash scripts pass `shellcheck` with no errors.
  4. All Python code passes the project's configured linter.
- **Audit log**: Every deploy session MUST be recorded in
  `.audit-log.json` so that uninstall and rollback can reason about
  provenance.

## Governance

- This constitution supersedes all ad-hoc conventions. If a pull
  request violates a principle, the reviewer MUST cite the specific
  principle and request a fix before merge.
- **Amendment procedure**: Any change to this constitution MUST be
  proposed as a diff, reviewed, and merged via the standard branching
  workflow. The version MUST be bumped according to semver rules
  (MAJOR for principle removals/redefinitions, MINOR for additions,
  PATCH for wording clarifications).
- **Compliance review**: At least once per feature branch, the
  implementation plan's "Constitution Check" section MUST enumerate
  each principle and confirm compliance or document a justified
  exception.

**Version**: 1.1.0 | **Ratified**: 2026-04-25 | **Last Amended**: 2026-04-25
