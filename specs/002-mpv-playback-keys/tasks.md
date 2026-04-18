# Tasks: MPV Playback Keys & Config Tuning

**Input**: Design documents from `specs/002-mpv-playback-keys/`  
**Prerequisites**: plan.md (required), spec.md (required for user stories)

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: User Story 1 — Resolve Keybinding Conflicts (Priority: P1) 🎯 MVP

**Goal**: Eliminate all keybinding conflicts between installed scripts so every key triggers exactly one action.

**Independent Test**: Press `h` → memo history opens. Press `B` → SponsorBlock upvote fires. Press `n` → autosubsync menu opens. No key fires two scripts.

- [ ] T001 [P] [US1] Add conflict-free script keybinding section to `config/input.conf.template` — add `h script-binding memo-history`, `B script-binding sponsorblock_upvote`, `Shift+B script-binding sponsorblock_downvote`, `n script-binding autosubsync-menu`
- [ ] T002 [P] [US1] Fix SmartSkip `n` conflict in `config/script-opts/SmartSkip.conf` — change `cancel_autoskip_countdown_keybind=["esc", "n"]` to `cancel_autoskip_countdown_keybind=["esc"]`
- [ ] T003 [US1] Add keybinding quick-reference comment block at the top of `config/input.conf.template` — document all assigned keys grouped by category (Anime4K, Screenshots, Scripts, SmartSkip, SponsorBlock)

**Checkpoint**: Deploy and press each key during playback — every key fires exactly one action, zero conflicts

---

## Phase 2: User Story 2 — Lossless Screenshot Capture (Priority: P2)

**Goal**: Screenshots save as lossless PNG with descriptive filenames in a fixed directory.

**Independent Test**: Press `F1` during playback → check `~/Pictures/mpv-screenshots/` for a PNG file named `VideoName_HH-MM-SS.mmm.png`

- [ ] T004 [US2] Add screenshot settings block to `config/mpv.conf.template` — add `screenshot-format=png`, `screenshot-png-compression=0`, `screenshot-high-bit-depth=yes`, `screenshot-directory=~/Pictures/mpv-screenshots`, `screenshot-template="%F_%P"` after the shader cache section

**Checkpoint**: Take a screenshot, verify it's lossless PNG in the correct directory with the correct filename format

---

## Phase 3: User Story 3 — YouTube Playback Optimization (Priority: P2)

**Goal**: YouTube seeking is near-instant with optimal quality selection and aggressive caching, scoped to streaming URLs only.

**Independent Test**: Open a YouTube URL, seek forward 30s → resumes within 2s. Seek backward → instant. Local files unaffected.

- [ ] T005 [US3] Add `[protocol.https]` auto-profile to `config/mpv.conf.template` — add `ytdl-format`, `cache=yes`, `demuxer-max-bytes=800M`, `demuxer-max-back-bytes=200M`, `demuxer-readahead-secs=300`, `hr-seek=yes`, `hr-seek-framedrop=no`, `interpolation=no`, `video-sync=audio`
- [ ] T006 [US3] Add `[protocol.http]` alias profile to `config/mpv.conf.template` — add `profile=protocol.https` so HTTP URLs also use the streaming profile

**Checkpoint**: Play YouTube URL, verify fast seeking. Play local file, verify default cache settings apply (500M not 800M)

---

## Phase 4: Polish & Verification

**Purpose**: Final validation and commit

- [ ] T007 Verify no regressions — run `python3 setup.py --verify` from project root to confirm all existing checks still pass
- [ ] T008 Manual keybinding test — play a local video and press `h`, `B`, `Shift+B`, `n`, `g`, `G`, `>`, `<`, `F1`, `F2` to confirm each fires the correct action
- [ ] T009 Commit all changes — `git add -A && git commit -m "feat: resolve keybinding conflicts, add lossless screenshots, optimize YouTube seeking (002-mpv-playback-keys)"`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (US1 — Keybindings)**: No dependencies — can start immediately. This is the MVP.
- **Phase 2 (US2 — Screenshots)**: Independent of Phase 1 — can run in parallel.
- **Phase 3 (US3 — YouTube)**: Independent of Phase 1 and 2 — can run in parallel.
- **Phase 4 (Polish)**: Depends on all three phases being complete.

### Parallel Opportunities

All three user story phases touch **different sections** of the same files, but the edits are non-overlapping:

- `input.conf.template` — only Phase 1 (keybindings section)
- `mpv.conf.template` — Phase 2 (screenshot block) and Phase 3 (YouTube profile) are in separate sections
- `SmartSkip.conf` — only Phase 1

T001 and T002 can run in parallel (different files). T004, T005, T006 edit `mpv.conf.template` in different sections but should run sequentially.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Keybinding conflict resolution (T001 + T002 + T003)
2. **STOP and VALIDATE**: Test every key — zero conflicts
3. Continue to Phase 2 + 3

### Full Delivery

1. Phase 1: Keybindings → Test
2. Phase 2: Screenshots → Test
3. Phase 3: YouTube → Test
4. Phase 4: Final verification + commit

---

## Notes

- Total tasks: **9**
- All changes are **config-only** — no Python/Bash code changes needed
- Files modified: `config/input.conf.template`, `config/mpv.conf.template`, `config/script-opts/SmartSkip.conf`
- Commit after all tasks complete (single atomic commit)
