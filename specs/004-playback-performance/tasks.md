# Tasks: Playback Performance — Display Sync Fixes

**Input**: Design documents from `specs/004-playback-performance/`
**Prerequisites**: plan.md (required), spec.md (required), research.md

**Organization**: Tasks target a single file (`config/mpv.conf.template`) with atomic, independently verifiable changes.

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

## Phase 3: User Story 1 — Reduce display-resample Jitter (Priority: P0) 🎯 MVP

**Goal**: Replace `tscale=oversample` with `tscale=linear` and add `video-timing-offset=0.01` in both `[live-action]` and `[anime]` profiles to reduce frame timing jitter on both Windows and Linux.

**Independent Test**: Play a 23.976 fps file at 143.981 Hz on either platform. Check Shift+I stats: VSync Jitter should drop from 0.8–0.9 to below 0.30, and Delayed frames should drop from 172 to below 50.

### Implementation for User Story 1

- [ ] T001 [US1] Replace `tscale=oversample` with `tscale=linear` in `[live-action]` profile in `config/mpv.conf.template`
- [ ] T002 [US1] Add `video-timing-offset=0.01` to `[live-action]` profile in `config/mpv.conf.template`
- [ ] T003 [US1] Replace `tscale=oversample` with `tscale=linear` in `[anime]` profile in `config/mpv.conf.template`
- [ ] T004 [US1] Add `video-timing-offset=0.01` to `[anime]` profile in `config/mpv.conf.template`

**Checkpoint**: Both profiles updated. Play a test file — jitter and delayed frames should be significantly reduced on both platforms.

---

## Phase 4: User Story 2 — Wayland Refresh Rate Stabilization (Priority: P1)

**Goal**: Add a conditional `[wayland-144hz-fix]` profile that forces `override-display-fps=143.981` on Linux/Wayland only, compensating for KDE Plasma's unstable presentation timing estimation.

**Independent Test**: Play a 23.976 fps file on KDE Plasma Wayland at 143.981 Hz. Check Shift+I stats: VSync Ratio should stabilize near 6 instead of wandering around 5.

### Implementation for User Story 2

- [ ] T005 [US2] Add `[wayland-144hz-fix]` conditional profile with `override-display-fps=143.981` after the `[protocol.http]` profile in `config/mpv.conf.template`. Profile-cond must gate to Wayland GPU context AND ~144 Hz display range only. Must use `profile-restore=copy`.

**Checkpoint**: Linux/Wayland VSync Ratio should stabilize near 6. Windows behavior must be unaffected — verify the profile does NOT activate on Windows.

---

## Phase 5: User Story 3 — Profile Compatibility (Priority: P1)

**Goal**: Add VRR/G-Sync documentation comment and verify no existing profile behavior is broken.

**Independent Test**: Play one file from each profile category (live-action local file, anime local file, YouTube stream). Verify each profile's video-sync mode is correct and no regression occurs.

### Implementation for User Story 3

- [ ] T006 [US3] Add VRR/Adaptive Sync documentation comment block before the `[live-action]` profile section in `config/mpv.conf.template`

**Checkpoint**: Comments present. All profiles functional — `[live-action]` and `[anime]` use `display-resample`, `[protocol.https]` uses `audio`.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T007 Verify `config/mpv.conf.template` still contains all required template placeholders (`{{SHADER_SEP}}`, `{{GPU_API}}`, `{{HWDEC}}`, `{{VO}}`, `{{BORDER}}`, `{{LINUX_VISUAL_TUNING}}`)
- [ ] T008 Verify zero files changed outside `config/` directory — `git diff --name-only` must show only `config/mpv.conf.template`
- [ ] T009 Commit and push changes to `004-playback-performance` branch

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 3 (US1 — Jitter Fix)**: No dependencies — can start immediately
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
3. If jitter improved → proceed to US2 and US3
4. If not improved → investigate further before continuing

### Full Implementation

1. T001–T004: Core jitter fix (both profiles)
2. T005: Wayland conditional profile
3. T006: VRR documentation
4. T007–T008: Verification
5. T009: Commit and push

---

## Notes

- All 9 tasks target ONE file: `config/mpv.conf.template`
- Tasks are ordered for sequential execution to avoid edit conflicts
- T001–T004 are the MVP — test after these before continuing
- T005 must NOT activate on Windows — verify with profile-cond
- T007–T008 are validation gates before committing
