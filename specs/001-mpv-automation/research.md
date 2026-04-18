# Research: MPV Auto-Deploy Automation

**Feature**: 001-mpv-automation
**Date**: 2026-04-18

## R1: Rich Library Integration Strategy

### Decision
Migrate `deploy/ui.py` from raw ANSI escape codes to Rich, preserving
the existing public API (`ui.banner()`, `ui.success()`, etc.) so all
callers require zero changes.

### Rationale
Constitution Principle IV mandates Rich for Python terminal output.
The current `ui.py` is already a clean facade — swapping internals
from raw ANSI to Rich is a drop-in replacement at the implementation
layer only.

### Alternatives Considered

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| Keep raw ANSI | Zero dependencies, already works | Violates Constitution Principle IV | ❌ Rejected |
| Rich (selected) | Spinners, Tables, Panels, Progress, auto-color detection | Adds one dependency (permitted by Constitution) | ✅ Selected |
| Textual (full TUI) | Full terminal UI framework | Overkill for sequential CLI; adds complexity | ❌ Rejected |
| Click + Rich | CLI framework + UI | Click is unnecessary (argparse sufficient) | ❌ Rejected |

### Implementation Notes
- Rich is imported with try/except fallback to ANSI-based output.
- This ensures `install.sh` bootstrap phase (before pip install) still
  produces readable output via the fallback path.
- Rich auto-detects terminal width, color support, and Unicode
  capability — replacing the manual `_supports_color()` and
  `_supports_unicode()` detection.

---

## R2: Symlink vs Copy Deployment Strategy

### Decision
Linux/macOS: symlinks for script/shader/font directories.
Windows: full copy for everything.
Config files are always full copies on all platforms (they are patched).

### Rationale
Symlinks on Linux allow instant updates (re-fetch to install dir,
symlinks automatically point to new content). Windows symlinks require
Developer Mode or elevation, making them unreliable for a
zero-knowledge user.

### Alternatives Considered

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| Symlinks everywhere | Instant update on all platforms | Fails on Windows without Developer Mode | ❌ Rejected |
| Copy everywhere | Simple, universally works | Loses instant-update benefit on Linux | ❌ Rejected |
| Symlinks Linux + Copy Windows | Best of both worlds | Two code paths to maintain | ✅ Selected |
| NTFS Junctions (Windows) | Directory-level symlink-like behavior | Only directories, breaks on non-NTFS, confusing behavior with deletion | ❌ Rejected |
| Hardlinks | No elevated permissions needed | Cannot link directories, breaks on cross-device | ❌ Rejected |

### Implementation Notes
- A persistent `deployed/` directory under the install dir replaces
  the ephemeral `.staging/` directory.
- `deployer.py` detects existing symlinks and handles replacement
  gracefully.
- Backup (`shutil.copytree`) follows symlinks by default, producing
  real-file backups.

---

## R3: Systematic Error Detection Architecture

### Decision
Implement defense-in-depth error detection at every operation boundary.
Use `audit_log.py` as the diagnostic instrumentation layer.

### Rationale
Per systematic-debugging skill: every multi-component system needs
instrumentation at component boundaries. The installer pipeline
(detect → install → fetch → deploy → verify) has 5 boundaries that
can each fail independently.

### Key Design Decisions

1. **Error context enrichment**: Each `record_file()` and
   `record_package()` call CAN include structured error context
   (exception type, truncated traceback, environment snapshot).
   This is optional so happy-path performance is unaffected.

2. **Pre-existing state snapshot**: Session start captures the full
   `env.installed` dict so even if the process crashes, the baseline
   is on disk.

3. **Diagnostic report**: `generate_diagnostic_report()` produces a
   human-readable markdown string grouping all failures by category,
   renderable by Rich or by plain text.

4. **Atomic writes**: The audit log uses write-to-tmp + `os.replace()`
   for atomic persistence. Corrupt files are renamed, not deleted.

---

## R4: Gum Integration for Bash Scripts

### Decision
Use charmbracelet/gum for interactive elements in `install.sh`, with
graceful fallback to plain echo/read if Gum is unavailable.

### Rationale
Constitution Principle IV mandates Gum for Bash interactive elements.
However, `install.sh` is a bootstrap script that runs before any tools
are installed, so Gum cannot be a hard dependency.

### Implementation Notes
- Auto-install Gum at script start if possible (pacman/apt/brew).
- If Gum cannot be installed, a `_gum_available()` function returns
  false and all wrappers fall back to plain ANSI echo + read -p.
- Gum commands used: `gum spin`, `gum confirm`, `gum choose`,
  `gum style`.
