# Tasks: Installer & KDE Fixes

**Input**: Design documents from `specs/003-installer-and-kde-fixes/`
**Prerequisites**: plan.md (required), spec.md (required for user stories)
**Status (2026-11-20)**: Partially superseded — installer design replaced; see
[spec.md — As-built](spec.md#as-built-2026-11-19). Ticked: T001, T004, T006, T008,
O1–O3. Superseded: T002, T003, T005, T007. Open: T009, O4, O5.

**Tests**: Not requested — no test tasks included. (As-built: related
tests exist, e.g. `tests/lua/test_fast_close.lua`, `tests/test_dep_actions.py`.)

**Organization**: Tasks ordered by dependency; what unblocks others comes first.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)

---

## Phase 1: Foundational — UI crash fix

**Purpose**: Fix the `TypeError` that blocks ALL installer operations

- [x] T001 [US1] Fix `_print()` signature in deploy/ui.py — *done: now `deploy/ui.py:129`; bare `_print()` calls at 892, 914, 921, 929, 1027.* Change line 76 from `def _print(text, **kwargs)` to `def _print(text="", **kwargs)` so bare `_print()` calls (line 273) emit an empty line instead of crashing

  **File**: `deploy/ui.py`
  **Changes**: Line 76 only — make `text` parameter optional with default `""`
  **Acceptance**:
  - `_print()` with zero args produces an empty line (no `TypeError`)
  - `_print("hello")` still works identically
  - `_print("hello", end="")` still works identically
  - `ui.table("Title", ["A","B"], [["1","2"]])` renders without crash when `_RICH_AVAILABLE` is `False`

**Checkpoint**: After T001, the installer can at least run on systems where Rich IS installed. All subsequent tasks depend on this fix.

---

## Phase 2: User Story 1 — Installer Crash-Free Boot (Priority: P1) 🎯 MVP

**Goal**: A user runs `python setup.py --install` on a fresh machine where Rich is NOT installed. The installer bootstraps Rich automatically and completes without crashing.

**Independent Test**: Run `python setup.py --install` on a system where Rich is NOT installed. The installer must print plain-text bootstrap messages, install Rich, re-exec, and proceed with styled output.

- [ ] T002 [US1] **Superseded** — *replaced by `install.sh` installing Rich into the venv from `pyproject.toml`; no `setup.py`, `_bootstrap_rich()` or `os.execv` re-exec.* Add Rich ImportError guard to setup.py — insert `_bootstrap_rich()` function and `try: import rich / except ImportError` block between `sys.path.insert` (line 31) and the `from deploy import ui` statement (line 33). All existing `from deploy import ...` lines (33–44) move AFTER the guard. The guard must use only plain `print()` — no `ui.*` calls.

  **File**: `setup.py`
  **Changes**: Replace lines 29–44 with the bootstrap guard block from plan.md Section 2
  **Acceptance**:
  - On a machine WITHOUT Rich: installer prints `[bootstrap]` messages via plain `print()`, attempts system package install, falls back to venv at `~/.local/share/mpv-config/venv`, installs Rich inside the venv via `pip`, then `os.execv` re-execs under the venv Python
  - On a machine WITH Rich: the `try: import rich` succeeds, `_bootstrap_rich()` is never called, imports proceed normally
  - On a machine with a stale venv (venv exists but Rich broken inside): venv is deleted and recreated
  - `pip` is NEVER invoked system-wide — only via `venv_pip`

---

## Phase 3: User Story 2 — Safe Dependency Installation (Priority: P1)

**Goal**: All CLI executables installed via OS package manager. pip never used for Category A tools. `--break-system-packages` purged from codebase.

**Independent Test**: Run `grep -r "break-system" .` → zero results. Run full install on Arch → verify `pip list --user` does NOT show yt-dlp or ffsubsync.

- [ ] T003 [P] [US2] **Superseded** — *replaced by the current `SYSTEM_DEPS` (GitHub release files on Windows instead of winget, mpv PPA / yt-dlp GitHub binary on Ubuntu, ffsubsync via `uv tool`, aria2/uv/autohotkey added, no gum). Of the acceptance list, "no `"method": "pip"`", "no `break-system-packages`" and "per-platform entries" hold; "Fedora/dnf for yt-dlp and ffsubsync" does not.* Rewrite SYSTEM_DEPS in deploy/registry.py — replace lines 156–196 with the full updated dict from plan.md Section 3.1. Key changes: yt-dlp on ubuntu changes from `pip` to `apt`; ffsubsync on arch changes from `pip+break-system-packages` to `aur`; ffsubsync gets per-platform entries instead of `"all": pip`; Fedora `dnf` entries added for all tools.

  **File**: `deploy/registry.py`
  **Changes**: Lines 156–196 — full replacement of `SYSTEM_DEPS` dict
  **Acceptance**:
  - Zero occurrences of `"method": "pip"` in the entire `SYSTEM_DEPS` dict
  - Zero occurrences of `break-system-packages` anywhere in the file
  - Every Category A tool has explicit per-platform entries (no `"all": pip` fallback)
  - Fedora/dnf entries present for mpv, yt-dlp, ffmpeg, python, ffsubsync

- [x] T004 [P] [US2] *Done 2026-11-20: `_get_pip_args`, `_prepare_ffsubsync_build` and `FFSUBSYNC_SETUPTOOLS_PIN` removed; `dnf` handlers added; the `sync_dependencies` pip fallback replaced by uv tool / pipx (O1, `58d50f2`). `_install_one` now handles 15 methods.* Remove all pip machinery from deploy/installer.py — delete `_get_pip_args()` (lines 36–94), the `elif method == "pip":` branch in `_install_one()` (lines 121–138), the `elif method == "pip":` branch in `_uninstall_one()` (lines 223–228), `_prepare_ffsubsync_build()` (lines 163–202), and `FFSUBSYNC_SETUPTOOLS_PIN` (line 15). Add `elif method == "dnf":` handlers to both `_install_one` and `_uninstall_one`.

  **File**: `deploy/installer.py`
  **Changes**:
  - DELETE line 15 (`FFSUBSYNC_SETUPTOOLS_PIN`)
  - DELETE lines 36–94 (`_get_pip_args`)
  - DELETE lines 121–138 (`elif method == "pip":` in `_install_one`)
  - DELETE lines 163–202 (`_prepare_ffsubsync_build`)
  - DELETE lines 223–228 (`elif method == "pip":` in `_uninstall_one`)
  - ADD `elif method == "dnf": return _run(["sudo", "dnf", "install", "-y", info["pkg"]])` in `_install_one`
  - ADD `elif method == "dnf": return _run(["sudo", "dnf", "remove", "-y", info["pkg"]], check=False)` in `_uninstall_one`
  **Acceptance**:
  - Zero occurrences of `pip` in any subprocess call constructed by installer.py
  - `_install_one` handles methods: pacman, apt, dnf, brew, winget, aur, manual
  - `_uninstall_one` handles methods: pacman, apt, dnf, brew, winget, aur, manual
  - No reference to `FFSUBSYNC_SETUPTOOLS_PIN` or `_prepare_ffsubsync_build`

- [ ] T005 [US2] **Superseded** — *`install.sh` was rewritten to always create the venv and install with the venv's pip / `uv pip`; no system `python-rich` attempt, no Gum wrappers at the time (added 2026-11-20, O2).* Replace bare pip calls in install.sh — delete lines 196–197 (system-wide `pip install` of setuptools/wheel/rich) and replace with system-package-first logic from plan.md Section 3.6. Try `pacman -S python-rich` / `apt install python3-rich` / `brew install python-rich`. If all fail, print a dim message that `setup.py` will handle venv fallback.

  **File**: `install.sh`
  **Changes**: Replace lines 196–198 with the system-pkg-first block from plan.md Section 3.6
  **Acceptance**:
  - Zero occurrences of `pip install` in install.sh
  - Zero occurrences of `setuptools` or `wheel` in install.sh
  - Rich installation attempts system package manager first
  - If system package fails, a dim message is printed (not a crash)

**Checkpoint**: After T003–T005, the dependency system is fully PEP 668 compliant. `--break-system-packages` is gone. pip is never used outside a venv.

---

## Phase 4: User Story 3 — mpv Window Close on KDE (Priority: P2)

**Goal**: Clicking the X button on KDE Plasma 6.6.4 terminates mpv within 1 second.

**Independent Test**: Open mpv on KDE, play any file, click the X button. The process should terminate within 1 second.

- [x] T006 [P] [US3] *Done in modified form: `config/input.conf.template:156` is `CLOSE_WIN set window-minimized yes ; quit` (placed after the F10 sharpen binding), plus `q`/`Q` at lines 157–158 and `scripts/fast_close.lua`.* Add CLOSE_WIN quit binding to config/input.conf.template — add `CLOSE_WIN quit` after line 104 (after the F8 night-mode binding, before the end-of-settings comment). Include a comment explaining this is the WM close-button pseudo-key.

  **File**: `config/input.conf.template`
  **Changes**: Insert after line 104:
  ```
  # ── Window close ── ensure WM close button kills mpv instantly ──
  CLOSE_WIN quit
  ```
  **Acceptance**:
  - `CLOSE_WIN quit` present in the template
  - Binding is in the "useful shortcuts" section, not inside any script-binding block
  - No duplicate `CLOSE_WIN` bindings exist
  - Note: `MBTN_CLOSE` does NOT exist in mpv's input system — the correct key is `CLOSE_WIN`

---

## Phase 5: User Story 4 — Fullscreen Button State Sync on KDE (Priority: P2)

**Goal**: uosc fullscreen button icon stays in sync with actual window state when toggling fullscreen via uosc or KDE title bar.

**Independent Test**: Toggle fullscreen via uosc button, then via KDE title bar. The uosc icon must always reflect the actual state.

- [ ] T007 [P] [US4] **Superseded** — *`--native-fs` is macOS-only per the mpv manual, so the `native-fs = no` line this task added had no effect on Linux; it was removed on 2026-11-20 (O3, `e6eb056`). US4 is met by mpv's Wayland backend (manual test 2026-11-19).* Add native-fs and geometry options to config/mpv.conf.template — add `native-fs = no` after the `force-window` line (after line 20). Add geometry/autofit lines to the `{{LINUX_VISUAL_TUNING}}` injection point documentation.

  **File**: `config/mpv.conf.template`
  **Changes**: Insert after line 20 (`force-window = immediate`):
  ```ini
  # ── KDE Plasma fullscreen synchronization ────────────────────────
  native-fs               = no
  ```
  **Acceptance**:
  - `native-fs = no` present in the general settings section
  - No conflict with existing fullscreen-related options
  - `fs = yes` (line 18) and `native-fs = no` coexist correctly — `fs=yes` means start fullscreen, `native-fs=no` means use mpv's own fullscreen mechanism

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T008 *Done: plan.md Section 4.3 present; geometry/autofit in `deploy/deployer.py::_get_linux_visual_tuning_block` (lines 169–172). Note: these are config literals in `deploy/` (O4).* Document KDE window snap as out of scope in specs/003-installer-and-kde-fixes/plan.md — verify Section 4.3 (scope boundary) is present and complete. Add geometry/autofit convenience options to `{{LINUX_VISUAL_TUNING}}` expansion in deploy/deployer.py if not already there.

  **Files**: `specs/003-installer-and-kde-fixes/plan.md` (verify), `deploy/deployer.py` (add geometry/autofit to LINUX_VISUAL_TUNING expansion)
  **Changes**: In `deploy/deployer.py`, locate the `LINUX_VISUAL_TUNING` template variable expansion and add:
  ```ini
  geometry                = 50%x50%
  autofit-larger          = 90%x90%
  autofit-smaller         = 30%x30%
  ```
  **Acceptance**:
  - geometry/autofit lines injected on Linux deploys via LINUX_VISUAL_TUNING
  - These are NOT presented as "window snap fixes" — they are convenience sizing helpers
  - No changes to Windows deploys

- [ ] T009 *Not met: `grep -r "break-system" .` hits `.specify/memory/constitution.md:119` (the ban itself); `"method": "pip"` → 0; constitution Principle III is not satisfied (O5); O1 and O2 were fixed 2026-11-20.* Final codebase validation — run `grep -r "break-system" .` and confirm zero results. Run `grep -r '"method": "pip"' deploy/` and confirm zero results. Verify all constitution principles are satisfied per the compliance table in plan.md.

  **Files**: entire codebase (read-only scan)
  **Acceptance**:
  - `grep -r "break-system" .` → 0 results (excluding spec.md which documents the old behavior)
  - `grep -r '"method": "pip"' deploy/` → 0 results
  - All 7 constitution principles pass (see plan.md compliance table)

---

## Open items (code bugs — separate change)

Tracked in [spec.md — Open items](spec.md#open-items-code-bugs--to-be-fixed-in-a-separate-change):

- [x] O1 *(fixed 2026-11-20, `58d50f2`)* Remove the `python -m pip` / bare `pip` ffsubsync fallback from `deploy/installer.py::sync_dependencies` (constitution: no pip for CLI tools)
- [x] O2 *(fixed 2026-11-20, `729639f`)* Replace raw `echo` in `install.sh` with Gum wrappers and an ANSI fallback (Principle V)
- [x] O3 *(fixed 2026-11-20, `e6eb056`)* Remove the no-op `native-fs` line from the Linux output (`{{NATIVE_FS}}`, `deploy/deployer.py:473`)
- [ ] O4 Move the window sizing helpers out of `deploy/deployer.py` into a config template (Principle I) — found in this update
- [ ] O5 Stop `install.ps1` from running `pip install --user` against the system Python (Principle III) — found in this update

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (T001)**: No dependencies — must complete FIRST (unblocks everything)
- **Phase 2 (T002)**: Depends on T001 — bootstrap guard needs `_print` fix to be safe
- **Phase 3 (T003–T005)**: T003 and T004 are parallel (different files). T005 is parallel with T003/T004 (different file). All depend on T001.
- **Phase 4 (T006)**: Independent — can run in parallel with any phase after T001
- **Phase 5 (T007)**: Independent — can run in parallel with any phase after T001
- **Phase 6 (T008–T009)**: Depends on ALL previous phases completing

### Task Dependency Graph

```
T001 (ui.py fix)
├── T002 (setup.py bootstrap)
├── T003 (registry.py rewrite)     ─┐
├── T004 (installer.py pip purge)  ─┤── can run in parallel
├── T005 (install.sh pip purge)    ─┘
├── T006 (input.conf CLOSE_WIN)    ── independent, parallel OK
├── T007 (mpv.conf native-fs)      ── independent, parallel OK
└── T008, T009 (polish)            ── after all above
```

### Parallel Opportunities

```bash
# After T001 completes, launch all of these in parallel:
Task: T003 "Rewrite SYSTEM_DEPS in deploy/registry.py"
Task: T004 "Remove pip machinery from deploy/installer.py"
Task: T005 "Replace bare pip calls in install.sh"
Task: T006 "Add CLOSE_WIN quit to config/input.conf.template"
Task: T007 "Add native-fs=no to config/mpv.conf.template"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete T001 (ui.py `_print` fix)
2. Complete T002 (setup.py bootstrap guard)
3. **STOP and VALIDATE**: Run `python setup.py --install` on a system without Rich

### Incremental Delivery

1. T001 → installer stops crashing
2. T002 → installer auto-bootstraps Rich
3. T003 + T004 + T005 → dependency system is PEP 668 clean
4. T006 + T007 → KDE window behaviors fixed
5. T008 + T009 → polish and validation

---

## Summary

| Metric | Value |
|--------|-------|
| Total tasks | 9 |
| US1 (crash-free boot) | 1 task (T002) + T001 foundational |
| US2 (safe deps) | 3 tasks (T003, T004, T005) |
| US3 (window close) | 1 task (T006) |
| US4 (fullscreen sync) | 1 task (T007) |
| Polish | 2 tasks (T008, T009) |
| Max parallel width | 5 tasks (T003–T007 after T001) |
| MVP scope | T001 + T002 |

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Commit after each task or logical group
- T006 and T007 touch `config/` only — zero risk to `deploy/` code
- The spec mentions `MBTN_CLOSE` but the correct mpv key is `CLOSE_WIN` (documented in plan.md Section 4.1)
