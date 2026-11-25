---
description: "Task list for spec 006: control bar cleanup"
---

# Tasks: Control bar cleanup

**Input**: [spec.md](spec.md), [plan.md](plan.md)
**Gates**: `PYTHONPATH=src python -m unittest discover -s tests` (project venv) and `python tests/run_lua_tests.py`

## Phase 1: Spec

- [x] T001 Rename `specs/006-player-ui-themes/` to `specs/006-control-bar-cleanup/`; short spec with a "Dropped" section; plan and tasks; remove the theme-only documents; update `AGENTS.md` and `.specify/feature.json`.

## Phase 2: Remove the theme work

- [x] T002 One revert commit of P5 to P1 (`66e11bc`); tree equals `6c56baf`.
- [x] T003 Both suites green after the revert (742 Python tests, all Lua suites).

## Phase 3: Bar and More menu

- [x] T004 `scripts/more_menu.lua` (FR-002) and the stable-volume `user-data` in `scripts/player-toolbar.lua`.
- [x] T005 New `controls=` line in `config/script-opts/uosc.conf` (FR-001).
- [x] T006 Lua tests: entries, conditional rows, marks, live update, open/close toggle.

## Phase 4: Existing installs

- [x] T007 Replace the `controls=` line in a kept `uosc.conf` (FR-003).
- [x] T008 Remove the two spec-006 lines from a kept `mpv.conf` (FR-004).
- [x] T009 Delete a leftover `script-opts/ui_appearance.conf` (FR-005).
- [x] T010 Python tests for T007 to T009: other lines kept, idempotent, fresh install; the backup holds the old files (FR-006); `--dry-run` lists the changes and writes nothing (FR-007).

## Phase 5: Docs

- [x] T011 READMEs (English and Arabic), `docs/YOUTUBE_GUI.md`, the help overlay's "menu button" row, `CHANGELOG.md`.

## Phase 6: Checks

- [x] T012 Both suites green (757 Python tests, all Lua suites).
- [x] T013 Does "thumbfast: pipe open failed" happen before spec 006 (`eb6cd4c`)? Headless check; if it cannot reproduce, give the maintainer steps.
  Result (2026-11-25): yes. Headless mpv with `eb6cd4c` scripts and with the P5 config each log it once per file load: thumbfast respawns its helper and writes to `/tmp/thumbfast<pid>_1` about 1 ms before the helper creates that socket. Later requests succeed. `scripts/thumbfast.lua` is unchanged since `eb6cd4c`, so spec 006 is not the cause.
- [ ] T014 (manual, maintainer, last) Playback check on KDE Wayland, two runs from `--start=5:00`: A no UI use, B bar and More menu. Pass: `delayed=0` and `drop=0` in both.
