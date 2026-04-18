# Tasks: MPV Auto-Deploy Automation

**Input**: Design documents from `/specs/001-mpv-automation/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: Not explicitly requested — test tasks omitted. Verification via `verifier.py`.

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Install Rich dependency and prepare the project for the UI migration

- [x] T001 Add `rich` to project requirements in `requirements.txt` (create file if absent)
- [x] T002 [P] Add `rich` install step to `install.sh` bootstrap script via `pip install rich`
- [x] T003 [P] Add `rich` install step to `install.ps1` bootstrap script via `pip install rich`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Migrate `deploy/ui.py` to Rich — this blocks ALL user stories because every module imports `ui`

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Add Rich import with try/except fallback at top of `deploy/ui.py` — set `_RICH_AVAILABLE` flag and create `_console = Console()` if Rich is available; preserve existing `C` class and ANSI functions as fallback
- [x] T005 Migrate `ui.banner()` in `deploy/ui.py` — replace raw `print()` ASCII art with `rich.panel.Panel` containing styled banner text; fallback to current ANSI implementation when `_RICH_AVAILABLE is False`
- [x] T006 Migrate `ui.header(text)` in `deploy/ui.py` — replace ANSI bold+underline with `rich.rule.Rule` or `rich.panel.Panel(title=text)`; preserve fallback
- [x] T007 Migrate `ui.step(text)` in `deploy/ui.py` — replace `print(f"{C.CYAN}>{C.RESET} {text}")` with `_console.print(f"[cyan]>[/cyan] {text}")` ; preserve fallback
- [x] T008 [P] Migrate `ui.success(text)` in `deploy/ui.py` — replace ANSI green checkmark with `_console.print(f"[green]  ✓[/green] {text}")`; preserve fallback
- [x] T009 [P] Migrate `ui.warn(text)` in `deploy/ui.py` — replace ANSI yellow warning with `_console.print(f"[yellow]  ![/yellow] {text}")`; preserve fallback
- [x] T010 [P] Migrate `ui.error(text)` in `deploy/ui.py` — replace ANSI red with `_console.print(Panel(text, title="Error", border_style="red"))`; preserve fallback
- [x] T011 [P] Migrate `ui.info(text)` in `deploy/ui.py` — replace ANSI dim with `_console.print(f"[dim]  ℹ[/dim] {text}")`; preserve fallback
- [x] T012 Migrate `ui.progress(current, total, label)` in `deploy/ui.py` — replace ANSI progress bar with `rich.progress.Progress` using `BarColumn`, `TaskProgressColumn`, and `TextColumn`; preserve fallback
- [x] T013 Migrate `ui.summary(results)` in `deploy/ui.py` — replace `print()` loop with `rich.table.Table` having columns `[Name, Status, Detail]` with color-coded status cells; preserve fallback
- [x] T014 Migrate `ui.confirm(question)` in `deploy/ui.py` — replace `input()` call with `rich.prompt.Confirm.ask(question)` returning bool; preserve `input()` fallback
- [x] T015 Add new `ui.spinner(text)` context manager in `deploy/ui.py` — wrap `rich.status.Status` returning a context manager; fallback is a no-op context manager that prints the text
- [x] T016 Add new `ui.table(title, columns, rows)` helper in `deploy/ui.py` — wrap `rich.table.Table(title=title)` adding columns and rows; fallback prints tab-separated plain text
- [x] T017 Add new `ui.panel(text, title, style)` helper in `deploy/ui.py` — wrap `rich.panel.Panel(text, title=title, border_style=style)`; fallback prints boxed text with ANSI
- [x] T018 Remove the `C` ANSI color class from public API of `deploy/ui.py` — internalize it as `_C` for fallback use only; update `planner.py` references to `ui.C.` to use new `ui.*` wrappers instead
- [x] T019 Verify all callers of `deploy/ui.py` still work — run `python -c "from deploy import ui; ui.banner(); ui.success('test'); ui.warn('test'); ui.error('test')"` from project root

**Checkpoint**: Rich migration complete — all `deploy/*.py` modules produce Rich output with ANSI fallback. No public API signatures changed.

---

## Phase 3: User Story 3 — OS Detection & Environment Profiling (Priority: P1) 🎯 MVP

**Goal**: Ensure `detector.py` correctly detects OS/GPU/display/packages on all supported platforms and surfaces results via Rich UI

**Independent Test**: Run `python -c "from deploy.detector import detect; env = detect(); print(vars(env))"` on each platform and verify all fields are populated with correct values

- [x] T020 [US3] Update `detector.py` detection output to use `ui.table()` — replace the `ui.success()` calls in `detect()` function with a single `ui.table("Detection Results", ["Property", "Value"], rows)` call at the end of detection in `deploy/detector.py`
- [x] T021 [US3] Add `ui.spinner("Detecting environment...")` wrapper around the detection phase in `deploy/detector.py` — wrap the main detection block with `with ui.spinner(...):`
- [x] T022 [US3] Add GPU detection fallback logging in `deploy/detector.py` — when `gpu_vendor` is empty, log `ui.warn("GPU vendor not detected — using safe defaults (gpu_api=auto, hwdec=auto)")` and ensure empty string (not None) is stored
- [x] T023 [US3] Validate `Environment` fields in `deploy/detector.py` — add a `_validate_env(env)` function at end of `detect()` that asserts: `os` is never empty (default `"linux"`), `config_dir` is absolute path, `installed` keys match `SYSTEM_DEPS` keys

**Checkpoint**: Detection works on Linux, outputs a Rich table, handles missing GPU gracefully

---

## Phase 4: User Story 1 — One-Command Full Install (Priority: P1) 🎯 MVP

**Goal**: The full pipeline detect → plan → confirm → install → fetch → deploy → verify works end-to-end with Rich UI

**Independent Test**: Run `python setup.py --dry-run` and verify the full plan is displayed as a Rich table with confirmation prompt

### Deploy Strategy (Symlink/Copy)

- [ ] T024 [US1] Add `_deploy_directory(src, dst, env, audit_log)` function in `deploy/deployer.py` — implement OS-conditional logic: Linux/macOS creates symlink from `dst → src`; Windows uses `shutil.copytree(src, dst)`. Handle existing symlinks (unlink+recreate), existing dirs (backup+replace), and log the method used via `audit_log.record_file()`
- [ ] T025 [US1] Add `_is_symlink_safe(dst)` guard function in `deploy/deployer.py` — check if target exists: if symlink pointing elsewhere → safe to replace; if real directory → needs backup first; if file → raise error (unexpected state)
- [ ] T026 [US1] Update `deploy()` function in `deploy/deployer.py` — replace direct `shutil.copytree()` calls for `scripts/`, `shaders/`, `fonts/` with calls to new `_deploy_directory()` function
- [ ] T027 [US1] Add persistent staging directory logic in `deploy/deployer.py` — after successful deploy, move `.staging/` to `<install_dir>/deployed/` instead of deleting; update symlinks to point to `deployed/` paths
- [ ] T028 [US1] Update `backup_existing()` in `deploy/deployer.py` — handle the case where `<config_dir>/scripts` is a symlink by using `shutil.copytree(src, dst, follow_symlinks=True)` to produce real-file backups

### Audit Log Enhancements

- [ ] T029 [P] [US1] Add `error_context` parameter to `record_file()` in `deploy/audit_log.py` — optional dict with keys `type` (exception class name), `traceback` (truncated traceback string), `env` (environment snapshot dict); store under `error_context` key in entry
- [ ] T030 [P] [US1] Add `error_context` parameter to `record_package()` in `deploy/audit_log.py` — same structure as T029; store under `error_context` key in package entry
- [ ] T031 [US1] Add `generate_diagnostic_report()` method in `deploy/audit_log.py` — iterate latest session, collect all entries where `status == "failed"`, group by category (packages/files), return formatted markdown string suitable for Rich rendering
- [ ] T032 [US1] Add pre-existing state snapshot at session start in `deploy/audit_log.py` — in `start_session()`, accept `env.installed` dict and store as `initial_package_state` in the session record so baseline is always available even if process crashes

### Planner Rich Migration

- [ ] T033 [US1] Update `display_plan()` in `deploy/planner.py` — replace raw `print()` with ANSI color references to use `ui.table()` for plan display; each plan category becomes a section in a Rich Table with columns `[Action, Target, Detail]` and color-coded action column
- [ ] T034 [US1] Update `confirm_plan()` in `deploy/planner.py` — replace raw `input()` and `ui.C.*` references with `ui.confirm()` call; remove direct `ui.C` usage
- [ ] T035 [US1] Remove all `ui.C.*` references from `deploy/planner.py` — replace `ui.C.YELLOW`, `ui.C.GREEN`, etc. with `ui.success()`, `ui.warn()`, `ui.info()` wrapper calls or pass style hints to `ui.panel()`/`ui.table()`

### Fetcher UI Enhancement

- [ ] T036 [US1] Wrap `fetch_all()` loop in `deploy/fetcher.py` with `ui.progress()` — replace the per-item `ui.progress(current, total, name)` with a Rich `Progress` context wrapping all fetches, adding a task per script/shader
- [ ] T037 [P] [US1] Add `ui.spinner()` to individual `fetch_raw()` and `fetch_release()` calls in `deploy/fetcher.py` — wrap the HTTP download portion with `with ui.spinner(f"Downloading {name}..."):`

### Installer UI Enhancement

- [ ] T038 [US1] Wrap each `_install_one()` call in `deploy/installer.py` with `ui.spinner(f"Installing {name}...")` — add spinner context around the `subprocess.run()` call
- [ ] T039 [US1] Update `install_deps()` in `deploy/installer.py` — replace `ui.confirm()` call to use the new Rich-based confirmation; add `try/except` around each install with `audit_log.record_package(error_context=...)` on failure

### Verifier UI Enhancement

- [ ] T040 [US1] Update `verify()` in `deploy/verifier.py` — replace the internal `check()` function's `print()` calls with `ui.success()`/`ui.error()` and collect results into a `ui.table("Verification Results", ...)` at the end
- [ ] T041 [US1] Add diagnostic report display in `setup.py` — after `verify()` returns, if any checks failed, call `audit_log.generate_diagnostic_report()` and display via `ui.panel(..., title="Diagnostic Report", style="yellow")`

### Entry Point Polish

- [ ] T042 [US1] Add `ui.spinner("Checking internet connectivity...")` wrapper in `cmd_install()` in `setup.py` around the `urllib.request.urlopen` pre-flight check
- [ ] T043 [US1] Replace the inline `print(f"\n  {ui.C.GREEN}...")` success/failure messages at end of `cmd_install()` in `setup.py` with `ui.panel("Deployment complete!", title="✅ Success", style="green")` and `ui.panel("... issues", title="⚠️ Warning", style="yellow")`

**Checkpoint**: Full install pipeline works end-to-end with Rich output, symlink deployment on Linux, copy on Windows, and enriched audit logging

---

## Phase 5: User Story 2 — Interactive Menu Experience (Priority: P2)

**Goal**: Returning users see a polished, Rich-formatted interactive menu

**Independent Test**: Run `python setup.py --interactive` and verify menu renders with Rich styling, all 8 options are selectable, and each triggers the correct command

- [ ] T044 [US2] Rewrite `_interactive_menu(args)` in `setup.py` — replace plain `print()` menu with `ui.panel()` containing numbered options styled via Rich markup; replace `input("Select option")` with `rich.prompt.IntPrompt.ask("Select option", choices=...)` (with fallback to `input()` if Rich unavailable)
- [ ] T045 [US2] Add menu option descriptions in `setup.py` — each menu item gets a `[dim]description[/dim]` suffix explaining what it does (e.g., `1) Full install  [dim]detect → deps → fetch → deploy → verify[/dim]`)
- [ ] T046 [US2] Add confirmation sub-prompts for uninstall options in `setup.py` — replace `ui.confirm()` plain calls in menu options 7 and 8 with Rich-styled `Confirm.ask()` calls with colored warning text
- [ ] T047 [US2] Update `cmd_update()`, `cmd_rollback()`, `cmd_status()` in `setup.py` — replace inline `print(f"... {ui.C.GREEN}...")` with `ui.panel()` and `ui.success()` calls; remove all direct `ui.C.*` references
- [ ] T048 [US2] Update `cmd_uninstall()` in `setup.py` — replace inline `print(f"... {ui.C.GREEN}...")` with `ui.panel("Uninstall completed.", title="🧹 Done", style="green")` at the end

**Checkpoint**: Interactive menu is Rich-formatted, all 8 options work, all commands use `ui.*` wrappers instead of raw `print()`/`ui.C.*`

---

## Phase 6: User Story 4 — Config Deployment Without Conflicts (Priority: P1)

**Goal**: Template patching produces correct platform values, symlinks/copies deploy without conflicts

**Independent Test**: Run `python setup.py --dry-run` on Linux and Windows, verify plan shows correct GPU API, shader separator, and deploy method for each platform

- [ ] T049 [US4] Add symlink detection to `verify()` in `deploy/verifier.py` — add a new check: if on Linux, verify `scripts/` and `shaders/` in config dir are symlinks pointing to valid targets; if broken symlink → report as failed check
- [ ] T050 [US4] Update line-ending normalization in `deploy/deployer.py` — ensure `_normalize_line_endings()` skips symlinked directories (normalize only the source files before symlinking, not after)
- [ ] T051 [P] [US4] Add `operation: "symlink"` as a valid operation type in `deploy/audit_log.py` `record_file()` documentation — update the docstring to include `"symlink"` alongside existing `"copy"`, `"modify"`, `"delete"`, `"backup"`, `"create"`

**Checkpoint**: Config deployment produces correct files on both platforms, symlinks verified on Linux, audit log records symlink operations

---

## Phase 7: User Story 5 — Safe Uninstall & Rollback (Priority: P3)

**Goal**: Uninstall respects audit log; rollback restores cleanly

**Independent Test**: Run install → uninstall with `--remove-deps` → verify pre-existing packages untouched; run install → rollback → verify backup restored

- [ ] T052 [US5] Update `_remove_deployed_files()` in `setup.py` — handle symlinks during uninstall: if `scripts/` is a symlink, `os.unlink()` instead of `shutil.rmtree()`; add `os.path.islink()` check before each removal
- [ ] T053 [US5] Update `rollback_config()` in `deploy/deployer.py` — after restoring backup (which contains real files), remove any remaining symlinks in config dir that pointed to the old deployed/ directory
- [ ] T054 [US5] Add diagnostic report to `cmd_uninstall()` in `setup.py` — after uninstall completes, if any items failed, call `audit_log.generate_diagnostic_report()` and display via `ui.panel()`
- [ ] T055 [US5] Update uninstall plan display in `deploy/planner.py` — ensure `build_uninstall_plan()` shows symlink-specific actions (e.g., `"remove symlink"` vs `"remove directory"`) by checking `os.path.islink()` on each target

**Checkpoint**: Uninstall handles symlinks, rollback cleans up stale symlinks, diagnostics shown on failure

---

## Phase 8: Gum Integration for Bash (Priority: P2)

**Goal**: `install.sh` uses Gum for interactive elements per Constitution Principle IV

**Independent Test**: Run `bash install.sh` on a system with Gum installed — verify styled prompts appear; run on a system without Gum — verify plain fallback works

- [ ] T056 [P] Add `_install_gum()` function to `install.sh` — detect OS (Arch/Ubuntu/macOS) and install `gum` via appropriate package manager; set `GUM_AVAILABLE=true` on success
- [ ] T057 [P] Add `_gum_available()` test function to `install.sh` — return 0 if `command -v gum` succeeds, 1 otherwise
- [ ] T058 Add `_styled_echo()` wrapper function to `install.sh` — if `_gum_available`, use `gum style --foreground "$color" "$text"`; else use `echo -e "\033[${ansi}m${text}\033[0m"`
- [ ] T059 Replace all `echo` output calls in `install.sh` with `_styled_echo` calls — update banner, step messages, success/error messages throughout the script
- [ ] T060 Replace `read -p` prompts in `install.sh` with `gum confirm` calls — wrap with fallback: `if _gum_available; then gum confirm "$prompt"; else read -p "$prompt [Y/n] " reply; fi`
- [ ] T061 Add `gum spin` wrapper for long operations in `install.sh` — wrap `git clone` and `pip install` commands with `gum spin --spinner dot --title "message" -- command`; fallback to running command directly with echo prefix

**Checkpoint**: `install.sh` uses Gum when available, falls back gracefully, all interactive elements are visually polished

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Final cleanup, documentation, and consistency validation

- [ ] T062 [P] Update `README.md` — add Rich dependency mention, update installation instructions to reflect new Gum-based install.sh experience
- [ ] T063 [P] Update `quickstart.md` in `specs/001-mpv-automation/quickstart.md` — add troubleshooting entry for "Rich not installed" fallback behavior
- [ ] T064 Run full dry-run validation — execute `python setup.py --dry-run` from project root and verify zero import errors, Rich output displays correctly, and all plan entries render in table format
- [ ] T065 Run `install.sh` validation — execute `bash -n install.sh` (syntax check) to verify no shell errors in Gum integration
- [ ] T066 Verify Constitution compliance — manually confirm: no `deploy/` file imports from `config/script-opts/` (Principle I); `install.sh` has `#!/usr/bin/env bash` (Principle III); Rich/Gum used for all output (Principle IV)
- [ ] T067 Commit and finalize — `git add -A && git commit -m "feat: implement MPV Auto-Deploy Automation (001-mpv-automation)"`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — **BLOCKS all user stories**
- **US3 (Phase 3)**: Depends on Phase 2 — detection can proceed first
- **US1 (Phase 4)**: Depends on Phase 2 — the main pipeline
- **US2 (Phase 5)**: Depends on Phase 2 — menu experience
- **US4 (Phase 6)**: Depends on Phase 4 (uses symlink infrastructure from US1)
- **US5 (Phase 7)**: Depends on Phase 4 (uses audit log enhancements from US1)
- **Gum (Phase 8)**: Independent of Python phases — can run in parallel
- **Polish (Phase 9)**: Depends on all previous phases

### User Story Dependencies

- **US3 (Detection)**: Can start immediately after Foundational — no story deps
- **US1 (Full Install)**: Can start immediately after Foundational — no story deps
- **US2 (Menu)**: Can start after Foundational — light integration with US1 commands
- **US4 (Config Deploy)**: Depends on US1 (symlink infrastructure)
- **US5 (Uninstall)**: Depends on US1 (audit log enhancements)

### Within Each User Story

- Models/entities before services
- Infrastructure before UI integration
- Core logic before error handling
- Each story complete before moving to next priority

### Parallel Opportunities

- Phase 1: T002 ∥ T003 (install.sh ∥ install.ps1)
- Phase 2: T008 ∥ T009 ∥ T010 ∥ T011 (success ∥ warn ∥ error ∥ info — different functions, same file but independent edits)
- Phase 3 ∥ Phase 8: Python detection (US3) can run in parallel with Bash Gum integration
- Phase 4: T029 ∥ T030 (audit_log error_context); T036 ∥ T037 (fetcher UI)
- Phase 5: T044–T048 all touch `setup.py` sequentially but are independent of Phase 3/4/6/7
- Phase 6: T051 independent (audit_log docstring)

---

## Parallel Example: User Story 1 (Phase 4)

```bash
# Parallel group 1 — different files:
Task T029: "Add error_context to record_file() in deploy/audit_log.py"
Task T033: "Update display_plan() in deploy/planner.py"
Task T036: "Wrap fetch_all() with ui.progress() in deploy/fetcher.py"

# Parallel group 2 — different files:
Task T037: "Add ui.spinner() to fetch_raw() in deploy/fetcher.py"
Task T038: "Wrap _install_one() with ui.spinner() in deploy/installer.py"
Task T040: "Update verify() table in deploy/verifier.py"

# Sequential (same file: deploy/deployer.py):
Task T024 → T025 → T026 → T027 → T028
```

---

## Implementation Strategy

### MVP First (US3 + US1 Only)

1. Complete Phase 1: Setup (install Rich)
2. Complete Phase 2: Foundational (migrate ui.py to Rich)
3. Complete Phase 3: US3 — Detection with Rich output
4. Complete Phase 4: US1 — Full install pipeline
5. **STOP and VALIDATE**: Run `python setup.py --dry-run` end-to-end

### Incremental Delivery

1. Setup + Foundational → Rich UI working ✅
2. Add US3 (Detection) → Test on Linux ✅
3. Add US1 (Full Install) → Test full pipeline ✅ (MVP!)
4. Add US2 (Menu) → Test interactive mode ✅
5. Add US4 (Config) → Verify symlinks ✅
6. Add US5 (Uninstall) → Verify safe removal ✅
7. Add Gum (Bash) → Test install.sh ✅
8. Polish → Final validation ✅

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Commit after each phase completion
- Stop at any checkpoint to validate story independently
- All `ui.C.*` references MUST be removed from all files by end of Phase 5
- Rich fallback MUST work in all files (import Rich failure → ANSI output)
