---

description: "Task list for spec 005: playlist drag-to-reorder (User Story 1)"
---

# Tasks: Playlist Drag-to-Reorder

**Input**: Design documents from `specs/005-playlist-drag-reorder/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md, contracts/
**Generated**: 2026-11-22, after Stage 9 review round 5 (0 Blockers; `.egm/implementation_readiness_report_round5.md`)

**Tests**: requested. The plan is test-first per area (plan "Test Strategy"): each test
task is written first and must fail before its implementation task.

**Scope**: User Story 1 only (plan decisions table). Write allowlist: plan "Project
Structure" (12 created, 11 modified, 2 deleted); nothing else may change.

**Standing rules** (AGENTS.md, plan Constitution Check): `pathlib` for new and changed
code; never `shell=True`; no secrets or personal paths; commit on `main` only when the
maintainer says so; run Python tests with the project venv and `PYTHONPATH=src`, and
Lua suites with `python tests/run_lua_tests.py`; all tests headless.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[US1]**: User Story 1, "Drag a playlist item to a new position"

---

## Phase 1: Setup (shared infrastructure)

**Purpose**: line-ending rules and the upstream fixture every suite uses (research R9).

- [X] T001 [P] Create `.gitattributes` marking `tests/fixtures/uosc-5.13.0/**` as `-text` and `tools/uosc_patches/*.lua` as `eol=lf` (plan C-001/FR-022 risk row)
- [X] T002 [P] Download `uosc.zip` for tag `5.13.0`, copy `scripts/uosc/elements/Menu.lua` unmodified to `tests/fixtures/uosc-5.13.0/elements/Menu.lua`, and check SHA-256 `0cbc42afbe72f3f76f069995744de1e772d706445ed7987d1bffaafed50f2f49` and 1831 lines (research R9)
- [X] T003 [P] Add uosc's `LICENSE` (LGPL-2.1, tag 5.13.0) as `tests/fixtures/uosc-5.13.0/LICENSE` and a provenance `tests/fixtures/uosc-5.13.0/README.md` (release URL, tag, hash, line count)

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: the fixture guard and the uosc pin that the patcher, deployer and release check rely on.

**⚠️ CRITICAL**: no User Story 1 work starts before this phase is done.

- [ ] T004 Write the fixture test in `tests/test_patch_uosc_playlist_reorder.py`: SHA-256 and 1831 lines equal the upstream values, no `b"\r"`, `.gitattributes` marks the fixture `-text` (plan Test Strategy "Fixture")
- [ ] T005 [P] Write the registry pin test (`uosc` `pin == "5.13.0"`) in `tests/test_deploy_uosc_reorder_patch.py`; it must fail first (plan Test Strategy "Registry")
- [ ] T006 Set the uosc `"pin"` from `None` to `"5.13.0"` in `deploy/registry.py` (C-007); T005 passes

**Checkpoint**: fixture and pin in place; the suites stay green.

---

## Phase 3: User Story 1 - Drag a playlist item to a new position (Priority: P1) 🎯 MVP

**Goal**: a mouse-only drag handle on the hovered playlist row; drag with a held-row
outline and a whole-row drop line; edge auto-scroll; one `playlist-move` one
event-loop turn after the release; cancel on Esc or any menu key, close, list update or
focus loss (per the accepted rules); deployed as a byte-reversible patch of uosc's
`elements/Menu.lua`, applied to the prepared copy before `replace_items`.

**Independent Test**: with a 30-item local playlist playing item 5, drag item 20 to
position 2: the order is right, item 5 plays on uninterrupted and keeps its marker
(spec US1; quickstart §4 steps 1-3).

### Payload (Lua), test-first (research R4, R5, R7, R10; data-model "Drag session")

- [ ] T007 [US1] Write `tests/lua/test_playlist_reorder.lua` with the R10 stubs (cursor bus `on`/`trigger(event, zone_fn)` over the live handler table, `mp.add_timeout` recording pending callbacks, `mp.get_property`/`get_property_number` backed by the emulated playlist, recording `ass`, emulated `playlist-move`) and every case in the plan's Lua row: threshold, pointer → gap table, 50 random drags (SC-002), depth and `dt` cap, off-window freeze on all four sides and `math.huge`, deferred commit (pending until the timer; Esc/close/`Menu:update` before it → no move; one timer per release; gap frozen; `outside` judged at release), stale-playlist guard, new press after start cancels, own press does not, focus rules, search mid-drag, hover restore after every exit, stale `drag_last_y`/`is_dragging`/fling reset, start refusals, no handle outside the menu, `item.active` never written
- [ ] T008 [US1] Write the payload `tools/uosc_patches/playlist_reorder.lua` to the R4 Payload API (`reorder_off_window` first, then `reorder_enabled`, `reorder_gap`, `reorder_start`, `reorder_end`, `reorder_move`, `reorder_release`, `reorder_commit`, `reorder_depth`, `reorder_tick`, `reorder_handle`, `reorder_draw`); ≤ 149 lines, LF, tabs (C-002); T007 passes via `python tests/run_lua_tests.py`

### Patcher (Python), test-first (contracts/uosc-reorder-patch.md; research R3, R4, R12)

- [ ] T009 [US1] Extend `tests/test_patch_uosc_playlist_reorder.py` with the patcher tests: each of the 8 anchors matches once (`verify_hash=False`); `unpatch(patch(f)) == f`; hunks do not overlap; FR-006 highlight lines untouched; handle hook after the last `primary_click` (R5); the `menu-key` hook right after `if info.event == 'up' then return end`; budget (payload ≤ 149, `Menu.lua` +≤ 159, 0 replaced); `PAYLOAD_SHA256` matches the payload file; idempotency (`st_mtime_ns`/`st_ino` unchanged); R12 states including a patched copy of non-pinned bytes → `UNEXPECTED_UPSTREAM` without raising and version-free `MARKER_TOKEN` detection; all-or-nothing with a broken anchor; `OSError` on replace → original untouched, temp removed, `skipped`; no `\r`; CLI exit codes and output lines
- [ ] T010 [US1] Create `tools/patch_uosc_playlist_reorder.py` constants and the 8-hunk table exactly as research R4 (`PATCH_NAME`, `PATCH_VERSION`, `MARKER`, `MARKER_TOKEN`, `PAYLOAD_PATH`/`PAYLOAD` read at import, `PAYLOAD_SHA256`, `TARGET`, `PIN`, `EXPECTED_UPSTREAM_SHA256`, `HUNKS`, `PatchState`, `Hunk`, `AnchorFailure`, `PatchResult`)
- [ ] T011 [US1] Implement the pure functions `check_anchors`, `detect_state` (R12 order), `patch_bytes`, `unpatch_bytes` in `tools/patch_uosc_playlist_reorder.py` (bytes only, no I/O)
- [ ] T012 [US1] Implement `apply(dir, *, unpatch=False)` (atomic temp write, `tmp.chmod(st.st_mode)`, `Path.replace`, `OSError` → `skipped`) and the CLI (`--uosc-dir` default from `get_default_uosc_dir()` in `tools/patch_uosc_timeline_thumb.py`, `--unpatch`, `--check`, specified output lines) in `tools/patch_uosc_playlist_reorder.py`; T004 and T009 pass; patcher ≤ 300 lines

### Summary warnings, test-first (plan "Summary warnings")

- [ ] T013 [P] [US1] Add Warnings tests to `tests/test_ui_summary.py` (exact Rich lines with `soft_wrap=True`, ANSI lines with the conditional ` -- detail`, count order succeeded/skipped/warnings/failed, `warn` rows not counted as failed) and to `tests/test_ui_protocol.py` (`log` warn per row with `_proto.plain(...)`, not in the `summary` event's `failed` list)
- [ ] T014 [US1] Implement the Warnings group in `summary()` in `deploy/ui.py`; T013 passes and no existing assertion changes (plan Test Strategy "Regression")

### Deployer, test-first (contracts/uosc-reorder-patch.md "Deployer integration"; research R1, R2)

- [ ] T015 [US1] Write the integration tests in `tests/test_deploy_uosc_reorder_patch.py`: the real `deploy()` with a staged uosc; patch runs on `prepared` before `replace_items` (call-order spy, install and update); staged and nothing-staged; second update leaves live bytes unchanged; hash mismatch → update shows the patch once in the Warnings block with no `ui.warn`, exit 0, live `elements/Menu.lua` equals the fetched bytes (SC-008); install lists it under Warnings and exits 0; install `verify_callback` failure and update `os.replace` failure restore the old `scripts/`
- [ ] T016 [US1] Add `prepare_hook=None` to `update_assets(...)` in `deploy/transaction.py`, called on the prepared tree before `asset_manifest`/`replace_items` (transaction.py:461-463)
- [ ] T017 [US1] Give the fake `update_assets` in `tests/test_update_regenerates_mpv_conf.py` a `prepare_hook=None` parameter (the only existing test double that changes)
- [ ] T018 [US1] Implement `_patch_prepared_uosc(prepared, staging, config_dir, lockfile)` in `deploy/deployer.py` per the patch contract (lazy `from tools.patch_uosc_playlist_reorder import apply`, staged/live source, version from the lockfile or `tx.MANIFEST` read as UTF-8 with the named exceptions, status → row table)
- [ ] T019 [US1] In `deploy/deployer.py`: delete the local `from pathlib import Path` at :1455, wire `_patch_prepared_uosc` into `deploy()` (before `replace_items`) and `cmd_update()` (as `prepare_hook`), with update showing a skipped patch only through `ui.summary`; T015 passes

### Release check, test-first (contracts/uosc-release-check.md; research R8, R12; C-008)

- [ ] T020 [P] [US1] Write `tests/test_uosc_release_check.py` per the contract test table: SC-009 on the fixture (and a broken `menu-key` anchor), hung server, trickled body, trickled headers → exit 2 within 5 s, HTTP 500, invalid zip, missing asset or member, token sent only to `api.github.com`, CLI smoke with a list argv
- [ ] T021 [US1] Implement `tools/check_uosc_release.py` (`API_URL`, `run(api_url, download_timeout)`, one 120 s monotonic deadline with per-read timeouts and the `threading.Timer` watchdog, in-memory zip, `fetcher` limits, exact output strings with `{N:g}`); T020 passes
- [ ] T022 [US1] Add `.github/workflows/uosc-release-check.yml` (weekly and `workflow_dispatch`, `permissions: contents: read`, step `timeout-minutes: 5`, job `timeout-minutes: 10`)

**Checkpoint**: User Story 1 works end to end in tests: payload, patcher, deployer,
summary and release check, with every suite green.

---

## Phase 4: Polish, verification and retirement

- [ ] T023 [P] Add the AST scan to `tests/test_repo_hygiene.py`: no `shell=True` keyword in tracked `*.py` outside `VENDORED_PREFIXES`, reusing `tracked`
- [ ] T024 Run quickstart §1: all Python suites (project venv, `PYTHONPATH=src`), `python tests/run_lua_tests.py`, `ruff check` and `ruff format --check`; all green
- [ ] T025 Run quickstart §2 (patcher by hand on a throwaway copy) and §3 (deploy twice; the second run changes nothing, FR-023)
- [ ] T026 Maintainer, on KDE Wayland: quickstart §4 steps 1-7 (SC-001, SC-004, SC-007, FR-006, step 5 Esc/menu key/Space/focus loss with the button held, step 6 off-window check with outcome (a) or (b) recorded, step 7 SC-003)
- [ ] T027 Maintainer, on Windows: repeat T026 (C-001 parity; steps 5-7 at least)
- [ ] T028 Run quickstart §5 (release check against the fixture, and `--latest` with network)
- [ ] T029 Only after T026 and T027 pass: delete `tools/patch_uosc_playlist_drag.py` and `tests/test_patch_uosc_playlist_drag.py` (C-006)
- [ ] T030 [P] Mark `docs/superpowers/specs/2026-09-09-uosc-playlist-drag-drop-design.md` and `docs/superpowers/plans/2026-09-09-uosc-playlist-drag-drop.md` superseded by spec 005 (C-006)
- [ ] T031 Add the feature to `CHANGELOG.md`

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Setup)**: none; T001-T003 can run together.
- **Phase 2 (Foundational)**: after Phase 1 (T004 needs the fixture from T002). Blocks Phase 3.
- **Phase 3 (US1)**: after Phase 2.
- **Phase 4**: T023 any time after Phase 2; T024-T028 after Phase 3; T029-T031 only after T026 and T027.

### Within User Story 1

- Payload: T007 → T008.
- Patcher: T009 → T010 → T011 → T012. T010 needs the payload file (T008) for `PAYLOAD_SHA256`.
- Summary: T013 → T014.
- Deployer: T015 → T016 → T017 → T018 → T019. T018 needs T012 (patcher `apply`) and T014 (Warnings rows).
- Release check: T020 → T021 → T022. T021 reuses the patcher's `check_anchors` and constants (T011).

### Parallel opportunities

- T001, T002, T003 (different files).
- T005 alongside T004.
- Inside Phase 3, three independent tracks once Phase 2 is done:
  - the payload → patcher track (T007-T012);
  - summary warnings (T013-T014);
  - the release-check tests (T020), which only need the fixture.
- T023 and T030 alongside other work.

## Parallel Example: User Story 1

```text
Track A: T007 → T008 → T009 → T010 → T011 → T012
Track B: T013 → T014
Track C: T020 (tests only, until T011 lands) → T021 → T022
Join:    T015 → T016 → T017 → T018 → T019 (needs A and B)
```

## Implementation Strategy

### MVP (User Story 1 is the whole scope)

1. Phases 1 and 2: fixture, `.gitattributes`, pin.
2. Phase 3 in track order; stop at the checkpoint and run every suite.
3. Phase 4 verification on KDE Wayland, then Windows (T026, T027). These manual
   checks gate retirement (T029-T031), as plan Phase 2 step 8 requires.

### Budget rule (plan decisions table, C-002)

If a payload that passes every Lua test exceeds 149 lines (or `Menu.lua` +159),
remove comment lines first; if it still exceeds, stop and report; do not edit the limit
without maintainer approval.

## Notes

- Every test task must fail before its implementation task.
- Commit only when the maintainer says "commit", on `main`, without `Co-Authored-By`.
- The prototype measurements (149 / 159, 29 stub checks) come from a throwaway
  prototype that is not in the repo; T007 and T008 rebuild it from research R4.
