# Implementation Plan: MPV Auto-Deploy Automation

**Branch**: `001-mpv-automation` | **Date**: 2026-04-18 | **Spec**: [spec.md](file:///home/abdallahx/Desktop/mpv-config/specs/001-mpv-automation/spec.md)
**Input**: Feature specification from `/specs/001-mpv-automation/spec.md`

## Summary

Build a cross-platform mpv deployment automation system with four core
subsystems: environment detection (`detector.py`), interactive terminal UI
(`ui.py` via Rich), safe config deployment with symlinks/copy strategy
(`deployer.py`), and auditable error tracking (`audit_log.py`). The system
detects OS/GPU/display, installs missing dependencies, fetches scripts from
GitHub, patches config templates, and deploys everything to the correct
mpv config directory — with full backup, rollback, and uninstall support.

## Technical Context

**Language/Version**: Python 3.8+ (sole language for `deploy/`), Bash
(install.sh with `#!/usr/bin/env bash`), PowerShell 5.1+ (install.ps1)
**Primary Dependencies**: Rich (Python terminal UI library — the ONLY
permitted external dependency per Constitution Principle IV), Gum
(charmbracelet/gum for Bash interactive elements)
**Storage**: JSON files (`.audit-log.json`, `.deploy.lock.json`) in the
mpv config directory. No database.
**Testing**: Manual verification + post-deploy verification suite
(`verifier.py`). No pytest framework (stdlib-only project).
**Target Platform**: Windows 10+, Linux (Arch, Ubuntu/Debian, Fedora),
macOS (secondary)
**Project Type**: CLI automation tool
**Performance Goals**: Full install < 5 minutes on reasonable internet.
Detection phase < 2 seconds.
**Constraints**: Zero external Python packages for core logic. Only Rich
allowed for UI. Bash scripts require Gum for interactive elements.
**Scale/Scope**: Single-user deployment tool. 9 scripts + 1 shader pack
+ 6 config files.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| **I. Terminology Separation** | ✅ PASS | Automation Scripts live in `deploy/` and project root. mpv Internal Scripts live in `config/script-opts/`. No cross-contamination in any module. `deployer.py` copies `config/` files TO the mpv directory but never imports or depends on their content. |
| **II. OS Parity** | ✅ PASS | Every file in `deploy/` uses `detector.py`/`registry.py` abstractions for platform differences. `install.sh` and `install.ps1` achieve feature parity. Symlinks (Linux) vs copy (Windows) strategy adds a new platform divergence but is properly isolated in `deployer.py` behind `env.os` checks. |
| **III. Fish Environment** | ✅ PASS | `install.sh` already has `#!/usr/bin/env bash`. All new `.sh` files MUST follow this. No reliance on Bash as login shell. |
| **IV. CLI Aesthetics** | ⚠️ REQUIRES WORK | Current `ui.py` uses raw ANSI codes and `print()`. Constitution mandates Rich (Python) and Gum (Bash). This plan addresses the migration. |

**Gate Decision**: PASS with noted remediation for Principle IV in the
implementation phases below.

## Project Structure

### Documentation (this feature)

```text
specs/001-mpv-automation/
├── plan.md              # This file
├── research.md          # Phase 0: technology decisions
├── data-model.md        # Phase 1: entity definitions
├── quickstart.md        # Phase 1: getting started guide
├── contracts/           # Phase 1: CLI interface contracts
│   └── cli-contract.md
└── tasks.md             # Phase 2: actionable task list
```

### Source Code (repository root)

```text
├── setup.py                  # CLI entry point + interactive menu
├── install.sh                # Linux/macOS bootstrap (Bash + Gum)
├── install.ps1               # Windows bootstrap (PowerShell)
├── deploy/
│   ├── __init__.py
│   ├── ui.py                 # Terminal UI (→ Rich migration)
│   ├── detector.py           # OS/GPU/display/package detection
│   ├── registry.py           # Script sources + platform defaults
│   ├── fetcher.py            # GitHub downloader (retry + backoff)
│   ├── installer.py          # Dependency installer
│   ├── deployer.py           # Deploy + backup + symlink/copy
│   ├── verifier.py           # Post-deploy verification
│   ├── planner.py            # Pre-flight action plan display
│   └── audit_log.py          # Operation audit log
└── config/
    ├── mpv.conf.template
    ├── input.conf.template
    └── script-opts/
        ├── uosc.conf
        ├── SmartSkip.conf
        ├── evafast.conf
        ├── memo.conf
        └── autosubsync.conf.template
```

**Structure Decision**: This is an existing single-project CLI tool. No
new directories are needed. All changes happen within the existing
`deploy/`, `config/`, and root-level files.

---

## Phase 0: Research

### R1: Rich Library Integration Strategy

**Decision**: Migrate `deploy/ui.py` from raw ANSI escape codes to the
Rich library, maintaining the same public API so all callers (`setup.py`,
`detector.py`, `installer.py`, `deployer.py`, `verifier.py`, `planner.py`)
require zero changes.

**Rationale**: Constitution Principle IV mandates Rich for Python CLI.
The current `ui.py` already provides a clean abstraction layer (`ui.banner()`,
`ui.header()`, `ui.success()`, etc.). Swapping internals from ANSI to Rich
preserves the API contract while delivering Spinners, Panels, Tables, and
Progress bars.

**Alternatives considered**:
- **Keep raw ANSI**: Violates Constitution. Rejected.
- **Textual (full TUI)**: Overkill for a sequential CLI tool. Rejected.
- **Click + Rich**: Click adds unnecessary dependency. Rejected.

**Rich components to use**:

| Current Function | Rich Replacement |
|-----------------|-----------------|
| `ui.banner()` | `rich.panel.Panel` with styled ASCII art |
| `ui.header()` | `rich.panel.Panel` with title + rule |
| `ui.step()` | `rich.console.Console.print()` with `[cyan]>` markup |
| `ui.success()` | `Console.print()` with `[green]✓` markup |
| `ui.warn()` | `Console.print()` with `[yellow]!` markup |
| `ui.error()` | `rich.panel.Panel(border_style="red")` with actionable guidance |
| `ui.progress()` | `rich.progress.Progress` with transfer speed |
| `ui.summary()` | `rich.table.Table` with colored status column |
| `ui.confirm()` | `rich.prompt.Confirm.ask()` |
| Long operations | `rich.status.Status` (spinner) wrapping fetches/installs |

**Graceful fallback**: If Rich is not installed (e.g., during bootstrap
before dependencies are installed), `ui.py` MUST fall back to the current
ANSI-based output. This is achieved with a try/except import at module top.

### R2: Symlink vs Copy Deployment Strategy

**Decision**: Use OS-conditional deployment strategy in `deployer.py`:
- **Linux/macOS**: Symlinks (`os.symlink`) for script directories
  (`scripts/`, `shaders/`, `fonts/`) pointing from the mpv config dir
  back to the staging/installed copy. Config files (`mpv.conf`,
  `input.conf`, `script-opts/`) are always full copies (since they are
  patched per-platform).
- **Windows**: Full copy (`shutil.copytree`) for everything, since
  symlinks on Windows require Developer Mode or elevated privileges
  and are unreliable on FAT32/exFAT USB drives.

**Rationale**: Symlinks on Linux allow `mpv-config --update` to be a
simple re-fetch to the install directory without needing to re-copy to
the config dir. On Windows, the permission model makes symlinks
unreliable for a zero-knowledge user.

**Implementation detail**:
```
if env.os in ("linux", "macos"):
    # Remove existing dir, create symlink
    if os.path.exists(dst):
        if os.path.islink(dst):
            os.unlink(dst)
        else:
            shutil.rmtree(dst)
    os.symlink(src, dst)
else:
    # Windows: full copy
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
```

**Junction alternative (Windows)**: NTFS junctions (`mklink /J`) were
considered but rejected because:
1. They only work for directories, not files.
2. They silently break on non-NTFS filesystems.
3. `shutil.copytree` is simpler and equally performant for ~100 files.

**Alternatives considered**:
- **Symlinks everywhere**: Fails on Windows without Developer Mode. Rejected.
- **Copy everywhere**: Works but loses the instant-update benefit on Linux. Rejected.
- **Hardlinks**: Cannot link directories. Rejected.

### R3: Systematic Error Detection & Audit Logging (from @systematic-debugging)

**Decision**: Implement defense-in-depth error detection following the
systematic-debugging skill's Phase 1 (Root Cause Investigation) and
Phase 4 (Diagnostic instrumentation) principles.

**Rationale**: The audit log is the project's diagnostic instrumentation
layer. Every operation boundary (detect → install → fetch → deploy →
verify) MUST log entry/exit state so root cause analysis is possible
after failures.

**Error detection architecture**:

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  detect()   │───▶│  install()  │───▶│  fetch()    │
│  Log: env   │    │  Log: pkg   │    │  Log: files │
│  state      │    │  pre-exist  │    │  + retries  │
└─────────────┘    └─────────────┘    └─────────────┘
       │                  │                  │
       ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────┐
│              audit_log.py                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │ session  │ │ packages │ │ files    │           │
│  │ metadata │ │ state    │ │ ops      │           │
│  └──────────┘ └──────────┘ └──────────┘           │
│                                                     │
│  JSON on disk: <config_dir>/.audit-log.json        │
└─────────────────────────────────────────────────────┘
```

**Error categories and handling**:

| Error Category | Detection Point | Audit Log Entry | User-Facing Action |
|---------------|----------------|-----------------|-------------------|
| Network failure | `fetcher.py:_request()` | `{file, operation:"fetch", status:"failed", detail:"ConnectionError after 3 retries"}` | Rich Panel (red) with retry count + suggestion to check internet |
| Package install failure | `installer.py:_install_one()` | `{package, action:"install", status:"failed"}` | Rich Panel with exact command that failed + manual install instructions |
| Permission denied | `deployer.py:deploy()` | `{file, operation:"copy", status:"failed", detail:"PermissionError"}` | Rich Panel suggesting `sudo` or checking directory ownership |
| Template placeholder leak | `verifier.py:verify()` | Verification check failure | Rich Table showing which file has unresolved `{{…}}` |
| Corrupt audit log | `audit_log.py:_load()` | Original renamed to `.corrupt`, fresh log started | Warning panel, no data loss |
| Rate limit (GitHub) | `fetcher.py:_request()` | Logged as retry event | Spinner with "Rate limited, waiting Xs..." |

**Defense-in-depth layers** (per systematic-debugging skill):

1. **Input validation**: `detector.py` validates every detected value
   before storing (empty string defaults, never None).
2. **Operation boundaries**: Every function in `deployer.py` wraps
   file operations in try/except with structured audit log entries.
3. **Atomic operations**: Backup uses `shutil.copytree` to a temp
   location, then `shutil.move` — never partial state.
4. **Recovery paths**: Every failure has a documented recovery:
   rollback for deploy failures, retry for network, manual instructions
   for package failures.

---

## Phase 1: Design

### 1.1 — `deploy/ui.py` Interactive UI Architecture (Rich Migration)

The UI module MUST maintain backward API compatibility. All existing
callers use `ui.banner()`, `ui.header()`, `ui.step()`, `ui.success()`,
`ui.warn()`, `ui.error()`, `ui.info()`, `ui.item()`, `ui.progress()`,
`ui.summary()`, `ui.confirm()`. These function signatures MUST NOT change.

**New capabilities added**:

- `ui.spinner(text)` → Context manager wrapping `rich.status.Status`.
  Usage: `with ui.spinner("Fetching uosc..."): fetch_raw(...)`.
- `ui.table(title, columns, rows)` → Wrapper around `rich.table.Table`.
  Usage: `ui.table("Detection Results", ["Property", "Value"], rows)`.
- `ui.panel(text, title, style)` → Wrapper around `rich.panel.Panel`.
  Usage for errors: `ui.panel("...", title="Error", style="red")`.

**Fallback strategy**:

```python
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.progress import Progress
    from rich.prompt import Confirm
    from rich.status import Status
    _RICH_AVAILABLE = True
    _console = Console()
except ImportError:
    _RICH_AVAILABLE = False
    # Fall back to current ANSI implementation
```

**Windows UTF-8 handling**: The existing `sys.stdout.reconfigure()`
logic is preserved. Rich auto-detects terminal capabilities, but
the explicit UTF-8 reconfiguration ensures compatibility with
Windows cmd.exe and PowerShell 5.1 where Rich's auto-detection
may fail.

### 1.2 — `deploy/deployer.py` Safe Config Deployment

**Current behavior** (to be preserved): backup → copy scripts/shaders/
fonts → copy script-opts → patch templates → create directories →
normalize line endings.

**New behavior** (added by this plan):

1. **Symlink strategy for Linux/macOS**:
   - For `scripts/`, `shaders/`, `fonts/`: create symlinks from
     `<config_dir>/<item>` → `<install_dir>/.staging/<item>` (or
     `<install_dir>/deployed/<item>` for a persistent copy).
   - For `script-opts/`, `mpv.conf`, `input.conf`: always full copy
     (these are patched/generated, not raw upstream files).

2. **Persistent install directory**:
   - Instead of deleting `.staging/` after deploy, move it to
     `<install_dir>/deployed/` so symlinks remain valid.
   - On `--update`, re-fetch into `.staging/`, replace `deployed/`,
     symlinks automatically point to new content.

3. **Symlink-aware backup**:
   - `backup_existing()` MUST handle the case where `<config_dir>/scripts`
     is a symlink. `shutil.copytree` follows symlinks by default, so the
     backup will contain real files even when the source is symlinked.
   - On rollback, the restored backup is always real files (no symlinks),
     which is the safer default.

4. **Conflict prevention**:
   - Before creating a symlink, check if the target already exists:
     - If it's a symlink pointing elsewhere → remove and recreate.
     - If it's a real directory → back up, then replace with symlink.
     - If it's a file → error (unexpected state).
   - `audit_log.record_file()` logs whether a symlink or copy was used.

### 1.3 — `deploy/audit_log.py` Error Tracking Architecture

**Current state**: Already implements session-based JSON logging with
`record_package()`, `record_file()`, `record_backup()`, and query
helpers. This is well-designed.

**Enhancements from systematic-debugging analysis**:

1. **Error context enrichment**: Add optional `error_context` field to
   `record_file()` and `record_package()`:
   ```python
   def record_file(self, path, operation, status, detail="",
                   backup_path=None, error_context=None):
       entry = { ... }
       if error_context:
           entry["error_context"] = {
               "exception_type": error_context.get("type", ""),
               "traceback_summary": error_context.get("traceback", ""),
               "environment_snapshot": error_context.get("env", {}),
           }
   ```

2. **Diagnostic summary generation**: Add `generate_diagnostic_report()`
   method that produces a human-readable summary of all failures in the
   latest session:
   ```python
   def generate_diagnostic_report(self) -> str:
       """Generate a structured diagnostic report for the latest session."""
       # Collects all failed operations, groups by category,
       # and formats as a Rich-renderable markdown string.
   ```

3. **Pre-existing state snapshot**: The `record_package()` method already
   tracks `was_pre_existing`. Extend the session start to snapshot ALL
   detected package states upfront, so even if a failure occurs before
   individual records are written, the baseline is preserved.

### 1.4 — `install.sh` Gum Integration

**Current state**: `install.sh` uses `echo` with ANSI codes for output.
Constitution Principle IV mandates Gum for Bash interactive elements.

**Strategy**:
1. Auto-install Gum at the start of `install.sh` if not present:
   - Arch: `sudo pacman -S --noconfirm gum`
   - Ubuntu/Debian: Download from GitHub Releases
   - macOS: `brew install gum`
2. All interactive prompts switch from `read -p` to `gum confirm`.
3. Progress indicators switch from `echo` to `gum spin`.
4. Styled output uses `gum style`.
5. **Graceful fallback**: If Gum cannot be installed (no sudo, restricted
   network), fall back to plain `echo` with ANSI colors. The script MUST
   NOT fail because Gum is unavailable.

### 1.5 — `deploy/planner.py` Rich Integration

**Current state**: Uses raw ANSI via `ui.C.*` color constants and
`print()` calls. The `display_plan()` and `confirm_plan()` functions
render action plans with color-coded categories.

**Migration**: Replace `print()` calls with `ui.table()` and
`ui.panel()` calls. The plan display becomes a Rich Table with columns:
`[Action] [Target] [Detail]`, color-coded by action type. The
confirmation prompt uses `ui.confirm()` (which internally uses
`rich.prompt.Confirm.ask()`).

---

## Phase 1 Design Outputs

### Data Model → [data-model.md](file:///home/abdallahx/Desktop/mpv-config/specs/001-mpv-automation/data-model.md)

### Contracts → [contracts/cli-contract.md](file:///home/abdallahx/Desktop/mpv-config/specs/001-mpv-automation/contracts/cli-contract.md)

### Quickstart → [quickstart.md](file:///home/abdallahx/Desktop/mpv-config/specs/001-mpv-automation/quickstart.md)

---

## Complexity Tracking

| Item | Why Needed | Simpler Alternative Rejected Because |
|------|-----------|--------------------------------------|
| Symlink vs Copy bifurcation | Windows doesn't support symlinks without Developer Mode | Copy-everywhere loses instant-update on Linux; symlink-everywhere breaks on Windows |
| Rich + ANSI fallback | Bootstrap phase runs before Rich is installed | Rich-only would crash during initial curl install |
| Gum + echo fallback | Some systems can't install Gum (restricted envs) | Gum-only would block install on minimal servers |
