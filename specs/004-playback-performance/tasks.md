# Tasks: Playback Performance — Display Sync Fixes

**Input**: Design documents from `specs/004-playback-performance/`
**Prerequisites**: plan.md (required), spec.md (required), research.md

**Organization**: Tasks target a single file (`config/mpv.conf.template`) with atomic, independently verifiable changes.
**Status**: Implemented — verified on Linux/Wayland 2026-11-19. Windows verification pending (T011). T001–T007 and T010 done; T008, T009, T011, T012 open. FR-002 / User Story 4 (nv12) is deferred and has no task.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- All file paths are relative to repository root

---

## Phase 1: Setup

**Purpose**: No setup needed — single config file change, no dependencies to install.

*(Phase skipped — no project initialization required)*

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: No foundational infrastructure needed — all changes are direct edits to one template file.

*(Phase skipped — no blocking prerequisites)*

---

## Phase 3: User Story 1 — Clean display-resample Frame Timing (Priority: P0) 🎯 MVP

**Goal**: Replace `tscale=oversample` with `tscale=linear` and add `video-timing-offset=0.01` in both `[live-action]` and `[anime]` profiles. Note: `scripts/smart_motion.lua` overrides `tscale` at runtime (`default_tscale`, currently `oversample`), so `linear` is not the effective runtime value. `video-timing-offset` is not used under `display-resample` (mpv manual); it only matters in VRR mode.

**Independent Test (manual)**: run the measurement command in [spec.md — Verification Method](spec.md#verification-method) for ≥ 60 s without seeking. Pass: `vsync-ratio` 6 (±0.05), delayed 0 and drop 0 after startup, mistimed not increasing after startup, `avsync` within ±0.005 s. `vsync-jitter` is recorded only.

### Implementation for User Story 1

- [x] T001 [US1] Replace `tscale=oversample` with `tscale=linear` in `[live-action]` profile in `config/mpv.conf.template`
- [x] T002 [US1] Add `video-timing-offset=0.01` to `[live-action]` profile in `config/mpv.conf.template`
- [x] T003 [US1] Replace `tscale=oversample` with `tscale=linear` in `[anime]` profile in `config/mpv.conf.template`
- [x] T004 [US1] Add `video-timing-offset=0.01` to `[anime]` profile in `config/mpv.conf.template`

**Checkpoint**: Both profiles updated. Linux/Wayland passes the criteria (2026-11-19). Windows not measured yet.

---

## Phase 4: User Story 2 — Wayland Refresh Rate Stabilization (Priority: P1)

**Goal**: Add a conditional `[wayland-144hz-fix]` profile that forces `display-fps-override = 143.981` on Linux/Wayland only, compensating for KDE Plasma's unstable presentation timing estimation.

**Independent Test (manual)**: Run the measurement command on KDE Plasma Wayland at 143.98 Hz. `vsync-ratio` must hold at 6 (±0.05) instead of wandering around 5.

### Implementation for User Story 2

- [x] T005 [US2] Add `[wayland-144hz-fix]` conditional profile with `display-fps-override = 143.981` between `[anime]` and `[protocol.file]` in `config/mpv.conf.template`. `profile-cond` gates on a 140–148 Hz `display-fps` (null-guarded) AND a Wayland GPU context (`current-gpu-context` or `options/gpu-context`, string or list). Uses `profile-restore=copy`.

**Checkpoint**: Linux/Wayland `vsync-ratio` holds at 6 (measured 2026-11-19). Windows behavior must be unaffected — verify the profile does NOT activate on Windows (not yet checked).

---

## Phase 5: User Story 3 — Profile Compatibility (Priority: P1)

**Goal**: Add VRR/G-Sync documentation comment and verify no existing profile behavior is broken.

**Independent Test (manual)**: Play one file from each profile category (live-action local file, anime local file, YouTube stream). Verify each profile's video-sync mode is correct and no regression occurs.

### Implementation for User Story 3

- [x] T006 [US3] Add VRR/Adaptive Sync documentation comment block before the `[live-action]` profile section in `config/mpv.conf.template`

**Checkpoint**: Comments present. All profiles functional — `[live-action]`, `[anime]` and `[protocol.https]` all use `display-resample` (`[protocol.https]` inherits it on purpose: at 144 Hz, 30 fps under `video-sync=audio` has a non-integer 4.8 cadence, and its large cache covers network jitter). `video-sync=audio` is only rendered with `--display-mode vrr`.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T007 Verify `config/mpv.conf.template` still contains all required template placeholders: `{{ANIME_CHAIN}}`, `{{BORDER}}`, `{{CSCALE}}`, `{{D3D11_FLIP}}`, `{{DITHER_DEPTH}}`, `{{DSCALE}}`, `{{GPU_API}}`, `{{GPU_CONTEXT}}`, `{{HWDEC}}`, `{{INTERPOLATION}}`, `{{LINUX_VISUAL_TUNING}}`, `{{NATIVE_FS}}`, `{{SCALE}}`, `{{SCREENSHOT_DIR}}`, `{{VIDEO_SYNC}}`, `{{VO}}` (`{{SHADER_SEP}}` is no longer in the template; the deployer applies it separately). Checked 2026-11-19: all 16 present (grep, not a measurement)
- [ ] T008 Verify no playback logic was added to `deploy/` or root-level scripts. The deployer (`deploy/deployer.py`) fills `{{VIDEO_SYNC}}` and `{{INTERPOLATION}}` from `_resolve_display_mode()` and resolves the Wayland GPU context (`{{GPU_CONTEXT}}`); only that pre-existing substitution is expected there (code review of the diff)
- [ ] T009 Commit and push changes
- [x] T010 [US1][US2] Linux/Wayland measurement (CachyOS, KDE Plasma Wayland, RTX 3060, 143.98 Hz, VRR off): full config meets the pass criteria over 60+ s (Black Clover S02E05). Results in [spec.md](spec.md#measurement-results--2026-11-19)
- [ ] T011 [US1][US3] Windows measurement (nv12 and p010 files) against the same pass criteria — **not measured yet**
- [ ] T012 Open item: `scripts/smart_motion.lua` needs its own spec or a section here. It sets `tscale`, `video-sync` and `interpolation` at runtime, overriding the profiles' `tscale=linear`. (The VRR-mode override is fixed since 2026-11-20, `1a38d97`: VRR mode seeds `smart_motion.conf` with `enabled=no`.)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 3 (US1 — Frame Timing Fix)**: No dependencies — can start immediately
- **Phase 4 (US2 — Wayland Fix)**: No dependency on Phase 3 — can run in parallel
- **Phase 5 (US3 — Documentation)**: No dependency on Phase 3 or 4 — can run in parallel
- **Phase 6 (Polish)**: Depends on Phases 3, 4, 5 completion

### User Story Dependencies

- **US1 (P0)**: Independent — tscale and timing-offset changes
- **US2 (P1)**: Independent — new conditional profile, no overlap with US1 edits
- **US3 (P1)**: Independent — comment block only

### Parallel Opportunities

All three user stories edit different sections of the same file and could theoretically be done in a single pass. However, they are separated for atomic verification:

```text
# Execute sequentially since they share one file:
T001–T004 (US1: tscale + timing-offset in both profiles)
T005      (US2: new Wayland conditional profile)
T006      (US3: VRR documentation comment)
T007–T009 (Polish: verification + commit)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Execute T001–T004 (change tscale + add timing-offset)
2. **STOP and TEST**: Play test files on both platforms
3. If the pass criteria hold (no delayed/dropped frames, ratio 6) → proceed to US2 and US3
4. If not improved → investigate further before continuing

### Full Implementation

1. T001–T004: Core frame-timing fix (both profiles)
2. T005: Wayland conditional profile
3. T006: VRR documentation
4. T007–T008: Verification
5. T009: Commit and push

---

## Notes

- T001–T006 edit ONE file: `config/mpv.conf.template`; T007–T009 are verification/commit gates
- Tasks are ordered for sequential execution to avoid edit conflicts
- T001–T004 are the MVP — test after these before continuing
- T005 must NOT activate on Windows or X11 — verify with profile-cond
- Measured targets (VSync ratio, delayed/dropped/mistimed frames, avsync; jitter recorded only) are manual checks on the maintainer's 143.98 Hz monitor using the `--term-status-msg` command in spec.md; the only automated coverage is `tests/test_audit_patches.py::test_spec_004_playback_performance_profiles` (string assertions)
- FR-002 / User Story 4 (nv12 mitigation) is deferred: no task
- T007–T008 are validation gates before committing
