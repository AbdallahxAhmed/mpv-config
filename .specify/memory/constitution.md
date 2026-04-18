<!--
  ╔══════════════════════════════════════════════════════════════╗
  ║                    SYNC IMPACT REPORT                       ║
  ╠══════════════════════════════════════════════════════════════╣
  ║ Version change: N/A (template) → 1.0.0                     ║
  ║                                                             ║
  ║ Added principles:                                           ║
  ║   • I. Terminology Separation (NEW)                         ║
  ║   • II. OS Parity (NEW)                                     ║
  ║   • III. Fish Environment (NEW)                             ║
  ║   • IV. CLI Aesthetics (NEW)                                ║
  ║                                                             ║
  ║ Added sections:                                             ║
  ║   • Technology Constraints                                  ║
  ║   • Development Workflow                                    ║
  ║   • Governance                                              ║
  ║                                                             ║
  ║ Removed sections: None (fresh constitution)                 ║
  ║                                                             ║
  ║ Templates requiring updates:                                ║
  ║   • .specify/templates/plan-template.md       ✅ reviewed   ║
  ║     Constitution Check section aligns with 4 principles     ║
  ║   • .specify/templates/spec-template.md       ✅ reviewed   ║
  ║     No conflicts with new constraints                       ║
  ║   • .specify/templates/tasks-template.md      ✅ reviewed   ║
  ║     Phase structure compatible; no principle-driven          ║
  ║     task types need adding at template level                 ║
  ║                                                             ║
  ║ Follow-up TODOs: None                                       ║
  ╚══════════════════════════════════════════════════════════════╝
-->

# mpv-config Constitution

## Core Principles

### I. Terminology Separation

The project maintains a **strict, non-negotiable boundary** between two
categories of scripts. Violating this boundary—whether in code, naming,
documentation, or directory placement—is a constitutional infringement.

- **Automation Scripts**: Files under `deploy/` (e.g., `deploy/ui.py`,
  `deploy/deployer.py`) and root-level bootstrap scripts (`install.sh`,
  `install.ps1`, `setup.py`). These orchestrate installation, deployment,
  verification, and user interaction. They are **our** tooling.
- **mpv Internal Scripts**: Files under `config/script-opts/` (e.g.,
  `uosc.conf`, `SmartSkip.conf`) and any Lua/JS scripts fetched by
  `deploy/fetcher.py` for the mpv player. These are **third-party
  extensions** consumed by mpv at runtime.

**Rules**:

1. Automation Scripts MUST NOT import, invoke, or depend on mpv Internal
   Scripts at build time or deploy time.
2. mpv Internal Scripts MUST NOT reference or assume the existence of
   Automation Scripts.
3. Directory boundaries MUST be enforced: automation logic lives in
   `deploy/` and project root; mpv configuration lives in `config/`.
4. Naming conventions MUST reflect the category: automation modules use
   Python/Bash naming; mpv configs use mpv's expected naming (`.conf`,
   `.lua`, `.js`).
5. Documentation MUST always qualify which category a script belongs to
   when referencing it.

### II. OS Parity

All code MUST work on **Windows** and **Linux** with equal reliability
and performance. macOS is a secondary target that MUST NOT break but
MAY have reduced functionality where platform APIs differ.

**Rules**:

1. Every code path that touches the filesystem, environment variables,
   process spawning, or path construction MUST be tested on both Windows
   and Linux.
2. Windows performance MUST NOT be sacrificed for Linux convenience.
   If a cross-platform abstraction introduces measurable overhead on
   Windows, a platform-specific fast path MUST be implemented.
3. Platform-specific code MUST be isolated behind detector/registry
   abstractions (see `deploy/detector.py`, `deploy/registry.py`),
   never inlined with `if os.name` scattered through business logic.
4. Path separators, config directories, shader separators (`;` vs `:`),
   and GPU API selection MUST be resolved through the existing registry
   system, not hardcoded.
5. All install scripts (`install.sh` for Linux, `install.ps1` for
   Windows) MUST achieve feature parity: any capability added to one
   MUST be mirrored in the other within the same release.

### III. Fish Environment

The maintainer's default shell is **fish**. All shell scripts MUST
respect this constraint.

**Rules**:

1. Every Bash script (e.g., `install.sh`) MUST begin with an explicit
   shebang: `#!/usr/bin/env bash`.
2. Scripts MUST NOT rely on Bash being the login shell, the default
   shell, or being sourced from `.bashrc`/`.bash_profile`.
3. Any shell script that generates commands for the user to run
   (e.g., `eval` blocks, `source` instructions) MUST provide
   fish-compatible alternatives or use POSIX-portable constructs.
4. CI/CD pipelines and Makefiles MUST explicitly specify `bash` as
   the shell executor and MUST NOT assume `sh` equals `bash`.
5. No script may use Bash-specific syntax (e.g., `[[ ]]`, `(( ))`,
   process substitution) without the `#!/usr/bin/env bash` shebang
   being present.

### IV. CLI Aesthetics

Boring, plain-text terminal interfaces are **prohibited**. Every
user-facing CLI interaction MUST deliver a polished, visually rich
experience.

**Rules**:

1. **Python scripts** in `deploy/` MUST use the **Rich** library for
   all terminal output:
   - Spinners for long-running operations (downloads, installs).
   - Panels for grouped information (system detection results,
     verification summaries).
   - Tables for structured data (script versions, status checks).
   - Progress bars for multi-step operations.
   - Color-coded status indicators (✓ green, ✗ red, ⚠ yellow).
2. **Bash scripts** (`install.sh` and any future `.sh` files) MUST
   use **Gum** (charmbracelet/gum) for interactive elements:
   - `gum spin` for spinners.
   - `gum choose` / `gum confirm` for user prompts.
   - `gum style` for styled output panels.
   - Graceful fallback to plain `echo` if Gum is not installed,
     but Gum SHOULD be auto-installed when possible.
3. Raw `print()` in Python and bare `echo` in Bash are permitted
   ONLY for debug/logging output that is not user-facing.
4. Error messages MUST be visually distinct (red panel/border) and
   include actionable guidance.
5. The UI/UX skill (`ui-ux-pro-max`) MUST be consulted when designing
   new CLI flows to ensure exceptional user experience.

## Technology Constraints

- **Python**: 3.8+ minimum. No external packages for core functionality
  (the `rich` library is the sole permitted UI dependency for `deploy/`
  scripts).
- **Bash**: POSIX-compatible logic preferred; Bash-specific features
  allowed only with explicit `#!/usr/bin/env bash` shebang.
- **PowerShell**: 5.1+ for Windows scripts (`install.ps1`).
- **mpv Scripts**: Lua 5.1 (mpv's embedded interpreter) or JavaScript
  (mpv's JS backend). Configuration files use mpv's `.conf` format.
- **Dependencies**: External tool dependencies (mpv, yt-dlp, ffmpeg,
  ffsubsync, gum) MUST be auto-detected and auto-installed where
  possible, with clear error messages when manual intervention is
  required.

## Development Workflow

- **Branch strategy**: Feature branches from `main`. Constitution
  changes require their own dedicated branch.
- **Commit discipline**: Each commit MUST reference which Principle
  it touches if it modifies constrained areas (e.g.,
  `fix(parity): normalize paths on Windows [Principle II]`).
- **Code review gates**: Any PR that adds platform-specific code MUST
  include evidence of testing on both Windows and Linux (screenshots,
  CI logs, or manual verification notes).
- **Template patching**: Changes to `config/*.template` files MUST be
  validated against both `windows-like` and `native` mpv profiles.

## Governance

This Constitution is the supreme governing document of the mpv-config
project. All development practices, code reviews, and architectural
decisions MUST comply with the principles defined herein.

- **Supremacy**: The Constitution supersedes all other guidelines,
  conventions, or ad-hoc decisions. In case of conflict, the
  Constitution wins.
- **Amendments**: Any change to this document MUST follow semantic
  versioning (MAJOR for principle removal/redefinition, MINOR for
  new principles/sections, PATCH for clarifications). Amendments
  MUST be documented in the Sync Impact Report header.
- **Compliance review**: Every spec, plan, and task list generated
  by the Spec-Kit workflow MUST include a Constitution Check section
  validating adherence to all four principles.
- **Enforcement**: Violations discovered in code review MUST be
  resolved before merge. No exception, no "we'll fix it later."
- **Runtime guidance**: Refer to `AGENTS.md` and the current plan
  for runtime development guidance.

**Version**: 1.0.0 | **Ratified**: 2026-04-18 | **Last Amended**: 2026-04-18
